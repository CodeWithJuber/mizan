"""ISM Feed-Forward Network (SwiGLU) for the Ruh Model.

Implements the SwiGLU variant of the feed-forward sub-layer:

    FFN(x) = (Swish(x @ W_gate) * (x @ W_up)) @ W_down

SwiGLU uses three weight matrices instead of two, with a gated activation
(Swish/SiLU) that provides smoother gradients and better training dynamics
than standard ReLU FFN. The FFN expansion factor is adjusted to 2.667x
(instead of 4x) to keep the parameter count comparable.
"""

from __future__ import annotations

import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from ruh_model.config import RuhConfig


class ISMFFN(nn.Module):
    """SwiGLU Feed-Forward Network operating in root-space.

    Architecture:
        gate = SiLU(x @ W_gate)   (d_model -> d_ffn)
        up   = x @ W_up           (d_model -> d_ffn)
        out  = (gate * up) @ W_down  (d_ffn -> d_model)

    Args:
        config: Model configuration providing d_model, d_ffn, and dropout.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.W_gate = nn.Linear(config.d_model, config.d_ffn, bias=False)
        self.W_up = nn.Linear(config.d_model, config.d_ffn, bias=False)
        self.W_down = nn.Linear(config.d_ffn, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: Tensor) -> Tensor:
        """Apply SwiGLU feed-forward transformation.

        Args:
            x: Input tensor of shape (B, N, d_model).

        Returns:
            Output tensor of shape (B, N, d_model).
        """
        gate = F.silu(self.W_gate(x))
        up = self.W_up(x)
        return self.dropout(self.W_down(gate * up))
