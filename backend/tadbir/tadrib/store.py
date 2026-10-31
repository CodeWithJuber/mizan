"""Each person's lessons: what MIZAN's own models learned from their work.

One SQLite file per person, ``private/<sha256(owner)>/tadrib.sqlite3`` (the
folder Mahw erases from). A row keeps the words, because a lesson must be
replayed to rebuild a model without another one; it is deleted with its chat
(Mahw) or when the person rejects it.

Statuses: ``pending`` (waiting for the trainer), ``learned``, ``held_out``
(never learned, kept as test). A pending lesson the trainer turns down
(Lughah and the reader read it differently) is deleted: only what was
learned or held out is listed. ``consolidated``: a night made it part of the
slow weights.

The functions take the person (``owner``); the ``*_at`` ones take the file,
for the trainer, which finds every person's file without knowing who they are.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

FILE = "tadrib.sqlite3"
STATUSES = ("pending", "learned", "held_out")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    digest TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    verifier TEXT NOT NULL,
    created TEXT NOT NULL,
    status TEXT NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS lessons_chat ON lessons (chat_id);
CREATE INDEX IF NOT EXISTS lessons_created ON lessons (created, digest);
"""
_COLUMNS = "digest, chat_id, kind, language, text, verifier, created, status, consolidated"


@dataclass(frozen=True)
class Lesson:
    digest: str
    chat_id: str
    kind: str
    language: str
    text: str
    verifier: str
    created: str
    status: str
    consolidated: bool

    def view(self) -> dict:
        """What the person sees of a lesson in a listing."""
        return {
            "digest": self.digest,
            "chat_id": self.chat_id,
            "kind": self.kind,
            "language": self.language,
            "text": self.text,
            "verifier": self.verifier,
            "created": self.created,
            "status": self.status,
            "consolidated": self.consolidated,
        }


def path_of(owner: str) -> Path:
    from memory.mahw import private_dir

    return Path(private_dir(owner)) / FILE


@contextmanager
def _open(path: Path, create: bool = False) -> Iterator[sqlite3.Connection | None]:
    if not path.exists() and not create:
        yield None
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row(row: Sequence) -> Lesson:
    digest, chat_id, kind, language, text, verifier, created, status, consolidated = row
    return Lesson(
        str(digest),
        str(chat_id),
        str(kind),
        str(language),
        str(text),
        str(verifier),
        str(created),
        str(status),
        bool(consolidated),
    )


def _select(path: Path, where: str, params: Sequence = ()) -> list[Lesson]:
    with _open(path) as conn:
        if conn is None:
            return []
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM lessons WHERE {where}",  # noqa: S608 - fixed clauses
            tuple(params),
        ).fetchall()
    return [_row(row) for row in rows]


# ── by file (the trainer) ────────────────────────────────────────────────


def get_at(path: Path, digest: str) -> Lesson | None:
    found = _select(path, "digest = ?", (digest,))
    return found[0] if found else None


def settle_at(path: Path, digest: str, status: str, language: str) -> bool:
    """A pending lesson learned or held out, in the language it was read in;
    False when it is no longer pending (erased or rejected meanwhile)."""
    if status not in STATUSES[1:]:
        raise ValueError(f"not a settled status: {status}")
    with _open(path) as conn:
        if conn is None:
            return False
        cursor = conn.execute(
            "UPDATE lessons SET status = ?, language = ? WHERE digest = ? AND status = 'pending'",
            (status, language, digest),
        )
        return cursor.rowcount > 0


def drop_at(path: Path, digest: str) -> bool:
    with _open(path) as conn:
        if conn is None:
            return False
        return conn.execute("DELETE FROM lessons WHERE digest = ?", (digest,)).rowcount > 0


def pending_at(path: Path) -> list[Lesson]:
    return _select(path, "status = 'pending' ORDER BY created, digest")


def unconsolidated_at(path: Path, kind: str) -> list[Lesson]:
    """Learned lessons a night has not yet made part of the slow weights, oldest first."""
    return _select(
        path,
        "kind = ? AND status = 'learned' AND consolidated = 0 ORDER BY created, digest",
        (kind,),
    )


def owners_with_lessons() -> list[Path]:
    """Every person's lesson file (the trainer rebuilds from all of them)."""
    from memory.mahw import _data_dir

    root = _data_dir() / "private"
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob(f"*/{FILE}") if path.is_file())


# ── by person ────────────────────────────────────────────────────────────


def add(owner: str, digest: str, chat_id: str, kind: str, text: str, verifier: str) -> bool:
    """Keep a new pending lesson; False when the same words are already one."""
    with _open(path_of(owner), create=True) as conn:
        assert conn is not None
        cursor = conn.execute(
            "INSERT OR IGNORE INTO lessons (digest, chat_id, kind, text, verifier, created, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (digest, chat_id, kind, text, verifier, datetime.now(UTC).isoformat()),
        )
        return cursor.rowcount > 0


def get(owner: str, digest: str) -> Lesson | None:
    return get_at(path_of(owner), digest)


def settle(owner: str, digest: str, status: str, language: str) -> bool:
    return settle_at(path_of(owner), digest, status, language)


def drop(owner: str, digest: str) -> bool:
    """Delete one lesson (turned down, or rejected by the person)."""
    return drop_at(path_of(owner), digest)


def drop_chat(owner: str, chat_id: str) -> list[str]:
    """Delete a chat's lessons (Mahw); the digests of those that were deleted."""
    with _open(path_of(owner)) as conn:
        if conn is None:
            return []
        digests = [
            row[0]
            for row in conn.execute("SELECT digest FROM lessons WHERE chat_id = ?", (chat_id,))
        ]
        conn.execute("DELETE FROM lessons WHERE chat_id = ?", (chat_id,))
    return digests


def listing(owner: str, limit: int = 50, offset: int = 0) -> tuple[list[Lesson], int]:
    """The person's learned and held-out lessons, newest first, and how many there are."""
    path = path_of(owner)
    with _open(path) as conn:
        if conn is None:
            return [], 0
        total = conn.execute("SELECT COUNT(*) FROM lessons WHERE status != 'pending'").fetchone()[0]
    found = _select(
        path,
        "status != 'pending' ORDER BY created DESC, digest LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return found, int(total)


def pending(owner: str) -> list[Lesson]:
    return pending_at(path_of(owner))


def unconsolidated(owner: str, kind: str) -> list[Lesson]:
    return unconsolidated_at(path_of(owner), kind)


def learned_digests(owner: str, kind: str) -> set[str]:
    """The digests of the person's lessons of this kind that are learned."""
    return {
        lesson.digest
        for lesson in _select(path_of(owner), "kind = ? AND status = 'learned'", (kind,))
    }


def consolidate(owner: str, digests: Sequence[str]) -> int:
    with _open(path_of(owner)) as conn:
        if conn is None or not digests:
            return 0
        return sum(
            conn.execute("UPDATE lessons SET consolidated = 1 WHERE digest = ?", (digest,)).rowcount
            for digest in digests
        )


def counts(owner: str) -> dict[str, int]:
    with _open(path_of(owner)) as conn:
        if conn is None:
            return {}
        return {
            status: int(n)
            for status, n in conn.execute("SELECT status, COUNT(*) FROM lessons GROUP BY status")
        }
