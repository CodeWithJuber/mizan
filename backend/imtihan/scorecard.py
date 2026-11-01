"""Public reliability scorecard: AGI-test results anyone can read.

An administrator publishes a finished Imtihan run. Only its aggregate report
is made public: per-block pass rates with Wilson intervals, the weighted
index, pass^k, calibration (ECE/Brier), consistency, the agentic dimensions,
Isnad support, cost and latency. Prompts, answers and per-task rows are never
published, and the locked evaluation appears only as its block score.

Each publication is written as a Sakk receipt (owner ``system``) holding the
SHA-256 of the report's canonical JSON, so a published number cannot be
changed later without the signed chain showing it.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_KEYS = (
    "blocks",
    "index",
    "weighted",
    "faculties",
    "agentic",
    "games",
    "isnad",
    "calibration",
    "consistency",
    "cost",
)


def _db() -> sqlite3.Connection:
    directory = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "imtihan"
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "scorecard.db")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE IF NOT EXISTS published (run_id TEXT PRIMARY KEY, created_at REAL, "
        "published_at TEXT, model TEXT, repeats INTEGER, blocks TEXT, report TEXT, "
        "report_sha256 TEXT, receipt TEXT)"
    )
    return connection


def aggregate(report: dict) -> dict:
    """Only the aggregate parts of a run's report."""
    return {key: report[key] for key in REPORT_KEYS if key in report}


def report_digest(report: dict) -> str:
    from security.sakk import canonical

    return hashlib.sha256(canonical(report)).hexdigest()


def publish(run: dict) -> dict:
    if run.get("status") != "complete":
        raise ValueError("Only a finished run can be published")
    report = aggregate(((run.get("result") or {}).get("report")) or {})
    if not report.get("index"):
        raise ValueError("This run has no report to publish")
    from security import sakk

    found = report_digest(report)
    receipt = sakk.store().append(
        "system",
        "scorecard",
        {"run": run["id"], "report": found},
        "AGI test result published",
    )
    sakk.store().sign_day()  # the published result is in a signed checkpoint at once
    entry = {
        "run_id": run["id"],
        "created_at": run.get("created_at"),
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": run.get("model"),
        "repeats": run.get("repeats"),
        "blocks": run.get("blocks") or [],
        "report": report,
        "report_sha256": found,
        "receipt": {"seq": receipt["seq"], "hash": receipt["hash"]},
    }
    with _db() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO published VALUES (?,?,?,?,?,?,?,?,?)",
            (
                entry["run_id"],
                entry["created_at"],
                entry["published_at"],
                entry["model"],
                entry["repeats"],
                json.dumps(entry["blocks"]),
                json.dumps(report, ensure_ascii=False),
                found,
                json.dumps(entry["receipt"]),
            ),
        )
    return entry


def unpublish(run_id: str) -> bool:
    with _db() as connection:
        return connection.execute("DELETE FROM published WHERE run_id = ?", (run_id,)).rowcount > 0


def _entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "published_at": row["published_at"],
        "model": row["model"],
        "repeats": row["repeats"],
        "blocks": json.loads(row["blocks"] or "[]"),
        "report": json.loads(row["report"]),
        "report_sha256": row["report_sha256"],
        "receipt": json.loads(row["receipt"] or "{}"),
    }


def get(run_id: str) -> dict | None:
    with _db() as connection:
        row = connection.execute("SELECT * FROM published WHERE run_id = ?", (run_id,)).fetchone()
    return _entry(row) if row else None


def published_ids() -> set[str]:
    with _db() as connection:
        return {row[0] for row in connection.execute("SELECT run_id FROM published")}


def view() -> dict:
    """The public page: the latest published run in full, earlier ones as their index."""
    with _db() as connection:
        rows = connection.execute("SELECT * FROM published ORDER BY created_at DESC").fetchall()
    entries = [_entry(row) for row in rows]
    from security import sakk

    store = sakk.store()
    return {
        "latest": entries[0] if entries else None,
        "history": [
            {
                "run_id": entry["run_id"],
                "created_at": entry["created_at"],
                "model": entry["model"],
                "index": entry["report"].get("index"),
                "weighted": entry["report"].get("weighted"),
            }
            for entry in entries
        ],
        "sakk": {"public_key": store.public_key(), "roots": store.roots(7)},
    }
