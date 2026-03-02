"""
Bayan Tokenizer (مُبَيِّن)
============================

Morphologically-aware, root-cognizant tokenizer for the Ruh model.
Encodes text as (root_id, pattern_id) tuples instead of BPE tokens.

Supports Arabic (via morphological analysis) and English (via
concept-map bridge). Auto-detects language per word.

"He created man. He taught him al-Bayan (clear expression)." -- Quran 55:3-4
"""

from __future__ import annotations

import re
from typing import Any

from ruh_model.tokenizer.english_bridge import EnglishRootBridge
from ruh_model.tokenizer.morphology import ArabicMorphAnalyzer
from ruh_model.tokenizer.q28_articulatory import Q28ArticulatoryBasis
from ruh_model.tokenizer.root_vocab import (
    BOS_ID,
    EOS_ID,
    PAD_ID,
    PATTERN_STOPWORD,
    PATTERN_UNKNOWN,
    RootVocab,
    build_default_vocab,
    _load_roots_module,
)

# Arabic character range detection
_ARABIC_RE = re.compile("[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

# Tokenization: split on whitespace and punctuation (keep words only)
_WORD_SPLIT_RE = re.compile(r"[^\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")

# English stopwords that carry no semantic root
_ENGLISH_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could",
    "of", "in", "to", "for", "with", "on", "at", "from", "by",
    "and", "or", "but", "not", "no", "nor",
    "it", "its", "this", "that", "these", "those",
    "i", "me", "my", "we", "us", "our",
    "he", "him", "his", "she", "her", "they", "them", "their",
    "who", "whom", "which", "what", "where", "when", "how", "why",
    "if", "then", "so", "as", "than", "too", "very",
    "just", "about", "up", "out", "into", "over",
})

# Arabic stopwords (common particles with no trilateral root)
_ARABIC_STOPWORDS: frozenset[str] = frozenset({
    "في", "من", "إلى", "على", "عن", "مع",
    "هو", "هي", "هم", "هن", "أنا", "نحن", "أنت", "أنتم",
    "هذا", "هذه", "ذلك", "تلك", "هؤلاء", "أولئك",
    "لا", "لم", "لن", "ما", "إن", "أن", "كان", "ليس",
    "قد", "ثم", "أو", "بل", "لكن", "حتى",
})


def _contains_arabic(text: str) -> bool:
    """Check whether text contains any Arabic character."""
    return bool(_ARABIC_RE.search(text))


def _is_stopword(word: str) -> bool:
    """Check if word is a stopword in either language."""
    lower = word.lower().strip()
    return lower in _ENGLISH_STOPWORDS or lower in _ARABIC_STOPWORDS


def _tokenize_text(text: str) -> list[str]:
    """Split text into word tokens, filtering empty strings."""
    return [w for w in _WORD_SPLIT_RE.split(text) if w]


