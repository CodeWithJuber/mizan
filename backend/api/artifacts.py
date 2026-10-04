"""Chat Artifacts API — versioned agent-produced documents (code / HTML / docs).

JEV-LOCKED: Artifacts = HYBRID — Sandpack for code + locked-down iframe
for HTML/docs. This module is the persistence + HTTP layer behind that.

Routes (all JWT-gated):

    POST /api/artifacts/               create {session_id, title, kind, content, language?}
                                       -> 201 {id, version: 1}
    POST /api/artifacts/{id}/versions  append a new version {content, title?}
                                       -> {id, version: N}
    GET  /api/artifacts/{id}           artifact + latest content (404 if missing/unowned)
    GET  /api/artifacts/{id}/versions  version history, oldest first
    GET  /api/artifacts/               list own artifacts (?session_id=, ?limit=)

Storage choice (documented per ticket): extend the Dhikr SQLite database —
same DB file (``DB_PATH`` env or ``backend/data/mizan_memory.db``), two NEW
tables ``artifacts`` + ``artifact_versions``. One database file keeps the
backup story simple; the tables are namespaced so dhikr is untouched.

Privacy: every row carries the authenticated user's ``user_id``
(``TokenPayload.user_id``). All reads/writes filter on it. Accessing another
user's artifact returns 404 (not 403) so existence is not leaked.

Auth note: ``require_auth`` below DELEGATES to ``backend.api.main.require_auth``
at request time (resolved from ``sys.modules``). A module-level
``from backend.api.main import require_auth`` would be circular — main.py
mounts this router — so the real function is looked up per request, when main
is fully loaded. Semantics (401 on missing/invalid token, request role
binding) are therefore identical to every other protected route.

Frontend convention (handled in ``App.tsx`` ``handleWsMessage``): when the
agent pipeline creates an artifact it persists via ``create_artifact()``
below and then emits over the chat WebSocket::

    {"type": "artifact",
     "artifact": {"id": ..., "session_id": ..., "title": ...,
                  "kind": "code|html|markdown", "language": ...,
                  "content": ..., "version": 1, "created_at": ...}}

``App.tsx`` keeps the artifact in panel state (toast on arrival); version
history / restore go through the HTTP routes above.
"""

from __future__ import annotations

import base64
import io
import os
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from security.auth import TokenPayload

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

# Mirrors backend/api/main.py::_default_path("DB_PATH", "mizan_memory.db")
# without importing main (circular). Env override wins; otherwise the file
# inside the backend package data dir.
_PACKAGE_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _db_path() -> str:
    explicit = os.getenv("DB_PATH")
    if explicit:
        return explicit
    _PACKAGE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(_PACKAGE_DATA_DIR / "mizan_memory.db")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def validate_image(content: str) -> None:
    """Accept decoded raster images only; never accept SVG or external image URLs."""
    try:
        header, encoded = content.split(",", 1)
        formats = {
            "data:image/png;base64": "PNG",
            "data:image/jpeg;base64": "JPEG",
            "data:image/webp;base64": "WEBP",
        }
        expected = formats.get(header)
        if expected is None or len(content) > 500000:
            raise ValueError("Unsupported or oversized image")
        data = base64.b64decode(encoded, validate=True)
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.format != expected or image.width * image.height > 16000000:
                raise ValueError("Invalid image format or dimensions")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except ImportError:
        raise HTTPException(503, "Image support requires the Pillow runtime dependency") from None
    except Exception as exc:
        raise HTTPException(
            422, "A valid PNG, JPEG or WebP image up to 500000 encoded characters is required"
        ) from exc


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    """Idempotent schema — safe to run on every operation."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            language TEXT,
            current_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_artifacts_user_session
            ON artifacts (user_id, session_id);
        CREATE TABLE IF NOT EXISTS artifact_versions (
            artifact_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (artifact_id, version),
            FOREIGN KEY (artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE
        );
        """
    )


# ---------------------------------------------------------------------------
# Auth — deferred delegation to main.require_auth (see module docstring)
# ---------------------------------------------------------------------------


