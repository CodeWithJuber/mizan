"""Meaningful text-integrity, annotation and split-leakage regressions."""

from __future__ import annotations

import json

import pytest

from ruh_model.data.quranic import (
    CHAPTER_LENGTHS,
    SOURCES,
    build_paths,
    build_tafsir_path,
    compare_editions,
    fetch_sources,
    from_buckwalter,
    read_morphology,
    read_verses,
    surah_groups,
)
from ruh_model.data.quranic_evaluation import quotation_score, score_record
from ruh_model.data.sequence import split_records, tokenize_record
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.root_vocab import EOS_ID


def test_numbering_covers_complete_hafs_quran():
    assert len(CHAPTER_LENGTHS) == 114
    assert sum(CHAPTER_LENGTHS) == 6236
    data = {
        str(s): [{"chapter": s, "verse": v, "text": "نص"} for v in range(1, n + 1)]
        for s, n in enumerate(CHAPTER_LENGTHS, 1)
    }
    assert len(read_verses(json.dumps(data).encode())) == 6236
    data["114"].pop()
    with pytest.raises(ValueError, match="6,236"):
        read_verses(json.dumps(data).encode())


@pytest.mark.parametrize(
    "rows",
    [
        [{"chapter": 1, "verse": 1, "text": "x"}] * 2,
        [{"chapter": 1, "verse": 8, "text": "x"}],
        [{"chapter": 2, "verse": 1, "text": "x"}],
        [{"chapter": 1, "verse": 1, "text": "\ufffd"}],
    ],
)
def test_bad_verse_ids_and_encoding_are_rejected(rows):
    with pytest.raises(ValueError):
        read_verses(json.dumps({"1": rows}).encode(), complete=False)


def test_cached_source_is_always_hash_checked(tmp_path):
    (tmp_path / "tanzil.source").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="hash mismatch"):
        fetch_sources(tmp_path)


def test_every_source_is_pinned_and_attributed():
    for source in SOURCES.values():
        assert len(source["sha256"]) == 64
        assert len(source["revision"]) == 40
    assert "verbatim" in SOURCES["tanzil"]["license"]
    assert "GPL" in SOURCES["qac"]["license"]


def test_comparison_never_changes_training_text():
    original = {"1:1": "بِسْمِ ٱللَّهِ", "2:1": "بِسْمِ ٱللَّهِ الٓمٓ"}
    before = dict(original)
    report = compare_editions(original, {"1:1": "بِسۡمِ ٱللَّهِ", "2:1": "الٓمٓ"})
    assert report["comparison_fold_agreement"] == 2
    assert original == before
    assert report["training_text_modified"] is False


def test_buckwalter_preserves_hamza_diacritics_and_unknown_fails():
    assert from_buckwalter("laA") == "لَا"
    assert from_buckwalter("^#") == "ٓٔ"
    with pytest.raises(ValueError, match="Unknown"):
        from_buckwalter("☃")


def _morphology(extra=""):
    return (
        "# Copyright (C) 2011 Kais Dukes\n# CHANGING IT IS NOT ALLOWED\n"
        "LOCATION\tFORM\tTAG\tFEATURES\n"
        "(1:1:1:1)\tbi\tP\tPREFIX|bi+\n"
        "(1:1:1:2)\tsomi\tN\tSTEM|POS:N|LEM:{som|ROOT:smw|M|GEN\n" + extra
    ).encode()


def test_morphology_keeps_original_labels_and_segment_locations():
    words, notice = read_morphology(_morphology(), {"1:1": "بِسْمِ"})
    assert "Copyright" in notice
    assert words[0]["form"] == "بِسْمِ"
    assert words[0]["segments"][0]["root_bw"] is None
    assert words[0]["segments"][1]["root_bw"] == "smw"
    assert words[0]["segments"][1]["features"] == "STEM|POS:N|LEM:{som|ROOT:smw|M|GEN"


def test_duplicate_qac_location_and_missing_word_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        read_morphology(_morphology("(1:1:1:1)\tbi\tP\tPREFIX|bi+\n"), {"1:1": "بِسْمِ"})
    with pytest.raises(ValueError, match="word order"):
        read_morphology(_morphology("(1:1:3:1)\tbi\tP\tPREFIX|bi+\n"), {"1:1": "بِسْمِ"})


def test_whole_surah_and_repeated_verse_groups_do_not_leak():
    verses = {f"{s}:1": f"سورة {s}" for s in range(1, 115)}
    verses["3:1"] = verses["2:1"]
    verses["2:2"] = "نص آخر"
    groups = surah_groups(verses)
    assert groups["2:1"] == groups["3:1"] == groups["2:2"]
    rows = [
        {"text": text, "verse_id": identity, "group_id": groups[identity]}
        for identity, text in verses.items()
    ]
    train, validation = split_records(rows)
    train_surahs = {row["verse_id"].split(":")[0] for row in train}
    validation_surahs = {row["verse_id"].split(":")[0] for row in validation}
    assert not train_surahs & validation_surahs
    assert not {row["group_id"] for row in train} & {row["group_id"] for row in validation}


def test_three_paths_preserve_original_and_distinguish_translation():
    words, _ = read_morphology(_morphology(), {"1:1": "بِسْمِ"})
    paths = build_paths({"1:1": "بِسْمِ"}, {"1:1": "In the name"}, words)
    assert paths["continuation"][0]["text"] == "بِسْمِ"
    qa = paths["grounded_qa"][0]
    assert "Pickthall" in qa["messages"][-1]["content"]
    assert "not original Quran" in qa["messages"][0]["content"]
    assert paths["morphology"][0]["group_id"] == qa["group_id"]
    assert "QAC 0.4" in paths["morphology"][0]["messages"][-1]["content"]


def test_v2_windows_preserve_every_quranic_byte_and_only_final_eos():
    text = "لَا تَخَفْ وَلا تَحْزَنْ " * 40
    tokenizer = BayanTokenizer(version=2)
    windows = list(tokenize_record({"text": text}, tokenizer, max_seq_len=32))
    tokens = windows[0]["root_ids"] + [
        token for window in windows[1:] for token in window["root_ids"][1:]
    ]
    assert tokenizer.decode([(token, 0) for token in tokens]) == text
    assert tokens.count(EOS_ID) == 1


def test_unlicensed_or_unattributed_tafsir_is_rejected():
    with pytest.raises(ValueError, match="attribution"):
        build_tafsir_path({"1:1": "نص"}, [{"verse_id": "1:1", "text": "شرح"}], {})
    source = {
        "attribution": "Author",
        "license": "Licence",
        "license_url": "https://example.org",
        "revision": "v1",
        "sha256": "a" * 64,
    }
    with pytest.raises(ValueError, match="permission"):
        build_tafsir_path({"1:1": "نص"}, [{"verse_id": "1:1", "text": "شرح"}], source)


def test_evaluation_detects_lost_diacritics_and_negation():
    expected = "لَا تَخَفْ"
    exact = quotation_score(expected, expected)
    assert exact["exact_match"] and exact["negation_tokens_exact"]
    incorrect = quotation_score(expected, "تخف")
    assert not incorrect["exact_match"]
    assert not incorrect["diacritic_sequence_exact"]
    assert not incorrect["negation_tokens_exact"]


def test_grounded_score_rejects_wrong_verse_citation():
    row = {
        "task": "grounded_translation",
        "verse_id": "1:1",
        "attribution": "Pickthall",
        "expected": "Text [Quran 1:1; Pickthall]",
        "generated": "Text [Quran 1:2; Pickthall]",
    }
    assert score_record(row)["correct_citation"] is False
