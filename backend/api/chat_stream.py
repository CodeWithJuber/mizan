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
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

HEARTBEAT_SECONDS = 15.0
SEND_TIMEOUT_SECONDS = 20.0
MAX_QUEUED_EVENTS = 64
MAX_FRAME_BYTES = 128 * 1024
TEXT_CHUNK_CHARACTERS = 2048
MAX_RESPONSE_CHARACTERS = 1_000_000


class StreamDeliveryError(Exception):
    """A disconnected or excessively slow reader must not hold an agent open."""


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

        try:
            await super().__call__(scope, receive, bounded_send)
        finally:
            await self.close()


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