class BayanTokenizer:
    """Root-cognizant tokenizer producing (root_id, pattern_id) tuples.

    Each token is a pair of integers: the root identity and the
    morphological pattern, replacing subword BPE with linguistically
    grounded representations.
    """

    def __init__(self, vocab: RootVocab | None = None) -> None:
        self._vocab = vocab if vocab is not None else build_default_vocab()
        self._arabic_analyzer = ArabicMorphAnalyzer()
        self._english_bridge = self._build_english_bridge()
        self._q28 = Q28ArticulatoryBasis()

    def _build_english_bridge(self) -> EnglishRootBridge:
        """Create EnglishRootBridge from the project's CONCEPT_MAP."""
        roots_mod = _load_roots_module()
        return EnglishRootBridge(roots_mod.CONCEPT_MAP)

    def encode(self, text: str) -> list[tuple[int, int]]:
        """Encode text into a list of (root_id, pattern_id) tuples.

        Prepends BOS and appends EOS. Stopwords get (PAD_ID, STOPWORD).
        """
        if not text or not text.strip():
            return [(BOS_ID, 0), (EOS_ID, 0)]

        tokens: list[tuple[int, int]] = [(BOS_ID, 0)]
        words = _tokenize_text(text)

        for word in words:
            root_id, pattern_id = self._encode_word(word)
            tokens.append((root_id, pattern_id))

        tokens.append((EOS_ID, 0))
        return tokens

    def _encode_word(self, word: str) -> tuple[int, int]:
        """Encode a single word to (root_id, pattern_id)."""
        if _is_stopword(word):
            return (PAD_ID, PATTERN_STOPWORD)

        if _contains_arabic(word):
            return self._encode_arabic(word)
        return self._encode_english(word)

    def _encode_arabic(self, word: str) -> tuple[int, int]:
        """Encode an Arabic word via morphological analysis."""
        root_str, pattern_name = self._arabic_analyzer.analyze(word)
        root_id = self._vocab.get_root_id(root_str)
        pattern_id = self._vocab.get_pattern_id(pattern_name)
        return (root_id, pattern_id)

    def _encode_english(self, word: str) -> tuple[int, int]:
        """Encode an English word via concept-map, falling back to Q28 articulatory matching.

        Pipeline: concept-map lookup -> Q28 IPA->articulatory->root matching.
        """
        root_str, pattern_name = self._english_bridge.to_root(word)

        # If bridge returned a hash-bucket fallback, try Q28 articulatory matching
        if root_str.startswith("<ENG:"):
            root_str = self._q28_root_match(word)

        root_id = self._vocab.get_root_id(root_str)
        pattern_id = self._vocab.get_pattern_id(pattern_name)
        return (root_id, pattern_id)

    def _q28_root_match(self, word: str) -> str:
        """Find the nearest Arabic root via Q28 articulatory phonetics."""
        q28_coords = self._q28.text_to_q28(word, lang="en")
        if not q28_coords:
            return f"<UNK:{word}>"
        return self._q28.q28_to_root_hint(q28_coords)

    def decode(self, tokens: list[tuple[int, int]]) -> str:
        """Decode (root_id, pattern_id) tuples back to approximate text.

        Best-effort reconstruction using the root string and first
        derivative found for the pattern. BOS/EOS/PAD tokens are skipped.
        """
        words: list[str] = []
        skip_ids = {PAD_ID, BOS_ID, EOS_ID}

        for root_id, pattern_id in tokens:
            if root_id in skip_ids:
                continue
            word = self._decode_token(root_id, pattern_id)
            if word:
                words.append(word)

        return " ".join(words)

    def _decode_token(self, root_id: int, pattern_id: int) -> str:
        """Decode a single token to its best surface form."""
        root_str = self._vocab.id_to_root.get(root_id, "")
        if not root_str or root_str.startswith("<"):
            return root_str

        derivative = self._find_derivative(root_str, pattern_id)
        return derivative if derivative else root_str

    def _find_derivative(self, root_str: str, pattern_id: int) -> str:
        """Look up the first derivative matching the pattern for a root."""
        roots_mod = _load_roots_module()
        ARABIC_ROOTS = roots_mod.ARABIC_ROOTS

        root_data = ARABIC_ROOTS.get(root_str)
        if not root_data:
            return root_str

        pattern_name = self._vocab.id_to_pattern.get(pattern_id, "")
        derivatives = root_data.get("derivatives", {})

        # Return root string if no derivatives exist
        if not derivatives:
            return root_str

        # Try to match pattern to a derivative key heuristically
        target = _pattern_to_derivative_hint(pattern_name)
        for deriv_key in derivatives:
            if target and target in derivatives[deriv_key].lower():
                return deriv_key

        # Fallback: return first derivative
        return next(iter(derivatives))

    def encode_batch(self, texts: list[str]) -> list[list[tuple[int, int]]]:
        """Encode a batch of texts."""
        return [self.encode(text) for text in texts]

    def analyze(self, text: str) -> list[dict[str, Any]]:
        """Produce a detailed per-word analysis of the input text.

        Returns a list of dicts with: surface, root, pattern, root_meaning.
        """
        if not text or not text.strip():
            return []

        words = _tokenize_text(text)
        results: list[dict[str, Any]] = []

        for word in words:
            entry = self._analyze_word(word)
            results.append(entry)

        return results

    def _analyze_word(self, word: str) -> dict[str, Any]:
        """Analyze a single word into a detailed dict."""
        roots_mod = _load_roots_module()
        ARABIC_ROOTS = roots_mod.ARABIC_ROOTS

        if _is_stopword(word):
            return {
                "surface": word,
                "root": "",
                "pattern": "STOPWORD",
                "root_meaning": "stopword",
                "is_stopword": True,
            }

        if _contains_arabic(word):
            root_str, pattern_name = self._arabic_analyzer.analyze(word)
        else:
            root_str, pattern_name = self._english_bridge.to_root(word)

        root_data = ARABIC_ROOTS.get(root_str, {})
        meaning = root_data.get("meaning", "unknown")

        return {
            "surface": word,
            "root": root_str,
            "pattern": pattern_name,
            "root_meaning": meaning,
            "is_stopword": False,
        }

    @property
    def vocab_size(self) -> int:
        """Total vocabulary size (roots * patterns)."""
        return self._vocab.n_roots * self._vocab.n_patterns


def _pattern_to_derivative_hint(pattern_name: str) -> str:
    """Map a pattern name to a keyword used to find matching derivatives."""
    hints: dict[str, str] = {
        "VERB_PAST": "he ",
        "VERB_PRESENT": "he ",
        "ACTIVE_PARTICIPLE": "one who",
        "PASSIVE_PARTICIPLE": "that which",
        "VERBAL_NOUN": "act of",
        "AGENT": "one who",
        "PATIENT": "that which",
        "PLACE_NOUN": "place",
        "INSTRUMENT_NOUN": "tool",
    }
    return hints.get(pattern_name, "")
