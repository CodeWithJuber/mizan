"""Ruh Model -- Full transformer language model for Arabic root-space.

Assembles all components into a complete language model:
    1. ISMEmbedding: factored (root, pattern) -> d_model embedding
    2. RuhBlock stack: first block uses SamBasarDual, rest use QalbAttention
    3. Final RMSNorm + weight-tied output projection to root vocabulary

Uses MizanLoss (5-component composite objective) for training instead of
raw cross-entropy. Supports next-token prediction and autoregressive generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from ruh_model.config import RuhConfig
from ruh_model.embedding.ism import ISMEmbedding
from ruh_model.embedding.rope import RMSNorm
from ruh_model.layers.transformer_block import RuhBlock
from ruh_model.loss.mizan_loss import MizanLoss


class RuhModel(nn.Module):
    """Full Ruh language model.

    Architecture:
        - Factored ISM embedding (root + pattern -> d_model)
        - N transformer blocks (first = SamBasarDual, rest = QalbAttention)
        - RMSNorm final normalisation
        - Weight-tied output projection to root vocabulary logits
        - MizanLoss composite objective (CE + calibration + consistency + fitrah + hisbah)

    Args:
        config: Model configuration.
    """

    def __init__(self, config: RuhConfig) -> None:
        super().__init__()
        self.config = config
        self.embedding = ISMEmbedding(config)

        # First block uses dual (Sam' + Basar) attention, rest use Qalb.
        # Blocks at MoE intervals get ShuraMoE instead of standard FFN.
        moe_on = config.moe_interval > 0
        self.blocks = nn.ModuleList([
            RuhBlock(
                config,
                use_dual=(i == 0),
                use_moe=(moe_on and i > 0 and i % config.moe_interval == 0),
            )
            for i in range(config.n_layers)
        ])

        self.final_norm = RMSNorm(config.d_model)
        self.loss_fn = MizanLoss(
            pad_id=config.PAD_ROOT,
            vocab_size=config.n_roots,
        )

    def forward(
        self,
        root_ids: Tensor,
        pattern_ids: Tensor,
        labels: Optional[Tensor] = None,
        confidence: Optional[Tensor] = None,
        paraphrase_logits: Optional[Tensor] = None,
    ) -> dict[str, Any]:
        """Forward pass through the full model.

        Args:
            root_ids: (B, S) integer root vocabulary indices.
            pattern_ids: (B, S) integer morphological pattern indices.
            labels: (B, S) optional target root IDs for next-token
                prediction loss. PAD_ROOT positions are ignored.
            confidence: (B,) optional confidence scores from LubbMetacognition.
            paraphrase_logits: (B, S, V) optional logits from paraphrase inputs.

        Returns:
            Dict with 'logits' (B, S, n_roots). When labels are provided,
            also includes 'loss' (scalar), 'loss_breakdown' (MizanLossOutput).
        """
        hidden = self.embedding(root_ids, pattern_ids)

        for layer_idx, block in enumerate(self.blocks):
            hidden = block(hidden, root_ids, t_step=layer_idx)

        hidden = self.final_norm(hidden)

        logits = self._compute_logits(hidden)
        result: dict[str, Any] = {"logits": logits}

        if labels is not None:
            loss_output = self.loss_fn(
                logits, labels, confidence, paraphrase_logits
            )
            result["loss"] = loss_output.total
            result["loss_breakdown"] = loss_output

        return result

    def _compute_logits(self, hidden: Tensor) -> Tensor:
        """Project hidden states to root vocabulary logits (weight-tied).

        Args:
            hidden: Normalised hidden states (B, S, d_model).

        Returns:
            Logits tensor of shape (B, S, n_roots).
        """
        output_weight = self.embedding.get_output_projection_weight()
        return F.linear(hidden, output_weight)

    @torch.no_grad()
    def generate(
        self,
        root_ids: Tensor,
        pattern_ids: Tensor,
        max_new_tokens: int = 128,
        temperature: float = 1.0,
        default_pattern_id: int = 1,
    ) -> Tensor:
        """Autoregressive generation of root ID sequences.

        Uses simple temperature-scaled sampling. For each new token,
        runs a full forward pass and samples from the last position.

        Args:
            root_ids: (B, S) initial root ID prompt.
            pattern_ids: (B, S) initial pattern ID prompt.
            max_new_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature. Lower = more deterministic.
            default_pattern_id: Pattern ID to assign to generated tokens.

        Returns:
            Tensor of shape (B, S + max_new_tokens) with generated root IDs.
        """
        generated = root_ids.clone()
        patterns = pattern_ids.clone()

        for _ in range(max_new_tokens):
            next_token = self._sample_next_token(
                generated, patterns, temperature
            )
            generated = torch.cat([generated, next_token], dim=1)

            # Extend patterns with default pattern for generated token
            pattern_extension = torch.full_like(next_token, default_pattern_id)
            patterns = torch.cat([patterns, pattern_extension], dim=1)

            # Stop if all sequences have generated EOS
            if (next_token == self.config.EOS_ROOT).all():
                break

        return generated

    def _sample_next_token(
        self,
        root_ids: Tensor,
        pattern_ids: Tensor,
        temperature: float,
    ) -> Tensor:
        """Sample a single next token from model output.

        Args:
            root_ids: Current sequence (B, S).
            pattern_ids: Current patterns (B, S).
            temperature: Sampling temperature.

        Returns:
            Sampled token IDs of shape (B, 1).
        """
        result = self.forward(root_ids, pattern_ids)
        logits = result["logits"][:, -1, :]

        if temperature <= 0:
            return logits.argmax(dim=-1, keepdim=True)

        probs = torch.softmax(logits / temperature, dim=-1)
        return torch.multinomial(probs, num_samples=1)

    def count_parameters(self) -> int:
        """Count total trainable parameters.

        Returns:
            Number of trainable parameters.
        """
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def save_pretrained(self, path: str) -> None:
        """Save model weights and config to a directory.

        Saves:
            - config.json: serialised RuhConfig
            - model.pt: state dict (PyTorch format)

        Args:
            path: Directory path to save into. Created if it does not exist.
        """
        save_dir = Path(path)
        save_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            field: getattr(self.config, field)
            for field in self.config.__dataclass_fields__
        }
        config_path = save_dir / "config.json"
        config_path.write_text(json.dumps(config_data, indent=2))

        model_path = save_dir / "model.pt"
        torch.save(self.state_dict(), model_path)

    @classmethod
    def from_pretrained(cls, path: str) -> RuhModel:
        """Load model from a saved checkpoint directory.

        Expects a directory containing config.json and model.pt
        as saved by save_pretrained().

        Args:
            path: Directory path containing the checkpoint.

        Returns:
            Loaded RuhModel instance with restored weights.

        Raises:
            FileNotFoundError: If config.json or model.pt is missing.
        """
        load_dir = Path(path)

        config_path = load_dir / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")

        config_data = json.loads(config_path.read_text())
        config = RuhConfig(**config_data)

        model = cls(config)

        model_path = load_dir / "model.pt"
        if not model_path.exists():
            raise FileNotFoundError(f"Model weights not found: {model_path}")

        state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)

        return model
