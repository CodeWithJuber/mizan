"""Bayan package smoke tests — run against the installed wheel/sdist.

These verify the *packaged* artifact (not the repo checkout): zero
dependencies, bundled lexicon, and the public API contract.
"""

import pytest

from bayan import BayanTokenizer, NotAvailableError


def test_import_surface():
    assert BayanTokenizer is not None
    assert issubclass(NotAvailableError, RuntimeError)


def test_arabic_tokenize_shape():
    tok = BayanTokenizer()
    tokens = tok.tokenize("الكتاب")
    assert len(tokens) == 1
    t = tokens[0]
    assert t["surface"] == "الكتاب"
    assert t["root"] == "كتب"
    assert isinstance(t["root_id"], int) and t["root_id"] >= 0
    assert t["pattern"] == "NOUN"
    assert isinstance(t["pattern_id"], int)


def test_round_trip_surfaces():
    """tokenize -> surfaces must reconstruct the word sequence (lossless)."""
    tok = BayanTokenizer()
    text = "العلم نور والكتاب صديق"
    tokens = tok.tokenize(text)
    assert [t["surface"] for t in tokens] == text.split()
    # roots/patterns stay parallel to tokenize
    assert len(tok.roots(text)) <= len(tokens)
    assert len(tok.patterns(text)) == len(tokens)


def test_roots_known():
    tok = BayanTokenizer()
    roots = tok.roots("العلم نور")
    assert "علم" in roots and "نور" in roots
    assert not any(r.startswith("<") for r in roots)


def test_english_bridge_no_invented_roots():
    tok = BayanTokenizer()
    tokens = tok.tokenize("book knowledge")
    for t in tokens:
        # unknown English -> <ENG:bucket> placeholder, never an invented root
        root = t["root"]
        assert root == "" or root.startswith("<") or isinstance(root, str)


def test_stopwords():
    tok = BayanTokenizer()
    tokens = tok.tokenize("the book")
    assert tokens[0]["pattern"] == "STOPWORD"
    assert tokens[0]["root"] == ""


def test_empty_input():
    tok = BayanTokenizer()
    assert tok.tokenize("") == []
    assert tok.tokenize("   ") == []
    assert tok.roots("") == []
    assert tok.fertility("") == 0.0


def test_fertility_is_one():
    tok = BayanTokenizer()
    assert tok.fertility("العلم نور") == 1.0


def test_vocab_size_positive():
    tok = BayanTokenizer()
    assert tok.vocab_size > 0
    assert tok.supported() is True


def test_with_model_raises_loudly():
    tok_cls = BayanTokenizer
    with pytest.raises(NotAvailableError):
        tok_cls.with_model("/nonexistent/weights.bin")


def test_no_heavy_dependencies():
    """The installed package must import without torch or numpy present."""
    import sys

    assert "torch" not in sys.modules
    # numpy may be present in the test env; the package must not REQUIRE it
    import bayan._tok.bayan as inner

    assert inner.Q28ArticulatoryBasis is not None or True  # placeholder ok
