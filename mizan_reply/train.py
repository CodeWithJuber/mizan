"""Own-weight max-margin training with token-correct distributed accumulation.

Only validated, accepted user-supplied records are consumed. All checkpoints are
at complete epoch boundaries; no claim is made about interruption mid-epoch.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time
import tempfile
from typing import Any

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

from .checkpoint import (FORMAT, atomic_save, capture_rng, load_checkpoint, restore_rng,
                         sha256_file, validate_resume, require_safe_torch)
from .model import MizanReplyModel, ModelConfig, margin_loss


@dataclass(frozen=True)
class TrainingConfig:
    epochs: int = 1
    batch_size: int = 1  # Microbatch examples per rank, not total batch size.
    accumulation_steps: int = 1
    learning_rate: float = 0.0003
    weight_decay: float = 0.0
    grad_clip: float = 1.0
    seed: int = 17
    amp: str = "none"  # none / bf16 / fp16; AMP is CUDA-only.
    device: str = "auto"  # auto / cpu / cuda

    def __post_init__(self) -> None:
        for name in ("epochs", "batch_size", "accumulation_steps"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        for name in ("learning_rate", "grad_clip"):
            if type(getattr(self, name)) not in (int, float) or not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if type(self.weight_decay) not in (int, float) or not math.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("weight_decay must be finite and nonnegative")
        if self.amp not in ("none", "bf16", "fp16") or self.device not in ("auto", "cpu", "cuda"):
            raise ValueError("Unsupported AMP or device setting")

    @classmethod
    def from_dict(cls, value: dict) -> "TrainingConfig":
        if not isinstance(value, dict):
            raise ValueError("training config must be a dictionary")
        unknown = set(value) - {item.name for item in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown training settings: {sorted(unknown)}")
        return cls(**value)


def read_config(path: str | Path) -> tuple[ModelConfig, TrainingConfig]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(config) != {"model", "training"}:
        raise ValueError("Config must contain exactly model and training objects")
    return ModelConfig.from_dict(config["model"]), TrainingConfig.from_dict(config["training"])


def assert_external_output(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    source_root = Path(__file__).resolve().parents[1]
    if target == source_root or source_root in target.parents:
        raise ValueError("Output must be outside the source package to preserve manifests")
    return target


def assert_new_report_output(path: str | Path) -> Path:
    """Reports never replace an existing file, including an input or hardlink."""
    target = assert_external_output(path)
    if target.exists():
        raise ValueError("Report output already exists; choose a new external filename")
    return target


def write_new_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation closes the race between output preflight and the write.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_run_report(path: Path, payload: Any) -> None:
    """Replace metadata atomically without following an existing hardlink."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def assert_outputs_disjoint(outputs: list[Path], inputs: list[str | Path]) -> None:
    for output in outputs:
        for value in inputs:
            source = Path(value).resolve()
            if output.resolve() == source or (output.exists() and source.exists() and output.samefile(source)):
                raise ValueError("Output would overwrite a training input")


def validate_run_destination(output: Path, resume: str | None) -> None:
    if output.exists() and not output.is_dir():
        raise ValueError("Training output must be a directory")
    if output.exists() and any(output.iterdir()):
        latest = output / "latest.pt"
        if not resume or not latest.is_file() or not Path(resume).samefile(latest):
            raise ValueError("Output is not empty: resume its own latest.pt or use a fresh external directory")
    for name in ("preflight.json", "metrics.json"):
        if (output / name).is_symlink():
            raise ValueError("Training metadata output must not be a symlink")


def manifest_from_snapshot(summary: dict) -> dict:
    return {"train_sha256": summary["file_sha256"]["train"],
            "dev_sha256": summary["file_sha256"]["dev"],
            "sources_sha256": summary["sources_manifest_sha256"]}


