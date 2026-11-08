"""Ruh speaker (ناطق): MIZAN's own larger language model, prepared as a pilot.

The reader (``tadbir.ruh_reader``) is 3.48M parameters that tell languages
apart. The speaker is the same family grown to about 125M parameters, trained
to continue text in English, Hindi, Urdu, Arabic and Roman Hindi/Urdu, so that
it can later take over some of the language work MIZAN now asks the base model
for (``docs/ruh-speaker.md`` is the pre-registered plan; nothing here is
adopted, and nothing turns it on).

This module needs no torch. It holds what the pilot is (``CONFIGS``,
``PLANS``, ``SOURCES`` with their licence verdicts), prepares training shards
from licence-checked text, and checks them. The network and its training loop
are ``speaker_net`` (torch, imported only to train or score).

**Tokens.** A byte-level BPE: the 256 byte values are its alphabet and every
other token is a merge of them, so every string has a token sequence and back
(a byte fallback by construction). Pre-tokenised on whitespace only: the usual
GPT-2 split cuts Devanagari at every vowel sign, and on the reader's held-out
short messages a 32,768-token BPE read 3.85 bytes per Hindi token with it and
10.71 without it (``docs/ruh-speaker.md``). The tiny test configuration keeps
the reader's plain bytes (``ByteCodec``). Both give the speaker the reader's
end-of-document token and 16 language tokens.

**What reaches the loss.** Every document, before it is kept:

1. **its own script**: more than half of the letters of its first 2,048
   characters are in its language's script (``corpus.own_script``);
2. **not a seed's**: its words as read (``ruh_reader.group_of``) are no line of
   Lughah's corpus, in any split, so neither the reader's nor Lughah's held-out
   groups are ever trained on;
3. **once**: one document per group;
4. **held out**: one group in 200, by the SHA-256 of ``ruh-speaker-1:<group>``,
   is the held-out set (bits per byte) and is never trained on;
5. **never scripture**: ``ruh_reader.scripture`` on every piece of it (``pieces``:
   each line, cut into runs of at most 64 words as Iqtibas counts them, each
   overlapping the next by half, because Iqtibas reads only a message's first 64
   words), with Iqtibas's Quran texts in memory (prepare refuses without them);
   a document with one flagged piece is dropped whole;
6. **never hadith**: no run of ``HADITH_RUN`` words in a row is a run of the
   six books' text (Arabic folded as the Truth Gate reads it, and English).
   The reader's filter is about the Quran only; this is the speaker's addition.

``Sieve`` makes 5 affordable: on the reader's corpus ``scripture`` reads
4–24 kB a second on one core, so it is asked only of pieces that could be
flagged at all, by exact necessary conditions read from the same texts
(``Sieve.may_hold``; the test checks it never skips a piece ``scripture``
flags).

    cd backend && python -m tadbir.ruh_reader.speaker prepare --plan tiny --tsv DOCS --out DIR
    cd backend && python -m tadbir.ruh_reader.speaker train --shards DIR --out RUN
"""

from __future__ import annotations

import array
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.ruh_speaker")

VERSION = 1
SALT = "ruh-speaker-1"
HELD_OUT = 200  # one document group in 200 is held out for good
HELD_OUT_BYTES = 4_000_000  # per language read for bits per byte; the rest held out unread
SCRIPT_CHARS = 2048  # the script rule reads a document's first characters
MIN_LETTERS = 3
# Words in a row a document may share with the six books before it is a quote.
# A rule written down, not fitted: twice the Quran's run (``LEAST_SHARED``),
# because the books are ten times the mushaf's length and narrate in ordinary
# words. The manifest counts what it drops.
HADITH_RUN = 8
TR_GRAM = 8  # transliteration letters a held run's first window is looked up by
# Slot order is the reader's (its languages sorted), so a speaker reads a
# message under the same language tokens the reader does.
LANGUAGES = ("ar", "en", "hi", "hi-latn", "ur")
SPECIALS = 17  # the end token, then 16 language tokens

CONFIGS: dict[str, dict[str, Any]] = {
    # About 125M parameters: 32,768 × 768 tied embedding (25.2M) and 14
    # blocks of 7.08M: 124,278,528 in all (``docs/ruh-speaker.md``).
    "pilot": {
        "codec": "bpe",
        "vocab": 32768,
        "d_model": 768,
        "layers": 14,
        "heads": 12,
        "d_ff": 2048,
        "context": 1024,
        "dropout": 0.0,
    },
    "tiny": {
        "codec": "bytes",
        "vocab": 256 + SPECIALS,
        "d_model": 32,
        "layers": 2,
        "heads": 2,
        "d_ff": 64,
        "context": 64,
        "dropout": 0.0,
    },
}

