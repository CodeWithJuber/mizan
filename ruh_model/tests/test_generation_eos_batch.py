"""Batch rows must terminate independently without resurrecting finished rows."""

import torch

from ruh_model.config import RuhConfig
from ruh_model.model import RuhModel


def test_staggered_eos_stops_finished_row_and_batch(monkeypatch):
    config = RuhConfig(d_model=32, n_heads=4, n_layers=1, n_roots=32, n_patterns=8)
    model = RuhModel(config)
    # Row 0 finishes at step 1; row 1 at step 3. The old all(next==EOS)
    # condition never stopped and allowed row 0 to resume with 7, 8, ... .
    samples = iter([[[2], [4]], [[7], [5]], [[8], [2]]])
    monkeypatch.setattr(model, "_sample_next_token", lambda *a: torch.tensor(next(samples)))
    generated = model.generate(torch.tensor([[1], [1]]), torch.zeros(2, 1, dtype=torch.long),
                               max_new_tokens=10, valid_n_roots=32)
    assert generated.tolist() == [[1, 2, 2, 2], [1, 4, 5, 2]]
