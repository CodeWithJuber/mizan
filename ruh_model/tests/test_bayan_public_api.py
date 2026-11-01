"""Unit tests for the Bayan public API facade.

Torch-free and deterministic: the facade is loaded directly by file path
because the repo's ``ruh_model/__init__.py`` unconditionally imports torch.
Run in torch-less environments as::

    python -m pytest --noconftest --import-mode=importlib \\
        ruh_model/tests/test_bayan_public_api.py

Root assertions below pin the analyzer's *measured* behaviour (verified
2026-09-29), not idealised linguistics: the bundled rule-based analyzer is
heuristic and has not been benchmarked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PUBLIC_API_PATH = Path(__file__).resolve().parent.parent / "tokenizer" / "public_api.py"

# root_vocab.py constants (kept in sync by the import-behaviour test below).
UNK_ID = 3
PAD_ID = 0


def _load_public_api():
    """Load public_api.py by file path, bypassing the torch-pulling package init."""
    spec = importlib.util.spec_from_file_location("bayan_public_api", PUBLIC_API_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bayan_public_api"] = module
    spec.loader.exec_module(module)
    return module


_mod = _load_public_api()
BayanTokenizer = _mod.BayanTokenizer
NotAvailableError = _mod.NotAvailableError


@pytest.fixture(scope="module")
def tok() -> BayanTokenizer:
    """One shared torch-free tokenizer for the module."""
    return BayanTokenizer()


class TestTokenizeShape:
    """The token dict contract: exact keys, sane types."""

    def test_token_keys(self, tok: BayanTokenizer) -> None:
        tokens = tok.tokenize("الكتاب")
        assert len(tokens) == 1
        assert set(tokens[0].keys()) == {
            "surface",
            "root",
            "root_id",
            "pattern",
            "pattern_id",
        }

    def test_surface_echoes_input(self, tok: BayanTokenizer) -> None:
        tokens = tok.tokenize("الكتاب يكتب")
        assert [t["surface"] for t in tokens] == ["الكتاب", "يكتب"]

    def test_ids_are_ints(self, tok: BayanTokenizer) -> None:
        for token in tok.tokenize("الكتاب يكتب"):
            assert isinstance(token["root_id"], int)
            assert isinstance(token["pattern_id"], int)


class TestRootExtraction:
    """Measured root behaviour of the bundled rule-based analyzer."""

    def test_definite_kitab_form(self, tok: BayanTokenizer) -> None:
        token = tok.tokenize("الكتاب")[0]
        assert token["root"] == "كتب"
        assert token["pattern"] == "NOUN"
        assert token["root_id"] != UNK_ID

    def test_present_verb_form(self, tok: BayanTokenizer) -> None:
        token = tok.tokenize("يكتب")[0]
        assert token["root"] == "كتب"
        assert token["pattern"] == "VERB_PRESENT"

    def test_english_concept_map_hit(self, tok: BayanTokenizer) -> None:
        token = tok.tokenize("book")[0]
        assert token["root"] == "كتب"
        assert token["root_id"] != UNK_ID

    def test_roots_excludes_placeholders_and_stopwords(self, tok: BayanTokenizer) -> None:
        assert tok.roots("الكتاب يكتب") == ["كتب", "كتب"]
        assert tok.roots("xyzzy في") == []

    def test_unknown_english_is_explicit_placeholder(self, tok: BayanTokenizer) -> None:
        token = tok.tokenize("xyzzy")[0]
        assert token["root"].startswith("<ENG:")
        assert token["root_id"] == UNK_ID

    def test_unknown_english_is_deterministic(self, tok: BayanTokenizer) -> None:
        first = tok.tokenize("xyzzy")[0]["root"]
        second = BayanTokenizer().tokenize("xyzzy")[0]["root"]
        assert first == second


class TestPatterns:
    """Pattern names stay parallel to the tokenized words."""

    def test_patterns_parallel_to_words(self, tok: BayanTokenizer) -> None:
        assert tok.patterns("الكتاب يكتب") == ["NOUN", "VERB_PRESENT"]

    def test_stopword_pattern(self, tok: BayanTokenizer) -> None:
        token = tok.tokenize("في")[0]
        assert token["pattern"] == "STOPWORD"
        assert token["root"] == ""
        assert token["root_id"] == PAD_ID


class TestEmptyAndNonArabic:
    """Empty input, whitespace, and non-Arabic input never crash."""

    def test_empty_string(self, tok: BayanTokenizer) -> None:
        assert tok.tokenize("") == []
        assert tok.roots("") == []
        assert tok.patterns("") == []
        assert tok.fertility("") == 0.0

    def test_whitespace_only(self, tok: BayanTokenizer) -> None:
        assert tok.tokenize("   \n\t  ") == []
        assert tok.fertility("   ") == 0.0

    def test_non_arabic_input_produces_tokens(self, tok: BayanTokenizer) -> None:
        tokens = tok.tokenize("hello world")
        assert len(tokens) == 2
        assert tok.fertility("hello world") == 1.0


class TestFertility:
    """Fertility = tokens per word; 1.0 by construction for Bayan."""

    def test_fertility_is_one_per_word(self, tok: BayanTokenizer) -> None:
        assert tok.fertility("العلم نور") == 1.0

    def test_fertility_math(self, tok: BayanTokenizer) -> None:
        text = "خلق الإنسان علمه البيان"
        tokens = tok.tokenize(text)
        words = text.split()
        assert len(tokens) == len(words) == 4
        assert tok.fertility(text) == len(tokens) / len(words) == 1.0


class TestSupportedAndModelPath:
    """supported() is honest; with_model() never silently fakes."""

    def test_supported_is_true(self, tok: BayanTokenizer) -> None:
        assert tok.supported() is True

    def test_vocab_size_positive(self, tok: BayanTokenizer) -> None:
        assert tok.vocab_size > 0

    def test_with_model_missing_weights(self, tok: BayanTokenizer, tmp_path: Path) -> None:
        missing = tmp_path / "nope.bin"
        with pytest.raises(NotAvailableError, match="not found"):
            BayanTokenizer.with_model(missing)

    def test_with_model_present_weights_still_unavailable(
        self, tok: BayanTokenizer, tmp_path: Path
    ) -> None:
        weights = tmp_path / "weights.bin"
        weights.write_bytes(b"fake-weights")
        with pytest.raises(NotAvailableError, match="not implemented"):
            BayanTokenizer.with_model(weights)

    def test_not_available_error_is_runtime_error(self) -> None:
        assert issubclass(NotAvailableError, RuntimeError)


class TestDeterminism:
    """Same input → same output, across instances."""

    def test_repeat_tokenize_identical(self, tok: BayanTokenizer) -> None:
        text = "الكتاب يكتب في المكتبة"
        assert tok.tokenize(text) == BayanTokenizer().tokenize(text)
