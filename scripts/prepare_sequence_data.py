#!/usr/bin/env python3
"""Prepare bounded real Arabic sentences plus reviewed Arabic/English dialogues."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ruh_model.data.chat_sources import OASST, prepare_aya, prepare_dialogues
from ruh_model.data.pipeline import DEFAULT_SOURCES, RealDataPipeline
from ruh_model.tokenizer.bayan import BayanTokenizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dialogues", type=int, default=1500)
    parser.add_argument("--sentences", type=int, default=500)
    parser.add_argument("--aya-arabic", type=int, default=0)
    parser.add_argument("--aya-english", type=int, default=0)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Choose a new preparation directory")
    args.output_dir.mkdir(parents=True)
    target = args.output_dir / "training.jsonl"
    dialogue_metadata = prepare_dialogues(target, args.dialogues)
    aya_metadata = (
        prepare_aya(target, args.aya_arabic, args.aya_english)
        if (args.aya_arabic or args.aya_english)
        else None
    )
    source = DEFAULT_SOURCES["arabic_wiki"]
    pipeline = RealDataPipeline(
        BayanTokenizer(version=2),
        max_seq_len=384,
        sources={"arabic_wiki": source},
        mixing_ratios={"arabic_wiki": 1},
    )
    sentences = 0
    with target.open("a", encoding="utf-8") as handle:
        for row in pipeline.stream(args.sentences):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            sentences += 1
    metadata = {
        "schema_version": 1,
        "conversation_source": OASST,
        "dialogues": dialogue_metadata,
        "aya": aya_metadata,
        "sentence_source": dict(
            source,
            license=["cc-by-sa-3.0", "gfdl"],
            attribution="Arabic Wikipedia contributors",
            url="https://huggingface.co/datasets/wikimedia/wikipedia",
        ),
        "sentence_records": sentences,
        "data_file": target.name,
        "privacy": "public licensed sources; no production chats or private checkpoint data",
    }
    (args.output_dir / "sources.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2)
    )
    print(json.dumps(metadata), flush=True)


if __name__ == "__main__":
    main()
