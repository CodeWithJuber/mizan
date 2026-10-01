"""Numerical and checkpoint-compatibility regressions from the deep review."""

import json

import pytest
import torch

from ruh_model.config import RuhConfig
from ruh_model.data.collator import RuhCollator
from ruh_model.data.pipeline import RealDataPipeline
from ruh_model.model import RuhModel
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.conversation import serialize_messages
from ruh_model.training.trainer import RuhTrainer
from ruh_model.training.scheduler import WarmupCosineScheduler


def config(version=1, lubb=False):
    return RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=8,
        n_roots=400,
        n_patterns=20,
        n_layers=3,
        n_heads=4,
        max_seq_len=32,
        dropout=0,
        tokenizer_version=version,
        use_lubb=lubb,
    )


@pytest.mark.parametrize(
    "text",
    [
        "not knowledge",
        "very knowledge",
        "لا علم",
        "unseenword !?",
        "spaces  and\nnewlines",
        "أحمد🙂",
    ],
)
def test_v2_roundtrip_preserves_surface(text):
    t = BayanTokenizer(version=2)
    assert t.decode(t.encode(text)) == text
    assert all(root != 0 for root, pattern in t.encode(text))


def test_inference_prompt_and_legacy_stopwords_have_supervision():
    t = BayanTokenizer()
    assert t.encode("knowledge", add_eos=False)[-1][0] != 2
    tokens = t.encode("the and")
    batch = RuhCollator()(
        [{"root_ids": [r for r, p in tokens], "pattern_ids": [p for r, p in tokens]}]
    )
    assert batch["labels"][0, -2].item() == 2  # EOS remains a supervised target.
    result = RuhModel(config())(**batch)
    assert torch.isfinite(result["loss"])
    with pytest.raises(ValueError, match="supervised"):
        RuhModel(config())(torch.tensor([[0]]), torch.tensor([[0]]), labels=torch.tensor([[0]]))


def test_negation_and_punctuation_distinct_for_new_training():
    t = BayanTokenizer(version=2)
    assert t.encode("not knowledge") != t.encode("very knowledge")
    assert t.encode("لا علم") != t.encode("علم")
    assert t.encode("knowledge!") != t.encode("knowledge?")


def test_invalid_root_sampling_and_greedy(monkeypatch):
    model = RuhModel(config())
    logits = torch.zeros(1, 1, 400)
    logits[..., 399] = 100
    logits[..., 10] = 10
    monkeypatch.setattr(model, "forward", lambda *args: {"logits": logits})
    assert model._sample_next_token(torch.tensor([[1]]), torch.tensor([[0]]), 0).item() == 10


def test_versioned_checkpoint_roundtrip_and_missing_vocab_rejected(tmp_path):
    model = RuhModel(config(version=2))
    model.save_pretrained(str(tmp_path))
    restored = RuhModel.from_pretrained(str(tmp_path))
    assert restored.tokenizer.version == 2
    assert restored.tokenizer.decode(restored.tokenizer.encode("not علم!")) == "not علم!"
    (tmp_path / "vocab.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        RuhModel.from_pretrained(str(tmp_path))


def test_legacy_checkpoint_without_new_parameters_remains_loadable(tmp_path):
    model = RuhModel(config())
    torch.save(model.state_dict(), tmp_path / "model.pt")
    values = model.config.__dict__.copy()
    for key in ("tokenizer_version", "use_lubb", "moe_aux_weight"):
        values.pop(key)
    (tmp_path / "config.json").write_text(json.dumps(values))
    restored = RuhModel.from_pretrained(str(tmp_path))
    assert restored.tokenizer.version == 1
    assert restored.tokenizer._vocab.n_roots == 62


def test_corpus_mixing_batches_and_conversation_context():
    t = BayanTokenizer(version=2)
    sources = {
        "corpus": [
            {"text": "first text"},
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "reply"},
                ]
            },
        ]
    }
    pipeline = RealDataPipeline(t, 32, sources=sources)
    batches = list(pipeline.get_dataloader(2, 2))
    assert len(batches) == 1 and batches[0]["root_ids"].shape[0] == 2
    serialized = serialize_messages(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ],
        system="system rule",
    )
    assert all(text in serialized for text in ("first", "second", "third", "system rule"))


