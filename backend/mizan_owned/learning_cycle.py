"""Bounded, local, original-data learning with measured development admission.

The operator owns the inputs and policy. Hashes bind their declarations; they do
not prove authorship or semantic truth. Chat review exports are not inputs here.
Each snapshot trains fresh weights, never a disguised incremental warm start.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, NoReturn

SCHEMA = "mizan.owned.learning.v1"
APPROVAL_SCHEMA = "mizan.owned.learning.approval.v1"
POLICY_SCHEMA = "mizan.owned.learning.policy.v1"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
# Source checkouts contain backend/; release images copy its contents to /app/.
SOURCE_ROOT = BACKEND_ROOT if (BACKEND_ROOT / "mizan_reply").is_dir() else BACKEND_ROOT.parent
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
INPUT_NAMES = {"config.json", "train.jsonl", "dev.jsonl", "sources.jsonl"}
LIMITS = {
    "cycle_seconds": 900,
    "preflight_seconds": 60,
    "train_seconds": 600,
    "evaluation_seconds": 120,
    "cpu_threads": 1,
    "memory_mb": 4096,
    "max_file_bytes": 16 * 1024 * 1024,
    "max_bundle_bytes": 64 * 1024 * 1024,
    "max_files": 512,
    "max_train_examples": 2000,
    "max_dev_examples": 128,
    "max_parameters": 5_000_000,
    "max_new_tokens": 64,
}
LIMIT_CAPS = {
    "cycle_seconds": 1800,
    "preflight_seconds": 120,
    "train_seconds": 1200,
    "evaluation_seconds": 300,
    "cpu_threads": 2,
    "memory_mb": 8192,
    "max_file_bytes": 32 * 1024 * 1024,
    "max_bundle_bytes": 128 * 1024 * 1024,
    "max_files": 1024,
    "max_train_examples": 5000,
    "max_dev_examples": 256,
    "max_parameters": 10_000_000,
    "max_new_tokens": 256,
}
GATE_KEYS = {
    "min_train_examples",
    "min_dev_examples",
    "max_dev_hinge",
    "min_dev_byte_accuracy",
    "min_generation_exact_match",
    "min_generation_eos_rate",
    "max_hinge_regression",
    "max_byte_accuracy_drop",
    "max_generation_exact_drop",
}


class LearningError(ValueError):
    """Safe machine-readable refusal; messages never contain source text or paths."""


class LearningBusy(LearningError):
    pass


class LearningInterrupted(LearningError):
    pass


def _fail(code: str) -> NoReturn:
    raise LearningError(code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    value: dict = {}
    for key, item in pairs:
        if key in value:
            _fail("duplicate_json_key")
        value[key] = item
    return value


def _json(raw: bytes) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail("nonfinite_json"),
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise LearningError("invalid_json") from exc


def _read(path: Path, maximum: int = 1024 * 1024) -> bytes:
    """Capture a regular, non-symlink file; bound the actual read and identity."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                _fail("invalid_or_oversized_file")
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) > maximum or any(getattr(before, x) != getattr(after, x) for x in fields):
            _fail("file_changed_or_oversized")
        return raw
    except OSError as exc:
        raise LearningError("missing_or_unsafe_file") from exc


def _hash_file(path: Path, maximum: int = 256 * 1024 * 1024) -> str:
    # Resolve is used on each chat request; never allocate the whole checkpoint.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                _fail("invalid_or_oversized_file")
            digest = hashlib.sha256()
            total = 0
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(block)
                if total > maximum:
                    _fail("file_changed_or_oversized")
                digest.update(block)
            after = os.fstat(stream.fileno())
        if any(
            getattr(before, key) != getattr(after, key)
            for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ):
            _fail("file_changed_or_oversized")
        return digest.hexdigest()
    except OSError as exc:
        raise LearningError("missing_or_unsafe_file") from exc


def _directory(path: Path, *, create: bool = False) -> Path:
    path = path.expanduser().absolute()
    if path != path.resolve():
        _fail("symlink_directory_forbidden")
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir() or path.is_symlink():
        _fail("missing_or_unsafe_directory")
    return path


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".learning-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path, follow_symlinks=False)
        else:
            os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextlib.contextmanager
