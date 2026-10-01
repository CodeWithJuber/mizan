"""Tests for the ruh_model.review scholar-review pipeline (Phase 0).

Torch-free: pipeline.py is stdlib-only, loaded by file path via
``_bootstrap.ensure_torchfree``. Run with::

    python -m pytest ruh_model/tests/test_review_pipeline.py \\
        --import-mode=importlib --noconftest -v

Deterministic, no network, no torch.
"""

from __future__ import annotations

import importlib.util
import json
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

pipeline = _load("ruh_model.review.pipeline", "ruh_model/review/pipeline.py")


def _item(**kwargs):
    base = {
        "item_id": "q1",
        "text": "نص تجريبي",
        "proposed_sense": "sense-a",
        "confidence": 0.5,
    }
    base.update(kwargs)
    return pipeline.ReviewItem(**base)


# ---------------------------------------------------------------------------
# needs_review thresholds (JEV: conservative — 0.95 quranic / 0.80 general)
# ---------------------------------------------------------------------------


def test_needs_review_general_threshold():
    assert pipeline.needs_review(0.79) is True
    assert pipeline.needs_review(0.80) is False  # boundary: < threshold escalates
    assert pipeline.needs_review(0.95) is False


def test_needs_review_quranic_always_conservative():
    # amāna: low-confidence Quranic items ALWAYS go to review
    assert pipeline.needs_review(0.90, is_quranic=True) is True
    assert pipeline.needs_review(0.949, is_quranic=True) is True
    assert pipeline.needs_review(0.95, is_quranic=True) is False
    assert pipeline.needs_review(0.99, is_quranic=True) is False


def test_needs_review_rejects_bad_confidence():
    with pytest.raises(ValueError, match="outside"):
        pipeline.needs_review(1.5)
    with pytest.raises(ValueError, match="outside"):
        pipeline.needs_review(-0.1)


def test_threshold_constants_match_jev_decision():
    assert pipeline.QURANIC_REVIEW_THRESHOLD == pytest.approx(0.95)
    assert pipeline.GENERAL_REVIEW_THRESHOLD == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# ReviewItem validation
# ---------------------------------------------------------------------------


def test_item_rejects_bad_status():
    with pytest.raises(ValueError, match="invalid status"):
        _item(status="maybe")


def test_item_rejects_confidence_out_of_range():
    with pytest.raises(ValueError, match="outside"):
        _item(confidence=2.0)


def test_item_rejects_decided_without_reviewer():
    with pytest.raises(ValueError, match="reviewer"):
        _item(status="approved")


def test_item_rejects_empty_id():
    with pytest.raises(ValueError, match="item_id"):
        _item(item_id="")


# ---------------------------------------------------------------------------
# ReviewStore transitions
# ---------------------------------------------------------------------------


def _store(tmp_path: Path) -> pipeline.ReviewStore:
    return pipeline.ReviewStore(tmp_path / "reviews.jsonl")


def test_add_and_get(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    assert store.get("q1").proposed_sense == "sense-a"
    assert len(store) == 1


def test_add_duplicate_raises(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    with pytest.raises(ValueError, match="duplicate item_id"):
        store.add(_item())


def test_get_unknown_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.get("missing")


def test_decide_sets_audit_trail(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    decided = store.decide("q1", pipeline.APPROVED, reviewer="scholar@example.org")
    assert decided.status == "approved"
    assert decided.reviewer == "scholar@example.org"
    assert decided.decided_at is not None  # ISO timestamp recorded


def test_decide_rejected_path(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    decided = store.decide("q1", pipeline.REJECTED, reviewer="scholar@example.org")
    assert decided.status == "rejected"


def test_decide_requires_pending(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    store.decide("q1", pipeline.APPROVED, reviewer="s@x.org")
    with pytest.raises(ValueError, match="already decided"):
        store.decide("q1", pipeline.REJECTED, reviewer="s@x.org")


def test_decide_rejects_bad_status_and_empty_reviewer(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    with pytest.raises(ValueError, match="approved/rejected"):
        store.decide("q1", "pending", reviewer="s@x.org")
    with pytest.raises(ValueError, match="reviewer is required"):
        store.decide("q1", pipeline.APPROVED, reviewer="  ")


def test_reopen_resets_to_pending(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item())
    store.decide("q1", pipeline.APPROVED, reviewer="s@x.org")
    reopened = store.reopen("q1")
    assert reopened.status == "pending"
    assert reopened.reviewer is None
    assert reopened.decided_at is None
    with pytest.raises(ValueError, match="already pending"):
        store.reopen("q1")


def test_list_pending_and_quranic_filter(tmp_path: Path):
    store = _store(tmp_path)
    store.add(_item(item_id="a", is_quranic=True))
    store.add(_item(item_id="b", is_quranic=False))
    store.add(_item(item_id="c", is_quranic=True))
    store.decide("c", pipeline.APPROVED, reviewer="s@x.org")
    assert store.pending_count() == 2
    assert {i.item_id for i in store.list_pending()} == {"a", "b"}
    assert [i.item_id for i in store.list_pending(quranic_only=True)] == ["a"]


def test_save_load_roundtrip(tmp_path: Path):
    path = tmp_path / "reviews.jsonl"
    store = pipeline.ReviewStore(path)
    store.add(_item(item_id="a", is_quranic=True, source="ruh-beta"))
    store.add(_item(item_id="b", confidence=0.99))
    store.decide("b", pipeline.REJECTED, reviewer="s@x.org")
    store.save()

    raw = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(raw) == 2
    assert json.loads(raw[0])["item_id"] == "a"

    reloaded = pipeline.ReviewStore(path)
    assert len(reloaded) == 2
    assert reloaded.get("a").is_quranic is True
    assert reloaded.get("a").source == "ruh-beta"
    assert reloaded.get("b").status == "rejected"
    assert reloaded.get("b").reviewer == "s@x.org"


def test_enqueue_proposal_lands_pending(tmp_path: Path):
    store = _store(tmp_path)
    item = pipeline.enqueue_proposal(
        store,
        item_id="n1",
        text="نص",
        proposed_sense="sense-x",
        confidence=0.4,
        is_quranic=True,
        source="test",
    )
    assert item.status == "pending"
    assert store.pending_count() == 1
