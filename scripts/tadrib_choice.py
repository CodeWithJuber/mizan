#!/usr/bin/env python3
"""Tadrib phase 2b: can MIZAN choose the action itself, when it is sure?
(docs/tadrib.md, "Phase 2b").

  --lessons WORK --before PREV   ask the teacher (Lisan.plan_steps) for fresh
                                 MASSIVE utterances no earlier stream used
                                 -> WORK/lessons.jsonl (spending capped)
  --run WORK --before PREV       MIZAN's reading (tadrib.choice) learns the
                                 earlier lessons, then reads each fresh one
                                 before learning it -> WORK/choice.json

PREV is phase 2's folder (its lessons.jsonl and again.jsonl). OPENROUTER_API_KEY
must be set for --lessons.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

FRESH_PER_LANGUAGE = 1500  # fresh lessons asked per language (about $1.2 in all)
FAST = 0.2  # seconds: reading and learning one message, at the 95th percentile
PROVEN = 40.0  # e >= 1/α with α = 0.05 split between phase 2 and 2b (Bonferroni)
LANGUAGES = ("en", "hi", "ur")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def teacher_bar(before: Path) -> dict[str, float]:
    """p0 per language: how often the teacher, asked twice, chose the same action."""
    from tadbir.tadrib.choice import action_of

    first = {row["source"]: row for row in _rows(before / "lessons.jsonl")}
    tally = {language: [0, 0] for language in LANGUAGES}
    for row in _rows(before / "again.jsonl"):
        if "target" not in row or row["source"] not in first:
            continue
        earlier = action_of(first[row["source"]].get("target"))
        tally[row["language"]][0] += 1
        tally[row["language"]][1] += earlier is not None and earlier == action_of(row.get("target"))
    return {language: hits / max(1, n) for language, (n, hits) in tally.items()}


def run(work: Path, before: Path) -> dict:
    from core.adaptive import BettingEProcess
    from tadbir.tadrib import plans
    from tadbir.tadrib.choice import SURE, Choice, action_of

    def lessons(path: Path) -> list[dict]:
        # never a message about the deen, as MIZAN reads it now (the facet
        # changed after phase 2's lessons were collected)
        return [
            row
            for row in _rows(path)
            if action_of(row.get("target")) and not plans.about_the_deen(row["text"])
        ]

    earlier = lessons(before / "lessons.jsonl")
    fresh = lessons(work / "lessons.jsonl")
    p0 = teacher_bar(before)
    choice = Choice((row["text"], action_of(row["target"])) for row in earlier)
    tests = {language: BettingEProcess(p0[language]) for language in LANGUAGES}
    proven: dict[str, int | None] = {language: None for language in LANGUAGES}
    seen = {
        language: {"n": 0, "answered": 0, "agreed": 0, "agreed_all": 0} for language in LANGUAGES
    }
    rows = []
    seconds: list[float] = []
    for index, row in enumerate(fresh):
        language = row["language"]
        taught = action_of(row["target"])
        started = time.perf_counter()
        action, probability = choice.read(row["text"])
        answered = action is not None and probability >= SURE
        agreed = action == taught
        part = seen[language]
        part["n"] += 1
        part["agreed_all"] += agreed
        if answered:
            part["answered"] += 1
            part["agreed"] += agreed
            tests[language].update(1.0 if agreed else 0.0)
            if proven[language] is None and tests[language].value >= PROVEN:
                proven[language] = index
        choice.learn(row["text"], taught)
        seconds.append(time.perf_counter() - started)
        rows.append(
            {
                "language": language,
                "taught": taught,
                "read": action,
                "probability": round(probability, 4),
                "answered": answered,
                "agreed": agreed,
            }
        )
    (work / "choice.rows.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    seconds.sort()
    p95 = seconds[min(len(seconds) - 1, int(0.95 * len(seconds)))] if seconds else 0.0
    report = {
        "sure": SURE,
        "proven_at_e": PROVEN,
        "seconds_p95": round(p95, 4),
        "fast_enough": p95 <= FAST,
        "earlier_lessons": len(earlier),
        "fresh_lessons": len(fresh),
        "p0": {language: round(value, 4) for language, value in p0.items()},
        "by_language": {
            language: {
                "n": part["n"],
                "answered": part["answered"],
                "coverage": round(part["answered"] / max(1, part["n"]), 4),
                "agreement_answered": round(part["agreed"] / max(1, part["answered"]), 4),
                "answered_wrongly": part["answered"] - part["agreed"],
                "agreement_all": round(part["agreed_all"] / max(1, part["n"]), 4),
                "e": round(tests[language].value, 3),
                "proven": proven[language] is not None,
                "proven_at": proven[language],
            }
            for language, part in seen.items()
        },
    }
    (work / "choice.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> None:
    import tadrib_lisan

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lessons", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--massive", type=Path)
    parser.add_argument("--model", default="deepseek/deepseek-chat-v3-0324")
    args = parser.parse_args()
    if args.lessons:
        used = frozenset(row["source"] for row in _rows(args.before / "lessons.jsonl"))
        found = tadrib_lisan.collect(
            args.lessons,
            args.massive,
            args.model,
            skip=used,
            per_language=FRESH_PER_LANGUAGE,
        )
        print(json.dumps(found, indent=1))
    elif args.run:
        print(json.dumps(run(args.run, args.before), indent=1))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
