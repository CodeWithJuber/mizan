"""The Ruh reader's own corpus: licence-clean text that is not Lughah's seeds.

Lughah's seeds stay Lughah's. The reader learned from them alone at first
(about 200 KB), and its development bits per byte were still falling when its
time ran out; this corpus gives it more of each language to learn from, and a
slice of short requests people actually write to be judged on.

Sources (licences and notices in ``LICENSES.md`` beside this file):

- **Tatoeba** per-language exports (eng, hin, urd, ara), CC BY 2.0 FR. Every
  sentence id Lughah's seeds already use is left out. The exports change
  weekly, so each file's SHA-256 is recorded, not pinned.
- **MASSIVE 1.1** (Amazon, CC BY 4.0; built on SLURP, CC BY 4.0), pinned by
  SHA-256: en-US, hi-IN, ur-PK, ar-SA. The ``train`` partition is training
  text; the ``test`` partition's utterances of 3 to 8 words are the held-out
  slice of short requests (``short.tsv``), never trained on.
- **FineWeb-2** ``hin_Latn`` and ``urd_Latn`` (Hugging Face, ODC-By 1.0 and
  Common Crawl's terms), pinned by commit and SHA-256 as the speaker pins
  them: Roman Hindi/Urdu web text people wrote. One document in five (by
  SHA-256 of its id) is held out for good; the others are read in an order
  fixed by SHA-256 of their ids, each cut into short lines (``lines_of``).

**Never trained on: text a language model wrote** (``MODEL_WRITTEN``). v1
trained on Abhishekcr448/Hinglish-Everyday-Conversations-1M, which its card
says GPT-4o-mini wrote; MIZAN never trains on OpenAI's or Anthropic's output
(``docs/consent.md``), so since v2 it is a measurement source only
(``HINGLISH_1M``): its held-out rows are the Roman part of ``short.tsv`` (so
v1 and v2 are reported on the same slice) and of v1.1's and test 3's slices.
Lines of an older corpus from it are loaded as ``Corpus.written``, never as
training lines.

Every line, before it is kept for training:

1. **its own script**: more than half of its letters are written in the
   language's script (MASSIVE's ar-SA has utterances written in English only);
2. **not the seeds'**: neither a Tatoeba id the seeds use nor a line whose
   words as read (``ruh_reader.group_of``: letters and marks, lower case) are a
   seed's, in any split, so nothing Lughah's held-out or development groups
   hold is trained on;
3. **not held out here**: not a short message of the held-out slice, and
   (``measured``) not the words of any message ever measured, nor near them
   (``Near``);
4. **once**: one line per group;
5. **never scripture**: ``ruh_reader.scripture``, with Iqtibas's full texts in
   memory (the mushaf and the four translations Fihris downloads), so no
   Quranic span ever reaches the loss; with ``hadith`` (the speaker's rule,
   ``speaker.Hadith``) no run of 8 words of the six books either. A FineWeb-2
   document with one flagged line gives no line at all.

Lines are taken in an order fixed by SHA-256 of their source id, round robin
over a language's sources, until the language holds ``bytes_per_language``
bytes of words as read: the reader's training time, not the data, is what
bounds it, so each language gets an equal share.

Written to ``$MIZAN_DATA_DIR/corpora/ruh_reader/``: ``train.tsv`` (source id,
label, text), ``short.tsv`` (source id, label, group, text), and
``manifest.json`` (each source with its URL, licence and SHA-256, the seeds'
SHA-256 the corpus was built against, what was kept and dropped by each rule).
Downloads go to ``sources/<name>/`` there. Nothing of it is in git.

**Validation slices** (``build_validation``, v1.1): MASSIVE's ``dev``
partition and Roman Hindi/Urdu rows v1's build never read, none of them a
seed's, a training line's or a short message's words, split by SHA-256 into
a calibration half (κ and b are fitted there) and a gate half (the gate is
run there): ``validation.tsv`` (source, label, group, half, text) and
``validation.json``.

**Fresh slices** (``build_fresh``, test 3): English requests from CLINC150
(CC BY 3.0, not MASSIVE) and Roman Hindi/Urdu rows never read, none of them a
seen text's words or near them (``Near``), the Roman rows kept only where
Qamus reads a Hindi or Urdu word in them (``roman_words``): ``fresh.tsv``
(source, label, group, part, text), ``fresh.json``, and ``labels.tsv``, the
never-read rows labelled by hand to check that rule before it is used.

**v2's slices** (``build_v2``): messages people wrote that no model has been
trained on or measured on: English requests from BANKING77 (CC BY 4.0), and
Roman Hindi/Urdu from three sources, a third each (Dakshina's romanized
Wikipedia sentences, CC BY-SA 4.0; PHINC's code-mixed tweets, CC BY 4.0;
lines of FineWeb-2's held-out documents), the last two only where Qamus reads
two Hindi or Urdu words (``roman_words(…, least=2)``), split by SHA-256 into a
calibration half and a gate half: ``v2.tsv`` and ``v2.json``.

    cd backend && python -m tadbir.ruh_reader --corpus
"""

from __future__ import annotations

import bz2
import csv
import hashlib
import io
import itertools
import json
import logging
import math
import os
import re
import tarfile
from collections import Counter, defaultdict
from collections.abc import Callable, Container, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .speaker import SOURCES as SPEAKER_SOURCES

logger = logging.getLogger("mizan.ruh_reader.corpus")

VERSION = 2
SALT = "ruh-reader-corpus-1"  # the order lines are taken in
BYTES_PER_LANGUAGE = 900_000
MAX_BYTES = 192  # the reader's context: a longer line would be cut
MIN_LETTERS = 3
SHORT_WORDS = (3, 8)
SHORT_HINGLISH = 2000
OVERSELECT = 1.15  # candidates per budget byte, before the scripture check
SCRIPTS = {"en": "latin", "hi-latn": "latin", "hi": "devanagari", "ur": "arabic", "ar": "arabic"}


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    licence: str
    file: str
    sha256: str | None = None  # pinned content; None: recorded, not pinned
    labels: tuple[str, ...] = ()


MASSIVE_LOCALES = {"en": "en-US", "hi": "hi-IN", "ur": "ur-PK", "ar": "ar-SA"}
TATOEBA = {"en": "eng", "hi": "hin", "ur": "urd", "ar": "ara"}
HINGLISH_COMMIT = "cf040b1b80857c6038eb73ddad441f0b435e02a6"


def _fineweb(name: str) -> Source:
    """A FineWeb-2 Latin subset, pinned where the speaker pins it (one place)."""
    pinned = next(item for item in SPEAKER_SOURCES if item.name == name)
    ((path, digest),) = pinned.files
    return Source(
        name,
        f"https://huggingface.co/datasets/{pinned.repo}/resolve/{pinned.revision}/{path}",
        f"{pinned.licence}; {pinned.repo} at {pinned.revision}",
        Path(path).name,
        digest,
        ("hi-latn",),
    )


FINEWEB_LATIN = ("fineweb-2-hin_Latn", "fineweb-2-urd_Latn")
# What the reader trains on (since v2: no text a language model wrote).
SOURCES = (
    Source(
        "massive",
        "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz",
        "CC BY 4.0 (MASSIVE 1.1, Amazon; built on SLURP, CC BY 4.0)",
        "amazon-massive-dataset-1.1.tar.gz",
        "4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577",
        tuple(MASSIVE_LOCALES),
    ),
    *(
        Source(
            f"tatoeba-{code}",
            f"https://downloads.tatoeba.org/exports/per_language/{code}/{code}_sentences.tsv.bz2",
            "CC BY 2.0 FR (Tatoeba)",
            f"{code}_sentences.tsv.bz2",
            None,
            (label,),
        )
        for label, code in TATOEBA.items()
    ),
    *(_fineweb(name) for name in FINEWEB_LATIN),
)
# Written by a language model (its card says GPT-4o-mini): read to measure
# (v1's short slice, v1.1's and test 3's slices), never trained on.
HINGLISH_1M = Source(
    "hinglish-1m",
    "https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M"
    f"/resolve/{HINGLISH_COMMIT}/hinglish_conversations.csv",
    "MIT (Abhishekcr448/Hinglish-Everyday-Conversations-1M); written by GPT-4o-mini "
    "(its card): measured, never trained on",
    "hinglish_conversations.csv",
    "3ec4aa4f23394dc7e6ecef990453641fa85c0f03175ad60f1408e3b3c0c36484",
    ("hi-latn",),
)
MEASURED = (HINGLISH_1M,)
# Source prefixes of text a language model wrote: never a training line,
# never a development line of the reader (``ruh_reader.written_by_a_model``).
MODEL_WRITTEN = frozenset({"hinglish-1m"})
# Large sources are read in part: a line is a candidate when its rank (by
# SHA-256 of its source id) falls in this share. The rank also orders the
# lines taken, so a cut here only shortens the order, never changes it. Few
# Hinglish utterances are 3 to 8 words, so a quarter is read to hold 2,000 out.
# A FineWeb-2 document is read when the rank of ``<source>:<id>`` falls in its
# share; a thirty-second of each Latin subset holds several times the budget.
KEEP = {
    "tatoeba-eng": 1 / 16,
    "hinglish-1m": 1 / 4,
    "fineweb-2-hin_Latn": 1 / 32,
    "fineweb-2-urd_Latn": 1 / 32,
}
V2_SALT = "ruh-reader-v2"
HELD_DOCUMENTS = 5  # one FineWeb-2 document in five is held out for good
PER_DOCUMENT = 32  # lines a FineWeb-2 document gives at most (its first)


