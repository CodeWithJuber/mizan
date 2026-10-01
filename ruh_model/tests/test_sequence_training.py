"""Regression coverage for the actual lossless sentence/dialogue training path."""

import math

import pytest
import torch

from ruh_model.config import RuhConfig
from ruh_model.data.chat_sources import conversation_pairs
from ruh_model.data.collator import RuhCollator
from ruh_model.data.sequence import split_records, tokenize_record
from ruh_model.model import RuhModel
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.train_sequence import run_training


def test_windows_preserve_all_bytes_and_terminal_eos():
    tokenizer = BayanTokenizer(version=2)
    text = "لا يوجد علم بلا عمل. not knowledge is different from very knowledge."
    windows = list(tokenize_record({"text": text}, tokenizer, 13))
    reconstructed = windows[0]["root_ids"] + [
        token for window in windows[1:] for token in window["root_ids"][1:]
    ]
    assert reconstructed == [root for root, _ in tokenizer.encode(text)]
    assert sum(root == 2 for root in reconstructed) == 1
    assert tokenizer.decode([(root, 0) for root in reconstructed]) == text


def test_dialogue_labels_only_predict_assistant_content():
    tokenizer = BayanTokenizer(version=2)
    row = {
        "messages": [
            {"role": "user", "content": "not knowledge"},
            {"role": "assistant", "content": "No. لا."},
        ]
    }
    sample = next(tokenize_record(row, tokenizer, 256))
    batch = RuhCollator()([sample])
    target_ids = batch["labels"][0][batch["labels"][0] != 0].tolist()
    assert tokenizer.decode([(token, 0) for token in target_ids]) == " No. لا."
    assert target_ids[-1] == 2
    assert int((batch["labels"] != 0).sum()) == len(" No. لا.".encode()) + 1
    bad = dict(sample, target_mask=[True])
    with pytest.raises(ValueError, match="target_mask"):
        RuhCollator()([bad])


def test_conversation_groups_and_duplicate_content_cannot_leak():
    rows = [
        {"text": f"Sentence {index}", "group_id": f"conversation-{index // 2}"}
        for index in range(80)
    ]
    rows.append(rows[0].copy())
    train, validation = split_records(rows)
    assert len(train) + len(validation) == 80
    assert not {row["group_id"] for row in train} & {row["group_id"] for row in validation}
    assert split_records(rows) == (train, validation)
    repeated = [
        {
            "messages": [
                {"role": "user", "content": "Same question"},
                {"role": "assistant", "content": f"Answer {i}"},
            ],
            "group_id": f"source-{i}",
        }
        for i in range(3)
    ]
    train, validation = split_records(rows + repeated)
    assert sum(row in train for row in repeated) in (0, 3)


def test_oasst_filters_deleted_unreviewed_and_non_answers():
    base = {"lang": "ar", "deleted": False, "review_result": True, "message_tree_id": "thread-1"}
    parent = dict(base, message_id="user", parent_id=None, role="prompter", text="ما معنى العلم؟")
    answer = dict(
        base, message_id="assistant", parent_id="user", role="assistant", text="العلم هو المعرفة."
    )
    rows = [
        parent,
        answer,
        dict(answer, message_id="deleted", deleted=True),
        dict(answer, message_id="unreviewed", review_result=False),
    ]
    pairs = list(conversation_pairs(rows))
    assert len(pairs) == 1
    assert pairs[0]["messages"][1]["content"] == answer["text"]


def test_v2_generation_uses_the_training_pattern_and_surface_vocabulary():
    tokenizer = BayanTokenizer(version=2)
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_heads=4,
        n_layers=1,
        n_roots=tokenizer._vocab.n_roots,
        max_seq_len=64,
        tokenizer_version=2,
        moe_interval=0,
        dropout=0,
    )
    model = RuhModel(config)
    model.tokenizer = tokenizer
    seen = []
    original = model._sample_next_token

    def sample(roots, patterns, temperature, valid_n_roots):
        seen.append(patterns.clone())
        return original(roots, patterns, temperature, valid_n_roots)

    model._sample_next_token = sample
    generated = model.generate(
        torch.tensor([[1, tokenizer._byte_start + 97]]),
        torch.tensor([[0, 0]]),
        max_new_tokens=3,
        temperature=0,
    )
    assert all(
        token == 2 or tokenizer._byte_start <= token < tokenizer._byte_start + 256
        for token in generated[0, 2:].tolist()
    )
    for patterns in seen:
        assert not patterns.any()


