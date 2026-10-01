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

    def __call__(self, batch: list[dict[str, list[int]]]) -> dict[str, Tensor]:
        if not batch:
            raise ValueError("Cannot collate an empty batch")
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
        # Only true sequence padding is ignored, not rootless legacy stopwords.
        for i, sample in enumerate(batch):
            labels[i, max(0, len(sample["root_ids"]) - 1) :] = self.pad_id

        result = {
            "root_ids": root_ids,
            "pattern_ids": pattern_ids,
            "labels": labels,
        }
        if any("paraphrase_root_ids" in sample for sample in batch):
            paired = self(
                [
                    {
                        "root_ids": s.get("paraphrase_root_ids", s["root_ids"]),
                        "pattern_ids": s.get("paraphrase_pattern_ids", s["pattern_ids"]),
                    }
                    for s in batch
                ]
            )
            result["paraphrase_root_ids"] = paired["root_ids"]
            result["paraphrase_pattern_ids"] = paired["pattern_ids"]
            result["paraphrase_mask"] = torch.tensor(
                ["paraphrase_root_ids" in s for s in batch], dtype=torch.bool
            )
        return result
