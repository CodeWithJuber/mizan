"""Capture private model-output candidates, separate from actual weight training."""

import hashlib
import json
import os
import time
from pathlib import Path

import aiosqlite

from learner.review_contract import content_hash, validate_quality

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prompt TEXT NOT NULL,
        response TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        domain TEXT DEFAULT '',
        quality_score REAL DEFAULT 0.0,
        metadata TEXT DEFAULT '{}',
        created_at REAL NOT NULL
    )
"""

_INSERT_SQL = (
    "INSERT INTO interactions "
    "(prompt, response, provider, model, metadata, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_STATS_BY_PROVIDER_SQL = "SELECT COUNT(*), provider FROM interactions GROUP BY provider"

_STATS_TOTAL_SQL = "SELECT COUNT(*) FROM interactions"

_RECENT_SQL = (
    "SELECT id, prompt, response, provider, model, quality_score, created_at, "
    "review_status, reviewer_id, reviewed_at, review_evidence "
    "FROM interactions ORDER BY created_at DESC, id DESC LIMIT ?"
)

_UPDATE_QUALITY_SQL = (
    "UPDATE interactions SET quality_score = ?, review_status = 'unreviewed', "
    "reviewer_id = NULL, reviewed_at = NULL, review_evidence = NULL, "
    "reviewed_content_hash = NULL WHERE id = ?"
)

_REVIEW_COLUMNS = {
    "review_status": "TEXT NOT NULL DEFAULT 'unreviewed'",
    "reviewer_id": "TEXT",
    "reviewed_at": "REAL",
    "review_evidence": "TEXT",
    "reviewed_content_hash": "TEXT",
}


class RuhLearner:
    """Store unreviewed captures; explicit review permits candidate export only."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        return self._db_path

    @classmethod
    def for_owner(cls, owner_id: str) -> "RuhLearner":
        if not owner_id:
            raise ValueError("An authenticated owner is required")
        directory = (
            Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan"))
            / "private"
            / hashlib.sha256(owner_id.encode()).hexdigest()
        )
        directory.mkdir(parents=True, exist_ok=True)
        return cls(str(directory / "learner.sqlite3"))

    async def initialize(self) -> None:
        """Migrate legacy scores as unreviewed; scores never imply human review."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(_CREATE_TABLE_SQL)
            async with db.execute("PRAGMA table_info(interactions)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            for column, declaration in _REVIEW_COLUMNS.items():
                if column not in columns:
                    await db.execute(f"ALTER TABLE interactions ADD COLUMN {column} {declaration}")
            await db.execute(
                "CREATE TABLE IF NOT EXISTS interaction_reviews ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, interaction_id INTEGER NOT NULL, "
                "reviewer_id TEXT NOT NULL, content_hash TEXT NOT NULL, "
                "accepted INTEGER NOT NULL, evidence TEXT NOT NULL, "
                "quality_score REAL NOT NULL, reviewed_at REAL NOT NULL)"
            )
            await db.commit()

    async def capture(
        self,
        prompt: str,
        response: str,
        provider: str,
        model: str,
        metadata: dict | None = None,
    ) -> None:
        """Record an unreviewed candidate; metadata cannot grant review approval."""
        from memory import stateless

        if not stateless.trains():
            return  # an evaluation run, or words a channel's terms keep out of training
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                _INSERT_SQL,
                (
                    prompt,
                    response,
                    provider,
                    model,
                    json.dumps(metadata or {}),
                    time.time(),
                ),
            )
            await db.commit()

    async def get_stats(self) -> dict:
        """Get interaction statistics grouped by provider."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(_STATS_BY_PROVIDER_SQL) as cursor:
                provider_rows = await cursor.fetchall()
            async with db.execute(_STATS_TOTAL_SQL) as cursor:
                total_row = await cursor.fetchone()

        from learner.data_export import DataExporter

        total = total_row[0] if total_row else 0
        return {
            "total_interactions": total,
            "by_provider": {row[1]: row[0] for row in provider_rows},
            "exportable_count": await DataExporter(self._db_path).count_exportable(),
            "last_export": None,
            "automatic_weight_training": False,
            "capture_status": "unreviewed_candidates",
            "export_kind": "reviewed_model_interactions",
            "original_data_eligible": False,
        }

    async def get_recent(self, limit: int = 50) -> list[dict]:
        """Retrieve the most recent interactions."""
        limit = max(0, min(limit, 200))
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(_RECENT_SQL, (limit,)) as cursor:
                rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "prompt": row[1],
                "response": row[2],
                "provider": row[3],
                "model": row[4],
                "quality_score": row[5],
                "created_at": row[6],
                "review_status": row[7],
                "reviewer_id": row[8],
                "reviewed_at": row[9],
                "review_evidence": row[10],
                "content_hash": content_hash(row[1], row[2], row[3], row[4]),
            }
            for row in rows
        ]

    async def update_quality(self, interaction_id: int, score: float) -> None:
        """A score change invalidates review; scoring alone cannot admit an export."""
        validate_quality(score)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_UPDATE_QUALITY_SQL, (score, interaction_id))
            await db.commit()

    async def review_interaction(
        self,
        interaction_id: int,
        *,
        reviewer_id: str,
        expected_hash: str,
        accepted: bool,
        evidence: str,
        quality_score: float,
    ) -> dict:
        """Review exact captured content; this never turns model output into gold.

        The caller must bind reviewer_id and the owner's database to the
        authenticated principal, never to model output or a request body.
        """
        validate_quality(quality_score)
        if not reviewer_id.strip() or not evidence.strip() or type(accepted) is not bool:
            raise ValueError("Authenticated reviewer, evidence and explicit verdict required")
        if len(evidence) > 4000:
            raise ValueError("Review evidence exceeds 4000 characters")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT prompt, response, provider, model FROM interactions WHERE id = ?",
                (interaction_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None or content_hash(*row) != expected_hash:
                raise ValueError("Interaction missing or review hash mismatch")
            status = "accepted" if accepted else "rejected"
            reviewed_at = time.time()
            await db.execute(
                "UPDATE interactions SET review_status = ?, reviewer_id = ?, "
                "reviewed_at = ?, review_evidence = ?, reviewed_content_hash = ?, "
                "quality_score = ? WHERE id = ?",
                (
                    status,
                    reviewer_id,
                    reviewed_at,
                    evidence.strip(),
                    expected_hash,
                    quality_score,
                    interaction_id,
                ),
            )
            await db.execute(
                "INSERT INTO interaction_reviews (interaction_id, reviewer_id, content_hash, "
                "accepted, evidence, quality_score, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    interaction_id,
                    reviewer_id,
                    expected_hash,
                    int(accepted),
                    evidence.strip(),
                    quality_score,
                    reviewed_at,
                ),
            )
            await db.commit()
        return {
            "id": interaction_id,
            "review_status": status,
            "content_hash": expected_hash,
            "original_data_eligible": False,
        }
