"""WarmupCosineScheduler -- linear warmup followed by cosine decay.

Standard two-phase LR schedule:
1. Linear warmup: LR ramps from 0 to base_lr over warmup_steps.
2. Cosine decay: LR follows a cosine curve from base_lr to 0 over
   the remaining steps.

This scheduler updates the LR in-place on each call to step().
It does not subclass torch.optim.lr_scheduler to keep the
implementation minimal and explicit.
"""

from __future__ import annotations

import math

import torch.optim


class WarmupCosineScheduler:
    """Linear warmup + cosine decay learning rate scheduler.

    Args:
        optimizer: The PyTorch optimizer whose LR will be adjusted.
        warmup_steps: Number of steps for the linear warmup phase.
        total_steps: Total number of training steps (warmup + decay).
        min_lr_fraction: Minimum LR as a fraction of base LR (default 0.0).
    """

    def __init__(
        self,
        optimizer: torch.optim.Optimizer,
        warmup_steps: int,
        total_steps: int,
        min_lr_fraction: float = 0.0,
    ) -> None:
        if warmup_steps < 0:
            raise ValueError(f"warmup_steps must be >= 0, got {warmup_steps}")
        if total_steps < 1:
            raise ValueError(f"total_steps must be >= 1, got {total_steps}")
        if not 0.0 <= min_lr_fraction <= 1.0:
            raise ValueError(
                f"min_lr_fraction must be in [0, 1], got {min_lr_fraction}"
            )

        self.optimizer = optimizer
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self.min_lr_fraction = min_lr_fraction
        self._current_step = 0

        # Capture base LRs from each param group at init time
        self._base_lrs = [group["lr"] for group in optimizer.param_groups]

    def step(self) -> None:
        """Advance one step and update the optimizer's learning rates."""
        self._current_step += 1
        multiplier = self._compute_multiplier(self._current_step)
        _apply_lr_multiplier(self.optimizer, self._base_lrs, multiplier)

    def _compute_multiplier(self, step: int) -> float:
        """Compute the LR multiplier for the given step.

        Returns a value in [min_lr_fraction, 1.0].
        """
        if step <= self.warmup_steps:
            return _linear_warmup(step, self.warmup_steps)

        return _cosine_decay(
            step, self.warmup_steps, self.total_steps, self.min_lr_fraction
        )

    def get_lr(self) -> list[float]:
        """Return the current learning rate for each parameter group."""
        return [group["lr"] for group in self.optimizer.param_groups]

    @property
    def current_step(self) -> int:
        """Return the number of steps taken so far."""
        return self._current_step


def _linear_warmup(step: int, warmup_steps: int) -> float:
    """Compute linear warmup multiplier: ramp from 0 to 1."""
    if warmup_steps == 0:
        return 1.0
    return step / warmup_steps


def _cosine_decay(
    step: int,
    warmup_steps: int,
    total_steps: int,
    min_lr_fraction: float,
) -> float:
    """Compute cosine decay multiplier after warmup."""
    decay_steps = total_steps - warmup_steps
    if decay_steps <= 0:
        return 1.0

    progress = (step - warmup_steps) / decay_steps
    progress = min(progress, 1.0)

    cosine_value = 0.5 * (1.0 + math.cos(math.pi * progress))
    return min_lr_fraction + (1.0 - min_lr_fraction) * cosine_value


def _apply_lr_multiplier(
    optimizer: torch.optim.Optimizer,
    base_lrs: list[float],
    multiplier: float,
) -> None:
    """Set LR on each param group to base_lr * multiplier."""
    for group, base_lr in zip(optimizer.param_groups, base_lrs):
        group["lr"] = base_lr * multiplier
