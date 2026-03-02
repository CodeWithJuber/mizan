"""Ruh Transformer Block for the Ruh Model.

Each block follows the pre-norm residual pattern:

    x = x + Attention(Norm(x))
    x = x + FFN(Norm(x))

The first block in the stack uses SamBasarDual (causal + bidirectional
fusion) for richer initial representations. All subsequent blocks use
QalbAttention with cardiac oscillation for efficient processing.

Blocks at MoE positions replace the standard FFN with ShuraMoE routing.
"""

from __future__ import annotations

from typing import Optional, Union

import torch.nn as nn
from torch import Tensor

from ruh_model.config import RuhConfig
from ruh_model.attention.qalb import QalbAttention
from ruh_model.attention.sam_basar import SamBasarDual
from ruh_model.embedding.rope import RMSNorm
from ruh_model.layers.ism_ffn import ISMFFN
from ruh_model.layers.shura_moe import ShuraMoE


class RuhBlock(nn.Module):
    """Single Ruh transformer block with pre-norm residual connections.

    Architecture:
        1. Pre-norm attention (QalbAttention or SamBasarDual)
        2. Residual add
        3. Pre-norm FFN (ISMFFN or ShuraMoE)
        4. Residual add

    Args:
        config: Model configuration.
        use_dual: If True, use SamBasarDual attention.
        use_moe: If True, use ShuraMoE instead of standard FFN.
    """

    def __init__(
        self,
        config: RuhConfig,
        use_dual: bool = False,
        use_moe: bool = False,
    ) -> None:
        super().__init__()
        self.attn_norm = RMSNorm(config.d_model)
        self.ffn_norm = RMSNorm(config.d_model)

        self.attention: Union[SamBasarDual, QalbAttention]
        if use_dual:
            self.attention = SamBasarDual(config)
        else:
            self.attention = QalbAttention(config)

        self.use_moe = use_moe
        if use_moe and config.moe_interval > 0:
            self.ffn: Union[ISMFFN, ShuraMoE] = ShuraMoE(config)
        else:
            self.ffn = ISMFFN(config)

    def forward(
        self,
        x: Tensor,
        root_ids: Tensor,
        t_step: int = 0,
        mask: Optional[Tensor] = None,
    ) -> Tensor:
        """Forward pass through one transformer block.

        Args:
            x: Hidden states (B, N, D).
            root_ids: Root IDs per token (B, N).
            t_step: Processing step for cardiac oscillation.
            mask: Optional attention mask.

        Returns:
            Output tensor (B, N, D).
        """
        # Pre-norm residual attention
        hidden = x + self.attention(self.attn_norm(x), root_ids, t_step, mask)
        # Pre-norm residual FFN (or MoE)
        output = hidden + self.ffn(self.ffn_norm(hidden))
        return output
