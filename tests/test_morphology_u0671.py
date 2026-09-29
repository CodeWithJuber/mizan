"""Regression tests: U+0671 (alef wasla) Quranic-orthography handling.

Quranic spelling writes word-initial alef as U+0671 SUPERSCRIPT ALEF (ٱ) —
the definite article (ٱلـ for الـ, e.g. ٱلناس for الناس) and other initial
alefs (ٱقْرَأْ for اقرأ, وَٱلشَّمْسِ for والشمس). The analyzer normalizes ٱ
to plain alef before affix stripping, so Quranic spellings must behave
exactly like their standard-orthography twins.

Contract under test:
1. Parity: analyze(quranic_word) == analyze(standard_twin) for every case.
2. No-op: words without U+0671 are byte-identical through the old and new
   normalization pipelines (previously-correct analyses cannot regress).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_morphology():
    """Import the analyzer, torch-free (bypasses ruh_model/__init__)."""
    try:
        from ruh_model.tokenizer import morphology

        return morphology
    except ImportError:
        pass
    here = Path(__file__).resolve()
    for parent in (here.parent.parent, *here.parents):
        cand = parent / "ruh_model" / "tokenizer" / "morphology.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("ruh_morphology_u0671", str(cand))
            mod = importlib.util.module_from_spec(spec)
            sys.modules["ruh_morphology_u0671"] = mod
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("ruh_model/tokenizer/morphology.py not found")


morphology = _load_morphology()
ArabicMorphAnalyzer = morphology.ArabicMorphAnalyzer

# (Quranic spelling, expected root) — expected root is whatever the
# standard-orthography twin yields; the assertion that matters is parity.
QURANIC_CASES: list[tuple[str, str]] = [
    ("ٱلناس", "ناس"),  # definite article, bare
    ("ٱلْحَمْدُ", "حمد"),  # definite article with diacritics
    ("وَٱلشَّمْسِ", "شمس"),  # conjunction + article
    ("ٱقْرَأْ", "اقر"),  # imperative, hamzat al-wasl (not an article)
    ("وَٱلْأَرْضِ", "ارض"),  # conjunction + article + hamza
    ("ٱلْحَقُّ", "حق"),
    ("ٱلْعَلِيمُ", "علم"),
    ("ٱهْدِنَا", "اهد"),  # imperative + pronoun suffix
    ("بِٱلْحَقِّ", "حق"),  # preposition + article
    ("ٱلصِّرَٰطَ", "صرط"),
    ("ٱلْمُسْتَقِيمَ", "مست"),
    ("وَٱذْكُرُوا", "ذكر"),  # conjunction + imperative
    ("ٱلَّذِي", "ذي"),  # relative pronoun
    ("ٱلْجِنَّةِ", "جن"),  # article + ta-marbuta
    ("ٱلنَّبَإِ", "نبا"),  # article + hamza-final root
    ("ٱلْكِتَٰبَ", "كتب"),
    ("فَٱسْتَغْفِرْهُ", "ستغ"),  # conjunction + derived verb + suffix
    ("ٱلرَّحْمَٰنِ", "رحم"),
]


@pytest.fixture(scope="module")
def analyzer() -> ArabicMorphAnalyzer:
    return ArabicMorphAnalyzer()


@pytest.mark.parametrize("quranic,expected_root", QURANIC_CASES)
def test_quranic_orthography_root(
    analyzer: ArabicMorphAnalyzer, quranic: str, expected_root: str
) -> None:
    """Quranic ٱ-spellings yield the expected root."""
    assert analyzer.extract_root(quranic) == expected_root


@pytest.mark.parametrize("quranic,expected_root", QURANIC_CASES)
def test_quranic_standard_parity(
    analyzer: ArabicMorphAnalyzer, quranic: str, expected_root: str
) -> None:
    """Quranic spelling behaves exactly like its standard twin."""
    twin = quranic.replace("\u0671", "\u0627")
    assert analyzer.extract_root(quranic) == analyzer.extract_root(twin)
    assert analyzer.analyze(quranic) == analyzer.analyze(twin)


def test_wasla_normalization_unit() -> None:
    assert morphology._normalize_wasla("ٱلناس") == "الناس"
    assert morphology._normalize_wasla("وَبِٱلْحَقِّ") == "وَبِالْحَقِّ"
    # No-op for text without U+0671
    assert morphology._normalize_wasla("الناس") == "الناس"
    assert morphology._normalize_wasla("hello") == "hello"
    assert morphology._normalize_wasla("") == ""


def test_pipeline_noop_without_wasla() -> None:
    """Old vs new normalization pipeline: byte-identical without U+0671."""
    words = [
        "الكتاب",
        "والشمس",
        "يستغفرون",
        "مدرسة",
        "بسم الله",
        "فاستغفره",
    ]
    for word in words:
        old = morphology._normalize_hamza(morphology._strip_tashkeel(word))
        assert morphology._clean_word(word) == old


def test_gold_u0671_parity() -> None:
    """Every U+0671 word in the QAC gold behaves like its standard twin."""
    here = Path(__file__).resolve()
    gold = None
    for parent in (here.parent.parent, *here.parents):
        cand = parent / "ruh_model" / "benchmarks" / "data" / "morph_gold_qac_test.tsv"
        if cand.is_file():
            gold = cand
            break
    if gold is None:
        pytest.skip("gold file not present in this tree")
    analyzer = ArabicMorphAnalyzer()
    n = 0
    for line in gold.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        word = line.split("\t")[0]
        if "\u0671" not in word:
            continue
        n += 1
        twin = word.replace("\u0671", "\u0627")
        assert analyzer.analyze(word) == analyzer.analyze(twin), word
    assert n == 40, f"expected 40 U+0671 gold words, found {n}"
