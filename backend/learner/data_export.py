"""Export explicitly reviewed model interactions, never original-data training gold."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite

from learner.review_contract import DEFAULT_MIN_QUALITY, content_hash, validate_quality

_EXPORT_SQL = (
    "SELECT id, prompt, response, provider, model, domain, quality_score, created_at, "
    "reviewer_id, reviewed_at, review_evidence, reviewed_content_hash FROM interactions "
    "WHERE quality_score >= ? AND review_status = 'accepted' "
    "AND provider NOT IN ('mizan-owned', 'mizan-support') ORDER BY id"
)


class DataExporter:
    """Exports reviewed candidates with provenance in a non-training schema.

    Captures remain model-authored after review. The export deliberately has no
    text/messages field accepted by the training pipelines. Independently
    sourced training records need their own authorship, rights and evaluation.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def records(self, min_quality: float = DEFAULT_MIN_QUALITY) -> AsyncIterator[dict]:
        """Yield accepted, hash-bound records; historical score-only rows are excluded."""
        validate_quality(min_quality)
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("PRAGMA table_info(interactions)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            # Direct use against a legacy store fails closed without altering it.
            if "reviewed_content_hash" not in columns:
                return
            db.row_factory = aiosqlite.Row
            async with db.execute(_EXPORT_SQL, (min_quality,)) as cursor:
                async for row in cursor:
                    expected = content_hash(
                        row["prompt"], row["response"], row["provider"], row["model"]
                    )
                    if (
                        row["reviewed_content_hash"] != expected
                        or not row["reviewer_id"]
                        or not row["review_evidence"]
                        or row["reviewed_at"] is None
                    ):
                        continue
                    yield self._build_entry(dict(row))

    async def export_jsonl(
        self,
        output_path: str,
        min_quality: float = DEFAULT_MIN_QUALITY,
    ) -> int:
        """Write reviewed candidate JSONL; returns the exported record count."""
        validate_quality(min_quality)
        self._validate_output_path(output_path)
        count = 0

        with open(output_path, "w", encoding="utf-8") as file_handle:
            async for entry in self.records(min_quality):
                file_handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                count += 1
        return count

    async def count_exportable(self, min_quality: float = DEFAULT_MIN_QUALITY) -> int:
        """Count records admitted by the same review gate used by export."""
        count = 0
        async for _ in self.records(min_quality):
            count += 1
        return count

    def _build_entry(self, row: dict) -> dict:
        return {
            "schema_version": 1,
            "record_type": "reviewed_model_interaction",
            "interaction_id": row["id"],
            "prompt": row["prompt"],
            "model_response": row["response"],
            "domain": row["domain"] or "conversation",
            "provenance": {
                "authorship": "model",
                "provider": row["provider"],
                "model": row["model"],
                "captured_at": row["created_at"],
                "content_hash": row["reviewed_content_hash"],
            },
            "review": {
                "status": "accepted",
                "reviewer_id": row["reviewer_id"],
                "reviewed_at": row["reviewed_at"],
                "evidence": row["review_evidence"],
                "quality_score": row["quality_score"],
            },
            "original_data_eligible": False,
            "independently_verified": False,
        }

    def _validate_output_path(self, output_path: str) -> None:
        """Ensure the output directory exists."""
        parent = Path(output_path).parent
        if not parent.exists():
            raise FileNotFoundError(f"Output directory does not exist: {parent}")