async def require_auth(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> TokenPayload:
    """JWT gate delegating to ``backend.api.main.require_auth``.

    Resolved from ``sys.modules`` at request time (main is fully loaded by
    then); raises 500 only if the main app was never imported, which cannot
    happen in production or in the full-app test path.
    """
    for mod_name in ("backend.api.main", "api.main"):
        mod = sys.modules.get(mod_name)
        delegate = getattr(mod, "require_auth", None) if mod is not None else None
        if delegate is not None:
            return await delegate(authorization=authorization, x_api_key=x_api_key)
    raise HTTPException(status_code=500, detail="Auth subsystem not initialised")


# ---------------------------------------------------------------------------
# Storage layer (also importable by the agent pipeline for WS-driven creates)
# ---------------------------------------------------------------------------


def create_artifact(
    *,
    user_id: str,
    session_id: str,
    title: str,
    kind: str,
    content: str,
    language: str | None = None,
) -> dict:
    """Persist a new artifact (version 1). Returns {id, version}."""
    if kind == "image":
        validate_image(content)
    artifact_id = uuid.uuid4().hex
    now = _utcnow()
    conn = _connect()
    try:
        _init_tables(conn)
        conn.execute(
            """
            INSERT INTO artifacts
                (id, user_id, session_id, title, kind, language,
                 current_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (artifact_id, user_id, session_id, title, kind, language, now, now),
        )
        conn.execute(
            """
            INSERT INTO artifact_versions
                (artifact_id, version, user_id, title, content, created_at)
            VALUES (?, 1, ?, ?, ?, ?)
            """,
            (artifact_id, user_id, title, content, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": artifact_id, "version": 1}


def add_artifact_version(
    *,
    user_id: str,
    artifact_id: str,
    content: str,
    title: str | None = None,
) -> dict | None:
    """Append a version. Returns {id, version}, or None if missing/unowned."""
    now = _utcnow()
    conn = _connect()
    try:
        _init_tables(conn)
        row = conn.execute(
            "SELECT current_version, title, kind FROM artifacts WHERE id = ? AND user_id = ?",
            (artifact_id, user_id),
        ).fetchone()
        if row is None:
            return None
        if row["kind"] == "image":
            validate_image(content)
        new_version = int(row["current_version"]) + 1
        new_title = title if title is not None else row["title"]
        conn.execute(
            "UPDATE artifacts SET current_version = ?, title = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (new_version, new_title, now, artifact_id, user_id),
        )
        conn.execute(
            """
            INSERT INTO artifact_versions
                (artifact_id, version, user_id, title, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (artifact_id, new_version, user_id, new_title, content, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": artifact_id, "version": new_version}


def get_artifact(*, user_id: str, artifact_id: str) -> dict | None:
    """Artifact with its latest content, or None if missing/unowned."""
    conn = _connect()
    try:
        _init_tables(conn)
        art = conn.execute(
            "SELECT * FROM artifacts WHERE id = ? AND user_id = ?",
            (artifact_id, user_id),
        ).fetchone()
        if art is None:
            return None
        ver = conn.execute(
            "SELECT content, created_at FROM artifact_versions "
            "WHERE artifact_id = ? AND version = ?",
            (artifact_id, int(art["current_version"])),
        ).fetchone()
    finally:
        conn.close()
    return {
        "id": art["id"],
        "session_id": art["session_id"],
        "title": art["title"],
        "kind": art["kind"],
        "language": art["language"],
        "version": int(art["current_version"]),
        "content": ver["content"] if ver else "",
        "created_at": art["created_at"],
        "updated_at": art["updated_at"],
    }


def list_artifact_versions(*, user_id: str, artifact_id: str) -> list[dict] | None:
    """Version history oldest-first, or None if missing/unowned."""
    conn = _connect()
    try:
        _init_tables(conn)
        art = conn.execute(
            "SELECT id FROM artifacts WHERE id = ? AND user_id = ?",
            (artifact_id, user_id),
        ).fetchone()
        if art is None:
            return None
        rows = conn.execute(
            "SELECT version, title, content, created_at FROM artifact_versions "
            "WHERE artifact_id = ? ORDER BY version ASC",
            (artifact_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "version": int(r["version"]),
            "title": r["title"],
            "content": r["content"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def list_artifacts(*, user_id: str, session_id: str | None = None, limit: int = 50) -> list[dict]:
    """Own artifacts, newest first (optionally filtered to a session)."""
    conn = _connect()
    try:
        _init_tables(conn)
        if session_id:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE user_id = ? AND session_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (user_id, session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "title": r["title"],
            "kind": r["kind"],
            "language": r["language"],
            "version": int(r["current_version"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


class ArtifactKind(StrEnum):
    code = "code"
    html = "html"
    markdown = "markdown"
    image = "image"


class ArtifactCreate(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    kind: ArtifactKind
    content: str = Field(..., min_length=1, max_length=500_000)
    language: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_content(self):
        if self.kind == ArtifactKind.image:
            validate_image(self.content)
        return self


class ArtifactVersionCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)
    title: str | None = Field(default=None, min_length=1, max_length=200)


def _not_found() -> HTTPException:
    # 404 (not 403) for missing OR unowned — no existence leak.
    return HTTPException(status_code=404, detail="Artifact not found")


@router.post("/", status_code=201)
def create_artifact_route(body: ArtifactCreate, user: TokenPayload = Depends(require_auth)) -> dict:
    return create_artifact(
        user_id=user.user_id,
        session_id=body.session_id,
        title=body.title,
        kind=body.kind.value,
        content=body.content,
        language=body.language,
    )


@router.post("/{artifact_id}/versions")
def add_version_route(
    artifact_id: str,
    body: ArtifactVersionCreate,
    user: TokenPayload = Depends(require_auth),
) -> dict:
    res = add_artifact_version(
        user_id=user.user_id,
        artifact_id=artifact_id,
        content=body.content,
        title=body.title,
    )
    if res is None:
        raise _not_found()
    return res


@router.get("/{artifact_id}")
def get_artifact_route(artifact_id: str, user: TokenPayload = Depends(require_auth)) -> dict:
    art = get_artifact(user_id=user.user_id, artifact_id=artifact_id)
    if art is None:
        raise _not_found()
    return art


@router.get("/{artifact_id}/versions")
def list_versions_route(artifact_id: str, user: TokenPayload = Depends(require_auth)) -> list[dict]:
    versions = list_artifact_versions(user_id=user.user_id, artifact_id=artifact_id)
    if versions is None:
        raise _not_found()
    return versions


@router.get("/")
def list_artifacts_route(
    user: TokenPayload = Depends(require_auth),
    session_id: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    return list_artifacts(user_id=user.user_id, session_id=session_id, limit=limit)
