"""Bab links: which outside account (a Telegram user) speaks for which MIZAN user.

A link is made only by the MIZAN user: they ask for a one-time code in MIZAN
and open it in the outside app, which sends it back. The code is 128 random
bits, stored only as its SHA-256, valid for 10 minutes and usable once.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

CODE_TTL = timedelta(minutes=10)


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class BabStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS links (
                    channel TEXT NOT NULL, external_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL, session_id TEXT NOT NULL, linked TEXT NOT NULL,
                    PRIMARY KEY (channel, external_id));
                CREATE UNIQUE INDEX IF NOT EXISTS links_owner ON links(channel, owner_id);
                CREATE TABLE IF NOT EXISTS codes (
                    digest TEXT PRIMARY KEY, owner_id TEXT NOT NULL, channel TEXT NOT NULL,
                    expires TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ── linking ──────────────────────────────────────────────────────────

    def new_code(self, owner: str, channel: str) -> str:
        code = secrets.token_urlsafe(16)  # 128 bits, URL- and deep-link-safe
        expires = (datetime.now(UTC) + CODE_TTL).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM codes WHERE owner_id = ? AND channel = ?", (owner, channel))
            conn.execute(
                "INSERT INTO codes VALUES (?,?,?,?,0)", (_digest(code), owner, channel, expires)
            )
        return code

    def redeem(self, code: str, channel: str, external_id: str, chat_id: str) -> str | None:
        """Link the sender to the code's owner; returns the owner, or None."""
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT owner_id, expires, used FROM codes WHERE digest = ? AND channel = ?",
                (_digest(code), channel),
            ).fetchone()
            if row is None or row["used"] or row["expires"] < now:
                return None
            conn.execute("UPDATE codes SET used = 1 WHERE digest = ?", (_digest(code),))
            owner = str(row["owner_id"])
            # One outside account per user per channel; relinking replaces the old one.
            conn.execute("DELETE FROM links WHERE channel = ? AND owner_id = ?", (channel, owner))
            conn.execute(
                "INSERT OR REPLACE INTO links VALUES (?,?,?,?,?,?)",
                (channel, external_id, owner, chat_id, _session(channel), now),
            )
            return owner

    def link(self, channel: str, external_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM links WHERE channel = ? AND external_id = ?", (channel, external_id)
            ).fetchone()
        return dict(row) if row else None

    def link_for_owner(self, channel: str, owner: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM links WHERE channel = ? AND owner_id = ?", (channel, owner)
            ).fetchone()
        return dict(row) if row else None

    def unlink(self, channel: str, owner: str) -> bool:
        with self._lock, self._connect() as conn:
            return (
                conn.execute(
                    "DELETE FROM links WHERE channel = ? AND owner_id = ?", (channel, owner)
                ).rowcount
                > 0
            )

    def new_session(self, channel: str, external_id: str) -> str:
        session = _session(channel)
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE links SET session_id = ? WHERE channel = ? AND external_id = ?",
                (session, channel, external_id),
            )
        return session

    # ── poll position ────────────────────────────────────────────────────

    def get(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else default

    def put(self, key: str, value: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )


def _session(channel: str) -> str:
    return f"{channel}-{uuid.uuid4().hex[:20]}"


_STORES: dict[str, BabStore] = {}


def store() -> BabStore:
    path = str(Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "bab.db")
    if path not in _STORES:
        _STORES[path] = BabStore(path)
    return _STORES[path]
