"""Elicitation: a connected server asks the person a question during a tool call.

The question reaches the live chat as an ``elicitation`` event; the person
answers with ``POST /api/chat/elicitations/{id}`` (accept with content, decline
or cancel). Pending answers are in-process futures owned by one user, like tool
approvals (:mod:`security.approvals`), so the backend keeps one worker. With no
one watching the run, MIZAN declines for the person.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

ACTIONS = ("accept", "decline", "cancel")
TIMEOUT_SECONDS = 300
MAX_PENDING = 200


@dataclass
class _Pending:
    user_id: str
    session_id: str
    server: str
    future: asyncio.Future
    created: float


class ElicitationBroker:
    def __init__(self) -> None:
        self._pending: dict[str, _Pending] = {}

    def open(self, user_id: str, session_id: str, server: str) -> tuple[str, asyncio.Future]:
        self._expire()
        elicitation_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[elicitation_id] = _Pending(user_id, session_id, server, future, time.time())
        return elicitation_id, future

    def resolve(
        self,
        user_id: str,
        elicitation_id: str,
        action: str,
        content: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> bool:
        """Deliver the owner's answer. ``session_id``, when the answer names its chat,
        must be the chat that asked: an answer given elsewhere is not this one's."""
        pending = self._pending.get(elicitation_id)
        if pending is None or pending.user_id != user_id or pending.future.done():
            return False
        if session_id is not None and pending.session_id != session_id:
            return False
        if action not in ACTIONS:
            return False
        pending.future.set_result({"action": action, "content": content or {}})
        return True

    def close(self, elicitation_id: str) -> None:
        pending = self._pending.pop(elicitation_id, None)
        if pending is not None and not pending.future.done():
            pending.future.cancel()

    def pending_for(self, user_id: str) -> list[dict]:
        return [
            {
                "id": key,
                "session_id": item.session_id,
                "server": item.server,
                "created_at": item.created,
            }
            for key, item in self._pending.items()
            if item.user_id == user_id and not item.future.done()
        ]

    def _expire(self) -> None:
        cutoff = time.time() - TIMEOUT_SECONDS * 2
        stale = [key for key, item in self._pending.items() if item.created < cutoff]
        if len(self._pending) - len(stale) > MAX_PENDING:
            oldest = sorted(self._pending, key=lambda key: self._pending[key].created)
            stale += oldest[: len(self._pending) - MAX_PENDING]
        for key in set(stale):
            self.close(key)


broker = ElicitationBroker()
