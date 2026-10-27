"""Sarf (صرف, morphology): the root, pattern (wazn), part of speech and meaning
of an Arabic word, read from the Quranic Arabic Corpus, never guessed by rule.

The data is downloaded once into ``$MIZAN_DATA_DIR/morphology`` and pinned by
SHA-256; it is GPL and is not shipped with MIZAN:
- ``quran-morphology.txt``: the Quranic Arabic Corpus morphology v0.4 (Kais
  Dukes, University of Leeds, https://corpus.quran.com), as corrected in the
  mustafa0x fork: every segment of every word of the Quran with its root,
  lemma and tags;
- ``word-by-word.txt``: the corpus's English gloss of each of the 77,429
  words, in the same order.

How a word is read:
1. **A word the Quran contains** is given its own analysis: the reading it has
   most often in the corpus, with its vowelled wazn (كَاتِب → فَاعِل).
2. **Any other word** is read by a noisy-channel model whose every
   probability is counted in the corpus (add-one smoothed): each split into a
   prefix, a stem and a suffix the corpus has seen, each pattern (the stem
   with its root letters replaced by ف ع ل) and each root that can fill it,
   with how the corpus writes each root letter (a weak و can be written ا):

       log P(prefix) + log P(suffix) + log P(pattern) + log P(root)
         + Σ log P(written letter | root letter)

   The most probable reading wins (MAP). The part of speech is the one the
   corpus gives that pattern most often.

A root's meaning is the corpus's own glosses of its most frequent words.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import httpx

logger = logging.getLogger("mizan.tadbir.sarf")

SOURCES = {
    "quran-morphology.txt": (
        "https://raw.githubusercontent.com/mustafa0x/quran-morphology/"
        "8f38b39016824284f9ed16ae15069ff9102c4acf/quran-morphology.txt",
        "742bfac59941b2cb09736d5b7aae694af50792261fb8450cbf6afafcc340645f",
    ),
    "word-by-word.txt": (
        "https://raw.githubusercontent.com/kaisdukes/quranic-corpus-api/"
        "17a9062416eccc332111ef3e84f74072d709e187/src/main/resources/data/translation/"
        "word-by-word.txt",
        "f732efe12ed56c36c2f94525ed28f4b4e9a4290bdf31a2640bc210d6a9e015d5",
    ),
}
ATTRIBUTION = "Quranic Arabic Corpus (corpus.quran.com), GPL"
PLACEHOLDERS = "فعلل"  # the first, second, third (and fourth) root letter

_MARKS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u06d6-\u06ed\u0640]")
_FOLD = str.maketrans({"ٱ": "ا", "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ؤ": "ء", "ئ": "ء"})
_ARABIC_WORD = re.compile(r"[\u0621-\u064a\u0671\u0670\u064b-\u065f\u06d6-\u06ed]+")

# The corpus's tags, named for a reader (these are the corpus's own categories).
_LABELS = (
    ("ACT_PCPL", "active participle"),
    ("PASS_PCPL", "passive participle"),
    ("VN", "verbal noun"),
    ("PN", "proper noun"),
    ("ADJ", "adjective"),
    ("PRON", "pronoun"),
    ("DEM", "demonstrative"),
    ("REL", "relative pronoun"),
)
_VERB_LABELS = {"PERF": "verb (past)", "IMPF": "verb (present)", "IMPV": "verb (command)"}


class Unavailable(RuntimeError):
    """The corpus could not be read (offline, or a download that did not verify)."""


def fold(text: str) -> str:
    """Letters only, as people type them: no vowel marks, one alef."""
    text = text.replace("\u0670", "ا")  # the small alef the Uthmani script writes
    return _MARKS.sub("", text).translate(_FOLD)


def words(text: str) -> list[str]:
    return _ARABIC_WORD.findall(text or "")


def label(pos: str, tags: set[str]) -> str:
    if pos == "V":
        return next((name for tag, name in _VERB_LABELS.items() if tag in tags), "verb")
    if pos == "N":
        return next((name for tag, name in _LABELS if tag in tags), "noun")
    return "particle"


# ── alignment of a root with a written stem ──────────────────────────────


def align(root: str, stem: str) -> list[int | None] | None:
    """For each root letter, the stem position that writes it (or None when the
    stem drops it), in order: the alignment with the most identical letters,
    then the fewest dropped. None when the root cannot be read in the stem."""
    best: tuple[tuple[int, int], list[int | None]] | None = None

    def walk(index: int, start: int, chosen: list[int | None], same: int, dropped: int) -> None:
        nonlocal best
        if index == len(root):
            key = (same, -dropped)
            if best is None or key > best[0]:
                best = (key, list(chosen))
            return
        for position in range(start, len(stem)):
            match = stem[position] == root[index]
            walk(index + 1, position + 1, [*chosen, position], same + match, dropped)
        if dropped < 1:  # a weak or doubled letter may go unwritten, once
            walk(index + 1, start, [*chosen, None], same, dropped + 1)

    walk(0, 0, [], 0, 0)
    if best is None or best[0][0] < len(root) - 1 - (best[0][1] == 0):
        return None  # more than one root letter changed: not this root
    return best[1]


def template(stem: str, positions: list[int | None]) -> str:
    letters = list(stem)
    for number, position in enumerate(positions):
        if position is not None:
            letters[position] = PLACEHOLDERS[min(number, 3)]
    return "".join(letters)


def wazn(vowelled: str, root: str) -> str:
    """The vowelled pattern of a vowelled stem: its root letters become ف ع ل."""
    base = [(index, char) for index, char in enumerate(vowelled) if fold(char)]
    folded = "".join(fold(char) for _, char in base)
    positions = align(root, folded)
    if positions is None:
        return ""
    out = list(vowelled)
    for number, position in enumerate(positions):
        if position is not None:
            out[base[position][0]] = PLACEHOLDERS[min(number, 3)]
    text = "".join(out).replace("\u0670", "ا")
    return re.sub(r"[\u064b-\u0652\u06d6-\u06ed]+$", "", text)  # no case ending


# ── the corpus ───────────────────────────────────────────────────────────


@dataclass
class Reading:
    root: str
    lemma: str
    pos: str
    wazn: str
    verb_form: int | None
    gloss: str
    source: str  # "quran" (a word of the Quran) or "inferred"
    probability: float = 1.0
    prefix: str = ""
    suffix: str = ""

    def to_dict(self, meaning: str, occurrences: int) -> dict:
        return {
            "root": self.root,
            "root_letters": "-".join(self.root),
            "lemma": self.lemma,
            "pattern": self.wazn,
            "pos": self.pos,
            "verb_form": self.verb_form,
            "gloss": self.gloss,
            "meaning": meaning,
            "root_occurrences": occurrences,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "source": self.source,
            "probability": round(self.probability, 4),
        }


@dataclass
class Corpus:
    words: dict[str, Counter] = field(default_factory=dict)  # folded word → readings
    word_glosses: dict[tuple, Counter] = field(default_factory=lambda: defaultdict(Counter))
    roots: Counter = field(default_factory=Counter)
    prefixes: Counter = field(default_factory=Counter)
    suffixes: Counter = field(default_factory=Counter)
    patterns: Counter = field(default_factory=Counter)
    pattern_pos: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    pattern_wazn: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    writes: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    glosses: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    total_words: int = 0

    # probabilities, add-one smoothed over what the corpus has seen
    def p(self, table: Counter, key: str) -> float:
        return (table.get(key, 0) + 1) / (sum(table.values()) + len(table) + 1)

    def written(self, root_letter: str, letter: str) -> float:
        table = self.writes.get(root_letter) or Counter()
        return (table.get(letter, 0) + 0.1) / (sum(table.values()) + 0.1 * 40)

    def meaning(self, root: str) -> str:
        found = [gloss for gloss, _ in self.glosses.get(root, Counter()).most_common(3)]
        return "; ".join(found)


def _gloss(text: str) -> str:
    plain = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)
    plain = re.sub(r"[\"“”,.;:!?]", " ", plain)
    return " ".join(plain.split()).lower()


def build(morphology: str, glosses: list[str]) -> Corpus:
    """Count everything the analyzer uses from the corpus text."""
    corpus = Corpus()
    segments: dict[str, list[tuple[str, str, set[str], dict[str, str]]]] = {}
    order: list[str] = []
    for line in morphology.splitlines():
        fields = line.split("\t")
        if len(fields) != 4 or line.startswith("#"):
            continue
        location, form, pos, features = fields
        word = location.rsplit(":", 1)[0]
        if word not in segments:
            segments[word] = []
            order.append(word)
        tags = set(features.split("|"))
        values = dict(tag.split(":", 1) for tag in tags if ":" in tag)
        segments[word].append((form, pos, tags, values))
    for number, word in enumerate(order):
        parts = segments[word]  # (form, tag, tags, values) of each segment
        gloss = _gloss(glosses[number]) if number < len(glosses) else ""
        stem = next(
            (part for part in parts if "PREF" not in part[2] and "SUFF" not in part[2]), None
        )
        if stem is None:
            continue
        form, pos, tags, values = stem[0], stem[1], stem[2], stem[3]
        prefix = "".join(fold(p[0]) for p in parts if "PREF" in p[2])
        suffix = "".join(fold(p[0]) for p in parts if "SUFF" in p[2])
        root = fold(values.get("ROOT", ""))
        name = label(pos, tags)
        corpus.total_words += 1
        corpus.prefixes[prefix] += 1
        corpus.suffixes[suffix] += 1
        vowelled = wazn(form, root) if root else ""
        reading = (
            root,
            values.get("LEM", ""),
            name,
            vowelled,
            int(values["VF"]) if values.get("VF", "").isdigit() else None,
        )
        whole = fold("".join(part[0] for part in parts))
        corpus.words.setdefault(whole, Counter())[reading] += 1
        if gloss:
            corpus.word_glosses[(whole, reading)][gloss] += 1
        if not root:
            continue
        corpus.roots[root] += 1
        corpus.glosses[root][gloss] += 1 if gloss else 0
        folded_stem = fold(form)
        positions = align(root, folded_stem)
        if positions is None:
            continue
        shape = template(folded_stem, positions)
        corpus.patterns[shape] += 1
        corpus.pattern_pos[shape][name] += 1
        if vowelled:
            corpus.pattern_wazn[shape][vowelled] += 1
        for root_letter, position in zip(root, positions, strict=False):
            if position is not None:
                corpus.writes[root_letter][folded_stem[position]] += 1
    for root in list(corpus.glosses):
        corpus.glosses[root] = Counter(
            {gloss: count for gloss, count in corpus.glosses[root].items() if gloss}
        )
    return corpus


# ── reading a word ───────────────────────────────────────────────────────


def _from_quran(corpus: Corpus, word: str) -> list[Reading]:
    """The word's readings in the Quran, most frequent first."""
    readings = corpus.words.get(word)
    if not readings:
        return []
    total = sum(readings.values())
    return [
        Reading(
            root=key[0],
            lemma=key[1],
            pos=key[2],
            wazn=key[3],
            verb_form=key[4],
            gloss=_top(corpus.word_glosses.get((word, key))),
            source="quran",
            probability=count / total,
        )
        for key, count in readings.most_common(3)
    ]


