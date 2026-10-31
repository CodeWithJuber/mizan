"""The Ruh reader's own corpus: licence-clean text that is not Lughah's seeds.

Lughah's seeds stay Lughah's. The reader learned from them alone at first
(about 200 KB), and its development bits per byte were still falling when its
time ran out; this corpus gives it more of each language to learn from, and a
slice of short requests people actually write to be judged on.

Sources (licences and notices in ``LICENSES.md`` beside this file):

- **Tatoeba** per-language exports (eng, hin, urd, ara), CC BY 2.0 FR. Every
  sentence id Lughah's seeds already use is left out. The exports change
  weekly, so each file's SHA-256 is recorded, not pinned.
- **Abhishekcr448/Hinglish-Everyday-Conversations-1M** (MIT), pinned by
  commit and SHA-256: Roman Hindi/Urdu. Synthetic (written by a language
  model), so it is training text, and its held-out rows are a check of style,
  not of how people write.
- **MASSIVE 1.1** (Amazon, CC BY 4.0; built on SLURP, CC BY 4.0), pinned by
  SHA-256: en-US, hi-IN, ur-PK, ar-SA. The ``train`` partition is training
  text; the ``test`` partition's utterances of 3 to 8 words are the held-out
  slice of short requests (``short.tsv``), never trained on.

Every line, before it is kept for training:

1. **its own script**: more than half of its letters are written in the
   language's script (MASSIVE's ar-SA has utterances written in English only);
2. **not the seeds'**: neither a Tatoeba id the seeds use nor a line whose
   words as read (``ruh_reader.group_of``: letters and marks, lower case) are a
   seed's, in any split, so nothing Lughah's held-out or development groups
   hold is trained on;
3. **not held out here**: not a short message of the held-out slice;
4. **once**: one line per group;
5. **never scripture**: ``ruh_reader.scripture``, with Iqtibas's full texts in
   memory (the mushaf and the four translations Fihris downloads), so no
   Quranic span ever reaches the loss.

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
import os
import tarfile
from collections import Counter, defaultdict
from collections.abc import Callable, Container, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.ruh_reader.corpus")

VERSION = 1
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
SOURCES = (
    Source(
        "massive",
        "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz",
        "CC BY 4.0 (MASSIVE 1.1, Amazon; built on SLURP, CC BY 4.0)",
        "amazon-massive-dataset-1.1.tar.gz",
        "4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577",
        tuple(MASSIVE_LOCALES),
    ),
    Source(
        "hinglish-1m",
        "https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M"
        f"/resolve/{HINGLISH_COMMIT}/hinglish_conversations.csv",
        "MIT (Abhishekcr448/Hinglish-Everyday-Conversations-1M)",
        "hinglish_conversations.csv",
        "3ec4aa4f23394dc7e6ecef990453641fa85c0f03175ad60f1408e3b3c0c36484",
        ("hi-latn",),
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
)
# Large sources are read in part: a line is a candidate when its rank (by
# SHA-256 of its source id) falls in this share. The rank also orders the
# lines taken, so a cut here only shortens the order, never changes it. Few
# Hinglish utterances are 3 to 8 words, so a quarter is read to hold 2,000 out.
KEEP = {"tatoeba-eng": 1 / 16, "hinglish-1m": 1 / 4}


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
        """The source's name (``tatoeba-eng``, ``massive``, ``hinglish-1m``)."""
        head = self.source.split(":", 1)[0]
        return f"tatoeba-{TATOEBA[self.label]}" if head == "tatoeba" else head


def rank(source: str) -> int:
    return int(hashlib.sha256(f"{SALT}:{source}".encode()).hexdigest()[:16], 16)


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


def _check_scripture(
    texts: Sequence[str], scripture: Callable[[str], bool], workers: int
) -> list[bool]:
    if workers <= 1 or len(texts) < 1000:
        return [scripture(text) for text in texts]
    import multiprocessing

    # Forked workers share the parent's loaded Quran texts.
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        return list(pool.map(scripture, texts, chunksize=256))


