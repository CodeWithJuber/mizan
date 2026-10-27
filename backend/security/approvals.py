"""Izn approvals for interactive chats: ask the user before acting.

A chat that can show prompts binds an :class:`ApprovalContext` with its
permission mode:

- ``auto``: run every permitted tool (no prompts).
- ``auto_edits``: private project edits run; commands, external writes and
  unknown tools wait for the user.
- ``ask``: every tool that changes something waits for the user.
- ``plan``: read-only tools only; changes are refused and proposed instead.

Runs without a context (REST, scheduler, queue) keep the legacy behaviour.
Pending decisions are in-process futures, so the backend must keep a single
worker process (``uvicorn --workers 1``).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

MODES = ("auto", "auto_edits", "ask", "plan")
APPROVAL_TIMEOUT_SECONDS = 600

# Tools that only observe. Everything else may change state.
READ_ONLY_TOOLS = frozenset(
    {
        "mizan_discover_tools",
        "recall_memory",
        "query_knowledge",
        "disambiguate_sense",
        "compact_context",
        "todo_write",
        "web_browse",
        "web_search",
        "workspace_list",
        "workspace_tree",
        "workspace_read",
        "workspace_glob",
        "workspace_grep",
        "workspace_diff",
        "activate_skill",
        "read_skill_file",
        "list_files",
        "read_file",
        "http_get",
    }
)
# Private, checkpointed project edits (auto in ``auto_edits`` mode).
EDIT_TOOLS = frozenset(
    {
        "workspace_create",
        "workspace_write",
        "workspace_edit",
        "workspace_checkpoint",
        "workspace_artifact",
    }
)


def tool_category(tool_name: str, read_only_hint: bool = False) -> str:
    if tool_name in READ_ONLY_TOOLS or read_only_hint:
        return "read"
    if tool_name in EDIT_TOOLS:
        return "edit"
    return "execute"


@dataclass
class ApprovalContext:
    user_id: str
    session_id: str
    mode: str = "auto_edits"
    always: set[str] = field(default_factory=set)

    def needs_approval(self, tool_name: str, read_only_hint: bool = False) -> bool:
        category = tool_category(tool_name, read_only_hint)
        if category == "read" or self.mode == "auto" or tool_name in self.always:
            return False
        if self.mode == "auto_edits":
            return category == "execute"
        return True  # ask; plan is refused before reaching here

    def blocks(self, tool_name: str, read_only_hint: bool = False) -> bool:
        return self.mode == "plan" and tool_category(tool_name, read_only_hint) != "read"


_context: ContextVar[ApprovalContext | None] = ContextVar("mizan_approval_context", default=None)


@contextmanager
def bind_approvals(context: ApprovalContext | None) -> Iterator[None]:
    token = _context.set(context)
    try:
        yield
    finally:
        _context.reset(token)


def current_approvals() -> ApprovalContext | None:
    return _context.get()


@dataclass
class _Pending:
    user_id: str
    session_id: str
    tool: str
    future: asyncio.Future
    created: float


class ApprovalBroker:
    """Owner-scoped pending decisions keyed by an unguessable approval id."""

    def __init__(self) -> None:
        self._pending: dict[str, _Pending] = {}

    def open(self, context: ApprovalContext, tool: str) -> tuple[str, asyncio.Future]:
        approval_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[approval_id] = _Pending(
            context.user_id, context.session_id, tool, future, time.time()
        )
        return approval_id, future

    def resolve(self, user_id: str, approval_id: str, decision: str) -> bool:
        pending = self._pending.get(approval_id)
        if pending is None or pending.user_id != user_id or pending.future.done():
            return False
        if decision not in {"allow", "deny", "always"}:
            return False
        pending.future.set_result(decision)
        return True

    def close(self, approval_id: str) -> None:
        pending = self._pending.pop(approval_id, None)
        if pending is not None and not pending.future.done():
            pending.future.cancel()

    def pending_for(self, user_id: str) -> list[dict]:
        return [
            {
                "approval_id": approval_id,
                "session_id": item.session_id,
                "tool": item.tool,
                "created_at": item.created,
            }
            for approval_id, item in self._pending.items()
            if item.user_id == user_id and not item.future.done()
        ]


broker = ApprovalBroker()


async def request_approval(
    context: ApprovalContext,
    tool_name: str,
    params: dict,
    *,
    reason: str = "",
    timeout: float | None = None,
) -> str:
    """Ask the user through the run's event sink; returns allow | deny | always."""
    from agents.events import emit, has_event_sink

    if not has_event_sink():
        return "deny"
    timeout = APPROVAL_TIMEOUT_SECONDS if timeout is None else timeout
    approval_id, future = broker.open(context, tool_name)
    try:
        await emit(
            "approval_request",
            {
                "approval_id": approval_id,
                "tool": tool_name,
                "input": params,
                "category": tool_category(tool_name),
                "reason": reason,
                "expires_in": int(timeout),
            },
        )
        try:
            decision = str(await asyncio.wait_for(future, timeout=timeout))
        except TimeoutError:
            decision = "deny"
        if decision == "always":
            context.always.add(tool_name)
        await emit("approval_resolved", {"approval_id": approval_id, "decision": decision})
        return decision
    finally:
        broker.close(approval_id)
