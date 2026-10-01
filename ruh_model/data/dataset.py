"""PyTorch dataset for Ruh model training.

Reads JSONL files (one ``{"text": ...}`` object per line) and tokenizes
each text into ``(root_id, pattern_id)`` sequences via :class:`BayanTokenizer`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from torch.utils.data import Dataset

from ruh_model.tokenizer.bayan import BayanTokenizer


class RuhDataset(Dataset):  # type: ignore[type-arg]
    """Tokenized dataset for causal language-model training.

    Args:
        data_path: JSONL file or directory of JSONL files with ``{"text"}`` rows.
        tokenizer: BayanTokenizer instance.
        max_seq_len: Truncate token sequences to this length.
        config: RuhConfig (accepted for API compatibility; currently unused
            beyond documentation).
    """

    def __init__(
        self,
        data_path: str,
        tokenizer: BayanTokenizer,
        max_seq_len: int,
        config: Any = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len

        files = self._collect_files(data_path)
        self._samples: list[dict[str, list[int]]] = []
        for file in files:
            for line in file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = row.get("text", "")
                if row.get("messages"):
                    from ruh_model.tokenizer.conversation import serialize_messages

                    text = serialize_messages(row["messages"], assistant_prefix=False)
                if not text or not text.strip():
                    continue
                tokens = tokenizer.encode(text)[:max_seq_len]
                if len(tokens) < 2:
                    continue
                root_ids = [r for r, _ in tokens]
                pattern_ids = [p for _, p in tokens]
                sample = {"root_ids": root_ids, "pattern_ids": pattern_ids}
                if row.get("paraphrase"):
                    paired = tokenizer.encode(row["paraphrase"])[:max_seq_len]
                    sample["paraphrase_root_ids"] = [r for r, _ in paired]
                    sample["paraphrase_pattern_ids"] = [p for _, p in paired]
                self._samples.append(sample)

    @staticmethod
    def _collect_files(data_path: str) -> list[Path]:
        path = Path(data_path)
        if path.is_dir():
            return sorted(path.glob("*.jsonl"))
        return [path]

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, idx: int) -> dict[str, list[int]]:
        return self._samples[idx]
