"""Lubb Metacognition Head -- confidence, certainty level, and quality assessment.

Named after Lubb (لب), the kernel or innermost essence of intellect.
"Only people of Lubb truly understand." -- Quran

The module maps a transformer's final hidden state to three outputs:

1. **Confidence** -- scalar in [0, 1] estimating prediction reliability.
2. **Yaqin level** -- three-class certainty drawn from Quranic epistemology:
   - Ilm al-Yaqin  (علم اليقين)  inferential certainty   [0.0 – 0.6)
   - Ayn al-Yaqin  (عين اليقين)  witnessed certainty     [0.6 – 0.9)
   - Haqq al-Yaqin (حق اليقين)   embodied certainty      [0.9 – 1.0]
3. **Quality** -- coherence and relevance scores in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import torch.nn as nn
from torch import Tensor

from ruh_model.config import RuhConfig


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

class YaqinIndex(IntEnum):
    """Indices into the 3-class Yaqin logits vector."""

    ILM = 0    # inferential
    AYN = 1    # witnessed
    HAQQ = 2   # embodied


YAQIN_LABELS: dict[int, str] = {
    YaqinIndex.ILM: "ilm_al_yaqin",
    YaqinIndex.AYN: "ayn_al_yaqin",
    YaqinIndex.HAQQ: "haqq_al_yaqin",
}

_ILM_UPPER = 0.6
_AYN_UPPER = 0.9

# Small tolerance for float32 boundary comparisons
_EPS = 1e-6


# ------------------------------------------------------------------
# Output container
# ------------------------------------------------------------------

@dataclass(frozen=True)
class LubbOutput:
    """Immutable container for metacognition results."""

    confidence: Tensor       # (B,) scalar confidence
    yaqin_logits: Tensor     # (B, 3) raw logits for certainty level
    yaqin_level: list[str]   # human-readable certainty labels
    coherence: Tensor        # (B,) quality sub-score
    relevance: Tensor        # (B,) quality sub-score


# ------------------------------------------------------------------
# Module
# ------------------------------------------------------------------

class LubbMetacognition(nn.Module):
    """Metacognition head producing confidence scores and quality assessment.

    All three sub-heads share a common pooling step (mean over the
    sequence dimension) and then diverge into independent MLPs so that
    gradient signals remain cleanly separated.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.d_model = config.d_model
        hidden = config.d_model // 4

        self.confidence_head = self._build_confidence_head(config.d_model, hidden)
        self.yaqin_head = self._build_yaqin_head(config.d_model, hidden)
        self.quality_head = self._build_quality_head(config.d_model, hidden)

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, hidden: Tensor) -> LubbOutput:
        """Compute metacognitive assessment of the hidden representation.

        Args:
            hidden: (B, S, d_model) final-layer hidden states.

        Returns:
            LubbOutput with confidence, yaqin, and quality fields.
        """
        pooled = hidden.mean(dim=1)  # (B, d_model)

        confidence = self.confidence_head(pooled).squeeze(-1)  # (B,)
        yaqin_logits = self.yaqin_head(pooled)                 # (B, 3)
        quality = self.quality_head(pooled)                     # (B, 2)

        yaqin_level = _classify_yaqin(confidence)

        return LubbOutput(
            confidence=confidence,
            yaqin_logits=yaqin_logits,
            yaqin_level=yaqin_level,
            coherence=quality[:, 0],
            relevance=quality[:, 1],
        )

    # ------------------------------------------------------------------
    # Head constructors (kept small, pure functions)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_confidence_head(d_in: int, d_hidden: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Linear(d_in, d_hidden),
            nn.GELU(),
            nn.Linear(d_hidden, 1),
            nn.Sigmoid(),
        )

    @staticmethod
    def _build_yaqin_head(d_in: int, d_hidden: int) -> nn.Sequential:
        """Raw logits -- no activation; use cross-entropy during training."""
        return nn.Sequential(
            nn.Linear(d_in, d_hidden),
            nn.GELU(),
            nn.Linear(d_hidden, 3),
        )

    @staticmethod
    def _build_quality_head(d_in: int, d_hidden: int) -> nn.Sequential:
        """Two bounded scores: coherence and relevance."""
        return nn.Sequential(
            nn.Linear(d_in, d_hidden),
            nn.GELU(),
            nn.Linear(d_hidden, 2),
            nn.Sigmoid(),
        )


# ------------------------------------------------------------------
# Pure helper
# ------------------------------------------------------------------

def _classify_yaqin(confidence: Tensor) -> list[str]:
    """Map confidence scalars to Yaqin certainty labels.

    Thresholds:
        [0.0, 0.6)  ->  ilm_al_yaqin   (inferential)
        [0.6, 0.9)  ->  ayn_al_yaqin   (witnessed)
        [0.9, 1.0]  ->  haqq_al_yaqin  (embodied)
    """
    levels: list[str] = []
    for value in confidence.detach().tolist():
        # Tolerance handles float32 boundary rounding (e.g. 0.9 -> 0.8999...)
        if value >= _AYN_UPPER - _EPS:
            levels.append(YAQIN_LABELS[YaqinIndex.HAQQ])
        elif value >= _ILM_UPPER - _EPS:
            levels.append(YAQIN_LABELS[YaqinIndex.AYN])
        else:
            levels.append(YAQIN_LABELS[YaqinIndex.ILM])
    return levels
