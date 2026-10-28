"""
Arabic Morphological Analyzer (محلل صرفي)
==========================================

Strips affixes from Arabic words, extracts trilateral roots,
and classifies morphological patterns. Pure rule-based -- no ML.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Common Arabic prefixes, ordered longest-first for greedy matching
_PREFIXES: list[tuple[str, str]] = [
    ("وال", "conjunction+definite"),  # wa-al
    ("فال", "conjunction+definite"),  # fa-al
    ("بال", "preposition+definite"),  # bi-al
    ("كال", "preposition+definite"),  # ka-al
    ("لل", "preposition+definite"),   # li-al (assimilated)
    ("ال", "definite"),               # al-
    ("و", "conjunction"),             # wa-
    ("ف", "conjunction"),             # fa-
    ("ب", "preposition"),             # bi-
    ("ل", "preposition"),             # li-
    ("ك", "preposition"),             # ka-
]

# Common Arabic suffixes, ordered longest-first
_SUFFIXES: list[tuple[str, str]] = [
    ("اتهم", "fem_plural+their"),
    ("ونهم", "masc_plural+their"),
    ("ينهم", "masc_plural+their"),
    ("ات", "fem_plural"),
    ("ون", "masc_plural_nom"),
    ("ين", "masc_plural_acc"),
    ("ان", "dual_nom"),
    ("تين", "dual_fem_acc"),
    ("تان", "dual_fem_nom"),
    ("هم", "their"),
    ("هن", "their_fem"),
    ("كم", "your_plural"),
    ("نا", "our"),
    ("ها", "her"),
    ("هم", "him"),
    ("ية", "nisba_fem"),
    ("ة", "ta_marbuta"),
    ("ي", "nisba"),
    ("ه", "pronoun_suffix"),
]

# Arabic diacritical marks (tashkeel) to strip
_TASHKEEL = re.compile(
    "[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]"
)

# Arabic letter detection
_ARABIC_CHAR = re.compile("[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

# Weak letters that may be elided in roots
_WEAK_LETTERS = {"ا", "و", "ي", "ى", "ء", "أ", "إ", "آ", "ؤ", "ئ"}

# Hamza normalizations
_HAMZA_MAP = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ؤ": "و",
    "ئ": "ي",
}

# U+0671 ARABIC LETTER SUPERSCRIPT ALEF (alef wasla). Quranic orthography
# writes word-initial alefs with ٱ instead of ا — the definite article
# (ٱلـ for الـ, e.g. ٱلناس for الناس) and other initial alefs (e.g. ٱقْرَأْ
# for اقرأ, وَٱلشَّمْسِ for والشمس). It always corresponds to U+0627 ALEF in
# standard orthography and never occurs word-medially/finally, so mapping it
# to plain alef before affix stripping makes Quranic spellings behave
# exactly like their standard equivalents. Kept separate from _HAMZA_MAP:
# wasla is not a hamza variant, and the mapping must be auditable on its own.
_WASLA_ALEF = "\u0671"
_PLAIN_ALEF = "\u0627"


def _strip_tashkeel(text: str) -> str:
    """Remove all Arabic diacritical marks."""
    return _TASHKEEL.sub("", text)


def _normalize_hamza(text: str) -> str:
    """Normalize hamza variants to their base letters."""
    return "".join(_HAMZA_MAP.get(char, char) for char in text)


def _normalize_wasla(text: str) -> str:
    """Map Quranic alef-wasla (U+0671) to plain alef (U+0627).

    No-op for text without U+0671, so standard-orthography words are
    unaffected by construction.
    """
    return text.replace(_WASLA_ALEF, _PLAIN_ALEF)


def _clean_word(word: str) -> str:
    """Full normalization pipeline: tashkeel strip, wasla, hamza.

    Single choke point so every consumer (prefix stripping, root
    extraction, pattern classification) sees the same normalized form.
    """
    return _normalize_hamza(_normalize_wasla(_strip_tashkeel(word)))


def _is_arabic(text: str) -> bool:
    """Check if text contains any Arabic character."""
    return bool(_ARABIC_CHAR.search(text))


@lru_cache(maxsize=1)
def _known_roots() -> frozenset[str]:
    """Roots of the bundled lexicon (``ARABIC_ROOTS``), normalized.

    Used only to choose between readings of a word whose first letter may be
    a prefix or a root letter (كتاب: ك-ت-ب, not the preposition ك + تاب).
    Without a lexicon the greedy reading is kept.
    """
    try:
        from bayan._tok.root_vocab import _load_roots_module

        roots = _load_roots_module().ARABIC_ROOTS
    except Exception:  # noqa: BLE001 - no lexicon: keep the greedy reading
        return frozenset()
    return frozenset(_clean_word(root) for root in roots)


class ArabicMorphAnalyzer:
    """Rule-based Arabic morphological analyzer.

    Strips affixes, extracts trilateral roots, and classifies
    the morphological pattern of surface forms.
    """

    def __init__(self) -> None:
        self._prefixes = _PREFIXES
        self._suffixes = _SUFFIXES

    def analyze(self, word: str) -> tuple[str, str]:
        """Analyze a single Arabic word into (root, pattern_name).

        Returns the extracted trilateral root and best-guess pattern.
        """
        if not word or not _is_arabic(word):
            return ("", "UNKNOWN")

        cleaned = _clean_word(word)

        prefix, prefix_type, stem, suffix_type, root = self._best_reading(cleaned)
        # ال, ب and ك attach only to nouns (ل also introduces a verb: ليعلم).
        nominal = "definite" in prefix_type or prefix in ("ب", "ك")
        pattern = self._classify_pattern(cleaned, stem, suffix_type, nominal)

        return (root, pattern)

    def _best_reading(self, cleaned: str) -> tuple[str, str, str, str, str]:
        """(prefix, prefix_type, stem, suffix_type, root) of the most likely reading.

        The longest matching prefix and suffix are stripped, as before, unless
        a shorter reading gives a root the lexicon knows and that one does not:
        ك in كتاب and ي in وحي are root letters, ك in كالبرق is a preposition.
        """
        readings = []
        for prefix, prefix_type in [*self._prefixes, ("", "none")]:
            if not prefix or (cleaned.startswith(prefix) and len(cleaned) - len(prefix) >= 2):
                rest = cleaned[len(prefix):]
                for stem, suffix_type in dict.fromkeys([self._strip_suffixes(rest), (rest, "none")]):
                    root = self._extract_trilateral(stem)
                    readings.append((prefix, prefix_type, stem, suffix_type, root))
        known = _known_roots()
        return next((reading for reading in readings if reading[4] in known), readings[0])

    def extract_root(self, word: str) -> str:
        """Extract just the root from an Arabic word."""
        root, _ = self.analyze(word)
        return root

    def _strip_prefixes(self, word: str) -> str:
        """Remove the longest matching prefix."""
        return self._strip_prefix(word)[0]

    def _strip_prefix(self, word: str) -> tuple[str, str]:
        """Remove the longest matching prefix. Returns (stem, prefix_type)."""
        for prefix, prefix_type in self._prefixes:
            if word.startswith(prefix) and len(word) - len(prefix) >= 2:
                return (word[len(prefix):], prefix_type)
        return (word, "none")

    def _strip_suffixes(self, word: str) -> tuple[str, str]:
        """Remove the longest matching suffix. Returns (stem, suffix_type)."""
        for suffix, suffix_type in self._suffixes:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                return (word[:-len(suffix)], suffix_type)
        return (word, "none")

    def _extract_trilateral(self, stem: str) -> str:
        """Extract a 3-letter root skeleton from the stem.

        Filters out weak/filler letters to find the consonantal root.
        """
        if len(stem) <= 3:
            return stem

        # Keep only strong consonants (non-weak letters)
        consonants = [ch for ch in stem if ch not in _WEAK_LETTERS]

        if len(consonants) >= 3:
            return "".join(consonants[:3])

        # If not enough strong consonants, use what we have
        return stem[:3] if len(stem) >= 3 else stem

    def _classify_pattern(
        self, original: str, stem: str, suffix_type: str, nominal: bool = False
    ) -> str:
        """Classify the morphological pattern based on word shape.

        Uses prefix/suffix context and stem length to determine the
        most likely pattern category. ``nominal``: a prefix that only a
        noun takes was stripped (ال, ب, ك), so the word is not a verb.
        """
        if suffix_type == "ta_marbuta":
            return self._classify_ta_marbuta_word(original)
        if suffix_type in ("fem_plural", "fem_plural+their"):
            return "NOUN"
        if suffix_type in ("masc_plural_nom", "masc_plural_acc", "masc_plural+their"):
            return "NOUN"
        if suffix_type in ("nisba", "nisba_fem"):
            return "ADJECTIVE"

        if nominal:
            return self._classify_noun_shape(stem)
        return self._classify_by_shape(original, stem)

    def _classify_ta_marbuta_word(self, original: str) -> str:
        """Words ending in ta-marbuta are usually nouns or verbal nouns."""
        cleaned = _clean_word(original)
        # Pattern: maf3ala -> PLACE_NOUN
        if cleaned.startswith("م") and len(cleaned) >= 5:
            return "PLACE_NOUN"
        return "VERBAL_NOUN"

    def _classify_noun_shape(self, stem: str) -> str:
        """Classify a stem known to be a noun (its prefix was ال, ب or ك)."""
        # Active participle: fa'il, alef after the first root letter (كاتب, not كتاب)
        if len(stem) >= 4 and stem[1] == "ا":
            return "ACTIVE_PARTICIPLE"
        # Passive participle: maf'ul (مكتوب)
        if len(stem) == 5 and stem[0] == "م" and stem[3] == "و":
            return "PASSIVE_PARTICIPLE"
        return "NOUN"

    def _classify_by_shape(self, original: str, stem: str) -> str:
        """Classify based on word shape (prefix patterns, stem length)."""
        cleaned = _clean_word(original)

        # Verbal prefixes: ya-, ta-, na- (present tense markers)
        if cleaned and cleaned[0] in ("ي", "ت", "ن") and len(cleaned) >= 4:
            return "VERB_PRESENT"

        # Past tense is typically 3-4 letters with no special prefix
        if len(stem) == 3:
            return "VERB_PAST"

        # Active participle: fa'il, alef after the first root letter (كاتب, not كتاب)
        if len(cleaned) >= 4 and cleaned[1] == "ا":
            return "ACTIVE_PARTICIPLE"

        # Passive participle: maf'ul pattern
        if cleaned.startswith("م") and len(cleaned) >= 5:
            return "PASSIVE_PARTICIPLE"

        # Instrument noun: mif'al pattern
        if cleaned.startswith("م") and len(cleaned) == 4:
            return "INSTRUMENT_NOUN"

        return "NOUN"
