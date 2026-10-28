"""Iqtibas (اقتباس): a message that quotes the Quran's own words.

"Light upon light" and "سدرة المنتهى" carry no request word: what makes them a
request for an ayah is that they are the Quran's words, which Qasd's letters
cannot see. MIZAN looks for the longest span of the message that its Quran
texts hold word for word (Arabic, transliteration, Saheeh, Jalandhry, Hindi,
the editions Fihris downloads), and asks how surprising that span would be in
ordinary speech: -log P under a Witten-Bell bigram model of the ordinary
language that ships with MIZAN (the Lughah corpora and Qasd's conversation
seeds, where everyday dhikr and salam live). "peace be upon you" is in the
Quran (6:54) and in everyday speech, so it is cheap; "light upon light" is
not said in passing.

The surprise S enters as a Bayes factor exp(b·S) on the Quran family of
intents. b is the only parameter, fitted like Tamyiz's own weights: the value
that minimises the leave-one-out log-loss of Qasd's posteriors over the seeds
(``fit``, stored in core/data/iqtibas.json). With no span, or before the
texts are on disk, the factor is 1 and nothing changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import threading
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from . import fihris, quran

PACKAGED = Path(__file__).resolve().parents[1] / "core" / "data" / "iqtibas.json"
CALIBRATION = Path(__file__).resolve().parent / "data" / "iqtibas" / "calibration.tsv"
MAX_WORDS = 64  # a quote is looked for in the first words of a long message
# Arabic-script punctuation and digits read as letters by ``fihris.words``.
_PUNCT = re.compile("[،؛؟۔٪٫٬٠-٩۰-۹]")
_START = "\x02"  # sentence start, for the bigram model


def enabled() -> bool:
    return os.getenv("MIZAN_IQTIBAS", "on").strip().lower() != "off"


def tokens(text: str) -> list[str]:
    """Words as Fihris reads them, without Arabic-script punctuation."""
    return [w for w in (_PUNCT.sub("", word) for word in fihris.words(text)) if w]


def _letters(found: Sequence[str]) -> str:
    """Transliteration letters: a letter repeated counts once, across words too
    ("hasbunal laahu" and "hasbunallahu" are the same letters)."""
    return fihris._RUNS.sub(r"\1", "".join(found))


# ── the Quran's texts ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Span:
    words: tuple[str, ...]  # the message's own words that are quoted
    view: str  # the edition that holds them
    ayah: tuple[int, int]
    surprise: float  # -log P(words) in ordinary speech, in nats
    evidence: float  # log P(words | quoting the Quran) - log P(words | ordinary speech)
    share: float  # the part of the message's words the span is

    @property
    def weight(self) -> float:
        """The evidence the message carries: a message that is the quote is
        more surely a quote than one that only holds a fragment of it ("May
        Allah have mercy on him" holds "have mercy")."""
        return self.evidence * self.share


@dataclass(frozen=True)
class Quotes:
    texts: dict[str, str]  # view -> every ayah, one per line
    starts: dict[str, list[int]]  # view -> offset of each ayah's line
    keys: list[tuple[int, int]]
    positions: dict[str, int]  # view -> words (letters for transliteration) it holds
    vocabulary: dict[str, frozenset[str]]  # word views -> the words they use

    def _needle(self, view: str, found: Sequence[str]) -> str:
        return _letters(found) if view == "tr" else " " + " ".join(found) + " "

    def holds(self, view: str, found: Sequence[str]) -> int:
        """The offset where the view holds these words in order, or -1."""
        return self.texts[view].find(self._needle(view, found))

    def chance(self, view: str, found: Sequence[str]) -> float:
        """log P(these words | a span drawn from the view at random): the times
        the view holds them over the places a span could start."""
        held = self.texts[view].count(self._needle(view, found))
        return math.log(max(held, 1)) - math.log(self.positions[view])

    def ayah(self, view: str, offset: int) -> tuple[int, int]:
        starts = self.starts[view]
        low, high = 0, len(starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return self.keys[low]


def build(editions: dict[str, Sequence[Sequence]]) -> Quotes:
    """The texts of each edition (rows of surah, ayah, text), in one string per
    view: words between spaces, or transliteration letters, one ayah per line."""
    texts: dict[str, str] = {}
    starts: dict[str, list[int]] = {}
    positions: dict[str, int] = {}
    vocabulary: dict[str, frozenset[str]] = {}
    keys: list[tuple[int, int]] = []
    for view in fihris.EDITIONS:
        rows = sorted(editions[view], key=lambda row: (int(row[0]), int(row[1])))
        if not keys:
            keys = [(int(row[0]), int(row[1])) for row in rows]
        lines, offsets, at, held, used = [], [], 0, 0, set()
        for row in rows:
            found = tokens(str(row[2]))
            used.update(found)
            line = (_letters(found) if view == "tr" else " " + " ".join(found) + " ") + "\n"
            held += len(line) - 1 if view == "tr" else len(found)
            offsets.append(at)
            lines.append(line)
            at += len(line)
        texts[view] = "".join(lines)
        starts[view] = offsets
        positions[view] = max(held, 1)
        if view != "tr":
            vocabulary[view] = frozenset(used)
    return Quotes(texts, starts, keys, positions, vocabulary)


_lock = threading.Lock()
_quotes: Quotes | None = None
_loading = False


def ready() -> Quotes | None:
    return _quotes


def _files() -> dict[str, Path]:
    return {view: fihris._data_dir() / f"{name}.json" for view, name in fihris.EDITIONS.items()}


def load() -> Quotes | None:
    """The texts from the editions Fihris keeps on disk, or None when one is missing."""
    global _quotes, _loading
    with _lock:
        if _quotes is None:
            editions = {}
            for view, path in _files().items():
                try:
                    rows = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    _loading = False
                    return None
                if len(rows) != quran.TOTAL_AYAHS:
                    _loading = False
                    return None
                editions[view] = rows
            _quotes = build(editions)
        _loading = False
        return _quotes


def _load_soon() -> None:
    """Read the texts in the background; the message in hand is read without them."""
    global _loading
    with _lock:
        if _loading or _quotes is not None:
            return
        _loading = True
    threading.Thread(target=load, name="iqtibas-load", daemon=True).start()


async def warm() -> None:
    """Fetch the editions once (as Fihris does) and read them; best effort."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            for name in fihris.EDITIONS.values():
                await fihris._edition(client, name)
    except (fihris.Unavailable, OSError):
        return
    if await asyncio.to_thread(load) is not None:
        await asyncio.to_thread(background)  # the first message is not kept waiting


# ── ordinary speech ──────────────────────────────────────────────────────


class Background:
    """Witten-Bell interpolated word bigrams over ordinary sentences, backed off
    to a letter model for words never seen, so -log P of any span is finite."""

    def __init__(self, sentences: Iterable[Sequence[str]]):
        self.unigrams: Counter[str] = Counter()
        self.bigrams: Counter[tuple[str, str]] = Counter()
        self.followers: Counter[str] = Counter()  # distinct words after each word
        self.contexts: Counter[str] = Counter()  # times each word is followed
        self.total = 0  # words counted
        letters: Counter[str] = Counter()
        for sentence in sentences:
            self.add(sentence, 1)
            for word in sentence:
                letters.update(word)
                letters["$"] += 1
        self.types = len(self.unigrams)
        total = sum(letters.values()) + len(letters) + 1
        self.letter = {c: (n + 1) / total for c, n in letters.items()}
        self.unseen_letter = 1 / total

    def add(self, sentence: Sequence[str], sign: int) -> None:
        """Count a sentence in (sign 1) or out (sign -1): a seed's own words are
        taken out while it is read, as Tamyiz holds a seed out of its own fit."""
        previous = _START
        for word in sentence:
            if sign > 0 and self.bigrams[previous, word] == 0:
                self.followers[previous] += 1
            self.bigrams[previous, word] += sign
            if sign < 0 and self.bigrams[previous, word] == 0:
                self.followers[previous] -= 1
            self.contexts[previous] += sign
            self.unigrams[word] += sign
            self.total += sign
            previous = word

    def _spelling(self, word: str) -> float:
        p = self.letter.get("$", self.unseen_letter)
        for c in word:
            p *= self.letter.get(c, self.unseen_letter)
        return p

    def _unigram(self, word: str) -> float:
        return (self.unigrams[word] + self.types * self._spelling(word)) / (self.total + self.types)

    def surprise(self, found: Sequence[str]) -> float:
        """-log P(words) in nats; the first word is read without its context."""
        nats = -math.log(self._unigram(found[0]))
        for previous, word in zip(found, found[1:], strict=False):
            seen = self.contexts[previous]
            kinds = self.followers[previous]
            unigram = self._unigram(word)
            p = (
                (self.bigrams[previous, word] + kinds * unigram) / (seen + kinds)
                if seen + kinds
                else unigram
            )
            nats -= math.log(p)
        return nats


def _ordinary() -> list[tuple[str, list[str]]]:
    """Ordinary speech that ships with MIZAN: the Lughah corpora (not the
    Uthmani quotes or names) and Qasd's conversation seeds."""
    from . import lughah, qasd

    texts = [text for text, label in lughah.corpus() if label not in {"quote", "name"}]
    texts += [text for label, text in qasd._rows("intents.tsv") if label == "converse"]
    return [(text, tokens(text)) for text in texts]


@cache
def background() -> Background:
    return Background(found for _text, found in _ordinary())


# ── the evidence ─────────────────────────────────────────────────────────


def _spans(quotes: Quotes, found: Sequence[str], views: Iterable[str]) -> list[tuple]:
    """The longest quoted span from each word, per view: (start, end, view, offset)."""
    spans = []
    for view in views:
        known = quotes.vocabulary.get(view)
        for start in range(len(found)):
            end, offset = start, -1
            while end < len(found):
                if known is not None and found[end] not in known:
                    break  # a word the view never uses ends every span through it
                at = quotes.holds(view, found[start : end + 1])
                if at < 0:
                    break
                end, offset = end + 1, at
            if end > start:
                spans.append((start, end, view, offset))
    return spans


def quoted(
    message: str, quotes: Quotes | None = None, model: Background | None = None
) -> Span | None:
    """The span of the message that the Quran's texts hold word for word and that
    is most likely a quote: log P(span | drawn from the Quran) - log P(span |
    ordinary speech), the evidence a likelihood ratio gives, times the share of
    the message it is. None without one."""
    quotes = quotes or _quotes
    if quotes is None:
        return None
    found = tokens(message)[:MAX_WORDS]
    if not found:
        return None
    scripts = {fihris._script(word) for word in found}
    views = [
        view
        for script in sorted(scripts)
        for view in fihris.SCRIPT_VIEWS.get(script, ())
        if view in quotes.texts
    ]
    model = model or background()
    candidates = []
    for start, end, view, offset in _spans(quotes, found, views):
        words = tuple(found[start:end])
        candidates.append((model.surprise(words), words, view, offset))
    # log(times held / places) is never above 0, so surprise x share bounds the
    # weight: the costlier count is taken only while it could still win.
    candidates.sort(key=lambda item: -item[0] * len(item[1]))
    best: Span | None = None
    for surprise, words, view, offset in candidates:
        share = len(words) / len(found)
        if best is not None and surprise * share <= best.weight:
            break
        evidence = surprise + quotes.chance(view, words)
        span = Span(words, view, quotes.ayah(view, offset), surprise, evidence, share)
        if best is None or span.weight > best.weight:
            best = span
    return best


@lru_cache(maxsize=512)
def _span(message: str) -> Span | None:
    return quoted(message)


@cache
def fitted() -> dict:
    try:
        saved: dict = json.loads(PACKAGED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved


def weigh(ranked: list[tuple[str, float]], message: str) -> tuple[list[tuple[str, float]], dict]:
    """Qasd's posterior with the quote's Bayes factor on the Quran family, and
    what was found (empty when nothing changed)."""
    from .fahm import FAMILIES

    rate = float(fitted().get("b") or 0.0)
    if not enabled() or rate <= 0 or not ranked:
        return ranked, {}
    if _quotes is None:
        _load_soon()
        return ranked, {}
    span = _span(message)
    if span is None:
        return ranked, {}
    factor = math.exp(max(min(rate * span.weight, 700.0), -700.0))
    family = set(FAMILIES["quran"])
    weighed = [(intent, p * factor if intent in family else p) for intent, p in ranked]
    total = sum(p for _intent, p in weighed) or 1.0
    weighed = sorted(((intent, p / total) for intent, p in weighed), key=lambda item: -item[1])
    found = {
        "words": " ".join(span.words),
        "view": span.view,
        "ayah": f"{span.ayah[0]}:{span.ayah[1]}",
        "surprise": round(span.surprise, 2),
        "evidence": round(span.evidence, 2),
        "share": round(span.share, 3),
        "factor": round(factor, 3),
    }
    return weighed, found


# ── fitting b ────────────────────────────────────────────────────────────


def _digest(paths: Iterable[Path]) -> str:
    sha = hashlib.sha256()
    for path in paths:
        sha.update(path.read_bytes())
    return sha.hexdigest()


def calibration() -> list[tuple[str, str]]:
    """(text, label): bare quotes sent as requests, and Quranic formulas said in
    conversation. The seeds hold almost no bare quote (seeds of them taught
    Qasd's letters to read any short odd message as a Quran search), so b is
    fitted on these too; Qasd never trains on them."""
    rows = []
    for line in CALIBRATION.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            label, _, text = line.partition("\t")
            rows.append((text, label))
    return rows


def fit(quotes: Quotes) -> dict:
    """b that minimises the log-loss of Qasd's posteriors once the quote's factor
    is applied (the method Tamyiz fits its own weights by): leave-one-out over
    the seeds, out of sample over the calibration rows."""
    from core.tamyiz import _combine, _golden, _loo_parts
    from core.tamyiz_cache import digest

    from . import qasd
    from .fahm import FAMILIES

    model = qasd.model()
    rows = qasd.examples()
    family = set(FAMILIES["quran"])
    ordinary = background()
    seen = {text: found for text, found in _ordinary()}
    # S of each seed's own words, with the seed taken out of the background first.
    surprise: dict[str, float] = {}
    for row in rows:
        text = row[0].removeprefix(qasd.PROJECT)
        if text in surprise:
            continue
        own = seen.get(text)
        if own is not None:
            ordinary.add(own, -1)
        span = quoted(text, quotes, ordinary)
        if own is not None:
            ordinary.add(own, 1)
        surprise[text] = span.weight if span else 0.0
    held = [(row[1], model.vector(row[0]), row[2] if len(row) > 2 else None) for row in rows]
    groups: dict = {}
    for _label, vector, group in held:
        if group is not None:
            summed, size = groups.get(group, ({}, 0.0))
            for index, count in vector.items():
                summed[index] = summed.get(index, 0.0) + count
            groups[group] = (summed, size + 1)
    held_out = [
        (label, vector, *(groups[group] if group is not None else (vector, 1.0)))
        for label, vector, group in held
    ]
    scores = [
        (truth, _combine(parts, model.weights, model.gamma))
        for truth, parts in _loo_parts(model, held_out, model.alpha)
    ]
    shifts = [surprise[row[0].removeprefix(qasd.PROJECT)] for row in rows]
    seeds = len(scores)
    for text, label in calibration():
        span = quoted(text, quotes, ordinary)
        scores.append(
            (label, _combine(model.parts(model.vector(text)), model.weights, model.gamma))
        )
        shifts.append(span.weight if span else 0.0)

    def outcome(rate: float) -> tuple[float, list[bool]]:
        loss, right = 0.0, []
        for (truth, score), s in zip(scores, shifts, strict=True):
            shifted = {
                label: value + (rate * s if label in family else 0.0)
                for label, value in score.items()
            }
            top = max(shifted.values())
            normaliser = top + math.log(sum(math.exp(v - top) for v in shifted.values()))
            loss -= shifted[truth] - normaliser
            right.append(max(shifted, key=shifted.__getitem__) == truth)
        return loss / len(scores), right

    rate = _golden(lambda value: outcome(value)[0], 0.0, 2.0)
    before, right_before = outcome(0.0)
    after, right_after = outcome(rate)
    if after >= before:
        rate, after, right_after = 0.0, before, right_before
    positive = [s for (truth, _), s in zip(scores, shifts, strict=True) if truth in family]
    negative = [s for (truth, _), s in zip(scores, shifts, strict=True) if truth not in family]
    from .talim import p_worse

    def share(right: list[bool]) -> float:
        return round(sum(right) / max(1, len(right)), 6)

    return {
        "b": rate,
        "seeds_sha256": digest(rows),
        "editions_sha256": _digest(_files().values())
        if all(path.exists() for path in _files().values())
        else "",
        "loo_loss_before": round(before, 6),
        "loo_loss_after": round(after, 6),
        "seed_accuracy_before": share(right_before[:seeds]),
        "seed_accuracy_after": share(right_after[:seeds]),
        "calibration_accuracy_before": share(right_before[seeds:]),
        "calibration_accuracy_after": share(right_after[seeds:]),
        "p_worse": p_worse(right_before[:seeds], right_after[:seeds]),
        "auc": round(_auc(positive, negative), 4),
        "seeds_with_a_span": sum(1 for s in shifts[:seeds] if s > 0),
        "seeds": seeds,
        "calibration_sha256": hashlib.sha256(CALIBRATION.read_bytes()).hexdigest(),
        "calibration": len(scores) - seeds,
    }


def _auc(positive: Sequence[float], negative: Sequence[float]) -> float:
    """P(a Quran seed's S > another seed's S), ties counted half."""
    ranked = sorted([(s, 1) for s in positive] + [(s, 0) for s in negative])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        mean_rank = (i + j + 1) / 2
        rank_sum += mean_rank * sum(1 for k in range(i, j) if ranked[k][1])
        i = j
    n1, n0 = len(positive), len(negative)
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else 0.5


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fit Iqtibas's Bayes factor on the seeds")
    parser.add_argument("--fit", action="store_true", help="refit b and store it with the code")
    args = parser.parse_args()
    os.environ["MIZAN_TALIM"] = "off"  # the shipped fit is of the shipped seeds only
    asyncio.run(warm())
    quotes = load()
    if quotes is None:
        raise SystemExit("The Quran editions are not on disk and could not be fetched")
    report = fit(quotes)
    print(json.dumps(report, indent=1))
    if args.fit:
        PACKAGED.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
