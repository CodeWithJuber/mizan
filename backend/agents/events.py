"""Structured agent activity events (tool calls, todos, approvals) for live UIs.

A transport that can deliver structured frames binds a sink for one run;
agents emit through it. Runs without a sink (REST, scheduler, queue) emit
nothing, so events never reach a connection that did not ask for them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("mizan.events")

EventSink = Callable[[str, dict], Awaitable[None]]

_sink: ContextVar[EventSink | None] = ContextVar("mizan_agent_event_sink", default=None)

# Frames stay well below the transport's per-event limit.
MAX_EVENT_BYTES = 96 * 1024
MAX_TEXT_CHARS = 32 * 1024
_SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|authorization|cookie)", re.I)


@contextmanager
def bind_event_sink(sink: EventSink | None) -> Iterator[None]:
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def has_event_sink() -> bool:
    return _sink.get() is not None


def bounded(value: Any, depth: int = 0) -> Any:
    """JSON-safe copy with secret-looking keys redacted and long text trimmed."""
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        return {
            str(key)[:80]: "[redacted]"
            if _SECRET_KEY.search(str(key))
            else bounded(item, depth + 1)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple)):
        items = [bounded(item, depth + 1) for item in list(value)[:200]]
        return items + (["…"] if len(value) > 200 else [])
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT_CHARS else value[:MAX_TEXT_CHARS] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


def summarize(value: Any, limit: int = 2000) -> str:
    try:
        text = json.dumps(bounded(value), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


async def emit(kind: str, payload: dict) -> None:
    """Deliver one event to the bound sink; delivery failures stop the run."""
    sink = _sink.get()
    if sink is None:
        return
    data = bounded(payload)
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
        data = {key: summarize(item, 4000) for key, item in data.items()}
    try:
        await sink(kind, data)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - an activity frame must not fail a tool
        logger.debug("Agent activity event %s was not delivered", kind, exc_info=True)
