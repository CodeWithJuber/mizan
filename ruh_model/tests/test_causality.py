"""Prefix-invariance tests for Ruh Model causality.

If the model is truly causal, the output at position i must be identical
whether the input is the full sequence or just the prefix ending at i.
Any difference means future tokens leaked into the past (via attention,
the complexity statistic, or any other sequence-wide operation).
"""

from __future__ import annotations

import torch

from ruh_model.config import RuhConfig
from ruh_model.model import RuhModel


def _tiny_model() -> RuhModel:
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=4,
        n_roots=50,
        n_patterns=10,
        n_layers=2,
        n_heads=2,
        max_seq_len=32,
        dropout=0.0,
    )
    model = RuhModel(config)
    model.eval()
    return model


def test_prefix_invariance_logits():
    """Logits at position i are unchanged when tokens after i are appended."""
    torch.manual_seed(0)
    model = _tiny_model()
    seq_len, prefix_len = 12, 7

    root_ids = torch.randint(0, 50, (2, seq_len))
    pattern_ids = torch.randint(0, 10, (2, seq_len))

    with torch.no_grad():
        full = model(root_ids, pattern_ids)["logits"]
        prefix = model(root_ids[:, :prefix_len], pattern_ids[:, :prefix_len])[
            "logits"
        ]

    # Position prefix_len - 1 is the last position of the prefix run;
    # it must match the same position of the full run exactly.
    assert torch.allclose(
        full[:, prefix_len - 1, :], prefix[:, prefix_len - 1, :], atol=1e-5
    ), "Future tokens leaked into prefix positions"


def test_prefix_invariance_all_positions():
    """Every prefix position matches between full and truncated runs."""
    torch.manual_seed(1)
    model = _tiny_model()
    seq_len = 10

    root_ids = torch.randint(0, 50, (1, seq_len))
    pattern_ids = torch.randint(0, 10, (1, seq_len))

    with torch.no_grad():
        full = model(root_ids, pattern_ids)["logits"]
        for k in (3, 6, 9):
            prefix = model(root_ids[:, :k], pattern_ids[:, :k])["logits"]
            assert torch.allclose(
                full[:, k - 1, :], prefix[:, k - 1, :], atol=1e-5
            ), f"Leak detected at prefix length {k}"
