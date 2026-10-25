"""Captures all LLM interactions for Ruh Model training data."""

import hashlib
import json
import os
import time
from pathlib import Path

import aiosqlite

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
    "SELECT id, prompt, response, provider, model, quality_score, created_at "
    "FROM interactions ORDER BY created_at DESC LIMIT ?"
)

_UPDATE_QUALITY_SQL = "UPDATE interactions SET quality_score = ? WHERE id = ?"


class RuhLearner:
    """Captures LLM request/response pairs for training the Ruh Model."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

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
        """Create the interactions table if it doesn't exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE_SQL)
            await db.commit()

    async def capture(
        self,
        prompt: str,
        response: str,
        provider: str,
        model: str,
        metadata: dict | None = None,
    ) -> None:
        """Record an LLM interaction for future training."""
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
            async with db.execute(
                "SELECT COUNT(*) FROM interactions WHERE quality_score >= 0.8 "
                "AND provider NOT IN ('mizan-owned', 'mizan-support')"
            ) as cursor:
                reviewed_row = await cursor.fetchone()

        total = total_row[0] if total_row else 0
        return {
            "total_interactions": total,
            "by_provider": {row[1]: row[0] for row in provider_rows},
            "exportable_count": reviewed_row[0] if reviewed_row else 0,
            "last_export": None,
            "automatic_weight_training": False,
            "capture_status": "unreviewed_candidates",
        }

    async def get_recent(self, limit: int = 50) -> list[dict]:
        """Retrieve the most recent interactions."""
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
            }
            for row in rows
        ]

    async def update_quality(self, interaction_id: int, score: float) -> None:
        """Update the quality score for an interaction."""
        if not 0.0 <= score <= 1.0:
            raise ValueError("Quality score must be between 0.0 and 1.0")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_UPDATE_QUALITY_SQL, (score, interaction_id))
            await db.commit()
