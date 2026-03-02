"""Shared fixtures for Ruh Model Phase 1 tests."""

from __future__ import annotations

import pytest

from ruh_model.config import RuhConfig
from ruh_model.tokenizer.root_vocab import build_default_vocab, RootVocab


@pytest.fixture
def sample_config() -> RuhConfig:
    """Small-dimension config for fast tests."""
    return RuhConfig(
        d_model=64,
        d_root=16,
        d_pattern=8,
        n_roots=100,
        n_patterns=20,
        n_layers=2,
        n_heads=4,
        max_seq_len=128,
        dropout=0.0,  # deterministic during tests
    )


@pytest.fixture
def default_vocab() -> RootVocab:
    """Full default vocabulary built from project roots."""
    return build_default_vocab()
