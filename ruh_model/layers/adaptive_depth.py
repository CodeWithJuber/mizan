"""Adaptive Depth Gate for early-exit computation.

Implements System 1 / System 2 style processing: simple inputs exit the
transformer early (fewer layers), while complex inputs propagate through
the full stack.  Based on Adaptive Computation Time (Graves, 2016) and
Universal Transformers (Dehghani et al., 2019).
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor


class AdaptiveDepthGate(nn.Module):
    """Per-layer exit gate for adaptive computation depth.

    Each transformer layer owns one gate.  After the layer's forward pass
    the gate inspects the hidden state and decides whether the batch can
    skip the remaining layers.

    Gate signal:
        g = sigmoid(W_g @ pool(hidden) + b_g)

    Decision:
        if g > threshold for every sample in the batch  ->  exit early
        else                                             ->  continue
    """

    def __init__(self, d_model: int, threshold: float = 0.8) -> None:
        super().__init__()
        self.gate_proj = nn.Linear(d_model, 1)
        self.threshold = threshold

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, hidden: Tensor) -> tuple[Tensor, bool]:
        """Compute exit confidence and halting decision.

        Args:
            hidden: (B, S, d_model) hidden states after a transformer layer.

        Returns:
            confidence: (B,) per-sample confidence scalars in [0, 1].
            should_exit: True when *all* samples exceed the threshold.
        """
        confidence = self._compute_confidence(hidden)
        should_exit = self._should_halt(confidence)
        return confidence, should_exit

    # ------------------------------------------------------------------
    # Halting regularisation
    # ------------------------------------------------------------------

    @staticmethod
    def get_halting_loss(confidences: list[Tensor]) -> Tensor:
        """ACT-style regularisation that encourages early exiting.

        Penalises the model for using more layers than necessary by
        rewarding high confidence (= early exits).

        Args:
            confidences: list of (B,) tensors, one per layer traversed.

        Returns:
            Scalar loss in [0, 1].  Lower means earlier exits.
        """
        if not confidences:
            return torch.tensor(0.0)
        stacked = torch.stack(confidences)  # (L, B)
        return 1.0 - stacked.mean()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_confidence(self, hidden: Tensor) -> Tensor:
        """Pool hidden states and project to a scalar confidence."""
        pooled = hidden.mean(dim=1)                     # (B, d_model)
        gate_logit = self.gate_proj(pooled).squeeze(-1)  # (B,)
        return torch.sigmoid(gate_logit)

    def _should_halt(self, confidence: Tensor) -> bool:
        """Return True when every sample in the batch is confident."""
        return bool((confidence > self.threshold).all().item())
