"""Default Quran selection, explicit source permission and lossless supervision."""

from __future__ import annotations

import pytest

from ruh_model.data.pipeline import DEFAULT_SOURCES, RealDataPipeline
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.root_vocab import EOS_ID


def _source():
    return {
        "path": "explicit-test-corpus",
        "revision": "a" * 40,
        "lang": "ar",
        "license": "Test fixture permission",
        "attribution": "Test fixture",
        "training_permission": True,
        "edition": "Fixture edition",
        "verse_columns": ["surah", "ayah"],
    }


def _pipeline(rows, source=None):
    with pytest.warns(UserWarning, match="Explicit custom quran"):
        return RealDataPipeline(
            BayanTokenizer(version=2),
            32,
            sources={"quran": source or _source()},
            loader=lambda *args, **kwargs: rows,
        )


def test_defaults_use_verified_text_and_no_automatic_hadith():
    assert DEFAULT_SOURCES["quran"]["kind"] == "verified_quran"
    assert "files" not in DEFAULT_SOURCES["quran"]
    assert "hadith" not in DEFAULT_SOURCES


def test_unattributed_or_unlicensed_custom_religious_source_refused():
    for domain in ("quran", "hadith"):
        with pytest.raises(ValueError, match="permission"):
            RealDataPipeline(BayanTokenizer(version=2), 32, sources={domain: {"path": "unknown"}})


def test_legacy_root_tokenizer_cannot_discard_quran_surface():
    with pytest.raises(ValueError, match="lossless"):
        RealDataPipeline(BayanTokenizer(version=1), 32, mixing_ratios={"quran": 1})


def test_explicit_reciter_rows_are_deduplicated_with_provenance():
    rows = [{"surah": 1, "ayah": 1, "text": "بِسْمِ"}] * 2
    result = list(_pipeline(rows).stream(10))
    assert len(result) == 1
    assert result[0]["verse_id"] == "1:1"
    assert result[0]["source_provenance"]["attribution"] == "Test fixture"
    assert result[0]["text"] == "بِسْمِ"


def test_conflicting_text_for_one_verse_is_rejected():
    rows = [{"surah": 1, "ayah": 1, "text": "الأصل"}, {"surah": 1, "ayah": 1, "text": "تغيير"}]
    with pytest.raises(ValueError, match="Conflicting"):
        list(_pipeline(rows).stream(10))


def test_custom_quran_cannot_omit_or_forge_verse_identity():
    with pytest.raises(KeyError):
        list(_pipeline([{"text": "نص"}]).stream(1))
    with pytest.raises(ValueError, match="identifier"):
        list(_pipeline([{"verse_id": "1:999", "text": "نص"}]).stream(1))


def test_long_verse_targets_all_bytes_once_without_manufactured_eos():
    text = "لَا تَخَفْ " * 50
    pipeline = _pipeline([{"surah": 1, "ayah": 1, "text": text}])
    batches = list(pipeline.get_dataloader(1, 1))
    targets = [int(token) for batch in batches for token in batch["labels"][0] if token != 0]
    assert pipeline.tokenizer.decode([(token, 0) for token in targets]) == text
    assert targets.count(EOS_ID) == 1
    assert len(batches) > 1


def test_train_full_defaults_hadith_weight_to_zero(monkeypatch):
    import sys

    from ruh_model.train_full import _parse_args

    monkeypatch.setattr(sys, "argv", ["train_full"])
    args = _parse_args()
    assert args.hadith_weight == 0
    assert args.quran_weight == 0.3
