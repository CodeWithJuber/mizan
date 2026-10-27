"""Run the Imtihan from the command line.

    cd backend && python -m imtihan --blocks exactness,scripture --repeats 1 --out report.json

It uses the provider configured in the environment, the same way the server does.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agents.specialized import create_agent
from security.izn import IznPermission

from . import report, runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m imtihan", description=__doc__)
    parser.add_argument("--blocks", help="comma-separated blocks (default: all)")
    parser.add_argument("--repeats", type=int, default=1, help="attempts per task (1-3)")
    parser.add_argument("--out", help="write the full result as JSON to this file")
    parser.add_argument("--list", action="store_true", help="list the blocks and exit")
    args = parser.parse_args(argv)
    if args.list:
        for entry in runner.catalog():
            print(f"{entry['block']}: {entry['tasks']} tasks")
        return 0
    agent = create_agent("khalifah", izn=IznPermission())
    if getattr(agent, "ai_client", None) is None:
        print("No language model is configured (set a provider key).", file=sys.stderr)
        return 2
    blocks = [b.strip() for b in args.blocks.split(",") if b.strip()] if args.blocks else None

    def progress(done: int, total: int, task_id: str) -> None:
        print(f"[{done}/{total}] {task_id}", file=sys.stderr, flush=True)

    result = asyncio.run(
        runner.run_suite(
            agent, owner="imtihan-cli", blocks=blocks, repeats=args.repeats, progress=progress
        )
    )
    print(report.markdown(result["report"]))
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
