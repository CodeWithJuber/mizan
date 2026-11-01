"""Lughah (لغة): which language the user wrote in, as a posterior.

A naive Bayes model (``core.tamyiz``) over character n-grams, trained on a
corpus per class (``data/lughah``, sources and licences in its LICENSES.md):

- the asker's possible languages: English, Roman Hindi/Urdu (``hi-latn``),
  Arabic, Urdu and Hindi;
- two neutral classes that say nothing about the asker's language: ``quote``
  (the vowelled Uthmani text of the Quran) and ``name`` (surah, collection,
  prayer and other names written in Latin letters, taken from MIZAN's own
  indexes).

No word list or letter set is written by hand: the model learns which
letters, vowel marks and letter sequences tell these apart.

A message is read in two steps:

1. Each word is classified on its own (word-level identification, as is
   standard for code-mixed text). A word whose most probable class is
   ``name`` or ``quote`` is material, not the asker's language, and is set
   aside.
2. The remaining words, joined in runs of one script, are classified as
   wholes (a run of Hinglish keeps its English words), and
   ``score(L) = log prior(L) + Σ_runs log P(L | run)``.

The prior is a Dirichlet over the languages: one pseudo-count each, plus the
user's earlier messages in this chat, plus one shared by the languages the
material is written in. Quoted Quran is Arabic; a name is in no language. So
"Bukhari 1" is answered in the language of the chat, a bare ayah in Arabic,
"Ayatul Kursi sunao" in Hinglish, and a first message of names alone in the
first language listed, English (the app's default), where the languages tie.

MIZAN's own small language model, the Ruh reader (``tadbir.ruh_reader``),
reads the same words as a second opinion: P(language | words) from
log P(words | language), multiplied in with a fitted weight ``b`` (a product
of experts). It changes the posterior only under ``MIZAN_RUH_READER=on`` and
only once it beat this model on held-out seeds; by default (``shadow``) it is
computed and logged beside the decision, which stays this model's.
"""

from __future__ import annotations

import math
import threading
from functools import cache, lru_cache
from pathlib import Path

from core.tamyiz import Tamyiz, char_ngrams, letters

LANGUAGES = ("en", "hi-latn", "ar", "ur", "hi")
# The neutral classes, with the language each is written in.
NEUTRAL: dict[str, str | None] = {"name": None, "quote": "ar"}
LABELS = LANGUAGES + tuple(NEUTRAL)
CORPUS = Path(__file__).parent / "data" / "lughah"
MAX_WORDS = 400  # a long paste is judged by its first words
_LOCK = threading.Lock()
# Unicode blocks, used only to cut a message where its script changes.
_ARABIC = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
_DEVANAGARI = ((0x0900, 0x097F), (0xA8E0, 0xA8FF))


def _script(char: str) -> str:
    point = ord(char)
    if any(low <= point <= high for low, high in _ARABIC):
        return "arabic"
    if any(low <= point <= high for low, high in _DEVANAGARI):
        return "devanagari"
    return "other"


def _features(text: str):
    return char_ngrams(letters(text))


def shipped() -> list[tuple[str, str]]:
    """The seeds that ship with MIZAN: the same on every server."""
    examples = []
    for label in LABELS:
        for line in (CORPUS / f"{label}.tsv").read_text(encoding="utf-8").splitlines():
            _source, _, text = line.partition("\t")
            if text.strip():
                examples.append((text, label))
    return examples


def corpus() -> list[tuple[str, str]]:
    """The seeds that ship with MIZAN, then what an administrator taught (Ta'lim),
    including languages it adds."""
    from . import talim

    return shipped() + [(text, label) for text, label, _ in talim.rows("lughah")]


def languages() -> tuple[str, ...]:
    """Every language Lughah reads: the shipped ones and any taught since."""
    return tuple(label for label in model().labels if label not in NEUTRAL)


@cache
def model() -> Tamyiz:
    with _LOCK:
        from core.tamyiz_cache import fitted

        return fitted("lughah", _features, corpus)


@lru_cache(maxsize=50_000)
def _word(word: str) -> tuple[tuple[str, float], ...]:
    return tuple(model().posterior(word).items())


