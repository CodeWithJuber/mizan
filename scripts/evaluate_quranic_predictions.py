#!/usr/bin/env python3
"""Score held-out Quranic predictions, keeping Arabic text and citations exact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ruh_model.data.quranic_evaluation import summarize_scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()]
    args.output.write_text(json.dumps(summarize_scores(rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
