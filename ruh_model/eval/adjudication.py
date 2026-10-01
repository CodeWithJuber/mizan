"""Adjudication pilot scaffold: annotation tasks + Cohen's kappa (beta).

The Q-CSMP v2 card makes expert adjudication with inter-annotator agreement
κ ≥ 0.61 a hard prerequisite before any peer-reviewed publication. This module
is the tooling for that pilot: task JSONL format, annotation JSONL format, and
a deterministic Cohen's kappa calculator.

Task JSONL (one per line):
  {"task_id": ..., "lemma": ..., "context": ..., "candidate_senses": [...],
   "source": "qcsmp2", "notes": ...}

Annotation JSONL (one per line):
  {"task_id": ..., "annotator": ..., "chosen_sense": ...,
   "decided_at": "2026-09-29T12:00:00+00:00", "notes": ...}

Status: beta / unverified scaffold. Torch-free, stdlib-only.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The Q-CSMP v2 card's own prerequisite for publication.
ADJUDICATION_KAPPA_BAR = 0.61


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnnotationTask:
    task_id: str
    lemma: str
    context: str
    candidate_senses: list[str] = field(default_factory=list)
    source: str = "qcsmp2"
    notes: str = ""


@dataclass(frozen=True)
class Annotation:
    task_id: str
    annotator: str
    chosen_sense: str
    decided_at: str = field(default_factory=_utcnow_iso)
    notes: str = ""


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_tasks_jsonl(path: str | Path, tasks: list[AnnotationTask]) -> None:
    write_jsonl(path, [asdict(t) for t in tasks])


def read_tasks_jsonl(path: str | Path) -> list[AnnotationTask]:
    tasks: list[AnnotationTask] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            if raw.strip():
                tasks.append(AnnotationTask(**json.loads(raw)))
    return tasks


def write_annotations_jsonl(path: str | Path, annotations: list[Annotation]) -> None:
    write_jsonl(path, [asdict(a) for a in annotations])


def read_annotations_jsonl(path: str | Path) -> list[Annotation]:
    annotations: list[Annotation] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            if raw.strip():
                annotations.append(Annotation(**json.loads(raw)))
    return annotations


def validate_annotation(annotation: Annotation, task: AnnotationTask) -> list[str]:
    """Return human-readable warnings (empty = clean)."""
    warnings: list[str] = []
    if annotation.task_id != task.task_id:
        warnings.append("task_id mismatch")
    if task.candidate_senses and annotation.chosen_sense not in task.candidate_senses:
        warnings.append(
            f"chosen_sense {annotation.chosen_sense!r} not in candidate_senses "
            "(annotator added a new sense — adjudicate)"
        )
    return warnings


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------


def paired_labels(
    annotations_a: list[Annotation], annotations_b: list[Annotation]
) -> tuple[list[str], list[str], int]:
    """Align two annotators' labels by task_id.

    Returns (labels_a, labels_b, n_skipped). Only tasks annotated by BOTH
    annotators are paired; tasks annotated by one side only are counted in
    ``n_skipped`` and reported, never silently dropped.
    """
    map_a = {a.task_id: a.chosen_sense for a in annotations_a}
    map_b = {b.task_id: b.chosen_sense for b in annotations_b}
    common = sorted(set(map_a) & set(map_b))
    skipped = len(set(map_a) ^ set(map_b))
    return [map_a[t] for t in common], [map_b[t] for t in common], skipped


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> dict[str, Any]:
    """Cohen's kappa for two annotators' label sequences.

    kappa = (po - pe) / (1 - pe), where po is observed agreement and pe is
    chance agreement from the marginal label distributions. Deterministic.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("label sequences have different lengths")
    n = len(labels_a)
    if n == 0:
        raise ValueError("no paired labels")
    po = sum(a == b for a, b in zip(labels_a, labels_b, strict=True)) / n

    labels = sorted(set(labels_a) | set(labels_b))
    pe = 0.0
    for label in labels:
        pa = sum(a == label for a in labels_a) / n
        pb = sum(b == label for b in labels_b) / n
        pe += pa * pb

    if pe == 1.0:
        # Degenerate: both annotators used a single identical label.
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)
    return {
        "kappa": kappa,
        "observed_agreement": po,
        "expected_agreement": pe,
        "n": n,
        "meets_bar": kappa >= ADJUDICATION_KAPPA_BAR,
        "bar": ADJUDICATION_KAPPA_BAR,
    }


def meets_adjudication_bar(kappa: float, threshold: float = ADJUDICATION_KAPPA_BAR) -> bool:
    """Whether kappa clears the publication prerequisite (default 0.61)."""
    return kappa >= threshold


def print_kappa_report(result: dict[str, Any]) -> None:
    print("== Adjudication kappa (beta) ==")
    print(
        f"n={result['n']} po={result['observed_agreement']:.4f} "
        f"pe={result['expected_agreement']:.4f} kappa={result['kappa']:.4f}"
    )
    bar = result["bar"]
    verdict = "MEETS" if result["meets_bar"] else "BELOW"
    print(f"adjudication bar κ≥{bar}: {verdict}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adjudication kappa calculator (beta)")
    parser.add_argument("--a", required=True, help="annotator A annotations JSONL")
    parser.add_argument("--b", required=True, help="annotator B annotations JSONL")
    parser.add_argument("--threshold", type=float, default=ADJUDICATION_KAPPA_BAR)
    args = parser.parse_args(argv)

    ann_a = read_annotations_jsonl(args.a)
    ann_b = read_annotations_jsonl(args.b)
    labels_a, labels_b, skipped = paired_labels(ann_a, ann_b)
    if skipped:
        print(f"note: {skipped} task(s) annotated by only one side — excluded from kappa")
    if not labels_a:
        print("no tasks annotated by both annotators — nothing to score")
        return 2
    result = cohen_kappa(labels_a, labels_b)
    result["meets_bar"] = meets_adjudication_bar(result["kappa"], args.threshold)
    result["bar"] = args.threshold
    print_kappa_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
