#!/usr/bin/env python3
"""Run one bounded V2 Quranic objective; never changes the production endpoint.

Resume a private V2 candidate and sibling training_state.pt to continue model
and AdamW state. A tiny fresh model is only an engineering smoke test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ruh_model.config import RuhConfig
from ruh_model.train_sequence import run_training


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--path", choices=("continuation", "morphology", "grounded_qa"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--max-seconds", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--precision", choices=("float32", "bfloat16"), default="float32")
    args = parser.parse_args()
    if not 0 < args.max_seconds <= 1800:
        raise ValueError("Each run has a hard 30-minute training limit")
    manifest = json.loads((args.data_dir / "manifest.json").read_text())
    spec = manifest["paths"][args.path]
    data = (args.data_dir / spec["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError("Prepared data hash differs from the verified manifest")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    config = RuhConfig(
        d_model=64,
        n_layers=2,
        n_heads=4,
        ffn_multiplier=2,
        moe_interval=0,
        n_roots=4000,
        max_seq_len=384,
        tokenizer_version=2,
        device=args.device,
    )
    if args.resume_from and not (args.resume_from.parent / "training_state.pt").is_file():
        raise ValueError("Resumption requires the original AdamW training_state.pt")
    report = run_training(
        rows,
        args.output,
        config=config,
        steps=args.steps,
        batch_size=args.batch_size,
        max_seconds=args.max_seconds,
        seed=42,
        resume_from=args.resume_from,
        precision=args.precision,
        checkpoint_every_seconds=120,
        source_metadata={
            "objective": args.path,
            "manifest_sha256": hashlib.sha256(
                (args.data_dir / "manifest.json").read_bytes()
            ).hexdigest(),
            "sources": manifest["source_snapshots"],
            "split_policy": manifest["split_policy"],
        },
    )
    expected = set(spec["validation_surahs"])
    # Report linkage is retained beside model/optimizer for durable restoration.
    (args.output / "quranic-run.json").write_text(
        json.dumps(
            {
                "path": args.path,
                "manifest_sha256": hashlib.sha256(
                    (args.data_dir / "manifest.json").read_bytes()
                ).hexdigest(),
                "data_sha256": spec["sha256"],
                "held_out_surahs": sorted(expected),
                "resumed": args.resume_from is not None,
                "training_steps": report["training"]["steps"],
                "engineering_smoke_only": args.resume_from is None,
                "promotion_approved": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
