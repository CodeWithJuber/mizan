"""Smoke tests for the eval harness end-to-end paths + committed artifacts.

Covers what ``test_eval_harness.py`` does not: full ``run_*`` pipelines on tiny
synthetic data with JSON-schema assertions on the reports (the keys
``RESULTS.md`` tooling depends on), and the committed QAC gold file that backs
the published morphology numbers.

Torch-free: same file-path loading pattern as test_eval_harness.py. Run with::

    python -m pytest ruh_model/tests/test_eval_smoke.py \\
        --import-mode=importlib --noconftest -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

REPO_ROOT = (
    Path(os.environ.get("MIZAN_ROOT", "")).resolve()
    if os.environ.get("MIZAN_ROOT")
    else Path(__file__).resolve().parents[2]
)


def _load(dotted_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(dotted_name, REPO_ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)
    return module


_bootstrap = _load("ruh_eval__bootstrap", "ruh_model/eval/_bootstrap.py")
_bootstrap.ensure_torchfree(REPO_ROOT)

morphology_eval = _load("ruh_model.eval.morphology_eval", "ruh_model/eval/morphology_eval.py")
qcsmp_eval = _load("ruh_model.eval.qcsmp_eval", "ruh_model/eval/qcsmp_eval.py")


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# morphology_eval: end-to-end report schema
# ---------------------------------------------------------------------------


def test_morphology_eval_end_to_end_schema(tmp_path: Path):
    gold = _write(
        tmp_path / "gold.tsv",
        "يكتب\tكتب\tVERB_PRESENT\nكتب\tكتب\tVERB_PAST\n",
    )
    report = morphology_eval.run_morphology_eval(gold, use_camel=False)

    assert report["status"] == "beta"
    assert report["gold_path"] == str(gold)
    ruh = report["ruh"]
    for key in ("n", "n_scored", "n_failed", "root_accuracy", "pattern_accuracy", "exact_accuracy"):
        assert key in ruh, f"missing report key: {key}"
    assert ruh["n"] == 2
    assert 0.0 <= ruh["root_accuracy"] <= 1.0
    assert report["camel"]["status"] == "skipped"
    # JSON-serializable (results are committed as JSON)
    json.dumps(report)


def test_committed_qac_gold_file_loads():
    """The gold file backing the published 34.9% number must stay loadable."""
    gold_path = REPO_ROOT / "ruh_model" / "benchmarks" / "data" / "morph_gold_qac_test.tsv"
    assert gold_path.exists(), "committed gold file missing"
    items = morphology_eval.load_gold(gold_path)
    assert len(items) == 172, f"expected 172 gold types, got {len(items)}"
    assert all(i.word and i.root for i in items)


# ---------------------------------------------------------------------------
# qcsmp_eval: end-to-end report schema
# ---------------------------------------------------------------------------


def test_qcsmp_eval_end_to_end_schema():
    records = [
        qcsmp_eval.SenseRecord(id="1", lemma="كتب", context="c1", sense_id="qcsmp2:كتب:write"),
        qcsmp_eval.SenseRecord(id="2", lemma="كتب", context="c2", sense_id="qcsmp2:كتب:write"),
        qcsmp_eval.SenseRecord(id="3", lemma="كتب", context="c3", sense_id="qcsmp2:كتب:ordain"),
    ]
    report = qcsmp_eval.run_qcsmp_eval(
        records, qcsmp_eval.majority_sense_predictor(records), source="smoke"
    )

    for key in (
        "status",
        "n",
        "n_lemmas",
        "n_senses",
        "predictor",
        "accuracy",
        "macro_f1",
        "n_zero_recall_senses",
        "zero_recall_senses",
        "pilot_bar",
    ):
        assert key in report, f"missing report key: {key}"
    assert report["n"] == 3
    assert report["accuracy"] == 2 / 3  # majority sense "write" wins 2/3
    assert report["n_zero_recall_senses"] == 1  # "ordain" never predicted
    bar = report["pilot_bar"]
    assert bar["surface_acc"] == 0.7592
    assert bar["delta_Q"] == -0.0555  # the negative headline must stay in the schema
    json.dumps(report)
