#!/usr/bin/env python3
"""The salam recipe, measured (docs/fahm.md, "Salam (4:86)"; pre-registered).

A message that is a salam and nothing else ("Assalamualaikum", "AoA bhai",
"السلام علیکم ورحمۃ اللہ") is answered by MIZAN with the fuller reply and no
model call (4:86). This measures, through ``fahm.understand`` as production
runs it (MIZAN orchestration, Iqtibas on when the Quran's editions are there):

1. recall: the share of held-out salam-only messages read as ``salam``
   (bar: at least 90%);
2. false fires: held-out messages that are not a salam alone (a salam with a
   request or question, a returned salam, other greetings, questions about
   the salam) read as ``salam`` (bar: none);
3. the known seeds: exact leave-one-out on Qasd's earlier seeds before and
   after (rows whose label changed are left out), refused when the paired
   bootstrap gives P(worse) >= 0.95 (Ta'lim's gate, ``talim.p_worse``).

The dev split may be read many times while the seeds are chosen; the test
split is read once and its result written as it comes. MASSIVE 1.1's
general_greet/general_quirky test rows (en, hi, ur, ar; CC BY 4.0) are
reported for a look by hand, with no bar: a translator may have written a
salam for "hello".

  python scripts/salam_eval.py --split dev  --quran DIR            # choose seeds
  python scripts/salam_eval.py --split test --quran DIR --massive amazon-massive-dataset-1.1.tar.gz
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "scripts" / "data" / "salam"
SEEDS = "backend/tadbir/data/qasd/intents.tsv"
# The commit the seeds are compared against: main before the salam round.
BASE = "7be4f475937b910b1528fc695717f7e8278eeeef"
RECALL_BAR = 0.90
REFUSE_AT = 0.95
LOO_SAMPLE = 1500
MASSIVE_LOCALES = {"en-US": "en", "hi-IN": "hi", "ur-PK": "ur", "ar-SA": "ar"}
MASSIVE_INTENTS = ("general_greet", "general_quirky")


def _key(text: str) -> str:
    """A row's identity for overlap checks: case, marks and punctuation aside."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def held_out(split: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in (DATA / f"{split}.tsv").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            label, kind, text = line.split("\t")
            rows.append((label, kind, text))
    return rows


