"""CLI entry point for Ruh Model training.

Usage:
    python -m ruh_model.train --stage nutfah --data-dir ruh_model/data/training
    python -m ruh_model.train --stage nutfah --generate-data
    python -m ruh_model.train --stage alaqah --checkpoint-dir ruh_model/checkpoints
    python -m ruh_model.train --config ruh_model/configs/nutfah.yaml

For real-data training with HuggingFace datasets, use train_full.py instead:
    python -m ruh_model.train_full --stage nutfah --samples 100000
    python -m ruh_model.train_full --all-stages --samples 500000 --device cuda
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from ruh_model.config import RuhConfig
from ruh_model.data.collator import RuhCollator
from ruh_model.data.dataset import RuhDataset
from ruh_model.data.generator import SeedDataGenerator
from ruh_model.model import RuhModel
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.training.curriculum import VALID_STAGE_NAMES, NafsCurriculum
from ruh_model.training.trainer import RuhTrainer

logger = logging.getLogger(__name__)


def main() -> None:
    """Parse CLI args and run training."""
    args = _parse_args()
    _setup_logging(args.verbose)

    stage_config = _resolve_stage_config(args)
    data_path = _ensure_training_data(args, stage_config)

    logger.info("Stage: %s -- %s", stage_config["name"], stage_config["description"])
    logger.info("Data path: %s", data_path)

    config = RuhConfig(max_seq_len=stage_config["max_seq_len"])
    tokenizer = BayanTokenizer()
    dataset = RuhDataset(
        data_path=data_path,
        tokenizer=tokenizer,
        max_seq_len=stage_config["max_seq_len"],
        config=config,
    )

    if len(dataset) == 0:
        logger.error("No training samples found. Use --generate-data to create seed data.")
        sys.exit(1)

    model = _create_model(config, args.resume_from)
    collator = RuhCollator(pad_id=config.PAD_ROOT)

    # Build progress callbacks for JSON output mode
    on_step = None
    on_epoch = None
    if args.json_progress:
        on_step = _make_json_step_callback(stage_config["name"])
        on_epoch = _make_json_epoch_callback(stage_config["name"])

    trainer = RuhTrainer(
        model=model,
        config=config,
        train_dataset=dataset,
        collator=collator,
        lr=stage_config["lr"],
        checkpoint_dir=args.checkpoint_dir,
        on_step=on_step,
        on_epoch=on_epoch,
    )

    _log_training_summary(trainer, stage_config)

    if args.json_progress:
        _emit_json({"type": "start", "stage": stage_config["name"],
                    "epochs": stage_config["epochs"],
                    "batch_size": stage_config["batch_size"],
                    "dataset_size": len(dataset),
                    "model_params": model.count_parameters()})

    epoch_losses = trainer.train(
        epochs=stage_config["epochs"],
        batch_size=stage_config["batch_size"],
        log_every=args.log_every,
    )

    if args.json_progress:
        _emit_json({"type": "complete", "stage": stage_config["name"],
                    "final_loss": epoch_losses[-1] if epoch_losses else None,
                    "losses": epoch_losses})

    _log_final_results(epoch_losses)


def _parse_args() -> argparse.Namespace:
    """Build and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Train the Ruh Model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--stage",
        default="nutfah",
        choices=VALID_STAGE_NAMES,
        help="Curriculum stage to train (default: nutfah)",
    )
    parser.add_argument(
        "--data-dir",
        default="ruh_model/data/training",
        help="Directory containing training JSONL files",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="ruh_model/checkpoints",
        help="Directory to save model checkpoints",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a YAML config file (overrides --stage)",
    )
    parser.add_argument(
        "--generate-data",
        action="store_true",
        help="Generate seed training data before training",
    )
    parser.add_argument(
        "--samples-per-root",
        type=int,
        default=10,
        help="Samples per root when generating data (default: 10)",
    )
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Path to a checkpoint directory to resume from",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10,
        help="Log loss every N steps (default: 10)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="Emit JSON progress lines to stdout (for API integration)",
    )
    return parser.parse_args()


def _setup_logging(verbose: bool) -> None:
    """Configure logging format and level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _resolve_stage_config(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve training config from either YAML file or curriculum stage."""
    if args.config is not None:
        return _load_yaml_config(args.config)
    return _stage_to_dict(args.stage)


