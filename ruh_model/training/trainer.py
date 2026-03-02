"""RuhTrainer -- training loop for the Ruh Model.

Supports:
- AdamW optimizer with gradient clipping
- Warmup + cosine LR scheduling
- Model checkpointing per epoch
- Per-step and per-epoch loss logging
- Optional MizanLoss with Lubb metacognition confidence
- Adaptive depth regularisation awareness
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

import torch
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from ruh_model.config import RuhConfig
from ruh_model.data.collator import RuhCollator
from ruh_model.layers.lubb import LubbMetacognition
from ruh_model.loss.mizan_loss import MizanLoss
from ruh_model.model import RuhModel
from ruh_model.training.scheduler import WarmupCosineScheduler

logger = logging.getLogger(__name__)

# Callback type aliases for training progress reporting
StepCallback = Callable[[dict[str, Any]], None]
EpochCallback = Callable[[dict[str, Any]], None]


class RuhTrainer:
    """Training loop for the Ruh Model.

    Handles the full training lifecycle: DataLoader creation, optimiser
    setup, gradient clipping, loss computation (with optional Mizan loss
    and Lubb confidence), checkpointing, and logging.

    Args:
        model: The RuhModel instance to train.
        config: Model configuration.
        train_dataset: Training dataset (RuhDataset).
        collator: Batch collation function.
        lr: Base learning rate for AdamW.
        weight_decay: AdamW weight decay coefficient.
        max_grad_norm: Maximum gradient norm for clipping.
        warmup_fraction: Fraction of total steps used for LR warmup.
        checkpoint_dir: Directory to save model checkpoints.
        use_mizan_loss: If True, use MizanLoss instead of model's built-in CE.
        use_lubb: If True, compute Lubb confidence for calibration loss.
    """

    def __init__(
        self,
        model: RuhModel,
        config: RuhConfig,
        train_dataset: Dataset,
        collator: RuhCollator,
        lr: float = 3e-4,
        weight_decay: float = 0.01,
        max_grad_norm: float = 1.0,
        warmup_fraction: float = 0.1,
        checkpoint_dir: str = "checkpoints",
        use_mizan_loss: bool = True,
        use_lubb: bool = False,
        on_step: StepCallback | None = None,
        on_epoch: EpochCallback | None = None,
    ) -> None:
        self.model = model
        self.config = config
        self.train_dataset = train_dataset
        self.collator = collator
        self.checkpoint_dir = Path(checkpoint_dir)
        self.max_grad_norm = max_grad_norm
        self.warmup_fraction = warmup_fraction
        self.use_mizan_loss = use_mizan_loss
        self.on_step = on_step
        self.on_epoch = on_epoch

        self.optimizer = torch.optim.AdamW(
            model.parameters(), lr=lr, weight_decay=weight_decay
        )

        self.mizan_loss = MizanLoss(pad_id=config.PAD_ROOT) if use_mizan_loss else None
        self.lubb = LubbMetacognition(config) if use_lubb else None

    def train(
        self,
        epochs: int = 5,
        batch_size: int = 8,
        log_every: int = 10,
    ) -> list[float]:
        """Run the training loop.

        Args:
            epochs: Number of training epochs.
            batch_size: Samples per batch.
            log_every: Log loss every N steps.

        Returns:
            List of average losses, one per epoch.
        """
        loader = self._create_dataloader(batch_size)
        total_steps = len(loader) * epochs
        scheduler = self._create_scheduler(total_steps)

        epoch_losses: list[float] = []

        for epoch in range(epochs):
            avg_loss = self._train_epoch(
                epoch, epochs, loader, scheduler, log_every, total_steps,
            )
            epoch_losses.append(avg_loss)
            self._save_checkpoint(epoch)

            if self.on_epoch:
                self.on_epoch({
                    "type": "epoch",
                    "epoch": epoch + 1,
                    "total_epochs": epochs,
                    "avg_loss": avg_loss,
                    "losses_so_far": list(epoch_losses),
                })

        return epoch_losses

    def _create_dataloader(self, batch_size: int) -> DataLoader:
        """Build a DataLoader from the training dataset."""
        return DataLoader(
            self.train_dataset,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=self.collator,
            drop_last=False,
        )

    def _create_scheduler(self, total_steps: int) -> WarmupCosineScheduler:
        """Build the LR scheduler with warmup + cosine decay."""
        warmup_steps = max(1, int(total_steps * self.warmup_fraction))
        return WarmupCosineScheduler(
            optimizer=self.optimizer,
            warmup_steps=warmup_steps,
            total_steps=total_steps,
        )

    def _train_epoch(
        self,
        epoch: int,
        total_epochs: int,
        loader: DataLoader,
        scheduler: WarmupCosineScheduler,
        log_every: int,
        total_steps_all_epochs: int = 0,
    ) -> float:
        """Train for a single epoch, return average loss."""
        self.model.train()
        total_loss = 0.0
        steps = 0
        steps_per_epoch = len(loader)
        start_time = time.time()

        for batch in loader:
            batch = _move_batch_to_device(batch, self.config.device)
            loss = self._train_step(batch, scheduler)
            total_loss += loss
            steps += 1

            if steps % log_every == 0:
                self._log_step(epoch, total_epochs, steps, loss)

            if self.on_step and steps % log_every == 0:
                current_lr = self.optimizer.param_groups[0]["lr"]
                global_step = epoch * steps_per_epoch + steps
                elapsed = time.time() - start_time
                self.on_step({
                    "type": "step",
                    "epoch": epoch + 1,
                    "total_epochs": total_epochs,
                    "step": steps,
                    "total_steps": steps_per_epoch,
                    "global_step": global_step,
                    "total_global_steps": total_steps_all_epochs,
                    "loss": loss,
                    "lr": current_lr,
                    "elapsed": round(elapsed, 2),
                })

        elapsed = time.time() - start_time
        avg_loss = total_loss / max(steps, 1)

        logger.info(
            "Epoch %d/%d -- Avg Loss: %.4f, Steps: %d, Time: %.1fs",
            epoch + 1, total_epochs, avg_loss, steps, elapsed,
        )

        return avg_loss

    def _train_step(
        self,
        batch: dict[str, Tensor],
        scheduler: WarmupCosineScheduler,
    ) -> float:
        """Execute a single training step. Returns scalar loss value."""
        self.optimizer.zero_grad()

        result = self.model(
            root_ids=batch["root_ids"],
            pattern_ids=batch["pattern_ids"],
            labels=batch["labels"],
        )

        loss = self._compute_loss(result, batch)
        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            self.model.parameters(), self.max_grad_norm
        )

        self.optimizer.step()
        scheduler.step()

        return loss.item()

    def _compute_loss(
        self,
        result: dict[str, Tensor],
        batch: dict[str, Tensor],
    ) -> Tensor:
        """Compute loss using either MizanLoss or the model's built-in CE."""
        if self.mizan_loss is not None:
            confidence = self._get_confidence(result) if self.lubb else None
            mizan_output = self.mizan_loss(
                logits=result["logits"],
                labels=batch["labels"],
                confidence=confidence,
            )
            return mizan_output.total

        # Fallback to model's built-in cross-entropy
        return result["loss"]

    def _get_confidence(self, result: dict[str, Tensor]) -> Tensor | None:
        """Extract confidence from Lubb metacognition if available."""
        if self.lubb is None:
            return None

        # Lubb expects the final hidden states; approximate with logits shape
        # In practice, the model would expose hidden states. For now, we skip.
        return None

    def _save_checkpoint(self, epoch: int) -> None:
        """Save model checkpoint for the given epoch."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        save_path = str(self.checkpoint_dir / f"epoch_{epoch}")
        self.model.save_pretrained(save_path)
        logger.info("Checkpoint saved: %s", save_path)

    def _log_step(
        self,
        epoch: int,
        total_epochs: int,
        step: int,
        loss: float,
    ) -> None:
        """Log a training step."""
        current_lr = self.optimizer.param_groups[0]["lr"]
        logger.info(
            "  Epoch %d/%d, Step %d, Loss: %.4f, LR: %.2e",
            epoch + 1, total_epochs, step, loss, current_lr,
        )

    def get_training_summary(self) -> dict[str, Any]:
        """Return a summary of the current trainer configuration."""
        return {
            "model_params": self.model.count_parameters(),
            "dataset_size": len(self.train_dataset),
            "optimizer": "AdamW",
            "lr": self.optimizer.param_groups[0]["lr"],
            "max_grad_norm": self.max_grad_norm,
            "use_mizan_loss": self.use_mizan_loss,
            "checkpoint_dir": str(self.checkpoint_dir),
        }


def _move_batch_to_device(
    batch: dict[str, Tensor], device: str
) -> dict[str, Tensor]:
    """Move all tensors in a batch dict to the target device.

    Returns a new dict (no mutation of original).
    """
    return {key: tensor.to(device) for key, tensor in batch.items()}
