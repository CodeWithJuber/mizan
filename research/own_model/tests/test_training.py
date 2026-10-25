"""Machine invariants using tiny tensor fixtures, never dialogue training data."""
from __future__ import annotations

from dataclasses import asdict, replace
import os
from pathlib import Path
import random
import tempfile

import pytest
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel as DDP

from mizan_reply.checkpoint import (FORMAT, atomic_save, capture_rng, load_checkpoint,
                                    restore_rng, validate_resume, validate_safe_tree)
from mizan_reply.model import MizanReplyModel, ModelConfig
from mizan_reply.train import (TrainingConfig, epoch_steps, evaluate_encoded,
                              runtime_identity, train_epoch)


def fixture_records():
    # Arbitrary machine token IDs; no semantic gold or user training corpus.
    records = []
    for index, length in enumerate((4, 7, 5, 6, 3)):
        ids = torch.tensor([(index * 5 + j) % 30 for j in range(length)], dtype=torch.long)
        targets = (ids + 1) % 30
        targets[:index % 3 + 1] = -100
        targets[-1] = 256
        records.append({"input_ids": ids, "targets": targets,
                        "roots": torch.zeros(length, 4, dtype=torch.long)})
    return records


def tiny_model():
    return MizanReplyModel(ModelConfig(dim=8, layers=3, kernel_size=3, max_seq_len=15, root_dim=3, root_mode="none"))


def assert_state_equal(a, b):
    if isinstance(a, torch.Tensor):
        assert torch.equal(a, b)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a:
            assert_state_equal(a[key], b[key])
    elif isinstance(a, (tuple, list)):
        assert len(a) == len(b)
        for left, right in zip(a, b):
            assert_state_equal(left, right)
    else:
        assert a == b


def test_epoch_partition_has_no_duplicate_padding():
    steps = epoch_steps(5, batch_size=1, accumulation_steps=2, world_size=2, seed=17, epoch=0)
    indices = [item for step in steps for micro in step for rank in micro for item in rank]
    assert sorted(indices) == list(range(5))
    assert len(steps) == 2
    assert any(not rank for step in steps for micro in step for rank in micro)
    assert steps == epoch_steps(5, batch_size=1, accumulation_steps=2, world_size=2, seed=17, epoch=0)


def test_actual_model_parameters_update_and_hinge_decreases():
    torch.set_num_threads(1)
    torch.manual_seed(17)
    model = tiny_model()
    before = {name: tensor.detach().clone() for name, tensor in model.named_parameters()}
    records = fixture_records()
    config = TrainingConfig(batch_size=5, accumulation_steps=1, grad_clip=100.0, device="cpu")
    optimizer = torch.optim.SGD(model.parameters(), lr=0.05)
    initial = evaluate_encoded(model, records, device=torch.device("cpu"))["hinge_per_target_token"]
    for epoch in range(8):
        result = train_epoch(model, optimizer, records, config, epoch=epoch, device=torch.device("cpu"))
    final = evaluate_encoded(model, records, device=torch.device("cpu"))["hinge_per_target_token"]
    assert final < initial
    assert result["target_tokens"] == sum(int((r["targets"] != -100).sum()) for r in records)
    assert any(not torch.equal(before[name], value) for name, value in model.named_parameters())


def _ddp_worker(rank, world_size, rendezvous, output):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(17)
    dist.init_process_group("gloo", init_method=f"file://{rendezvous}", rank=rank, world_size=world_size)
    model = tiny_model()
    wrapped = DDP(model, broadcast_buffers=False)
    optimizer = torch.optim.SGD(wrapped.parameters(), lr=0.01)
    config = TrainingConfig(batch_size=1, accumulation_steps=2, grad_clip=100.0, device="cpu")
    result = train_epoch(wrapped, optimizer, fixture_records(), config, epoch=0,
                         device=torch.device("cpu"), rank=rank, world_size=world_size)
    evaluation = evaluate_encoded(model, fixture_records(), device=torch.device("cpu"), rank=rank, world_size=world_size)
    if rank == 0:
        torch.save({"model": model.state_dict(), "metrics": result, "evaluation": evaluation}, output)
    dist.barrier()
    dist.destroy_process_group()


def test_two_rank_matches_single_rank_unequal_lengths_and_empty_last_rank(tmp_path):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(17)
    single = tiny_model()
    optimizer = torch.optim.SGD(single.parameters(), lr=0.01)
    config = TrainingConfig(batch_size=4, accumulation_steps=1, grad_clip=100.0, device="cpu")
    expected = train_epoch(single, optimizer, fixture_records(), config, epoch=0, device=torch.device("cpu"))
    single_eval = evaluate_encoded(single, fixture_records(), device=torch.device("cpu"))
    output = str(tmp_path / "distributed.pt")
    try:
        mp.spawn(_ddp_worker, args=(2, str(tmp_path / "rendezvous"), output), nprocs=2, join=True)
    except mp.ProcessRaisedException as exc:
        if "Operation not permitted" in str(exc) and "gloo/transport/tcp/device.cc" in str(exc):
            pytest.skip("This host blocks Gloo TCP sockets; actual distributed parity must run on the GPU/CPU host")
        raise
    distributed = torch.load(output, weights_only=True)
    for name, tensor in single.state_dict().items():
        torch.testing.assert_close(tensor, distributed["model"][name], atol=2e-7, rtol=2e-6)
    assert expected["target_tokens"] == distributed["metrics"]["target_tokens"]
    assert expected["hinge_per_target_token"] == pytest.approx(distributed["metrics"]["hinge_per_target_token"], abs=2e-7)
    assert single_eval["examples"] == distributed["evaluation"]["examples"] == 5
    assert single_eval["hinge_per_target_token"] == pytest.approx(distributed["evaluation"]["hinge_per_target_token"], abs=2e-7)


