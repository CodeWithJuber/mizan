"""Full-scale real-data training CLI for the Ruh Model.

Streams data from HuggingFace datasets (Quran, Hadith, Arabic Wikipedia,
OPUS parallel corpus, Tashkeela morphology) and trains through all four
Nafs curriculum stages.

Usage:
    # Quick: single stage with defaults
    python -m ruh_model.train_full --stage nutfah

    # Full 4-stage curriculum run
    python -m ruh_model.train_full --all-stages --samples 500000

    # Custom mixing and GPU training
    python -m ruh_model.train_full --stage alaqah --samples 200000 \\
        --device cuda --quran-weight 0.4 --hadith-weight 0.2

    # Resume from a checkpoint
    python -m ruh_model.train_full --stage mudghah --resume-from ruh_model/checkpoints/alaqah_final

    # Prepare data only (download + materialize to JSONL, no training)
    python -m ruh_model.train_full --prepare-only --samples 100000 --output-dir data/real

    # Train from previously prepared JSONL (no streaming)
    python -m ruh_model.train_full --stage nutfah --data-dir data/real
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

from ruh_model.config import RuhConfig
from ruh_model.data.collator import RuhCollator
from ruh_model.model import RuhModel
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.training.curriculum import VALID_STAGE_NAMES, NafsCurriculum
from ruh_model.training.scheduler import WarmupCosineScheduler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default data mixing ratios
# ---------------------------------------------------------------------------
_DEFAULT_RATIOS: dict[str, float] = {
    "quran": 0.30,
    "hadith": 0.20,
    "arabic_wiki": 0.25,
    "opus": 0.15,
    "morphology": 0.10,
}


# ===================================================================
# Main entry point
# ===================================================================

def main() -> None:
    """Parse CLI args and dispatch to the appropriate workflow."""
    args = _parse_args()
    _setup_logging(args.verbose)

    if args.prepare_only:
        _prepare_data_to_disk(args)
        return

    if args.all_stages:
        _run_all_stages(args)
    else:
        _run_single_stage(args)


# ===================================================================
# Run modes
# ===================================================================

def _run_single_stage(args: argparse.Namespace) -> None:
    """Run training for a single curriculum stage."""
    curriculum = NafsCurriculum()
    stage = curriculum.get_stage(args.stage)
    logger.info("=== Stage: %s — %s ===", stage.name, stage.description)

    device = _resolve_device(args.device)
    config = _build_config(stage.max_seq_len, device)
    tokenizer = BayanTokenizer()

    model = _create_or_resume_model(config, args.resume_from, device)
    _log_model_info(model, device)

    ratios = _build_mixing_ratios(args)

    if args.data_dir:
        epoch_losses = _train_from_jsonl(
            model=model,
            config=config,
            tokenizer=tokenizer,
            data_dir=args.data_dir,
            stage=stage,
            args=args,
        )
    else:
        epoch_losses = _train_streaming(
            model=model,
            config=config,
            tokenizer=tokenizer,
            ratios=ratios,
            stage=stage,
            args=args,
        )

    _save_final_checkpoint(model, args.checkpoint_dir, stage.name)
    _log_final_results(stage.name, epoch_losses)


def _run_all_stages(args: argparse.Namespace) -> None:
    """Run all 4 curriculum stages in sequence."""
    curriculum = NafsCurriculum()
    device = _resolve_device(args.device)
    tokenizer = BayanTokenizer()
    ratios = _build_mixing_ratios(args)

    resume_path = args.resume_from

    for stage in curriculum.get_all_stages():
        logger.info("")
        logger.info("=" * 60)
        logger.info("=== STAGE: %s — %s ===", stage.name.upper(), stage.description)
        logger.info("=" * 60)

        config = _build_config(stage.max_seq_len, device)
        model = _create_or_resume_model(config, resume_path, device)
        _log_model_info(model, device)

        if args.data_dir:
            epoch_losses = _train_from_jsonl(
                model=model,
                config=config,
                tokenizer=tokenizer,
                data_dir=args.data_dir,
                stage=stage,
                args=args,
            )
        else:
            epoch_losses = _train_streaming(
                model=model,
                config=config,
                tokenizer=tokenizer,
                ratios=ratios,
                stage=stage,
                args=args,
            )

        checkpoint_path = _save_final_checkpoint(model, args.checkpoint_dir, stage.name)
        _log_final_results(stage.name, epoch_losses)

        # Next stage resumes from this stage's checkpoint
        resume_path = checkpoint_path

    logger.info("")
    logger.info("All 4 curriculum stages complete!")


def _prepare_data_to_disk(args: argparse.Namespace) -> None:
    """Download and materialize streaming data to JSONL files on disk."""
    from ruh_model.data.pipeline import RealDataPipeline

    tokenizer = BayanTokenizer()
    ratios = _build_mixing_ratios(args)
    pipeline = RealDataPipeline(
        tokenizer=tokenizer,
        max_seq_len=2048,
        mixing_ratios=ratios,
    )

    output_dir = Path(args.output_dir or args.data_dir or "ruh_model/data/real")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples_total = args.samples
    logger.info("Preparing %d samples to %s ...", samples_total, output_dir)

    # Split into domain-specific files for traceability
    writers: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total = 0
    start_time = time.time()

    try:
        for sample in pipeline.stream(max_samples=samples_total):
            domain = sample.get("domain", "general")
            lang = sample.get("lang", "unk")
            file_key = f"{domain}_{lang}"

            if file_key not in writers:
                filepath = output_dir / f"{file_key}.jsonl"
                writers[file_key] = open(filepath, "w", encoding="utf-8")
                counts[file_key] = 0

            writers[file_key].write(json.dumps(sample, ensure_ascii=False) + "\n")
            counts[file_key] += 1
            total += 1

            if total % 10_000 == 0:
                elapsed = time.time() - start_time
                rate = total / elapsed if elapsed > 0 else 0
                logger.info("  Prepared %d / %d samples (%.0f samples/sec)", total, samples_total, rate)
    finally:
        for writer in writers.values():
            writer.close()

    elapsed = time.time() - start_time
    logger.info("Data preparation complete: %d total samples in %.1fs", total, elapsed)
    for file_key, count in sorted(counts.items()):
        logger.info("  %s: %d samples", file_key, count)

    logger.info("Files written to: %s", output_dir)
    logger.info("Train with: python -m ruh_model.train_full --stage nutfah --data-dir %s", output_dir)


# ===================================================================
# Training loops
# ===================================================================

def _train_streaming(
    model: RuhModel,
    config: RuhConfig,
    tokenizer: BayanTokenizer,
    ratios: dict[str, float],
    stage: Any,
    args: argparse.Namespace,
) -> list[float]:
    """Train with streaming data from HuggingFace (no JSONL on disk)."""
    from ruh_model.data.pipeline import RealDataPipeline

    samples_per_epoch = args.samples // stage.epochs
    collator = RuhCollator(pad_id=config.PAD_ROOT)
    device = config.device

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=stage.lr,
        weight_decay=args.weight_decay,
    )

    estimated_steps_per_epoch = max(1, samples_per_epoch // stage.batch_size)
    total_steps = estimated_steps_per_epoch * stage.epochs
    warmup_steps = max(1, int(total_steps * args.warmup_fraction))
    scheduler = WarmupCosineScheduler(
        optimizer=optimizer,
        warmup_steps=warmup_steps,
        total_steps=total_steps,
    )

    logger.info("Streaming training: %d samples/epoch × %d epochs", samples_per_epoch, stage.epochs)
    logger.info("  Estimated steps/epoch: %d, total steps: %d", estimated_steps_per_epoch, total_steps)
    logger.info("  LR: %s, warmup: %d steps", stage.lr, warmup_steps)
    logger.info("  Batch size: %d, max_seq_len: %d", stage.batch_size, stage.max_seq_len)

    epoch_losses: list[float] = []

    for epoch in range(stage.epochs):
        pipeline = RealDataPipeline(
            tokenizer=tokenizer,
            max_seq_len=stage.max_seq_len,
            mixing_ratios=ratios,
        )

        model.train()
        epoch_loss = 0.0
        steps = 0
        epoch_start = time.time()

        for batch in pipeline.get_dataloader(
            max_samples=samples_per_epoch,
            batch_size=stage.batch_size,
            shuffle=True,
        ):
            batch = _move_to_device(batch, device)
            loss = _train_step(model, optimizer, scheduler, batch, args.max_grad_norm)
            epoch_loss += loss
            steps += 1

            if steps % args.log_every == 0:
                current_lr = optimizer.param_groups[0]["lr"]
                logger.info(
                    "  Epoch %d/%d, Step %d, Loss: %.4f, LR: %.2e",
                    epoch + 1, stage.epochs, steps, loss, current_lr,
                )

        elapsed = time.time() - epoch_start
        avg_loss = epoch_loss / max(steps, 1)
        epoch_losses.append(avg_loss)

        logger.info(
            "Epoch %d/%d complete — Avg Loss: %.4f, Steps: %d, Time: %.1fs",
            epoch + 1, stage.epochs, avg_loss, steps, elapsed,
        )

        # Checkpoint per epoch
        _save_epoch_checkpoint(model, args.checkpoint_dir, stage.name, epoch)

    return epoch_losses


def _train_from_jsonl(
    model: RuhModel,
    config: RuhConfig,
    tokenizer: BayanTokenizer,
    data_dir: str,
    stage: Any,
    args: argparse.Namespace,
) -> list[float]:
    """Train from pre-materialized JSONL files (loaded into memory)."""
    from ruh_model.data.dataset import RuhDataset
    from ruh_model.training.trainer import RuhTrainer

    dataset = RuhDataset(
        data_path=data_dir,
        tokenizer=tokenizer,
        max_seq_len=stage.max_seq_len,
        config=config,
    )

    if len(dataset) == 0:
        logger.error("No training samples in %s. Run with --prepare-only first.", data_dir)
        sys.exit(1)

    collator = RuhCollator(pad_id=config.PAD_ROOT)
    trainer = RuhTrainer(
        model=model,
        config=config,
        train_dataset=dataset,
        collator=collator,
        lr=stage.lr,
        weight_decay=args.weight_decay,
        max_grad_norm=args.max_grad_norm,
        warmup_fraction=args.warmup_fraction,
        checkpoint_dir=args.checkpoint_dir,
    )

    summary = trainer.get_training_summary()
    logger.info("JSONL training: %d samples, %d params", summary["dataset_size"], summary["model_params"])

    return trainer.train(
        epochs=stage.epochs,
        batch_size=stage.batch_size,
        log_every=args.log_every,
    )


# ===================================================================
# Training step
# ===================================================================

def _train_step(
    model: RuhModel,
    optimizer: torch.optim.Optimizer,
    scheduler: WarmupCosineScheduler,
    batch: dict[str, torch.Tensor],
    max_grad_norm: float,
) -> float:
    """Execute a single gradient update step. Returns scalar loss."""
    optimizer.zero_grad()

    result = model(
        root_ids=batch["root_ids"],
        pattern_ids=batch["pattern_ids"],
        labels=batch["labels"],
    )

    loss = result["loss"]
    loss.backward()

    nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
    optimizer.step()
    scheduler.step()

    return loss.item()


# ===================================================================
# Helpers
# ===================================================================

def _parse_args() -> argparse.Namespace:
    """Build and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Train the Ruh Model with real-world data from HuggingFace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream from HuggingFace and train Stage 1
  python -m ruh_model.train_full --stage nutfah --samples 100000

  # Run all 4 stages end-to-end
  python -m ruh_model.train_full --all-stages --samples 500000 --device cuda

  # Prepare data to disk first, then train offline
  python -m ruh_model.train_full --prepare-only --samples 500000 --output-dir data/real
  python -m ruh_model.train_full --stage nutfah --data-dir data/real

  # Resume interrupted training
  python -m ruh_model.train_full --stage alaqah --resume-from ruh_model/checkpoints/nutfah_final

  # Custom data mix (more Quran, less Wikipedia)
  python -m ruh_model.train_full --stage nutfah --quran-weight 0.5 --wiki-weight 0.1