PLANS: dict[str, dict[str, Any]] = {
    # 2.5B tokens of 1,024 in batches of 32 × 8 (262,144 tokens a step).
    "pilot": {
        "tokens": 2_500_000_000,
        "batch": 32,
        "accumulate": 8,
        "lr": 1e-3,
        "min_lr": 0.1,  # of the peak, at the end of the cosine
        "warmup": 200,
        "weight_decay": 0.1,
        "clip": 1.0,
        "checkpoint_seconds": 1200.0,
        "evaluate_every": 1000,
        "seed": 0,
        "compile": True,
    },
    "tiny": {
        "tokens": 64 * 4 * 8,
        "batch": 4,
        "accumulate": 1,
        "lr": 3e-3,
        "min_lr": 0.1,
        "warmup": 2,
        "weight_decay": 0.1,
        "clip": 1.0,
        "checkpoint_seconds": 0.0,  # every step
        "evaluate_every": 0,
        "seed": 0,
        "compile": False,
    },
}


# ── the sources and their licences ───────────────────────────────────────


@dataclass(frozen=True)
class Source:
    name: str
    label: str
    licence: str
    kind: str  # ``parquet`` (a Hugging Face dataset file), ``tatoeba``, ``massive``
    repo: str = ""
    revision: str = ""  # the dataset commit every file is read at
    files: tuple[tuple[str, str], ...] = ()  # (path in the repo, SHA-256 of its content)
    budget: int = 0  # bytes of training text kept from it; 0: all it gives


FINEWEB_2 = "af9c13333eb981300149d5ca60a8e9d659b276b9"
FINEWEB_EDU = "87f09149ef4734204d70ed1d046ddc9ca3f2b8f9"
ODC_BY = "ODC-By 1.0 (and Common Crawl's terms of use)"
SOURCES: tuple[Source, ...] = (
    Source(
        "fineweb-edu",
        "en",
        ODC_BY,
        "parquet",
        "HuggingFaceFW/fineweb-edu",
        FINEWEB_EDU,
        (
            (
                "sample/10BT/000_00000.parquet",
                "b1ba7b2ce4cb5ea6ef42dca40263eabb85f37700d01693a68e9b30a31d78e871",
            ),
            (
                "sample/10BT/001_00000.parquet",
                "3fcf2dc69cd52503986276d3d2d26a8c356d0f2ea28a0de4fdbda8cf87755693",
            ),
        ),
        4_500_000_000,
    ),
    Source(
        "fineweb-2-hin_Deva",
        "hi",
        ODC_BY,
        "parquet",
        "HuggingFaceFW/fineweb-2",
        FINEWEB_2,
        (
            (
                "data/hin_Deva/train/000_00000.parquet",
                "071a6d4cc4b5a21fed9531b2de1bdc8b4be16d38fc35dde41f73b0bd7263adad",
            ),
        ),
        4_000_000_000,
    ),
    Source(
        "fineweb-2-urd_Arab",
        "ur",
        ODC_BY,
        "parquet",
        "HuggingFaceFW/fineweb-2",
        FINEWEB_2,
        (
            (
                "data/urd_Arab/train/000_00000.parquet",
                "a3e64b92cb606bca9ef522bb82d15828beef4825e8998bb43f6e142cc947338d",
            ),
        ),
        3_000_000_000,
    ),
    Source(
        "fineweb-2-arb_Arab",
        "ar",
        ODC_BY,
        "parquet",
        "HuggingFaceFW/fineweb-2",
        FINEWEB_2,
        (
            (
                "data/arb_Arab/train/000_00000.parquet",
                "814460aa1fab3ed2c98f0a64674aab5023b4bf9df25480dfbcc04e51513a0583",
            ),
        ),
        3_000_000_000,
    ),
    Source(
        "fineweb-2-hin_Latn",
        "hi-latn",
        ODC_BY,
        "parquet",
        "HuggingFaceFW/fineweb-2",
        FINEWEB_2,
        (
            (
                "data/hin_Latn/train/000_00000.parquet",
                "e26effecb80746f7917d0bc3576eb8aad7287b8e110218e59015851437dc97ea",
            ),
        ),
    ),
    Source(
        "fineweb-2-urd_Latn",
        "hi-latn",  # Lughah reads Roman Hindi and Roman Urdu as one language
        ODC_BY,
        "parquet",
        "HuggingFaceFW/fineweb-2",
        FINEWEB_2,
        (
            (
                "data/urd_Latn/train/000_00000.parquet",
                "82937843bfb27bd70f0f0c5914b25c46739f95adb4f17f91a80a7fbccff173bd",
            ),
        ),
    ),
    *(
        Source(f"tatoeba-{code}", label, "CC BY 2.0 FR (Tatoeba)", "tatoeba")
        for label, code in (("en", "eng"), ("hi", "hin"), ("ur", "urd"), ("ar", "ara"))
    ),
    # The train partition only: dev and test are the reader's measured slices.
    Source("massive", "", "CC BY 4.0 (MASSIVE 1.1, Amazon; built on SLURP)", "massive"),
)