def _writer(root: Path):
    root = _directory(root, create=True)
    fd = os.open(root / "cycle.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _fail("unsafe_lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LearningBusy("learning_cycle_busy") from exc
        yield fd
    finally:
        os.close(fd)


def _integer(value: Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _number(value: Any, low: float, high: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _policy(root: Path) -> tuple[dict, str]:
    raw = _read(root / "policy.json", 32 * 1024)
    policy = _json(raw)
    required = {"schema_version", "enabled", "allow_first_model", "gates"}
    if not isinstance(policy, dict) or not required <= policy.keys():
        _fail("invalid_policy")
    if set(policy) - required - {"limits"} or policy["schema_version"] != POLICY_SCHEMA:
        _fail("invalid_policy")
    if type(policy["enabled"]) is not bool or type(policy["allow_first_model"]) is not bool:
        _fail("invalid_policy")
    gates = policy["gates"]
    if not isinstance(gates, dict) or set(gates) != GATE_KEYS:
        _fail("invalid_policy_gates")
    for key in ("min_train_examples", "min_dev_examples"):
        if not _integer(gates[key], 1, LIMIT_CAPS["max_train_examples"]):
            _fail("invalid_policy_gates")
    for key in ("min_dev_byte_accuracy", "min_generation_exact_match", "min_generation_eos_rate"):
        if not _number(gates[key], 0, 1) or gates[key] == 0:
            _fail("positive_absolute_gate_required")
    if not _number(gates["max_dev_hinge"], 0, 100):
        _fail("invalid_policy_gates")
    if not _number(gates["max_hinge_regression"], 0, 0.25):
        _fail("invalid_policy_gates")
    for key in ("max_byte_accuracy_drop", "max_generation_exact_drop"):
        if not _number(gates[key], 0, 0.05):
            _fail("invalid_policy_gates")
    overrides = policy.get("limits", {})
    if not isinstance(overrides, dict) or set(overrides) - LIMITS.keys():
        _fail("invalid_policy_limits")
    limits = LIMITS | overrides
    if any(not _integer(value, 1, LIMIT_CAPS[key]) for key, value in limits.items()):
        _fail("invalid_policy_limits")
    if limits["memory_mb"] < 1024:
        _fail("invalid_policy_limits")
    if any(
        gates[f"min_{split}_examples"] > limits[f"max_{split}_examples"]
        for split in ("train", "dev")
    ):
        _fail("invalid_policy_gates")
    policy["limits"] = limits
    return policy, _digest(raw)


def _capacity(limits: dict) -> dict:
    """Conservative cgroup-v2 admission, not a reservation or isolation boundary.

    A bounded ancestor's remaining budget must fit the entire worker address
    space allowance plus 512 MiB for the API. Unknown/unlimited budgets refuse.
    Reading memory.current includes sibling use at every controlling ancestor.
    """
    required = (limits["memory_mb"] + 512) * 1024 * 1024
    result = {
        "admitted": False,
        "required_bytes": required,
        "api_reserve_bytes": 512 * 1024 * 1024,
        "available_bytes": None,
        "reason": "memory_budget_unknown",
    }
    try:
        membership = _read(Path("/proc/self/cgroup"), 16 * 1024).decode("ascii")
        rows = [line[3:] for line in membership.splitlines() if line.startswith("0::")]
        if len(rows) != 1 or not rows[0].startswith("/"):
            return result
        relative = Path(rows[0].lstrip("/"))
        if ".." in relative.parts or len(relative.parts) > 32:
            return result
        base = Path("/sys/fs/cgroup")
        directory = base / relative
        if directory.resolve() != directory or not directory.is_dir():
            return result
        budgets = []
        for ancestor in (directory, *directory.parents):
            if not ancestor.is_relative_to(base):
                break
            maximum = _read(ancestor / "memory.max", 64).strip()
            current = _read(ancestor / "memory.current", 64).strip()
            if not current.isdigit() or len(current) > 20:
                return result
            if maximum == b"max":
                continue
            if not maximum.isdigit() or len(maximum) > 20 or int(maximum) < 1:
                return result
            budgets.append(max(0, int(maximum) - int(current)))
        if budgets:
            available = min(budgets)
            result.update(
                available_bytes=available,
                admitted=available >= required,
                reason="sufficient_bounded_headroom"
                if available >= required
                else "insufficient_memory_headroom",
            )
    except (LearningError, OSError, UnicodeError, ValueError):
        pass
    return result


def _require_capacity(limits: dict) -> None:
    result = _capacity(limits)
    if not result["admitted"]:
        _fail(result["reason"])


def _bounded_config(raw: bytes) -> dict:
    config = _json(raw)
    if not isinstance(config, dict) or set(config) != {"model", "training"}:
        _fail("invalid_training_config")
    model, training = config["model"], config["training"]
    bounds = {
        "dim": (2, 128),
        "layers": (1, 12),
        "kernel_size": (2, 5),
        "max_seq_len": (8, 2048),
        "root_dim": (1, 32),
    }
    if not isinstance(model, dict) or set(model) != set(bounds) | {"root_mode", "margin"}:
        _fail("explicit_bounded_model_config_required")
    if any(not _integer(model[k], *bounds[k]) for k in bounds):
        _fail("model_limit_exceeded")
    if model["root_mode"] not in ("none", "ordered", "bag") or not _number(
        model["margin"], 0.01, 10
    ):
        _fail("invalid_training_config")
    if model["max_seq_len"] > 1 + (model["kernel_size"] - 1) * ((1 << model["layers"]) - 1):
        _fail("model_receptive_field_too_small")
    defaults = {
        "epochs": 1,
        "batch_size": 1,
        "accumulation_steps": 1,
        "learning_rate": 0.0003,
        "weight_decay": 0.0,
        "grad_clip": 1.0,
        "seed": 17,
        "amp": "none",
        "device": "cpu",
    }
    if not isinstance(training, dict) or set(training) - defaults.keys():
        _fail("invalid_training_config")
    if training.get("device") != "cpu" or training.get("amp", "none") != "none":
        _fail("explicit_cpu_training_required")
    effective = defaults | training
    for key, high in {
        "epochs": 100,
        "batch_size": 8,
        "accumulation_steps": 8,
        "seed": 2**31 - 1,
    }.items():
        if not _integer(effective[key], 0 if key == "seed" else 1, high):
            _fail("training_limit_exceeded")
    for key, low, upper in (
        ("learning_rate", 1e-8, 0.1),
        ("weight_decay", 0, 1),
        ("grad_clip", 0.01, 100),
    ):
        if not _number(effective[key], low, upper):
            _fail("training_limit_exceeded")
    return config


def _inventory(bundle: Path, limits: dict) -> dict[str, dict]:
    bundle = _directory(bundle)
    files: dict[str, dict] = {}
    total = 0
    directory_count = 0
    for directory, dirs, names in os.walk(bundle, followlinks=False):
        directory_count += 1
        if directory_count > limits["max_files"]:
            _fail("bundle_limit_exceeded")
        base = Path(directory)
        for name in dirs:
            item = base / name
            relative_directory = item.relative_to(bundle)
            if (
                item.is_symlink()
                or relative_directory.parts[0] != "assets"
                or len(relative_directory.parts) > 8
            ):
                _fail("unsafe_bundle_directory")
        for name in names:
            item = base / name
            relative = item.relative_to(bundle).as_posix()
            if relative == "approval.json":
                continue
            if relative not in INPUT_NAMES and not relative.startswith("assets/"):
                _fail("unexpected_bundle_file")
            if len(relative) > 240 or any(ord(c) < 32 for c in relative):
                _fail("unsafe_bundle_path")
            raw = _read(item, limits["max_file_bytes"])
            total += len(raw)
            files[relative] = {"sha256": _digest(raw), "bytes": len(raw)}
            if len(files) > limits["max_files"] or total > limits["max_bundle_bytes"]:
                _fail("bundle_limit_exceeded")
    if not INPUT_NAMES <= files.keys():
        _fail("missing_bundle_inputs")
    _bounded_config(_read(bundle / "config.json", 32 * 1024))
    for split in ("train", "dev", "sources"):
        raw = _read(bundle / f"{split}.jsonl", limits["max_file_bytes"])
        count = len(raw.splitlines())
        maximum = limits[f"max_{split}_examples"] if split != "sources" else limits["max_files"]
        if not 1 <= count <= maximum:
            _fail("dataset_row_limit_exceeded")
    referenced = set()
    for source in _rows(bundle / "sources.jsonl", limits):
        if not isinstance(source, dict) or not isinstance(source.get("local_path"), str):
            _fail("invalid_source_asset_path")
        name = source["local_path"]
        relative_asset = Path(name)
        if (
            not name.startswith("assets/")
            or relative_asset.is_absolute()
            or ".." in relative_asset.parts
            or relative_asset.as_posix() != name
        ):
            _fail("invalid_source_asset_path")
        if name not in files or files[name]["sha256"] != source.get("sha256"):
            _fail("original_source_asset_hash_mismatch")
        referenced.add(name)
    if referenced != set(files) - INPUT_NAMES:
        _fail("unreferenced_asset_in_bundle")
    return files


def _rows(path: Path, limits: dict) -> list[dict]:
    return [_json(line) for line in _read(path, limits["max_file_bytes"]).splitlines()]


def _evaluation_identity(snapshot: Path, limits: dict) -> str:
    dev = _rows(snapshot / "dev.jsonl", limits)
    ids = {sid for row in dev for sid in row["provenance"]["source_ids"]}
    sources = [row for row in _rows(snapshot / "sources.jsonl", limits) if row["source_id"] in ids]
    return _digest(
        _canonical(
            {
                "dev_sha256": _hash_file(snapshot / "dev.jsonl"),
                "sources": sorted(sources, key=lambda row: row["source_id"]),
                "max_new_tokens": limits["max_new_tokens"],
                "hinge_margin": _json(_read(snapshot / "config.json"))["model"]["margin"],
                "selection": "all_development_rows",
            }
        )
    )


def _require_accumulated(previous: Path, snapshot: Path, limits: dict, candidate_id: str) -> None:
    old_inventory = _inventory(previous, LIMIT_CAPS)
    if _digest(_canonical(old_inventory)) != candidate_id:
        _fail("previous_snapshot_integrity_failed")
    for name in ("train.jsonl", "sources.jsonl"):
        key = "id" if name == "train.jsonl" else "source_id"
        current = {row[key]: row for row in _rows(snapshot / name, limits)}
        if any(current.get(row[key]) != row for row in _rows(previous / name, LIMIT_CAPS)):
            _fail("accumulated_original_snapshot_required")


def bundle_digest(bundle: str | Path, *, limits: dict | None = None) -> str:
    """Operator helper: exact fixed-input/asset digest, excluding approval.json."""
    return _digest(_canonical(_inventory(Path(bundle), limits or LIMITS)))


def _approval(bundle: Path, digest: str) -> str:
    raw = _read(bundle / "approval.json", 16 * 1024)
    approval = _json(raw)
    keys = {
        "schema_version",
        "bundle_sha256",
        "approved",
        "original_data_attested",
        "reviewer_id",
        "evidence",
    }
    if not isinstance(approval, dict) or set(approval) != keys:
        _fail("invalid_bundle_approval")
    if (
        approval["schema_version"] != APPROVAL_SCHEMA
        or approval["bundle_sha256"] != digest
        or approval["approved"] is not True
        or approval["original_data_attested"] is not True
        or not isinstance(approval["reviewer_id"], str)
        or not SAFE_ID.fullmatch(approval["reviewer_id"])
        or not isinstance(approval["evidence"], str)
        or not 1 <= len(approval["evidence"].strip()) <= 2000
    ):
        _fail("unapproved_original_data")
    return _digest(raw)


def _snapshot(bundle: Path, target: Path, inventory: dict, limits: dict) -> None:
    target.mkdir(mode=0o700)
    for name, expected in sorted(inventory.items()):
        raw = _read(bundle / name, limits["max_file_bytes"])
        if {"sha256": _digest(raw), "bytes": len(raw)} != expected:
            _fail("bundle_changed_during_snapshot")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with destination.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        destination.chmod(0o400)
    if _inventory(target, limits) != inventory:
        _fail("snapshot_integrity_failed")
    for directory, _, _ in os.walk(target, topdown=False):
        _fsync_dir(Path(directory))


def _new_bytes(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o400)
    _fsync_dir(path.parent)


def _implementation() -> dict[str, str]:
    rows = _json(_read(SOURCE_ROOT / "research/registry/runtime_sources.json"))
    if not isinstance(rows, list) or len(rows) != 12:
        _fail("invalid_runtime_source_registry")
    result = {}
    for row in rows:
        name = row["path"]
        if not isinstance(name, str) or not name.startswith(("mizan_reply/", "mizan_research/")):
            _fail("invalid_runtime_source_registry")
        path = SOURCE_ROOT / name
        if not path.resolve().is_relative_to(SOURCE_ROOT) or _hash_file(path) != row["sha256"]:
            _fail("pinned_runtime_source_changed")
        result[name] = row["sha256"]
    return result


def _initial_state() -> dict:
    return {"schema_version": SCHEMA, "generation": 0, "active": None, "rollback_chain": []}


def _state(root: Path) -> dict:
    path = root / "registry.json"
    if not path.exists() and not path.is_symlink():
        if (root / "initialized.json").exists():
            _fail("initialized_registry_missing")
        return _initial_state()
    value = _json(_read(path))
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "generation", "active", "rollback_chain"}
        or value["schema_version"] != SCHEMA
        or not _integer(value["generation"], 0, 1_000_000)
        or not isinstance(value["rollback_chain"], list)
        or len(value["rollback_chain"]) > 256
    ):
        _fail("invalid_registry")
    for entry in [value["active"], *value["rollback_chain"]]:
        if entry is None:
            continue
        if (
            not isinstance(entry, dict)
            or set(entry) != {"candidate_id", "sha256", "receipt_sha256"}
            or any(not isinstance(entry[k], str) or not SHA.fullmatch(entry[k]) for k in entry)
        ):
            _fail("invalid_registry_entry")
    return value


def _candidate_path(root: Path, candidate_id: str) -> Path:
    if not isinstance(candidate_id, str) or not SHA.fullmatch(candidate_id):
        _fail("invalid_candidate_id")
    return _directory(root / "candidates" / candidate_id)


def _save_receipt(directory: Path, receipt: dict) -> None:
    _atomic(directory / "receipt.json", receipt, exclusive=True)
    _atomic(
        directory / "receipt.sha256",
        {"sha256": _hash_file(directory / "receipt.json")},
        exclusive=True,
    )


def _candidate_receipt(
    directory: Path, candidate_id: str, *, expected_hash: str | None = None
) -> dict:
    raw = _read(directory / "receipt.json")
    identity = _json(_read(directory / "receipt.sha256", 256))
    receipt = _json(raw)
    if (
        not isinstance(identity, dict)
        or identity != {"sha256": _digest(raw)}
        or (expected_hash is not None and expected_hash != _digest(raw))
        or not isinstance(receipt, dict)
        or receipt.get("schema_version") != SCHEMA
        or receipt.get("bundle_sha256") != candidate_id
        or receipt.get("status") not in ("accepted", "rejected", "failed", "interrupted")
        or not isinstance(receipt.get("gates"), dict)
        or type(receipt["gates"].get("passed")) is not bool
    ):
        _fail("invalid_candidate_receipt")
    checkpoint_hash = receipt.get("checkpoint_sha256")
    if checkpoint_hash is not None and (
        not isinstance(checkpoint_hash, str)
        or not SHA.fullmatch(checkpoint_hash)
        or _hash_file(directory / "checkpoint.pt") != checkpoint_hash
    ):
        _fail("candidate_artifact_integrity_failed")
    if receipt["status"] == "accepted" and (
        checkpoint_hash is None or not receipt["gates"]["passed"]
    ):
        _fail("invalid_candidate_receipt")
    if receipt["status"] == "accepted":
        for name in ("approval", "policy"):
            expected = receipt.get(f"{name}_sha256")
            if (
                not isinstance(expected, str)
                or not SHA.fullmatch(expected)
                or _hash_file(directory / f"{name}.json") != expected
            ):
                _fail("candidate_provenance_integrity_failed")
    return receipt


def _resolve_entry(root: Path, entry: dict | None, generation: int) -> dict | None:
    if entry is None:
        return None
    directory = _candidate_path(root, entry["candidate_id"])
    receipt = _candidate_receipt(
        directory, entry["candidate_id"], expected_hash=entry["receipt_sha256"]
    )
    if (
        receipt.get("schema_version") != SCHEMA
        or receipt.get("bundle_sha256") != entry["candidate_id"]
        or receipt.get("status") != "accepted"
        or not isinstance(receipt.get("gates"), dict)
        or receipt["gates"].get("passed") is not True
        or receipt.get("checkpoint_sha256") != entry["sha256"]
    ):
        _fail("active_artifact_integrity_failed")
    return {
        "path": str(directory / "checkpoint.pt"),
        "sha256": entry["sha256"],
        "generation": generation,
    }


def resolve_active(root: str | Path) -> dict | None:
    """Select one atomic registry snapshot. Invalid artifacts raise; never fallback."""
    root = Path(root).expanduser().absolute()
    if not root.exists():
        return None
    root = _directory(root)
    state = _state(root)
    return _resolve_entry(root, state["active"], state["generation"])


def _safe_selection(entry: dict | None, generation: int) -> dict | None:
    return (
        {"candidate_id": entry["candidate_id"], "sha256": entry["sha256"], "generation": generation}
        if entry
        else None
    )


def registry_status(root: str | Path) -> dict:
    """Small provider-health view of one registry snapshot, without corpus scans."""
    root = Path(root).expanduser().absolute()
    result: dict = {
        "configured": True,
        "initialized": False,
        "status": "idle",
        "generation": 0,
        "active": None,
        "previous": None,
        "ready_for_general_chat": False,
    }
    if not root.exists():
        return result
    try:
        root = _directory(root)
        state = _state(root)
        _resolve_entry(root, state["active"], state["generation"])
        result.update(
            initialized=(root / "initialized.json").exists(),
            generation=state["generation"],
            active=_safe_selection(state["active"], state["generation"]),
        )
        if state["rollback_chain"]:
            result["previous"] = _safe_selection(
                state["rollback_chain"][-1], state["generation"] - 1
            )
    except (LearningError, OSError, TypeError, KeyError) as exc:
        result.update(
            status="invalid",
            active=None,
            reason=str(exc) if isinstance(exc, LearningError) else "invalid_learning_state",
        )
    return result


def _busy(root: Path) -> bool:
    if not (root / "cycle.lock").exists():
        return False
    try:
        with _writer(root):
            return False
    except LearningBusy:
        return True


def list_bundles(root: str | Path) -> list[dict]:
    root = Path(root).expanduser().absolute()
    bundles = root / "bundles"
    if not bundles.exists():
        return []
    try:
        _directory(root)
        _directory(bundles)
        policy, _ = _policy(root)
    except LearningError:
        return []
    capacity = _capacity(policy["limits"])
    rows = []
    for path in sorted(bundles.iterdir())[:256]:
        if not SAFE_ID.fullmatch(path.name):
            continue
        row = {"bundle_id": path.name, "state": "pending"}
        try:
            inventory = _inventory(path, policy["limits"])
            digest = _digest(_canonical(inventory))
            row["bundle_sha256"] = digest
            if (root / "candidates" / digest).exists():
                row["state"] = "processed"
            elif not (path / "approval.json").exists():
                row["state"] = "pending"
            else:
                _approval(path, digest)
                row["state"] = "ready" if policy["enabled"] and capacity["admitted"] else "pending"
                if not capacity["admitted"]:
                    row["reason"] = capacity["reason"]
        except LearningError as exc:
            row.update(state="invalid", reason=str(exc))
        rows.append(row)
    return rows


def status(root: str | Path) -> dict:
    root = Path(root).expanduser().absolute()
    result: dict = {
        "configured": True,
        "initialized": False,
        "status": "idle",
        "generation": 0,
        "active": None,
        "previous": None,
        "busy": False,
        "policy_ready": False,
        "last_run": None,
        "runs": [],
        "bundles": [],
        "ready_for_general_chat": False,
    }
    if not root.exists():
        return result
    try:
        root = _directory(root)
        state = _state(root)
        _resolve_entry(root, state["active"], state["generation"])
        result.update(
            initialized=(root / "initialized.json").exists(),
            generation=state["generation"],
            active=_safe_selection(state["active"], state["generation"]),
            busy=_busy(root),
        )
        if state["rollback_chain"]:
            result["previous"] = _safe_selection(
                state["rollback_chain"][-1], state["generation"] - 1
            )
        try:
            policy, policy_hash = _policy(root)
            result.update(
                policy_ready=policy["enabled"],
                policy_sha256=policy_hash,
                first_model_allowed=policy["allow_first_model"],
                limits=policy["limits"],
                capacity=_capacity(policy["limits"]),
            )
        except LearningError as exc:
            result["policy_reason"] = str(exc)
        result["bundles"] = list_bundles(root)
        if (root / "last_run.json").exists():
            result["last_run"] = _json(_read(root / "last_run.json"))
        candidates = root / "candidates"
        if candidates.exists():
            _directory(candidates)
            for directory in sorted(candidates.iterdir())[-64:]:
                if SHA.fullmatch(directory.name) and (directory / "receipt.json").exists():
                    try:
                        receipt = _candidate_receipt(directory, directory.name)
                    except LearningError as exc:
                        result["runs"].append(
                            {
                                "bundle_sha256": directory.name,
                                "status": "invalid",
                                "reason": str(exc),
                            }
                        )
                        continue
                    result["runs"].append(
                        {
                            k: receipt.get(k)
                            for k in ("bundle_sha256", "status", "finished_at", "gates", "metrics")
                        }
                    )
        result["status"] = "running" if result["busy"] else "idle"
    except (LearningError, OSError, TypeError, KeyError) as exc:
        result.update(
            status="invalid",
            active=None,
            reason=str(exc) if isinstance(exc, LearningError) else "invalid_learning_state",
        )
    return result


def _terminate(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=5)
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    # Descendants can outlive a cooperative parent; kill the complete session
    # even when wait() already reaped its leader before releasing our lock.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _stage(
    kind: str, directory: Path, payload: dict, limits: dict, deadline: float, lock_fd: int
) -> dict:
    _require_capacity(limits)
    remaining = deadline - time.monotonic()
    seconds = min(
        limits[
            "train_seconds"
            if kind == "train"
            else "preflight_seconds"
            if kind == "preflight"
            else "evaluation_seconds"
        ],
        remaining,
    )
    if seconds <= 0:
        _fail("cycle_deadline_exceeded")
    request = payload | {
        "kind": kind,
        "limits": limits,
        "cpu_seconds": math.ceil(seconds),
        "parent_pid": os.getpid(),
    }
    request_path = directory / f"{kind}-request.json"
    _atomic(request_path, request, exclusive=True)
    output = directory / f"{kind}-result.json"
    environment = {
        "PATH": os.defpath,
        "PYTHONPATH": str(BACKEND_ROOT) + os.pathsep + str(SOURCE_ROOT),
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": str(limits["cpu_threads"]),
        "MKL_NUM_THREADS": str(limits["cpu_threads"]),
        "OPENBLAS_NUM_THREADS": str(limits["cpu_threads"]),
        "NUMEXPR_NUM_THREADS": str(limits["cpu_threads"]),
        "CUDA_VISIBLE_DEVICES": "",
        "WORLD_SIZE": "1",
        "RANK": "0",
        "LOCAL_RANK": "0",
    }
    with (directory / f"{kind}.log").open("xb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "mizan_owned.learning_worker", str(request_path), str(output)],
            cwd=SOURCE_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            pass_fds=(lock_fd,),
        )
        try:
            try:
                code = process.wait(timeout=seconds)
            except subprocess.TimeoutExpired as exc:
                raise LearningError(f"{kind}_timeout") from exc
            if code:
                _fail(f"{kind}_failed")
        finally:
            _terminate(process)
    result = _json(_read(output, 4 * 1024 * 1024))
    if not isinstance(result, dict):
        _fail("invalid_worker_result")
    return result


