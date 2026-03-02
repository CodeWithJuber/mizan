"""Shura (Consultation) Mixture-of-Experts layer for the Ruh Model.

Inspired by the Quranic principle of Shura (42:38) -- "whose affair is
[determined by] consultation among themselves." Each token consults
multiple expert FFNs, and the final output is a weighted combination
of the top-k experts selected by a learned gating network.

4 domain experts: theology, ethics, language, general.
Top-2 routing with load-balancing auxiliary loss to prevent expert collapse.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from ruh_model.config import RuhConfig
from ruh_model.layers.ism_ffn import ISMFFN


class ShuraMoE(nn.Module):
    """Consultative Mixture-of-Experts with top-k routing.

    Each token is routed to the top-k experts via a learned gating network.
    The output is the weighted sum of expert outputs. An auxiliary load-
    balancing loss encourages equal utilisation across experts.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.n_experts = config.n_experts
        self.top_k = config.moe_top_k

        self.gate = nn.Linear(config.d_model, config.n_experts, bias=False)
        self.experts = nn.ModuleList([
            ISMFFN(config) for _ in range(config.n_experts)
        ])

        # Track auxiliary loss for load balancing
        self._aux_loss: Tensor | None = None

    @property
    def aux_loss(self) -> Tensor:
        """Return the most recently computed load-balancing loss."""
        if self._aux_loss is None:
            return torch.tensor(0.0)
        return self._aux_loss

    def forward(self, x: Tensor) -> Tensor:
        """Route tokens to top-k experts and combine outputs.

        Args:
            x: Input tensor (B, N, D).

        Returns:
            Combined expert output (B, N, D).
        """
        batch_size, seq_len, d_model = x.shape

        gate_logits = self.gate(x)  # (B, N, n_experts)
        gate_probs = F.softmax(gate_logits, dim=-1)

        top_k_probs, top_k_indices = gate_probs.topk(self.top_k, dim=-1)
        # Renormalize selected expert weights
        top_k_weights = top_k_probs / top_k_probs.sum(dim=-1, keepdim=True)

        self._aux_loss = _load_balance_loss(gate_probs, top_k_indices, self.n_experts)

        output = _combine_expert_outputs(
            x, self.experts, top_k_indices, top_k_weights
        )
        return output


def _load_balance_loss(
    gate_probs: Tensor,
    top_k_indices: Tensor,
    n_experts: int,
) -> Tensor:
    """Compute auxiliary load-balancing loss (Switch Transformer style).

    Encourages equal token assignment across experts to prevent collapse.

    Args:
        gate_probs: (B, N, E) softmax gating probabilities.
        top_k_indices: (B, N, K) selected expert indices.
        n_experts: Total number of experts.

    Returns:
        Scalar load-balancing loss.
    """
    # Fraction of tokens assigned to each expert
    flat_indices = top_k_indices.reshape(-1)
    counts = torch.zeros(n_experts, device=gate_probs.device)
    for idx in range(n_experts):
        counts[idx] = (flat_indices == idx).float().sum()
    fraction_assigned = counts / counts.sum().clamp(min=1)

    # Mean probability assigned to each expert
    mean_prob = gate_probs.mean(dim=(0, 1))  # (E,)

    # Auxiliary loss: n_experts * sum(fraction * mean_prob)
    return n_experts * (fraction_assigned * mean_prob).sum()


def _combine_expert_outputs(
    x: Tensor,
    experts: nn.ModuleList,
    top_k_indices: Tensor,
    top_k_weights: Tensor,
) -> Tensor:
    """Combine outputs from selected experts weighted by gating scores.

    Args:
        x: Input tensor (B, N, D).
        experts: List of expert FFN modules.
        top_k_indices: (B, N, K) selected expert indices.
        top_k_weights: (B, N, K) normalized weights for selected experts.

    Returns:
        Weighted combination of expert outputs (B, N, D).
    """
    batch_size, seq_len, d_model = x.shape
    k = top_k_indices.size(-1)

    output = torch.zeros_like(x)
    for expert_idx in range(k):
        indices = top_k_indices[:, :, expert_idx]   # (B, N)
        weights = top_k_weights[:, :, expert_idx]    # (B, N)

        for eidx, expert in enumerate(experts):
            mask = indices == eidx  # (B, N)
            if not mask.any():
                continue
            expert_input = x * mask.unsqueeze(-1).float()
            expert_out = expert(expert_input)
            output = output + expert_out * (weights * mask.float()).unsqueeze(-1)

    return output