def folder() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "corpora" / "ruh_reader"


# ── reading the sources ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Line:
    source: str  # where it came from: ``tatoeba:<id>``, ``massive:<locale>:<id>``, …
    label: str
    text: str
    kind: str = "train"  # ``train``; for MASSIVE also ``test`` and ``dev``

    @property
    def origin(self) -> str:
        """The source's name (``tatoeba-eng``, ``massive``, ``fineweb-2-hin_Latn``)."""
        head = self.source.split(":", 1)[0]
        return f"tatoeba-{TATOEBA[self.label]}" if head == "tatoeba" else head

    @property
    def document(self) -> str:
        """The document a line was cut from: a FineWeb-2 line's
        ``<source>:<id>``; any other line is its own."""
        if self.origin in FINEWEB_LATIN:
            return self.source.rsplit(":", 1)[0]
        return self.source

    @property
    def order(self) -> tuple[int, int]:
        """Lines are taken by the rank of their document, then in its order."""
        if self.origin in FINEWEB_LATIN:
            return rank(self.document), int(self.source.rsplit(":", 1)[1])
        return rank(self.source), 0


def rank(source: str) -> int:
    return int(hashlib.sha256(f"{SALT}:{source}".encode()).hexdigest()[:16], 16)


def model_written(source: str) -> bool:
    """Whether a ``source:id`` names text a language model wrote."""
    return source.split(":", 1)[0] in MODEL_WRITTEN


def _kept(source: str, share: float) -> bool:
    return share >= 1 or rank(source) < share * 16**16


def _clean(text: str) -> str:
    return " ".join(text.replace("\t", " ").split())


def tatoeba(path: Path, label: str, share: float = 1.0) -> Iterator[Line]:
    """``id <TAB> lang <TAB> text`` rows of a per-language export (bz2)."""
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for row in handle:
            parts = row.rstrip("\n").split("\t")
            if len(parts) == 3 and parts[0].isdigit():
                source = f"tatoeba:{parts[0]}"
                if _kept(source, share):
                    yield Line(source, label, _clean(parts[2]))


def hinglish(path: Path, share: float = 1.0) -> Iterator[Line]:
    """Each utterance (``input`` and ``output``) of each conversation row."""
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None) or []
        for number, row in enumerate(reader):
            for column, text in zip(header, row, strict=False):
                source = f"hinglish-1m:{number}:{column}"
                if _kept(source, share):
                    yield Line(source, "hi-latn", _clean(text))


_SENTENCE_END = re.compile(r"(?<=[.!?।۔])\s+")


def lines_of(text: str) -> list[str]:
    """A web document cut into short lines, as the reader's other sources are
    sentences: at each line break and sentence end; a piece longer than
    ``MAX_BYTES`` bytes of words as read is cut into the fewest equal runs of
    words that could fit."""
    found: list[str] = []
    for raw in text.splitlines():
        for sentence in _SENTENCE_END.split(raw):
            words = sentence.split()
            if not words:
                continue
            size = len(_words(" ".join(words)).encode("utf-8"))
            parts = min(len(words), max(1, math.ceil(size / MAX_BYTES)))
            step = math.ceil(len(words) / parts)
            found += [" ".join(words[i : i + step]) for i in range(0, len(words), step)]
    return found


def held_document(key: str) -> bool:
    """One FineWeb-2 document in ``HELD_DOCUMENTS`` (``<source>:<id>``), fixed
    by SHA-256: never trained on, the only documents v2's slices are cut from."""
    digest = hashlib.sha256(f"{V2_SALT}:held:{key}".encode()).hexdigest()
    return int(digest[:16], 16) % HELD_DOCUMENTS == 0


def parquet_rows(path: Path) -> Iterator[tuple[str, str]]:
    """(id, text) of a FineWeb-2 parquet file (needs pyarrow)."""
    import pyarrow.parquet as pq

    handle = pq.ParquetFile(str(path))
    for batch in handle.iter_batches(batch_size=1024, columns=["id", "text"]):
        for identifier, text in zip(
            batch.column("id").to_pylist(), batch.column("text").to_pylist(), strict=True
        ):
            if text:
                yield str(identifier), str(text)


def fineweb(
    rows: Iterable[tuple[str, str]], name: str, share: float = 1.0, held: bool = False
) -> Iterator[Line]:
    """The lines of a FineWeb-2 subset's documents ((id, text) rows): of the
    documents not held out whose rank falls in ``share`` (``kind`` ``train``),
    or, with ``held``, of the held-out ones (``kind`` ``held``). Each document
    gives its first ``PER_DOCUMENT`` lines; a line's id is ``<source>:<id>:<n>``."""
    for identifier, text in rows:
        key = f"{name}:{identifier}"
        if held_document(key) != held or not _kept(key, share):
            continue
        for number, piece in enumerate(lines_of(text)[:PER_DOCUMENT]):
            yield Line(f"{key}:{number}", "hi-latn", _clean(piece), "held" if held else "train")