def test_exact_epoch_resume_model_optimizer_rng_and_hash_refusal(tmp_path):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(29)
    random.seed(29)
    model = tiny_model()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    config = TrainingConfig(epochs=2, batch_size=2, device="cpu")
    records = fixture_records()
    train_epoch(model, optimizer, records, config, epoch=0, device=torch.device("cpu"))
    manifest = {"train_sha256": "a" * 64, "dev_sha256": "b" * 64, "sources_sha256": "c" * 64}
    runtime = runtime_identity(torch.device("cpu"))
    payload = {"format": FORMAT, "checkpoint_boundary": "complete_epoch", "model_config": model.config.to_dict(), "training_config": asdict(config),
               "model_state": model.state_dict(), "optimizer_state": optimizer.state_dict(), "scaler_state": {},
               "data_manifest": manifest, "epoch_completed": 1, "optimizer_steps": 3,
               "world_size": 1, "runtime": runtime, "rng_by_rank": [capture_rng()]}
    path = tmp_path / "saved.pt"
    atomic_save(path, payload)
    train_epoch(model, optimizer, records, config, epoch=1, device=torch.device("cpu"))
    random_draw = random.random()
    tensor_draw = torch.rand(5)
    loaded = load_checkpoint(path)
    validate_resume(loaded, model_config=model.config.to_dict(), training_config=asdict(config),
                    data_manifest=manifest, world_size=1, runtime=runtime)
    resumed = tiny_model()
    resumed.load_state_dict(loaded["model_state"])
    resumed_optimizer = torch.optim.AdamW(resumed.parameters(), lr=0.001)
    resumed_optimizer.load_state_dict(loaded["optimizer_state"])
    restore_rng(loaded["rng_by_rank"][0], torch.device("cpu"))
    train_epoch(resumed, resumed_optimizer, records, config, epoch=1, device=torch.device("cpu"))
    assert_state_equal(model.state_dict(), resumed.state_dict())
    assert_state_equal(optimizer.state_dict(), resumed_optimizer.state_dict())
    assert random.random() == random_draw
    assert torch.equal(torch.rand(5), tensor_draw)
    altered = dict(manifest, train_sha256="d" * 64)
    with pytest.raises(ValueError, match="hashes"):
        validate_resume(loaded, model_config=model.config.to_dict(), training_config=asdict(config),
                        data_manifest=altered, world_size=1, runtime=runtime)
    with pytest.raises(ValueError, match="topology"):
        validate_resume(loaded, model_config=model.config.to_dict(), training_config=asdict(config),
                        data_manifest=manifest, world_size=2, runtime=runtime)


class MaliciousPickle:
    def __init__(self, path):
        self.path = path

    def __reduce__(self):
        return (os.system, (f"touch {self.path}",))


def test_restricted_load_never_executes_custom_pickle(tmp_path):
    marker = tmp_path / "marker"
    path = tmp_path / "untrusted.pt"
    torch.save(MaliciousPickle(str(marker)), path)
    with pytest.raises(Exception):
        load_checkpoint(path)
    assert not marker.exists()


def test_checkpoint_rejects_cycles_and_custom_objects():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="Cyclic"):
        validate_safe_tree(cycle)
    with pytest.raises(ValueError, match="Forbidden"):
        validate_safe_tree({"bad": set()})


def test_rank_gradient_average_matches_global_token_mean_with_empty_rank():
    """Explicit DDP averaging arithmetic; does not replace a real Gloo/NCCL run."""
    from mizan_reply.data import collate_records
    from mizan_reply.model import margin_loss
    torch.set_num_threads(1)
    for rank_indices in (([0, 1, 2, 3], [4]), ([0, 1, 2, 3, 4], [])):
        torch.manual_seed(71)
        global_model = tiny_model()
        records = fixture_records()
        batch = collate_records(records)
        count = sum(int((row["targets"] != -100).sum()) for row in records)
        objective = margin_loss(global_model(batch["input_ids"], batch["roots"]), batch["targets"], reduction="sum") / count
        objective.backward()
        gradients = []
        for indices in rank_indices:
            torch.manual_seed(71)
            local = tiny_model()
            local_batch = collate_records([records[i] for i in indices] if indices else [records[0]])
            if not indices:
                local_batch["targets"].fill_(-100)
            loss = margin_loss(local(local_batch["input_ids"], local_batch["roots"]), local_batch["targets"], reduction="sum") * 2 / count
            loss.backward()
            gradients.append({name: parameter.grad.clone() for name, parameter in local.named_parameters()})
        for name, parameter in global_model.named_parameters():
            averaged = (gradients[0][name] + gradients[1][name]) / 2
            torch.testing.assert_close(parameter.grad, averaged, atol=2e-7, rtol=2e-6)
