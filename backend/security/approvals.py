"""Izn approvals for interactive chats: ask the user before acting.

A chat that can show prompts binds an :class:`ApprovalContext` with its
permission mode:

- ``auto``: run every permitted tool (no prompts).
- ``auto_edits``: private project edits run; commands, external writes and
  unknown tools wait for the user.
- ``ask``: every tool that changes something waits for the user.
- ``plan``: read-only tools only; changes are refused and proposed instead.

Runs no one is watching (watchers, schedules, triggers, the queue) bind a
*deferred* context: an action that needs a person is not run and not refused
for good, but held with its exact parameters in :class:`HeldActions`; the
owner allows or denies it later, and it then runs exactly once.

Pending decisions are in-process futures, so the backend must keep a single
worker process (``uvicorn --workers 1``).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
        # Shahid with nothing approved: every request that would change a page is held.
        "shahid_read",
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


# Send something to a site on the user's behalf (a form, an order): a person
# decides each time, whatever the chat's mode, and never with no one to ask.
ALWAYS_ASK_TOOLS = frozenset({"shahid_submit"})

# Runs inside MIZAN's isolated sandbox (no host access, egress allowlist):
# unattended runs may use it without a person present.
SANDBOXED_TOOLS = frozenset({"workspace_run"})


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
    # No one is watching this run: actions that need a person are held.
    deferred: bool = False
    origin: str = ""  # "watcher:<id>", "schedule", "trigger:<id>", "queue"
    # One call the owner already allowed (a held action): (tool, params digest).
    granted: tuple[str, str] | None = None

    def was_granted(self, tool_name: str, params: dict) -> bool:
        return self.granted == (tool_name, params_digest(params))

    def needs_approval(self, tool_name: str, read_only_hint: bool = False) -> bool:
        category = tool_category(tool_name, read_only_hint)
        if tool_name in ALWAYS_ASK_TOOLS:
            return True
        if category == "read" or tool_name in self.always:
            return False
        if self.deferred:
            # Unattended: private project edits and sandboxed runs go ahead;
            # anything else that acts on the world waits for the owner.
            return category == "execute" and tool_name not in SANDBOXED_TOOLS
        if self.mode == "auto":
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


# ── Held actions: decisions for runs no one is watching ──────────────────

HELD_TTL = timedelta(hours=24)


def params_digest(params: dict) -> str:
    return hashlib.sha256(
        json.dumps(params, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


class HeldActions:
    """Actions an unattended run wanted to take, waiting for their owner.

    Each is stored with the exact parameters and their SHA-256; a decision is
    accepted once, by the owner, before it expires, and only if the stored
    parameters still match their digest."""

    def __init__(self, path: str | None = None):
        directory = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan"))
        self.path = path or str(directory / "held_actions.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS held (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, origin TEXT NOT NULL,
                    session_id TEXT NOT NULL, tool TEXT NOT NULL, params TEXT NOT NULL,
                    params_sha256 TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL,
                    expires TEXT NOT NULL, status TEXT NOT NULL, decided TEXT,
                    decided_via TEXT, result TEXT);
                CREATE INDEX IF NOT EXISTS idx_held_owner ON held(owner_id, status);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            return conn.execute(sql, params).fetchall()

    def hold(self, context: ApprovalContext, tool: str, params: dict, reason: str = "") -> str:
        held_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        self._run(
            "INSERT INTO held (id, owner_id, origin, session_id, tool, params, params_sha256, "
            "reason, created, expires, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (held_id, context.user_id, context.origin or "unattended", context.session_id, tool,
             json.dumps(params, ensure_ascii=False, default=str), params_digest(params),
             reason[:300], now.isoformat(), (now + HELD_TTL).isoformat()),
        )  # fmt: skip
        return held_id

    @staticmethod
    def _public(row: sqlite3.Row) -> dict:
        item = dict(row)
        item["params"] = json.loads(item["params"])
        item["result"] = json.loads(item["result"]) if item.get("result") else None
        return item

    def get(self, owner_id: str, held_id: str) -> dict | None:
        rows = self._run("SELECT * FROM held WHERE id = ? AND owner_id = ?", (held_id, owner_id))
        return self._public(rows[0]) if rows else None

    def pending(self, owner_id: str) -> list[dict]:
        now = datetime.now(UTC).isoformat()
        rows = self._run(
            "SELECT * FROM held WHERE owner_id = ? AND status = 'pending' AND expires > ? "
            "ORDER BY created DESC LIMIT 100",
            (owner_id, now),
        )
        return [self._public(row) for row in rows]

    def claim(self, owner_id: str, held_id: str, decision: str, via: str = "web") -> dict | None:
        """Take one pending action for a decision (allow | deny), at most once."""
        if decision not in {"allow", "deny"}:
            return None
        now = datetime.now(UTC)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM held WHERE id = ? AND owner_id = ? AND status = 'pending'",
                (held_id, owner_id),
            ).fetchone()
            if row is None or row["expires"] <= now.isoformat():
                return None
            if params_digest(json.loads(row["params"])) != row["params_sha256"]:
                return None  # changed after it was held: never run it
            status = "allowed" if decision == "allow" else "denied"
            updated = conn.execute(
                "UPDATE held SET status = ?, decided = ?, decided_via = ? "
                "WHERE id = ? AND status = 'pending'",
                (status, now.isoformat(), via, held_id),
            ).rowcount
            if not updated:
                return None
        return {**self._public(row), "status": status}

    def finish(self, held_id: str, result: dict) -> None:
        self._run(
            "UPDATE held SET status = 'done', result = ? WHERE id = ?",
            (json.dumps(result, ensure_ascii=False, default=str)[:20000], held_id),
        )


_HELD_STORES: dict[str, HeldActions] = {}


def held_store() -> HeldActions:
    path = str(Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "held_actions.db")
    if path not in _HELD_STORES:
        _HELD_STORES[path] = HeldActions(path)
    return _HELD_STORES[path]


_collected: ContextVar[list[dict] | None] = ContextVar("mizan_held_in_run", default=None)


@contextmanager
def collecting_held() -> Iterator[list[dict]]:
    """Collect the actions held while this block runs (shared with child tasks)."""
    found: list[dict] = []
    token = _collected.set(found)
    try:
        yield found
    finally:
        _collected.reset(token)


def hold_action(context: ApprovalContext, tool: str, params: dict, reason: str = "") -> str:
    held_id = held_store().hold(context, tool, params, reason)
    found = _collected.get()
    if found is not None:
        found.append({"id": held_id, "tool": tool, "reason": reason})
    return held_id


@contextmanager
def unattended(owner_id: str, session_id: str, origin: str) -> Iterator[ApprovalContext]:
    """Bind a deferred approval context for a run no one is watching."""
    context = ApprovalContext(owner_id, session_id, "ask", deferred=True, origin=origin)
    with bind_approvals(context):
        yield context