def _metrics(report: dict, count: int) -> dict:
    metrics = report.get("metrics", {})
    rows = report.get("generation", [])
    if (
        not isinstance(metrics, dict)
        or not isinstance(rows, list)
        or len(rows) != count
        or metrics.get("examples") != count
    ):
        _fail("incomplete_development_evaluation")
    hinge = metrics.get("hinge_per_target_token")
    accuracy = metrics.get("teacher_forced_byte_accuracy_including_eos")
    if not _number(hinge, 0, 1e9) or not _number(accuracy, 0, 1):
        _fail("invalid_development_metrics")
    if any(
        not isinstance(row, dict)
        or type(row.get("eos")) is not bool
        or type(row.get("reference_exact_match")) is not bool
        for row in rows
    ):
        _fail("invalid_generation_metrics")
    return {
        "dev_examples": count,
        "hinge_per_target_token": hinge,
        "byte_accuracy": accuracy,
        "generation_exact_match": sum(row["reference_exact_match"] and row["eos"] for row in rows)
        / count,
        "generation_eos_rate": sum(row["eos"] for row in rows) / count,
        "factual_accuracy_established": False,
    }


def _gates(candidate: dict, baseline: dict | None, policy: dict, train_count: int) -> dict:
    gates = policy["gates"]
    reasons: list[str] = []
    comparisons = (
        (train_count >= gates["min_train_examples"], "insufficient_train_examples"),
        (candidate["dev_examples"] >= gates["min_dev_examples"], "insufficient_dev_examples"),
        (candidate["hinge_per_target_token"] <= gates["max_dev_hinge"], "dev_hinge_above_limit"),
        (
            candidate["byte_accuracy"] >= gates["min_dev_byte_accuracy"],
            "dev_byte_accuracy_below_limit",
        ),
        (
            candidate["generation_exact_match"] >= gates["min_generation_exact_match"],
            "generation_exact_below_limit",
        ),
        (
            candidate["generation_eos_rate"] >= gates["min_generation_eos_rate"],
            "generation_eos_below_limit",
        ),
    )
    reasons.extend(reason for passed, reason in comparisons if not passed)
    if baseline is None:
        if not policy["allow_first_model"]:
            reasons.append("first_model_requires_operator_policy")
    else:
        for passed, reason in (
            (
                candidate["hinge_per_target_token"]
                <= baseline["hinge_per_target_token"] + gates["max_hinge_regression"],
                "hinge_regression",
            ),
            (
                candidate["byte_accuracy"] + gates["max_byte_accuracy_drop"]
                >= baseline["byte_accuracy"],
                "byte_accuracy_regression",
            ),
            (
                candidate["generation_exact_match"] + gates["max_generation_exact_drop"]
                >= baseline["generation_exact_match"],
                "generation_exact_regression",
            ),
            (
                candidate["generation_eos_rate"] >= baseline["generation_eos_rate"],
                "generation_eos_regression",
            ),
        ):
            if not passed:
                reasons.append(reason)
    return {
        "passed": not reasons,
        "reasons": reasons,
        "selection_split": "dev",
        "scope": "measured_byte_and_generation_regression_not_general_or_factual_correctness",
    }


