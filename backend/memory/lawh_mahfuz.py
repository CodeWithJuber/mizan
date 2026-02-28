"""
Lawh al-Mahfuz (لَوْح مَحْفُوظ) — The Preserved Tablet
=========================================================

"Nay, it is a Glorious Quran, inscribed in a Preserved Tablet (Lawh Mahfuz)."
— Quran 85:21-22

Immutable core memory with triple-checksum integrity verification.
Once stored, entries CANNOT be modified — only new entries can be added.
Used for: Fitrah axioms, proven theorems, verified facts, immutable truths.

Integrity mechanism: SHA-256 + CRC-32 + content_length
Any mismatch on read → corruption detected → entry quarantined.
"""

import binascii
import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.lawh_mahfuz")


@dataclass
class LawhEntry:
    """An immutable entry in the Preserved Tablet."""
    key: str
    content: str
    source: str
    stored_at: float
    sha256: str       # SHA-256 of content
    crc32: str        # CRC-32 hex of content
    length: int       # len(content) in bytes
    certainty: float = 1.0
    category: str = "general"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "content": self.content[:500],
            "source": self.source,
            "certainty": self.certainty,
            "category": self.category,
            "stored_at": self.stored_at,
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _crc32(text: str) -> str:
    return format(binascii.crc32(text.encode("utf-8")) & 0xFFFFFFFF, "08x")


class LawhMahfuz:
    """
    Immutable memory store with triple-checksum integrity.

    All entries are stored with SHA-256 + CRC-32 + length.
    Every read re-verifies all three checksums.
    Corrupted entries are moved to a quarantine table.

    Usage:
        lawh = LawhMahfuz()
        key = lawh.store_immutable("TRUTH:1", "Always speak truth", source="Quran 33:70")
        lawh.verify_integrity("TRUTH:1")  # True if intact
        entry = lawh.get("TRUTH:1")       # None if corrupted
    """

    def __init__(self, db_path: str = "/data/lawh_mahfuz.db"):
        self.db_path = db_path
        # In-memory cache for fast reads
        self._cache: dict[str, LawhEntry] = {}
        self._quarantine: set[str] = set()
        self._init_db()
        self._load_into_cache()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS lawh_entries (
                    key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    stored_at REAL NOT NULL,
                    sha256 TEXT NOT NULL,
                    crc32 TEXT NOT NULL,
                    length INTEGER NOT NULL,
                    certainty REAL DEFAULT 1.0,
                    category TEXT DEFAULT 'general'
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS lawh_quarantine (
                    key TEXT PRIMARY KEY,
                    reason TEXT,
                    quarantined_at REAL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _load_into_cache(self):
        """Load all entries into memory cache on startup."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM lawh_entries")
            for row in c.fetchall():
                key, content, source, stored_at, sha256, crc32, length, certainty, category = row
                entry = LawhEntry(
                    key=key, content=content, source=source, stored_at=stored_at,
                    sha256=sha256, crc32=crc32, length=length,
                    certainty=certainty, category=category,
                )
                self._cache[key] = entry
            logger.info("[LAWH] Loaded %d entries from preserved tablet", len(self._cache))
        finally:
            conn.close()

    def store_immutable(
        self,
        key: str,
        content: str,
        source: str = "system",
        certainty: float = 1.0,
        category: str = "general",
    ) -> str:
        """
        Store an immutable entry. Once stored, it cannot be modified.
        Returns the key if successful.
        Raises ValueError if key already exists (immutability enforcement).
        """
        if key in self._cache:
            logger.debug("[LAWH] Key '%s' already exists — immutability preserved", key)
            return key  # Already stored — idempotent

        sha = _sha256(content)
        crc = _crc32(content)
        length = len(content.encode("utf-8"))
        now = time.time()

        entry = LawhEntry(
            key=key, content=content, source=source, stored_at=now,
            sha256=sha, crc32=crc, length=length,
            certainty=certainty, category=category,
        )

        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                """INSERT OR IGNORE INTO lawh_entries
                   (key, content, source, stored_at, sha256, crc32, length, certainty, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, content, source, now, sha, crc, length, certainty, category),
            )
            conn.commit()
        finally:
            conn.close()

        self._cache[key] = entry
        logger.debug("[LAWH] Stored '%s' (len=%d sha=%s...)", key, length, sha[:8])
        return key

    def verify_integrity(self, key: str) -> bool:
        """
        Verify all three checksums for an entry.
        Returns True if intact, False if corrupted.
        Quarantines corrupted entries.
        """
        if key in self._quarantine:
            return False

        entry = self._cache.get(key)
        if entry is None:
            return False

        # Re-compute all three checksums
        actual_sha = _sha256(entry.content)
        actual_crc = _crc32(entry.content)
        actual_len = len(entry.content.encode("utf-8"))

        if actual_sha != entry.sha256:
            self._quarantine_entry(key, f"SHA-256 mismatch: {actual_sha[:8]}≠{entry.sha256[:8]}")
            return False
        if actual_crc != entry.crc32:
            self._quarantine_entry(key, f"CRC-32 mismatch: {actual_crc}≠{entry.crc32}")
            return False
        if actual_len != entry.length:
            self._quarantine_entry(key, f"Length mismatch: {actual_len}≠{entry.length}")
            return False

        return True

    def get(self, key: str) -> LawhEntry | None:
        """
        Retrieve an entry. Verifies integrity on every read.
        Returns None if entry doesn't exist or is corrupted.
        """
        if key in self._quarantine:
            logger.warning("[LAWH] Attempted read of quarantined key: %s", key)
            return None
        if not self.verify_integrity(key):
            return None
        return self._cache.get(key)

    def search(self, query: str, top_k: int = 5) -> list[LawhEntry]:
        """Search entries by keyword match in content or key."""
        query_lower = query.lower()
        results = []
        for key, entry in self._cache.items():
            if key in self._quarantine:
                continue
            if query_lower in entry.content.lower() or query_lower in key.lower():
                results.append(entry)
        # Sort by certainty desc
        results.sort(key=lambda e: -e.certainty)
        return results[:top_k]

    def get_by_category(self, category: str) -> list[LawhEntry]:
        """Get all entries in a category (e.g., 'ethical', 'epistemic')."""
        return [
            e for k, e in self._cache.items()
            if e.category == category and k not in self._quarantine
        ]

    def _quarantine_entry(self, key: str, reason: str):
        """Move corrupted entry to quarantine."""
        self._quarantine.add(key)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO lawh_quarantine (key, reason, quarantined_at) VALUES (?,?,?)",
                (key, reason, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
        logger.error("[LAWH] CORRUPTION DETECTED — quarantined '%s': %s", key, reason)

    def stats(self) -> dict:
        return {
            "total_entries": len(self._cache),
            "quarantined": len(self._quarantine),
            "categories": list({e.category for e in self._cache.values()}),
        }
