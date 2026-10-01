#!/usr/bin/env python3
"""Prepare all 114 surahs into three pinned, attributed Quranic training paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ruh_model.data.quranic import prepare_quranic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare_quranic(args.cache, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "coverage": manifest["coverage"],
                "paths": manifest["paths"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
