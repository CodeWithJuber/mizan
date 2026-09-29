"""Tests for the ruh_model.eval harness (Phase 0 credibility foundation).

Torch-free: modules are loaded by file path via ``_bootstrap.ensure_torchfree``,
bypassing the torch-importing ``ruh_model/__init__.py``. Run with::

    python -m pytest ruh_model/tests/test_eval_harness.py \\
        --import-mode=importlib --noconftest -v

(``--noconftest`` skips the existing torch-dependent ``conftest.py``;
``--import-mode=importlib`` avoids package-qualified imports of this file.)

All fixtures are synthetic and inline. Deterministic, no network, no torch.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

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
dialect_eval = _load("ruh_model.eval.dialect_eval", "ruh_model/eval/dialect_eval.py")
qcsmp_eval = _load("ruh_model.eval.qcsmp_eval", "ruh_model/eval/qcsmp_eval.py")
adjudication = _load("ruh_model.eval.adjudication", "ruh_model/eval/adjudication.py")


# ---------------------------------------------------------------------------
# morphology_eval: gold loading
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_gold_tsv_basic(tmp_path: Path):
    gold = _write(tmp_path / "gold.tsv", "يكتب\tكتب\tVERB_PRESENT\nمكتبة\tمكت\tPLACE_NOUN\n")
    items = morphology_eval.load_gold(gold)
    assert [(i.word, i.root, i.pattern) for i in items] == [
        ("يكتب", "كتب", "VERB_PRESENT"),
        ("مكتبة", "مكت", "PLACE_NOUN"),
    ]


def test_load_gold_tsv_skips_comments_and_blanks(tmp_path: Path):
    gold = _write(
        tmp_path / "gold.tsv",
        "# comment\n\nيكتب\tكتب\tVERB_PRESENT\n",
    )
    assert len(morphology_eval.load_gold(gold)) == 1


def test_load_gold_tsv_rejects_short_rows(tmp_path: Path):
    gold = _write(tmp_path / "gold.tsv", "يكتب\tكتب\n")
    with pytest.raises(ValueError, match="3 tab-separated"):
        morphology_eval.load_gold(gold)


def test_load_gold_jsonl(tmp_path: Path):
    gold = _write(
        tmp_path / "gold.jsonl",
        '{"word": "يكتب", "root": "كتب", "pattern": "VERB_PRESENT"}\n',
    )
    items = morphology_eval.load_gold(gold)
    assert items[0].root == "كتب"


def test_load_gold_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="gold file not found"):
        morphology_eval.load_gold(tmp_path / "nope.tsv")


# ---------------------------------------------------------------------------
# morphology_eval: scoring math
# ---------------------------------------------------------------------------


def test_score_predictions_exact_math():
    gold = [
        morphology_eval.GoldItem("w1", "r1", "P1"),
        morphology_eval.GoldItem("w2", "r2", "P2"),
        morphology_eval.GoldItem("w3", "r3", "P3"),
    ]
    pred = [("r1", "P1"), ("r2", "WRONG"), None]
    scores = morphology_eval.score_predictions(pred, gold)
    assert scores["n"] == 3
    assert scores["n_scored"] == 2
    assert scores["n_failed"] == 1
    assert scores["root_accuracy"] == pytest.approx(1.0)
    assert scores["pattern_accuracy"] == pytest.approx(0.5)
    assert scores["exact_accuracy"] == pytest.approx(0.5)


def test_score_predictions_length_mismatch():
    with pytest.raises(ValueError, match="lengths differ"):
        morphology_eval.score_predictions([("a", "b")], [])


def test_camel_leg_skips_gracefully_without_camel_tools():
    try:
        import camel_tools  # noqa: F401

        pytest.skip("camel_tools installed — skip-path not exercised here")
    except ImportError:
        pass
    fn, note = morphology_eval.try_camel_analyzer()
    assert fn is None
    assert "not installed" in note
    assert "fake" in note  # must say no fake comparison is generated


# ---------------------------------------------------------------------------
# morphology_eval: end-to-end Ruh leg (rule-based analyzer, torch-free)
# ---------------------------------------------------------------------------


def test_run_morphology_eval_ruh_leg(tmp_path: Path):
    gold = _write(
        tmp_path / "gold.tsv",
        "يكتب\tكتب\tVERB_PRESENT\nمكتبة\tمكت\tPLACE_NOUN\nكتب\tكتب\tVERB_PAST\n",
    )
    report = morphology_eval.run_morphology_eval(gold, use_camel=False)
    ruh = report["ruh"]
    assert ruh["n"] == 3 and ruh["n_scored"] == 3
    # يكتب and مكتبة match the analyzer's current behavior; كتب does not
    assert ruh["root_accuracy"] == pytest.approx(2 / 3)
    assert ruh["pattern_accuracy"] == pytest.approx(2 / 3)
    assert ruh["exact_accuracy"] == pytest.approx(2 / 3)
    assert report["camel"]["status"] == "skipped"


def test_run_morphology_eval_camel_absent_reports_skip(tmp_path: Path):
    try:
        import camel_tools  # noqa: F401

        pytest.skip("camel_tools installed")
    except ImportError:
        pass
    gold = _write(tmp_path / "gold.tsv", "يكتب\tكتب\tVERB_PRESENT\n")
    report = morphology_eval.run_morphology_eval(gold, use_camel=True)
    assert report["camel"]["status"] == "skipped"
    assert "not installed" in report["camel"]["note"]


# ---------------------------------------------------------------------------
# dialect_eval
# ---------------------------------------------------------------------------


def test_load_nadi_tsv_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as excinfo:
        dialect_eval.load_nadi_tsv(tmp_path / "nadi.tsv")
    assert "NADI" in str(excinfo.value)  # clear pointer, not a bare error


def test_load_nadi_tsv_basic(tmp_path: Path):
    gold = _write(
        tmp_path / "nadi.tsv",
        "id\ttext\tdialect\n1\tازيك يا صاحبي\tEGY\n2\tشلونك\tGLF\n",
    )
    items = dialect_eval.load_nadi_tsv(gold)
    assert [(i.text, i.gold_label) for i in items] == [
        ("ازيك يا صاحبي", "EGY"),
        ("شلونك", "GLF"),
    ]


def test_dialect_accuracy_and_macro_f1_known_values():
    gold = ["a", "a", "b", "b"]
    pred = ["a", "b", "b", "b"]
    assert dialect_eval.accuracy(pred, gold) == pytest.approx(0.75)
    # a: p=1.0 r=0.5 f1=2/3; b: p=2/3 r=1.0 f1=0.8; macro=(2/3+0.8)/2
    assert dialect_eval.macro_f1(pred, gold) == pytest.approx((2 / 3 + 0.8) / 2)


def test_majority_baseline_deterministic_tiebreak():
    labels = ["b", "a", "b", "a"]  # tie 2-2 -> lexicographically smallest
    fn = dialect_eval.majority_baseline_predictor(labels)
    assert fn("anything") == "a"
    assert fn("anything else") == "a"


def test_run_dialect_eval_report_shape(tmp_path: Path):
    gold = _write(
        tmp_path / "nadi.tsv",
        "id\ttext\tdialect\n1\tt1\tEGY\n2\tt2\tEGY\n3\tt3\tGLF\n",
    )
    items = dialect_eval.load_nadi_tsv(gold)
    baseline = dialect_eval.majority_baseline_predictor([i.gold_label for i in items])
    report = dialect_eval.run_dialect_eval(items, baseline, source="majority_baseline")
    assert report["n"] == 3
    assert report["predictor"] == "majority_baseline"
    assert report["accuracy"] == pytest.approx(2 / 3)
    assert sorted(report["labels"]) == ["EGY", "GLF"]


def test_load_madar_tsv_basic(tmp_path: Path):
    corpus = _write(
        tmp_path / "madar.tsv",
        "id\tMSA\tEGY\n1\tكيف حالك\tازيك\n",
    )
    madar = dialect_eval.load_madar_tsv(corpus)
    assert madar.dialects == ["MSA", "EGY"]
    assert madar.rows == [{"MSA": "كيف حالك", "EGY": "ازيك"}]


# ---------------------------------------------------------------------------
# qcsmp_eval
# ---------------------------------------------------------------------------


def test_load_qcsmp_jsonl_missing_file_mentions_zenodo(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as excinfo:
        qcsmp_eval.load_qcsmp_jsonl(tmp_path / "qcsmp.jsonl")
    msg = str(excinfo.value)
    assert "Zenodo" in msg and qcsmp_eval.QCSMP_DOI in msg


def test_qcsmp_scoring_and_zero_recall(tmp_path: Path):
    gold = _write(
        tmp_path / "qcsmp.jsonl",
        '{"id": "1", "lemma": "L1", "context": "c1", "sense_id": "s1"}\n'
        '{"id": "2", "lemma": "L1", "context": "c2", "sense_id": "s1"}\n'
        '{"id": "3", "lemma": "L2", "context": "c3", "sense_id": "s2"}\n'
        '{"id": "4", "lemma": "L2", "context": "c4", "sense_id": "s3"}\n',
    )
    records = qcsmp_eval.load_qcsmp_jsonl(gold)
    # predictor gets s1/s2 right, never predicts s3 -> s3 has 0 recall
    report = qcsmp_eval.run_qcsmp_eval(
        records, lambda r: {"1": "s1", "2": "s1", "3": "s2", "4": "s2"}[r.id]
    )
    assert report["accuracy"] == pytest.approx(0.75)
    assert report["n_zero_recall_senses"] == 1
    assert report["zero_recall_senses"] == ["s3"]
    # the pilot's negative headline result is quoted as the bar to beat
    assert report["pilot_bar"]["delta_Q"] == pytest.approx(-0.0555)


def test_qcsmp_macro_f1_known_value():
    pred = ["a", "b", "b", "b"]
    gold = ["a", "a", "b", "b"]
    assert qcsmp_eval.macro_f1(pred, gold) == pytest.approx((2 / 3 + 0.8) / 2)


def test_majority_sense_predictor_picks_per_lemma_majority(tmp_path: Path):
    gold = _write(
        tmp_path / "qcsmp.jsonl",
        '{"id": "1", "lemma": "L1", "context": "c1", "sense_id": "s1"}\n'
        '{"id": "2", "lemma": "L1", "context": "c2", "sense_id": "s2"}\n'
        '{"id": "3", "lemma": "L1", "context": "c3", "sense_id": "s1"}\n',
    )
    records = qcsmp_eval.load_qcsmp_jsonl(gold)
    fn = qcsmp_eval.majority_sense_predictor(records)
    assert fn(records[0]) == "s1"


# ---------------------------------------------------------------------------
# adjudication: kappa math
# ---------------------------------------------------------------------------


def test_cohen_kappa_perfect_agreement():
    result = adjudication.cohen_kappa(["a", "b", "a"], ["a", "b", "a"])
    assert result["kappa"] == pytest.approx(1.0)
    assert result["observed_agreement"] == pytest.approx(1.0)
    assert result["meets_bar"] is True


def test_cohen_kappa_known_table():
    # po=0.5, pe=0.5 -> kappa=0.0 (agreement at chance level)
    result = adjudication.cohen_kappa(["x", "x", "y", "y"], ["x", "y", "x", "y"])
    assert result["observed_agreement"] == pytest.approx(0.5)
    assert result["expected_agreement"] == pytest.approx(0.5)
    assert result["kappa"] == pytest.approx(0.0)
    assert result["meets_bar"] is False


def test_cohen_kappa_degenerate_single_label():
    result = adjudication.cohen_kappa(["a", "a"], ["a", "a"])
    assert result["kappa"] == pytest.approx(1.0)


def test_cohen_kappa_length_mismatch():
    with pytest.raises(ValueError, match="different lengths"):
        adjudication.cohen_kappa(["a"], ["a", "b"])


def test_paired_labels_counts_skipped():
    a = [
        adjudication.Annotation("t1", "ann_a", "s1"),
        adjudication.Annotation("t2", "ann_a", "s2"),
    ]
    b = [adjudication.Annotation("t2", "ann_b", "s2")]
    labels_a, labels_b, skipped = adjudication.paired_labels(a, b)
    assert (labels_a, labels_b) == (["s2"], ["s2"])
    assert skipped == 1  # t1 annotated by one side only


def test_meets_adjudication_bar_threshold():
    assert adjudication.meets_adjudication_bar(0.61) is True
    assert adjudication.meets_adjudication_bar(0.609) is False
    assert adjudication.ADJUDICATION_KAPPA_BAR == pytest.approx(0.61)


def test_annotation_jsonl_roundtrip(tmp_path: Path):
    tasks = [
        adjudication.AnnotationTask("t1", "كتب", "context words", ["s1", "s2"]),
    ]
    annotations = [adjudication.Annotation("t1", "scholar_1", "s1")]
    adjudication.write_tasks_jsonl(tmp_path / "tasks.jsonl", tasks)
    adjudication.write_annotations_jsonl(tmp_path / "ann.jsonl", annotations)
    assert adjudication.read_tasks_jsonl(tmp_path / "tasks.jsonl")[0].lemma == "كتب"
    back = adjudication.read_annotations_jsonl(tmp_path / "ann.jsonl")
    assert (back[0].task_id, back[0].annotator, back[0].chosen_sense) == (
        "t1",
        "scholar_1",
        "s1",
    )


def test_validate_annotation_warns_on_new_sense():
    task = adjudication.AnnotationTask("t1", "L", "ctx", ["s1"])
    ann = adjudication.Annotation("t1", "ann", "s9-new")
    warnings = adjudication.validate_annotation(ann, task)
    assert len(warnings) == 1 and "not in candidate_senses" in warnings[0]
