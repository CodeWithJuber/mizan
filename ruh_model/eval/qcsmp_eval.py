"""Q-CSMP eval runner: accuracy + macro-F1 over sense-disambiguation records (beta).

HONEST NOTE (read first): the Q-CSMP v2 pilot's own headline result is NEGATIVE
for root-space features — Δ_Q = −0.0555 (surface statistics beat
root/pattern/morph features at pilot scale; pilot acc 0.7592, macro-F1 0.5471
vs majority baseline 0.6156/0.2925). This benchmark exists to define exactly
what the adjudicated labels must test: do root-space features win once labels
are trustworthy (κ ≥ 0.61 adjudication pending) and models are non-linear?
Lead with the negative result; do not bury it.

Record format (Zenodo-style JSONL, one per line):
  {"id": ..., "lemma": "كتب", "context": "...", "sense_id": "qcsmp2:كتب:write"}

``predict_fn`` maps a record -> predicted ``sense_id``. No trained Ruh
checkpoint is wired in here yet — pass any predictor (including the
majority-sense baseline below). Dataset not bundled: fetch Q-CSMP v2 from
Zenodo DOI 10.5281/zenodo.23024527.

Status: beta / unverified. Torch-free, stdlib-only.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

QCSMP_DOI = "10.5281/zenodo.23024527"
QCSMP_POINTER = (
    "Q-CSMP v2 is not bundled in this repo. Download the pilot JSONL from "
    f"Zenodo DOI {QCSMP_DOI} (CC-BY-4.0) and point --gold at it."
)

# Pilot headline numbers, quoted from the dataset card — the bar to beat.
PILOT_SURFACE_ACC = 0.7592
PILOT_SURFACE_MACRO_F1 = 0.5471
PILOT_MAJORITY_ACC = 0.6156
PILOT_MAJORITY_MACRO_F1 = 0.2925
PILOT_DELTA_Q = -0.0555  # surface stats beat root/pattern/morph at pilot scale


# ---------------------------------------------------------------------------
# Gold data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SenseRecord:
    id: str
    lemma: str
    context: str
    sense_id: str


def load_qcsmp_jsonl(path: str | Path) -> list[SenseRecord]:
    """Load Zenodo-format Q-CSMP JSONL records."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Q-CSMP data not found: {path}\n{QCSMP_POINTER}")
    records: list[SenseRecord] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            rec = json.loads(line)
            try:
                records.append(
                    SenseRecord(
                        id=str(rec["id"]),
                        lemma=rec["lemma"],
                        context=rec["context"],
                        sense_id=rec["sense_id"],
                    )
                )
            except KeyError as exc:
                raise ValueError(f"{path}:{lineno}: missing key {exc}") from exc
    if not records:
        raise ValueError(f"{path}: no records found")
    return records


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def accuracy(predicted: list[str], gold: list[str]) -> float:
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold lengths differ")
    return sum(p == g for p, g in zip(predicted, gold, strict=True)) / len(gold) if gold else 0.0


def macro_f1(predicted: list[str], gold: list[str]) -> float:
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold lengths differ")
    labels = sorted(set(gold) | set(predicted))
    if not labels:
        return 0.0
    f1s: list[float] = []
    for label in labels:
        tp = sum(p == label and g == label for p, g in zip(predicted, gold, strict=True))
        fp = sum(p == label and g != label for p, g in zip(predicted, gold, strict=True))
        fn = sum(p != label and g == label for p, g in zip(predicted, gold, strict=True))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if (precision + recall) else 0.0)
    return sum(f1s) / len(f1s)


def per_sense_recall(predicted: list[str], gold: list[str]) -> dict[str, float]:
    """Recall per gold sense — surfaces the rare-sense zero-recall problem."""
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold lengths differ")
    recall: dict[str, float] = {}
    for sense in sorted(set(gold)):
        idx = [i for i, g in enumerate(gold) if g == sense]
        recall[sense] = sum(predicted[i] == sense for i in idx) / len(idx)
    return recall


def majority_sense_predictor(records: list[SenseRecord]) -> Callable[[SenseRecord], str]:
    """Per-lemma majority-sense predictor (in-sample floor).

    Caveat: built from the eval records themselves, so it is an optimistic
    floor, not a held-out baseline. Any real model must beat it on held-out
    data to claim it learned anything.
    """
    from collections import Counter

    by_lemma: dict[str, Counter] = {}
    for rec in records:
        by_lemma.setdefault(rec.lemma, Counter())[rec.sense_id] += 1
    majority = {
        lemma: sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for lemma, counter in by_lemma.items()
    }

    def _predict(rec: SenseRecord) -> str:
        return majority[rec.lemma]

    _predict.__name__ = "majority_sense_baseline"
    return _predict


def run_qcsmp_eval(
    records: list[SenseRecord],
    predict_fn: Callable[[SenseRecord], str],
    *,
    source: str = "custom",
) -> dict:
    """Score a sense predictor. Returns a JSON-serializable report."""
    predicted = [predict_fn(rec) for rec in records]
    gold = [rec.sense_id for rec in records]
    sense_recall = per_sense_recall(predicted, gold)
    zero_recall = sorted(s for s, r in sense_recall.items() if r == 0.0)
    return {
        "status": "beta",
        "n": len(records),
        "n_lemmas": len({r.lemma for r in records}),
        "n_senses": len(set(gold)),
        "predictor": source,
        "accuracy": accuracy(predicted, gold),
        "macro_f1": macro_f1(predicted, gold),
        "n_zero_recall_senses": len(zero_recall),
        "zero_recall_senses": zero_recall,
        "pilot_bar": {
            "surface_acc": PILOT_SURFACE_ACC,
            "surface_macro_f1": PILOT_SURFACE_MACRO_F1,
            "majority_acc": PILOT_MAJORITY_ACC,
            "majority_macro_f1": PILOT_MAJORITY_MACRO_F1,
            "delta_Q": PILOT_DELTA_Q,
            "note": "pilot headline is negative for root-space features — beat this honestly",
        },
    }


def print_report(report: dict) -> None:
    print("== Q-CSMP eval (beta) ==")
    print(f"predictor: {report['predictor']}")
    print(
        f"n={report['n']} lemmas={report['n_lemmas']} senses={report['n_senses']} "
        f"accuracy={report['accuracy']:.4f} macro_f1={report['macro_f1']:.4f}"
    )
    print(
        f"zero-recall senses: {report['n_zero_recall_senses']} "
        "(pilot had 12/88 rare senses at 0 recall)"
    )
    bar = report["pilot_bar"]
    print(
        f"pilot bar to beat: acc={bar['surface_acc']} macro_f1={bar['surface_macro_f1']} "
        f"(Δ_Q={bar['delta_Q']}: surface stats won at pilot scale)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Q-CSMP sense-disambiguation eval (beta)")
    parser.add_argument(
        "--gold", required=True, help="Q-CSMP JSONL path (Zenodo DOI " + QCSMP_DOI + ")"
    )
    parser.add_argument("--out", help="write JSON report to this path")
    args = parser.parse_args(argv)

    try:
        records = load_qcsmp_jsonl(args.gold)
    except FileNotFoundError as exc:
        print(f"SKIP — {exc}")
        return 2

    baseline = majority_sense_predictor(records)
    report = run_qcsmp_eval(records, baseline, source="majority_sense_baseline")
    print_report(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
