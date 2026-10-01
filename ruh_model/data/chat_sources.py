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
AYA = {
    "path": "CohereForAI/aya_dataset",
    "revision": "f9ea04583f02a8f86404ff6c58bf75fe637df8a2",
    "license": "apache-2.0",
    "files": ["data/train-00000-of-00001.parquet"],
    "description": "Human multilingual instructions and answers, no annotation user IDs retained",
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


def prepare_aya(output: Path, arabic_limit: int, english_limit: int):
    import hashlib

    import pyarrow.parquet as parquet
    from huggingface_hub import hf_hub_download

    if arabic_limit < 0 or english_limit < 0:
        raise ValueError("Aya limits must be nonnegative")
    limits, counts = {"arb": arabic_limit, "eng": english_limit}, {"arb": 0, "eng": 0}
    file = hf_hub_download(
        AYA["path"],
        AYA["files"][0],
        repo_type="dataset",
        revision=AYA["revision"],
        cache_dir=str(output.parent / ".hf-cache"),
    )
    reader = parquet.ParquetFile(file)
    try:
        with output.open("a", encoding="utf-8") as handle:
            for batch in reader.iter_batches(
                batch_size=512,
                columns=["inputs", "targets", "language_code", "annotation_type"],
                use_threads=False,
            ):
                for row in batch.to_pylist():
                    language = row["language_code"]
                    if language not in limits or counts[language] >= limits[language]:
                        continue
                    prompt, answer = row["inputs"], row["targets"]
                    if not prompt.strip() or not answer.strip():
                        continue
                    example = {
                        "messages": [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": answer},
                        ],
                        "group_id": hashlib.sha256(prompt.encode()).hexdigest(),
                        "lang": "ar" if language == "arb" else "en",
                        "source": AYA["path"],
                        "annotation_type": row["annotation_type"],
                    }
                    handle.write(json.dumps(example, ensure_ascii=False) + "\n")
                    counts[language] += 1
                if counts == limits:
                    break
    finally:
        reader.close()
    if any(counts[lang] == 0 for lang, limit in limits.items() if limit > 0):
        raise ValueError("Aya did not provide the requested language")
    return {"source": AYA, "records_by_language": counts, "requested_limits": limits}
