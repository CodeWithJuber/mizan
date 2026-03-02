"""Export captured interactions as Bayan-tokenized JSONL for training."""

import json
from pathlib import Path

import aiosqlite

_EXPORT_SQL = (
    "SELECT prompt, response, provider, model, domain "
    "FROM interactions WHERE quality_score >= ?"
)

_COUNT_SQL = (
    "SELECT COUNT(*) FROM interactions WHERE quality_score >= ?"
)


class DataExporter:
    """Exports captured LLM interactions to training-ready JSONL."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def export_jsonl(
        self,
        output_path: str,
        min_quality: float = 0.0,
    ) -> int:
        """Export interactions as JSONL. Returns count of records exported."""
        self._validate_output_path(output_path)
        count = 0

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(_EXPORT_SQL, (min_quality,)) as cursor:
                with open(output_path, "w", encoding="utf-8") as file_handle:
                    async for row in cursor:
                        entry = self._build_entry(row)
                        file_handle.write(
                            json.dumps(entry, ensure_ascii=False) + "\n"
                        )
                        count += 1
        return count

    async def count_exportable(self, min_quality: float = 0.0) -> int:
        """Count interactions that meet the quality threshold."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(_COUNT_SQL, (min_quality,)) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else 0

    def _build_entry(self, row: tuple) -> dict:
        """Build a JSONL entry from a database row."""
        prompt, response, provider, model, domain = row
        return {
            "text": f"{prompt}\n{response}",
            "lang": "en",
            "domain": domain or "conversation",
            "source": f"{provider}/{model}",
        }

    def _validate_output_path(self, output_path: str) -> None:
        """Ensure the output directory exists."""
        parent = Path(output_path).parent
        if not parent.exists():
            raise FileNotFoundError(
                f"Output directory does not exist: {parent}"
            )