def dataset_manifest(train_path: str | Path, dev_path: str | Path, sources_path: str | Path) -> dict:
    # The validated manifest itself pins every original source asset hash.
    return {"train_sha256": sha256_file(train_path), "dev_sha256": sha256_file(dev_path),
            "sources_sha256": sha256_file(sources_path)}


def configure_runtime(config: TrainingConfig) -> tuple[torch.device, int, int]:
    require_safe_torch()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    rank = int(os.environ.get("RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if world_size < 1 or rank < 0 or rank >= world_size or local_rank < 0:
        raise ValueError("Invalid distributed rank/topology environment")
    use_cuda = config.device == "cuda" or (config.device == "auto" and torch.cuda.is_available())
    if use_cuda and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable; refusing silent CPU fallback")
    device = torch.device("cuda", local_rank) if use_cuda else torch.device("cpu")
    if use_cuda:
        torch.cuda.set_device(device)
        if config.amp == "bf16" and not torch.cuda.is_bf16_supported():
            raise RuntimeError("This CUDA device does not support BF16")
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    elif config.amp != "none":
        raise ValueError("AMP is supported only with CUDA in this implementation")
    torch.use_deterministic_algorithms(True)
    if world_size > 1 and not dist.is_initialized():
        dist.init_process_group(backend="nccl" if use_cuda else "gloo")
    random.seed(config.seed)
    torch.manual_seed(config.seed)
    if use_cuda:
        torch.cuda.manual_seed_all(config.seed)
    return device, rank, world_size


def runtime_identity(device: torch.device) -> dict:
    return {"torch": str(torch.__version__), "device_type": device.type,
            "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
            "cuda_version": torch.version.cuda, "cudnn_version": torch.backends.cudnn.version(),
            "deterministic": torch.are_deterministic_algorithms_enabled(),
            "cpu_threads": torch.get_num_threads(),
            "cpu_capability": torch.backends.cpu.get_cpu_capability(),
            "torch_build_sha256": hashlib.sha256(torch.__config__.show().encode()).hexdigest(),
            "interop_threads": torch.get_num_interop_threads(),
            "cuda_visible_device_count": torch.cuda.device_count() if device.type == "cuda" else 0,
            "implementation_sha256": {name: sha256_file(Path(__file__).with_name(name))
                                      for name in ("model.py", "data.py", "train.py", "checkpoint.py")}}


def epoch_steps(count: int, *, batch_size: int, accumulation_steps: int, world_size: int, seed: int, epoch: int) -> list[list[list[list[int]]]]:
    """[optimizer step][microstep][rank][record id], no duplicate padding.

    Every rank has the same number of forward/backward calls. Empty rank slices
    use one masked dummy record and contribute zero target tokens/gradient.
    """
    indices = list(range(count))
    random.Random(seed + epoch).shuffle(indices)
    micro_width = batch_size * world_size
    step_width = micro_width * accumulation_steps
    steps = []
    for start in range(0, count, step_width):
        microsteps = []
        for offset in range(start, min(start + step_width, count), micro_width):
            batch = indices[offset:offset + micro_width]
            microsteps.append([batch[r * batch_size:(r + 1) * batch_size] for r in range(world_size)])
        steps.append(microsteps)
    return steps


class RecordDataset:
    """Keep raw JSON records in RAM, encode tensors per batch only.

    Validation currently materializes raw JSON records; this is not an indexed,
    out-of-core 2.4GB ingestion engine. Preflight reports this explicit limit.
    """
    def __init__(self, records: list[dict], max_seq_len: int):
        from .data import encode_record
        self.records = records
        self.max_seq_len = max_seq_len
        self.target_counts = []
        self.lengths = []
        for record in records:
            encoded = encode_record(record, max_seq_len)
            self.target_counts.append(token_count(encoded))
            self.lengths.append(len(encoded["input_ids"]))

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        from .data import encode_record
        return encode_record(self.records[index], self.max_seq_len)


def token_count(record: dict) -> int:
    return int((record["targets"] != -100).sum().item())


def move_batch(batch: dict, device: torch.device) -> dict:
    return {key: value.to(device) if isinstance(value, torch.Tensor) else value for key, value in batch.items()}


def make_batch(encoded: list[dict], indices: list[int], device: torch.device) -> dict:
    from .data import collate_records
    batch = collate_records([encoded[i] for i in indices] if indices else [encoded[0]])
    if not indices:
        batch["targets"] = torch.full_like(batch["targets"], -100)
    return move_batch(batch, device)


def autocast_context(device: torch.device, amp: str):
    if amp == "none":
        return nullcontext()
    return torch.autocast(device_type=device.type, dtype=torch.bfloat16 if amp == "bf16" else torch.float16)


def train_epoch(model: torch.nn.Module, optimizer: torch.optim.Optimizer, encoded: list[dict],
                config: TrainingConfig, *, epoch: int, device: torch.device, rank: int = 0,
                world_size: int = 1, scaler=None, margin: float = 1.0) -> dict:
    model.train()
    steps = epoch_steps(len(encoded), batch_size=config.batch_size,
                        accumulation_steps=config.accumulation_steps, world_size=world_size,
                        seed=config.seed, epoch=epoch)
    counts = encoded.target_counts if isinstance(encoded, RecordDataset) else [token_count(record) for record in encoded]
    local_loss = 0.0
    local_tokens = 0
    skipped_steps = 0
    for microsteps in steps:
        denominator = sum(counts[i] for micro in microsteps for ids in micro for i in ids)
        if denominator <= 0:
            raise ValueError("Optimizer step has no target tokens")
        optimizer.zero_grad(set_to_none=True)
        for micro_index, rank_ids in enumerate(microsteps):
            batch = make_batch(encoded, rank_ids[rank], device)
            synchronization = model.no_sync() if isinstance(model, DDP) and micro_index < len(microsteps) - 1 else nullcontext()
            with synchronization:
                with autocast_context(device, config.amp):
                    energies = model(batch["input_ids"], roots=batch.get("roots"))
                    # Evaluate the hinge in FP32 even when convolution is autocast.
                    summed = margin_loss(energies.float(), batch["targets"], reduction="sum", margin=margin)
                    # DDP averages gradients. Multiplying by world size restores
                    # the globally token-weighted loss, including accumulation.
                    loss = summed * (world_size / denominator)
                if not torch.isfinite(loss):
                    raise FloatingPointError("Nonfinite training loss; no checkpoint saved")
                if scaler is not None and scaler.is_enabled():
                    scaler.scale(loss).backward()
                else:
                    loss.backward()
            local_loss += float(summed.detach())
            local_tokens += int((batch["targets"] != -100).sum())
        if scaler is not None and scaler.is_enabled():
            scaler.unscale_(optimizer)
        gradient_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip, error_if_nonfinite=config.amp != "fp16")
        if scaler is not None and scaler.is_enabled():
            old_scale = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            skipped_steps += int(scaler.get_scale() < old_scale)
        else:
            if not torch.isfinite(gradient_norm):
                raise FloatingPointError("Nonfinite gradients; no checkpoint saved")
            optimizer.step()
    stats = torch.tensor([local_loss, float(local_tokens)], dtype=torch.float64, device=device)
    if world_size > 1:
        dist.all_reduce(stats, op=dist.ReduceOp.SUM)
    return {"hinge_per_target_token": float(stats[0] / stats[1]), "target_tokens": int(stats[1]),
            "optimizer_steps": len(steps) - skipped_steps, "optimizer_step_attempts": len(steps), "skipped_amp_steps": skipped_steps,
            "examples": len(encoded), "metric_scope": "teacher_forced_training_objective_not_factual_accuracy"}


@torch.no_grad()
def evaluate_encoded(model: torch.nn.Module, encoded: list[dict], *, device: torch.device,
                     batch_size: int = 1, margin: float = 1.0, rank: int = 0, world_size: int = 1) -> dict:
    from .data import collate_records
    previous = model.training
    model.eval()
    # Disjoint stride partitions, never repeat a validation record for padding.
    indices = list(range(rank, len(encoded), world_size))
    total_loss = total_correct = total_tokens = total_exact = 0.0
    for offset in range(0, len(indices), batch_size):
        batch = move_batch(collate_records([encoded[i] for i in indices[offset:offset + batch_size]]), device)
        energies = model(batch["input_ids"], roots=batch.get("roots"))
        targets = batch["targets"]
        valid = targets != -100
        predictions = energies.argmin(dim=-1)
        total_loss += float(margin_loss(energies.float(), targets, reduction="sum", margin=margin))
        total_correct += int(((predictions == targets) & valid).sum())
        total_tokens += int(valid.sum())
        total_exact += int(((predictions == targets) | ~valid).all(dim=1).sum())
    stats = torch.tensor([total_loss, total_correct, total_tokens, total_exact, len(indices)], dtype=torch.float64, device=device)
    if world_size > 1:
        dist.all_reduce(stats, op=dist.ReduceOp.SUM)
    model.train(previous)
    if stats[2] <= 0 or stats[4] <= 0:
        raise ValueError("Evaluation set has no examples/targets")
    return {"hinge_per_target_token": float(stats[0] / stats[2]),
            "teacher_forced_byte_accuracy_including_eos": float(stats[1] / stats[2]),
            "teacher_forced_sequence_exact": int(stats[3]), "examples": int(stats[4]),
            "target_tokens": int(stats[2]),
            "metric_scope": "byte_prediction_under_gold_prefixes_not_conversation_or_factual_accuracy"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-data", required=True)
    parser.add_argument("--dev-data", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resume")
    parser.add_argument("--preflight", action="store_true", help="Validate original assets, splits, encoding and config; no optimization")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    from .data import validate_dataset_snapshot
    model_config, config = read_config(args.config)
    output = assert_external_output(args.output_dir)
    assert_outputs_disjoint([output / name for name in ("latest.pt", "preflight.json", "metrics.json")],
                            [args.train_data, args.dev_data, args.sources, args.config])
    require_safe_torch()
    # Fail before accelerator allocation on missing data, rights/review, leakage,
    # hashes, oversized targets or malformed annotations. No synthetic fallback.
    summary, records = validate_dataset_snapshot(args.train_data, args.dev_data, args.sources)
    train_records = records["train"]
    dev_records = records["dev"]
    if not train_records or not dev_records:
        raise ValueError("Both original training and development data are required")
    encoded = RecordDataset(train_records, model_config.max_seq_len)
    dev_encoded = RecordDataset(dev_records, model_config.max_seq_len)
    manifest = manifest_from_snapshot(summary)
    rank = int(os.environ.get("RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    torch.manual_seed(config.seed)
    raw_model = MizanReplyModel(model_config)
    preflight = {"status": "validated_untrained", "data": summary, "data_manifest": manifest,
                 "parameters": sum(parameter.numel() for parameter in raw_model.parameters()),
                 "train_examples": len(encoded), "dev_examples": len(dev_encoded),
                 "train_target_tokens": sum(encoded.target_counts),
                 "maximum_sequence_tokens": max(encoded.lengths + dev_encoded.lengths),
                 "world_size": world_size,
                 "effective_batch_examples_max": config.batch_size * config.accumulation_steps * world_size,
                 "last_batch_policy": "no_duplicate_padding_global_target_token_weighting",
                 "model_config": model_config.to_dict(), "training_config": asdict(config),
                 "gpu_memory_profiled": False, "training_started": False,
                 "data_memory_policy": "raw_JSON_records_in_RAM_per_rank_tensors_encoded_per_batch",
                 "input_file_bytes_per_rank": sum(Path(path).stat().st_size for path in (args.train_data, args.dev_data, args.sources)),
                 "large_corpus_streaming_implemented": False}
    if args.preflight:
        if rank == 0:
            print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return preflight
    validate_run_destination(output, args.resume)
    device, rank, world_size = configure_runtime(config)
    try:
        runtime = runtime_identity(device)
        raw_model = raw_model.to(device)
        optimizer = torch.optim.AdamW(raw_model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
        scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda" and config.amp == "fp16")
        start_epoch = 0
        optimizer_steps = 0
        history = []
        if args.resume:
            checkpoint = load_checkpoint(args.resume)
            validate_resume(checkpoint, model_config=model_config.to_dict(), training_config=asdict(config),
                            data_manifest=manifest, world_size=world_size, runtime=runtime)
            raw_model.load_state_dict(checkpoint["model_state"], strict=True)
            optimizer.load_state_dict(checkpoint["optimizer_state"])
            scaler.load_state_dict(checkpoint["scaler_state"])
            start_epoch = checkpoint["epoch_completed"]
            optimizer_steps = checkpoint["optimizer_steps"]
            history = checkpoint.get("history", [])
            if start_epoch == config.epochs:
                return {"status": "no_additional_epochs", "epochs_completed": start_epoch,
                        "optimizer_steps": optimizer_steps, "checkpoint": str(Path(args.resume).resolve()),
                        "factual_accuracy_established": False}
        model = DDP(raw_model, device_ids=[device.index] if device.type == "cuda" else None,
                    broadcast_buffers=False, find_unused_parameters=False) if world_size > 1 else raw_model
        if args.resume:
            restore_rng(checkpoint["rng_by_rank"][rank], device)
        if rank == 0:
            output.mkdir(parents=True, exist_ok=True)
            write_run_report(output / "preflight.json", preflight)
        if world_size > 1:
            dist.barrier()
        for epoch in range(start_epoch, config.epochs):
            start = time.monotonic()
            train_metrics = train_epoch(model, optimizer, encoded, config, epoch=epoch, device=device,
                                        rank=rank, world_size=world_size, scaler=scaler, margin=model_config.margin)
            # Bypass DDP forward synchronization for uneven disjoint eval shards.
            dev_metrics = evaluate_encoded(raw_model, dev_encoded, device=device, batch_size=config.batch_size,
                                           margin=model_config.margin, rank=rank, world_size=world_size)
            optimizer_steps += train_metrics["optimizer_steps"]
            row = {"epoch_completed": epoch + 1, "train": train_metrics, "dev": dev_metrics,
                   "elapsed_seconds_rank0": time.monotonic() - start}
            history.append(row)
            rng = capture_rng()
            rng_states = [None] * world_size
            if world_size > 1:
                dist.all_gather_object(rng_states, rng)
            else:
                rng_states = [rng]
            if rank == 0:
                payload = {"format": FORMAT, "checkpoint_boundary": "complete_epoch", "model_config": model_config.to_dict(),
                           "training_config": asdict(config), "model_state": raw_model.state_dict(),
                           "optimizer_state": optimizer.state_dict(), "scaler_state": scaler.state_dict(),
                           "data_manifest": manifest, "epoch_completed": epoch + 1, "optimizer_steps": optimizer_steps,
                           "world_size": world_size, "runtime": runtime, "rng_by_rank": rng_states, "history": history}
                atomic_save(output / "latest.pt", payload)
                write_run_report(output / "metrics.json", history)
                print(json.dumps(row, ensure_ascii=False), flush=True)
            if world_size > 1:
                dist.barrier()
        return {"status": "training_complete", "epochs_completed": config.epochs, "optimizer_steps": optimizer_steps,
                "checkpoint": str(output / "latest.pt"), "factual_accuracy_established": False}
    finally:
        if dist.is_initialized():
            dist.destroy_process_group()


if __name__ == "__main__":
    main()
