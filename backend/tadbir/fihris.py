"""Fihris: find ayahs by their words, however the person spells them.

"Sidratul muntaha kya hai", "inna lillahi wa inna ilayhi rajiun", "light upon
light", "قرآن میں صبر": MIZAN searches its own index of the Quran and quotes
what it finds from the authentic text; no model chooses or words an ayah.

The index has five views of every ayah, each from the same Tanzil-based
source as the Quran recipe (api.alquran.cloud), downloaded once into
``$MIZAN_DATA_DIR/quran``:

- the Arabic text (Simple Clean) and its Latin transliteration, as letter
  trigrams of each word, so "sidra tu munhtah" still meets "sidratil muntaha"
  and "قرآن" meets "القرآن" with no rule about spellings or articles;
- the Saheeh International, Jalandhry (Urdu) and Hindi translations, as words.

Text is only normalised: lower case without accents, and Arabic-script
letters that are one letter in different code points (Urdu ی and Arabic ي,
the seats of hamza) written one way.

**Weighing a query.** Each word counts in each view in proportion to how often
that view uses it: an English word goes to the translation, a word no
translation has goes to the transliteration. It also counts in proportion to
how much more often the Quran uses it than people's way of asking for things
(MIZAN's own request seeds, ``data/qasd``): in "Quran me Kausar ka zikr" the
words "Quran", "me", "ka" and "zikr" are how the request is phrased, and
"Kausar" is what it is about. Every view scores the ayahs by BM25; the scores
are standardised over all 6236 ayahs (a view counts by how far its best ayahs
stand out, whatever its scale) and summed, each view weighted by the share of
the query's words it reads.

**When no ayah says it.** A word that no view uses, and that reads as English
rather than as a spelling of an Arabic, Urdu or Hindi word (a letter model of
the Saheeh International words against the transliteration's and Roman Hindi
words), is a word no ayah uses: "continents", "smartphones". When such words
carry more of the query's distinctive information than the best ayah holds,
the answer is that no ayah uses them, and the nearest ayah is named only as
what it shares, never quoted as the answer.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import unicodedata
from array import array
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from core.tamyiz import Tamyiz, char_ngrams

from . import quran

EDITIONS = {
    "ar": "quran-simple-clean",
    "tr": "en.transliteration",
    "en": "en.sahih",
    "ur": "ur.jalandhry",
    "hi": "hi.hindi",
}
# Which views read a word, by its script.
SCRIPT_VIEWS = {"latin": ("en", "tr"), "arabic": ("ar", "ur"), "devanagari": ("hi",)}
K1, B = 1.5, 0.75  # BM25's usual constants
_RUNS = re.compile(r"(.)\1+")

_MARKS = re.compile("[ؐ-ًؚ-ٰٟـۖ-ۭ﻿]")
_FOLD = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ی": "ي", "ے": "ي",
        "ئ": "ي", "ة": "ه", "ۃ": "ه", "ہ": "ه", "ھ": "ه", "ؤ": "و", "ک": "ك",
    }
)  # fmt: skip


class Unavailable(RuntimeError):
    pass


def _data_dir() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "quran"


# ── words ────────────────────────────────────────────────────────────────


def _script(word: str) -> str:
    if re.match(r"[؀-ۿ]", word):
        return "arabic"
    if re.match(r"[ऀ-ॿ]", word):
        return "devanagari"
    return "latin"


def words(text: str) -> list[str]:
    """Words in their searchable form: Latin lowercased without accents,
    Arabic-script without marks and with letter variants folded, Devanagari
    without the nukta."""
    text = unicodedata.normalize("NFKC", text)
    found: list[str] = []
    for word in re.findall(r"[؀-ۿ]+|[ऀ-ॿ]+|[^\W\d_]+", text):
        script = _script(word)
        if script == "arabic":
            word = _MARKS.sub("", word).translate(_FOLD)
        elif script == "devanagari":
            word = word.replace("़", "")
        else:
            word = unicodedata.normalize("NFKD", word.lower())
            word = "".join(c for c in word if "a" <= c <= "z")
        if word:
            found.append(word)
    return found


def grams(word: str) -> list[str]:
    """Letter trigrams of a word, with its edges marked."""
    padded = f"^{word}$"
    return [padded[i : i + 3] for i in range(len(padded) - 2)]


def terms(view: str, word: str) -> list[str]:
    if view == "tr":
        # Long vowels and doubled letters are written however the person
        # hears them ("lillahi", "lillaahi"): a letter repeated counts once.
        return grams(_RUNS.sub(r"\1", word))
    return grams(word) if view == "ar" else [word]


# ── index ────────────────────────────────────────────────────────────────


@dataclass
class View:
    """One view of every ayah: postings (term → ayah numbers and counts)."""

    lengths: array = field(default_factory=lambda: array("I"))
    postings: dict[str, tuple[array, array]] = field(default_factory=dict)
    words: Counter = field(default_factory=Counter)  # ayahs that use each word

    def add(self, number: int, text: str, view: str) -> None:
        found = words(text)
        counted: Counter[str] = Counter(t for w in found for t in terms(view, w))
        self.words.update(set(found))
        self.lengths.append(sum(counted.values()))
        for term, count in counted.items():
            docs, counts = self.postings.setdefault(term, (array("I"), array("H")))
            docs.append(number)
            counts.append(min(count, 65535))

    def term_score(self, term: str, doc: int, weight: float) -> float:
        """One term's BM25 share of one ayah's score."""
        if term not in self.postings or weight <= 0:
            return 0.0
        docs, counts = self.postings[term]
        try:
            count = int(counts[docs.index(doc)])
        except ValueError:
            return 0.0
        total = len(self.lengths)
        average = sum(self.lengths) / total or 1.0
        idf = math.log(1 + (total - len(docs) + 0.5) / (len(docs) + 0.5))
        norm = K1 * (1 - B + B * self.lengths[doc] / average)
        return float(weight * idf * count * (K1 + 1) / (count + norm))

    def scores(self, weighted: dict[str, float]) -> dict[int, float]:
        """BM25 of every ayah that has a query term, each term at its weight."""
        total = len(self.lengths)
        average = sum(self.lengths) / total or 1.0
        found: dict[int, float] = {}
        for term, weight in weighted.items():
            if term not in self.postings or weight <= 0:
                continue
            docs, counts = self.postings[term]
            idf = math.log(1 + (total - len(docs) + 0.5) / (len(docs) + 0.5))
            for doc, count in zip(docs, counts, strict=True):
                norm = K1 * (1 - B + B * self.lengths[doc] / average)
                found[doc] = found.get(doc, 0.0) + weight * idf * count * (K1 + 1) / (count + norm)
        return found


@dataclass
class Index:
    keys: list[tuple[int, int]]  # (surah, ayah) of each ayah, in mushaf order
    views: dict[str, View]
    asked: Counter  # request seeds that use each word
    seeds: int
    english: Tamyiz | None = None  # P(English | a word's letters)

    def search(self, query: str, limit: int = 3) -> list[Match]:
        total = len(self.keys)
        weighted: dict[str, dict[str, float]] = {name: {} for name in self.views}
        used: dict[str, set[str]] = {name: set() for name in self.views}
        mass: dict[str, float] = {name: 0.0 for name in self.views}
        for word in dict.fromkeys(words(query)):
            topic = self.topic(word)
            for name, share in self.shares(word).items():
                if share * topic <= 0:
                    continue
                for term in terms(name, word):
                    weighted[name][term] = weighted[name].get(term, 0.0) + share * topic
                used[name].add(word)
                mass[name] += share * topic
        whole = sum(mass.values()) or 1.0
        summed: dict[int, float] = {}
        offset = 0.0
        for name, view in self.views.items():
            scores = view.scores(weighted[name])
            if not scores:
                continue
            # Standardise over all ayahs (an ayah with no term scores 0), and
            # count the view by the share of the query's words it reads.
            mean = sum(scores.values()) / total
            spread = math.sqrt(
                max(sum(s * s for s in scores.values()) / total - mean * mean, 1e-12)
            )
            part = mass[name] / whole
            offset -= part * mean / spread
            for doc, score in scores.items():
                summed[doc] = summed.get(doc, 0.0) + part * score / spread
        ranked = sorted(summed.items(), key=lambda item: -item[1])[:limit]
        return [
            Match(*self.keys[doc], round(score + offset, 2), self._matched(doc, weighted, used))
            for doc, score in ranked
        ]

    def find(self, query: str, limit: int = 3) -> Found:
        """The best ayahs for the query; or, when most (> ½) of the query's
        distinctive information is in words no ayah uses, those words and the
        nearest ayah (named for what it shares, not as the answer)."""
        matches = [match for match in self.search(query, limit) if match.words]
        if not matches:
            return Found([], [])
        weights = self.distinctive(query)
        unused = {word: weights[word] * self.unused(word) for word in weights}
        if 2 * sum(unused.values()) > sum(weights.values()):
            absent = sorted(unused, key=lambda word: -unused[word])
            named = [word for word in absent if self.unused(word) > 0.5] or absent[:1]
            return Found([], named, matches[0])
        return Found(matches, [])

    def distinctive(self, query: str) -> dict[str, float]:
        """The query's distinctive words and the information each carries: how
        much it is what the request is about (``topic``) times how rare it is in
        the views that read it (a word no view uses is as rare as a word can
        be). Distinctive are the words above the query's mean, as Ahl al-Dhikr
        reads a claim, so "the", "ka" and "ayah" never decide."""
        total = len(self.keys)
        found: dict[str, float] = {}
        for word in dict.fromkeys(words(query)):
            shares = self.shares(word)
            if not shares:
                continue
            rarity = sum(
                share * _idf(total, self.views[name].words[word]) for name, share in shares.items()
            )
            found[word] = self.topic(word) * rarity
        if not found:
            return {}
        mean = sum(found.values()) / len(found)
        return {word: info for word, info in found.items() if info > mean} or found

    def unused(self, word: str) -> float:
        """P(no ayah uses the word): 0 for a word some view uses; for a Latin
        word no view uses, the probability that it is English (Saheeh
        International would use it) rather than the person's spelling of an
        Arabic, Urdu or Hindi word ("munhtah", "aasani"), which the views read
        only by its letters. Arabic-script and Devanagari words are never
        called unused: their spellings vary by the letters joined to them."""
        if _script(word) != "latin" or self.english is None:
            return 0.0
        if any(
            self.views[name].words[word] for name in SCRIPT_VIEWS["latin"] if name in self.views
        ):
            return 0.0
        return float(self.english.posterior(word).get("en", 0.0))

    def _matched(
        self, doc: int, weighted: dict[str, dict[str, float]], used: dict[str, set[str]]
    ) -> list[str]:
        """The query words that carry this ayah's score, most first: those
        whose share of it is at least the average word's."""
        found: dict[str, float] = {}
        for name, view in self.views.items():
            for word in used[name]:
                part = sum(
                    view.term_score(term, doc, weighted[name].get(term, 0.0))
                    for term in set(terms(name, word))
                )
                if part > 0:
                    found[word] = found.get(word, 0.0) + part
        if not found:
            return []
        mean = sum(found.values()) / len(found)
        return [word for word, part in sorted(found.items(), key=lambda i: -i[1]) if part >= mean]

    def shares(self, word: str) -> dict[str, float]:
        """How much each view of the word's script reads it: in proportion to
        the share of its ayahs that use the word. A word no view uses goes to
        the view that matches spellings by trigram (Arabic or transliteration)."""
        names = SCRIPT_VIEWS[_script(word)]
        total = len(self.keys)
        rates = {name: self.views[name].words[word] / total for name in names if name in self.views}
        mass = sum(rates.values())
        if mass > 0:
            return {name: rate / mass for name, rate in rates.items()}
        fuzzy = [name for name in rates if name in ("ar", "tr")]
        return {name: 1.0 / len(fuzzy) for name in fuzzy}

    def topic(self, word: str) -> float:
        """P(the word is what the request is about | the word): the share of
        ayahs that use it against the share of request seeds that do, each
        seed left out once (a word only one seed uses is that seed's topic, not
        a way of asking). A word no two seeds share is the topic."""
        asked = max(self.asked[word] - 1, 0) / self.seeds if self.seeds else 0.0
        if asked == 0:
            return 1.0
        names = SCRIPT_VIEWS[_script(word)]
        used = max((self.views[n].words[word] for n in names if n in self.views), default=0)
        rate = used / len(self.keys)
        return rate / (rate + asked)


