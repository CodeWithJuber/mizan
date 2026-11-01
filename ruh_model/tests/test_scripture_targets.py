"""The owner's rule as a tested property: scripture is never a training target.

The Quran (and hadith text) may be an input, a retrieval source or an
evaluation set. These tests build real windows and batches from a tiny
synthetic corpus that quotes an ayah, through the same code the trainers use
(``tokenize_record``, ``RealDataPipeline``, ``RuhCollator``, ``RuhDataset``),
and check that no supervised label falls inside it. Nothing is downloaded.

The oracle never reads the code's own ``scripture_mask``: it finds every
occurrence of the quoted bytes in the token stream itself.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace

import pytest

from ruh_model.data.pipeline import RealDataPipeline
from ruh_model.data.quranic import build_paths, build_tafsir_path, read_morphology
from ruh_model.data.scripture import (
    SCRIPTURE_DOMAINS,
    check_mixing_ratios,
    check_trainable,
    scripture_byte_mask,
)
from ruh_model.data.sequence import tokenize_record
from ruh_model.tokenizer.bayan import BayanTokenizer

# Al-Fatihah 1:1 as a fixture (byte-exactness to an edition is not under test).
AYAH = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
TRANSLATION = "In the name of Allah, the Beneficent, the Merciful."
REFUSED = "never a training target"

TOKENIZER = BayanTokenizer(version=2)
BYTE_START = TOKENIZER.encode("\x00", add_eos=False)[1][0]


def _byte_of(token: int) -> int | None:
    return token - BYTE_START if BYTE_START <= token < BYTE_START + 256 else None


def _positions(tokens: list[int], quotes: list[str]) -> set[int]:
    """Token indices inside any occurrence of any quote, found in the tokens themselves."""
    stream = [_byte_of(token) for token in tokens]
    found = set()
    for quote in quotes:
        needle = list(quote.encode("utf-8"))
        for start in range(len(stream) - len(needle) + 1):
            if stream[start : start + len(needle)] == needle:
                found.update(range(start, start + len(needle)))
    return found


def _locate(tokens: list[int], window: list[int], max_seq_len: int) -> int:
    starts = [
        start
        for start in range(0, len(tokens) - 1, max_seq_len - 1)
        if tokens[start : start + max_seq_len] == window
    ]
    assert len(starts) == 1, "fixture text must make every yielded window unique"
    return starts[0]


# --- The rule itself (no Torch) ---------------------------------------------


def test_scripture_domains_and_default_ratios_hold_no_scripture_weight(monkeypatch):
    monkeypatch.delenv("RUH_DATA_SOURCES", raising=False)
    assert {"quran", "hadith"} == SCRIPTURE_DOMAINS
    ratios = RealDataPipeline(TOKENIZER, 32).ratios
    assert not any(ratios.get(domain) for domain in SCRIPTURE_DOMAINS)


@pytest.mark.parametrize("domain", ["quran", "hadith"])
def test_positive_scripture_weight_is_refused(domain):
    with pytest.raises(ValueError, match=REFUSED):
        check_mixing_ratios({domain: 0.3, "arabic_wiki": 0.7})
    with pytest.raises(ValueError, match=REFUSED):
        RealDataPipeline(TOKENIZER, 32, {domain: 0.3, "arabic_wiki": 0.7})
    check_mixing_ratios({domain: 0.0, "arabic_wiki": 1.0})


def test_canary_and_scripture_records_are_refused_as_training_records():
    words, _ = read_morphology(_morphology(), {"1:1": AYAH})
    canary = build_paths({"1:1": AYAH}, {"1:1": TRANSLATION}, words)["canary"]
    assert canary and all(row["evaluation_only"] for row in canary)
    for row in [*canary, {"domain": "quran", "text": AYAH}, {"domain": "hadith", "text": "x"}]:
        with pytest.raises(ValueError, match=REFUSED):
            check_trainable(row)
        with pytest.raises(ValueError, match=REFUSED):
            list(tokenize_record(row, TOKENIZER, 64))


def test_declared_scripture_must_occur_verbatim():
    with pytest.raises(ValueError, match="verbatim"):
        scripture_byte_mask("commentary only", [AYAH])
    with pytest.raises(ValueError, match="non-empty"):
        scripture_byte_mask("text", [" "])
    with pytest.raises(ValueError, match="list of exact strings"):
        scripture_byte_mask(AYAH, AYAH)


def test_record_that_is_only_a_quotation_yields_no_window():
    assert list(tokenize_record({"text": AYAH, "scripture": [AYAH]}, TOKENIZER, 64)) == []


def test_windowed_record_supervises_every_byte_except_scripture_once():
    """Windows cut through the ayah; the union of targets is everything but the ayah."""
    text = f"Note one: A{AYAH}B. Note two explains it. Note three: C{AYAH}D. End."
    row = {"text": text, "scripture": [AYAH]}
    max_seq_len = 16
    tokens = [root for root, _ in TOKENIZER.encode(text)]
    ayah = _positions(tokens, [AYAH])
    assert len(ayah) == 2 * len(AYAH.encode())

    supervised: list[int] = []
    for window in tokenize_record(row, TOKENIZER, max_seq_len):
        start = _locate(tokens, window["root_ids"], max_seq_len)
        supervised += [start + t for t, on in enumerate(window["target_mask"]) if t and on]
    assert not set(supervised) & ayah
    assert sorted(supervised) == sorted(set(range(1, len(tokens))) - ayah)


def test_input_only_quranic_paths_never_supervise_scripture():
    words, _ = read_morphology(_morphology(), {"1:1": AYAH})
    paths = build_paths({"1:1": AYAH}, {"1:1": TRANSLATION}, words)
    tafsir = build_tafsir_path(
        {"1:1": AYAH},
        [{"verse_id": "1:1", "text": f"The verse {AYAH} opens every surah but one."}],
        {
            "attribution": "Fixture commentator",
            "license": "Fixture licence",
            "license_url": "https://example.org",
            "revision": "v1",
            "sha256": "a" * 64,
            "training_permission": True,
        },
    )
    rows = [*paths["morphology"], *paths["grounded_qa"], *tafsir]
    for row in rows:
        quotes = row["scripture"]
        assert quotes, "every Quran-derived training record declares its scripture"
        (sample,) = tokenize_record(row, TOKENIZER, 4096)
        inside = _positions(sample["root_ids"], quotes)
        targets = {t for t, on in enumerate(sample["target_mask"]) if on}
        assert inside, "the record really quotes scripture"
        assert targets, "the record still has a target"
        assert not targets & inside

    # Morphology supervises QAC labels only: the word's letters are not in the target.
    answer = paths["morphology"][0]["messages"][-1]["content"]
    assert not any("؀" <= char <= "ۿ" for char in answer)
    assert not any({"form", "form_bw"} & set(seg) for seg in json.loads(answer)["segments"])
    # Grounded QA supervises the citation, never the quoted translation.
    qa = paths["grounded_qa"][0]
    (sample,) = tokenize_record(qa, TOKENIZER, 4096)
    supervised = bytes(
        _byte_of(token)
        for t, token in enumerate(sample["root_ids"])
        if sample["target_mask"][t] and _byte_of(token) is not None
    ).decode()
    # The separator space after "assistant:", then (translation masked) the citation.
    assert supervised == "  [Quran 1:1; Pickthall, 1930 translation]"


# --- Batches through the collator (Torch) -----------------------------------


def test_collator_ignores_scripture_tokens_whatever_target_mask_says():
    pytest.importorskip("torch")
    from ruh_model.data.collator import RuhCollator

    sample = {
        "root_ids": [1, 10, 11, 12, 13],
        "pattern_ids": [0] * 5,
        "target_mask": [False, True, True, True, True],
        "scripture_mask": [False, False, True, True, False],
    }
    assert RuhCollator()([sample])["labels"][0].tolist() == [10, 0, 0, 13, 0]
    with pytest.raises(ValueError, match="scripture_mask"):
        RuhCollator()([dict(sample, scripture_mask=[True])])


def test_windowed_batches_never_label_scripture():
    pytest.importorskip("torch")
    from ruh_model.data.collator import RuhCollator

    text = f"Opening: A{AYAH}B, then a gloss. Again: C{AYAH}D. Done."
    max_seq_len = 16
    tokens = [root for root, _ in TOKENIZER.encode(text)]
    ayah = _positions(tokens, [AYAH])
    windows = list(tokenize_record({"text": text, "scripture": [AYAH]}, TOKENIZER, max_seq_len))
    # Strip the code's own scripture_mask: the collated labels must hold on target_mask alone,
    # and the collator must also hold alone (scripture_mask with every target switched on).
    plain = [{k: v for k, v in w.items() if k != "scripture_mask"} for w in windows]
    forced = [dict(w, target_mask=[False] + [True] * (len(w["root_ids"]) - 1)) for w in windows]
    for samples in (plain, forced):
        labels = RuhCollator()(samples)["labels"].tolist()
        supervised = set()
        for window, row in zip(samples, labels, strict=True):
            start = _locate(tokens, window["root_ids"], max_seq_len)
            supervised |= {start + t + 1 for t, label in enumerate(row) if label != 0}
        assert supervised, "the batch still has targets"
        assert not supervised & ayah


def test_pipeline_epoch_never_labels_an_ayah():
    """A full epoch through RealDataPipeline.get_dataloader and RuhCollator."""
    pytest.importorskip("torch")
    rows = [
        {"text": f"The opening of the Book reads {AYAH} and a gloss follows.", "scripture": [AYAH]},
        {"text": "An ordinary sentence with no quotation."},
        {"text": AYAH, "scripture": [AYAH]},
        {"text": f"Twice: {AYAH} / {AYAH} end.", "scripture": [AYAH]},
        {"text": f"Translated: {TRANSLATION} (Pickthall).", "scripture": [TRANSLATION]},
    ]
    pipeline = RealDataPipeline(TOKENIZER, 512, sources={"corpus": rows})
    quoted, ordinary = 0, 0
    for batch in pipeline.get_dataloader(len(rows), 2):
        for tokens, labels in zip(
            batch["root_ids"].tolist(), batch["labels"].tolist(), strict=True
        ):
            inside = _positions(tokens, [AYAH, TRANSLATION])
            targets = {t + 1 for t, label in enumerate(labels) if label != 0}
            assert not targets & inside
            assert targets, "every yielded row keeps a target"
            text_bytes = sum(_byte_of(token) is not None for token in tokens)
            # Every byte outside scripture plus the end of text is supervised, nothing else.
            assert len(targets) == text_bytes + 1 - len(inside)
            quoted += bool(inside)
            ordinary += not inside
    assert quoted == 3 and ordinary == 1  # the quotation-only row yields nothing


def test_jsonl_dataset_refuses_scripture_records_and_masks_declared_spans(tmp_path):
    pytest.importorskip("torch")
    from ruh_model.data.dataset import RuhDataset

    for row in ({"domain": "quran", "text": AYAH}, {"text": AYAH, "evaluation_only": True}):
        path = tmp_path / "refused.jsonl"
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=REFUSED):
            RuhDataset(str(path), TOKENIZER, 512)

    path = tmp_path / "quoting.jsonl"
    row = {"text": f"Gloss on {AYAH} here.", "scripture": [AYAH]}
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    (sample,) = RuhDataset(str(path), TOKENIZER, 512)
    inside = _positions(sample["root_ids"], [AYAH])
    assert inside and not inside & {t for t, on in enumerate(sample["target_mask"]) if on}


# --- The training CLI (Torch) ------------------------------------------------


def test_train_full_defaults_hold_no_scripture_weight(monkeypatch):
    pytest.importorskip("torch")
    from ruh_model.train_full import _DEFAULT_RATIOS, _parse_args

    assert _DEFAULT_RATIOS["quran"] == 0 and _DEFAULT_RATIOS["hadith"] == 0
    monkeypatch.setattr(sys, "argv", ["train_full"])
    args = _parse_args()
    assert args.quran_weight == 0 and args.hadith_weight == 0


@pytest.mark.parametrize("flag", ["--quran-weight", "--hadith-weight"])
def test_train_full_refuses_positive_scripture_weight(monkeypatch, capsys, flag):
    pytest.importorskip("torch")
    from ruh_model.train_full import _build_mixing_ratios, _parse_args

    monkeypatch.setattr(sys, "argv", ["train_full", flag, "0.3"])
    with pytest.raises(SystemExit) as raised:
        _parse_args()
    assert raised.value.code == 2
    assert REFUSED in capsys.readouterr().err

    weights = dict(quran_weight=0.0, hadith_weight=0.0, wiki_weight=1.0)
    weights[flag.removeprefix("--").replace("-", "_")] = 0.3
    with pytest.raises(ValueError, match=REFUSED):
        _build_mixing_ratios(Namespace(**weights, opus_weight=0.0, morpho_weight=0.0))


def _morphology() -> bytes:
    return (
        b"# Copyright (C) 2011 Kais Dukes\n# CHANGING IT IS NOT ALLOWED\n"
        b"LOCATION\tFORM\tTAG\tFEATURES\n"
        b"(1:1:1:1)\tbi\tP\tPREFIX|bi+\n"
        b"(1:1:1:2)\tsomi\tN\tSTEM|POS:N|LEM:{som|ROOT:smw|M|GEN\n"
    )