""",
    )

    # --- Mode ---
    mode = parser.add_argument_group("Training mode")
    mode.add_argument(
        "--stage", default="nutfah", choices=VALID_STAGE_NAMES,
        help="Curriculum stage (default: nutfah)",
    )
    mode.add_argument(
        "--all-stages", action="store_true",
        help="Run all 4 curriculum stages in sequence",
    )
    mode.add_argument(
        "--prepare-only", action="store_true",
        help="Download and materialize data to JSONL without training",
    )

    # --- Data ---
    data = parser.add_argument_group("Data sources")
    data.add_argument(
        "--samples", type=int, default=100_000,
        help="Total samples to stream from HuggingFace (default: 100,000)",
    )
    data.add_argument(
        "--data-dir", default=None,
        help="Train from pre-materialized JSONL instead of streaming",
    )
    data.add_argument(
        "--output-dir", default=None,
        help="Output directory for --prepare-only (default: ruh_model/data/real)",
    )

    # --- Mixing ratios ---
    mix = parser.add_argument_group("Data mixing weights (proportional, need not sum to 1)")
    mix.add_argument("--quran-weight", type=float, default=0.30, help="Quran weight (default: 0.30)")
    mix.add_argument("--hadith-weight", type=float, default=0.20, help="Hadith weight (default: 0.20)")
    mix.add_argument("--wiki-weight", type=float, default=0.25, help="Arabic Wikipedia weight (default: 0.25)")
    mix.add_argument("--opus-weight", type=float, default=0.15, help="OPUS parallel corpus weight (default: 0.15)")
    mix.add_argument("--morpho-weight", type=float, default=0.10, help="Tashkeela morphology weight (default: 0.10)")

    # --- Training hyperparams ---
    train = parser.add_argument_group("Training hyperparameters")
    train.add_argument("--device", default="auto", help="Device: cpu, cuda, mps, or auto (default: auto)")
    train.add_argument("--weight-decay", type=float, default=0.01, help="AdamW weight decay (default: 0.01)")
    train.add_argument("--max-grad-norm", type=float, default=1.0, help="Gradient clip norm (default: 1.0)")
    train.add_argument("--warmup-fraction", type=float, default=0.1, help="LR warmup fraction (default: 0.1)")

    # --- Checkpointing ---
    ckpt = parser.add_argument_group("Checkpointing")
    ckpt.add_argument(
        "--checkpoint-dir", default="ruh_model/checkpoints",
        help="Directory to save checkpoints (default: ruh_model/checkpoints)",
    )
    ckpt.add_argument(
        "--resume-from", default=None,
        help="Path to a checkpoint directory to resume from",
    )

    # --- Logging ---
    log = parser.add_argument_group("Logging")
    log.add_argument("--log-every", type=int, default=50, help="Log loss every N steps (default: 50)")
    log.add_argument("--verbose", action="store_true", help="Enable debug-level logging")

    return parser.parse_args()


def _setup_logging(verbose: bool) -> None:
    """Configure logging format and level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _resolve_device(device_arg: str) -> str:
    """Resolve the device string, handling 'auto' detection."""
    if device_arg != "auto":
        return device_arg

    if torch.cuda.is_available():
        logger.info("Auto-detected CUDA device")
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        logger.info("Auto-detected MPS device (Apple Silicon)")
        return "mps"

    logger.info("Using CPU (no GPU detected)")
    return "cpu"


