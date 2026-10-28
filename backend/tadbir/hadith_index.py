"""Which collection holds a hadith's words: MIZAN's own index of the six books.

An answer in the model's words can cite a hadith to the wrong book: on 27
October "The martyr has six distinctions with Allah" was given as Bukhari and
Muslim; it is Tirmidhi 1663 and Ibn Majah 2799. A quote is checked against the
English text of the six books (the open hadith-api dataset MIZAN already
quotes from, ``tadbir/hadith.py``), downloaded once into
``$MIZAN_DATA_DIR/hadith`` and indexed here with BM25.

A narration is taken to hold the quote when it holds more than half of the
quote's distinctive information (``ahl_dhikr.about``): the words that carry
more information than its average word, so a paraphrase ("six distinctions"
for "six things") still finds its source and a quote sharing only "Allah" and
"said" finds none. The answer is never rewritten: Sidq reports where the words
are found when the cited book is not among them.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx

from core.adaptive import tokenize

from .hadith import API, BY_KEY, COLLECTIONS, HadithRef, link

BOOKS = ("bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah")
# Words every narration carries ("narrated", "messenger"): weighed by the index
# itself, through their document frequency, never listed here.
_K1, _B = 1.5, 0.75
_QUOTED = re.compile(r"[\"“”«»‘’']([^\"“”«»]{20,600})[\"“”«»’']")


def _data_dir() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "hadith"


@dataclass(frozen=True)
class Holder:
    book: str
    number: int
    text: str
    score: float

    @property
    def label(self) -> str:
        return HadithRef(self.book, self.number).label

    @property
    def url(self) -> str:
        return link(HadithRef(self.book, self.number))


class Index:
    def __init__(self, docs: list[tuple[str, int, str]]):
        self.docs = docs
        self.terms = [Counter(tokenize(text)) for _book, _number, text in docs]
        self.lengths = [sum(terms.values()) for terms in self.terms]
        self.average = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        self.postings: dict[str, list[int]] = {}
        for position, terms in enumerate(self.terms):
            for term in terms:
                self.postings.setdefault(term, []).append(position)

    def _idf(self, term: str) -> float:
        seen = len(self.postings.get(term, ()))
        return math.log(1 + (len(self.docs) - seen + 0.5) / (seen + 0.5))

    def ranked(self, quote: str, books: tuple[str, ...] = BOOKS, limit: int = 5) -> list[Holder]:
        """The narrations of these books whose words best match the quote (BM25)."""
        query = set(tokenize(quote))
        scores: dict[int, float] = {}
        for term in query:
            idf = self._idf(term)
            for position in self.postings.get(term, ()):
                if self.docs[position][0] not in books:
                    continue
                tf = self.terms[position][term]
                norm = tf + _K1 * (1 - _B + _B * self.lengths[position] / self.average)
                scores[position] = scores.get(position, 0.0) + idf * tf * (_K1 + 1) / norm
        best = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [Holder(*self.docs[position], round(score, 3)) for position, score in best]

    def holders(self, quote: str, limit: int = 4) -> list[Holder]:
        """The narrations that hold the quote's words, best first."""
        from .ahl_dhikr import about

        return [
            holder for holder in self.ranked(quote, limit=limit * 5) if about(quote, holder.text)
        ][:limit]


def build(editions: dict[str, list[dict]]) -> Index:
    docs = [
        (book, int(item["hadithnumber"]), str(item.get("text", "")))
        for book, items in editions.items()
        for item in items
        if str(item.get("text", "")).strip() and isinstance(item.get("hadithnumber"), int | float)
    ]
    return Index(docs)


async def _edition(client: httpx.AsyncClient, book: str) -> list[dict]:
    path = _data_dir() / f"eng-{book}.json"
    if path.exists():
        return list(json.loads(path.read_text(encoding="utf-8")))
    response = await client.get(f"{API}/editions/eng-{book}.min.json")
    response.raise_for_status()
    items = [
        {"hadithnumber": item.get("hadithnumber"), "text": item.get("text", "")}
        for item in response.json().get("hadiths", [])
        if isinstance(item, dict)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return items


_lock = asyncio.Lock()
_index: Index | None = None


async def index() -> Index:
    """The index, downloaded once and built off the event loop."""
    global _index
    async with _lock:
        if _index is None:
            async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
                editions = {book: await _edition(client, book) for book in BOOKS}
            _index = await asyncio.to_thread(build, editions)
        return _index


# ── what an answer cites ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Citation:
    quote: str
    books: tuple[str, ...]


def citations(text: str) -> list[Citation]:
    """Quoted words an answer gives as a hadith of named books, in order."""
    found: list[Citation] = []
    for line in (text or "").splitlines():
        books = tuple(
            item.key
            for item in COLLECTIONS
            if item.key in BOOKS and re.search(item.strong, line, re.IGNORECASE)
        )
        if not books:
            continue
        for match in _QUOTED.finditer(line):
            quote = match.group(1).strip()
            if len(tokenize(quote)) >= 5:
                found.append(Citation(quote, books))
    return found[:6]


def _focus(narration: str, quote: str) -> str:
    """The sentence of a narration that best answers to the quote, with the
    ones on either side (the model reading the pair sees the words, not the
    isnad)."""
    from core.adaptive import bm25_scores

    parts = [part.strip() for part in re.split(r"(?<=[.!?:])\s+", narration) if part.strip()]
    if len(parts) <= 3:
        return narration[:1200]
    scores = bm25_scores(quote, parts)
    best = max(range(len(parts)), key=lambda index: scores[index])
    return " ".join(parts[max(0, best - 1) : best + 2])[:1200]


async def _entailed(quote: str, holders: list[Holder]) -> list[Holder]:
    """The narrations that say what the quote says (the NLI model's MAP label
    is entailment). None when the model cannot run: nothing is claimed."""
    from .ahl_dhikr import nli

    readings = await nli([(_focus(holder.text, quote), quote) for holder in holders])
    if readings is None:
        return []
    return [
        holder
        for holder, reading in zip(holders, readings, strict=True)
        if max(reading, key=reading.__getitem__) == "entailment"
    ]


async def check(text: str) -> list[dict]:
    """Each quoted hadith whose cited books hold nothing that says it, while
    another of the six books does: where it is, from MIZAN's index.

    Translations of one hadith differ from book to book, so the words alone
    never settle that a book lacks it: the cited books' closest narrations are
    read against the quote by the NLI model, and only when none of them says
    it and a narration of another book does is it reported."""
    cited = citations(text)
    if not cited or os.getenv("MIZAN_HADITH_INDEX", "on").strip().lower() == "off":
        return []
    try:
        held = await index()
    except (httpx.HTTPError, OSError, ValueError):
        return []  # no index: nothing is claimed either way
    findings: list[dict] = []
    for citation in cited:
        others = [h for h in await asyncio.to_thread(held.holders, citation.quote, 6)]
        others = [holder for holder in others if holder.book not in citation.books]
        if not others:
            continue
        own = await asyncio.to_thread(held.ranked, citation.quote, citation.books, 5)
        if await _entailed(citation.quote, own):
            continue  # a cited book says it, in its own translation's words
        found = await _entailed(citation.quote, others[:3])
        if not found:
            continue
        findings.append(
            {
                "quote": citation.quote[:200],
                "cited": [BY_KEY[book].name for book in citation.books],
                "found": [{"reference": holder.label, "url": holder.url} for holder in found],
            }
        )
    return findings
