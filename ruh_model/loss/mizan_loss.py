"""Mizan (Balance) Loss -- truth-calibrated composite training objective.

L_mizan = L_ce
        + lambda_cal * L_calibration
        + lambda_con * L_consistency
        + lambda_fit * L_fitrah
        + lambda_hisb * L_hisbah

Components
----------
L_ce          Standard cross-entropy for next-root prediction.
L_calibration Differentiable Expected Calibration Error -- are the
              confidence scores from Lubb actually predictive of accuracy?
L_consistency KL divergence between logits and paraphrase-pair logits,
              encouraging semantically equivalent inputs to produce
              equivalent output distributions.
L_fitrah      Entropy-target regularisation: penalises both over-confident
              (low entropy) and uniform (high entropy) distributions by
              pulling the output entropy toward a calibrated target.
L_hisbah      Self-accountability: penalises high confidence when the model
              is actually wrong, encouraging honest uncertainty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


# ------------------------------------------------------------------
# Output container
# ------------------------------------------------------------------

@dataclass(frozen=True)
class MizanLossOutput:
    """Immutable container for loss breakdown."""

    total: Tensor
    ce: float
    calibration: float
    consistency: float
    fitrah: float
    hisbah: float


# ------------------------------------------------------------------
# Loss module
# ------------------------------------------------------------------

class MizanLoss(nn.Module):
    """Mizan (balance) loss: truth-calibrated training objective.

    Combines standard language-modelling cross-entropy with auxiliary
    losses that encourage well-calibrated confidence, consistency across
    paraphrase pairs, ethical moderation in output distributions, and
    self-accountability when the model is confidently wrong.
    """

    def __init__(
        self,
        pad_id: int = 0,
        lambda_cal: float = 0.1,
        lambda_con: float = 0.05,
        lambda_fit: float = 0.01,
        lambda_hisb: float = 0.02,
        n_bins: int = 10,
        vocab_size: int = 4000,
    ) -> None:
        super().__init__()
        self.pad_id = pad_id
        self.lambda_cal = lambda_cal
        self.lambda_con = lambda_con
        self.lambda_fit = lambda_fit
        self.lambda_hisb = lambda_hisb
        self.n_bins = n_bins
        self.vocab_size = vocab_size

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(
        self,
        logits: Tensor,
        labels: Tensor,
        confidence: Tensor | None = None,
        paraphrase_logits: Tensor | None = None,
    ) -> MizanLossOutput:
        """Compute the composite Mizan loss.

        Args:
            logits: (B, S, V) predicted logits over root vocabulary.
            labels: (B, S) target root IDs.
            confidence: (B,) optional confidence from LubbMetacognition.
            paraphrase_logits: (B, S, V) optional logits from a paraphrase
                of each input, used to compute L_consistency.

        Returns:
            MizanLossOutput with total loss tensor and per-component floats.
        """
        ce_loss = self._cross_entropy(logits, labels)
        cal_loss = self._calibration_loss(logits, labels, confidence)
        con_loss = self._consistency_loss(logits, paraphrase_logits)
        fit_loss = self._fitrah_loss(logits)
        hisb_loss = self._hisbah_loss(logits, labels, confidence)

        total = (
            ce_loss
            + self.lambda_cal * cal_loss
            + self.lambda_con * con_loss
            + self.lambda_fit * fit_loss
            + self.lambda_hisb * hisb_loss
        )

        return MizanLossOutput(
            total=total,
            ce=ce_loss.item(),
            calibration=cal_loss.item(),
            consistency=con_loss.item(),
            fitrah=fit_loss.item(),
            hisbah=hisb_loss.item(),
        )

    # ------------------------------------------------------------------
    # Component losses
    # ------------------------------------------------------------------

    def _cross_entropy(self, logits: Tensor, labels: Tensor) -> Tensor:
        """Standard cross-entropy ignoring padding tokens."""
        return F.cross_entropy(
            logits.view(-1, logits.size(-1)),
            labels.view(-1),
            ignore_index=self.pad_id,
        )

    def _calibration_loss(
        self,
        logits: Tensor,
        labels: Tensor,
        confidence: Tensor | None,
    ) -> Tensor:
        """Differentiable approximation of Expected Calibration Error.

        Measures the gap between per-sample accuracy and the model's
        own confidence estimate.  When confidence is None (no Lubb head)
        this returns zero.
        """
        if confidence is None:
            return torch.tensor(0.0, device=logits.device)

        accuracy = _per_sample_accuracy(logits, labels, self.pad_id)
        return (accuracy - confidence).abs().mean()

    def _consistency_loss(
        self,
        logits: Tensor,
        paraphrase_logits: Tensor | None,
    ) -> Tensor:
        """KL divergence between original and paraphrase output distributions.

        Encourages the model to produce equivalent distributions for
        semantically equivalent inputs. Returns zero when no paraphrase
        logits are provided.
        """
        if paraphrase_logits is None:
            return torch.tensor(0.0, device=logits.device)

        vocab = self.vocab_size
        log_p = F.log_softmax(logits.view(-1, vocab), dim=-1)
        q = F.softmax(paraphrase_logits.view(-1, vocab), dim=-1)
        return F.kl_div(log_p, q, reduction="batchmean")

    def _fitrah_loss(self, logits: Tensor) -> Tensor:
        """Entropy-target regularisation toward a calibrated entropy level.

        Penalises both over-confident (low-entropy) and uniform (high-entropy)
        distributions by measuring squared deviation from a target entropy
        of 0.3 * log(vocab_size).
        """
        eps = 1e-8
        vocab = self.vocab_size
        p = F.softmax(logits.view(-1, vocab), dim=-1)
        entropy = -(p * (p + eps).log()).sum(dim=-1).mean()
        target_entropy = 0.3 * math.log(vocab)
        return (entropy - target_entropy).pow(2)

    def _hisbah_loss(
        self,
        logits: Tensor,
        labels: Tensor,
        confidence: Tensor | None,
    ) -> Tensor:
        """Self-accountability: penalise high confidence when the model is wrong.

        High confidence on incorrect predictions violates Hisbah (internal
        moral accounting). Returns zero when confidence is not provided.
        """
        if confidence is None:
            return torch.tensor(0.0, device=logits.device)

        accuracy = _per_sample_accuracy(logits, labels, self.pad_id)
        wrong_mask = accuracy < 0.5
        return (confidence * wrong_mask.float()).mean()


# ------------------------------------------------------------------
# Pure helpers
# ------------------------------------------------------------------

def _per_sample_accuracy(
    logits: Tensor,
    labels: Tensor,
    pad_id: int,
) -> Tensor:
    """Compute per-sample token-level accuracy, ignoring padding.

    Args:
        logits: (B, S, V)
        labels: (B, S)
        pad_id: token ID to ignore.

    Returns:
        (B,) accuracy for each sample in the batch.
    """
    preds = logits.argmax(dim=-1)           # (B, S)
    mask = labels != pad_id                 # (B, S)

    if not mask.any():
        return torch.zeros(logits.size(0), device=logits.device)

    correct = (preds == labels).float() * mask.float()
    counts = mask.float().sum(dim=-1).clamp(min=1)
    return correct.sum(dim=-1) / counts     # (B,)