def _build_config(max_seq_len: int, device: str) -> RuhConfig:
    """Build a RuhConfig with the given sequence length and device."""
    return RuhConfig(max_seq_len=max_seq_len, device=device)


def _build_mixing_ratios(args: argparse.Namespace) -> dict[str, float]:
    """Build mixing ratios dict from CLI arguments."""
    return {
        "quran": args.quran_weight,
        "hadith": args.hadith_weight,
        "arabic_wiki": args.wiki_weight,
        "opus": args.opus_weight,
        "morphology": args.morpho_weight,
    }


def _create_or_resume_model(
    config: RuhConfig, resume_from: str | None, device: str
) -> RuhModel:
    """Create a new model or load from checkpoint, then move to device."""
    if resume_from is not None:
        logger.info("Resuming from checkpoint: %s", resume_from)
        model = RuhModel.from_pretrained(resume_from)
    else:
        model = RuhModel(config)

    model = model.to(device)
    return model


def _log_model_info(model: RuhModel, device: str) -> None:
    """Log model parameter count and device."""
    param_count = model.count_parameters()
    param_mb = param_count * 4 / (1024 * 1024)  # float32 -> MB
    logger.info("Model: %d params (%.1f MB float32) on %s", param_count, param_mb, device)


def _move_to_device(
    batch: dict[str, torch.Tensor], device: str
) -> dict[str, torch.Tensor]:
    """Move all tensors in a batch to the target device (immutable)."""
    return {key: tensor.to(device) for key, tensor in batch.items()}


