#!/usr/bin/env python3
"""Episodic encoding measured on Multi-Session Chat (docs/episodic-memory.md).

  python scripts/episodic_eval.py --msc msc_v0.1.tar.gz --split valid
  python scripts/episodic_eval.py --msc msc_v0.1.tar.gz --split test --policy novel

MSC (pinned by SHA-256 below) is read for measurement only: never trained on,
never shipped, never quoted in the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

MSC_SHA256 = "e640e37cf4317cd09fc02a4cd57ef130a185f23635f4003b0cee341ffcb45e60"
RESAMPLES = 10_000
BARS = {"p_not_better": 0.05, "recall_s": 0.8, "keep_rate": 0.6}


def _records(path: Path, name: str) -> list[dict]:
    with tarfile.open(path, "r:gz") as archive:
        member = archive.extractfile(name)
        assert member is not None
        return [json.loads(line) for line in member.read().decode("utf-8").splitlines() if line]


def conversations(path: Path, split: str, session: int = 4) -> list[dict]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MSC_SHA256:
        raise SystemExit(f"{path}: SHA-256 {digest}, not the pinned release")
    return _records(path, f"msc/msc_dialogue/session_{session}/{split}.txt")


def background(path: Path):
    """The conversation background: every turn of MSC's train split (sessions 2
    and 3), which no measured conversation is part of."""
    from memory.episodic import Background

    turns = []
    for session in ("session_2", "session_3"):
        for record in _records(path, f"msc/msc_dialogue/{session}/train.txt"):
            turns += [turn["text"] for turn in record["dialog"]]
    return Background.of(turns)


def units(record: dict) -> list[dict]:
    """One per speaker: their statements in sessions 1-3 with the facts written
    for them after each session, and every turn of session 4."""
    later = [turn["text"] for turn in record["dialog"]]
    found = []
    for speaker in (0, 1):
        statements: list[tuple[str, list[str]]] = []
        for session in record["previous_dialogs"]:
            facts = list((session.get("personas") or [[], []])[speaker])
            turns = [turn["text"] for turn in session["dialog"]]
            statements += [
                (text, facts) for index, text in enumerate(turns) if index % 2 == speaker
            ]
        found.append({"statements": statements, "later": later})
    return found


def labelled(unit: dict) -> tuple[list[bool], list[bool]]:
    from tadbir.ahl_dhikr import about

    worth = [any(about(fact, text) for fact in facts) for text, facts in unit["statements"]]
    needed = [any(about(text, turn) for turn in unit["later"]) for text, _ in unit["statements"]]
    return worth, needed


def counts(kept: list[bool], truth: list[bool]) -> tuple[int, int, int]:
    hits = sum(k and t for k, t in zip(kept, truth, strict=True))
    return hits, sum(kept), sum(truth)


def score(rows: list[dict]) -> dict:
    """Micro precision, recall and F1 for S and N, the keep rate, and N's
    prevalence (the precision of keeping at random at the same rate)."""
    out: dict = {}
    total = sum(len(r["kept"]) for r in rows)
    kept = sum(sum(r["kept"]) for r in rows)
    out["statements"] = total
    out["keep_rate"] = round(kept / max(1, total), 4)
    for name in ("worth", "needed"):
        hits = sum(counts(r["kept"], r[name])[0] for r in rows)
        truth = sum(sum(r[name]) for r in rows)
        precision = hits / max(1, kept)
        recall = hits / max(1, truth)
        out[name] = {
            "prevalence": round(truth / max(1, total), 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(2 * precision * recall / max(1e-12, precision + recall), 4),
        }
    return out


def bootstrap(rows: list[dict], seed: int = 0) -> float:
    """P(not better): the share of resamples (over conversations) where N's
    precision is not above N's prevalence."""
    by_conversation: dict[int, list[dict]] = {}
    for row in rows:
        by_conversation.setdefault(row["conversation"], []).append(row)
    groups = list(by_conversation.values())
    rng = random.Random(seed)
    worse = 0
    for _ in range(RESAMPLES):
        hits = kept = truth = total = 0
        for group in rng.choices(groups, k=len(groups)):
            for row in group:
                h, k, t = counts(row["kept"], row["needed"])
                hits, kept, truth, total = hits + h, kept + k, truth + t, total + len(row["kept"])
        if kept == 0 or hits / kept <= truth / max(1, total):
            worse += 1
    return worse / RESAMPLES


def run(path: Path, split: str, policies: list[str], session: int = 4) -> dict:
    from memory.episodic import came_up_again, keep

    records = conversations(path, split, session)
    known = background(path)
    prepared = []
    for index, record in enumerate(records):
        for unit in units(record):
            worth, needed = labelled(unit)
            prepared.append((index, unit, worth, needed))
    report: dict = {
        "split": split,
        "session": session,
        "conversations": len(records),
        "background_turns": known.turns,
    }
    for policy in policies:
        began = time.monotonic()
        rows = []
        for index, unit, worth, needed in prepared:
            texts = [text for text, _ in unit["statements"]]
            if policy == "repeated":
                kept = came_up_again(texts, unit["after"])
            else:
                kept = keep(texts, policy, known)
            rows.append({"conversation": index, "kept": kept, "worth": worth, "needed": needed})
        seconds = time.monotonic() - began
        entry = score(rows)
        entry["seconds_per_statement"] = round(seconds / max(1, entry["statements"]), 5)
        if split == "test" or session == 5:
            entry["p_not_better"] = bootstrap(rows)
            entry["bars"] = {
                "needed_better_than_chance": entry["p_not_better"] < BARS["p_not_better"],
                "keeps_less": entry["keep_rate"] <= BARS["keep_rate"],
            }
            if session == 4:  # test 1 also asked to keep most of what people summarised
                entry["bars"]["recall_worth"] = entry["worth"]["recall"] >= BARS["recall_s"]
            entry["passed"] = all(entry["bars"].values())
        report[policy] = entry
        print(policy, json.dumps(entry), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--msc", type=Path, required=True)
    parser.add_argument("--split", choices=("valid", "test"), required=True)
    parser.add_argument("--policy", choices=("informative", "novel", "repeated"))
    parser.add_argument("--session", type=int, choices=(4, 5), default=4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.session == 5:
        # test 2: one rule, fixed beforehand, read once on each split of session 5
        policies = ["all", "repeated"]
    elif args.split == "test" and not args.policy:
        raise SystemExit("the test split is read once, with the policy chosen on valid")
    else:
        policies = ["all", args.policy] if args.split == "test" else ["all", "informative", "novel"]
    report = run(args.msc, args.split, policies, args.session)
    text = json.dumps(report, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
