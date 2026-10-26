"""Private CPU worker for learning_cycle; never accepts a user-provided command."""

from __future__ import annotations

import ctypes
import os
import resource
import signal
import sys
from dataclasses import asdict
from pathlib import Path

from .learning_cycle import LearningError, _atomic, _hash_file, _json, _read


def _limits(request: dict) -> None:
    if sys.platform != "linux":
        raise LearningError("linux_resource_control_required")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise LearningError("parent_death_control_unavailable")
    if os.getppid() != request["parent_pid"]:
        raise LearningError("parent_already_exited")
    os.umask(0o077)
    memory = request["limits"]["memory_mb"] * 1024 * 1024
    cpu = request["cpu_seconds"]
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(request: dict) -> dict:
    _limits(request)
    import torch

    torch.set_num_threads(request["limits"]["cpu_threads"])
    torch.set_num_interop_threads(1)
    snapshot = Path(request["snapshot"])
    common = [
        "--train-data",
        str(snapshot / "train.jsonl"),
        "--dev-data",
        str(snapshot / "dev.jsonl"),
        "--sources",
        str(snapshot / "sources.jsonl"),
    ]
    kind = request["kind"]
    from mizan_reply.cli import main

    if kind in ("preflight", "train"):
        result = main(
            [
                kind,
                *common,
                "--config",
                str(snapshot / "config.json"),
                "--output-dir",
                request["output_dir"],
            ]
        )
        if kind == "train":
            from mizan_reply.checkpoint import load_checkpoint

            checkpoint = load_checkpoint(Path(request["output_dir"]) / "latest.pt")
            if checkpoint["epoch_completed"] < 1 or checkpoint["optimizer_steps"] < 1:
                raise LearningError("training_did_not_update_weights")
        if not isinstance(result, dict):
            raise LearningError("invalid_cli_result")
        return result
    checkpoint_path = request["checkpoint"]
    if _hash_file(Path(checkpoint_path)) != request["expected_sha256"]:
        raise LearningError("evaluation_checkpoint_changed")
    if kind == "evaluate":
        report = snapshot.parent / "development-report.json"
        result = main(
            [
                "evaluate",
                *common,
                "--checkpoint",
                checkpoint_path,
                "--data",
                str(snapshot / "dev.jsonl"),
                "--split",
                "dev",
                "--output",
                str(report),
                "--device",
                "cpu",
                "--batch-size",
                "1",
                "--generate-limit",
                str(request["dev_count"]),
                "--max-new-tokens",
                str(request["limits"]["max_new_tokens"]),
            ]
        )
        if not isinstance(result, dict):
            raise LearningError("invalid_cli_result")
        return result
    if kind != "baseline":
        raise LearningError("unknown_worker_stage")
    # The old model was trained on an older snapshot. Evaluate both models on
    # the same validated, byte-frozen development suite without falsifying its
    # original checkpoint data_manifest (the CLI correctly forbids doing that).
    from mizan_reply.data import encode_prompt, validate_dataset_snapshot
    from mizan_reply.evaluate import load_inference_model
    from mizan_reply.generation import generate
    from mizan_reply.train import RecordDataset, evaluate_encoded

    summary, captured = validate_dataset_snapshot(
        snapshot / "train.jsonl", snapshot / "dev.jsonl", snapshot / "sources.jsonl"
    )
    model, _, digest = load_inference_model(
        checkpoint_path, torch.device("cpu"), include_sha256=True
    )
    if digest != request["expected_sha256"]:
        raise LearningError("baseline_checkpoint_changed")
    records = captured["dev"]
    encoded = RecordDataset(records, model.config.max_seq_len)
    metrics = evaluate_encoded(
        model,
        [encoded[index] for index in range(len(encoded))],
        device=torch.device("cpu"),
        margin=model.config.margin,
    )
    rows = []
    for record in records:
        prompt = encode_prompt(
            record["messages"], record["evidence"], record.get("roots"), model.config.max_seq_len
        )
        result = generate(
            model,
            prompt["input_ids"],
            roots=prompt["roots"],
            max_new_tokens=request["limits"]["max_new_tokens"],
        )
        rows.append(
            asdict(result)
            | {"id": record["id"], "reference_exact_match": result.text == record["target"]["text"]}
        )
    return {
        "checkpoint_sha256": digest,
        "dataset_sha256": summary["file_sha256"]["dev"],
        "split": "dev",
        "metrics": metrics,
        "generation": rows,
        "factual_accuracy_established": False,
    }


def main() -> int:
    request = _json(_read(Path(sys.argv[1])))
    result = run(request)
    _atomic(Path(sys.argv[2]), result, exclusive=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
