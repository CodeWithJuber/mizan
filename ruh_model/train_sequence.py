"""Bounded, evaluated Bayan v2 sequence-training CLI for Kaggle and CPU smoke.

This starts a new surface model. Legacy root checkpoints are not silently
reinterpreted as lossless text models. Outputs are candidates, never deployed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from dataclasses import asdict
from pathlib import Path

import torch
import torch.nn.functional as functional
from torch.utils.data import DataLoader

from ruh_model.config import RuhConfig
from ruh_model.data.collator import RuhCollator
from ruh_model.data.sequence import record_id, split_records, tokenize_record
from ruh_model.model import RuhModel
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.conversation import serialize_messages


def token_loss(model, batch):
    logits = model(batch["root_ids"], batch["pattern_ids"])["logits"]
    return functional.cross_entropy(logits.flatten(0, 1), batch["labels"].flatten(), ignore_index=0)


@torch.no_grad()
def evaluate(model, samples, batch_size=2, max_batches=16):
    model.eval()
    total, targets = 0.0, 0
    loader = DataLoader(samples, batch_size=batch_size, collate_fn=RuhCollator())
    for index, batch in enumerate(loader):
        if index >= max_batches:
            break
        batch = {key: value.to(model.config.device) for key, value in batch.items()}
        count = int((batch["labels"] != 0).sum())
        loss = token_loss(model, batch)
        if not torch.isfinite(loss):
            raise ValueError("Non-finite held-out loss")
        total += float(loss) * count
        targets += count
    if targets == 0:
        raise ValueError("Evaluation has no supervised targets")
    loss = total / targets
    return {"cross_entropy": loss, "perplexity": math.exp(min(loss, 80)), "target_tokens": targets}


@torch.no_grad()
def generation_samples(model, tokenizer, validation, count=3):
    model.eval()
    results = []
    for row in validation[:count]:
        if row.get("messages"):
            messages = row["messages"]
            # A complete user prefix; no terminal EOS and no held-out answer.
            prompt = serialize_messages(messages[:-1])
            expected = messages[-1]["content"]
        else:
            text = row["text"]
            boundary = max(1, len(text) // 3)
            prompt, expected = text[:boundary], text[boundary:]
        encoded = tokenizer.encode(prompt, add_eos=False)[-model.config.max_seq_len :]
        roots = torch.tensor([[root for root, _ in encoded]], device=model.config.device)
        patterns = torch.tensor([[pattern for _, pattern in encoded]], device=model.config.device)
        generated = model.generate(roots, patterns, max_new_tokens=80, temperature=0)
        continuation = generated[0, roots.shape[1] :].tolist()
        text = tokenizer.decode([(token, 0) for token in continuation])
        results.append(
            {
                "prompt": prompt,
                "expected": expected,
                "generated": text,
                "generated_tokens": len(continuation),
                "immediate_eos": continuation == [model.config.EOS_ROOT],
                "utf8_replacements": text.count("\ufffd"),
            }
        )
    return results


def run_training(
    rows,
    output: Path,
    *,
    config: RuhConfig,
    steps=200,
    batch_size=2,
    learning_rate=3e-4,
    max_seconds=600,
    seed=42,
    source_metadata=None,
    resume_from: Path | None = None,
):
    if steps < 1 or batch_size < 1 or not 0 < max_seconds <= 36000:
        raise ValueError("Positive steps/batch and bounded wall time are required")
    if config.tokenizer_version != 2:
        raise ValueError("New sequence training requires tokenizer_version=2")
    if output.exists():
        raise ValueError("Use a new output directory; existing candidates are never overwritten")
    random.seed(seed)
    torch.manual_seed(seed)
    tokenizer = BayanTokenizer(version=2)
    config.n_roots = max(config.n_roots, tokenizer._vocab.n_roots)
    if resume_from:
        model = RuhModel.from_pretrained(str(resume_from))
        if model.config.tokenizer_version != 2:
            raise ValueError("Cannot resume a legacy root checkpoint as a lossless sequence model")
        model.config.device = config.device
        config, tokenizer = model.config, model.tokenizer
    else:
        model = RuhModel(config)
        model.tokenizer = tokenizer
    train_rows, validation_rows = split_records(rows, seed=seed)
    train = [
        sample
        for row in train_rows
        for sample in tokenize_record(row, tokenizer, config.max_seq_len)
    ]
    validation = [
        sample
        for row in validation_rows
        for sample in tokenize_record(row, tokenizer, config.max_seq_len)
    ]
    if not train or not validation:
        raise ValueError("Both splits need supervised windows")
    model = model.to(config.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    if resume_from and (resume_from.parent / "training_state.pt").is_file():
        state = torch.load(
            resume_from.parent / "training_state.pt", map_location="cpu", weights_only=True
        )
        optimizer.load_state_dict(state["optimizer"])
        for group in optimizer.param_groups:
            group["lr"] = learning_rate
    before = evaluate(model, validation)
    loader = DataLoader(
        train,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=RuhCollator(),
        generator=torch.Generator().manual_seed(seed),
    )
    iterator, losses, targets = iter(loader), [], 0
    started = time.monotonic()
    for step in range(steps):
        if time.monotonic() - started >= max_seconds:
            break
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            batch = next(iterator)
        batch = {key: value.to(config.device) for key, value in batch.items()}
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = token_loss(model, batch)
        if not torch.isfinite(loss):
            raise ValueError("Non-finite loss; optimizer step refused")
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(norm):
            raise ValueError("Non-finite gradients; optimizer step refused")
        optimizer.step()
        losses.append(float(loss.detach()))
        targets += int((batch["labels"] != 0).sum())
        if (step + 1) % 25 == 0:
            print(
                json.dumps(
                    {
                        "step": step + 1,
                        "loss": losses[-1],
                        "seconds": round(time.monotonic() - started, 2),
                    }
                ),
                flush=True,
            )
    if not losses:
        raise ValueError("Wall-time budget elapsed before any training step")
    training_seconds = time.monotonic() - started
    after = evaluate(model, validation)
    generated = generation_samples(model, tokenizer, validation_rows)
    output.mkdir(parents=True)
    checkpoint = output / "candidate"
    model.save_pretrained(str(checkpoint))
    torch.save(
        {"optimizer": optimizer.state_dict(), "steps": len(losses)}, output / "training_state.pt"
    )
    restored = RuhModel.from_pretrained(str(checkpoint))
    assert restored.config.tokenizer_version == 2
    assert (
        restored.tokenizer.decode(restored.tokenizer.encode("not knowledge; لا علم."))
        == "not knowledge; لا علم."
    )
    files = {}
    for file in sorted(checkpoint.iterdir()):
        files[file.name] = {
            "bytes": file.stat().st_size,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
    report = {
        "schema_version": 1,
        "status": "evaluation_candidate_not_production",
        "tokenizer_version": 2,
        "protocol": "role: content, assistant prefix without EOS",
        "config": asdict(config),
        "parameters": model.count_parameters(),
        "seed": seed,
        "resume_from": str(resume_from) if resume_from else None,
        "source_metadata": source_metadata or {},
        "training": {
            "steps": len(losses),
            "requested_steps": steps,
            "seconds": training_seconds,
            "max_seconds": max_seconds,
            "target_tokens": targets,
            "first_loss": losses[0],
            "last_loss": losses[-1],
            "losses": losses,
        },
        "split": {
            "train_records": len(train_rows),
            "validation_records": len(validation_rows),
            "train_windows": len(train),
            "validation_windows": len(validation),
            "train_group_ids": sorted({record_id(row) for row in train_rows}),
            "validation_group_ids": sorted({record_id(row) for row in validation_rows}),
        },
        "held_out_before": before,
        "held_out_after": after,
        "generations": generated,
        "checkpoint_manifest": files,
        "promotion": {
            "approved": False,
            "reason": "A bounded repair run does not establish conversational quality.",
        },
    }
    (output / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "output": str(output),
                "steps": len(losses),
                "held_out_before": before,
                "held_out_after": after,
                "promotion_approved": False,
            }
        ),
        flush=True,
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--seq-len", type=int, default=384)
    parser.add_argument("--d-model", type=int, default=256)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument(
        "--production-architecture",
        action="store_true",
        help="Use the original 46M Ruh dimensions and MoE; never substitutes the pilot",
    )
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--source-metadata", type=Path)
    parser.add_argument("--resume-from", type=Path, help="V2 candidate; legacy epoch19 is rejected")
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but unavailable; enable the Kaggle GPU accelerator")
    if args.production_architecture:
        config = RuhConfig(max_seq_len=args.seq_len, tokenizer_version=2, device=args.device)
    else:
        config = RuhConfig(
            d_model=args.d_model,
            d_root=32,
            d_pattern=16,
            n_heads=4,
            n_layers=args.layers,
            n_roots=BayanTokenizer(version=2)._vocab.n_roots,
            max_seq_len=args.seq_len,
            tokenizer_version=2,
            moe_interval=0,
            dropout=0.0,
            device=args.device,
        )
    rows = [json.loads(line) for line in args.data.read_text().splitlines() if line.strip()]
    metadata = json.loads(args.source_metadata.read_text()) if args.source_metadata else {}
    run_training(
        rows,
        args.output,
        config=config,
        steps=args.steps,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        max_seconds=args.max_seconds,
        source_metadata=metadata,
        resume_from=args.resume_from,
    )


if __name__ == "__main__":
    main()