# Considered and not used, with the reason (the doc and LICENSES.md say more).
REJECTED: dict[str, str] = {
    "Abhishekcr448/Hinglish-Everyday-Conversations-1M": (
        "MIT, but written by GPT-4o-mini (its card): OpenAI's terms forbid using output "
        "to develop competing models (docs/consent.md); the reader v1 trained on it, v2 does not"
    ),
    "ai4bharat/sangraha": (
        "card CC BY 4.0, but Synthetic is English Wikipedia (CC BY-SA) translated, i.e. "
        "share-alike re-licensed, and Verified holds OCR'd PDFs and transcribed films "
        "with no source per row"
    ),
    "ai4bharat/IndicCorpV2": "CC0 'packaging' of crawled text AI4Bharat does not own; no source per row",
    "statmt/cc100": "licence 'unknown' on its card, Common Crawl terms only; no source per row",
    "ai4bharat/samanantar": "CC BY-NC 4.0 on its card; Quran translations inside (Qamus's verdict)",
    "ai4bharat/BPCC": "share-alike re-licensed sub-sources (Qamus's verdict)",
    "LingoIITGN/PHINC": "card CC BY 4.0 over tweets its authors do not own: evaluation only",
    "Dakshina (google-research-datasets)": "CC BY-SA 4.0: evaluation only, as in Qamus",
    "Wikipedia": "CC BY-SA 4.0: share-alike; not in the first run, the owner's decision",
}


# ── documents and the rules ──────────────────────────────────────────────


@dataclass(frozen=True)
class Document:
    source: str  # ``<source name>:<id>``
    label: str
    text: str


def _rank(key: str) -> int:
    return int(hashlib.sha256(f"{SALT}:{key}".encode()).hexdigest()[:16], 16)


def held_out(group: str) -> bool:
    """One group in ``HELD_OUT``, fixed by SHA-256, never trained on."""
    return _rank(group) % HELD_OUT == 0


_ARABIC = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def pieces(text: str, size: int | None = None) -> list[str]:
    """The pieces ``scripture`` reads whole: each line, cut into runs of at
    most ``size`` words (Iqtibas's ``MAX_WORDS``) as Iqtibas counts them, each
    run starting half-way through the one before, so every span of up to half
    of ``size`` words lies inside one piece."""
    from .. import iqtibas

    size = size or iqtibas.MAX_WORDS
    found: list[str] = []
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        if len(iqtibas.tokens(line)) <= size:
            found.append(" ".join(words))
            continue
        counts = [len(iqtibas.tokens(word)) for word in words]
        start = 0
        while start < len(words):
            end, held = start, 0
            while end < len(words) and held + counts[end] <= size:
                held += counts[end]
                end += 1
            end = max(end, start + 1)
            found.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            step, half = start, 0
            while step < end and half + counts[step] <= held // 2:
                half += counts[step]
                step += 1
            start = max(step, start + 1)
    return found


def _grams(words: Sequence[str], n: int) -> Iterator[tuple[str, ...]]:
    return (tuple(words[i : i + n]) for i in range(len(words) - n + 1))


class Sieve:
    """Which pieces ``ruh_reader.scripture`` could flag at all.

    ``scripture`` flags a piece when (1) Lughah reads a part of it as quoted
    Quran, (2) it shares ``LEAST_SHARED`` words in a row with the Uthmani sample,
    (3) the mushaf holds such a run of it, or (4) Iqtibas finds a span of at
    least ``LEAST_SHARED`` of its first ``MAX_WORDS`` words that a Quran text
    holds word for word, and that span is more likely a quote. Each needs a
    condition read here by set lookups:

    - (2) and (3) need Arabic words (``muqabala.words`` reads only those): a
      piece without Arabic letters cannot meet them; one with them is checked
      against every ``LEAST_SHARED``-word run of the sample and of the mushaf;
    - (4) needs the span's first ``LEAST_SHARED`` words held in order inside
      one line of a word view, or their letters inside the transliteration;
    - (1) is read for every piece with Arabic letters. Lughah's quote class is
      the vowelled Uthmani text, so a piece in another script is not read for
      it: the Quran in other scripts is (4)'s to find. On the reader's own
      corpus Lughah read no line without Arabic letters as a quote
      (``docs/ruh-speaker.md``).

    A piece no condition holds for is not asked; every other one is asked of
    ``scripture`` itself.
    """

    def __init__(self, quotes: Any = None):
        from . import LEAST_SHARED, _quote_shingles

        self.least = LEAST_SHARED
        self.shingles = _quote_shingles()
        self.views: list[frozenset[tuple[str, ...]]] = []
        self.mushaf: frozenset[tuple[str, ...]] = frozenset()
        self.tr_text = ""
        self.tr: frozenset[str] = frozenset()
        if quotes is None:
            return
        for view, text in quotes.texts.items():
            if view == "tr":
                continue
            self.views.append(
                frozenset(
                    gram for line in text.split("\n") for gram in _grams(line.split(), self.least)
                )
            )
        self.mushaf = frozenset(_grams(quotes.mushaf.split(), self.least))
        self.tr_text = quotes.texts.get("tr", "")
        self.tr = frozenset(
            line[i : i + TR_GRAM]
            for line in self.tr_text.split("\n")
            for i in range(len(line) - TR_GRAM + 1)
        )

    def _held(self, text: str) -> bool:
        from .. import iqtibas

        found = iqtibas.tokens(text)[: iqtibas.MAX_WORDS]
        for gram in _grams(found, self.least):
            if any(gram in view for view in self.views):
                return True
            if self.tr_text:
                letters = iqtibas._letters(gram)
                if len(letters) >= TR_GRAM and letters[:TR_GRAM] not in self.tr:
                    continue
                if self.tr_text.find(letters) >= 0:
                    return True
        return False

    def may_hold(self, text: str) -> bool:
        from .. import lughah, muqabala

        if not text.strip():
            return False
        if _ARABIC.search(text):
            if lughah.quoted(text):
                return True
            folded = [word.folded for word in muqabala.words(text)]
            if any(g in self.shingles or g in self.mushaf for g in _grams(folded, self.least)):
                return True
        return self._held(text)


