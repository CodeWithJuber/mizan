"""Batch collator for Ruh model training.

Pads variable-length ``(root_id, pattern_id)`` sequences and builds
next-token labels for causal LM training: ``labels[t] = root_ids[t+1]``,
with ``pad_id`` marking ignored positions (the loss uses
``ignore_index=pad_id``).
"""

from __future__ import annotations

import torch
from torch import Tensor


class RuhCollator:
    """Pad + label collator for :class:`RuhDataset` samples.

    Args:
        pad_id: ID used for padding and ignored label positions
            (``config.PAD_ROOT``, typically 0).
    """

    def __init__(self, pad_id: int = 0) -> None:
        self.pad_id = pad_id

    def __call__(
        self, batch: list[dict[str, list[int]]]
    ) -> dict[str, Tensor]:
        max_len = max(len(s["root_ids"]) for s in batch)

        root_ids = torch.full((len(batch), max_len), self.pad_id, dtype=torch.long)
        pattern_ids = torch.zeros((len(batch), max_len), dtype=torch.long)
        for i, sample in enumerate(batch):
            n = len(sample["root_ids"])
            root_ids[i, :n] = torch.tensor(sample["root_ids"], dtype=torch.long)
            pattern_ids[i, :n] = torch.tensor(sample["pattern_ids"], dtype=torch.long)

        # Next-token labels: labels[t] predicts root_ids[t+1]; the final
        # position and all padding positions are ignored via pad_id.
        labels = torch.full((len(batch), max_len), self.pad_id, dtype=torch.long)
        labels[:, :-1] = root_ids[:, 1:]
        # Positions that were padding in the input stay ignored.
        labels[root_ids == self.pad_id] = self.pad_id

        return {
            "root_ids": root_ids,
            "pattern_ids": pattern_ids,
            "labels": labels,
        }
