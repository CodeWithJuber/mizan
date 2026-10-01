"""Pinned, licensed public conversation data; no dataset loader scripts."""

from __future__ import annotations

import json
from pathlib import Path

OASST = {
    "path": "OpenAssistant/oasst1",
    "revision": "fdf72ae0827c1cda404aff25b6603abec9e3399b",
    "license": "apache-2.0",
    "files": [
        "data/train-00000-of-00001-b42a775f407cee45.parquet",
        "data/validation-00000-of-00001-134b8fd0c89408b6.parquet",
    ],
}


def conversation_pairs(rows: list[dict], languages=("ar", "en")):
    """Retain approved direct prompt/reply pairs and original thread IDs."""
    lookup = {row["message_id"]: row for row in rows}
    for row in rows:
        parent = lookup.get(row.get("parent_id"))
        if (
            row.get("role") != "assistant"
            or row.get("lang") not in languages
            or row.get("deleted")
            or row.get("review_result") is not True
            or not parent
            or parent.get("role") != "prompter"
            or parent.get("deleted")
            or parent.get("review_result") is not True
            or not row.get("text", "").strip()
            or not parent.get("text", "").strip()
        ):
            continue
        yield {
            "messages": [
                {"role": "user", "content": parent["text"]},
                {"role": "assistant", "content": row["text"]},
            ],
            "group_id": row["message_tree_id"],
            "lang": row["lang"],
            "source": OASST["path"],
        }


def prepare_dialogues(output: Path, limit: int = 2500):
    import pyarrow.parquet as parquet
    from huggingface_hub import hf_hub_download

    if limit < 1:
        raise ValueError("limit must be positive")
    rows = []
    for filename in OASST["files"]:
        file = hf_hub_download(
            OASST["path"],
            filename,
            repo_type="dataset",
            revision=OASST["revision"],
            cache_dir=str(output.parent / ".hf-cache"),
        )
        rows.extend(parquet.read_table(file).to_pylist())
    pairs = list(conversation_pairs(rows))
    # Keep the rare Arabic examples rather than allowing English order to hide them.
    pairs.sort(
        key=lambda row: (row["lang"] != "ar", row["group_id"], row["messages"][1]["content"])
    )
    selected = pairs[:limit]
    if not selected:
        raise ValueError("No approved conversation examples found")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "source": OASST,
        "records": len(selected),
        "arabic_records": sum(row["lang"] == "ar" for row in selected),
    }