class Hadith:
    """Runs of ``HADITH_RUN`` words of the six books (``hadith_index.BOOKS``):
    Arabic as the Truth Gate folds it, English as Iqtibas reads words. Built
    from the hadith-api editions MIZAN already quotes from; 64-bit hashes of
    the runs, so the books' runs fit in memory."""

    def __init__(self, arabic: Iterable[str] = (), english: Iterable[str] = ()):
        from .. import iqtibas, muqabala

        held: set[int] = set()
        for text in arabic:
            held.update(map(_hash, _grams([w.folded for w in muqabala.words(text)], HADITH_RUN)))
        for text in english:
            held.update(map(_hash, _grams(iqtibas.tokens(text), HADITH_RUN)))
        self.held = frozenset(held)

    def __call__(self, text: str) -> bool:
        from .. import iqtibas, muqabala

        if not self.held:
            return False
        folded = [w.folded for w in muqabala.words(text)] if _ARABIC.search(text) else []
        return any(_hash(g) in self.held for g in _grams(folded, HADITH_RUN)) or any(
            _hash(g) in self.held for g in _grams(iqtibas.tokens(text), HADITH_RUN)
        )


def _hash(gram: tuple[str, ...]) -> int:
    return int.from_bytes(hashlib.blake2b(" ".join(gram).encode(), digest_size=8).digest())


@dataclass
class Judge:
    """The rules a worker reads one document by (``prepare`` keeps the order,
    the groups seen and the budgets)."""

    seed_groups: frozenset[str]
    scripture: Callable[[str], bool]
    hadith: Callable[[str], bool]
    sieve: Sieve | None = None

    def __call__(self, document: Document) -> tuple[str | None, str]:
        from . import corpus, group_of

        text = document.text.replace("\r\n", "\n").strip()
        if sum(1 for char in text[:SCRIPT_CHARS] if char.isalpha()) < MIN_LETTERS:
            return "length", ""
        if not corpus.own_script(text[:SCRIPT_CHARS], document.label):
            return "script", ""
        group = group_of(text)
        if group in self.seed_groups:
            return "seed words", group
        for piece in pieces(text):
            if (self.sieve is None or self.sieve.may_hold(piece)) and self.scripture(piece):
                return "scripture", group
            if self.hadith(piece):
                return "hadith", group
        return None, group


_judge: Judge | None = None


def _judged(document: Document) -> tuple[str | None, str]:
    assert _judge is not None
    return _judge(document)


def judged(
    documents: Iterable[Document], judge: Judge, workers: int
) -> Iterator[tuple[Document, str | None, str]]:
    """(document, rule or None, group) in the documents' order; with workers,
    forked processes share the parent's loaded texts."""
    global _judge
    _judge = judge
    if workers <= 1:
        for document in documents:
            yield (document, *judge(document))
        return
    import multiprocessing

    def read(pool: Any, batch: list[Document]) -> Iterator[tuple[Document, str | None, str]]:
        for document, (rule, group) in zip(
            batch, pool.map(_judged, batch, chunksize=64), strict=True
        ):
            yield document, rule, group

    batch: list[Document] = []
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        for document in documents:
            batch.append(document)
            if len(batch) >= 256 * workers:
                yield from read(pool, batch)
                batch = []
        if batch:
            yield from read(pool, batch)


# ── the token codecs ─────────────────────────────────────────────────────


class ByteCodec:
    """The reader's tokens: the 256 bytes, the end, 16 language tokens."""

    kind = "bytes"
    end = 256
    vocab = 256 + SPECIALS

    def lang(self, slot: int) -> int:
        return 257 + slot

    def encode(self, texts: Sequence[str]) -> list[list[int]]:
        return [list(text.encode("utf-8")) for text in texts]

    def decode(self, ids: Sequence[int]) -> str:
        return bytes(i for i in ids if i < 256).decode("utf-8", errors="replace")

    def special(self, token: int) -> bool:
        return token >= 256

    def describe(self) -> dict:
        return {"kind": self.kind, "vocab": self.vocab}


