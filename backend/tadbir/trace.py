"""Trace (أثر): a record of every step MIZAN takes for one request.

The debug mode (Muqabala) binds a trace for one run. While it is bound,
Tadbir records what Fahm understood, the agent Majlis chose, every tool
MIZAN ran, every Lisan prompt and reply, every model call with its usage,
and every Furqan verdict. Span operations follow the OpenTelemetry GenAI
names (``invoke_agent``, ``execute_tool``, ``chat``) with MIZAN's own
(``understand``, ``plan``, ``verify``, ``learn``).

With no trace bound every function here returns at once, so ordinary chats
pay nothing.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from agents.events import bounded

MAX_SPANS = 400


class Trace:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.spans: list[dict] = []

    def _now_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)

    def to_list(self) -> list[dict]:
        return [dict(span) for span in self.spans]


_trace: ContextVar[Trace | None] = ContextVar("mizan_trace", default=None)
_parent: ContextVar[str | None] = ContextVar("mizan_trace_parent", default=None)


@contextmanager
def bind() -> Iterator[Trace]:
    """Record this run's steps; the trace is complete when the block ends."""
    trace = Trace()
    token = _trace.set(trace)
    parent = _parent.set(None)
    try:
        yield trace
    finally:
        _parent.reset(parent)
        _trace.reset(token)


def active() -> bool:
    return _trace.get() is not None


def _add(trace: Trace, op: str, name: str, attributes: dict) -> dict | None:
    if len(trace.spans) >= MAX_SPANS:
        return None
    span = {
        "id": uuid.uuid4().hex[:12],
        "parent": _parent.get(),
        "op": op,
        "name": name,
        "start_ms": trace._now_ms(),
        "duration_ms": 0.0,
        "status": "ok",
        "attributes": bounded(attributes),
    }
    trace.spans.append(span)
    return span


@contextmanager
def span(op: str, name: str, **attributes: Any) -> Iterator[dict]:
    """A step with a duration. Add results to the yielded dict's ``attributes``."""
    trace = _trace.get()
    record = _add(trace, op, name, attributes) if trace is not None else None
    if record is None:
        yield {"attributes": {}}
        return
    token = _parent.set(record["id"])
    try:
        yield record
    except BaseException as exc:
        record["status"] = "error"
        record["attributes"]["error"] = type(exc).__name__
        raise
    finally:
        _parent.reset(token)
        record["duration_ms"] = round(trace._now_ms() - record["start_ms"], 1)  # type: ignore[union-attr]
        record["attributes"] = bounded(record["attributes"])


def event(op: str, name: str, **attributes: Any) -> None:
    """A step with no duration (a decision or a verdict)."""
    trace = _trace.get()
    if trace is not None:
        _add(trace, op, name, attributes)


_faults: ContextVar[dict[str, dict] | None] = ContextVar("mizan_tool_faults", default=None)


@contextmanager
def bind_faults(faults: dict[str, dict] | None) -> Iterator[None]:
    """Make named tools fail for this run only (the AGI test checks honesty under faults).

    A fault with ``times`` fails that many calls and then clears, so the test
    can see whether the agent recovers; without it the tool fails every time.
    """
    token = _faults.set({name: dict(spec) for name, spec in (faults or {}).items()} or None)
    try:
        yield
    finally:
        _faults.reset(token)


def injected_fault(tool: str) -> dict | None:
    """The failure result a bound fault gives for ``tool``, if any."""
    faults = _faults.get()
    if not faults or tool not in faults:
        return None
    spec = faults[tool]
    if "times" in spec:
        if int(spec["times"]) <= 0:
            return None
        spec["times"] = int(spec["times"]) - 1
    reason = str(spec.get("error") or "injected fault: the tool is unavailable")
    return {"error": reason, "exit_code": None, "injected_fault": True}


_fixtures: ContextVar[dict[str, dict] | None] = ContextVar("mizan_tool_fixtures", default=None)


@contextmanager
def bind_fixtures(fixtures: dict[str, dict] | None) -> Iterator[None]:
    """Pages the web tools return for this run only (deterministic agentic tests)."""
    token = _fixtures.set(fixtures or None)
    try:
        yield
    finally:
        _fixtures.reset(token)


def fixture(tool: str, params: dict) -> dict | None:
    """The bound page for a web tool call, if the test provides one."""
    pages = (_fixtures.get() or {}).get(tool)
    if not pages:
        return None
    if tool in ("web_browse", "web_read", "http_get"):
        url = str(params.get("url") or params.get("action") or "").strip().rstrip("/")
        for address, page in pages.items():
            if address.rstrip("/") == url:
                if isinstance(page, dict) and page.get("error"):
                    return {"error": page["error"], "url": url}
                content = page if isinstance(page, str) else str(page.get("content", ""))
                title = "" if isinstance(page, str) else str(page.get("title", ""))
                return {"url": url, "title": title, "content": content, "characters": len(content)}
        return {"error": "HTTP 404: page not found", "url": url}
    if tool == "web_search":
        query = str(params.get("query") or "").lower()
        for words, results in pages.items():
            if all(word in query for word in words.lower().split()):
                return {"query": query, "results": results}
        return {"query": query, "results": []}
    return None


def model_call(response: Any, latency_ms: float) -> None:
    """One observed model call: the model the provider reported and its usage."""
    trace = _trace.get()
    if trace is None:
        return
    from api.usage import build_usage_block

    block = build_usage_block({"response": response, "latency_ms": round(latency_ms, 1)})
    record = _add(trace, "chat", str(block.get("model") or "model"), block)
    if record is not None:
        record["start_ms"] = round(max(0.0, record["start_ms"] - latency_ms), 1)
        record["duration_ms"] = round(latency_ms, 1)