def test_confidence_and_moe_objectives_receive_gradients(tmp_path):
    model = RuhModel(config(lubb=True))
    tokens = BayanTokenizer().encode("knowledge light")
    collator = RuhCollator()
    sample = {"root_ids": [r for r, p in tokens], "pattern_ids": [p for r, p in tokens]}
    batch = collator([sample])
    trainer = RuhTrainer(model, model.config, [sample], collator, checkpoint_dir=str(tmp_path))
    result = model(**batch)
    loss = trainer._compute_loss(result, batch)
    loss.backward()
    assert model.lubb_head[0].weight.grad is not None
    gates = [
        module.gate
        for module in model.modules()
        if hasattr(module, "gate") and hasattr(module, "aux_loss")
    ]
    assert gates and all(gate.weight.grad is not None for gate in gates)
    assert trainer.last_loss_components["moe_aux"] > 0
    assert trainer.last_loss_components["calibration"] > 0


def test_paired_training_records_reach_consistency_objective(tmp_path):
    from ruh_model.data.dataset import RuhDataset

    path = tmp_path / "pairs.jsonl"
    path.write_text(
        json.dumps({"text": "علم نور", "paraphrase": "knowledge is light"})
        + "\n"
        + json.dumps({"text": "ordinary text"})
    )
    model = RuhModel(config(version=2, lubb=True))
    dataset = RuhDataset(str(path), BayanTokenizer(version=2), 32)
    batch = RuhCollator()([dataset[0], dataset[1]])
    assert batch["paraphrase_mask"].tolist() == [True, False]
    trainer = RuhTrainer(model, model.config, dataset, RuhCollator(), checkpoint_dir=str(tmp_path))
    result = model(batch["root_ids"], batch["pattern_ids"], labels=batch["labels"])
    loss = trainer._compute_loss(result, batch)
    loss.backward()
    assert torch.isfinite(loss) and trainer.last_loss_components["consistency"] > 0


def test_resume_uses_selected_device_for_batches(monkeypatch):
    from ruh_model.train_full import _create_or_resume_model
    from types import SimpleNamespace

    resumed = SimpleNamespace(config=SimpleNamespace(device="cpu"))
    resumed.to = lambda device: resumed
    monkeypatch.setattr(RuhModel, "from_pretrained", lambda path: resumed)
    assert _create_or_resume_model(config(), "checkpoint", "cuda").config.device == "cuda"


def test_streaming_training_uses_composite_objectives(monkeypatch, tmp_path, caplog):
    from types import SimpleNamespace
    from ruh_model import train_full
    from ruh_model.data import pipeline as module

    real_pipeline = module.RealDataPipeline
    monkeypatch.setattr(
        module,
        "RealDataPipeline",
        lambda tokenizer, max_seq_len, mixing_ratios: real_pipeline(
            tokenizer,
            max_seq_len,
            mixing_ratios,
            sources={"corpus": [{"text": "knowledge", "paraphrase": "علم نور"}]},
        ),
    )
    model = RuhModel(config(version=2, lubb=True))
    stage = SimpleNamespace(name="smoke", epochs=1, batch_size=1, max_seq_len=32, lr=0.001)
    args = SimpleNamespace(
        samples=1,
        weight_decay=0.01,
        max_grad_norm=1,
        checkpoint_dir=str(tmp_path),
        warmup_fraction=0.1,
        log_every=1,
    )
    with caplog.at_level("INFO"):
        losses = train_full._train_streaming(
            model, model.config, BayanTokenizer(version=2), {"corpus": 1}, stage, args
        )
    assert len(losses) == 1 and torch.isfinite(torch.tensor(losses)).all()
    assert model.lubb_head[0].weight.grad is not None
    assert (
        "calibration" in caplog.text and "consistency" in caplog.text and "moe_aux" in caplog.text
    )