def _public_receipt(receipt: dict, state: dict) -> dict:
    return receipt | {
        "activated": bool(
            state["active"] and state["active"]["candidate_id"] == receipt["bundle_sha256"]
        ),
        "generation": state["generation"],
    }


def run_cycle(root: str | Path, bundle_id: str) -> dict:
    if not isinstance(bundle_id, str) or not SAFE_ID.fullmatch(bundle_id):
        _fail("invalid_bundle_id")
    root = Path(root).expanduser().absolute()
    if root.resolve().is_relative_to(SOURCE_ROOT):
        _fail("learning_root_must_be_outside_source_tree")
    with _writer(root) as lock_fd:
        policy, policy_hash = _policy(root)
        if not policy["enabled"]:
            _fail("learning_policy_disabled")
        limits = policy["limits"]
        deadline = time.monotonic() + limits["cycle_seconds"]
        state = _state(root)
        active = _resolve_entry(root, state["active"], state["generation"])
        bundle = _directory(root / "bundles" / bundle_id)
        inventory = _inventory(bundle, limits)
        digest = _digest(_canonical(inventory))
        approval_hash = _approval(bundle, digest)
        candidates = _directory(root / "candidates", create=True)
        directory = candidates / digest
        if directory.exists():
            directory = _directory(directory)
            if (directory / "receipt.json").exists():
                return _public_receipt(_candidate_receipt(directory, digest), state)
            # An incomplete previous attempt cannot silently resume or activate.
            interrupted_receipt = {
                "schema_version": SCHEMA,
                "bundle_sha256": digest,
                "status": "interrupted",
                "finished_at": time.time(),
                "gates": {"passed": False, "reasons": ["previous_attempt_interrupted"]},
            }
            _save_receipt(directory, interrupted_receipt)
            _atomic(root / "last_run.json", interrupted_receipt)
            return _public_receipt(interrupted_receipt, state)
        try:
            _require_capacity(limits)
        except LearningError as exc:
            _atomic(
                root / "last_run.json",
                {
                    "status": "refused",
                    "bundle_sha256": digest,
                    "reason": str(exc),
                    "finished_at": time.time(),
                },
            )
            raise
        directory.mkdir(mode=0o700)
        receipt: dict = {
            "schema_version": SCHEMA,
            "bundle_sha256": digest,
            "approval_sha256": approval_hash,
            "policy_sha256": policy_hash,
            "started_at": time.time(),
            "status": "running",
            "training_mode": "fresh_weights_from_accumulated_approved_original_snapshot",
            "original_data": "operator_attestation_plus_structure_assets_hashes_and_split_checks",
            "factual_accuracy_established": False,
            "ready_for_general_chat": False,
            "baseline_generation": state["generation"],
        }
        try:
            if not (root / "initialized.json").exists():
                _atomic(root / "initialized.json", {"schema_version": SCHEMA}, exclusive=True)
                _atomic(root / "registry.json", state)
            receipt["implementation_sha256"] = _implementation()
            _atomic(
                root / "last_run.json",
                {"bundle_sha256": digest, "status": "running", "stage": "preflight"},
            )
            snapshot = directory / "snapshot"
            _snapshot(bundle, snapshot, inventory, limits)
            approval_raw = _read(bundle / "approval.json", 16 * 1024)
            if _digest(approval_raw) != approval_hash:
                _fail("approval_changed_during_cycle")
            _new_bytes(directory / "approval.json", approval_raw)
            _atomic(directory / "inventory.json", inventory, exclusive=True)
            policy_raw = _read(root / "policy.json", 32 * 1024)
            if _digest(policy_raw) != policy_hash:
                _fail("registry_or_policy_changed_during_cycle")
            _new_bytes(directory / "policy.json", policy_raw)
            common = {"snapshot": str(snapshot), "output_dir": str(directory / "training")}
            preflight = _stage("preflight", directory, common, limits, deadline, lock_fd)
            train_count, dev_count = preflight["train_examples"], preflight["dev_examples"]
            if not _integer(train_count, 1, limits["max_train_examples"]) or not _integer(
                dev_count, 1, limits["max_dev_examples"]
            ):
                _fail("preflight_count_limit_exceeded")
            if not _integer(preflight["parameters"], 1, limits["max_parameters"]):
                _fail("parameter_limit_exceeded")
            receipt["data"] = preflight["data_manifest"] | {
                "train_examples": train_count,
                "dev_examples": dev_count,
            }
            receipt["evaluation_suite_sha256"] = _evaluation_identity(snapshot, limits)
            baseline = None
            if active:
                previous_directory = _candidate_path(root, state["active"]["candidate_id"])
                previous = _json(_read(previous_directory / "receipt.json"))
                if previous["evaluation_suite_sha256"] != receipt["evaluation_suite_sha256"]:
                    _fail("development_suite_changed")
                _require_accumulated(
                    previous_directory / "snapshot",
                    snapshot,
                    limits,
                    state["active"]["candidate_id"],
                )
                baseline_report = _stage(
                    "baseline",
                    directory,
                    common
                    | {
                        "checkpoint": active["path"],
                        "expected_sha256": active["sha256"],
                        "dev_count": dev_count,
                    },
                    limits,
                    deadline,
                    lock_fd,
                )
                baseline = _metrics(baseline_report, dev_count)
            _atomic(
                root / "last_run.json",
                {"bundle_sha256": digest, "status": "running", "stage": "training"},
            )
            _stage("train", directory, common, limits, deadline, lock_fd)
            checkpoint = directory / "checkpoint.pt"
            raw = _read(directory / "training/latest.pt", 256 * 1024 * 1024)
            with checkpoint.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            checkpoint.chmod(0o400)
            receipt["checkpoint_sha256"] = _digest(raw)
            _fsync_dir(directory)
            _atomic(
                root / "last_run.json",
                {"bundle_sha256": digest, "status": "running", "stage": "evaluation"},
            )
            report = _stage(
                "evaluate",
                directory,
                common
                | {
                    "checkpoint": str(checkpoint),
                    "expected_sha256": receipt["checkpoint_sha256"],
                    "dev_count": dev_count,
                },
                limits,
                deadline,
                lock_fd,
            )
            if (
                report.get("checkpoint_sha256") != receipt["checkpoint_sha256"]
                or report.get("split") != "dev"
                or report.get("dataset_sha256") != receipt["data"]["dev_sha256"]
            ):
                _fail("candidate_evaluation_identity_mismatch")
            candidate = _metrics(report, dev_count)
            receipt["metrics"] = {"candidate": candidate, "baseline": baseline}
            receipt["gates"] = _gates(candidate, baseline, policy, train_count)
            receipt["status"] = "accepted" if receipt["gates"]["passed"] else "rejected"
            if time.monotonic() >= deadline:
                _fail("cycle_deadline_exceeded")
            if (
                _inventory(snapshot, limits) != inventory
                or _hash_file(checkpoint) != receipt["checkpoint_sha256"]
            ):
                _fail("candidate_artifact_changed")
            if _state(root) != state or _policy(root)[1] != policy_hash:
                _fail("registry_or_policy_changed_during_cycle")
            if _approval(bundle, digest) != approval_hash:
                _fail("approval_changed_during_cycle")
            receipt["finished_at"] = time.time()
            _save_receipt(directory, receipt)
            if receipt["status"] == "accepted":
                if len(state["rollback_chain"]) >= 256:
                    _fail("rollback_history_limit_reached")
                entry = {
                    "candidate_id": digest,
                    "sha256": receipt["checkpoint_sha256"],
                    "receipt_sha256": _hash_file(directory / "receipt.json"),
                }
                _resolve_entry(root, entry, state["generation"] + 1)
                state = state | {
                    "generation": state["generation"] + 1,
                    "active": entry,
                    "rollback_chain": state["rollback_chain"] + [state["active"]],
                }
                _atomic(root / "registry.json", state)
        except BaseException as exc:
            # A child is always terminated/reaped by _stage before reaching here.
            # os.replace may already have committed when a signal or fsync error
            # reaches us. Reconcile the actual selection instead of reporting an
            # interrupted job while silently leaving its model active.
            current = _state(root)
            if (
                current["generation"] == receipt["baseline_generation"] + 1
                and current["active"]
                and current["active"]["candidate_id"] == digest
            ):
                _resolve_entry(root, current["active"], current["generation"])
                committed = _candidate_receipt(directory, digest)
                durability_confirmed = False
                try:
                    _fsync_dir(root)
                    durability_confirmed = True
                except (OSError, LearningError):
                    pass
                with contextlib.suppress(OSError, LearningError):
                    _atomic(root / "last_run.json", committed)
                return _public_receipt(committed, current) | {
                    "completion_note": "activation_observed_before_exception",
                    "activation_durability_confirmed": durability_confirmed,
                }
            receipt.update(
                status="interrupted"
                if isinstance(exc, (LearningInterrupted, KeyboardInterrupt, SystemExit))
                else "failed",
                finished_at=time.time(),
                gates={
                    "passed": False,
                    "reasons": [str(exc) if isinstance(exc, LearningError) else "cycle_failed"],
                },
            )
            if not (directory / "receipt.json").exists():
                _save_receipt(directory, receipt)
            _atomic(root / "last_run.json", receipt)
            if isinstance(exc, (KeyboardInterrupt, SystemExit, LearningInterrupted)):
                raise
            return _public_receipt(receipt, _state(root))
        _atomic(root / "last_run.json", receipt)
        return _public_receipt(receipt, state)