def massive(path: Path, labels: Iterable[str] = tuple(MASSIVE_LOCALES)) -> Iterator[Line]:
    """Every utterance of the chosen locales, with its partition as ``kind``."""
    wanted = {MASSIVE_LOCALES[label]: label for label in labels}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            locale = Path(member.name).stem
            if not member.isfile() or locale not in wanted or not member.name.endswith(".jsonl"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            for row in io.TextIOWrapper(handle, encoding="utf-8"):
                item = json.loads(row)
                yield Line(
                    f"massive:{locale}:{item['id']}",
                    wanted[locale],
                    _clean(str(item["utt"])),
                    str(item["partition"]),
                )


# ── the rules ────────────────────────────────────────────────────────────


def script_of(char: str) -> str:
    from .. import lughah

    found = lughah._script(char)
    if found != "other":
        return found
    return "latin" if ord(char) < 0x250 else "other"


def own_script(text: str, label: str) -> bool:
    """More than half of the letters are in the language's script."""
    letters = [char for char in text if char.isalpha()]
    if len(letters) < MIN_LETTERS:
        return False
    wanted = SCRIPTS.get(label)
    if wanted is None:
        return True
    return sum(1 for char in letters if script_of(char) == wanted) * 2 > len(letters)


def seed_ids() -> set[str]:
    """``source:id`` of every line of Lughah's shipped seed files."""
    from .. import lughah

    found = set()
    for path in lughah.CORPUS.glob("*.tsv"):
        for row in path.read_text(encoding="utf-8").splitlines():
            source, _, text = row.partition("\t")
            if text.strip() and not source.startswith("#"):
                found.add(source.strip())
    return found


@dataclass
class Counts:
    kept: Counter = field(default_factory=Counter)  # (label, origin) → lines
    kept_bytes: Counter = field(default_factory=Counter)
    dropped: Counter = field(default_factory=Counter)  # (origin, rule) → lines

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


def _words(text: str) -> str:
    from . import reading

    return reading(text)


def _group(text: str) -> str:
    from . import group_of

    return group_of(text)


def pick_short(
    test: Iterable[Line],
    hinglish_lines: Iterable[Line],
    seed_groups: set[str],
    *,
    hinglish_count: int = SHORT_HINGLISH,
    words: tuple[int, int] = SHORT_WORDS,
) -> list[tuple[Line, str]]:
    """The held-out slice of short messages, each with its group for the gate:
    MASSIVE test utterances of ``words`` words (one MASSIVE id is one group:
    its translations are one request), and Roman Hindi/Urdu utterances whose
    group the seeds' rule holds out (``ruh_reader.part``). Lines whose words
    are a seed's are left out, so neither model has seen them."""
    from . import group_of, part

    low, high = words
    chosen: list[tuple[Line, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in sorted(test, key=lambda item: rank(item.source)):
        if not low <= len(line.text.split()) <= high or not own_script(line.text, line.label):
            continue
        group = group_of(line.text)
        if group in seed_groups or (line.label, group) in seen:
            continue
        seen.add((line.label, group))
        chosen.append((line, "massive:" + line.source.rsplit(":", 1)[1]))
    roman: list[tuple[Line, str]] = []
    for line in sorted(hinglish_lines, key=lambda item: rank(item.source)):
        if len(roman) >= hinglish_count:
            break
        if not low <= len(line.text.split()) <= high or not own_script(line.text, line.label):
            continue
        group = group_of(line.text)
        if part(group) != "held_out" or group in seed_groups or (line.label, group) in seen:
            continue
        seen.add((line.label, group))
        roman.append((line, group))
    return chosen + roman


@dataclass(frozen=True)
class Holy:
    """What sets a text aside: ``scripture`` (``ruh_reader.scripture``), and
    ``hadith`` (``speaker.Hadith``) when given; ``sieve`` (``speaker.Sieve``)
    skips the pieces scripture could not flag, so only with the full check."""

    scripture: Callable[[str], bool]
    hadith: Callable[[str], bool] | None = None
    sieve: Any = None

    def __call__(self, text: str) -> str | None:
        if (self.sieve is None or self.sieve.may_hold(text)) and self.scripture(text):
            return "scripture"
        if self.hadith is not None and self.hadith(text):
            return "hadith"
        return None

    def document(self, text: str) -> str | None:
        """The first verdict on any piece of a whole document (``speaker.pieces``)."""
        from .speaker import pieces

        for piece in pieces(text):
            found = self(piece)
            if found:
                return found
        return None


_holy: Holy | None = None


def _line_verdict(text: str) -> str | None:
    assert _holy is not None
    return _holy(text)


def _document_verdict(text: str) -> str | None:
    assert _holy is not None
    return _holy.document(text)


def _check(texts: Sequence[str], holy: Holy, workers: int, whole: bool = False) -> list[str | None]:
    global _holy
    _holy = holy
    verdict = _document_verdict if whole else _line_verdict
    if workers <= 1 or len(texts) < (50 if whole else 1000):
        return [verdict(text) for text in texts]
    import multiprocessing

    # Forked workers share the parent's loaded Quran and hadith texts.
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        return list(pool.map(verdict, texts, chunksize=4 if whole else 256))


def pick_train(
    pools: dict[str, dict[str, list[Line]]],
    *,
    seed_groups: set[str],
    seed_sources: set[str],
    excluded: set[str],
    scripture: Callable[[str], bool] | Holy,
    bytes_per_language: int = BYTES_PER_LANGUAGE,
    counts: Counts | None = None,
    workers: int = 1,
    near: Container[str] = (),
    documents: dict[str, str] | None = None,
) -> list[Line]:
    """Training lines per language (``pools``: label → origin → lines), taken
    in rank order round robin over the language's sources until it holds
    ``bytes_per_language`` bytes of words, each passing every rule. ``near``
    holds the messages ever measured: a line near one is not trained on.
    ``documents`` (``<source>:<id>`` → text) are the whole documents lines
    were cut from: one that holds scripture (or hadith, with a ``Holy`` that
    has the rule) anywhere, or a line that does, gives no line."""
    from . import group_of

    holy = scripture if isinstance(scripture, Holy) else Holy(scripture)
    documents = documents or {}
    counts = counts if counts is not None else Counts()
    kept: list[Line] = []
    for label in sorted(pools):
        queues = {
            origin: sorted(lines, key=lambda item: item.order)
            for origin, lines in sorted(pools[label].items())
        }
        positions = dict.fromkeys(queues, 0)
        candidates: list[tuple[Line, int]] = []
        taken = 0
        seen: set[str] = set()
        while taken < bytes_per_language * OVERSELECT and any(
            positions[origin] < len(queue) for origin, queue in queues.items()
        ):
            for origin, queue in queues.items():
                if positions[origin] >= len(queue):
                    continue
                line = queue[positions[origin]]
                positions[origin] += 1
                words = _words(line.text)
                size = len(words.encode("utf-8"))
                group = group_of(line.text)
                rule = None
                if not own_script(line.text, label):
                    rule = "script"
                elif len(words.replace(" ", "")) < MIN_LETTERS or size > MAX_BYTES:
                    rule = "length"
                elif line.source in seed_sources:
                    rule = "seed id"
                elif group in seed_groups:
                    rule = "seed words"
                elif group in excluded:
                    rule = "held out here"
                elif group in seen:
                    rule = "duplicate"
                elif line.text in near:
                    rule = "near a measured message"
                if rule is not None:
                    counts.dropped[(origin, rule)] += 1
                    continue
                seen.add(group)
                candidates.append((line, size))
                taken += size
        verdicts = _check([line.text for line, _ in candidates], holy, workers)
        flagged = {
            line.document
            for (line, _), verdict in zip(candidates, verdicts, strict=True)
            if verdict
        }
        whole = sorted({line.document for line, _ in candidates} & documents.keys() - flagged)
        flagged |= {
            name
            for name, verdict in zip(
                whole,
                _check([documents[name] for name in whole], holy, workers, whole=True),
                strict=True,
            )
            if verdict
        }
        total = 0
        for (line, size), verdict in zip(candidates, verdicts, strict=True):
            if total >= bytes_per_language:
                break
            if verdict:
                counts.dropped[(line.origin, verdict)] += 1
                continue
            if line.document in flagged:
                counts.dropped[(line.origin, "document holds scripture or hadith")] += 1
                continue
            kept.append(line)
            total += size
            counts.kept[(label, line.origin)] += 1
            counts.kept_bytes[(label, line.origin)] += size
    return kept


def assemble(
    lines: Iterable[Line],
    *,
    labels: Iterable[str],
    seed_rows: Sequence[tuple[str, str]],
    seed_sources: set[str],
    scripture: Callable[[str], bool] | Holy,
    bytes_per_language: int = BYTES_PER_LANGUAGE,
    hinglish_count: int = SHORT_HINGLISH,
    workers: int = 1,
    measured: Iterable[str] = (),
    documents: dict[str, str] | None = None,
) -> tuple[list[Line], list[tuple[Line, str]], Counts]:
    """The training lines and the held-out short slice from the sources' lines
    (``seed_rows``: every line of Lughah's corpus, neutral classes included).
    A model-written line (``MODEL_WRITTEN``) is never a training candidate:
    the Roman part of the short slice is drawn from those lines, as v1 drew it.
    ``measured``: the texts of every message measured elsewhere; their words,
    or words near them, are never trained on."""
    from . import group_of

    seed_groups = {group_of(text) for text, _label in seed_rows}
    labels = set(labels)
    pools: dict[str, dict[str, list[Line]]] = defaultdict(lambda: defaultdict(list))
    test: list[Line] = []
    roman: list[Line] = []
    counts = Counts()
    for line in lines:
        if line.label not in labels:
            continue
        if line.kind == "test":
            test.append(line)
        elif line.kind == "train" and model_written(line.source):
            roman.append(line)  # measured only: the short slice's Roman part
        elif line.kind == "train":
            pools[line.label][line.origin].append(line)
        elif line.kind == "held":
            counts.dropped[(line.origin, "held-out document")] += 1
        else:
            counts.dropped[(line.origin, f"partition {line.kind}")] += 1
    short = pick_short(test, roman, seed_groups, hinglish_count=hinglish_count)
    measured = list(measured)
    excluded = {group_of(line.text) for line, _group in short}
    excluded |= {group_of(text) for text in measured}
    train = pick_train(
        pools,
        seed_groups=seed_groups,
        seed_sources=seed_sources,
        excluded=excluded,
        scripture=scripture,
        bytes_per_language=bytes_per_language,
        counts=counts,
        workers=workers,
        near=Near(measured) if measured else (),
        documents=documents,
    )
    return train, short, counts


# ── downloading ──────────────────────────────────────────────────────────


class Mismatch(RuntimeError):
    pass


def download(source: Source, target: Path, client=None) -> dict:
    """The source's file, fetched once into its own folder; a pinned file
    whose SHA-256 differs is refused and removed."""
    import httpx

    path = target / source.file
    if path.exists():
        digest = _sha256(path)
        if source.sha256 is None or digest == source.sha256:
            return {"sha256": digest, "bytes": path.stat().st_size, "cached": True}
        path.unlink()
    target.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    hasher = hashlib.sha256()
    own = client is None
    client = client or httpx.Client(timeout=120, follow_redirects=True)
    try:
        with client.stream("GET", source.url) as response:
            response.raise_for_status()
            modified = response.headers.get("last-modified", "")
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    hasher.update(chunk)
                    handle.write(chunk)
    finally:
        if own:
            client.close()
    digest = hasher.hexdigest()
    if source.sha256 is not None and digest != source.sha256:
        temporary.unlink(missing_ok=True)
        raise Mismatch(f"{source.name}: SHA-256 {digest} is not the pinned {source.sha256}")
    temporary.replace(path)
    return {"sha256": digest, "bytes": path.stat().st_size, "last_modified": modified}


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_sources(
    paths: dict[str, Path],
    labels: Iterable[str],
    documents: dict[str, str] | None = None,
    rows: Callable[[Path], Iterable[tuple[str, str]]] = parquet_rows,
) -> Iterator[Line]:
    """Every line of the downloaded sources (training and measured), for the
    given languages. The FineWeb-2 documents read (training side, in their
    share) are kept whole in ``documents``, for the scripture check."""
    wanted = set(labels)
    for source in (*SOURCES, *MEASURED):
        path = paths.get(source.name)
        if path is None or not wanted & set(source.labels):
            continue
        share = KEEP.get(source.name, 1.0)
        if source.name == "massive":
            yield from massive(path, [label for label in source.labels if label in wanted])
        elif source.name == "hinglish-1m":
            yield from hinglish(path, share)
        elif source.name in FINEWEB_LATIN:
            for identifier, text in rows(path):
                key = f"{source.name}:{identifier}"
                if held_document(key) or not _kept(key, share):
                    continue
                if documents is not None:
                    documents[key] = text
                yield from fineweb([(identifier, text)], source.name, share)
        else:
            yield from tatoeba(path, source.labels[0], share)


def full_scripture() -> Callable[[str], bool]:
    """``ruh_reader.scripture`` with Iqtibas's Quran texts in memory (fetched
    as Fihris does when they are not on disk); refused without them."""
    import asyncio

    from .. import iqtibas
    from . import scripture

    if iqtibas.ready() is None:
        asyncio.run(iqtibas.warm())
    if iqtibas.ready() is None and iqtibas.load() is None:
        raise RuntimeError(
            "The Quran's texts are not available, so the corpus cannot be checked for "
            "scripture; nothing was written"
        )
    return scripture


def build(
    *,
    bytes_per_language: int = BYTES_PER_LANGUAGE,
    hinglish_count: int = SHORT_HINGLISH,
    workers: int = 1,
    scripture: Callable[[str], bool] | None = None,
    hadith: Callable[[str], bool] | None = None,
    paths: dict[str, Path] | None = None,
    out: Path | None = None,
    measured: Sequence[str] = (),
    rows_of: Callable[[Path], Iterable[tuple[str, str]]] = parquet_rows,
    log: Callable[[str], None] = logger.info,
) -> dict:
    """Download the sources (unless ``paths`` are given), pick the lines and
    write the corpus. Returns its manifest. Without ``scripture`` the full
    check runs (Iqtibas's texts in memory, ``speaker.Sieve`` in front of it);
    ``hadith`` adds the speaker's rule. ``measured``: every message measured
    elsewhere (``measured_texts``), never trained on, nor its near copies."""
    from .. import iqtibas, lughah
    from . import corpus_digest, seeds

    out = out or folder()
    rows = seeds()
    labels = sorted({label for _text, label in rows})
    if scripture is None:
        from .speaker import Sieve

        holy = Holy(full_scripture(), hadith, Sieve(iqtibas.ready()))
    else:
        holy = Holy(scripture, hadith)
    pinned = {source.name: source for source in (*SOURCES, *MEASURED)}
    fetched: dict[str, dict] = {}
    if paths is None:
        paths = {}
        for source in pinned.values():
            if not set(labels) & set(source.labels):
                continue
            target = out / "sources" / source.name
            log(f"corpus: fetching {source.name}")
            fetched[source.name] = download(source, target)
            paths[source.name] = target / source.file
    else:
        for name, path in paths.items():
            digest = _sha256(path)
            expected = pinned[name].sha256 if name in pinned else None
            fetched[name] = {"sha256": digest, "pin_matches": expected in (None, digest)}
    documents: dict[str, str] = {}
    train, short, counts = assemble(
        read_sources(paths, labels, documents, rows_of),
        labels=labels,
        seed_rows=lughah.corpus(),
        seed_sources=seed_ids(),
        scripture=holy,
        bytes_per_language=bytes_per_language,
        hinglish_count=hinglish_count,
        workers=workers,
        measured=measured,
        documents=documents,
    )
    measured_groups = sorted({_group(text) for text in measured})
    out.mkdir(parents=True, exist_ok=True)
    train_body = "".join(f"{line.source}\t{line.label}\t{line.text}\n" for line in train)
    short_body = "".join(
        f"{line.source}\t{line.label}\t{group}\t{line.text}\n" for line, group in short
    )
    (out / "train.tsv").write_text(train_body, encoding="utf-8")
    (out / "short.tsv").write_text(short_body, encoding="utf-8")
    manifest = {
        "version": VERSION,
        "created": datetime.now(UTC).isoformat(),
        "seeds_sha256": corpus_digest(rows),
        "languages": labels,
        "settings": {
            "bytes_per_language": bytes_per_language,
            "short_words": list(SHORT_WORDS),
            "short_hinglish": hinglish_count,
            "keep": KEEP,
            "salt": SALT,
            "held_documents": f"1/{HELD_DOCUMENTS}",
            "per_document": PER_DOCUMENT,
        },
        # The full check (Iqtibas's Quran texts in memory) unless a caller gave its own.
        "scripture": {"checked": True, "iqtibas": scripture is None, "hadith": hadith is not None},
        "sources": [
            {
                "name": source.name,
                "url": source.url,
                "licence": source.licence,
                "pinned": source.sha256 is not None,
                "trained_on": source.name not in MODEL_WRITTEN,
                **fetched.get(source.name, {}),
            }
            for source in (*SOURCES, *MEASURED)
            if source.name in paths
        ],
        "model_written": sorted(MODEL_WRITTEN),  # never trained on
        "measured": {
            "messages": len(measured_groups),
            "sha256": hashlib.sha256("\n".join(measured_groups).encode("utf-8")).hexdigest(),
        },
        "train": {
            "lines": len(train),
            "sha256": hashlib.sha256(train_body.encode("utf-8")).hexdigest(),
        },
        "short": {
            "lines": len(short),
            "per_language": dict(Counter(line.label for line, _group in short)),
            "sha256": hashlib.sha256(short_body.encode("utf-8")).hexdigest(),
        },
        **counts.to_dict(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"corpus: {len(train)} training lines, {len(short)} short held-out messages in {out}")
    return manifest


@dataclass
class Corpus:
    train: list[tuple[str, str]]  # (text, label): what the reader may learn from
    short: list[tuple[str, str, str]]  # (text, label, group)
    manifest: dict
    # (text, label) of an older corpus's model-written lines (v1's Hinglish-1M
    # rows): seen, so never measured on, and never trained on.
    written: list[tuple[str, str]] = field(default_factory=list)


# ── the validation slices: calibrated on one half, gated on the other ────

VALIDATION_SALT = "ruh-reader-v1.1"
HALVES = ("calibration", "gate")


def half(key: str) -> str:
    """``calibration`` or ``gate``, fixed by SHA-256 of the key (a MASSIVE
    request ``massive:<id>``, a Hinglish conversation ``hinglish-1m:<row>``)."""
    value = int(hashlib.sha256(f"{VALIDATION_SALT}:{key}".encode()).hexdigest()[:16], 16)
    return HALVES[value % 2]


def pick_validation(
    dev: Iterable[Line],
    hinglish_lines: Iterable[Line],
    excluded: set[str],
    *,
    words: tuple[int, int] = SHORT_WORDS,
    read_share: float = KEEP["hinglish-1m"],
    counts: Counter | None = None,
) -> list[tuple[Line, str, str]]:
    """(line, group, half) of messages neither model was trained on or
    measured on: MASSIVE's ``dev`` partition (one id is one group and lies in
    one half), and Roman Hindi/Urdu utterances v1's build never read (outside
    ``read_share`` of Hinglish-1M, in its order) whose group the seeds' rule
    holds out. ``excluded``: the words (``group_of``) of every seed, every
    training line and every message already measured. Each half takes as
    many Roman rows as the mean per-language count of its MASSIVE rows."""
    from . import group_of, part

    low, high = words
    counts = counts if counts is not None else Counter()
    chosen: list[tuple[Line, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in sorted(dev, key=lambda item: rank(item.source)):
        if not low <= len(line.text.split()) <= high:
            counts["massive: words"] += 1
            continue
        if not own_script(line.text, line.label):
            counts["massive: script"] += 1
            continue
        group = group_of(line.text)
        if group in excluded:
            counts["massive: seen words"] += 1
            continue
        if (line.label, group) in seen:
            counts["massive: duplicate"] += 1
            continue
        seen.add((line.label, group))
        key = "massive:" + line.source.rsplit(":", 1)[1]
        chosen.append((line, key, half(key)))
    want = {}
    for name in HALVES:
        per_language = Counter(line.label for line, _g, h in chosen if h == name)
        want[name] = round(sum(per_language.values()) / len(per_language)) if per_language else 0
    candidates = [
        line
        for line in hinglish_lines
        if not _kept(line.source, read_share) and low <= len(line.text.split()) <= high
    ]
    have = Counter[str]()
    for line in sorted(candidates, key=lambda item: rank(item.source)):
        if all(have[name] >= want[name] for name in HALVES):
            break
        where = half(line.source.rsplit(":", 1)[0])  # the conversation: hinglish-1m:<row>
        if have[where] >= want[where]:
            continue
        if not own_script(line.text, line.label):
            counts["roman: script"] += 1
            continue
        group = group_of(line.text)
        if part(group) != "held_out":
            counts["roman: not a held-out group"] += 1
            continue
        if group in excluded:
            counts["roman: seen words"] += 1
            continue
        if (line.label, group) in seen:
            counts["roman: duplicate"] += 1
            continue
        seen.add((line.label, group))
        have[where] += 1
        chosen.append((line, group, where))
    return chosen


def _validation_body(rows: Sequence[tuple[Line, str, str]]) -> str:
    return "".join(
        f"{line.source}\t{line.label}\t{group}\t{where}\t{line.text}\n"
        for line, group, where in rows
    )


def build_validation(
    where: Path | None = None,
    *,
    paths: dict[str, Path] | None = None,
    log: Callable[[str], None] = logger.info,
) -> dict:
    """The validation slices beside a built corpus (``where``): MASSIVE's
    ``dev`` partition and fresh Roman Hindi/Urdu rows, from the corpus's own
    downloads (``sources/``, SHA-256 checked against the pins) unless
    ``paths`` are given. Written to ``validation.tsv`` (source, label, group,
    half, text) and ``validation.json``. Returns that manifest."""
    from .. import lughah
    from . import corpus_digest, group_of, seeds

    where = where or folder()
    found = load(where)
    if found is None:
        raise RuntimeError("no corpus to build the validation slices beside")
    pinned = {source.name: source for source in (*SOURCES, *MEASURED)}
    own = paths is None
    if paths is None:
        paths = {
            name: where / "sources" / name / pinned[name].file
            for name in ("massive", "hinglish-1m")
        }
    digests = {}
    for name in ("massive", "hinglish-1m"):
        digests[name] = _sha256(paths[name])
        expected = pinned[name].sha256
        if own and expected is not None and digests[name] != expected:
            raise Mismatch(f"{name}: SHA-256 {digests[name]} is not the pinned {expected}")
    excluded = {group_of(text) for text, _label in lughah.corpus()}
    excluded |= {group_of(text) for text, _label in [*found.train, *found.written]}
    excluded |= {group_of(text) for text, _label, _group in found.short}
    labels = set(found.manifest.get("languages") or MASSIVE_LOCALES)
    dev = list(massive(paths["massive"], [x for x in MASSIVE_LOCALES if x in labels]))
    counts: Counter = Counter()
    counts["massive: other partitions"] = sum(1 for line in dev if line.kind != "dev")
    dev = [line for line in dev if line.kind == "dev"]
    # The share of Hinglish-1M the corpus build read (its rows may be trained on).
    share = float(
        ((found.manifest.get("settings") or {}).get("keep") or {}).get("hinglish-1m", 1.0)
    )
    rows = pick_validation(
        dev, hinglish(paths["hinglish-1m"]), excluded, read_share=share, counts=counts
    )
    body = _validation_body(rows)
    (where / "validation.tsv").write_text(body, encoding="utf-8")
    sizes: dict[str, dict[str, int]] = {name: {} for name in HALVES}
    for line, _group, name in rows:
        sizes[name][line.label] = sizes[name].get(line.label, 0) + 1
    manifest = {
        "version": 1,
        "created": datetime.now(UTC).isoformat(),
        "seeds_sha256": corpus_digest(seeds()),
        "train_sha256": found.manifest["train"]["sha256"],
        "short_sha256": found.manifest["short"]["sha256"],
        "sources": {
            name: {"sha256": digests[name], "licence": pinned[name].licence, "pin_checked": own}
            for name in digests
        },
        "settings": {
            "salt": VALIDATION_SALT,
            "words": list(SHORT_WORDS),
            "hinglish_read_share": share,
            "massive_partition": "dev",
        },
        "excluded_groups": len(excluded),
        "lines": len(rows),
        "per_half": sizes,
        "dropped": dict(sorted(counts.items())),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    (where / "validation.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"validation: {len(rows)} messages in {where / 'validation.tsv'}: {json.dumps(sizes)}")
    return manifest


def load_validation(where: Path | None = None) -> list[tuple[str, str, str, str]] | None:
    """(text, label, group, half) of the validation slices, when the file is
    whole and was built beside this corpus and these seeds; otherwise None."""
    from . import corpus_digest, seeds

    where = where or folder()
    found = load(where)
    try:
        manifest = json.loads((where / "validation.json").read_text(encoding="utf-8"))
        body = (where / "validation.tsv").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    if (
        found is None
        or hashlib.sha256(body.encode("utf-8")).hexdigest() != manifest.get("sha256")
        or manifest.get("train_sha256") != found.manifest["train"]["sha256"]
        or manifest.get("short_sha256") != found.manifest["short"]["sha256"]
        or manifest.get("seeds_sha256") != corpus_digest(seeds())
    ):
        logger.warning("Ruh reader validation slices: not built beside this corpus; not used")
        return None
    rows = []
    for row in body.splitlines():
        _source, label, group, name, text = row.split("\t", 4)
        rows.append((text, label, group, name))
    return rows


# ── test 3: fresh messages, the Roman rows checked by Qamus ──────────────

FRESH_SALT = "ruh-reader-test3"
LABELLED = 200  # never-read Roman rows labelled by hand, to check the rule first
EDITS = 2  # a message this many character edits from a seen text is near it
CLINC150_COMMIT = "828f8093932c8fe6ca7936c3d2e52903b1c523de"
# Not a training source: its requests are only ever measured.
CLINC150 = Source(
    "clinc150",
    f"https://raw.githubusercontent.com/clinc/oos-eval/{CLINC150_COMMIT}/data/data_full.json",
    "CC BY 3.0 (CLINC150, Larson et al. 2019; clinc/oos-eval)",
    "data_full.json",
    "36923c3705a59e08fe9c3883d8bc2dd966ef93e22cb78ac41171782a698d56e0",
    ("en",),
)


def clinc(path: Path) -> Iterator[Line]:
    """Every query of CLINC150's ``data_full.json`` (all six splits; English),
    its split as ``kind``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for split in sorted(data):
        for number, item in enumerate(data[split]):
            yield Line(f"clinc150:{split}:{number}", "en", _clean(str(item[0])), split)


def roman_words(text: str, least: int = 1) -> bool:
    """Whether Qamus reads ``least`` of the words (distinct) as Hindi or Urdu
    words written in Latin letters (``qamus.read_roman``: P > ½, not an
    English word). A Hinglish-1M row counts as Roman Hindi/Urdu only with one
    (test 3): the dataset labels every utterance so, and many are written in
    English alone. v2's web and tweet rows need two (``V2_LEAST``)."""
    from .. import qamus

    found = {word for word in qamus.tokens(text) if qamus.read_roman(word)}
    return len(found) >= least


def within(a: str, b: str, limit: int = EDITS) -> bool:
    """Whether the Levenshtein distance of two strings is at most ``limit``
    (their common prefix and suffix are set aside first: they change nothing)."""
    if abs(len(a) - len(b)) > limit:
        return False
    start = 0
    while start < min(len(a), len(b)) and a[start] == b[start]:
        start += 1
    a, b = a[start:], b[start:]
    end = 0
    while end < min(len(a), len(b)) and a[-1 - end] == b[-1 - end]:
        end += 1
    a, b = a[: len(a) - end], b[: len(b) - end]
    if max(len(a), len(b)) <= limit:
        return True
    previous = list(range(len(b) + 1))
    for i, char in enumerate(a, 1):
        current = [i]
        for j, other in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char != other))
            )
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


def _thirds(size: int) -> tuple[tuple[int, int], ...]:
    return ((0, size // 3), (size // 3, 2 * size // 3), (2 * size // 3, size))


class Near:
    """Whether a message is a near copy of one of a set of texts, both read as
    words (``reading``): within ``EDITS`` character edits (Levenshtein, spaces
    counted), or the same words with one word more or one fewer. The same
    words are near too. Only texts that can be near a message of ``words``
    words are indexed. Candidates for the edit distance are found by the
    pigeonhole principle: two edits leave one of a text's three thirds
    untouched, shifted by at most two letters; each is then confirmed."""

    def __init__(self, texts: Iterable[str], words: tuple[int, int] = SHORT_WORDS) -> None:
        from . import reading

        low, high = words
        self.pieces: dict[tuple[int, int, str], set[str]] = defaultdict(set)
        self.same: set[tuple[str, ...]] = set()
        self.fewer: set[tuple[str, ...]] = set()
        for text in texts:
            said = reading(text)
            split = tuple(said.split())
            if low - EDITS <= len(split) <= high + EDITS and len(said) >= 3:
                for index, (start, end) in enumerate(_thirds(len(said))):
                    self.pieces[(len(said), index, said[start:end])].add(said)
            if low - 1 <= len(split) <= high + 1:
                self.same.add(split)
                self.fewer.update(split[:i] + split[i + 1 :] for i in range(len(split)))

    def __contains__(self, text: object) -> bool:
        from . import reading

        said = reading(str(text))
        split = tuple(said.split())
        if split in self.same or split in self.fewer:
            return True
        if any(split[:i] + split[i + 1 :] in self.same for i in range(len(split))):
            return True
        size = len(said)
        tried: set[str] = set()
        for length in range(max(3, size - EDITS), size + EDITS + 1):
            for index, (start, end) in enumerate(_thirds(length)):
                for shift in range(-EDITS, EDITS + 1):
                    at = start + shift
                    if at < 0 or at + end - start > size:
                        continue
                    for other in self.pieces.get((length, index, said[at : at + end - start]), ()):
                        if other not in tried:
                            tried.add(other)
                            if within(said, other):
                                return True
        return False


def label_order(source: str) -> str:
    """The order the rows to label by hand are drawn in (not v1's ``rank``)."""
    return hashlib.sha256(f"{FRESH_SALT}:label:{source}".encode()).hexdigest()


def _conversation(source: str) -> str:
    return source.rsplit(":", 1)[0]  # hinglish-1m:<row>:<column> → hinglish-1m:<row>


def roman_pool(
    candidates: Sequence[Line],
    seen: set[str],
    near: Container[str],
    used: set[str],
    order: Callable[[Line], Any],
    counts: Counter | None = None,
) -> Iterator[tuple[Line, str]]:
    """Never-read Roman rows of 3 to 8 words (``candidates``) that may be
    measured, in ``order``, each with its group: Latin script, a group the
    seeds' rule holds out, words no seen text's, a conversation not ``used``,
    not near a seen text, once per words."""
    from . import group_of, part

    counts = counts if counts is not None else Counter()
    chosen: set[str] = set()
    for line in sorted(candidates, key=order):
        if not own_script(line.text, line.label):
            counts["roman: script"] += 1
            continue
        group = group_of(line.text)
        if part(group) != "held_out":
            counts["roman: not a held-out group"] += 1
            continue
        if group in seen:
            counts["roman: seen words"] += 1
            continue
        if _conversation(line.source) in used:
            counts["roman: conversation measured or a seed's"] += 1
            continue
        if line.text in near:
            counts["roman: near a seen text"] += 1
            continue
        if group in chosen:
            counts["roman: duplicate"] += 1
            continue
        chosen.add(group)
        yield line, group


def fresh_candidates(
    hinglish_lines: Iterable[Line],
    read_share: float = KEEP["hinglish-1m"],
    words: tuple[int, int] = SHORT_WORDS,
) -> list[Line]:
    """Roman utterances v1's build never read (outside ``read_share`` of
    Hinglish-1M, in its order), of ``words`` words."""
    low, high = words
    return [
        line
        for line in hinglish_lines
        if not _kept(line.source, read_share) and low <= len(line.text.split()) <= high
    ]


def label_sample(
    candidates: Sequence[Line],
    seen: set[str],
    near: Container[str],
    used: set[str],
    size: int = LABELLED,
) -> list[Line]:
    """The never-read rows to label by hand: the first ``size`` of the Roman
    pool in ``label_order`` (the rule is not asked)."""
    pool = roman_pool(candidates, seen, near, used, lambda line: label_order(line.source))
    return [line for line, _group in itertools.islice(pool, size)]


def pick_fresh(
    clinc_lines: Iterable[Line],
    candidates: Sequence[Line],
    seen: set[str],
    near: Container[str],
    used: set[str],
    labelled: set[str],
    *,
    words: tuple[int, int] = SHORT_WORDS,
    rule: Callable[[str], bool] = roman_words,
    counts: Counter | None = None,
) -> list[tuple[Line, str, str]]:
    """(line, group, part) of test 3's fresh messages. English: every CLINC150
    query of ``words`` words, Latin script, not seen or near, once per words
    (part ``gate``). Roman: the pool in v1's rank order, the hand-labelled
    rows' words (``labelled``, groups) left out; a row the rule holds is ``gate``
    until the gate holds as many Roman rows as English ones, a row it does
    not is ``rule`` (left out by the rule, reported only)."""
    from . import group_of

    low, high = words
    counts = counts if counts is not None else Counter()
    rows: list[tuple[Line, str, str]] = []
    taken: set[str] = set()
    for line in sorted(clinc_lines, key=lambda item: rank(item.source)):
        if not low <= len(line.text.split()) <= high:
            counts["clinc150: words"] += 1
            continue
        if not own_script(line.text, line.label):
            counts["clinc150: script"] += 1
            continue
        group = group_of(line.text)
        if group in seen:
            counts["clinc150: seen words"] += 1
            continue
        if line.text in near:
            counts["clinc150: near a seen text"] += 1
            continue
        if group in taken:
            counts["clinc150: duplicate"] += 1
            continue
        taken.add(group)
        rows.append((line, group, "gate"))
    english = len(rows)
    roman = 0
    pool = roman_pool(candidates, seen, near, used, lambda line: rank(line.source), counts)
    for line, group in pool:
        if roman >= english:
            break
        if group in labelled:
            counts["roman: labelled by hand"] += 1
            continue
        if rule(line.text):
            roman += 1
            rows.append((line, group, "gate"))
        else:
            counts["roman: left out by the rule"] += 1
            rows.append((line, group, "rule"))
    return rows


def _sources(path: Path) -> set[str]:
    return {row.split("\t", 1)[0] for row in path.read_text(encoding="utf-8").splitlines()}


def build_fresh(
    where: Path | None = None,
    *,
    paths: dict[str, Path] | None = None,
    labels_only: bool = False,
    rule: Callable[[str], bool] = roman_words,
    log: Callable[[str], None] = logger.info,
) -> dict:
    """Test 3's fresh slices beside a built corpus with its validation slices
    (``where``), from the corpus's downloads and CLINC150 (fetched into
    ``sources/clinc150`` when absent; every pin checked) unless ``paths`` are
    given. Writes ``labels.tsv`` (source, text: the rows to label by hand,
    drawn without the rule) and, unless ``labels_only``, ``fresh.tsv``
    (source, label, group, part, text) and ``fresh.json``. Returns the manifest."""
    from .. import lughah
    from . import corpus_digest, group_of, seeds

    where = where or folder()
    found = load(where)
    validation = load_validation(where)
    if found is None or validation is None:
        raise RuntimeError("no corpus with validation slices to build the fresh slices beside")
    pinned = {source.name: source for source in (*SOURCES, *MEASURED, CLINC150)}
    own = paths is None
    if paths is None:
        paths = {
            name: where / "sources" / name / pinned[name].file
            for name in ("massive", "hinglish-1m", "clinc150")
        }
        if not paths["clinc150"].exists():
            download(CLINC150, paths["clinc150"].parent)
    digests = {name: _sha256(paths[name]) for name in ("massive", "hinglish-1m", "clinc150")}
    for name, digest in digests.items():
        expected = pinned[name].sha256
        if own and expected is not None and digest != expected:
            raise Mismatch(f"{name}: SHA-256 {digest} is not the pinned {expected}")
    massive_lines = list(massive(paths["massive"]))
    seen_texts = [text for text, _label in lughah.corpus()]
    seen_texts += [text for text, _label in [*found.train, *found.written]]
    seen_texts += [text for text, _label, _group in found.short]
    seen_texts += [text for text, *_rest in validation]
    seen_texts += [line.text for line in massive_lines]
    seen = {group_of(text) for text in seen_texts}
    near = Near(seen_texts)
    log(f"fresh: {len(seen):,} seen texts' words indexed")
    share = float(
        ((found.manifest.get("settings") or {}).get("keep") or {}).get("hinglish-1m", 1.0)
    )
    hinglish_lines = list(hinglish(paths["hinglish-1m"]))
    seed_groups = {group_of(text) for text, _label in lughah.corpus()}
    # Conversations with an utterance already measured (v1's short slice,
    # v1.1's slices, by source) or a seed's words (the seeds number another file).
    used = {_conversation(s) for s in _sources(where / "short.tsv") if s.startswith("hinglish")}
    used |= {
        _conversation(s) for s in _sources(where / "validation.tsv") if s.startswith("hinglish")
    }
    used |= {_conversation(x.source) for x in hinglish_lines if group_of(x.text) in seed_groups}
    candidates = fresh_candidates(hinglish_lines, share)
    labels = label_sample(candidates, seen, near, used, size=LABELLED)
    label_body = "".join(f"{line.source}\t{line.text}\n" for line in labels)
    (where / "labels.tsv").write_text(label_body, encoding="utf-8")
    log(f"fresh: {len(labels)} rows to label by hand in {where / 'labels.tsv'}")
    label_sha = hashlib.sha256(label_body.encode("utf-8")).hexdigest()
    if labels_only:
        return {"labels": len(labels), "labels_sha256": label_sha}
    counts: Counter = Counter()
    clinc_lines = list(clinc(paths["clinc150"]))
    rows = pick_fresh(
        clinc_lines,
        candidates,
        seen,
        near,
        used,
        {group_of(line.text) for line in labels},
        rule=rule,
        counts=counts,
    )
    low, high = SHORT_WORDS
    short_queries = [line for line in clinc_lines if low <= len(line.text.split()) <= high]
    massive_groups = {group_of(line.text) for line in massive_lines}
    copies = sum(1 for line in short_queries if group_of(line.text) in massive_groups)
    body = "".join(
        f"{line.source}\t{line.label}\t{group}\t{name}\t{line.text}\n" for line, group, name in rows
    )
    (where / "fresh.tsv").write_text(body, encoding="utf-8")
    sizes: dict[str, dict[str, int]] = {}
    for line, _group, name in rows:
        sizes.setdefault(name, {})
        sizes[name][line.label] = sizes[name].get(line.label, 0) + 1
    manifest = {
        "version": 1,
        "created": datetime.now(UTC).isoformat(),
        "seeds_sha256": corpus_digest(seeds()),
        "train_sha256": found.manifest["train"]["sha256"],
        "short_sha256": found.manifest["short"]["sha256"],
        "validation_sha256": _sha256(where / "validation.tsv"),
        "labels_sha256": label_sha,
        "sources": {
            name: {"sha256": digests[name], "licence": pinned[name].licence, "pin_checked": True}
            for name in digests
        },
        "settings": {
            "salt": FRESH_SALT,
            "words": list(SHORT_WORDS),
            "edits": EDITS,
            "hinglish_read_share": share,
            "labelled": LABELLED,
            "clinc150_commit": CLINC150_COMMIT,
        },
        "seen_texts": len(seen),
        "clinc150": {
            "queries": len(clinc_lines),
            "of_3_to_8_words": len(short_queries),
            "exact_massive_copies": copies,
        },
        "lines": len(rows),
        "per_part": sizes,
        "dropped": dict(sorted(counts.items())),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    (where / "fresh.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"fresh: {len(rows)} messages in {where / 'fresh.tsv'}: {json.dumps(sizes)}")
    return manifest


def load_fresh(where: Path | None = None) -> list[tuple[str, str, str, str]] | None:
    """(text, label, group, part) of the fresh slices, when the file is whole
    and was built beside this corpus, its validation slices and these seeds."""
    from . import corpus_digest, seeds

    where = where or folder()
    found = load(where)
    try:
        manifest = json.loads((where / "fresh.json").read_text(encoding="utf-8"))
        body = (where / "fresh.tsv").read_text(encoding="utf-8")
        validation = _sha256(where / "validation.tsv")
    except (OSError, ValueError):
        return None
    if (
        found is None
        or hashlib.sha256(body.encode("utf-8")).hexdigest() != manifest.get("sha256")
        or manifest.get("train_sha256") != found.manifest["train"]["sha256"]
        or manifest.get("short_sha256") != found.manifest["short"]["sha256"]
        or manifest.get("validation_sha256") != validation
        or manifest.get("seeds_sha256") != corpus_digest(seeds())
    ):
        logger.warning("Ruh reader fresh slices: not built beside this corpus; not used")
        return None
    rows = []
    for row in body.splitlines():
        _source, label, group, name, text = row.split("\t", 4)
        rows.append((text, label, group, name))
    return rows


# ── v2: fresh messages people wrote, calibrated on one half, gated on the other

V2_LABELLED = 200  # rows labelled by hand to check the Roman rule before it is used
V2_LEAST = 2  # Hindi or Urdu words Qamus must read in a web or tweet row
V2_PER_DOCUMENT = 3  # lines a held-out FineWeb-2 document gives v2's slices at most
V2_HELD_SHARE = 1 / 4  # the held-out FineWeb-2 documents read for them (the rest unread)
V2_ROMAN = ("dakshina", "phinc", "fineweb-2")  # a third each of the Roman rows
BANKING77_COMMIT = "57ec275d8078af65b7731c2a98be812d844a6d6b"
PHINC_COMMIT = "44b5471df75e508b9d6fcdbcc93df04bb1e84056"
_POLYAI = f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{BANKING77_COMMIT}"
# Never trained on: their messages are only ever measured.
V2_SOURCES = (
    Source(
        "banking77-train",
        f"{_POLYAI}/banking_data/train.csv",
        "CC BY 4.0 (BANKING77, PolyAI; Casanueva et al. 2020)",
        "train.csv",
        "b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b",
        ("en",),
    ),
    Source(
        "banking77-test",
        f"{_POLYAI}/banking_data/test.csv",
        "CC BY 4.0 (BANKING77, PolyAI; Casanueva et al. 2020)",
        "test.csv",
        "d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d",
        ("en",),
    ),
    Source(
        "phinc",
        f"https://huggingface.co/datasets/LingoIITGN/PHINC/resolve/{PHINC_COMMIT}/PHINC.csv",
        "CC BY 4.0 (PHINC, Srivastava and Singh 2020; tweets: measured only)",
        "PHINC.csv",
        "325ba383cd6d73e0c3128885e2a79133e612ec03d18c8b55506d0b4b12ec68ed",
        ("hi-latn",),
    ),
)
# Dakshina 1.0's romanized sentences (CC BY-SA 4.0: measured only), read from
# the files inside dakshina_dataset_v1.0.tar; never downloaded here (the
# archive is large): the operator gives the folder, every file pinned.
DAKSHINA_TAR = "https://storage.googleapis.com/gresearch/dakshina/dakshina_dataset_v1.0.tar"
DAKSHINA_TAR_SHA256 = "83530bec211893d9df429298f42e63c350c25ad56f9f5172f85edb0575ee5b03"
DAKSHINA_LICENCE = "CC BY-SA 4.0 (Dakshina 1.0, Roark et al. 2020): measured only"
DAKSHINA = {
    "hi.romanized.rejoined.dev.roman.txt": (
        "106fbc342d19587a9a7a7687e6bd8a0312669c238511618148c01b49f1c6f881"
    ),
    "hi.romanized.rejoined.test.roman.txt": (
        "c49ebf67a0f7fdcc69f7f421dd21f6b48491b8db5fe3ef641078d660ce6bf1e7"
    ),
    "ur.romanized.rejoined.dev.roman.txt": (
        "fb388346c18082b8e12c342d4eec7e4ae0d9eb2af174632bcda23a2e71f17178"
    ),
    "ur.romanized.rejoined.test.roman.txt": (
        "ec3bc5ad395ad2ae2048b60825557af20d4a8fa8406de34d0f1863ff3b723360"
    ),
}


def v2_half(unit: str) -> str:
    """``calibration`` or ``gate``, fixed by SHA-256 of the unit (a query, a
    tweet, a sentence, a FineWeb-2 document: its lines lie in one half)."""
    value = int(hashlib.sha256(f"{V2_SALT}:{unit}".encode()).hexdigest()[:16], 16)
    return HALVES[value % 2]


def v2_order(unit: str, purpose: str = "order") -> str:
    return hashlib.sha256(f"{V2_SALT}:{purpose}:{unit}".encode()).hexdigest()


def unit_of(line: Line) -> str:
    """What one group of v2's paired test is: a FineWeb-2 line's document,
    any other row itself."""
    return line.document


def banking77(path: Path, split: str) -> Iterator[Line]:
    with path.open(encoding="utf-8", newline="") as handle:
        for number, row in enumerate(csv.DictReader(handle)):
            yield Line(f"banking77:{split}:{number}", "en", _clean(row["text"]), split)


_HANDLE = ("@", "#", "http", "www.")


def tweet(text: str) -> str:
    """A tweet's words: mentions, hashtags, links and ``RT`` set aside."""
    return " ".join(w for w in text.split() if not w.startswith(_HANDLE) and w != "RT")


def phinc(path: Path) -> Iterator[Line]:
    with path.open(encoding="utf-8", newline="") as handle:
        for number, row in enumerate(csv.DictReader(handle)):
            yield Line(f"phinc:{number}", "hi-latn", _clean(tweet(row["Sentence"])), "tweet")


def dakshina(folder: Path, check: bool = True) -> Iterator[Line]:
    """Dakshina's romanized Hindi and Urdu sentences (dev and test), each file
    refused when its SHA-256 is not the pinned one."""
    for name, digest in DAKSHINA.items():
        path = folder / name
        if check and _sha256(path) != digest:
            raise Mismatch(f"dakshina {name}: SHA-256 is not the pinned {digest}")
        language, _, _, split = name.split(".")[:4]
        for number, text in enumerate(path.read_text(encoding="utf-8").splitlines()):
            yield Line(f"dakshina:{language}:{split}:{number}", "hi-latn", _clean(text), split)


def _source_of(line: Line) -> str:
    """Which of v2's sources a row is from (``banking77``, ``dakshina``, …)."""
    head = line.origin
    return "fineweb-2" if head in FINEWEB_LATIN else head


class V2Pool:
    """Whether a row may be measured in v2's slices: 3 to 8 words, its
    language's script, words no seen text's and not near one, once per words."""

    def __init__(self, seen: set[str], near: Container[str], counts: Counter):
        self.seen, self.near, self.counts = seen, near, counts
        self.taken: set[str] = set()

    def fresh(self, line: Line) -> str | None:
        from . import group_of

        low, high = SHORT_WORDS
        name = _source_of(line)
        if not low <= len(line.text.split()) <= high:
            self.counts[f"{name}: words"] += 1
            return None
        if not own_script(line.text, line.label):
            self.counts[f"{name}: script"] += 1
            return None
        group = group_of(line.text)
        if group in self.seen:
            self.counts[f"{name}: seen words"] += 1
            return None
        if group in self.taken:
            self.counts[f"{name}: duplicate"] += 1
            return None
        if line.text in self.near:
            self.counts[f"{name}: near a seen text"] += 1
            return None
        return group


def v2_label_sample(
    roman: dict[str, list[Line]], seen: set[str], near: Container[str], size: int = V2_LABELLED
) -> list[Line]:
    """The rows to label by hand before the rule is used: the first ``size``
    of the web and tweet rows (one per unit) in SHA-256 label order that pass
    every condition but the rule."""
    pool = V2Pool(seen, near, Counter())
    candidates = [line for name in ("phinc", "fineweb-2") for line in roman.get(name, [])]
    chosen: list[Line] = []
    units: set[str] = set()
    for line in sorted(candidates, key=lambda x: (v2_order(unit_of(x), "label"), x.order)):
        if len(chosen) >= size:
            break
        if unit_of(line) in units:
            continue
        group = pool.fresh(line)
        if group is None:
            continue
        pool.taken.add(group)
        units.add(unit_of(line))
        chosen.append(line)
    return chosen


def pick_v2(
    english: Iterable[Line],
    roman: dict[str, list[Line]],
    seen: set[str],
    near: Container[str],
    labelled: Iterable[Line],
    *,
    rule: Callable[[str], bool] = lambda text: roman_words(text, V2_LEAST),
    counts: Counter | None = None,
) -> list[tuple[Line, str, str, str]]:
    """(line, group, half, part) of v2's slices. English: every BANKING77 query
    that is fresh (``V2Pool``), in SHA-256 order of its unit, part ``in``. Each
    of the three Roman sources (``V2_ROMAN``) then gives each half at most a
    third of that half's English rows (rounded up), in its own SHA-256 order,
    at most ``V2_PER_DOCUMENT`` rows a FineWeb-2 document; a web or tweet row
    counts only where ``rule`` holds (part ``in``), the others are kept apart,
    as many again at most (part ``rule``, reported only); Dakshina's rows are
    Hindi or Urdu by construction. The hand-labelled rows' units are left out.
    A row's group is its unit (``unit_of``); its half is the unit's."""
    counts = counts if counts is not None else Counter()
    labelled = list(labelled)
    pool = V2Pool(seen | {_group(line.text) for line in labelled}, near, counts)
    left_out = {unit_of(line) for line in labelled}
    rows: list[tuple[Line, str, str, str]] = []
    for line in sorted(english, key=lambda x: v2_order(unit_of(x))):
        group = pool.fresh(line)
        if group is None:
            continue
        pool.taken.add(group)
        unit = unit_of(line)
        rows.append((line, unit, v2_half(unit), "in"))
    per_half = Counter(where for _l, _u, where, _p in rows)
    cap = {name: math.ceil(per_half[name] / 3) for name in HALVES}
    for name in V2_ROMAN:
        have: Counter = Counter()
        apart: Counter = Counter()
        from_unit: Counter = Counter()
        for line in sorted(roman.get(name, []), key=lambda x: (v2_order(unit_of(x)), x.order)):
            unit = unit_of(line)
            where = v2_half(unit)
            if all(have[h] >= cap[h] and apart[h] >= cap[h] for h in HALVES):
                break
            if unit in left_out:
                counts[f"{name}: labelled by hand"] += 1
                continue
            if from_unit[unit] >= V2_PER_DOCUMENT:
                continue
            if have[where] >= cap[where] and apart[where] >= cap[where]:
                continue
            group = pool.fresh(line)
            if group is None:
                continue
            holds = name == "dakshina" or rule(line.text)
            if holds and have[where] < cap[where]:
                have[where] += 1
                part = "in"
            elif not holds and apart[where] < cap[where]:
                apart[where] += 1
                part = "rule"
            else:
                continue
            pool.taken.add(group)
            from_unit[unit] += 1
            rows.append((line, unit, where, part))
    return rows


def _rows_tsv(rows: Sequence[tuple[Line, str, str, str]]) -> str:
    return "".join(
        f"{line.source}\t{line.label}\t{group}\t{where}\t{part}\t{line.text}\n"
        for line, group, where, part in rows
    )


OLD_SLICES = ("short.tsv", "validation.tsv", "fresh.tsv", "labels.tsv")
V2_SLICES = ("v2.tsv", "v2_labels.tsv")


def _last_columns(base: Path, names: Sequence[str]) -> list[str]:
    """The text (last column) of every row of these slice files that exist."""
    texts: list[str] = []
    for name in names:
        path = base / name
        if path.exists():
            texts += [
                row.rsplit("\t", 1)[-1]
                for row in path.read_text(encoding="utf-8").splitlines()
                if row.strip()
            ]
    return texts


def measured_texts(old: Path | None, where: Path | None = None) -> list[str]:
    """The text of every message measured so far: v1's short slice, v1.1's
    and test 3's slices and labels (beside ``old``, v1's corpus), and v2's
    slices and labels (beside ``where``, v2's corpus)."""
    texts = _last_columns(old, OLD_SLICES) if old is not None else []
    return texts + _last_columns(where or folder(), V2_SLICES)


def build_v2(
    where: Path | None = None,
    *,
    old: Path,
    dakshina_folder: Path,
    paths: dict[str, Path] | None = None,
    labels_only: bool = False,
    rule: Callable[[str], bool] = lambda text: roman_words(text, V2_LEAST),
    rows_of: Callable[[Path], Iterable[tuple[str, str]]] = parquet_rows,
    log: Callable[[str], None] = logger.info,
) -> dict:
    """v2's slices, written beside v2's corpus (``where``) before it is built:
    ``v2_labels.tsv`` (the rows to label by hand, drawn without the rule) and,
    unless ``labels_only``, ``v2.tsv`` (source, label, group, half, part, text)
    and ``v2.json``. Seen (never measured here): every line of Lughah's
    corpus, every line of v1's corpus (``old``: its training lines, its short
    slice, v1.1's and test 3's slices and labels), every MASSIVE 1.1
    utterance and every CLINC150 query; near copies too. Every file pinned
    (downloaded into ``sources/`` when absent, unless ``paths`` are given)."""
    from .. import lughah
    from . import corpus_digest, seeds

    where = where or folder()
    found = load(old)
    if found is None:
        raise RuntimeError(f"no v1 corpus in {old} to read what was seen")
    pinned = {s.name: s for s in (*SOURCES, *MEASURED, CLINC150, *V2_SOURCES)}
    wanted = ("massive", "clinc150", *FINEWEB_LATIN, *(s.name for s in V2_SOURCES))
    own = paths is None
    if paths is None:
        paths = {}
        for name in wanted:
            base = old if name in ("massive", "clinc150") else where
            target = base / "sources" / name
            path = target / pinned[name].file
            if not path.exists():
                download(pinned[name], target)
            paths[name] = path
    digests = {name: _sha256(paths[name]) for name in wanted}
    for name, digest in digests.items():
        if own and digest != pinned[name].sha256:
            raise Mismatch(f"{name}: SHA-256 {digest} is not the pinned {pinned[name].sha256}")
    massive_lines = list(massive(paths["massive"]))
    seen_texts = [text for text, _label in lughah.corpus()]
    seen_texts += [text for text, _label in [*found.train, *found.written]]
    seen_texts += _last_columns(old, OLD_SLICES)
    seen_texts += [line.text for line in massive_lines]
    seen_texts += [line.text for line in clinc(paths["clinc150"])]
    seen = {_group(text) for text in seen_texts}
    near = Near(seen_texts)
    log(f"v2: {len(seen):,} seen texts' words indexed")
    english = [
        *banking77(paths["banking77-train"], "train"),
        *banking77(paths["banking77-test"], "test"),
    ]
    roman: dict[str, list[Line]] = {
        "dakshina": list(dakshina(dakshina_folder, check=own)),
        "phinc": list(phinc(paths["phinc"])),
        "fineweb-2": [],
    }
    for name in FINEWEB_LATIN:
        documents = (
            (identifier, text)
            for identifier, text in rows_of(paths[name])
            if held_document(f"{name}:{identifier}")
            and int(v2_order(f"{name}:{identifier}", "read")[:16], 16) < V2_HELD_SHARE * 16**16
        )
        roman["fineweb-2"] += fineweb(documents, name, held=True)
    labels = v2_label_sample(roman, seen, near)
    label_body = "".join(f"{line.source}\t{line.text}\n" for line in labels)
    (where / "v2_labels.tsv").write_text(label_body, encoding="utf-8")
    label_sha = hashlib.sha256(label_body.encode("utf-8")).hexdigest()
    log(f"v2: {len(labels)} rows to label by hand in {where / 'v2_labels.tsv'}")
    if labels_only:
        return {"labels": len(labels), "labels_sha256": label_sha}
    counts: Counter = Counter()
    rows = pick_v2(english, roman, seen, near, labels, rule=rule, counts=counts)
    body = _rows_tsv(rows)
    (where / "v2.tsv").write_text(body, encoding="utf-8")
    sizes: dict[str, dict[str, int]] = {}
    for line, _group_name, half_name, part in rows:
        key = f"{half_name} {part}"
        sizes.setdefault(key, {})
        sizes[key][_source_of(line)] = sizes[key].get(_source_of(line), 0) + 1
    manifest = {
        "version": 2,
        "created": datetime.now(UTC).isoformat(),
        "seeds_sha256": corpus_digest(seeds()),
        "old_train_sha256": found.manifest["train"]["sha256"],
        "labels_sha256": label_sha,
        "sources": {
            **{
                name: {
                    "sha256": digests[name],
                    "licence": pinned[name].licence,
                    "url": pinned[name].url,
                }
                for name in wanted
            },
            "dakshina": {
                "files": DAKSHINA,
                "archive": DAKSHINA_TAR,
                "archive_sha256": DAKSHINA_TAR_SHA256,
                "licence": DAKSHINA_LICENCE,
            },
        },
        "settings": {
            "salt": V2_SALT,
            "words": list(SHORT_WORDS),
            "edits": EDITS,
            "least": V2_LEAST,
            "per_document": V2_PER_DOCUMENT,
            "held_documents": f"1/{HELD_DOCUMENTS}",
            "held_share_read": V2_HELD_SHARE,
            "labelled": V2_LABELLED,
        },
        "seen_texts": len(seen),
        "lines": len(rows),
        "sizes": sizes,
        "dropped": dict(sorted(counts.items())),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    (where / "v2.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"v2: {len(rows)} messages in {where / 'v2.tsv'}: {json.dumps(sizes)}")
    return manifest


def load_v2(where: Path | None = None) -> list[dict[str, str]] | None:
    """v2's slices (text, label, group, half, part, source), when the file is
    whole and was built against these seeds; otherwise None."""
    from . import corpus_digest, seeds

    where = where or folder()
    try:
        manifest = json.loads((where / "v2.json").read_text(encoding="utf-8"))
        body = (where / "v2.tsv").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != manifest.get("sha256") or manifest.get(
        "seeds_sha256"
    ) != corpus_digest(seeds()):
        logger.warning("Ruh reader v2 slices: changed, or built against other seeds; not used")
        return None
    rows = []
    for row in body.splitlines():
        source, label, group, where_half, part, text = row.split("\t", 5)
        rows.append(
            {
                "text": text,
                "label": label,
                "group": group,
                "half": where_half,
                "part": part,
                "source": source.split(":", 1)[0],
            }
        )
    return rows


def load(where: Path | None = None) -> Corpus | None:
    """The built corpus, when its files are whole and it was built against
    the seeds as they are now; otherwise None."""
    from . import corpus_digest, seeds

    where = where or folder()
    try:
        manifest = json.loads((where / "manifest.json").read_text(encoding="utf-8"))
        train_body = (where / "train.tsv").read_text(encoding="utf-8")
        short_body = (where / "short.tsv").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    if (
        hashlib.sha256(train_body.encode("utf-8")).hexdigest() != manifest["train"]["sha256"]
        or hashlib.sha256(short_body.encode("utf-8")).hexdigest() != manifest["short"]["sha256"]
    ):
        logger.warning("Ruh reader corpus: a file changed since it was built; not used")
        return None
    if manifest.get("seeds_sha256") != corpus_digest(seeds()):
        logger.info("Ruh reader corpus: built against other seeds; rebuild it")
        return None
    train, written = [], []
    for row in train_body.splitlines():
        source, label, text = row.split("\t", 2)
        (written if model_written(source) else train).append((text, label))
    short = []
    for row in short_body.splitlines():
        _source, label, group, text = row.split("\t", 3)
        short.append((text, label, group))
    if written:
        logger.info("Ruh reader corpus: %d model-written lines are not trained on", len(written))
    return Corpus(train, short, manifest, written)
