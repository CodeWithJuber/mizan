"""One-shot authenticated chat streams with bounded delivery and retry receipts.

POST streams are deliberately not replayed or resumed: clients use the same
request UUID to recover a receipt, then read owned chat history. The receipt is
durable, so a browser reconnect or backend restart cannot submit the same
model invocation twice. Only a digest of the request is stored here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from starlette.responses import StreamingResponse
from starlette.types import ASGIApp, Receive, Scope, Send

HEARTBEAT_SECONDS = 15.0
SEND_TIMEOUT_SECONDS = 20.0
MAX_QUEUED_EVENTS = 64
MAX_FRAME_BYTES = 128 * 1024
TEXT_CHUNK_CHARACTERS = 2048
MAX_RESPONSE_CHARACTERS = 1_000_000


class StreamDeliveryError(Exception):
    """A disconnected or excessively slow reader must not hold an agent open."""


@dataclass
class ChatRunLease:
    """A live local producer/transport pair, never an elapsed-time guess."""

    session_id: str
    request_id: str
    message_id: str
    status: str = "accepted"
    phase: str = "accepted"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started: float = field(default_factory=time.monotonic)
    provider_attempt_count: int | None = 0
    producer: asyncio.Task | None = None
    transport_finished: bool = False
    history_saved: bool | None = None

    def update(self, *, status: str | None = None, phase: str | None = None) -> None:
        if status is not None:
            self.status = status
        if phase is not None:
            self.phase = phase
        self.updated_at = datetime.now(UTC).isoformat()

    def public(self) -> dict:
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "message_id": self.message_id,
            "status": self.status,
            "phase": self.phase,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "elapsed_ms": round((time.monotonic() - self.started) * 1000, 1),
            "provider_attempt_count": self.provider_attempt_count,
        }

    @property
    def finished(self) -> bool:
        return self.transport_finished and (self.producer is None or self.producer.done())


class ChatStreamingResponse(StreamingResponse):
    """Bound transport writes and release capacity even before body iteration."""

    def __init__(
        self, *args: Any, release_stream: Callable[[], None] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._release_stream = release_stream

    async def close(self) -> None:
        try:
            close = getattr(self.body_iterator, "aclose", None)
            if close:
                await close()
        finally:
            if self._release_stream is not None:
                release, self._release_stream = self._release_stream, None
                release()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def bounded_send(message: Any) -> None:
            try:
                await asyncio.wait_for(send(message), timeout=SEND_TIMEOUT_SECONDS)
            except TimeoutError as exc:
                raise OSError("Chat transport exceeded the delivery deadline") from exc

        # With BaseHTTPMiddleware, this send may only rendezvous with an
        # internal memory-stream consumer. Timing that wait incorrectly kills
        # healthy clients while middleware is preparing/consuming a response.
        # The outer ASGI guard alone bounds the actual network write and owns
        # capacity until that transport and the app finish. Standalone callers
        # still need the response's own transport deadline.
        outer_guard = scope.get("mizan.chat_stream_guard")
        if outer_guard:
            scope["mizan.chat_stream_release"] = self._release_stream
            self._release_stream = None
        try:
            await super().__call__(scope, receive, send if outer_guard else bounded_send)
        finally:
            await self.close()


class ChatTransportGuard:
    """Bound the actual ASGI transport outside HTTP response-wrapping middleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/chat/stream"
        ):
            await self.app(scope, receive, send)
            return
        scope["mizan.chat_stream_guard"] = True

        async def bounded_send(message: Any) -> None:
            try:
                await asyncio.wait_for(send(message), timeout=SEND_TIMEOUT_SECONDS)
            except TimeoutError as exc:
                raise OSError("Chat transport exceeded the delivery deadline") from exc

        try:
            await self.app(scope, receive, bounded_send)
        finally:
            release = scope.pop("mizan.chat_stream_release", None)
            if release is not None:
                release()


