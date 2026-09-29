"""Dialect eval scaffold: NADI/MADAR-format loaders + scoring (beta).

Phase-0 purpose: establish the *baseline* numbers (majority-class) that the
future Bayan dialect-normalization layer must beat, and define the data
interfaces it will plug into. The normalization engine itself does not exist
yet — predictions come from a caller-supplied ``predict_fn``.

Formats (beta definitions, datasets not bundled):
  NADI-style TSV: one tweet per row — ``id<TAB>text<TAB>dialect_label``
    (column indices configurable; header row optional).
  MADAR-style TSV: parallel sentences — ``id<TAB><dialect_1><TAB><dialect_2>...``
    with one column per dialect; header names the dialects.

If the dataset file is absent, loaders raise FileNotFoundError with pointers —
no synthetic data is ever generated in its place.

Status: beta / unverified scaffold. Torch-free, stdlib-only.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

NADI_POINTER = (
    "NADI (Nuanced Arabic Dialect Identification) shared-task data is released "
    "by the task organizers; MADAR (Multi-Arabic Dialect Applications and "
    "Resources) is available from its authors. Neither is bundled here — "
    "download the split you have rights to and point --gold at it."
)


# ---------------------------------------------------------------------------
# Gold data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DialectGoldItem:
    text: str
    gold_label: str


def load_nadi_tsv(
    path: str | Path,
    text_col: int = 1,
    label_col: int = 2,
    has_header: bool = True,
    dialect_col_name: str | None = None,
) -> list[DialectGoldItem]:
    """Load NADI-style tweet-level dialect ID data.

    Row layout: ``id<TAB>text<TAB>dialect_label`` (indices configurable).
    If ``dialect_col_name`` is given with a header row, the label column is
    resolved by name instead of index.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}\n{NADI_POINTER}")
    items: list[DialectGoldItem] = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        rows = list(reader)
        if has_header:
            header = rows.pop(0)
            if dialect_col_name is not None:
                label_col = header.index(dialect_col_name)
        for lineno, row in enumerate(rows, 2 if has_header else 1):
            if not row or all(not c.strip() for c in row):
                continue
            if max(text_col, label_col) >= len(row):
                raise ValueError(f"{path}:{lineno}: row has {len(row)} columns")
            text, label = row[text_col].strip(), row[label_col].strip()
            if text and label:
                items.append(DialectGoldItem(text=text, gold_label=label))
    if not items:
        raise ValueError(f"{path}: no usable rows found")
    return items


@dataclass(frozen=True)
class MadarCorpus:
    """Parallel sentences across dialects: rows map dialect -> sentence."""

    dialects: list[str]
    rows: list[dict[str, str]]


def load_madar_tsv(path: str | Path, id_col: int = 0) -> MadarCorpus:
    """Load MADAR-style parallel dialect data.

    Header row names the dialects (first ``id_col`` columns are IDs, skipped).
    Each subsequent row holds the same sentence rendered in each dialect.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}\n{NADI_POINTER}")
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        rows = [r for r in reader if r and any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ValueError(f"{path}: need a header row plus at least one data row")
    header = rows[0]
    dialects = [h.strip() for h in header[id_col + 1 :]]
    if not dialects:
        raise ValueError(f"{path}: no dialect columns found in header")
    data_rows: list[dict[str, str]] = []
    for row in rows[1:]:
        cells = row[id_col + 1 : id_col + 1 + len(dialects)]
        if len(cells) < len(dialects):
            continue
        data_rows.append({d: c.strip() for d, c in zip(dialects, cells, strict=True)})
    return MadarCorpus(dialects=dialects, rows=data_rows)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def accuracy(predicted: list[str], gold: list[str]) -> float:
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold lengths differ")
    if not gold:
        return 0.0
    return sum(p == g for p, g in zip(predicted, gold, strict=True)) / len(gold)


def macro_f1(predicted: list[str], gold: list[str]) -> float:
    """Macro-averaged F1 over the union of predicted and gold labels."""
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


def majority_baseline_predictor(gold_labels: list[str]) -> Callable[[str], str]:
    """Return a predictor that always emits the majority gold label.

    Honest floor: any dialect model must beat this to claim it learned anything.
    Ties break toward the lexicographically smallest label (deterministic).
    """
    if not gold_labels:
        raise ValueError("no gold labels for majority baseline")
    counts: dict[str, int] = {}
    for label in gold_labels:
        counts[label] = counts.get(label, 0) + 1
    majority = sorted(counts, key=lambda lbl: (-counts[lbl], lbl))[0]

    def _predict(_text: str) -> str:
        return majority

    _predict.__name__ = f"majority_baseline({majority})"
    return _predict


def run_dialect_eval(
    gold: list[DialectGoldItem], predict_fn: Callable[[str], str], *, source: str = "custom"
) -> dict:
    """Score ``predict_fn`` on gold items. Returns a JSON-serializable report."""
    predicted = [predict_fn(item.text) for item in gold]
    gold_labels = [item.gold_label for item in gold]
    return {
        "status": "beta",
        "n": len(gold),
        "predictor": source,
        "accuracy": accuracy(predicted, gold_labels),
        "macro_f1": macro_f1(predicted, gold_labels),
        "labels": sorted(set(gold_labels)),
    }


def print_report(report: dict) -> None:
    print("== Dialect eval (beta) ==")
    print(f"predictor: {report['predictor']}")
    print(f"n={report['n']} accuracy={report['accuracy']:.4f} macro_f1={report['macro_f1']:.4f}")
    print(f"labels: {', '.join(report['labels'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dialect ID eval scaffold (beta)")
    parser.add_argument("--gold", required=True, help="NADI-style TSV path")
    parser.add_argument("--text-col", type=int, default=1)
    parser.add_argument("--label-col", type=int, default=2)
    parser.add_argument("--no-header", action="store_true")
    parser.add_argument("--out", help="write JSON report to this path")
    args = parser.parse_args(argv)

    try:
        gold = load_nadi_tsv(
            args.gold,
            text_col=args.text_col,
            label_col=args.label_col,
            has_header=not args.no_header,
        )
    except FileNotFoundError as exc:
        print(f"SKIP — {exc}")
        return 2

    baseline = majority_baseline_predictor([i.gold_label for i in gold])
    report = run_dialect_eval(gold, baseline, source="majority_baseline")
    print_report(report)
    print("note: majority baseline only — the dialect-normalization engine is not built yet")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