def test_cpu_mini_training_improves_held_out_and_round_trips_checkpoint(tmp_path):
    torch.set_num_threads(1)
    rows = [
        {
            "messages": [
                {"role": "user", "content": f"Give answer {index}."},
                {"role": "assistant", "content": "The answer is no, not yes."},
            ],
            "group_id": str(index),
        }
        for index in range(40)
    ]
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_heads=4,
        n_layers=1,
        max_seq_len=64,
        tokenizer_version=2,
        moe_interval=0,
        dropout=0,
    )
    report = run_training(
        rows,
        tmp_path / "run",
        config=config,
        steps=45,
        batch_size=4,
        learning_rate=0.005,
        max_seconds=30,
    )
    assert math.isfinite(report["held_out_after"]["cross_entropy"])
    assert report["held_out_after"]["cross_entropy"] < report["held_out_before"]["cross_entropy"]
    assert report["training"]["steps"] == 45
    assert report["promotion"]["approved"] is False
    assert set(report["checkpoint_manifest"]) == {
        "config.json",
        "model.pt",
        "tokenizer.json",
        "vocab.json",
    }
    restored = RuhModel.from_pretrained(str(tmp_path / "run" / "candidate"))
    assert restored.tokenizer.encode("not knowledge") != restored.tokenizer.encode("very knowledge")
    resumed = run_training(
        rows,
        tmp_path / "resumed",
        config=config,
        steps=2,
        batch_size=4,
        max_seconds=30,
        resume_from=tmp_path / "run" / "candidate",
    )
    assert resumed["training"]["steps"] == 2
    assert resumed["held_out_before"]["cross_entropy"] == pytest.approx(
        report["held_out_after"]["cross_entropy"]
    )


def test_sequence_training_refuses_legacy_resume(tmp_path):
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_heads=4,
        n_layers=1,
        n_roots=100,
        max_seq_len=64,
        moe_interval=0,
    )
    RuhModel(config).save_pretrained(str(tmp_path / "legacy"))
    config.tokenizer_version = 2
    rows = [{"text": f"Sentence {index}"} for index in range(80)]
    with pytest.raises(ValueError, match="legacy root checkpoint"):
        run_training(rows, tmp_path / "invalid", config=config, resume_from=tmp_path / "legacy")


def test_balanced_real_categories_and_continuation_resume(tmp_path):
    from ruh_model.train_sequence import save_continuation

    tokenizer = BayanTokenizer(version=2)
    rows = []
    for index in range(100):
        language = "ar" if index % 2 else "en"
        rows.append(
            {
                "messages": [
                    {"role": "user", "content": f"Question number {index}?"},
                    {"role": "assistant", "content": "لا. No."},
                ],
                "lang": language,
                "group_id": str(index),
            }
        )
    # Long document windows would dominate unweighted sampling.
    rows += [
        {"text": f"مقال {index} " + "المعرفة مفيدة. " * 20, "lang": "ar"} for index in range(100)
    ]
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_heads=4,
        n_layers=1,
        n_roots=tokenizer._vocab.n_roots,
        max_seq_len=64,
        tokenizer_version=2,
        moe_interval=0,
        dropout=0,
    )
    weights = {"ar:dialogue": 0.55, "en:dialogue": 0.25, "ar:text": 0.20}
    report = run_training(
        rows,
        tmp_path / "balanced",
        config=config,
        steps=100,
        batch_size=4,
        max_seconds=30,
        mixing_weights=weights,
    )
    counts = report["training"]["target_tokens_by_category"]
    assert (counts["ar:dialogue"] + counts["en:dialogue"]) / sum(counts.values()) > 0.6
    assert set(report["held_out_by_language_after"]) == {"ar", "en"}
    model = RuhModel.from_pretrained(str(tmp_path / "balanced" / "candidate"))
    optimizer = torch.optim.AdamW(model.parameters())
    first = save_continuation(model, optimizer, tmp_path / "balanced", 100, None)
    last = save_continuation(model, optimizer, tmp_path / "balanced", 200, first)
    assert not first.exists()
    assert (last / "candidate" / "tokenizer.json").is_file()
    resumed = run_training(
        rows,
        tmp_path / "continued",
        config=config,
        steps=2,
        max_seconds=30,
        resume_from=last / "candidate",
        mixing_weights=weights,
    )
    assert resumed["training"]["steps"] == 2


def test_v2_masks_dominant_legacy_unknown_and_root_logits():
    tokenizer = BayanTokenizer(version=2)
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_heads=4,
        n_layers=1,
        n_roots=tokenizer._vocab.n_roots,
        max_seq_len=64,
        tokenizer_version=2,
        moe_interval=0,
    )
    model = RuhModel(config)
    model.tokenizer = tokenizer

    def forward(roots, patterns):
        logits = torch.zeros((len(roots), roots.shape[1], config.n_roots))
        logits[..., 3] = 1e6  # Legacy UNK would win without the new mask.
        logits[..., 4] = 1e5  # A legacy root cannot reconstruct V2 surface text.
        logits[..., tokenizer._byte_start + ord("a")] = 1
        return {"logits": logits}

    model.forward = forward
    generated = model.generate(
        torch.tensor([[1]]), torch.tensor([[0]]), max_new_tokens=3, temperature=0
    )
    assert tokenizer.decode([(token, 0) for token in generated[0].tolist()]) == "aaa"


def test_v1_generation_keeps_legacy_pattern_one():
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_heads=4,
        n_layers=1,
        n_roots=100,
        max_seq_len=64,
        tokenizer_version=1,
        moe_interval=0,
    )
    model = RuhModel(config)
    seen = []

    def next_token(roots, patterns, temperature, valid_n_roots):
        seen.append(patterns.clone())
        return torch.full((len(roots), 1), 4)

    model._sample_next_token = next_token
    model.generate(torch.tensor([[1, 4]]), torch.tensor([[0, 1]]), max_new_tokens=3, temperature=0)
    assert seen[1][0, -1].item() == 1
    assert seen[2][0, -2:].tolist() == [1, 1]
