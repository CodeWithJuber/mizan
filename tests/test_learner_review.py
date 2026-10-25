"""Captured model outputs cannot silently become reviewed or original training gold."""

import json
import sqlite3

import pytest

from learner.data_export import DataExporter
from learner.ruh_learner import RuhLearner


async def capture(learner, provider="openrouter"):
    await learner.capture(
        "How should I greet?",
        "Assalamu alaikum",
        provider,
        "observed-model",
        {"review_status": "accepted", "quality_score": 1.0},
    )
    return (await learner.get_recent(limit=1))[0]


async def review(learner, row, **overrides):
    arguments = {
        "reviewer_id": "authenticated-reviewer",
        "expected_hash": row["content_hash"],
        "accepted": True,
        "evidence": "User verified the requested phrasing; no claim of source authorship.",
        "quality_score": 0.95,
    }
    arguments.update(overrides)
    return await learner.review_interaction(row["id"], **arguments)


@pytest.mark.asyncio
async def test_capture_metadata_and_quality_score_do_not_grant_export(tmp_path):
    learner = RuhLearner(str(tmp_path / "capture.db"))
    await learner.initialize()
    row = await capture(learner)
    exporter = DataExporter(learner.db_path)
    assert row["review_status"] == "unreviewed"
    assert await exporter.count_exportable(min_quality=0.0) == 0
    await learner.update_quality(row["id"], 1.0)
    assert await exporter.export_jsonl(str(tmp_path / "candidate.jsonl")) == 0
    assert (await learner.get_stats())["exportable_count"] == 0


@pytest.mark.asyncio
async def test_review_export_preserves_authorship_without_training_format(tmp_path):
    learner = RuhLearner(str(tmp_path / "capture.db"))
    await learner.initialize()
    row = await capture(learner)
    result = await review(learner, row)
    assert result["original_data_eligible"] is False
    exporter = DataExporter(learner.db_path)
    assert await exporter.count_exportable() == 1
    output = tmp_path / "candidate.jsonl"
    assert await exporter.export_jsonl(str(output)) == 1
    entry = json.loads(output.read_text())
    assert entry["provenance"]["authorship"] == "model"
    assert entry["provenance"]["content_hash"] == row["content_hash"]
    assert entry["review"]["reviewer_id"] == "authenticated-reviewer"
    assert entry["original_data_eligible"] is False
    assert entry["independently_verified"] is False
    assert "text" not in entry and "messages" not in entry and "lang" not in entry
    stats = await learner.get_stats()
    assert stats["exportable_count"] == 1
    assert stats["automatic_weight_training"] is False


@pytest.mark.asyncio
async def test_rejection_score_change_and_content_change_remove_export(tmp_path):
    learner = RuhLearner(str(tmp_path / "capture.db"))
    await learner.initialize()
    row = await capture(learner)
    exporter = DataExporter(learner.db_path)
    await review(learner, row)
    await review(learner, row, accepted=False)
    assert await exporter.count_exportable() == 0
    await review(learner, row)
    await learner.update_quality(row["id"], 1.0)
    assert await exporter.count_exportable() == 0
    await review(learner, row)
    with sqlite3.connect(learner.db_path) as db:
        db.execute("UPDATE interactions SET response = 'changed' WHERE id = ?", (row["id"],))
    assert await exporter.count_exportable() == 0
    with pytest.raises(ValueError, match="hash mismatch"):
        await review(learner, row)


@pytest.mark.asyncio
async def test_legacy_scores_migrate_unreviewed_without_losing_capture(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE interactions (id INTEGER PRIMARY KEY, prompt TEXT, response TEXT, "
            "provider TEXT, model TEXT, domain TEXT, quality_score REAL, metadata TEXT, created_at REAL)"
        )
        db.execute(
            "INSERT INTO interactions VALUES (1, 'old', 'unreviewed output', 'openrouter', "
            "'old-model', '', 1.0, '{}', 1.0)"
        )
    assert await DataExporter(path).count_exportable() == 0
    learner = RuhLearner(path)
    await learner.initialize()
    await learner.initialize()
    row = (await learner.get_recent())[0]
    assert row["response"] == "unreviewed output"
    assert row["quality_score"] == 1.0
    assert row["review_status"] == "unreviewed"
    assert (await learner.get_stats())["exportable_count"] == 0


@pytest.mark.asyncio
async def test_review_requires_verdict_reviewer_evidence_and_finite_score(tmp_path):
    learner = RuhLearner(str(tmp_path / "capture.db"))
    await learner.initialize()
    row = await capture(learner)
    for overrides in [
        {"reviewer_id": ""},
        {"evidence": " "},
        {"accepted": 1},
        {"expected_hash": "stale"},
        {"quality_score": float("nan")},
        {"quality_score": float("inf")},
        {"quality_score": True},
    ]:
        with pytest.raises(ValueError):
            await review(learner, row, **overrides)
    assert await DataExporter(learner.db_path).count_exportable() == 0


@pytest.mark.asyncio
async def test_owner_capture_and_review_do_not_cross_private_databases(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    alice = RuhLearner.for_owner("alice")
    bob = RuhLearner.for_owner("bob")
    await alice.initialize()
    await bob.initialize()
    row = await capture(alice)
    await review(alice, row)
    assert await bob.get_recent() == []
    assert await DataExporter(bob.db_path).count_exportable() == 0
    with pytest.raises(ValueError, match="missing"):
        await review(bob, row)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["mizan-owned", "mizan-support"])
async def test_own_support_output_stays_out_of_legacy_export_after_review(tmp_path, provider):
    learner = RuhLearner(str(tmp_path / "capture.db"))
    await learner.initialize()
    row = await capture(learner, provider=provider)
    await review(learner, row)
    assert await DataExporter(learner.db_path).count_exportable(min_quality=0.0) == 0
