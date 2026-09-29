"""Offline annotation store for the RootSpace Reader (use case #5).

``AnnotationStore`` persists per-word annotations built by
``annotator.annotate_text`` in SQLite and serves the
``(ref_id, word_index) -> annotation`` lookups a tap-any-word reader
needs on device.

Schema (v1):
* ``annotations(ref_id, word_index, surface, root, pattern, sense_id,
  sense_pending, confidence)`` -- ``PRIMARY KEY (ref_id, word_index)``.
* ``meta(key, value)`` -- ``schema_version``, ``created_at``,
  ``annotator_version``, and a beta note.

KB-scale: annotations are small fixed-shape rows (no embeddings, no
model weights). Measure, don't assume -- ``stats()`` reports row
counts and the on-disk byte size; see ``ruh_model/tests/test_reader.py``
for a measured sample.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

BETA_NOTE = (
    "BETA/UNVERIFIED: root/pattern are rule-based heuristics and "
    "per-occurrence senses are scholar-eval pending (see "
    "ruh_model/reader/annotator.py). Do not present as verified tafsir."
)

_DDL = """
CREATE TABLE IF NOT EXISTS annotations (
    ref_id       TEXT NOT NULL,
    word_index   INTEGER NOT NULL,
    surface      TEXT NOT NULL,
    root         TEXT NOT NULL DEFAULT '',
    pattern      TEXT NOT NULL DEFAULT '',
    sense_id     TEXT,
    sense_pending INTEGER NOT NULL DEFAULT 1,
    confidence   REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (ref_id, word_index)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_ANNOTATION_COLUMNS = (
    "ref_id",
    "word_index",
    "surface",
    "root",
    "pattern",
    "sense_id",
    "sense_pending",
    "confidence",
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class AnnotationStore:
    """SQLite-backed ``(ref_id, word_index) -> annotation`` lookup."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ------------------------------------------------------

    def open(self) -> AnnotationStore:
        """Open (creating parent dirs) and initialise the schema."""
        if self._conn is not None:
            return self
        if self._path.parent != Path("."):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_DDL)
        meta = dict(self._conn.execute("SELECT key, value FROM meta").fetchall())
        if "schema_version" not in meta:
            self._conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                [
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("created_at", _utcnow()),
                    ("beta_note", BETA_NOTE),
                ],
            )
            self._conn.commit()
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> AnnotationStore:
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _require_open(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("AnnotationStore is not open; call open() first")
        return self._conn

    # -- writes ----------------------------------------------------------

    def put(self, ref_id: str, annotation: dict[str, Any]) -> None:
        """Insert or replace one annotation for ``ref_id``."""
        self.put_many(ref_id, [annotation])

    def put_many(self, ref_id: str, annotations: list[dict[str, Any]]) -> int:
        """Insert or replace many annotations; returns rows written."""
        conn = self._require_open()
        rows = [
            (
                ref_id,
                int(a["word_index"]),
                str(a["surface"]),
                str(a.get("root", "")),
                str(a.get("pattern", "")),
                a.get("sense_id"),
                1 if a.get("sense_pending", True) else 0,
                float(a.get("confidence", 0.0)),
            )
            for a in annotations
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO annotations "
            "(ref_id, word_index, surface, root, pattern, sense_id, "
            "sense_pending, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        return len(rows)

    # -- reads -----------------------------------------------------------

    def get(self, ref_id: str, word_index: int) -> dict[str, Any] | None:
        """Fetch one annotation, or None when absent."""
        conn = self._require_open()
        row = conn.execute(
            "SELECT ref_id, word_index, surface, root, pattern, sense_id, "
            "sense_pending, confidence FROM annotations "
            "WHERE ref_id = ? AND word_index = ?",
            (ref_id, word_index),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_all(self, ref_id: str) -> list[dict[str, Any]]:
        """All annotations for ``ref_id`` ordered by ``word_index``."""
        conn = self._require_open()
        rows = conn.execute(
            "SELECT ref_id, word_index, surface, root, pattern, sense_id, "
            "sense_pending, confidence FROM annotations "
            "WHERE ref_id = ? ORDER BY word_index",
            (ref_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def refs(self) -> list[str]:
        """All stored ref_ids, sorted."""
        conn = self._require_open()
        return [
            r[0] for r in conn.execute("SELECT DISTINCT ref_id FROM annotations ORDER BY ref_id")
        ]

    # -- introspection ----------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Row counts plus the measured on-disk size (bytes)."""
        conn = self._require_open()
        n_words = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
        n_refs = conn.execute("SELECT COUNT(DISTINCT ref_id) FROM annotations").fetchone()[0]
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        db_bytes: int | None = None
        try:
            db_bytes = self._path.stat().st_size
        except OSError:
            db_bytes = None
        return {
            "schema_version": int(meta.get("schema_version", SCHEMA_VERSION)),
            "n_refs": n_refs,
            "n_words": n_words,
            "db_bytes": db_bytes,
            "db_path": str(self._path),
            "created_at": meta.get("created_at"),
            "beta_note": meta.get("beta_note", BETA_NOTE),
        }

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        record = dict(zip(_ANNOTATION_COLUMNS, row, strict=True))
        record["sense_pending"] = bool(record["sense_pending"])
        return record
