"""Configuration for the Ruh Model."""

from dataclasses import dataclass


@dataclass
class RuhConfig:
    """Central configuration for all Ruh Model components.

    Dimensions follow the triconsonantal root embedding design:
    - d_model: main hidden dimension throughout the transformer
    - d_root: dedicated embedding dimension for root IDs
    - d_pattern: dedicated embedding dimension for morphological pattern IDs
    """

    # --- Model dimensions ---
    d_model: int = 512
    d_root: int = 64
    d_pattern: int = 32

    # --- Transformer architecture ---
    n_heads: int = 8
    n_layers: int = 8

    # --- Vocabulary ---
    n_roots: int = 4000       # Root vocabulary size, IDs 0-3999
    n_patterns: int = 200     # Morphological pattern count

    # --- Sequence ---
    max_seq_len: int = 2048

    # --- Regularisation ---
    dropout: float = 0.1

    # --- Feed-forward ---
    ffn_multiplier: float = 2.667  # SwiGLU uses 2/3 of the standard 4x expansion

    # --- Cardiac oscillation ---
    alpha: float = 0.1  # Amplitude for Qalb-inspired sinusoidal modulation

    # --- Shura MoE ---
    n_experts: int = 4       # Number of FFN experts per MoE layer
    moe_top_k: int = 2       # Top-k experts activated per token
    moe_interval: int = 2    # Insert MoE layer every N blocks (0 = disabled)

    # --- Adaptive depth ---
    adaptive_depth_threshold: float = 0.8

    # --- Hardware ---
    device: str = "cpu"

    # ---- Special token IDs (class-level constants) ----
    PAD_ROOT: int = 0
    BOS_ROOT: int = 1
    EOS_ROOT: int = 2
    UNK_ROOT: int = 3
    FIRST_REAL_ROOT: int = 4

    @property
    def d_ffn(self) -> int:
        """Feed-forward inner dimension (SwiGLU-adjusted)."""
        return int(self.d_model * self.ffn_multiplier)

    @property
    def estimated_param_count(self) -> int:
        """Rough total parameter estimate for the full model.

        Accounts for:
        - Root + pattern embeddings
        - Per-layer: attention (QKV + output) + SwiGLU FFN + layer norms
        - Final projection to root vocabulary
        """
        # Embedding tables
        root_embed = self.n_roots * self.d_root
        pattern_embed = self.n_patterns * self.d_pattern
        # Projection from (d_root + d_pattern) to d_model
        input_proj = (self.d_root + self.d_pattern) * self.d_model

        # Per transformer layer
        qkv = 3 * self.d_model * self.d_model
        attn_out = self.d_model * self.d_model
        # SwiGLU has three weight matrices: W_gate, W_up (both d_model -> d_ffn), W_down (d_ffn -> d_model)
        ffn = 3 * self.d_model * self.d_ffn
        # Two layer norms per layer, each with 2 * d_model params (weight + bias)
        layer_norms = 2 * 2 * self.d_model
        per_layer = qkv + attn_out + ffn + layer_norms

        # Output head
        output_proj = self.d_model * self.n_roots

        total = (
            root_embed
            + pattern_embed
            + input_proj
            + self.n_layers * per_layer
            + output_proj
        )
        return total