def _top(table: Counter | None) -> str:
    return table.most_common(1)[0][0] if table else ""


def _inferred(corpus: Corpus, word: str) -> Reading | None:
    """The most probable split, pattern and root (MAP over the corpus counts)."""
    scored: list[tuple[float, Reading]] = []
    for prefix in [p for p in corpus.prefixes if word.startswith(p)]:
        for suffix in [s for s in corpus.suffixes if word.endswith(s)]:
            stem = word[len(prefix) : len(word) - len(suffix) if suffix else None]
            if len(stem) < 2:
                continue
            base = math.log(corpus.p(corpus.prefixes, prefix)) + math.log(
                corpus.p(corpus.suffixes, suffix)
            )
            for size in (3, 4):
                for positions in combinations(range(len(stem)), size):
                    shape = list(stem)
                    for number, position in enumerate(positions):
                        shape[position] = PLACEHOLDERS[min(number, 3)]
                    pattern = "".join(shape)
                    if pattern not in corpus.patterns:
                        continue
                    for root, written in _roots(corpus, stem, positions):
                        score = (
                            base
                            + math.log(corpus.p(corpus.patterns, pattern))
                            + math.log(corpus.p(corpus.roots, root))
                            + written
                        )
                        pos = corpus.pattern_pos[pattern].most_common(1)[0][0]
                        shown = corpus.pattern_wazn[pattern].most_common(1)
                        scored.append(
                            (
                                score,
                                Reading(
                                    root,
                                    "",
                                    pos,
                                    shown[0][0] if shown else pattern,
                                    None,
                                    "",
                                    "inferred",
                                    prefix=prefix,
                                    suffix=suffix,
                                ),
                            )
                        )
    if not scored:
        return None
    top = max(score for score, _ in scored)
    total = sum(math.exp(score - top) for score, _ in scored)
    score, best = max(scored, key=lambda item: item[0])
    best.probability = math.exp(score - top) / total
    return best