def _own_runs(text: str, using: Tamyiz | None = None) -> tuple[list[str], dict[str, float]]:
    """The user's own words, in runs of one script, with neutral material set aside.

    Each word whose most probable class is ``name`` or ``quote`` is material,
    not the asker's language; the rest are joined back into runs, because a
    run of words (code-mixed Hinglish included) is read better as a whole.
    Also counts the material's words by the language they are written in.
    ``using`` reads with another fit of the model (a held-out evaluation)."""
    runs: list[str] = []
    current: list[str] = []
    kind = None
    known = languages() if using is None else _languages_of(using)
    material = dict.fromkeys(known, 0.0)
    for word in letters(text).split()[:MAX_WORDS]:
        found = dict(_word(word)) if using is None else using.posterior(word)
        label = max(found, key=found.__getitem__)
        if label in NEUTRAL:
            written_in = NEUTRAL[label]
            if written_in is not None:
                material[written_in] += 1.0
            if current:
                runs.append(" ".join(current))
                current, kind = [], None
            continue
        script = _script(word[0])
        if kind is not None and script != kind:
            runs.append(" ".join(current))
            current = []
        current.append(word)
        kind = script
    if current:
        runs.append(" ".join(current))
    return runs, material


def _languages_of(using: Tamyiz) -> tuple[str, ...]:
    return tuple(label for label in using.labels if label not in NEUTRAL)


def posterior(text: str, prior: list[str] | None = None) -> dict[str, float]:
    """P(language | message), with the chat's earlier user messages as the prior.

    The Ruh reader's opinion of the user's own words is weighed in only when
    it is switched on and passed its test (``ruh_reader.weigh``); otherwise
    this is :func:`naive_posterior`."""
    from . import ruh_reader

    found, runs = _posterior(text, prior)
    return ruh_reader.weigh(found, " ".join(runs))


def naive_posterior(
    text: str, prior: list[str] | None = None, using: Tamyiz | None = None
) -> dict[str, float]:
    """P(language | message) by this naive Bayes model alone (``using``: another
    fit of it, for a held-out evaluation)."""
    return _posterior(text, prior, using)[0]


def own_words(text: str, using: Tamyiz | None = None) -> str:
    """The user's own words as the reader reads them: neutral material set aside."""
    return " ".join(_own_runs(text, using)[0])


def _posterior(
    text: str, prior: list[str] | None = None, using: Tamyiz | None = None
) -> tuple[dict[str, float], list[str]]:
    runs, material = _own_runs(text, using)
    known = languages() if using is None else _languages_of(using)
    counts = {label: 1.0 for label in known}
    for earlier in (prior or [])[-12:]:
        for label, probability in naive_posterior(earlier, using=using).items():
            counts[label] = counts.get(label, 1.0) + probability
    mass = sum(material.values())
    for label in known if mass else ():
        counts[label] += material[label] / mass
    total = sum(counts.values())
    scores = {label: math.log(counts[label] / total) for label in known}
    for run in runs:
        found = (model() if using is None else using).posterior(run)
        own = sum(found.get(label, 0.0) for label in known) or 1.0
        for label in known:
            scores[label] += math.log(found.get(label, 0.0) / own + 1e-12)
    top = max(scores.values())
    weights = {label: math.exp(score - top) for label, score in scores.items()}
    norm = sum(weights.values())
    return {label: weight / norm for label, weight in weights.items()}, runs


def language(text: str, prior: list[str] | None = None) -> str:
    """The most probable language of the user's own words."""
    found = posterior(text, prior)
    return max(found, key=found.__getitem__)


def pieces(text: str) -> list[str]:
    """The message cut at line breaks and wherever the script changes."""
    found: list[str] = []
    for line in (text or "").splitlines():
        current: list[str] = []
        kind = None
        for char in line:
            script = _script(char) if letters(char) else None
            if script and kind and script != kind and current:
                found.append("".join(current))
                current = []
            if script:
                kind = script
            current.append(char)
        if current:
            found.append("".join(current))
    return [piece for piece in found if letters(piece)]


def quoted(text: str) -> list[str]:
    """Pieces of the message that read as quoted Quranic text."""
    return [piece for piece in pieces(text) if model().predict(piece)[0] == "quote"]
