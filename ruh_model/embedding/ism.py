"""ISM Root-Space Embedding for the Ruh Model.

Implements a factored embedding that decomposes each token into a
(root_id, pattern_id) pair. Instead of a standard V x d_model embedding
table (~38.4M params for V=50K, d_model=768), we factor it as:

    W_root:    (n_roots, d_root)      = (4000, 64)  = 256K params
    W_pattern: (n_patterns, d_pattern) = (200, 32)   =  6.4K params
    Total: ~262K params (146x compression vs standard)

The root and pattern embeddings are combined via gated additive composition:
    root_proj + pattern_proj + (interact_proj * sigmoid(gate_proj))

This avoids the d_root * d_pattern = 2048 dimensional outer-product
intermediate, keeping all projections at d_model width throughout.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
from torch import Tensor

from ruh_model.config import RuhConfig
from ruh_model.embedding.rope import RMSNorm


class ISMEmbedding(nn.Module):
    """Factored embedding using triconsonantal root + morphological pattern.

    Each input token is represented by a (root_id, pattern_id) pair.
    The embedding is computed as:
        1. Look up root embedding vector    (B, S, d_root)
        2. Look up pattern embedding vector (B, S, d_pattern)
        3. Project root to d_model          (B, S, d_model)
        4. Project pattern to d_model       (B, S, d_model)
        5. Compute gated interaction:
               gate     = sigmoid(W_gate(pattern_emb))
               interact = W_interact(root_emb) * gate
        6. Add: root_proj + pattern_proj + interact  (B, S, d_model)
        7. Apply RMSNorm, scale by sqrt(d_model), dropout

    The gated additive approach avoids the wasteful d_root * d_pattern = 2048
    dimensional outer-product intermediate while retaining a multiplicative
    interaction between root and pattern signals.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.d_model = config.d_model
        self.d_root = config.d_root
        self.d_pattern = config.d_pattern
        self.scale = math.sqrt(config.d_model)

        self.root_embedding = nn.Embedding(config.n_roots, config.d_root)
        self.pattern_embedding = nn.Embedding(config.n_patterns, config.d_pattern)

        # Four lightweight projections, all landing at d_model width
        self.root_proj = nn.Linear(config.d_root, config.d_model, bias=False)
        self.pattern_proj = nn.Linear(config.d_pattern, config.d_model, bias=False)
        self.interact_proj = nn.Linear(config.d_root, config.d_model, bias=False)
        self.gate_proj = nn.Linear(config.d_pattern, config.d_model, bias=False)

        self.norm = RMSNorm(config.d_model)
        self.dropout = nn.Dropout(config.dropout)

        self._init_weights()

    def _init_weights(self) -> None:
        """Xavier-uniform initialization for embeddings and all projection layers."""
        nn.init.xavier_uniform_(self.root_embedding.weight)
        nn.init.xavier_uniform_(self.pattern_embedding.weight)
        nn.init.xavier_uniform_(self.root_proj.weight)
        nn.init.xavier_uniform_(self.pattern_proj.weight)
        nn.init.xavier_uniform_(self.interact_proj.weight)
        nn.init.xavier_uniform_(self.gate_proj.weight)

    def forward(self, root_ids: Tensor, pattern_ids: Tensor) -> Tensor:
        """Compute factored embedding from root and pattern IDs.

        Args:
            root_ids: (B, S) integer tensor of root vocabulary indices.
            pattern_ids: (B, S) integer tensor of pattern indices.

        Returns:
            Embedded representation of shape (B, S, d_model).
        """
        root_emb = self.root_embedding(root_ids)       # (B, S, d_root)
        pattern_emb = self.pattern_embedding(pattern_ids)  # (B, S, d_pattern)

        root_projected = self.root_proj(root_emb)          # (B, S, d_model)
        pattern_projected = self.pattern_proj(pattern_emb)  # (B, S, d_model)
        gate = torch.sigmoid(self.gate_proj(pattern_emb))   # (B, S, d_model)
        interact = self.interact_proj(root_emb) * gate       # (B, S, d_model)

        combined = root_projected + pattern_projected + interact  # (B, S, d_model)

        normalized = self.norm(combined)
        scaled = normalized * self.scale
        return self.dropout(scaled)

    def get_output_projection_weight(self) -> Tensor:
        """Compute the output projection weight for weight-tied decoding.

        For a weight-tied output head we need a matrix mapping d_model back
        to root vocabulary logits of shape (n_roots, d_model).

        With the gated additive composition, root_proj directly maps
        d_root -> d_model, so the tied weight is simply:

            root_embedding.weight @ root_proj.weight.T
              (n_roots, d_root) @ (d_root, d_model) -> (n_roots, d_model)

        Returns:
            Weight matrix of shape (n_roots, d_model) suitable for the
            output linear layer.
        """
        # root_embedding.weight: (n_roots, d_root)
        # root_proj.weight:      (d_model, d_root)
        return self.root_embedding.weight @ self.root_proj.weight.T

    def param_count(self) -> int:
        """Count total trainable parameters in this module.

        Returns:
            Total number of trainable parameters.
        """
        return sum(
            param.numel() for param in self.parameters() if param.requires_grad
        )