def _idf(total: int, used: int) -> float:
    return math.log(1 + (total - used + 0.5) / (used + 0.5))


@dataclass(frozen=True)
class Match:
    surah: int
    ayah: int
    score: float
    words: list[str]

    @property
    def label(self) -> str:
        return f"{self.surah}:{self.ayah}"


@dataclass(frozen=True)
class Found:
    matches: list[Match]
    absent: list[str]  # words no ayah uses, when they outweigh the best match
    nearest: Match | None = None


# ── loading ──────────────────────────────────────────────────────────────


def _request_words() -> tuple[Counter, int]:
    """How many request seeds use each word, all intents together."""
    from . import qasd

    seeds = [text for _label, text in qasd._rows("intents.tsv")]
    return Counter(w for text in seeds for w in set(words(text))), len(seeds)


def build(editions: dict[str, list[tuple[int, int, str]]]) -> Index:
    keys = [(surah, ayah) for surah, ayah, _text in editions["ar"]]
    views: dict[str, View] = {}
    for name, rows in editions.items():
        if [(s, a) for s, a, _t in rows] != keys:
            raise Unavailable(f"The {name} edition does not match the Arabic text ayah for ayah")
        view = View()
        for number, (_s, _a, text) in enumerate(rows):
            view.add(number, text, name)
        views[name] = view
    asked, seeds = _request_words()
    return Index(keys, views, asked, seeds, _english(views))


