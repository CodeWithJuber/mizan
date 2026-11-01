"""Scripture sources are refused as training domains, whatever permission they claim."""

from __future__ import annotations

import pytest

from ruh_model.data.pipeline import DEFAULT_SOURCES, RealDataPipeline
from ruh_model.data.scripture import is_scripture_source
from ruh_model.tokenizer.bayan import BayanTokenizer


def _permitted_source(**extra):
    # Every field the removed exemption asked for, including training_permission.
    return {
        "path": "explicit-test-corpus",
        "revision": "a" * 40,
        "lang": "ar",
        "license": "Test fixture permission",
        "attribution": "Test fixture",
        "training_permission": True,
        "edition": "Fixture edition",
        "verse_columns": ["surah", "ayah"],
        **extra,
    }


def test_defaults_hold_no_scripture_source():
    assert set(DEFAULT_SOURCES) == {"arabic_wiki"}
    assert not any(is_scripture_source(domain, spec) for domain, spec in DEFAULT_SOURCES.items())


@pytest.mark.parametrize("domain", ["quran", "hadith"])
@pytest.mark.parametrize("version", [1, 2])
def test_scripture_domain_refused_even_with_explicit_permission(domain, version):
    with pytest.raises(ValueError, match="never a training target"):
        RealDataPipeline(
            BayanTokenizer(version=version),
            32,
            sources={domain: _permitted_source()},
            loader=lambda *args, **kwargs: [],
        )


@pytest.mark.parametrize(
    "spec",
    [
        {"kind": "verified_quran", "path": "Tanzil/Uthmani-Hafs", "revision": "a" * 40},
        _permitted_source(),
    ],
)
def test_scripture_source_under_another_name_is_refused(spec):
    with pytest.raises(ValueError, match="never a training target"):
        RealDataPipeline(BayanTokenizer(version=2), 32, sources={"tanzil": spec})


def test_configured_quran_domain_with_default_weight_is_refused():
    # Ratios default to 1.0 for every configured domain, so this fails loudly.
    with pytest.raises(ValueError, match="never a training target"):
        RealDataPipeline(
            BayanTokenizer(version=2),
            32,
            sources={"quran": [{"text": "x"}], "corpus": [{"text": "y"}]},
        )


def test_zero_scripture_weight_is_allowed_and_never_streamed():
    pipeline = RealDataPipeline(
        BayanTokenizer(version=2),
        32,
        {"quran": 0.0, "corpus": 1.0},
        sources={"quran": [{"text": "x"}], "corpus": [{"text": "ordinary"}]},
    )
    assert [row["domain"] for row in pipeline.stream(3)] == ["corpus"]


def test_evaluation_only_row_in_a_general_corpus_is_refused():
    pipeline = RealDataPipeline(
        BayanTokenizer(version=2),
        32,
        sources={"corpus": [{"text": "x", "evaluation_only": True, "task": "canary"}]},
    )
    with pytest.raises(ValueError, match="evaluation-only"):
        list(pipeline.stream(1))
