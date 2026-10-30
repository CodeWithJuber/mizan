"""Batch collator for Ruh model training.

Pads variable-length ``(root_id, pattern_id)`` sequences and builds
next-token labels for causal LM training: ``labels[t] = root_ids[t+1]``,
with ``pad_id`` marking ignored positions (the loss uses
``ignore_index=pad_id``).

Scripture is never a target. A sample may carry ``scripture_mask``, one bool
per token, True for a token inside a scripture span (an ayah, a translation of
one, a hadith) that its record declared (``ruh_model.data.scripture``;
``sequence.tokenize_record`` builds it from the record's ``scripture`` strings).
A label is ignored whenever the token it predicts is marked, whatever
``target_mask`` says, so no supervised label ever falls inside a span. Spans a
record does not declare are not known here.
"""

from __future__ import annotations

import torch
from torch import Tensor


class RuhCollator:
    """Pad + label collator for :class:`RuhDataset` samples.

    Args:
        pad_id: ID used for padding and ignored label positions
            (``config.PAD_ROOT``, typically 0).

    Samples may carry ``target_mask`` (False: do not supervise the token) and
    ``scripture_mask`` (True: a scripture token, never supervised); both are
    per token and describe the token being predicted.
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
            if "target_mask" in sample:
                mask = sample["target_mask"]
                if len(mask) != len(sample["root_ids"]):
                    raise ValueError("target_mask must match the token sequence length")
                # A mask describes the token being predicted, so shift it with labels.
                for position, supervised in enumerate(mask[1:]):
                    if not supervised:
                        labels[i, position] = self.pad_id
            if "scripture_mask" in sample:
                protected = sample["scripture_mask"]
                if len(protected) != len(sample["root_ids"]):
                    raise ValueError("scripture_mask must match the token sequence length")
                # Never supervise a scripture token, whatever target_mask says.
                for position, inside in enumerate(protected[1:]):
                    if inside:
                        labels[i, position] = self.pad_id

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
