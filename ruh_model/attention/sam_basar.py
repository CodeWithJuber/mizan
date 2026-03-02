"""Sam'-Basar Dual Processing for the Ruh Model.

Implements the Fuad (heart/core understanding) fusion of two complementary
attention modalities:

    Sam' (السمع / Hearing): Causal/sequential processing. Each position
    attends only to previous positions, modelling temporal flow like
    auditory comprehension.

    Basar (البصر / Sight): Bidirectional/structural processing. Each
    position attends to all positions, modelling holistic pattern
    recognition like visual comprehension.

The Fuad module fuses these two streams via a learned sigmoid gate,
dynamically blending sequential and structural understanding per token.
"""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn
from torch import Tensor

from ruh_model.config import RuhConfig
from ruh_model.attention.qalb import QalbAttention
from ruh_model.embedding.rope import RMSNorm


def _build_causal_mask(seq_len: int, device: torch.device) -> Tensor:
    """Build a lower-triangular causal mask.

    Args:
        seq_len: Sequence length.
        device: Target device.

    Returns:
        Boolean mask of shape (1, 1, seq_len, seq_len) where True
        indicates allowed positions and False indicates masked positions.
    """
    mask = torch.tril(torch.ones(seq_len, seq_len, device=device))
    return mask.unsqueeze(0).unsqueeze(0)


class SamProcessor(nn.Module):
    """Sam' (السمع) -- Causal/sequential processing (like hearing).

    Wraps QalbAttention with an auto-generated causal mask so each
    position only attends to itself and previous positions.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.attention = QalbAttention(config)

    def forward(
        self,
        x: Tensor,
        root_ids: Tensor,
        t_step: int = 0,
        mask: Optional[Tensor] = None,
    ) -> Tensor:
        """Forward pass with causal masking.

        Args:
            x: Hidden states (B, N, D).
            root_ids: Root IDs per token (B, N).
            t_step: Processing step for cardiac oscillation.
            mask: Ignored; causal mask is always applied.

        Returns:
            Output tensor (B, N, D).
        """
        seq_len = x.shape[1]
        causal_mask = _build_causal_mask(seq_len, x.device)
        return self.attention(x, root_ids, t_step, causal_mask)


class BasarProcessor(nn.Module):
    """Basar (البصر) -- Bidirectional/structural processing (like sight).

    Wraps QalbAttention without any mask, allowing full bidirectional
    attention for global pattern recognition.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.attention = QalbAttention(config)

    def forward(
        self,
        x: Tensor,
        root_ids: Tensor,
        t_step: int = 0,
        mask: Optional[Tensor] = None,
    ) -> Tensor:
        """Forward pass with full bidirectional attention.

        Args:
            x: Hidden states (B, N, D).
            root_ids: Root IDs per token (B, N).
            t_step: Processing step for cardiac oscillation.
            mask: Ignored; no mask is applied (bidirectional).

        Returns:
            Output tensor (B, N, D).
        """
        return self.attention(x, root_ids, t_step, mask=None)


class SamBasarDual(nn.Module):
    """Fuad (الفؤاد) -- Fuses sequential and structural understanding.

    Combines the outputs of Sam' (causal) and Basar (bidirectional)
    attention through a learned sigmoid gate. The gate determines per-token
    how much to rely on sequential vs. structural processing:

        gate = sigmoid(Linear([sam_out; basar_out]))
        output = gate * sam_out + (1 - gate) * basar_out

    Args:
        config: Model configuration.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.sam = SamProcessor(config)
        self.basar = BasarProcessor(config)

        self.gate = nn.Linear(config.d_model * 2, config.d_model, bias=False)
        self.gate_act = nn.Sigmoid()
        self.norm = RMSNorm(config.d_model)

    def forward(
        self,
        x: Tensor,
        root_ids: Tensor,
        t_step: int = 0,
        mask: Optional[Tensor] = None,
    ) -> Tensor:
        """Forward pass fusing causal and bidirectional attention.

        Args:
            x: Hidden states (B, N, D).
            root_ids: Root IDs per token (B, N).
            t_step: Processing step for cardiac oscillation.
            mask: Accepted for interface compatibility; not used internally
                (Sam' always applies causal, Basar always applies none).

        Returns:
            Fused output tensor (B, N, D).
        """
        sam_out = self.sam(x, root_ids, t_step)
        basar_out = self.basar(x, root_ids, t_step)
        return self._fuse(sam_out, basar_out)

    def _fuse(self, sam_out: Tensor, basar_out: Tensor) -> Tensor:
        """Gated fusion of Sam' and Basar outputs.

        Args:
            sam_out: Causal attention output (B, N, D).
            basar_out: Bidirectional attention output (B, N, D).

        Returns:
            Fused and normalised output (B, N, D).
        """
        combined = torch.cat([sam_out, basar_out], dim=-1)
        gate_value = self.gate_act(self.gate(combined))
        fused = gate_value * sam_out + (1.0 - gate_value) * basar_out
        return self.norm(fused)