class BpeCodec:
    """Byte-level BPE (Hugging Face ``tokenizers``): ids 0..16 are the end and
    the language tokens, then the 256 bytes, then the merges."""

    kind = "bpe"
    end = 0

    def __init__(self, path: Path):
        from tokenizers import Tokenizer

        self.path = path
        self.tokenizer = Tokenizer.from_file(str(path))
        self.vocab = self.tokenizer.get_vocab_size()

    def lang(self, slot: int) -> int:
        return 1 + slot

    def encode(self, texts: Sequence[str]) -> list[list[int]]:
        return [item.ids for item in self.tokenizer.encode_batch(list(texts))]

    def decode(self, ids: Sequence[int]) -> str:
        return str(self.tokenizer.decode([i for i in ids if i >= SPECIALS]))

    def special(self, token: int) -> bool:
        return token < SPECIALS

    def describe(self) -> dict:
        return {"kind": self.kind, "vocab": self.vocab, "sha256": _sha256(self.path)}


def special_tokens() -> list[str]:
    return ["<end>"] + [f"<lang:{slot}>" for slot in range(SPECIALS - 1)]


def train_bpe(texts: Iterable[str], vocab: int, path: Path) -> BpeCodec:
    """A byte-level BPE of ``vocab`` tokens learned from ``texts``,
    pre-tokenised on whitespace alone (a word keeps its leading space)."""
    from tokenizers import Regex, Tokenizer, decoders, models, pre_tokenizers, trainers

    tokenizer = Tokenizer(models.BPE())
    tokenizer.pre_tokenizer = pre_tokenizers.Sequence(
        [
            pre_tokenizers.Split(Regex(r"\s*\S+|\s+"), behavior="isolated"),
            pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False),
        ]
    )
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab,
        special_tokens=special_tokens(),
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=False,
    )
    tokenizer.train_from_iterator(texts, trainer)
    path.parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(path))
    return BpeCodec(path)


def codec_of(shards: Path, described: dict) -> ByteCodec | BpeCodec:
    if described["kind"] == "bytes":
        return ByteCodec()
    path = shards / "tokenizer.json"
    if _sha256(path) != described["sha256"]:
        raise Mismatch("tokenizer.json changed since the shards were written")
    return BpeCodec(path)


# ── preparing the shards ─────────────────────────────────────────────────