def _load_yaml_config(config_path: str) -> dict[str, Any]:
    """Load training config from a YAML file."""
    path = Path(config_path)
    if not path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    required_keys = {"name", "max_seq_len", "lr", "epochs", "batch_size"}
    missing = required_keys - set(data.keys())
    if missing:
        logger.error("Config missing required keys: %s", missing)
        sys.exit(1)

    data.setdefault("description", f"Custom config from {config_path}")
    return data


def _stage_to_dict(stage_name: str) -> dict[str, Any]:
    """Convert a NafsCurriculum stage to a plain dict."""
    curriculum = NafsCurriculum()
    stage = curriculum.get_stage(stage_name)
    return {
        "name": stage.name,
        "max_seq_len": stage.max_seq_len,
        "lr": stage.lr,
        "epochs": stage.epochs,
        "batch_size": stage.batch_size,
        "description": stage.description,
    }


def _ensure_training_data(
    args: argparse.Namespace, stage_config: dict[str, Any]
) -> str:
    """Generate seed data if requested, return the data directory path."""
    data_dir = args.data_dir

    if args.generate_data:
        _generate_seed_data(data_dir, args.samples_per_root)

    return data_dir


def _generate_seed_data(data_dir: str, samples_per_root: int) -> None:
    """Generate seed training data from ARABIC_ROOTS."""
    generator = SeedDataGenerator()

    roots_path = str(Path(data_dir) / "seed_roots.jsonl")
    root_count = generator.generate(roots_path, samples_per_root=samples_per_root)
    logger.info("Generated %d root-based samples -> %s", root_count, roots_path)

    concepts_path = str(Path(data_dir) / "seed_concepts.jsonl")
    concept_count = generator.generate_concept_map_data(concepts_path)
    logger.info("Generated %d concept-map samples -> %s", concept_count, concepts_path)


def _create_model(config: RuhConfig, resume_from: str | None) -> RuhModel:
    """Create a new model or load from checkpoint."""
    if resume_from is not None:
        logger.info("Resuming from checkpoint: %s", resume_from)
        return RuhModel.from_pretrained(resume_from)

    model = RuhModel(config)
    param_count = model.count_parameters()
    logger.info("Created new model with %d parameters", param_count)
    return model


def _log_training_summary(
    trainer: RuhTrainer, stage_config: dict[str, Any]
) -> None:
    """Log a summary before training begins."""
    summary = trainer.get_training_summary()
    logger.info("Training Summary:")
    logger.info("  Model params: %d", summary["model_params"])
    logger.info("  Dataset size: %d", summary["dataset_size"])
    logger.info("  Stage: %s", stage_config["name"])
    logger.info("  LR: %s", stage_config["lr"])
    logger.info("  Epochs: %d", stage_config["epochs"])
    logger.info("  Batch size: %d", stage_config["batch_size"])
    logger.info("  Max seq len: %d", stage_config["max_seq_len"])


def _log_final_results(epoch_losses: list[float]) -> None:
    """Log training results after completion."""
    if not epoch_losses:
        logger.warning("No epochs completed.")
        return

    logger.info("Training complete.")
    logger.info("  Final loss: %.4f", epoch_losses[-1])
    logger.info(
        "  Loss progression: %s",
        " -> ".join(f"{loss:.4f}" for loss in epoch_losses),
    )

    if len(epoch_losses) >= 2 and epoch_losses[-1] < epoch_losses[0]:
        improvement = (1 - epoch_losses[-1] / epoch_losses[0]) * 100
        logger.info("  Improvement: %.1f%%", improvement)


def _emit_json(data: dict[str, Any]) -> None:
    """Write a single JSON line to stdout for machine consumption."""
    print(json.dumps(data, default=str), flush=True)


def _make_json_step_callback(stage: str):
    """Return a step callback that emits JSON progress."""
    def _on_step(info: dict[str, Any]) -> None:
        _emit_json({**info, "stage": stage})
    return _on_step


def _make_json_epoch_callback(stage: str):
    """Return an epoch callback that emits JSON progress."""
    def _on_epoch(info: dict[str, Any]) -> None:
        _emit_json({**info, "stage": stage})
    return _on_epoch


if __name__ == "__main__":
    main()
