"""Extra machine invariants; ephemeral fixtures are never a language corpus.

Serial gradient arithmetic and a fake scaler do not validate Gloo/NCCL/CUDA.
"""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest
import torch

from mizan_reply import cli, data, generation, train
from mizan_reply.checkpoint import (FORMAT, atomic_save, capture_rng, load_checkpoint,
                                    load_checkpoint_snapshot, sha256_file)
from mizan_reply.model import MizanReplyModel, ModelConfig, margin_loss
from mizan_reply.train import TrainingConfig, train_epoch


def tiny(mode="none"):
    return MizanReplyModel(ModelConfig(dim=4, layers=4, max_seq_len=31, root_dim=2, root_mode=mode))


def checkpoint_payload(model):
    return dict(format=FORMAT, checkpoint_boundary="complete_epoch", model_config=model.config.to_dict(),
                training_config=asdict(TrainingConfig(device="cpu")), model_state=model.state_dict(),
                optimizer_state={}, scaler_state={}, data_manifest={}, epoch_completed=0, optimizer_steps=0,
                world_size=1, runtime={}, rng_by_rank=[capture_rng()])


def fixture_files(directory):
    sources = []
    for index, split in enumerate(("train", "dev", "test")):
        asset = directory / f"{split}.txt"
        asset.write_text(f"Artificial machine fixture {index}; never an original corpus")
        sources.append(dict(source_id=split, source_family=split, kind="other", title="Machine fixture",
                            edition="unit", locator=f"unit:{index}", uri=f"urn:unit:{index}",
                            rights="Machine invariant only", sha256=sha256_file(asset), local_path=asset.name))
        row = dict(schema_version="mizan.reply.v1", id=split, split=split, group_id=split, language="en", task="dialogue",
                   messages=[dict(role="user", content=f"u{index}")], evidence=[],
                   target=dict(text=f"v{index}", citations=[], answer_status="answer"),
                   provenance=dict(origin="human_original", source_ids=[split], rights="Machine fixture declarations only",
                                   author_ids=["fixture-code"], reviewer_ids=["fixture-test"], review_status="accepted"))
        (directory / f"{split}.jsonl").write_text(json.dumps(row) + "\n")
    (directory / "sources.jsonl").write_text("".join(json.dumps(row) + "\n" for row in sources))
    config = dict(model=tiny().config.to_dict(), training=dict(epochs=1, device="cpu", seed=17))
    (directory / "config.json").write_text(json.dumps(config))
    return ["--train-data", str(directory / "train.jsonl"), "--dev-data", str(directory / "dev.jsonl"),
            "--sources", str(directory / "sources.jsonl")]


def test_noop_resume_points_to_real_checkpoint_and_does_not_create_output(tmp_path):
    torch.set_num_threads(1)
    common = fixture_files(tmp_path) + ["--config", str(tmp_path / "config.json")]
    train.main(common + ["--output-dir", str(tmp_path / "first")])
    source = tmp_path / "first/latest.pt"
    result = train.main(common + ["--output-dir", str(tmp_path / "fresh"), "--resume", str(source)])
    assert result["status"] == "no_additional_epochs"
    assert Path(result["checkpoint"]).samefile(source)
    assert not (tmp_path / "fresh").exists()


def test_resume_cannot_overwrite_an_unrelated_destination(tmp_path):
    torch.set_num_threads(1)
    common = fixture_files(tmp_path) + ["--config", str(tmp_path / "config.json")]
    train.main(common + ["--output-dir", str(tmp_path / "first")])
    other = tmp_path / "other"
    other.mkdir()
    (other / "latest.pt").write_bytes(b"unrelated checkpoint")
    (other / "metrics.json").write_bytes(b"unrelated metrics")
    with pytest.raises(ValueError, match="not empty"):
        train.main(common + ["--output-dir", str(other), "--resume", str(tmp_path / "first/latest.pt")])
    assert (other / "latest.pt").read_bytes() == b"unrelated checkpoint"
    assert (other / "metrics.json").read_bytes() == b"unrelated metrics"


@pytest.mark.parametrize("field,value", [("epoch_completed", -1), ("epoch_completed", True),
    ("optimizer_steps", -1), ("world_size", 0), ("rng_by_rank", []), ("checkpoint_boundary", "mid_epoch")])
