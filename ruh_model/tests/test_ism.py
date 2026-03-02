"""Tests for ISMEmbedding, RoPE, and RMSNorm -- neural embedding components."""

from __future__ import annotations

import pytest

try:
    import torch

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from ruh_model.config import RuhConfig

pytestmark = pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")


# ---------------------------------------------------------------------------
# ISMEmbedding
# ---------------------------------------------------------------------------


class TestISMEmbedding:
    """Factored root+pattern embedding layer."""

    def _make_embedding(self, config: RuhConfig):
        from ruh_model.embedding.ism import ISMEmbedding

        return ISMEmbedding(config)

    def test_forward_shape(self, sample_config: RuhConfig) -> None:
        """Output shape must be (batch, seq_len, d_model)."""
        embedding = self._make_embedding(sample_config)

        batch_size, seq_len = 2, 16
        root_ids = torch.randint(0, sample_config.n_roots, (batch_size, seq_len))
        pattern_ids = torch.randint(0, sample_config.n_patterns, (batch_size, seq_len))

        output = embedding(root_ids, pattern_ids)

        assert output.shape == (batch_size, seq_len, sample_config.d_model)

    def test_forward_single_token(self, sample_config: RuhConfig) -> None:
        """Single-token input (B=1, S=1) works without error."""
        embedding = self._make_embedding(sample_config)

        root_ids = torch.tensor([[5]])
        pattern_ids = torch.tensor([[1]])

        output = embedding(root_ids, pattern_ids)
        assert output.shape == (1, 1, sample_config.d_model)

    def test_param_count(self, sample_config: RuhConfig) -> None:
        """Parameter count should be reasonable for small config (< 2M)."""
        embedding = self._make_embedding(sample_config)
        count = embedding.param_count()

        assert count > 0
        assert count < 2_000_000, (
            f"Param count {count} exceeds 2M for small config"
        )

        # Sanity: should include root embed + pattern embed + projection + norm
        expected_min = (
            sample_config.n_roots * sample_config.d_root
            + sample_config.n_patterns * sample_config.d_pattern
        )
        assert count > expected_min, (
            f"Param count {count} too low, expected at least {expected_min}"
        )

    def test_gradient_flow(self, sample_config: RuhConfig) -> None:
        """Backpropagation produces non-zero gradients on embedding weights."""
        embedding = self._make_embedding(sample_config)

        root_ids = torch.randint(0, sample_config.n_roots, (2, 8))
        pattern_ids = torch.randint(0, sample_config.n_patterns, (2, 8))

        output = embedding(root_ids, pattern_ids)
        loss = output.sum()
        loss.backward()

        # Root embedding should have gradients
        assert embedding.root_embedding.weight.grad is not None
        assert embedding.root_embedding.weight.grad.abs().sum() > 0

        # Pattern embedding should have gradients
        assert embedding.pattern_embedding.weight.grad is not None
        assert embedding.pattern_embedding.weight.grad.abs().sum() > 0

        # root_proj should have gradients (primary projection layer)
        assert embedding.root_proj.weight.grad is not None
        assert embedding.root_proj.weight.grad.abs().sum() > 0

    def test_output_projection_shape(self, sample_config: RuhConfig) -> None:
        """get_output_projection_weight() returns (n_roots, d_model)."""
        embedding = self._make_embedding(sample_config)
        weight = embedding.get_output_projection_weight()

        assert weight.shape == (sample_config.n_roots, sample_config.d_model)

    def test_output_projection_is_differentiable(
        self, sample_config: RuhConfig
    ) -> None:
        """Output projection weight should retain gradient graph."""
        embedding = self._make_embedding(sample_config)
        weight = embedding.get_output_projection_weight()

        assert weight.requires_grad

    def test_different_inputs_different_outputs(
        self, sample_config: RuhConfig
    ) -> None:
        """Different root/pattern IDs produce different embeddings."""
        embedding = self._make_embedding(sample_config)

        root_a = torch.tensor([[4, 5, 6]])
        root_b = torch.tensor([[7, 8, 9]])
        pattern = torch.tensor([[1, 2, 3]])

        out_a = embedding(root_a, pattern)
        out_b = embedding(root_b, pattern)

        # Outputs should differ
        assert not torch.allclose(out_a, out_b)


# ---------------------------------------------------------------------------
# RotaryPositionEncoding
# ---------------------------------------------------------------------------


