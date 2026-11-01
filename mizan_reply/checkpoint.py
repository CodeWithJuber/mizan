"""Restricted tensor/primitive checkpoints; epoch-boundary continuation only.

This rejects executable object pickle formats. It is not a sandbox for arbitrary
untrusted files: checkpoints must come from your controlled training run.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import random
import re
import tempfile
from typing import Any

import torch

FORMAT = "mizan.reply.checkpoint.v1"


def require_safe_torch() -> None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", torch.__version__)
    if not match or tuple(map(int, match.groups())) < (2, 10, 0):
        raise RuntimeError("PyTorch >=2.10.0 is required for restricted checkpoint loading; no unsafe fallback exists")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_safe_tree(value: Any, *, depth: int = 0, active: set[int] | None = None) -> None:
    if depth > 100:
        raise ValueError("Checkpoint nesting exceeds 100 levels")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("Checkpoint contains a nonfinite scalar")
    if value is None or type(value) in (str, int, float, bool):
        return
    if type(value) is torch.Tensor:
        if value.layout != torch.strided:
            raise ValueError("Only ordinary strided tensors are supported")
        if (value.is_floating_point() or value.is_complex()) and not bool(torch.isfinite(value).all()):
            raise ValueError("Checkpoint contains a nonfinite tensor")
        return
    from collections import OrderedDict
    if type(value) not in (dict, OrderedDict, list, tuple):
        raise ValueError(f"Forbidden checkpoint object: {type(value).__name__}")
    active = set() if active is None else active
    if id(value) in active:
        raise ValueError("Cyclic checkpoint container")
    active.add(id(value))
    if isinstance(value, dict):
        if any(type(key) not in (str, int) for key in value):
            raise ValueError("Checkpoint mapping keys must be strings or integers")
        items = value.values()
    else:
        items = value
    for child in items:
        validate_safe_tree(child, depth=depth + 1, active=active)
    active.remove(id(value))


def cpu_tree(value: Any) -> Any:
    """Detach tensor state before serialization without serializing live modules."""
    if type(value) is torch.Tensor:
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {key: cpu_tree(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return tuple(cpu_tree(child) for child in value)
    if isinstance(value, list):
        return [cpu_tree(child) for child in value]
    return value


def atomic_save(path: str | Path, payload: dict) -> None:
    require_safe_torch()
    validate_safe_tree(payload)
    validate_checkpoint_metadata(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            torch.save(cpu_tree(payload), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_checkpoint_metadata(payload: dict) -> None:
    if type(payload) is not dict or payload.get("format") != FORMAT:
        raise ValueError("Not a supported Mizan reply restricted checkpoint")
    required = {"model_config", "training_config", "model_state", "optimizer_state", "data_manifest", "epoch_completed", "optimizer_steps", "world_size", "runtime", "rng_by_rank", "scaler_state", "checkpoint_boundary"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"Incomplete checkpoint: missing {sorted(missing)}")
    if payload["checkpoint_boundary"] != "complete_epoch":
        raise ValueError("Only complete-epoch checkpoints are supported")
    for name in ("model_config", "training_config", "model_state", "optimizer_state", "data_manifest", "runtime", "scaler_state"):
        if not isinstance(payload[name], dict):
            raise ValueError(f"Checkpoint {name} must be a mapping")
    for name in ("epoch_completed", "optimizer_steps", "world_size"):
        if type(payload[name]) is not int or payload[name] < (1 if name == "world_size" else 0):
            raise ValueError(f"Checkpoint {name} has invalid progress/topology")
    if payload["epoch_completed"] == 0 and payload["optimizer_steps"] != 0:
        raise ValueError("A zero-epoch checkpoint cannot contain optimizer updates")
    if type(payload["rng_by_rank"]) is not list or len(payload["rng_by_rank"]) != payload["world_size"]:
        raise ValueError("Checkpoint rank RNG state count is inconsistent")


def load_checkpoint_snapshot(path: str | Path) -> tuple[dict, str]:
    """Load and identify one open file; concurrent in-place changes are refused.

    Atomic replacement of the pathname is safe: both reads use the same open
    inode, and the returned digest identifies the checkpoint actually loaded.
    """
    require_safe_torch()
    with Path(path).open("rb") as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        stream.seek(0)
        payload = torch.load(stream, map_location="cpu", weights_only=True)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    # Unlinking the old inode during an atomic replacement changes ctime/nlink,
    # even though its open contents remain identical. Refuse other ctime changes.
    ctime_changed_in_place = before.st_ctime_ns != after.st_ctime_ns and before.st_nlink == after.st_nlink
    if ctime_changed_in_place or any(getattr(before, name) != getattr(after, name) for name in fields):
        raise ValueError("Checkpoint changed while it was being loaded")
    validate_safe_tree(payload)
    validate_checkpoint_metadata(payload)
    return payload, digest.hexdigest()


def load_checkpoint(path: str | Path) -> dict:
    return load_checkpoint_snapshot(path)[0]


def capture_rng() -> dict:
    return {
        "python": random.getstate(),
        "torch_cpu": torch.get_rng_state(),
        "torch_cuda": [torch.cuda.get_rng_state(torch.cuda.current_device())] if torch.cuda.is_available() else [],
        "cuda_device_index": torch.cuda.current_device() if torch.cuda.is_available() else None,
    }


def restore_rng(state: dict, device: torch.device) -> None:
    random.setstate(state["python"])
    torch.set_rng_state(state["torch_cpu"])
    if device.type == "cuda":
        if len(state["torch_cuda"]) != 1 or state["cuda_device_index"] != device.index:
            raise ValueError("CUDA rank device changed; exact resume refused")
        torch.cuda.set_rng_state(state["torch_cuda"][0], device=device)


def validate_resume(checkpoint: dict, *, model_config: dict, training_config: dict, data_manifest: dict, world_size: int, runtime: dict) -> None:
    validate_safe_tree(checkpoint)
    validate_checkpoint_metadata(checkpoint)
    # Total epochs may be extended; every setting affecting an update is fixed.
    previous = {k: v for k, v in checkpoint["training_config"].items() if k != "epochs"}
    requested = {k: v for k, v in training_config.items() if k != "epochs"}
    for label, before, after in (
        ("model configuration", checkpoint["model_config"], model_config),
        ("training settings", previous, requested),
        ("dataset/source hashes", checkpoint["data_manifest"], data_manifest),
        ("distributed topology", checkpoint["world_size"], world_size),
        ("runtime", checkpoint["runtime"], runtime),
    ):
        if before != after:
            raise ValueError(f"Exact resume refused: {label} changed")
    if checkpoint["epoch_completed"] > training_config["epochs"]:
        raise ValueError("Requested total epochs precede the checkpoint")
    if len(checkpoint["rng_by_rank"]) != world_size:
        raise ValueError("Checkpoint rank RNG state count is inconsistent")
