"""
Arabic Morphological Analyzer (محلل صرفي)
==========================================

Strips affixes from Arabic words, extracts trilateral roots,
and classifies morphological patterns. Pure rule-based -- no ML.
"""

from __future__ import annotations

import re
import unicodedata

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


def _strip_tashkeel(text: str) -> str:
    """Remove all Arabic diacritical marks."""
    return _TASHKEEL.sub("", text)


def _normalize_hamza(text: str) -> str:
    """Normalize hamza variants to their base letters."""
    return "".join(_HAMZA_MAP.get(char, char) for char in text)


def _is_arabic(text: str) -> bool:
    """Check if text contains any Arabic character."""
    return bool(_ARABIC_CHAR.search(text))


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

        cleaned = _strip_tashkeel(word)
        cleaned = _normalize_hamza(cleaned)

        stem = self._strip_prefixes(cleaned)
        stem, suffix_type = self._strip_suffixes(stem)
        root = self._extract_trilateral(stem)
        pattern = self._classify_pattern(cleaned, stem, suffix_type)

        return (root, pattern)

    def extract_root(self, word: str) -> str:
        """Extract just the root from an Arabic word."""
        root, _ = self.analyze(word)
        return root

    def _strip_prefixes(self, word: str) -> str:
        """Remove the longest matching prefix."""
        for prefix, _ in self._prefixes:
            if word.startswith(prefix) and len(word) - len(prefix) >= 2:
                return word[len(prefix):]
        return word

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
        self, original: str, stem: str, suffix_type: str
    ) -> str:
        """Classify the morphological pattern based on word shape.

        Uses prefix/suffix context and stem length to determine the
        most likely pattern category.
        """
        if suffix_type == "ta_marbuta":
            return self._classify_ta_marbuta_word(original)
        if suffix_type in ("fem_plural", "fem_plural+their"):
            return "NOUN"
        if suffix_type in ("masc_plural_nom", "masc_plural_acc", "masc_plural+their"):
            return "NOUN"
        if suffix_type in ("nisba", "nisba_fem"):
            return "ADJECTIVE"

        return self._classify_by_shape(original, stem)

    def _classify_ta_marbuta_word(self, original: str) -> str:
        """Words ending in ta-marbuta are usually nouns or verbal nouns."""
        cleaned = _strip_tashkeel(_normalize_hamza(original))
        # Pattern: maf3ala -> PLACE_NOUN
        if cleaned.startswith("م") and len(cleaned) >= 5:
            return "PLACE_NOUN"
        return "VERBAL_NOUN"

    def _classify_by_shape(self, original: str, stem: str) -> str:
        """Classify based on word shape (prefix patterns, stem length)."""
        cleaned = _strip_tashkeel(_normalize_hamza(original))

        # Verbal prefixes: ya-, ta-, na- (present tense markers)
        if cleaned and cleaned[0] in ("ي", "ت", "ن") and len(cleaned) >= 4:
            return "VERB_PRESENT"

        # Past tense is typically 3-4 letters with no special prefix
        if len(stem) == 3:
            return "VERB_PAST"

        # Active participle: fa'il pattern (starts with strong letter, 4+ chars)
        if len(cleaned) >= 4 and "ا" in cleaned[1:3]:
            return "ACTIVE_PARTICIPLE"

        # Passive participle: maf'ul pattern
        if cleaned.startswith("م") and len(cleaned) >= 5:
            return "PASSIVE_PARTICIPLE"

        # Instrument noun: mif'al pattern
        if cleaned.startswith("م") and len(cleaned) == 4:
            return "INSTRUMENT_NOUN"

        return "NOUN"