def seed_rows(text: str) -> list[tuple[str, str]]:
    return [
        tuple(line.split("\t")[:2])  # type: ignore[misc]
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def check_overlap(split: str) -> None:
    """No held-out row may be a seed, and test shares no row with dev."""
    seeds = {_key(text) for _label, text in seed_rows((ROOT / SEEDS).read_text(encoding="utf-8"))}
    mine = {_key(text) for _l, _k, text in held_out(split)}
    clash = mine & seeds
    if split == "test":
        clash |= mine & {_key(text) for _l, _k, text in held_out("dev")}
    if clash:
        raise SystemExit(f"{split} rows also in the seeds or dev: {sorted(clash)[:10]}")


def script_of(text: str) -> str:
    for ch in text:
        if "؀" <= ch <= "ۿ":
            return "arabic"
        if "ऀ" <= ch <= "ॿ":
            return "devanagari"
    return "latin"


def _wilson(k: int, n: int) -> list[float]:
    from core.adaptive import wilson_bounds

    low, high = wilson_bounds(k, n)
    return [round(low, 4), round(high, 4)]


def read_split(split: str) -> dict:
    from tadbir import fahm

    rows = held_out(split)
    outcome: dict = {"positives": {}, "negatives": {}, "missed": [], "fired": []}
    for label, kind, text in rows:
        said = fahm.understand(text).intent
        side = "positives" if label == "salam" else "negatives"
        bucket = outcome[side].setdefault(f"{kind}/{script_of(text)}", [0, 0])
        bucket[1] += 1
        if (said == "salam") == (label == "salam"):
            bucket[0] += label == "salam"
        if label == "salam" and said != "salam":
            outcome["missed"].append([text, said])
        if label != "salam" and said == "salam":
            outcome["fired"].append([text, kind])
    positives = sum(1 for row in rows if row[0] == "salam")
    negatives = len(rows) - positives
    found = positives - len(outcome["missed"])
    fired = len(outcome["fired"])
    outcome["recall"] = {"k": found, "n": positives, "share": round(found / positives, 4)}
    outcome["recall"]["wilson"] = _wilson(found, positives)
    outcome["false_fires"] = {"k": fired, "n": negatives, "wilson": _wilson(fired, negatives)}
    return outcome


def known_seeds(base: str = BASE) -> dict:
    """Exact leave-one-out on the earlier seeds, before and after (Ta'lim's gate)."""
    from core.tamyiz import Tamyiz
    from tadbir import qasd, talim

    old_text = subprocess.run(
        ["git", "show", f"{base}:{SEEDS}"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    old_rows = seed_rows(old_text)
    new_rows = seed_rows((ROOT / SEEDS).read_text(encoding="utf-8"))
    new_label: dict[str, set[str]] = {}
    for label, text in new_rows:
        new_label.setdefault(text, set()).add(label)
    pairs = [(text, label) for label, text in old_rows]
    old = qasd.shaped(pairs, "seed")
    # The seed row each shaped example came from (shaped counts a row twice,
    # with and without a selected project, unless it works on the project).
    sources = [
        raw
        for raw, label in pairs
        for _ in range(
            2 if label not in qasd.PROJECT_INTENTS and not raw.startswith("[project] ") else 1
        )
    ]
    assert len(sources) == len(old)
    new = qasd.examples()
    old_model = Tamyiz(qasd._features).fit(old)
    new_model = Tamyiz(qasd._features).fit(new)
    step = max(1, math.ceil(len(old) / LOO_SAMPLE))
    by_text: dict[tuple[str, str], tuple[str, ...]] = {(row[0], row[1]): row for row in new}
    before_rows, after_rows, relabelled = [], [], 0
    for index in range(0, len(old), step):
        row, source = old[index], sources[index]
        if row[1] not in new_label.get(source, {row[1]}):
            relabelled += 1
            continue
        match = by_text.get((row[0], row[1]))
        if match is None:
            continue
        before_rows.append(row)
        after_rows.append(match)
    before = old_model.held_out_correct(before_rows)
    after = new_model.held_out_correct(after_rows)
    risk = talim.p_worse(before, after)
    return {
        "scored": len(before),
        "left_out_relabelled": relabelled,
        "before": round(sum(before) / max(1, len(before)), 4),
        "after": round(sum(after) / max(1, len(after)), 4),
        "p_worse": round(risk, 4),
        "kept": risk < REFUSE_AT,
        "loo_accuracy": {"before": old_model.loo_accuracy, "after": new_model.loo_accuracy},
    }


def massive(path: Path) -> list[dict]:
    """MASSIVE greetings and small talk read as a salam (report only, no bar)."""
    from tadbir import fahm

    found = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            locale = Path(member.name).stem
            if not member.isfile() or locale not in MASSIVE_LOCALES:
                continue
            if not member.name.endswith(".jsonl"):
                continue
            handle = archive.extractfile(member)
            assert handle is not None
            for row in io.TextIOWrapper(handle, encoding="utf-8"):
                item = json.loads(row)
                if item["partition"] != "test" or item["intent"] not in MASSIVE_INTENTS:
                    continue
                text = " ".join(str(item["utt"]).split())
                if fahm.understand(text).intent == "salam":
                    found.append({"locale": locale, "intent": item["intent"], "text": text})
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--quran", type=Path, help="a folder holding the Quran's editions")
    parser.add_argument("--massive", type=Path)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--no-seeds-check", action="store_true", help="skip the slow LOO bar")
    args = parser.parse_args()

    check_overlap(args.split)
    home = Path(tempfile.mkdtemp(prefix="salam_eval_"))
    if args.quran is not None:
        (home / "quran").symlink_to(args.quran.resolve())
    os.environ.update(
        {
            "MIZAN_DATA_DIR": str(home),
            "MIZAN_ORCHESTRATION": "mizan",
            "MIZAN_TALIM": "off",
            "MIZAN_IQTIBAS": "on" if args.quran is not None else "off",
        }
    )
    sys.path.insert(0, str(ROOT / "backend"))
    from tadbir import iqtibas

    report: dict = {"split": args.split, "iqtibas": bool(args.quran and iqtibas.ready())}
    report.update(read_split(args.split))
    if not args.no_seeds_check:
        report["known_seeds"] = known_seeds(args.base)
    if args.massive is not None:
        report["massive_read_as_salam"] = massive(args.massive)
    bars = {
        "recall": report["recall"]["share"] >= RECALL_BAR,
        "no_false_fire": report["false_fires"]["k"] == 0,
    }
    if "known_seeds" in report:
        bars["known_seeds"] = report["known_seeds"]["kept"]
    report["bars"] = bars
    report["passed"] = all(bars.values())
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
