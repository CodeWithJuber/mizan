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
EVERYDAY_BAR = 0.001
REFUSE_AT = 0.95
LOO_SAMPLE = 1500
MASSIVE_LOCALES = {"en-US": "en", "hi-IN": "hi", "ur-PK": "ur", "ar-SA": "ar"}
MASSIVE_INTENTS = ("general_greet", "general_quirky")


def _key(text: str) -> str:
    """A row's identity for overlap checks: case, marks and punctuation aside."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if ch.isalnum() or unicodedata.category(ch).startswith("M"))


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
    # Tahiyya's own data (round 3) is a seed too.
    for name in ("salam.tsv", "returned.tsv", "other.tsv"):
        path = ROOT / "backend" / "tadbir" / "data" / "tahiyya" / name
        if path.exists():
            seeds |= {
                _key(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            }
    mine = {_key(text) for _l, _k, text in held_out(split)}
    clash = mine & seeds
    earlier_splits = {"test": ("dev",), "test2": ("dev", "test"), "test3": ("dev", "test", "test2")}
    for earlier in earlier_splits.get(split, ()):
        clash |= mine & {_key(text) for _l, _k, text in held_out(earlier)}
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


def _massive_rows(path: Path, partition: str):
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
                if item["partition"] == partition:
                    yield locale, str(item["intent"]), " ".join(str(item["utt"]).split())


# Qasd seeds that are a salam alone (labelled conversation before the salam rounds).
BARE_SALAM_SEEDS = {"Assalamualaikum dost", "السلام عليكم يا صديقي"}


def qasd_seeds_read_as_salam() -> dict:
    """Round 3's third bar: Qasd's own seeds (requests and conversation) read as
    a salam; the two seeds that are a salam alone are left out."""
    from tadbir import fahm, qasd

    rows = [
        (label, text)
        for label, text in seed_rows((ROOT / SEEDS).read_text(encoding="utf-8"))
        if text not in BARE_SALAM_SEEDS and label != "salam"
    ]
    fired = [
        [label, text] for label, text in rows if fahm.understand(qasd._text(text)).intent == "salam"
    ]
    return {"k": len(fired), "n": len(rows), "fired": fired}


def massive(path: Path, partition: str = "test") -> list[dict]:
    """MASSIVE greetings and small talk read as a salam (report only, no bar)."""
    from tadbir import fahm

    return [
        {"locale": locale, "intent": intent, "text": text}
        for locale, intent, text in _massive_rows(path, partition)
        if intent in MASSIVE_INTENTS and fahm.understand(text).intent == "salam"
    ]


def massive_everyday(path: Path, partition: str = "test") -> dict:
    """Round 2's fourth bar: MASSIVE's requests other than greetings (en, hi, ur,
    ar), people's own words, read as a salam: Wilson upper bound below 0.1%."""
    from tadbir import fahm

    rows = [row for row in _massive_rows(path, partition) if row[1] != "general_greet"]
    fired = [
        {"locale": locale, "intent": intent, "text": text}
        for locale, intent, text in rows
        if fahm.understand(text).intent == "salam"
    ]
    bound = _wilson(len(fired), len(rows))
    return {"k": len(fired), "n": len(rows), "wilson": bound, "fired": fired}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("dev", "test", "test2", "test3"), required=True)
    parser.add_argument("--quran", type=Path, help="a folder holding the Quran's editions")
    parser.add_argument("--massive", type=Path)
    parser.add_argument(
        "--massive-partition", default="test", help="MASSIVE split to read (dev while choosing)"
    )
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

    # Production reads the editions at startup; read them now, before any message.
    loaded = iqtibas.load() if args.quran is not None else None
    report: dict = {"split": args.split, "iqtibas": loaded is not None}
    report.update(read_split(args.split))
    if args.split == "test3":
        # Round 3 leaves Qasd unchanged: its seeds must not be read as a salam.
        report["qasd_seeds"] = qasd_seeds_read_as_salam()
    elif not args.no_seeds_check:
        report["known_seeds"] = known_seeds(args.base)
    if args.massive is not None:
        report["massive_read_as_salam"] = massive(args.massive, args.massive_partition)
        if args.split in ("test2", "test3") or args.massive_partition != "test":
            report["massive_everyday"] = massive_everyday(args.massive, args.massive_partition)
    bars = {
        "recall": report["recall"]["share"] >= RECALL_BAR,
        "no_false_fire": report["false_fires"]["k"] == 0,
    }
    if "known_seeds" in report:
        bars["known_seeds"] = report["known_seeds"]["kept"]
    if "qasd_seeds" in report:
        bars["qasd_seeds"] = report["qasd_seeds"]["k"] == 0
    if "massive_everyday" in report:
        bars["massive_everyday"] = report["massive_everyday"]["wilson"][1] < EVERYDAY_BAR
    report["bars"] = bars
    report["passed"] = all(bars.values())
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