def pick_train(
    pools: dict[str, dict[str, list[Line]]],
    *,
    seed_groups: set[str],
    seed_sources: set[str],
    excluded: set[str],
    scripture: Callable[[str], bool],
    bytes_per_language: int = BYTES_PER_LANGUAGE,
    counts: Counts | None = None,
    workers: int = 1,
) -> list[Line]:
    """Training lines per language (``pools``: label → origin → lines), taken
    in rank order round robin over the language's sources until it holds
    ``bytes_per_language`` bytes of words, each passing every rule."""
    from . import group_of

    counts = counts if counts is not None else Counts()
    kept: list[Line] = []
    for label in sorted(pools):
        queues = {
            origin: sorted(lines, key=lambda item: rank(item.source))
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
                if rule is not None:
                    counts.dropped[(origin, rule)] += 1
                    continue
                seen.add(group)
                candidates.append((line, size))
                taken += size
        verdicts = _check_scripture([line.text for line, _ in candidates], scripture, workers)
        total = 0
        for (line, size), holy in zip(candidates, verdicts, strict=True):
            if total >= bytes_per_language:
                break
            if holy:
                counts.dropped[(line.origin, "scripture")] += 1
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
    scripture: Callable[[str], bool],
    bytes_per_language: int = BYTES_PER_LANGUAGE,
    hinglish_count: int = SHORT_HINGLISH,
    workers: int = 1,
) -> tuple[list[Line], list[tuple[Line, str]], Counts]:
    """The training lines and the held-out short slice from the sources' lines
    (``seed_rows``: every line of Lughah's corpus, neutral classes included)."""
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
        elif line.kind == "train":
            pools[line.label][line.origin].append(line)
            if line.label == "hi-latn":
                roman.append(line)
        else:
            counts.dropped[(line.origin, f"partition {line.kind}")] += 1
    short = pick_short(test, roman, seed_groups, hinglish_count=hinglish_count)
    excluded = {group_of(line.text) for line, _group in short}
    train = pick_train(
        pools,
        seed_groups=seed_groups,
        seed_sources=seed_sources,
        excluded=excluded,
        scripture=scripture,
        bytes_per_language=bytes_per_language,
        counts=counts,
        workers=workers,
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


def read_sources(paths: dict[str, Path], labels: Iterable[str]) -> Iterator[Line]:
    """Every line of the downloaded sources, for the given languages."""
    wanted = set(labels)
    for source in SOURCES:
        path = paths.get(source.name)
        if path is None or not wanted & set(source.labels):
            continue
        share = KEEP.get(source.name, 1.0)
        if source.name == "massive":
            yield from massive(path, [label for label in source.labels if label in wanted])
        elif source.name == "hinglish-1m":
            yield from hinglish(path, share)
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
    paths: dict[str, Path] | None = None,
    out: Path | None = None,
    log: Callable[[str], None] = logger.info,
) -> dict:
    """Download the sources (unless ``paths`` are given), pick the lines and
    write the corpus. Returns its manifest."""
    from .. import lughah
    from . import corpus_digest, seeds

    out = out or folder()
    rows = seeds()
    labels = sorted({label for _text, label in rows})
    check = scripture or full_scripture()
    fetched: dict[str, dict] = {}
    if paths is None:
        paths = {}
        for source in SOURCES:
            if not set(labels) & set(source.labels):
                continue
            target = out / "sources" / source.name
            log(f"corpus: fetching {source.name}")
            fetched[source.name] = download(source, target)
            paths[source.name] = target / source.file
    else:
        fetched = {name: {"sha256": _sha256(path)} for name, path in paths.items()}
    train, short, counts = assemble(
        read_sources(paths, labels),
        labels=labels,
        seed_rows=lughah.corpus(),
        seed_sources=seed_ids(),
        scripture=check,
        bytes_per_language=bytes_per_language,
        hinglish_count=hinglish_count,
        workers=workers,
    )
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
        },
        # The full check (Iqtibas's Quran texts in memory) unless a caller gave its own.
        "scripture": {"checked": True, "iqtibas": scripture is None},
        "sources": [
            {
                "name": source.name,
                "url": source.url,
                "licence": source.licence,
                "pinned": source.sha256 is not None,
                **fetched.get(source.name, {}),
            }
            for source in SOURCES
            if source.name in paths
        ],
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
    train: list[tuple[str, str]]  # (text, label)
    short: list[tuple[str, str, str]]  # (text, label, group)
    manifest: dict


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
    pinned = {source.name: source for source in SOURCES}
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
    excluded |= {group_of(text) for text, _label in found.train}
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


def roman_words(text: str) -> bool:
    """Whether Qamus reads one of the words as a Hindi or Urdu word written in
    Latin letters (``qamus.read_roman``: P > ½, not an English word). A
    Hinglish-1M row counts as Roman Hindi/Urdu only then: the dataset labels
    every utterance so, and many are written in English alone."""
    from .. import qamus

    return any(qamus.read_roman(word) for word in qamus.tokens(text))


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
    pinned = {source.name: source for source in (*SOURCES, CLINC150)}
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
    seen_texts += [text for text, _label in found.train]
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
    train = []
    for row in train_body.splitlines():
        _source, label, text = row.split("\t", 2)
        train.append((text, label))
    short = []
    for row in short_body.splitlines():
        _source, label, group, text = row.split("\t", 3)
        short.append((text, label, group))
    return Corpus(train, short, manifest)
