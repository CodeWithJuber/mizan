"""Qalb (Heart) Attention for the Ruh Model.

Implements multi-head self-attention with cardiac oscillation modulation.
The oscillation parameter psi(t) = 1 + alpha * sin(2*pi*t / T) modulates
the attention temperature:

    - psi < 1 (Qabd / contraction): sharper, more focused attention
    - psi > 1 (Bast / expansion): broader, more exploratory attention

The root_ids input enables future root-grouped attention optimization
(O(R^2) instead of O(N^2)), but the current implementation uses standard
multi-head attention for batching efficiency.
"""

from __future__ import annotations

import math
from typing import Optional

import torch
import torch.nn as nn
from torch import Tensor

from ruh_model.config import RuhConfig
from ruh_model.embedding.rope import (
    RotaryPositionEncoding,
    apply_rotary_pos_emb,
)

TWO_PI = 2.0 * math.pi


def build_root_group_mask(root_ids: Tensor) -> Tensor:
    """Build a boolean mask where tokens with the same root can attend to each other.

    Args:
        root_ids: (B, N) root ID per token.

    Returns:
        (B, N, N) boolean mask.
    """
    return root_ids.unsqueeze(-1) == root_ids.unsqueeze(-2)


def _compute_cardiac_oscillation(
    t_step: int,
    period: Tensor,
    alpha: Tensor,
) -> Tensor:
    """Compute the cardiac oscillation factor psi(t).

    Args:
        t_step: Current processing step (e.g., layer index).
        period: Period tensor; scalar or (B,) for per-sample modulation.
        alpha: Learnable oscillation amplitude (scalar Parameter).

    Returns:
        psi = 1 + alpha * sin(2*pi*t / T).
        Shape matches period: scalar tensor or (B,).
    """
    phase = torch.tensor(
        TWO_PI * t_step,
        dtype=period.dtype,
        device=period.device,
    )
    return 1.0 + alpha * torch.sin(phase / period)


def _project_qkv(
    x: Tensor,
    w_q: nn.Linear,
    w_k: nn.Linear,
    w_v: nn.Linear,
    n_heads: int,
    head_dim: int,
) -> tuple[Tensor, Tensor, Tensor]:
    """Project input to query, key, value and reshape for multi-head attention.

    Args:
        x: Input tensor (B, N, D).
        w_q: Query projection.
        w_k: Key projection.
        w_v: Value projection.
        n_heads: Number of attention heads.
        head_dim: Dimension per head.

    Returns:
        Tuple of (Q, K, V) each shaped (B, n_heads, N, head_dim).
    """
    batch_size, seq_len, _ = x.shape
    query = w_q(x).view(batch_size, seq_len, n_heads, head_dim).transpose(1, 2)
    key = w_k(x).view(batch_size, seq_len, n_heads, head_dim).transpose(1, 2)
    value = w_v(x).view(batch_size, seq_len, n_heads, head_dim).transpose(1, 2)
    return query, key, value


def _scaled_dot_product_attention(
    query: Tensor,
    key: Tensor,
    value: Tensor,
    scale: Tensor,
    mask: Optional[Tensor],
    dropout: nn.Dropout,
) -> Tensor:
    """Compute scaled dot-product attention with optional masking.

    Args:
        query: (B, n_heads, N, head_dim).
        key: (B, n_heads, N, head_dim).
        value: (B, n_heads, N, head_dim).
        scale: Scalar tensor or (B, 1, 1, 1) tensor for attention scaling.
        mask: Optional mask; positions with 0 are masked out.
        dropout: Dropout module for attention weights.

    Returns:
        Attention output of shape (B, n_heads, N, head_dim).
    """
    attn_weights = torch.matmul(query, key.transpose(-2, -1)) / scale

    if mask is not None:
        attn_weights = attn_weights.masked_fill(mask == 0, float("-inf"))

    attn_weights = torch.softmax(attn_weights, dim=-1)
    attn_weights = dropout(attn_weights)

    return torch.matmul(attn_weights, value)


class QalbAttention(nn.Module):
    """Root-aware multi-head self-attention with cardiac oscillation.

    Standard multi-head attention where the softmax temperature is modulated
    by a cardiac oscillation signal psi(t). This creates a rhythmic
    alternation between focused (Qabd) and broad (Bast) attention states
    across layers.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.n_heads = config.n_heads
        self.d_model = config.d_model
        self.head_dim = config.d_model // config.n_heads

        # Per-layer learned amplitude; allows each layer to tune its own rhythm
        self.alpha = nn.Parameter(torch.tensor(config.alpha))

        self.W_q = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_k = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_v = nn.Linear(config.d_model, config.d_model, bias=False)
        self.W_o = nn.Linear(config.d_model, config.d_model, bias=False)

        self.rope = RotaryPositionEncoding(self.head_dim, config.max_seq_len)

        # Learnable base oscillation period
        self.T_base = nn.Parameter(torch.tensor(10.0))

        # Projects mean token embedding to a complexity scalar for period modulation
        self.complexity_proj = nn.Linear(config.d_model, 1, bias=True)

        self.dropout = nn.Dropout(config.dropout)

    def forward(
        self,
        x: Tensor,
        root_ids: Tensor,
        t_step: int = 0,
        mask: Optional[Tensor] = None,
    ) -> Tensor:
        """Forward pass for Qalb attention.

        Args:
            x: Hidden states (B, N, D).
            root_ids: Root IDs per token (B, N). Reserved for future
                root-grouped optimization; see build_root_group_mask().
            t_step: Processing step for cardiac oscillation (typically
                the layer index).
            mask: Optional attention mask (B, N, N) or (N, N).
                Positions with 0 are masked out.

        Returns:
            Output tensor of shape (B, N, D).
        """
        batch_size, seq_len, d_model = x.shape

        query, key, value = _project_qkv(
            x, self.W_q, self.W_k, self.W_v, self.n_heads, self.head_dim
        )

        # Apply rotary position encoding
        cos, sin = self.rope(query, seq_len)
        query, key = apply_rotary_pos_emb(query, key, cos, sin)

        # Complexity-adaptive period: longer sequences or richer context get
        # a wider oscillation cycle, encouraging broader attention exploration.
        complexity = torch.sigmoid(self.complexity_proj(x.mean(dim=1)))  # (B, 1)
        T_effective = (self.T_base.abs() + 1.0) * (0.5 + complexity.squeeze(-1))  # (B,)

        psi = _compute_cardiac_oscillation(t_step, T_effective, self.alpha)  # (B,)

        # Reshape for broadcasting over (B, n_heads, N, N)
        scale = math.sqrt(self.head_dim) * psi.view(-1, 1, 1, 1)

        out = _scaled_dot_product_attention(
            query, key, value, scale, mask, self.dropout
        )

        # Merge heads and project output
        out = out.transpose(1, 2).contiguous().view(batch_size, seq_len, d_model)
        return self.W_o(out)
