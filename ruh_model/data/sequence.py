"""Lossless sentence windows and assistant targets for Bayan v2 training."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.conversation import serialize_messages


def record_id(row: dict) -> str:
    """Keep all examples/windows of a source conversation in the same split."""
    text = (
        serialize_messages(row["messages"], assistant_prefix=False)
        if row.get("messages")
        else row["text"]
    )
    return str(row.get("group_id") or hashlib.sha256(text.encode()).hexdigest())


def split_records(rows: Iterable[dict], validation_fraction: float = 0.1, seed: int = 42):
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between zero and one")
    train, validation, seen = [], [], set()
    rows = list(rows)
    parents = {}

    def find(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]

    # Connect source thread IDs across repeated prompts, including different
    # licensed corpora. Alternative answers to the same question never leak.
    for row in rows:
        group = "group:" + record_id(row)
        find(group)
        for message in row.get("messages", []):
            if message["role"] == "user":
                normalized = " ".join(message["content"].casefold().split())
                prompt = "prompt:" + hashlib.sha256(normalized.encode()).hexdigest()
                a, b = find(group), find(prompt)
                parents[max(a, b)] = min(a, b)
    for row in rows:
        identity = record_id(row)
        content = (
            serialize_messages(row["messages"], assistant_prefix=False)
            if row.get("messages")
            else row["text"]
        )
        content_id = hashlib.sha256(content.encode()).hexdigest()
        if content_id in seen:
            continue
        seen.add(content_id)
        component = find("group:" + identity)
        bucket = int(hashlib.sha256(f"{seed}:{component}".encode()).hexdigest()[:16], 16) / 2**64
        (validation if bucket < validation_fraction else train).append(row)
    if not train or not validation:
        raise ValueError("Both training and validation need examples; increase the source limit")
    return train, validation


def tokenize_record(row: dict, tokenizer: BayanTokenizer, max_seq_len: int):
    """Window every byte; supervise only assistant content in conversation rows.

    No manufactured EOS is added at truncation boundaries. Each continuation
    window overlaps one token so the transition is trained exactly once.
    """
    if tokenizer.version != 2:
        raise ValueError("Sequence training requires lossless Bayan v2, not legacy root IDs")
    if max_seq_len < 2:
        raise ValueError("max_seq_len must allow a next-token target")
    messages = row.get("messages")
    if messages:
        parts, byte_mask = [], []
        for index, message in enumerate(messages):
            if index:
                parts.append("\n")
                byte_mask.append(False)
            role = message["role"]
            if role not in {"system", "user", "assistant", "tool"}:
                raise ValueError("Unsupported message role")
            prefix, content = f"{role}:", message["content"]
            if not isinstance(content, str):
                raise ValueError("Training conversation content must be plain text")
            # Inference ends at "assistant:". Its first continuation is the
            # separating space, which therefore needs an assistant target.
            content = " " + content
            parts.extend([prefix, content])
            byte_mask.extend([False] * len(prefix.encode()))
            byte_mask.extend([role == "assistant"] * len(content.encode()))
        text = "".join(parts)
        target_mask = [False, *byte_mask, messages[-1]["role"] == "assistant"]
    else:
        text = row["text"]
        target_mask = [False] + [True] * (len(text.encode()) + 1)
    tokens = tokenizer.encode(text)
    for start in range(0, len(tokens) - 1, max_seq_len - 1):
        window = tokens[start : start + max_seq_len]
        mask = target_mask[start : start + max_seq_len]
        if any(mask[1:]):
            yield {
                "root_ids": [root for root, _ in window],
                "pattern_ids": [pattern for _, pattern in window],
                "target_mask": mask,
            }
