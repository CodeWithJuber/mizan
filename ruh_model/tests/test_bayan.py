"""Tests for BayanTokenizer -- morphologically-aware root+pattern tokenizer."""

from __future__ import annotations

import pytest

from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.root_vocab import (
    BOS_ID,
    EOS_ID,
    PAD_ID,
    UNK_ID,
    RootVocab,
)


@pytest.fixture
def tokenizer(default_vocab: RootVocab) -> BayanTokenizer:
    """BayanTokenizer backed by the full default vocabulary."""
    return BayanTokenizer(vocab=default_vocab)


# ---------------------------------------------------------------------------
# Basic encode / decode
# ---------------------------------------------------------------------------


class TestEncodeBasics:
    """Core encoding behaviour: BOS/EOS framing, empty input, round-trip."""

    def test_encode_empty_string(self, tokenizer: BayanTokenizer) -> None:
        """Empty or whitespace-only text returns just BOS + EOS."""
        result = tokenizer.encode("")
        assert result == [(BOS_ID, 0), (EOS_ID, 0)]

        result_spaces = tokenizer.encode("   ")
        assert result_spaces == [(BOS_ID, 0), (EOS_ID, 0)]

    def test_encode_english_text(self, tokenizer: BayanTokenizer) -> None:
        """English phrase produces BOS + per-word tokens + EOS."""
        tokens = tokenizer.encode("Knowledge guides truth")
        assert len(tokens) >= 5  # BOS + 3 words + EOS (at minimum)

        # First and last must be BOS/EOS
        assert tokens[0][0] == BOS_ID
        assert tokens[-1][0] == EOS_ID

        # Interior tokens should be real (non-BOS/EOS)
        interior = tokens[1:-1]
        for root_id, pattern_id in interior:
            assert root_id != BOS_ID
            assert root_id != EOS_ID

    def test_encode_arabic_text(self, tokenizer: BayanTokenizer) -> None:
        """Arabic text produces valid (root_id, pattern_id) tuples."""
        tokens = tokenizer.encode("كتب العلم")
        assert len(tokens) >= 3  # BOS + at least 1 word + EOS

        assert tokens[0][0] == BOS_ID
        assert tokens[-1][0] == EOS_ID

        # Each token is a 2-tuple of ints
        for root_id, pattern_id in tokens:
            assert isinstance(root_id, int)
            assert isinstance(pattern_id, int)
            assert root_id >= 0
            assert pattern_id >= 0

    def test_encode_decode_roundtrip(self, tokenizer: BayanTokenizer) -> None:
        """Encode then decode produces recognizable output (not necessarily exact)."""
        original = "Knowledge guides truth"
        tokens = tokenizer.encode(original)
        decoded = tokenizer.decode(tokens)

        # Decoded text should be non-empty and contain at least one word
        assert isinstance(decoded, str)
        assert len(decoded) > 0

    def test_encode_single_word(self, tokenizer: BayanTokenizer) -> None:
        """Single word produces BOS + 1 token + EOS."""
        tokens = tokenizer.encode("knowledge")
        assert len(tokens) == 3  # BOS + word + EOS
        assert tokens[0][0] == BOS_ID
        assert tokens[-1][0] == EOS_ID


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------


class TestStopwords:
    """English and Arabic stopwords should get PAD_ID root."""

    def test_stopwords_get_pad_root(self, tokenizer: BayanTokenizer) -> None:
        """Common English stopwords map to PAD_ID root with STOPWORD pattern."""
        stopwords = ["the", "a", "is", "of", "in", "and"]
        for word in stopwords:
            tokens = tokenizer.encode(word)
            # Interior token (skip BOS/EOS)
            root_id, pattern_id = tokens[1]
            assert root_id == PAD_ID, f"'{word}' should map to PAD_ID, got {root_id}"
            assert pattern_id == 15, f"'{word}' should get STOPWORD pattern (15)"

    def test_arabic_stopwords_get_pad_root(self, tokenizer: BayanTokenizer) -> None:
        """Common Arabic stopwords map to PAD_ID root."""
        arabic_stopwords = ["في", "من", "على"]
        for word in arabic_stopwords:
            tokens = tokenizer.encode(word)
            root_id, _pattern_id = tokens[1]
            assert root_id == PAD_ID, (
                f"Arabic stopword '{word}' should map to PAD_ID, got {root_id}"
            )


# ---------------------------------------------------------------------------
# Batch encoding
# ---------------------------------------------------------------------------