def _letters(word: str) -> Counter[str]:
    return Counter(char_ngrams(f"^{word}$", (2, 3, 4)))


def _english(views: dict[str, View]) -> Tamyiz | None:
    """A letter model of English words (Saheeh International's and Lughah's
    English) against Latin spellings of other languages (the transliteration's
    and Lughah's Roman Hindi), words in both left out; fitted by leave-one-out
    and cached by the corpus's SHA-256."""
    if "en" not in views or "tr" not in views:
        return None
    from core.tamyiz_cache import fitted

    from . import lughah

    def corpus(label: str) -> set[str]:
        path = lughah.CORPUS / f"{label}.tsv"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        return {word for line in lines for word in words(line.partition("\t")[2])}

    english = set(views["en"].words) | corpus("en")
    spelled = set(views["tr"].words) | corpus("hi-latn")
    rows = [(word, "en") for word in sorted(english - spelled)]
    rows += [(word, "latn") for word in sorted(spelled - english)]
    return fitted("fihris_english", _letters, lambda: rows)


def _rows(data: dict) -> list[tuple[int, int, str]]:
    return [
        (surah["number"], ayah["numberInSurah"], ayah["text"])
        for surah in data["surahs"]
        for ayah in surah["ayahs"]
    ]


async def _edition(client: httpx.AsyncClient, name: str) -> list[tuple[int, int, str]]:
    path = _data_dir() / f"{name}.json"
    if path.exists():
        rows = [tuple(row) for row in json.loads(path.read_text(encoding="utf-8"))]
        if len(rows) == quran.TOTAL_AYAHS:
            return rows  # type: ignore[return-value]
    try:
        response = await client.get(f"{quran.API}/quran/{name}")
        response.raise_for_status()
        rows = _rows(response.json()["data"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        raise Unavailable("The Quran text source is not reachable right now") from None
    if len(rows) != quran.TOTAL_AYAHS:
        raise Unavailable(f"The {name} edition is incomplete")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return rows


_lock = asyncio.Lock()
_index: Index | None = None


async def index() -> Index:
    """The index, downloaded once and built off the event loop."""
    global _index
    async with _lock:
        if _index is None:
            async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
                editions = {view: await _edition(client, name) for view, name in EDITIONS.items()}
            _index = await asyncio.to_thread(build, editions)
        return _index


async def search(query: str, limit: int = 3) -> list[Match]:
    """The ayahs that best answer to the query's words, best first; [] when
    no ayah shares a word with it."""
    found = (await index()).search(query, limit)
    return [match for match in found if match.words]


async def find(query: str, limit: int = 3) -> Found:
    """``search``, or the words no ayah uses when they outweigh the best match."""
    return (await index()).find(query, limit)
