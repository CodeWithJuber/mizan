"""
English Root Bridge (جسر اللغة الإنجليزية)
============================================

Maps English words to Arabic roots via CONCEPT_MAP lookup
and a simple suffix-stripping stemmer. Words without a direct
mapping get hashed into a reserved bucket range (3500-3999).
"""

from __future__ import annotations

# Suffix rules for simple English stemming, ordered longest-first.
# Each tuple: (suffix, min_stem_length_after_strip)
_SUFFIX_RULES: list[tuple[str, int]] = [
    ("ization", 3),
    ("fulness", 3),
    ("iveness", 3),
    ("ousness", 3),
    ("ation", 3),
    ("tion", 3),
    ("ment", 3),
    ("ness", 3),
    ("ence", 3),
    ("ance", 3),
    ("able", 3),
    ("ible", 3),
    ("ious", 3),
    ("eous", 3),
    ("less", 3),
    ("ling", 3),
    ("ize", 3),
    ("ise", 3),
    ("ful", 3),
    ("ous", 3),
    ("ive", 3),
    ("ity", 3),
    ("ing", 3),
    ("est", 3),
    ("ion", 3),
    ("ed", 3),
    ("ly", 3),
    ("er", 3),
    ("al", 3),
]

# Suffix -> pattern classification for English words
_SUFFIX_TO_PATTERN: dict[str, str] = {
    "ing": "VERBAL_NOUN",
    "tion": "VERBAL_NOUN",
    "ation": "VERBAL_NOUN",
    "ization": "VERBAL_NOUN",
    "ment": "VERBAL_NOUN",
    "ness": "ABSTRACT_NOUN",
    "ity": "ABSTRACT_NOUN",
    "ence": "ABSTRACT_NOUN",
    "ance": "ABSTRACT_NOUN",
    "er": "AGENT",
    "or": "AGENT",
    "ist": "AGENT",
    "ed": "VERB_PAST",
    "ly": "ADJECTIVE",
    "ful": "ADJECTIVE",
    "ous": "ADJECTIVE",
    "ious": "ADJECTIVE",
    "ive": "ADJECTIVE",
    "al": "ADJECTIVE",
    "able": "ADJECTIVE",
    "ible": "ADJECTIVE",
    "less": "ADJECTIVE",
    "ize": "VERB_PAST",
    "ise": "VERB_PAST",
    "est": "ADJECTIVE",
}

# Bucket range for unknown English stems (hashed)
_UNKNOWN_BUCKET_START = 3500
_UNKNOWN_BUCKET_END = 3999
_UNKNOWN_BUCKET_SIZE = _UNKNOWN_BUCKET_END - _UNKNOWN_BUCKET_START + 1


def _stem_english(word: str) -> tuple[str, str]:
    """Strip the longest matching English suffix.

    Returns (stem, matched_suffix). If no suffix matches,
    returns (word, "").
    """
    for suffix, min_len in _SUFFIX_RULES:
        if word.endswith(suffix) and len(word) - len(suffix) >= min_len:
            return (word[:-len(suffix)], suffix)
    return (word, "")


def _hash_to_bucket(stem: str) -> int:
    """Deterministic hash of an English stem to a bucket ID."""
    hash_value = 0
    for char in stem:
        hash_value = (hash_value * 31 + ord(char)) & 0xFFFFFFFF
    return _UNKNOWN_BUCKET_START + (hash_value % _UNKNOWN_BUCKET_SIZE)


def _classify_by_suffix(suffix: str) -> str:
    """Map an English suffix to a morphological pattern name."""
    return _SUFFIX_TO_PATTERN.get(suffix, "NOUN")


class EnglishRootBridge:
    """Maps English words to Arabic root+pattern pairs.

    Uses CONCEPT_MAP for direct lookup and falls back to
    suffix-stripping + hashing for unknown words.
    """

    def __init__(self, concept_map: dict[str, str]) -> None:
        self._concept_map = {k.lower(): v for k, v in concept_map.items()}

    def to_root(self, word: str) -> tuple[str, str]:
        """Map an English word to (arabic_root_string, pattern_name).

        Pipeline:
        1. Direct CONCEPT_MAP lookup
        2. Stem the word, try CONCEPT_MAP again
        3. Hash the stem to a bucket for unknown roots
        """
        lower = word.lower().strip()
        if not lower:
            return ("", "UNKNOWN")

        # Direct lookup
        if lower in self._concept_map:
            return (self._concept_map[lower], "NOUN")

        # Stem and retry
        stem, suffix = _stem_english(lower)
        pattern = _classify_by_suffix(suffix) if suffix else "NOUN"

        if stem in self._concept_map:
            return (self._concept_map[stem], pattern)

        # No match -- hash to reserved bucket
        bucket_id = _hash_to_bucket(stem)
        return (f"<ENG:{bucket_id}>", pattern)
