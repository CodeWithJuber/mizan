#!/usr/bin/env python3
"""Generate exact held-out predictions separately from teacher-forced loss."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch
from ruh_model.data.quranic_evaluation import summarize_scores
from ruh_model.data.sequence import split_records
from ruh_model.model import RuhModel
from ruh_model.tokenizer.conversation import serialize_messages


@torch.no_grad()
def generate_predictions(candidate: Path, data_dir: Path, path: str, device: str, samples: int):
    manifest = json.loads((data_dir / "manifest.json").read_text())
    spec = manifest["paths"][path]
    data = (data_dir / spec["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError("Prepared data hash differs from the verified manifest")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    _, validation = split_records(rows, seed=42)
    selected, seen_surahs = [], set()
    for row in validation:
        surah = row["verse_id"].split(":")[0]
        if surah not in seen_surahs:
            selected.append(row)
            seen_surahs.add(surah)
        if len(selected) == samples:
            break
    model = RuhModel.from_pretrained(str(candidate))
    if model.config.tokenizer_version != 2:
        raise ValueError("Quranic evaluation requires the exact lossless V2 tokenizer")
    model.config.device = device
    model = model.to(device).eval()
    predictions = []
    for row in selected:
        if row.get("messages"):
            prompt = serialize_messages(row["messages"][:-1])
            expected = " " + row["messages"][-1]["content"]
        else:
            boundary = max(1, len(row["text"]) // 3)
            prompt, expected = row["text"][:boundary], row["text"][boundary:]
        encoded = model.tokenizer.encode(prompt, add_eos=False)[-model.config.max_seq_len :]
        roots = torch.tensor([[root for root, _ in encoded]], device=device)
        patterns = torch.tensor([[pattern for _, pattern in encoded]], device=device)
        tokens = model.generate(
            roots, patterns, max_new_tokens=min(512, len(expected.encode()) + 64), temperature=0
        )[0, roots.shape[1] :].tolist()
        generated = model.tokenizer.decode([(token, 0) for token in tokens])
        predictions.append(
            {
                "task": row["task"],
                "verse_id": row["verse_id"],
                "prompt": prompt,
                "expected": expected,
                "generated": generated,
                "generated_tokens": len(tokens),
                "attribution": "Pickthall" if path == "grounded_qa" else "QAC 0.4",
            }
        )
    return predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--path", choices=("continuation", "morphology", "grounded_qa"), required=True
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.samples <= 32:
        raise ValueError("Generation evaluation is bounded to 1-32 held-out samples")
    predictions = generate_predictions(
        args.candidate, args.data_dir, args.path, args.device, args.samples
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "quranic-predictions.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions)
    )
    report = summarize_scores(predictions)
    (args.output_dir / "quranic-evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {
                "samples": report["samples"],
                "metrics": report["metrics"],
                "promotion_approved": False,
            }
        )
    )


if __name__ == "__main__":
    main()