def _save_epoch_checkpoint(
    model: RuhModel, checkpoint_dir: str, stage_name: str, epoch: int
) -> str:
    """Save per-epoch checkpoint. Returns the checkpoint path."""
    path = str(Path(checkpoint_dir) / f"{stage_name}_epoch_{epoch}")
    model.save_pretrained(path)
    logger.info("Checkpoint saved: %s", path)
    return path


def _save_final_checkpoint(
    model: RuhModel, checkpoint_dir: str, stage_name: str
) -> str:
    """Save the final checkpoint for a stage. Returns the checkpoint path."""
    path = str(Path(checkpoint_dir) / f"{stage_name}_final")
    model.save_pretrained(path)
    logger.info("Final checkpoint saved: %s", path)
    return path


def _log_final_results(stage_name: str, epoch_losses: list[float]) -> None:
    """Log training results after a stage completes."""
    if not epoch_losses:
        logger.warning("Stage %s: no epochs completed.", stage_name)
        return

    logger.info("Stage %s complete.", stage_name)
    logger.info("  Final loss: %.4f", epoch_losses[-1])
    logger.info(
        "  Loss progression: %s",
        " → ".join(f"{loss:.4f}" for loss in epoch_losses),
    )

    if len(epoch_losses) >= 2 and epoch_losses[-1] < epoch_losses[0]:
        improvement = (1 - epoch_losses[-1] / epoch_losses[0]) * 100
        logger.info("  Improvement: %.1f%%", improvement)


if __name__ == "__main__":
    main()
