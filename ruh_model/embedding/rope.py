"""Rotary Position Encoding (RoPE) and RMSNorm for the Ruh Model.

RoPE encodes absolute position via rotation matrices applied to query/key
pairs, enabling relative position awareness without additive position
embeddings. RMSNorm provides a simpler, faster alternative to LayerNorm.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor


class RMSNorm(nn.Module):
    """Root Mean Square Layer Normalization.

    Normalises the input by its RMS value and scales with a learnable
    weight vector. Faster than LayerNorm because it skips the mean
    subtraction step.
    """

    def __init__(self, dim: int, eps: float = 1e-6) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: Tensor) -> Tensor:
        rms = torch.sqrt(torch.mean(x * x, dim=-1, keepdim=True) + self.eps)
        return (x / rms) * self.weight


def _rotate_half(x: Tensor) -> Tensor:
    """Rotate the second half of the last dimension and negate it.

    Splits x into two halves along the last dim, then returns [-x2, x1].
    This is the standard rotation used in RoPE.
    """
    first_half, second_half = x.chunk(2, dim=-1)
    return torch.cat((-second_half, first_half), dim=-1)


def apply_rotary_pos_emb(
    query: Tensor,
    key: Tensor,
    cos: Tensor,
    sin: Tensor,
) -> tuple[Tensor, Tensor]:
    """Apply rotary position embeddings to query and key tensors.

    Args:
        query: (B, n_heads, S, head_dim) query tensor.
        key: (B, n_heads, S, head_dim) key tensor.
        cos: (1, 1, S, head_dim) cosine cache for positions.
        sin: (1, 1, S, head_dim) sine cache for positions.

    Returns:
        Tuple of (rotated_query, rotated_key) with same shapes as inputs.
    """
    query_embed = (query * cos) + (_rotate_half(query) * sin)
    key_embed = (key * cos) + (_rotate_half(key) * sin)
    return query_embed, key_embed


class RotaryPositionEncoding(nn.Module):
    """Rotary Position Encoding (RoPE).

    Precomputes cos/sin frequency caches up to max_seq_len, then applies
    rotation to input tensors on forward pass. Registered as non-persistent
    buffers so they move with the model to different devices but are not
    saved in state_dict.
    """

    def __init__(
        self,
        dim: int,
        max_seq_len: int = 2048,
        base: float = 10000.0,
    ) -> None:
        super().__init__()
        self.dim = dim
        self.max_seq_len = max_seq_len
        self.base = base

        cos_cache, sin_cache = self._build_cache(max_seq_len)
        self.register_buffer("cos_cache", cos_cache, persistent=False)
        self.register_buffer("sin_cache", sin_cache, persistent=False)

    def _build_cache(self, seq_len: int) -> tuple[Tensor, Tensor]:
        """Precompute cos and sin values for all positions up to seq_len."""
        # Frequency bands: 1 / (base^(2i/dim)) for i in [0, dim/2)
        inv_freq = 1.0 / (
            self.base ** (torch.arange(0, self.dim, 2).float() / self.dim)
        )
        positions = torch.arange(seq_len).float()
        # Outer product: (seq_len, dim/2)
        angles = torch.outer(positions, inv_freq)
        # Duplicate to cover full dim: (seq_len, dim)
        angles = torch.cat([angles, angles], dim=-1)
        # Shape for broadcasting: (1, 1, seq_len, dim)
        cos_cache = angles.cos().unsqueeze(0).unsqueeze(0)
        sin_cache = angles.sin().unsqueeze(0).unsqueeze(0)
        return cos_cache, sin_cache

    def forward(self, x: Tensor, seq_len: int) -> tuple[Tensor, Tensor]:
        """Return cos and sin caches sliced to the requested sequence length.

        Args:
            x: Input tensor (used only for device/dtype matching).
            seq_len: Actual sequence length to slice caches to.

        Returns:
            Tuple of (cos, sin) each shaped (1, 1, seq_len, dim).
        """
        if seq_len > self.max_seq_len:
            cos_cache, sin_cache = self._build_cache(seq_len)
            return (
                cos_cache.to(x.device, x.dtype),
                sin_cache.to(x.device, x.dtype),
            )
        return (
            self.cos_cache[:, :, :seq_len, :].to(x.dtype),
            self.sin_cache[:, :, :seq_len, :].to(x.dtype),
        )
