"""Frozen-checkpoint diagnostics. These metrics do not establish factual accuracy."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import torch

from .checkpoint import load_checkpoint, load_checkpoint_snapshot
from .model import MizanReplyModel, ModelConfig
from .train import (RecordDataset, assert_new_report_output, manifest_from_snapshot,
                    evaluate_encoded, write_new_report)


def inference_device(name: str) -> torch.device:
    if name == "auto":
        name = "cuda" if torch.cuda.is_available() else "cpu"
    if name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    return torch.device(name)


def load_inference_model(path: str, device: torch.device, *, include_sha256: bool = False):
    checkpoint, digest = load_checkpoint_snapshot(path)
    model = MizanReplyModel(ModelConfig.from_dict(checkpoint["model_config"]))
    model.load_state_dict(checkpoint["model_state"], strict=True)
    result = (model.to(device).eval(), checkpoint)
    return (*result, digest) if include_sha256 else result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--train-data", required=True)
    parser.add_argument("--dev-data", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--data", required=True, help="Original accepted dev or test records")
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--generate-limit", type=int, default=0, help="First N records; no subset cherry-picking or semantic accuracy claim")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    from .data import validate_dataset_snapshot, encode_prompt, file_sha256
    from .generation import generate
    if args.batch_size < 1 or args.generate_limit < 0 or args.max_new_tokens < 1:
        raise ValueError("Invalid batch or generation limit")
    output = assert_new_report_output(args.output)
    validation, captured = validate_dataset_snapshot(args.train_data, args.dev_data, args.sources,
                                                    test_path=args.data if args.split == "test" else None)
    if args.split == "dev" and file_sha256(args.data) != validation["file_sha256"]["dev"]:
        raise ValueError("--data must match --dev-data for development evaluation")
    checkpoint, checkpoint_sha256 = load_checkpoint_snapshot(args.checkpoint)
    if checkpoint["data_manifest"] != manifest_from_snapshot(validation):
        raise ValueError("Training/development/source manifest hashes differ from the checkpoint")
    records = captured[args.split]
    if not records or any(record["split"] != args.split for record in records):
        raise ValueError("Evaluation records must be nonempty and all use the declared split")
    device = inference_device(args.device)
    model = MizanReplyModel(ModelConfig.from_dict(checkpoint["model_config"]))
    model.load_state_dict(checkpoint["model_state"], strict=True)
    model = model.to(device).eval()
    encoded = RecordDataset(records, model.config.max_seq_len)
    metrics = evaluate_encoded(model, encoded, device=device, batch_size=args.batch_size, margin=model.config.margin)
    generation_rows = []
    for record in records[:args.generate_limit]:
        prompt = encode_prompt(record["messages"], record["evidence"], record.get("roots"), model.config.max_seq_len)
        # Fixed user-requested budget; fail explicitly instead of shortening
        # particular test cases after seeing their lengths or outputs.
        result = generate(model, prompt["input_ids"].to(device), roots=prompt["roots"].to(device),
                          max_new_tokens=args.max_new_tokens)
        row = asdict(result)
        row.update({"id": record["id"], "reference_exact_match": result.text == record["target"]["text"],
                    "independently_verified": False})
        generation_rows.append(row)
    report = {"checkpoint_sha256": checkpoint_sha256, "dataset_sha256": validation["file_sha256"][args.split],
              "split": args.split, "validation": validation, "metrics": metrics,
              "generation": generation_rows, "generation_selection": "first_N_in_file_order",
              "generation_budget": args.max_new_tokens, "factual_accuracy_established": False,
              "test_use": "frozen_model_evaluation_do_not_tune_on_these_outputs" if args.split == "test" else "development_diagnostics",
              "limits": ["Byte exact match is not semantic correctness", "Evidence citations and religious interpretations require independent review", "No online learning occurs"]}
    write_new_report(output, report)
    print(json.dumps({"output": str(output), "metrics": metrics}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