class TestRotaryPositionEncoding:
    """RoPE cos/sin cache and application."""

    def _make_rope(self, dim: int = 64, max_seq_len: int = 128):
        from ruh_model.embedding.rope import RotaryPositionEncoding

        return RotaryPositionEncoding(dim=dim, max_seq_len=max_seq_len)

    def test_rope_forward_shape(self) -> None:
        """cos/sin caches have shape (1, 1, seq_len, dim)."""
        dim, max_seq_len = 64, 128
        rope = self._make_rope(dim=dim, max_seq_len=max_seq_len)

        dummy = torch.zeros(1)
        seq_len = 32
        cos_out, sin_out = rope(dummy, seq_len)

        assert cos_out.shape == (1, 1, seq_len, dim)
        assert sin_out.shape == (1, 1, seq_len, dim)

    def test_rope_max_seq_len(self) -> None:
        """Requesting exactly max_seq_len should work."""
        dim, max_seq_len = 32, 64
        rope = self._make_rope(dim=dim, max_seq_len=max_seq_len)

        dummy = torch.zeros(1)
        cos_out, sin_out = rope(dummy, max_seq_len)

        assert cos_out.shape == (1, 1, max_seq_len, dim)
        assert sin_out.shape == (1, 1, max_seq_len, dim)

    def test_rope_exceeds_max_rebuilds(self) -> None:
        """Requesting > max_seq_len triggers cache rebuild, not an error."""
        dim, max_seq_len = 32, 64
        rope = self._make_rope(dim=dim, max_seq_len=max_seq_len)

        dummy = torch.zeros(1)
        longer = max_seq_len + 16
        cos_out, sin_out = rope(dummy, longer)

        assert cos_out.shape == (1, 1, longer, dim)
        assert sin_out.shape == (1, 1, longer, dim)

    def test_rope_apply(self) -> None:
        """apply_rotary_pos_emb returns tensors of the same shape as input."""
        from ruh_model.embedding.rope import apply_rotary_pos_emb

        batch, heads, seq_len, head_dim = 2, 4, 16, 32
        query = torch.randn(batch, heads, seq_len, head_dim)
        key = torch.randn(batch, heads, seq_len, head_dim)

        rope = self._make_rope(dim=head_dim, max_seq_len=seq_len)
        cos_cache, sin_cache = rope(query, seq_len)

        rotated_query, rotated_key = apply_rotary_pos_emb(
            query, key, cos_cache, sin_cache
        )

        assert rotated_query.shape == query.shape
        assert rotated_key.shape == key.shape

    def test_rope_values_bounded(self) -> None:
        """cos/sin outputs are bounded in [-1, 1]."""
        rope = self._make_rope(dim=64, max_seq_len=128)
        dummy = torch.zeros(1)
        cos_out, sin_out = rope(dummy, 128)

        assert cos_out.min() >= -1.0
        assert cos_out.max() <= 1.0
        assert sin_out.min() >= -1.0
        assert sin_out.max() <= 1.0


# ---------------------------------------------------------------------------
# RMSNorm
# ---------------------------------------------------------------------------


class TestRMSNorm:
    """Root-mean-square layer normalization."""

    def _make_norm(self, dim: int = 64):
        from ruh_model.embedding.rope import RMSNorm

        return RMSNorm(dim)

    def test_rmsnorm_output_shape(self) -> None:
        """RMSNorm preserves input shape."""
        dim = 64
        norm = self._make_norm(dim)
        x = torch.randn(2, 16, dim)

        output = norm(x)
        assert output.shape == x.shape

    def test_rmsnorm_normalized(self) -> None:
        """Output has approximately unit RMS (within tolerance)."""
        dim = 256
        norm = self._make_norm(dim)
        x = torch.randn(4, 32, dim) * 10.0  # large-scale input

        output = norm(x)

        # RMS per position should be close to 1.0 (weight is initialized to ones)
        rms = torch.sqrt(torch.mean(output * output, dim=-1))
        assert torch.allclose(rms, torch.ones_like(rms), atol=0.1), (
            f"RMS values should be near 1.0, got mean={rms.mean():.4f}"
        )

    def test_rmsnorm_zero_input(self) -> None:
        """Zero input produces finite output (no NaN/Inf from division)."""
        dim = 32
        norm = self._make_norm(dim)
        x = torch.zeros(1, 4, dim)

        output = norm(x)
        assert torch.isfinite(output).all(), "RMSNorm on zero input should be finite"

    def test_rmsnorm_gradient_flow(self) -> None:
        """Gradients flow through RMSNorm to both input and weight."""
        dim = 32
        norm = self._make_norm(dim)
        x = torch.randn(2, 8, dim, requires_grad=True)

        output = norm(x)
        loss = output.sum()
        loss.backward()

        assert x.grad is not None
        assert x.grad.abs().sum() > 0
        assert norm.weight.grad is not None
        assert norm.weight.grad.abs().sum() > 0