class Mismatch(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_tokens(path: Path, ids: Iterable[int]) -> None:
    """Little-endian uint16, the layout ``speaker_net`` memory-maps."""
    values = array.array("H", ids)
    if sys.byteorder != "little":
        values.byteswap()
    with path.open("ab") as handle:
        values.tofile(handle)


@dataclass
class Counts:
    kept: Counter = field(default_factory=Counter)  # (source, split) -> documents
    kept_bytes: Counter = field(default_factory=Counter)
    dropped: Counter = field(default_factory=Counter)  # (source, rule) -> documents

    def to_dict(self) -> dict:
        def nested(counter: Counter) -> dict:
            found: dict[str, dict[str, int]] = defaultdict(dict)
            for (first, second), value in sorted(counter.items()):
                found[first][second] = value
            return dict(found)

        return {
            "kept": nested(self.kept),
            "kept_bytes": nested(self.kept_bytes),
            "dropped": nested(self.dropped),
        }


def select(
    documents: Iterable[Document],
    judge: Judge,
    out: Path,
    *,
    budgets: dict[str, int],
    workers: int = 1,
    deadline: float = math.inf,
) -> Counts:
    """Judge the documents in order and write the kept ones to
    ``text/<label>.train.jsonl`` and ``text/<label>.held.jsonl`` (the first
    ``HELD_OUT_BYTES`` of each language's held-out documents), until each
    language holds its budget of training bytes (0: no limit) or the deadline
    passes. Returns what was kept and dropped, by source and rule."""
    counts = Counts()
    folder = out / "text"
    if folder.exists():  # a selection cut short is started again, never patched
        for stale in folder.glob("*.jsonl"):
            stale.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    seen: set[bytes] = set()
    have: Counter = Counter()
    held: Counter = Counter()

    def wanted(label: str) -> bool:
        budget = budgets.get(label)
        return budget is not None and (budget == 0 or have[label] < budget)

    handles: dict[tuple[str, str], Any] = {}
    try:
        for document, rule, group in judged(
            (d for d in documents if wanted(d.label)), judge, workers
        ):
            origin = document.source.split(":", 1)[0]
            if rule is None and bytes.fromhex(group[:16]) in seen:
                rule = "duplicate"
            if rule is not None:
                counts.dropped[(origin, rule)] += 1
            else:
                seen.add(bytes.fromhex(group[:16]))
                size = len(document.text.encode("utf-8"))
                split = "held" if held_out(group) else "train"
                if split == "held" and held[document.label] >= HELD_OUT_BYTES:
                    split = "held, unread"  # held out for good, but not read
                elif split == "train" and not wanted(document.label):
                    split = "over budget"
                counts.kept[(origin, split)] += 1
                counts.kept_bytes[(origin, split)] += size
                if split in ("train", "held"):
                    (have if split == "train" else held)[document.label] += size
                    key = (document.label, split)
                    if key not in handles:
                        handles[key] = (folder / f"{document.label}.{split}.jsonl").open(
                            "a", encoding="utf-8"
                        )
                    row = {"source": document.source, "group": group, "text": document.text}
                    handles[key].write(json.dumps(row, ensure_ascii=False) + "\n")
            if time.monotonic() > deadline:
                counts.dropped[(origin, "prepare time")] += 1
                break
    finally:
        for handle in handles.values():
            handle.close()
    return counts


def _rows(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for row in handle:
            yield json.loads(row)


def _texts(out: Path, labels: Sequence[str], split: str) -> Iterator[tuple[str, str]]:
    for label in labels:
        for row in _rows(out / "text" / f"{label}.{split}.jsonl"):
            yield label, row["text"]


class _Shard:
    """One shard file being written, and what it holds."""

    def __init__(self, path: Path, label: str):
        self.path, self.label = path, label
        self.tokens = self.bytes = self.documents = 0
        path.unlink(missing_ok=True)

    def add(self, codec: ByteCodec | BpeCodec, slot: int, texts: Sequence[str]) -> None:
        stream: list[int] = []
        for ids in codec.encode(texts):
            stream += [codec.lang(slot), *ids, codec.end]
        _write_tokens(self.path, stream)
        self.tokens += len(stream)
        self.bytes += sum(len(text.encode("utf-8")) for text in texts)
        self.documents += len(texts)

    def record(self) -> dict:
        return {
            "file": self.path.name,
            "language": self.label,
            "tokens": self.tokens,
            "bytes": self.bytes,
            "documents": self.documents,
            "sha256": _sha256(self.path),
        }


def write_shards(
    out: Path,
    codec: ByteCodec | BpeCodec,
    labels: Sequence[str],
    tokens_per_shard: int = 1 << 30,
) -> dict[str, list[dict]]:
    """Each kept document as ``[language] tokens… [end]`` in uint16 shards:
    ``train-<language>-NNNNN.bin`` and ``held-<language>.bin`` beside the
    text, each with its SHA-256, tokens and the UTF-8 bytes of its text."""
    written: dict[str, list[dict]] = {"train": [], "held": []}
    for split in ("train", "held"):
        for label in labels:
            slot = LANGUAGES.index(label)
            number = 0
            name = f"train-{label}-{number:05d}.bin" if split == "train" else f"held-{label}.bin"
            shard = _Shard(out / name, label)
            batch: list[str] = []
            for _label, text in _texts(out, [label], split):
                batch.append(text)
                if len(batch) < 512:
                    continue
                shard.add(codec, slot, batch)
                batch = []
                if split == "train" and shard.tokens >= tokens_per_shard:
                    written[split].append(shard.record())
                    number += 1
                    shard = _Shard(out / f"train-{label}-{number:05d}.bin", label)
            if batch:
                shard.add(codec, slot, batch)
            if shard.documents:
                written[split].append(shard.record())
            else:
                shard.path.unlink(missing_ok=True)
    return written


def documents_from_tsv(path: Path, name: str) -> Iterator[Document]:
    """``id <TAB> label <TAB> text`` rows: test sources and hand-made sets."""
    for row in path.read_text(encoding="utf-8").splitlines():
        parts = row.split("\t", 2)
        if len(parts) == 3 and parts[2].strip():
            yield Document(f"{name}:{parts[0]}", parts[1], parts[2])


def prepare(
    out: Path,
    documents: Iterable[Document],
    *,
    plan: str = "pilot",
    budgets: dict[str, int] | None = None,
    sources: Sequence[dict] = (),
    scripture: Callable[[str], bool] | None = None,
    hadith: Callable[[str], bool] | None = None,
    workers: int = 1,
    seconds: float = math.inf,
    tokenizer_sample: int = 100_000_000,
    log: Callable[[str], None] = logger.info,
) -> dict:
    """Judge, select and write the shards for ``plan`` into ``out``; returns
    and writes ``shards.json``. Without ``scripture`` the full filter is used
    with Iqtibas's Quran texts in memory, and preparing is refused without
    them; without ``hadith`` the six books' runs are read from the editions on
    disk (``hadith_editions``), refused without them too."""
    from .. import iqtibas, lughah
    from . import corpus_digest, group_of, seeds
    from . import scripture as full

    config = CONFIGS[plan]
    began = time.monotonic()
    out.mkdir(parents=True, exist_ok=True)
    if scripture is None:
        from .corpus import full_scripture

        scripture = full_scripture()  # raises without the Quran's texts
    if hadith is None:
        arabic, english = hadith_editions()
        hadith = Hadith(arabic, english)
    labels = sorted(budgets) if budgets else list(LANGUAGES)
    budgets = budgets or dict.fromkeys(labels, 0)
    judge = Judge(
        frozenset(group_of(text) for text, _label in lughah.corpus()),
        scripture,
        hadith,
        Sieve(iqtibas.ready()) if scripture is full else None,
    )
    counts = select(
        documents, judge, out, budgets=budgets, workers=workers, deadline=began + seconds
    )
    log(f"speaker: selected {json.dumps(counts.to_dict()['kept_bytes'])}")
    if config["codec"] == "bpe":
        per_label = max(1, tokenizer_sample // max(1, len(labels)))

        def sample() -> Iterator[str]:
            for label in labels:
                taken = 0
                for _label, text in _texts(out, [label], "train"):
                    if taken >= per_label:
                        break
                    taken += len(text.encode("utf-8"))
                    yield text

        codec: ByteCodec | BpeCodec = train_bpe(sample(), config["vocab"], out / "tokenizer.json")
    else:
        codec = ByteCodec()
    written = write_shards(out, codec, labels)
    manifest = {
        "version": VERSION,
        "created": datetime.now(UTC).isoformat(),
        "plan": plan,
        "config": config,
        "codec": codec.describe(),
        "languages": list(LANGUAGES),
        "seeds_sha256": corpus_digest(seeds()),
        "rules": {
            "salt": SALT,
            "held_out": f"1/{HELD_OUT}",
            "held_out_bytes": HELD_OUT_BYTES,
            "script_chars": SCRIPT_CHARS,
            "hadith_run": HADITH_RUN,
            "pieces_words": iqtibas.MAX_WORDS,
            "scripture": "ruh_reader.scripture with Iqtibas"
            if scripture is full and iqtibas.ready() is not None
            else "given by the caller",
        },
        "budgets": budgets,
        "sources": list(sources),
        "rejected": REJECTED,
        **counts.to_dict(),
        "train": written["train"],
        "held_out": written["held"],
        "seconds": round(time.monotonic() - began, 1),
    }
    (out / "shards.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"speaker: {sum(s['tokens'] for s in written['train'])} training tokens in {out}")
    return manifest


def verify_shards(shards: Path) -> dict:
    """The shards' manifest, after every shard and the tokenizer match their
    SHA-256; raises ``Mismatch`` otherwise."""
    manifest: dict = json.loads((shards / "shards.json").read_text(encoding="utf-8"))
    for item in [*manifest["train"], *manifest["held_out"]]:
        if _sha256(shards / item["file"]) != item["sha256"]:
            raise Mismatch(f"{item['file']} changed since it was written")
    codec_of(shards, manifest["codec"])
    return manifest


# ── the pilot's own sources (downloaded on the pod) ──────────────────────


def fetch(source: Source, target: Path) -> list[dict]:
    """The source's pinned files, downloaded once (``huggingface_hub`` at the
    pinned commit) and refused when their SHA-256 is not the pinned one."""
    from huggingface_hub import hf_hub_download

    found = []
    for name, digest in source.files:
        path = Path(
            hf_hub_download(
                source.repo,
                name,
                repo_type="dataset",
                revision=source.revision,
                local_dir=str(target),
            )
        )
        actual = _sha256(path)
        if actual != digest:
            path.unlink(missing_ok=True)
            raise Mismatch(f"{source.repo}/{name}: SHA-256 {actual} is not the pinned {digest}")
        found.append({"file": name, "sha256": actual, "bytes": path.stat().st_size})
    return found


def parquet_documents(path: Path, source: Source) -> Iterator[Document]:
    import pyarrow.parquet as pq

    handle = pq.ParquetFile(str(path))
    for batch in handle.iter_batches(batch_size=1024, columns=["id", "text"]):
        for identifier, text in zip(
            batch.column("id").to_pylist(), batch.column("text").to_pylist(), strict=True
        ):
            if text:
                yield Document(f"{source.name}:{identifier}", source.label, str(text))


def interleave(
    streams: Mapping[str, Iterator[Document]], weights: Mapping[str, float]
) -> Iterator[Document]:
    """One stream of the languages' documents: always the next document of the
    language furthest below its share (bytes given so far over its weight),
    so a selection the clock cuts short is still balanced."""
    given: Counter = Counter()
    live = dict(streams)
    while live:
        label = min(live, key=lambda name: given[name] / weights[name])
        document = next(live[label], None)
        if document is None:
            del live[label]
            continue
        given[label] += len(document.text.encode("utf-8"))
        yield document


def pilot_documents(downloads: Path, record: list[dict]) -> Iterator[Document]:
    """Every pilot source's documents: the pinned files are fetched first
    (``record`` gets each file's SHA-256); Tatoeba's and MASSIVE's sentences
    come first, then the web documents of each language, interleaved by their
    budgets (a language with no budget weighs as the smallest that has one)."""
    from . import corpus

    small: list[Iterator[Document]] = []
    streams: dict[str, list[Iterator[Document]]] = defaultdict(list)
    for source in SOURCES:
        target = downloads / source.name
        if source.kind == "parquet":
            record.append({**asdict(source), "fetched": fetch(source, target)})
            streams[source.label] += [
                parquet_documents(target / name, source) for name, _digest in source.files
            ]
            continue
        name = source.name if source.kind == "tatoeba" else "massive"
        pinned = next(item for item in corpus.SOURCES if item.name == name)
        fetched = corpus.download(pinned, target)
        record.append({**asdict(source), "url": pinned.url, "fetched": [fetched]})
        if source.kind == "tatoeba":
            small.append(
                Document(line.source, line.label, line.text)
                for line in corpus.tatoeba(target / pinned.file, source.label)
            )
        else:  # the train partition only: dev and test are the reader's slices
            small.append(
                Document(line.source, line.label, line.text)
                for line in corpus.massive(target / pinned.file)
                if line.kind == "train"
            )
    for stream in small:
        yield from stream
    budgets = pilot_budgets()
    smallest = min(value for value in budgets.values() if value > 0)
    weights = {label: float(budgets[label] or smallest) for label in streams}
    joined = {
        label: (doc for stream in parts for doc in stream) for label, parts in streams.items()
    }
    yield from interleave(joined, weights)


def hadith_editions() -> tuple[list[str], list[str]]:
    """The six books' narrations in Arabic and English, from the hadith-api
    editions (``tadbir.hadith.API``), kept in ``$MIZAN_DATA_DIR/hadith`` as
    ``hadith_index`` keeps the English ones. Refused when one cannot be read."""
    import httpx

    from ..hadith import API
    from ..hadith_index import BOOKS, _data_dir

    folder = _data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    texts: dict[str, list[str]] = {"ara": [], "eng": []}
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        for language in texts:
            for book in BOOKS:
                path = folder / f"{language}-{book}.json"
                if not path.exists():
                    response = client.get(f"{API}/editions/{language}-{book}.min.json")
                    response.raise_for_status()
                    items = [
                        {"hadithnumber": item.get("hadithnumber"), "text": item.get("text", "")}
                        for item in response.json().get("hadiths", [])
                        if isinstance(item, dict)
                    ]
                    temporary = path.with_suffix(".part")
                    temporary.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
                    temporary.replace(path)
                rows = json.loads(path.read_text(encoding="utf-8"))
                texts[language] += [str(row.get("text", "")) for row in rows if row.get("text")]
    if not texts["ara"] or not texts["eng"]:
        raise RuntimeError("the six books' texts are not available; nothing was prepared")
    return texts["ara"], texts["eng"]


def pilot_budgets() -> dict[str, int]:
    """Training bytes per language: the sum of its sources' budgets (0 when a
    source of it has none: then all it gives)."""
    budgets: dict[str, int] = {}
    for source in SOURCES:
        if source.kind == "parquet":
            if source.budget == 0 or budgets.get(source.label) == 0:
                budgets[source.label] = 0
            else:
                budgets[source.label] = budgets.get(source.label, 0) + source.budget
    return budgets


# ── command line ─────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Prepare, train and check the Ruh speaker")
    commands = parser.add_subparsers(dest="command", required=True)
    making = commands.add_parser("prepare", help="judge the sources and write shards")
    making.add_argument("--out", type=Path, required=True)
    making.add_argument("--plan", choices=sorted(CONFIGS), default="pilot")
    making.add_argument("--tsv", type=Path, help="documents from a TSV instead of the sources")
    making.add_argument("--downloads", type=Path)
    making.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    making.add_argument("--seconds", type=float, default=math.inf)
    training = commands.add_parser("train", help="train from shards; resumes when it can")
    training.add_argument("--shards", type=Path, required=True)
    training.add_argument("--out", type=Path, required=True)
    training.add_argument("--plan", choices=sorted(PLANS), default=None)
    training.add_argument("--seconds", type=float, default=math.inf)
    training.add_argument(
        "--device",
        choices=("cuda", "mps", "cpu"),
        default=None,
        help="default: CUDA, else Apple silicon's GPU (mps), else the CPU",
    )
    training.add_argument(
        "--rows",
        type=int,
        default=None,
        help="windows per forward pass, a divisor of the plan's batch (memory only; "
        "the run, its data and its checkpoints are the same); default: the whole batch",
    )
    checking = commands.add_parser("verify", help="check the shards' SHA-256")
    checking.add_argument("--shards", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.command == "prepare":
        record: list[dict] = []
        if args.tsv:
            found = documents_from_tsv(args.tsv, args.tsv.stem)
            budgets = None
        elif args.plan != "pilot":
            parser.error("only the pilot reads the pinned sources; give --tsv")
        else:
            found = pilot_documents(args.downloads or args.out / "sources", record)
            budgets = pilot_budgets()
        manifest = prepare(
            args.out,
            found,
            plan=args.plan,
            budgets=budgets,
            sources=record,
            workers=args.workers,
            seconds=args.seconds,
            log=print,
        )
        print(json.dumps({k: manifest[k] for k in ("kept_bytes", "dropped", "codec")}, indent=1))
    elif args.command == "train":
        from . import speaker_net

        manifest = verify_shards(args.shards)
        report = speaker_net.train(
            args.shards,
            args.out,
            CONFIGS[manifest["plan"]],
            PLANS[args.plan or manifest["plan"]],
            seconds=args.seconds,
            device=args.device,
            rows=args.rows,
            log=print,
        )
        print(json.dumps({k: v for k, v in report.items() if k != "history"}, indent=1))
    else:
        manifest = verify_shards(args.shards)
        print(json.dumps({"train": len(manifest["train"]), "verified": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
