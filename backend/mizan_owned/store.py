"""User-scoped, hash-bound review ledger. Review is not a truth certificate."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


def canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class ReviewStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_hash TEXT NOT NULL,
                    request_json TEXT NOT NULL, answer TEXT NOT NULL, answer_hash TEXT NOT NULL,
                    origin TEXT NOT NULL, complete INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft', reviewer TEXT, evidence TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, owner TEXT NOT NULL, event TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_answer
                    ON proposals(owner, request_hash) WHERE status='accepted';
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, owner: str, request: dict, answer: str, origin: str, complete: bool) -> dict:
        if not owner or not answer.strip() or len(answer) > 100_000 or "\ufffd" in answer:
            raise ValueError("A scoped, nonempty, valid answer is required")
        pid = uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO proposals (id,owner,request_hash,request_json,answer,answer_hash,origin,complete) VALUES (?,?,?,?,?,?,?,?)",
                (
                    pid,
                    owner,
                    digest(request),
                    canonical(request),
                    answer,
                    digest(answer),
                    origin,
                    int(complete),
                ),
            )
            row = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        return dict(row)

    def list_proposals(self, owner: str) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM proposals WHERE owner=? ORDER BY rowid DESC LIMIT 100", (owner,)
                )
            ]

    def recall(self, owner: str, request: dict) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM proposals WHERE owner=? AND request_hash=? AND status='accepted'",
                (owner, digest(request)),
            ).fetchone()
            return dict(row) if row else None

    def review(
        self,
        owner: str,
        pid: str,
        *,
        reviewer: str,
        expected_hash: str,
        accepted: bool,
        evidence: str,
        supersedes: str | None = None,
    ) -> dict:
        if not reviewer or not evidence.strip() or type(accepted) is not bool:
            raise ValueError("Authenticated reviewer, evidence and explicit verdict required")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM proposals WHERE owner=? AND id=?", (owner, pid)
            ).fetchone()
            if not row or row["answer_hash"] != expected_hash:
                raise ValueError("Proposal missing or review hash mismatch")
            if accepted and not row["complete"]:
                raise ValueError("Incomplete generation cannot become a lesson")
            active = db.execute(
                "SELECT id FROM proposals WHERE owner=? AND request_hash=? AND status='accepted'",
                (owner, row["request_hash"]),
            ).fetchone()
            if accepted and active and active["id"] != pid:
                if supersedes != active["id"]:
                    raise ValueError("Conflicting answer requires explicit supersedes id")
                db.execute("UPDATE proposals SET status='superseded' WHERE id=?", (active["id"],))
            status = "accepted" if accepted else "rejected"
            db.execute(
                "UPDATE proposals SET status=?,reviewer=?,evidence=? WHERE id=?",
                (status, reviewer, evidence, pid),
            )
            db.execute(
                "INSERT INTO events(owner,event) VALUES (?,?)",
                (
                    owner,
                    canonical(
                        {
                            "proposal_id": pid,
                            "reviewer": reviewer,
                            "evidence": evidence,
                            "answer_hash": expected_hash,
                            "status": status,
                            "supersedes": supersedes,
                        }
                    ),
                ),
            )
        return {"id": pid, "status": status, "independently_verified": False}

    def retract(self, owner: str, evidence: str, reviewer: str) -> int:
        with self.connection() as db:
            count = db.execute(
                "UPDATE proposals SET status='retracted' WHERE owner=? AND evidence=? AND status='accepted'",
                (owner, evidence),
            ).rowcount
            db.execute(
                "INSERT INTO events(owner,event) VALUES (?,?)",
                (
                    owner,
                    canonical(
                        {
                            "retract_evidence": evidence,
                            "reviewer": reviewer,
                            "count": count,
                        }
                    ),
                ),
            )
            return int(count)

    def export_reviews(self, owner: str) -> list[dict]:
        """Reviewed memory, NOT original-data gold and NOT neural training records."""
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM proposals WHERE owner=? AND status='accepted' ORDER BY id",
                    (owner,),
                )
            ]
