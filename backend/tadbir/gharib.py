"""Gharib (غريب): how rare a word is in its language.

A word's information is its Shannon self-information in the language of the
text it is read in:

    information(w | L) = −log P(w | L)

for MIZAN's languages L: English, Arabic, Hindi, Urdu and Tamil, from the word
frequencies of wordfreq 3.1.1 (each language counted over Wikipedia, web text,
Twitter and more; data CC BY-SA 4.0), and Roman Hindi/Urdu (``hi-latn``) from
Lughah's Roman Hindi sentences (below). A text's language is the one under
which its words are most probable, Σ log P(w | L) (maximum likelihood); a word
read alone is read in the language that writes it most often.

A word is looked up as wordfreq's list writes it: Unicode NFKC (NFC for Latin
script), case-folded, and in Arabic script without vowel marks or tatweel. A
number is its shape (each digit a 0) times 10^−digits: every number of a shape
is equally likely. Every list keeps the words written at least once per
million (10^−6, the least the Hindi, Urdu and Tamil lists hold), so a word the
list does not hold (a name, a rare term, a word of another script) carries
−log 10^−6 = 13.8 nats, the same in every language.

A word is **informative** when it carries more than an average running word of
its language (``floor``, the entropy Σ_w P(w | L) · information(w | L)):
"the", "है", "کے", "hai" are below it; "Canberra", "राजधानी", "1975" above.

``ahl_dhikr.about`` weighs words by an inverse document frequency over
Lughah's five small corpora pooled (about 900 sentences each), so an ordinary
Hindi or Urdu word such as "प्रसिद्ध" (famous) or "سب" (all) looks distinctive.
This module was built to replace it and measured on 30 Oct 2026; it is not
used (``ahl_dhikr.WORDS = "lughah"``): it did not make Hindi and Urdu supports
more precise and lost English contradictions (``docs/ahl-dhikr.md``).

Roman Hindi is written in English letters and mixes English words in. Each
running word of Lughah's 982 Roman Hindi sentences is taken to be a Roman Hindi
word with probability λ, or an English one:

    P(w | hi-latn) = λ · P_roman(w) + (1 − λ) · P(w | en)

fitted by EM with each occurrence left out of its own word's estimate, so a
word seen once is no evidence of Roman Hindi (``scripts/build_gharib.py``).

Data: ``data/gharib/words.json.gz`` (``data/gharib/LICENSES.md``), rebuilt and
checked byte for byte by ``scripts/build_gharib.py --check``.
"""

from __future__ import annotations

import gzip
import json
import math
import unicodedata
from collections.abc import Mapping
from functools import cache, lru_cache
from pathlib import Path
from typing import Literal

from core.adaptive import tokenize

DATA = Path(__file__).parent / "data" / "gharib"
FORMAT = "mizan-gharib/1"
LANGUAGES = ("en", "hi-latn", "ar", "ur", "hi", "ta")
# The least frequency a list keeps: a word below it, or in no list, is as rare
# as the rarest word any list holds.
LEAST = 1e-6
MOST_INFORMATION = -math.log(LEAST)
MAX_WORDS = 400  # a text's language is read from its first words
_ABJAD = ("ar", "ur")
_LATIN = ("en", "hi-latn")
_TATWEEL = "ـ"

Tables = Mapping[str, Mapping[str, float]]
Mixed = Mapping[str, tuple[str, float]]


def fold(word: str, language: str) -> str:
    """A word as a language's list writes it (wordfreq's own normal form)."""
    form: Literal["NFC", "NFKC"] = "NFC" if language in _LATIN else "NFKC"
    text = unicodedata.normalize(form, word)
    if language in _ABJAD:
        text = "".join(
            char for char in text if char != _TATWEEL and unicodedata.category(char) != "Mn"
        )
    return text.casefold()


def shape(word: str) -> tuple[str, int]:
    """A word with each digit written 0, and how many digits it has."""
    digits = sum(1 for char in word if char.isdecimal())
    if not digits:
        return word, 0
    return "".join("0" if char.isdecimal() else char for char in word), digits


def chance(tables: Tables, mixed: Mixed, word: str, language: str) -> float:
    """P(word | language) from word lists, at least ``LEAST``. A language mixed
    with another (Roman Hindi with English) gives a word it does not hold the
    other's probability times the other's share."""
    written, digits = shape(fold(word, language))
    p = tables.get(language, {}).get(written)
    if p is None and language in mixed:
        base, share = mixed[language]
        p = share * tables.get(base, {}).get(shape(fold(word, base))[0], 0.0)
    return max((p or 0.0) * 10.0**-digits, LEAST)


@cache
def _load() -> tuple[dict[str, dict[str, float]], dict[str, tuple[str, float]], dict[str, float]]:
    """Each language's words with their probabilities, the mixed languages,
    and each language's floor."""
    data = json.loads(gzip.decompress((DATA / "words.json.gz").read_bytes()))
    if data.get("format") != FORMAT:
        raise ValueError(f"unexpected word list format: {data.get('format')!r}")
    tables: dict[str, dict[str, float]] = {}
    floors: dict[str, float] = {}
    for code, entry in data["languages"].items():
        table = tables.setdefault(code, {})
        for centibels, words in entry["bins"].items():
            p = 10 ** (-int(centibels) / 100)
            for word in words:
                table[word] = p
        floors[code] = float(entry["floor"])
    mixed = {
        code: (str(entry["base"]), float(entry["share"]))
        for code, entry in (data.get("mixed") or {}).items()
    }
    return tables, mixed, floors


def probability(word: str, language: str) -> float:
    """P(word | language), at least ``LEAST``."""
    tables, mixed, _floors = _load()
    return chance(tables, mixed, word, language)


@lru_cache(maxsize=8192)
def language_of(text: str) -> str:
    """The language under which the text's words are most probable (the first
    listed on a tie, English)."""
    words = tokenize(text)[:MAX_WORDS]
    scores = {code: sum(math.log(probability(word, code)) for word in words) for code in LANGUAGES}
    return max(LANGUAGES, key=scores.__getitem__)


def information(word: str, language: str | None = None) -> float:
    """The word's self-information in nats, −log P(word | language); without a
    language, in the language that writes it most often."""
    return -math.log(probability(word, language or language_of(word)))


def floor(language: str) -> float:
    """The information of an average running word of the language."""
    return _load()[2][language]


def informative(word: str, language: str | None = None) -> bool:
    """The word carries more than an average running word of its language: it
    is not a function word ("the", "है", "کے", "hai")."""
    code = language or language_of(word)
    return information(word, code) > floor(code)