def _roots(corpus: Corpus, stem: str, positions: tuple[int, ...]):
    """Roots the corpus knows whose letters, as the corpus writes them, give
    the stem's letters at these positions; with log P(written | root letter)."""
    options = []
    for position in positions:
        letter = stem[position]
        options.append(
            [
                (root_letter, math.log(corpus.written(root_letter, letter)))
                for root_letter, table in corpus.writes.items()
                if table.get(letter)
            ]
        )
    found: list[tuple[str, float]] = []

    def walk(index: int, letters: str, score: float) -> None:
        if index == len(options):
            if letters in corpus.roots:
                found.append((letters, score))
            return
        for root_letter, written in options[index]:
            walk(index + 1, letters + root_letter, score + written)

    walk(0, "", 0.0)
    return found


def analyze_word(corpus: Corpus, surface: str) -> dict:
    word = fold(surface)
    readings = _from_quran(corpus, word)
    inferred = None if readings else _inferred(corpus, word)
    if inferred is not None:
        readings = [inferred]
    if not readings:
        return {"surface": surface, "root": "", "source": "unknown", "is_stopword": False}
    reading = readings[0]
    found = reading.to_dict(corpus.meaning(reading.root), corpus.roots.get(reading.root, 0))
    found["surface"] = surface
    found["is_stopword"] = not reading.root and reading.pos in {"particle", "pronoun"}
    # The same letters read otherwise in the Quran (كتب: kutiba, kataba, kutub).
    found["alternatives"] = [
        {
            "root_letters": "-".join(other.root),
            "pattern": other.wazn,
            "pos": other.pos,
            "lemma": other.lemma,
            "share": round(other.probability, 4),
        }
        for other in readings[1:]
    ]
    return found


def analyze(corpus: Corpus, text: str) -> list[dict]:
    return [analyze_word(corpus, word) for word in words(text)]


# ── loading ──────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "morphology"


async def _download(name: str) -> str:
    url, digest = SOURCES[name]
    path = _data_dir() / name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return path.read_text(encoding="utf-8")
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        raise Unavailable("The Quranic Arabic Corpus is not reachable right now") from None
    if hashlib.sha256(response.content).hexdigest() != digest:
        raise Unavailable(f"{name} did not match its pinned SHA-256")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_bytes(response.content)
    temporary.replace(path)
    text: str = response.content.decode("utf-8")
    return text


_lock = asyncio.Lock()
_corpus: Corpus | None = None


async def corpus() -> Corpus:
    """The corpus, downloaded once and counted off the event loop."""
    global _corpus
    async with _lock:
        if _corpus is None:
            morphology = await _download("quran-morphology.txt")
            glosses = (await _download("word-by-word.txt")).splitlines()
            _corpus = await asyncio.to_thread(build, morphology, glosses)
        return _corpus