def test_invalid_checkpoint_progress_rejected(tmp_path, field, value):
    payload = checkpoint_payload(tiny())
    payload[field] = value
    path = tmp_path / "bad.pt"
    torch.save(payload, path)
    with pytest.raises(ValueError):
        load_checkpoint(path)
    with pytest.raises(ValueError):
        atomic_save(tmp_path / "never.pt", payload)
    assert not (tmp_path / "never.pt").exists()


@pytest.mark.parametrize("state", ["model_state", "optimizer_state", "scaler_state", "history"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_checkpoint_state_rejected(tmp_path, state, value):
    payload = checkpoint_payload(tiny())
    payload[state] = {"bad": torch.tensor([value])} if state != "history" else [{"bad": value}]
    torch.save(payload, tmp_path / "bad.pt")
    with pytest.raises(ValueError, match="nonfinite"):
        load_checkpoint(tmp_path / "bad.pt")
    with pytest.raises(ValueError, match="nonfinite"):
        atomic_save(tmp_path / "never.pt", payload)


@pytest.mark.parametrize("name", ["learning_rate", "weight_decay", "grad_clip"])
@pytest.mark.parametrize("value", [True, "0.1", None, float("nan"), float("inf")])
def test_bad_numeric_training_settings_rejected(name, value):
    with pytest.raises(ValueError):
        TrainingConfig(**{name: value})


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
def test_all_masked_and_zero_root_batches_keep_every_parameter_connected(mode):
    torch.set_num_threads(1)
    model = tiny(mode)
    ids = torch.tensor([[1, 2, 3]])
    roots = torch.zeros(1, 3, 4, dtype=torch.long)
    loss = margin_loss(model(ids, roots), torch.full_like(ids, -100), reduction="sum")
    loss.backward()
    for name, parameter in model.named_parameters():
        assert parameter.grad is not None, name
        assert torch.isfinite(parameter.grad).all(), name
        assert parameter.grad.count_nonzero() == 0, name


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
def test_serial_accumulation_matches_global_token_weighting_with_tail(mode):
    torch.set_num_threads(1)
    torch.manual_seed(91)
    model = tiny(mode)
    accumulated = deepcopy(model)
    records = []
    for index, length in enumerate((3, 5, 4, 6, 2)):
        ids = torch.arange(length, dtype=torch.long) + index
        targets = (ids + 1) % 257
        targets[:1] = -100
        roots = torch.zeros(length, 4, dtype=torch.long)
        if index % 2:
            roots[0, :3] = torch.tensor([1, 2, 3])
        records.append(dict(input_ids=ids, targets=targets, roots=roots))
    a = train_epoch(model, torch.optim.SGD(model.parameters(), lr=.01), records,
                    TrainingConfig(batch_size=3, grad_clip=100, device="cpu"), epoch=0, device=torch.device("cpu"))
    b = train_epoch(accumulated, torch.optim.SGD(accumulated.parameters(), lr=.01), records,
                    TrainingConfig(batch_size=1, accumulation_steps=3, grad_clip=100, device="cpu"), epoch=0, device=torch.device("cpu"))
    for name, parameter in model.state_dict().items():
        torch.testing.assert_close(parameter, accumulated.state_dict()[name], atol=2e-7, rtol=2e-6)
    assert a["target_tokens"] == b["target_tokens"] == sum(len(r["targets"]) - 1 for r in records)
    assert a["optimizer_steps"] == b["optimizer_steps"] == 2


def test_skipped_scaler_attempts_are_not_counted_as_optimizer_updates(monkeypatch):
    class FakeScaler:
        """Models scaler control flow only, never claims actual CUDA AMP parity."""
        scale_value = 8
        skip = True
        updates = 0
        def is_enabled(self): return True
        def get_scale(self): return self.scale_value
        def scale(self, value): return value
        def unscale_(self, optimizer): pass
        def step(self, optimizer):
            if not self.skip:
                optimizer.step()
                self.updates += 1
        def update(self):
            if self.skip:
                self.scale_value /= 2
                self.skip = False
    monkeypatch.setattr(train, "autocast_context", lambda *args: nullcontext())
    torch.set_num_threads(1)
    model = tiny()
    row = dict(input_ids=torch.tensor([1, 2]), targets=torch.tensor([2, 256]), roots=torch.zeros(2, 4, dtype=torch.long))
    scaler = FakeScaler()
    stats = train_epoch(model, torch.optim.SGD(model.parameters(), lr=.01), [row, row],
                        TrainingConfig(device="cpu", amp="fp16"), epoch=0, device=torch.device("cpu"), scaler=scaler)
    assert stats["optimizer_step_attempts"] == 2
    assert stats["optimizer_steps"] == scaler.updates == 1
    assert stats["skipped_amp_steps"] == 1


def test_generate_protects_inputs_and_hashes_consumed_snapshots(tmp_path, monkeypatch):
    torch.set_num_threads(1)
    checkpoint = tmp_path / "model.pt"
    atomic_save(checkpoint, checkpoint_payload(tiny()))
    prompt = tmp_path / "prompt.json"
    prompt.write_text(json.dumps(dict(messages=[dict(role="user", content="u")], evidence=[])))
    base = ["generate", "--checkpoint", str(checkpoint), "--prompt", str(prompt), "--device", "cpu", "--max-new-tokens", "2"]
    alias = tmp_path / "hardlink.pt"
    alias.hardlink_to(checkpoint)
    for output in (checkpoint, prompt, alias):
        with pytest.raises(ValueError, match="already exists"):
            cli.main(base + ["--output", str(output)])
    checkpoint_hash, prompt_hash = sha256_file(checkpoint), sha256_file(prompt)
    actual_generate = generation.generate
    def replace_after_generation(*args, **kwargs):
        result = actual_generate(*args, **kwargs)
        checkpoint.write_bytes(b"replacement checkpoint")
        prompt.write_bytes(b"replacement prompt")
        return result
    monkeypatch.setattr(generation, "generate", replace_after_generation)
    result = cli.main(base + ["--output", str(tmp_path / "report.json")])
    assert result["checkpoint_sha256"] == checkpoint_hash
    assert result["prompt_sha256"] == prompt_hash
    assert result["reply_source"] == "loaded_checkpoint_weights_argmin_byte_decoder"
    assert result["optimizer_steps"] == 0
    assert result["independently_verified"] is False


def test_checkpoint_snapshot_tracks_open_inode_on_atomic_replacement(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.pt"
    atomic_save(path, checkpoint_payload(tiny()))
    expected = sha256_file(path)
    actual_load = torch.load
    def replacement(stream, **kwargs):
        tmp = tmp_path / "replacement"
        tmp.write_bytes(b"not the loaded checkpoint")
        tmp.replace(path)
        return actual_load(stream, **kwargs)
    monkeypatch.setattr(torch, "load", replacement)
    payload, digest = load_checkpoint_snapshot(path)
    assert digest == expected != sha256_file(path)
    assert payload["epoch_completed"] == 0


def test_checkpoint_snapshot_refuses_inplace_change(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.pt"
    atomic_save(path, checkpoint_payload(tiny()))
    actual_load = torch.load
    def replacement(stream, **kwargs):
        payload = actual_load(stream, **kwargs)
        with path.open("ab") as changed:
            changed.write(b"change while loading")
        return payload
    monkeypatch.setattr(torch, "load", replacement)
    with pytest.raises(ValueError, match="changed"):
        load_checkpoint_snapshot(path)


def test_evaluate_preserves_inputs_and_hashes_validated_records(tmp_path, monkeypatch):
    torch.set_num_threads(1)
    common = fixture_files(tmp_path)
    train.main(common + ["--config", str(tmp_path / "config.json"), "--output-dir", str(tmp_path / "run")])
    checkpoint = tmp_path / "run/latest.pt"
    dev = tmp_path / "dev.jsonl"
    base = ["evaluate", *common, "--checkpoint", str(checkpoint), "--data", str(dev), "--split", "dev", "--device", "cpu"]
    with pytest.raises(ValueError, match="already exists"):
        cli.main(base + ["--output", str(dev)])
    from mizan_reply import evaluate
    actual_evaluate = evaluate.evaluate_encoded
    expected = sha256_file(dev)
    def replace_after_evaluate(*args, **kwargs):
        result = actual_evaluate(*args, **kwargs)
        dev.write_bytes(b"different dataset after computation")
        return result
    monkeypatch.setattr(evaluate, "evaluate_encoded", replace_after_evaluate)
    report = cli.main(base + ["--output", str(tmp_path / "eval.json")])
    assert report["dataset_sha256"] == expected != sha256_file(dev)
    assert report["metrics"]["examples"] == 1
    assert report["factual_accuracy_established"] is False