class ChatStreamLedger:
    """Store idempotency receipts in the application's existing SQLite DB."""

    def __init__(
        self,
        get_connection: Callable[[], sqlite3.Connection],
        release_connection: Callable[[sqlite3.Connection], None],
    ):
        self._get_connection = get_connection
        self._release_connection = release_connection

    def claim(
        self, owner_id: str, request_id: str, session_id: str, message_id: str, payload: dict
    ) -> dict | None:
        """Atomically claim a UUID or return this owner's existing receipt."""
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        now = datetime.now(UTC).isoformat()
        conn = self._get_connection()
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS chat_stream_requests (
                    owner_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (owner_id, request_id)
                )"""
            )
            cursor = conn.execute(
                """INSERT OR IGNORE INTO chat_stream_requests VALUES
                   (?, ?, ?, ?, ?, 'accepted', ?, ?)""",
                (owner_id, request_id, session_id, message_id, fingerprint, now, now),
            )
            conn.commit()
            if cursor.rowcount:
                return None
            row = conn.execute(
                """SELECT session_id, message_id, status, fingerprint
                   FROM chat_stream_requests WHERE owner_id = ? AND request_id = ?""",
                (owner_id, request_id),
            ).fetchone()
            return {
                "session_id": row[0],
                "message_id": row[1],
                "status": row[2],
                "same_request": row[3] == fingerprint,
            }
        finally:
            self._release_connection(conn)

    def update(self, owner_id: str, request_id: str, status: str) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """UPDATE chat_stream_requests SET status = ?, updated_at = ?
                   WHERE owner_id = ? AND request_id = ?""",
                (status, datetime.now(UTC).isoformat(), owner_id, request_id),
            )
            conn.commit()
        finally:
            self._release_connection(conn)

    def run_state(self, owner_id: str, session_id: str, request_id: str | None = None) -> dict:
        """Read a receipt without recreating, resuming or retrying its work."""
        conn = self._get_connection()
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_stream_requests'"
            ).fetchone()
            if not exists:
                return {"state": "idle", "request": None, "history_saved": None}
            query = (
                "SELECT request_id, message_id, status, created_at, updated_at "
                "FROM chat_stream_requests WHERE owner_id = ? AND session_id = ?"
            )
            params = [owner_id, session_id]
            if request_id:
                query += " AND request_id = ?"
                params.append(request_id)
            row = conn.execute(query + " ORDER BY rowid DESC LIMIT 1", params).fetchone()
            if not row:
                return {"state": "idle", "request": None, "history_saved": None}
            history_saved = False
            attempt_count = None
            for (raw,) in conn.execute(
                "SELECT metadata FROM agent_messages WHERE session_id = ? AND role = 'assistant' "
                "AND CASE WHEN json_valid(metadata) THEN json_extract(metadata, '$.request_id') END = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (session_id, row[0]),
            ):
                try:
                    metadata = json.loads(raw or "{}")
                except (TypeError, ValueError):
                    continue
                if not isinstance(metadata, dict):
                    continue
                if metadata.get("request_id") == row[0]:
                    history_saved = True
                    usage = metadata.get("usage")
                    timings = usage.get("timings") if isinstance(usage, dict) else None
                    value = (
                        timings.get("provider_attempt_count") if isinstance(timings, dict) else None
                    )
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        attempt_count = value
                    break
            terminal = row[2] in {"complete", "error", "cancelled", "rejected"}
            elapsed = max(
                0.0,
                (datetime.fromisoformat(row[4]) - datetime.fromisoformat(row[3])).total_seconds()
                * 1000,
            )
            return {
                "state": "terminal" if terminal else "unknown",
                "request": {
                    "session_id": session_id,
                    "request_id": row[0],
                    "message_id": row[1],
                    "status": row[2],
                    "phase": "delivery" if terminal else "unknown",
                    "created_at": row[3],
                    "updated_at": row[4],
                    "elapsed_ms": round(elapsed, 1),
                    "provider_attempt_count": attempt_count,
                },
                "history_saved": history_saved if terminal or history_saved else None,
            }
        finally:
            self._release_connection(conn)


class ChatEventChannel:
    """Deliver only this request's events; no shared WebSocket subscriptions."""

    def __init__(self, *, session_id: str, message_id: str, request_id: str):
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)
        self.session_id = session_id
        self.message_id = message_id
        self.request_id = request_id
        self.sequence = 0
        self.closed = False

    async def emit(self, kind: str, **data: Any) -> None:
        if self.closed:
            raise StreamDeliveryError("Chat reader disconnected")
        payload = {
            **data,
            "type": kind,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "request_id": self.request_id,
        }
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        # A single terminal frame may contain the accumulated final response;
        # deltas, tools, and thinking events have a much smaller per-frame cap.
        limit = (
            MAX_RESPONSE_CHARACTERS * 6 + MAX_FRAME_BYTES
            if kind == "chat_complete"
            else MAX_FRAME_BYTES
        )
        if len(encoded.encode("utf-8")) > limit:
            raise StreamDeliveryError("Chat event exceeds the delivery limit")
        self.sequence += 1
        frame = f"id: {self.sequence}\nevent: {kind}\ndata: {encoded}\n\n"
        try:
            await asyncio.wait_for(self.queue.put(frame), timeout=SEND_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise StreamDeliveryError("Chat reader is too slow") from exc

    def close(self) -> None:
        self.closed = True