def rollback(root: str | Path, expected_generation: int) -> dict:
    if not _integer(expected_generation, 0, 1_000_000):
        _fail("invalid_expected_generation")
    root = Path(root).expanduser().absolute()
    with _writer(root):
        state = _state(root)
        if state["generation"] != expected_generation:
            _fail("registry_generation_changed")
        if not state["rollback_chain"]:
            _fail("no_previous_selection")
        target = state["rollback_chain"][-1]
        # A broken current checkpoint must not prevent retreat to a valid prior one.
        _resolve_entry(root, target, state["generation"] + 1)
        state = state | {
            "generation": state["generation"] + 1,
            "active": target,
            "rollback_chain": state["rollback_chain"][:-1],
        }
        _atomic(root / "registry.json", state)
        result = {
            "schema_version": SCHEMA,
            "status": "rolled_back",
            "generation": state["generation"],
            "active": _safe_selection(target, state["generation"]),
            "finished_at": time.time(),
        }
        _atomic(root / "last_run.json", result)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "rollback", "digest"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--bundle-id")
    parser.add_argument("--expected-generation", type=int)
    args = parser.parse_args(argv)

    def interrupted(_signum, _frame):
        raise LearningInterrupted("cycle_cancelled")

    for name in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(name, interrupted)
    try:
        if args.command == "run":
            result = run_cycle(args.root, args.bundle_id)
        elif args.command == "rollback":
            result = rollback(args.root, args.expected_generation)
        elif args.command == "digest":
            if not args.bundle_id or not SAFE_ID.fullmatch(args.bundle_id):
                _fail("invalid_bundle_id")
            result = {
                "bundle_sha256": bundle_digest(
                    Path(args.root) / "bundles" / args.bundle_id,
                    limits=_policy(Path(args.root))[0]["limits"],
                )
            }
        else:
            result = status(args.root)
        print(json.dumps(result, allow_nan=False))
        return 0
    except LearningError as exc:
        print(
            json.dumps(
                {
                    "status": "busy" if isinstance(exc, LearningBusy) else "refused",
                    "reason": str(exc),
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