class TestBatchEncoding:
    """encode_batch should process multiple texts independently."""

    def test_encode_batch(self, tokenizer: BayanTokenizer) -> None:
        """Batch of 3 texts returns 3 token lists, each with BOS/EOS."""
        texts = [
            "Knowledge guides truth",
            "The quick brown fox",
            "Peace",
        ]
        results = tokenizer.encode_batch(texts)

        assert len(results) == 3
        for token_list in results:
            assert isinstance(token_list, list)
            assert len(token_list) >= 2  # at least BOS + EOS
            assert token_list[0][0] == BOS_ID
            assert token_list[-1][0] == EOS_ID

    def test_encode_batch_empty_list(self, tokenizer: BayanTokenizer) -> None:
        """Empty batch returns empty list."""
        assert tokenizer.encode_batch([]) == []

    def test_encode_batch_preserves_order(self, tokenizer: BayanTokenizer) -> None:
        """Results correspond to inputs in order."""
        texts = ["knowledge", "truth"]
        results = tokenizer.encode_batch(texts)

        single_first = tokenizer.encode("knowledge")
        single_second = tokenizer.encode("truth")

        assert results[0] == single_first
        assert results[1] == single_second


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------


class TestAnalyze:
    """analyze() returns per-word detail dicts."""

    def test_analyze_returns_details(self, tokenizer: BayanTokenizer) -> None:
        """Each analysis entry contains required keys."""
        results = tokenizer.analyze("Knowledge guides truth")

        assert len(results) >= 3  # at least 3 words
        for entry in results:
            assert "surface" in entry
            assert "root" in entry
            assert "pattern" in entry
            assert "root_meaning" in entry

    def test_analyze_empty_string(self, tokenizer: BayanTokenizer) -> None:
        """Empty string returns empty analysis list."""
        assert tokenizer.analyze("") == []
        assert tokenizer.analyze("   ") == []

    def test_analyze_stopword_entry(self, tokenizer: BayanTokenizer) -> None:
        """Stopwords are flagged in analysis output."""
        results = tokenizer.analyze("the knowledge")
        stopword_entry = results[0]  # "the" is first

        assert stopword_entry["surface"] == "the"
        assert stopword_entry["pattern"] == "STOPWORD"
        assert stopword_entry["is_stopword"] is True

    def test_analyze_concept_word(self, tokenizer: BayanTokenizer) -> None:
        """Concept-mapped words have a non-empty root and meaningful root_meaning."""
        results = tokenizer.analyze("knowledge")
        entry = results[0]

        assert entry["surface"] == "knowledge"
        assert entry["root"] != ""
        assert entry["root_meaning"] != "unknown"


# ---------------------------------------------------------------------------
# Mixed language
# ---------------------------------------------------------------------------


class TestMixedLanguage:
    """Texts containing both Arabic and English words."""

    def test_mixed_language(self, tokenizer: BayanTokenizer) -> None:
        """Mixed Arabic+English input produces valid tokens for every word."""
        mixed_text = "العلم knowledge"
        tokens = tokenizer.encode(mixed_text)

        assert tokens[0][0] == BOS_ID
        assert tokens[-1][0] == EOS_ID

        # Should have BOS + 2 words + EOS = 4 tokens
        assert len(tokens) >= 4

        # All tokens should be valid 2-tuples
        for root_id, pattern_id in tokens:
            assert isinstance(root_id, int)
            assert isinstance(pattern_id, int)


# ---------------------------------------------------------------------------
# Vocab properties
# ---------------------------------------------------------------------------


class TestVocabProperties:
    """Tokenizer vocabulary metadata."""

    def test_vocab_size_positive(self, tokenizer: BayanTokenizer) -> None:
        """vocab_size must be a positive integer."""
        assert tokenizer.vocab_size > 0

    def test_concept_map_words_get_real_roots(
        self, tokenizer: BayanTokenizer
    ) -> None:
        """Key concept words should map to non-UNK root IDs."""
        concept_words = ["knowledge", "truth", "guide"]
        for word in concept_words:
            tokens = tokenizer.encode(word)
            root_id, _pattern_id = tokens[1]  # skip BOS
            assert root_id != UNK_ID, (
                f"'{word}' should map to a real root, got UNK_ID ({UNK_ID})"
            )
            # Should also not be a special token
            assert root_id > 3, (
                f"'{word}' should have a real root ID > 3, got {root_id}"
            )
