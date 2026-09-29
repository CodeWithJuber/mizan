"""Tests for dialect -> root normalization (use case #6).

Torch-free: ``ruh_model/__init__.py`` needs torch (absent in CI), so the
module under test is loaded directly by file path. Run with
``--noconftest`` to skip the pre-existing
``ruh_model/tests/conftest.py`` (imports torch via ``ruh_model``).

BETA fixtures: expected roots come from the rule-based analyzer's
documented behaviour, NOT from a measured gold standard. The point of
these tests is contract stability (schema, foreign bucket, review
flags), not linguistic certification.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_KEYS = {
    "surface",
    "dialect",
    "root",
    "pattern",
    "confidence",
    "foreign",
    "needs_review",
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_dialect_normalize", REPO_ROOT / "ruh_model" / "dialect" / "normalize.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def normalize_mod() -> ModuleType:
    return _load()


@pytest.fixture(scope="module")
def normalize(normalize_mod: ModuleType):  # type: ignore[no-untyped-def]
    return normalize_mod.normalize


class TestSchema:
    def test_exact_keys(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("بيكتب", dialect_hint="egyptian")
        assert set(result.keys()) == EXPECTED_KEYS

    def test_surface_echo(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("  بيكتب  ", dialect_hint="egyptian")
        assert result["surface"] == "بيكتب"


class TestEgyptian:
    @pytest.mark.parametrize(
        ("word", "root"),
        [
            ("مايعرفش", "عرف"),  # ma-...-sh negation: "he doesn't know"
            ("هيكتب", "كتب"),  # ha- future: "he will write"
            ("بيكتب", "كتب"),  # bi- progressive: "he writes"
        ],
    )
    def test_affixes(self, normalize, word: str, root: str) -> None:  # type: ignore[no-untyped-def]
        result = normalize(word, dialect_hint="egyptian")
        assert result["dialect"] == "egyptian"
        assert result["root"] == root
        assert result["foreign"] is False
        assert result["needs_review"] is False


class TestLevantine:
    @pytest.mark.parametrize(
        ("word", "root"),
        [
            ("عميكتب", "كتب"),  # 'am- progressive: "he is writing"
            ("مابيعرف", "عرف"),  # ma- negation: "he doesn't know"
            ("مابيعرفش", "عرف"),  # ma-...-sh negation
        ],
    )
    def test_affixes(self, normalize, word: str, root: str) -> None:  # type: ignore[no-untyped-def]
        result = normalize(word, dialect_hint="levantine")
        assert result["dialect"] == "levantine"
        assert result["root"] == root
        assert result["foreign"] is False


class TestGulf:
    @pytest.mark.parametrize(
        ("word", "root"),
        [
            ("مايعرف", "عرف"),  # ma- negation: "he doesn't know"
            ("بايكتب", "كتب"),  # ba- future: "he will write"
        ],
    )
    def test_affixes(self, normalize, word: str, root: str) -> None:  # type: ignore[no-untyped-def]
        result = normalize(word, dialect_hint="gulf")
        assert result["dialect"] == "gulf"
        assert result["root"] == root

    def test_ga_prefix_excluded(self, normalize_mod: ModuleType) -> None:
        """JEV 2026-09-29 (exclude, 1.00): no unverified 'ga-' mapping."""
        gulf_prefixes = [
            surface
            for surface, _tag in normalize_mod._REGION_TABLES["gulf"]["prefixes"]  # noqa: SLF001
        ]
        assert "غ" not in gulf_prefixes
        assert not any(p.startswith("غ") for p in gulf_prefixes)


class TestMaghrebi:
    def test_ka_prefix(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("كايكتب", dialect_hint="maghrebi")
        assert result["dialect"] == "maghrebi"
        assert result["root"] == "كتب"

    def test_ma_sh_negation(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("مايعرفش", dialect_hint="maghrebi")
        assert result["root"] == "عرف"


class TestForeignBucket:
    """Non-Semitic loans must NEVER get a hallucinated root."""

    def test_french_loan_arabic_script(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("طوموبيل", dialect_hint="maghrebi")
        assert result["foreign"] is True
        assert result["root"] is None
        assert result["needs_review"] is False

    def test_latin_script_is_foreign(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("hello")
        assert result["foreign"] is True
        assert result["root"] is None

    @pytest.mark.parametrize("word", ["طوموبيل", "تيليفون", "hello", "merci"])
    def test_no_root_hallucinated(self, normalize, word: str) -> None:  # type: ignore[no-untyped-def]
        result = normalize(word)
        assert result["foreign"] is True
        assert result["root"] is None


class TestUnknown:
    def test_empty_word_needs_review(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("")
        assert result["needs_review"] is True
        assert result["confidence"] == pytest.approx(0.15)

    def test_mixed_script_needs_review(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("كتابbook")
        assert result["needs_review"] is True
        assert result["foreign"] is False
        assert result["root"] == ""


class TestAutoDetect:
    def test_egyptian_negation_detected(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("مايعرفش")
        assert result["dialect"] == "egyptian"
        assert result["root"] == "عرف"

    def test_maghrebi_ka_detected(self, normalize) -> None:  # type: ignore[no-untyped-def]
        result = normalize("كايكتب")
        assert result["dialect"] == "maghrebi"
        assert result["root"] == "كتب"

    def test_msa_word_not_misattributed(self, normalize) -> None:  # type: ignore[no-untyped-def]
        # "كتاب" merely starts with maghrebi "ka-"; without a hint the
        # module must not claim a dialect.
        result = normalize("كتاب")
        assert result["dialect"] == "msa"


class TestInvalidHint:
    def test_unknown_hint_raises(self, normalize) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ValueError, match="Unknown dialect_hint"):
            normalize("بيكتب", dialect_hint="klingon")
