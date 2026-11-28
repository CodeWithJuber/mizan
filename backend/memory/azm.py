"""'Azm (عزم): what was decided, and where the work stands.

"And when you have decided, put your trust in Allah" (3:159): a decision is
made once and then acted on, not made again each time the question comes back.
Two stores serve that, per person, in ``private/<sha256(owner)>/azm.sqlite3``:

- **Decisions**: an append-only log of what the person decided and why, with
  the chat (and the project or agent, if any) and the message it came from. A
  decision is recorded by the person (``POST /api/azm/decisions``, Library) or
  by the agent through the ``record_decision`` tool, which MIZAN accepts only
  when the person's own words in the chat hold most of the decision's
  distinctive information (``ahl_dhikr.about``): the model proposes, the check
  decides. Nothing is detected automatically: Qasd has no facet for decisions,
  and one would need seeds and a measurement first. An entry is never edited;
  a changed decision is a new entry, and any entry can be forgotten.
- **Hand-off**: a snapshot of at most 8 KB (goal, open items, last decisions,
  state) rewritten at the end of every run, per chat, project and agent. A new
  chat on the same project starts with the project's; a new chat with the same
  agent with the agent's, when the new request is about the same thing
  (``niyyah.related``). The writer selects rows in priority order until the
  snapshot fits, so what is written is what is read (ForgeKit's handoff.js).

Nothing here may fail a chat: an unwritable data directory or a damaged file
reads as empty and writes nothing (``Unavailable`` only for the routes).
Mahw erases a chat's decisions and every snapshot it wrote or that quotes them
(``docs/azm.md``).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.azm")

FILE = "azm.sqlite3"
HANDOFF_BYTES = 8192
MAX_TEXT = 500
DECISIONS_SHOWN = 10
SOURCES = ("person", "chat")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    why TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS decisions_chat ON decisions (chat_id);
CREATE TABLE IF NOT EXISTS handoffs (
    scope TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    text TEXT NOT NULL,
    about TEXT NOT NULL DEFAULT '',
    written TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS niyyah (
    scope TEXT PRIMARY KEY,
    cusum REAL NOT NULL,
    runs INTEGER NOT NULL,
    updated TEXT NOT NULL
);
"""


class Unavailable(RuntimeError):
    """The person's store cannot be opened (data directory or file)."""


def path_of(owner: str) -> Path:
    from memory.mahw import private_dir

    return Path(private_dir(owner)) / FILE


def kept_for(owner: str) -> bool:
    """Whether this person has a store at all (a stat, no open): a chat for someone
    with none skips reading it."""
    try:
        return bool(owner) and path_of(owner).exists()
    except OSError:
        return False


def connect(owner: str, *, create: bool) -> sqlite3.Connection | None:
    """The person's store; None when it does not exist and ``create`` is false.
    Raises OSError or sqlite3.Error when it cannot be opened."""
    path = path_of(owner)
    if not path.exists():
        if not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.executescript(_SCHEMA)
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _flat(text: Any, limit: int = MAX_TEXT) -> str:
    return " ".join(str(text or "").split())[:limit]


def _secret(text: str) -> bool:
    from connectors.manager import redact
    from skills.builtin.raqib_scanner import SECRET_PATTERNS

    return redact(text) != text or any(
        re.search(pattern, text) for pattern, _n, _s in SECRET_PATTERNS
    )


def redacted(text: str) -> str:
    """The text with anything shaped like a credential replaced."""
    from connectors.manager import redact
    from skills.builtin.raqib_scanner import SECRET_PATTERNS

    text = redact(text)
    for pattern, _name, _severity in SECRET_PATTERNS:
        text = re.sub(pattern, "[redacted]", text)
    return text


# ── decisions ────────────────────────────────────────────────────────────


def _decision(row: Sequence[Any]) -> dict:
    keys = ("id", "chat_id", "workspace_id", "agent_id", "text", "why", "message_id", "source")
    return {**dict(zip(keys, row[:8], strict=True)), "created": row[8]}


def record(
    owner: str,
    text: str,
    why: str = "",
    *,
    chat_id: str = "",
    workspace_id: str = "",
    agent_id: str = "",
    message_id: str = "",
    source: str = "person",
) -> dict:
    """Append one decision. ValueError when it has no words, holds something
    shaped like a credential or reads as an instruction to the AI (it is shown to
    the model in later chats); Unavailable when the store cannot be written."""
    from tadbir import amanah

    decided, reason = _flat(text), _flat(why)
    if len(decided) < 2:
        raise ValueError("Say what was decided")
    if source not in SOURCES:
        raise ValueError("Unknown source")
    if _secret(f"{decided}\n{reason}"):
        raise ValueError("A decision is never kept with a password, key or token in it")
    if amanah.scan(f"{decided}\n{reason}"):
        raise ValueError("This reads as an instruction to the AI, so it is not kept")
    row = (str(chat_id)[:100], str(workspace_id)[:100], str(agent_id)[:100], decided, reason,
           str(message_id)[:100], source, _now())  # fmt: skip
    try:
        conn = connect(owner, create=True)
        assert conn is not None
        try:
            cursor = conn.execute(
                "INSERT INTO decisions (chat_id, workspace_id, agent_id, text, why, message_id, "
                "source, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.commit()
            decision_id = int(cursor.lastrowid or 0)
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as error:
        raise Unavailable(str(error)) from error
    return _decision((decision_id, *row))


def _rows(owner: str, sql: str, params: tuple = ()) -> list[tuple]:
    """Rows of the person's store; nothing when it is absent or unreadable."""
    try:
        conn = connect(owner, create=False)
    except (OSError, sqlite3.Error):
        return []
    if conn is None:
        return []
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _change(owner: str, sql: str, params: tuple = ()) -> int:
    try:
        conn = connect(owner, create=False)
    except (OSError, sqlite3.Error):
        return 0
    if conn is None:
        return 0
    try:
        changed = conn.execute(sql, params).rowcount
        conn.commit()
        return max(0, int(changed))
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def decisions(
    owner: str,
    *,
    chat_id: str | None = None,
    workspace_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """The person's decisions, oldest first, narrowed to one chat, project or agent."""
    where, params = [], []
    for column, value in (
        ("chat_id", chat_id),
        ("workspace_id", workspace_id),
        ("agent_id", agent_id),
    ):
        if value:
            where.append(f"{column} = ?")
            params.append(value)
    # The columns come from the fixed list above, never from input.
    sql = (
        "SELECT id, chat_id, workspace_id, agent_id, text, why, message_id, source, created "
        "FROM decisions" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id "
        "LIMIT ? OFFSET ?"
    )
    rows = _rows(owner, sql, (*params, max(1, min(limit, 500)), max(0, offset)))
    return [_decision(row) for row in rows]


def forget_decision(owner: str, decision_id: int) -> bool:
    return _change(owner, "DELETE FROM decisions WHERE id = ?", (int(decision_id),)) > 0


def _in_scope(owner: str, chat_id: str, workspace_id: str) -> list[dict]:
    found = decisions(owner, chat_id=chat_id, limit=500)
    if workspace_id:
        known = {item["id"] for item in found}
        found += [
            item
            for item in decisions(owner, workspace_id=workspace_id, limit=500)
            if item["id"] not in known
        ]
    return sorted(found, key=lambda item: item["id"])[-DECISIONS_SHOWN:]


def person_said(decision: str, words: Iterable[str]) -> bool:
    """The person's words hold most of the decision's distinctive information."""
    from tadbir.ahl_dhikr import about

    return bool(about(decision, "\n".join(words)))


def record_from_run(
    owner: str, decision: str, why: str = "", *, chat_id: str, workspace_id: str, agent_id: str
) -> dict:
    """``record_decision``: what the agent says the person decided, kept only when
    the person's own words in this request and chat say it."""
    from memory import stateless
    from tadbir import tabayyun

    if not owner:
        return {"error": "Decisions are kept for a signed-in person"}
    if not stateless.learns():
        return {"error": "This chat keeps nothing (stateless, or learning is off)"}
    inquiry = tabayyun.current()
    said = (
        [inquiry.task, *inquiry.answers]
        + [
            str(turn.get("content") or "")
            for turn in inquiry.history
            if isinstance(turn, dict) and turn.get("role") == "user"
        ]
        if inquiry is not None
        else []
    )
    if not person_said(decision, said):
        return {
            "error": "Not recorded: the person's own words in this chat do not say this. Record "
            "only a decision they stated, in their words."
        }
    try:
        kept = record(
            owner,
            decision,
            why,
            chat_id=chat_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            message_id=(inquiry.source if inquiry is not None else "") or "",
            source="chat",
        )
    except ValueError as error:
        return {"error": str(error)}
    except Unavailable:
        return {"error": "MIZAN's store for decisions is unavailable right now"}
    return {"recorded": True, "decision": kept}


# ── the hand-off snapshot ────────────────────────────────────────────────


def _bytes(lines: Sequence[str]) -> int:
    return sum(len(line.encode("utf-8")) for line in lines) + max(0, len(lines) - 1)


def _omitted(count: int, budget: int) -> str:
    return f"- (+{count} more not kept: over the {budget}-byte hand-off)"


def select_snapshot(
    sections: Sequence[tuple[str, Sequence[str]]], budget: int = HANDOFF_BYTES
) -> list[str]:
    """Rows in priority order (the sections' order) until the snapshot fits
    ``budget`` UTF-8 bytes. Every header stays, and a section that lost rows
    ends with a "(+N more not kept)" row: a drop is never silent."""
    reserve = [_omitted(len(rows), budget) if rows else "- (none)" for _title, rows in sections]
    used = _bytes(
        [line for (title, _rows), spare in zip(sections, reserve, strict=True)
         for line in (f"## {title}", spare, "")]
    )  # fmt: skip
    kept: list[list[str]] = [[] for _ in sections]
    for index, (_title, rows) in enumerate(sections):
        for row in rows:
            line = f"- {row}"
            cost = len(line.encode("utf-8")) + 1
            if used + cost > budget:
                break
            used += cost
            kept[index].append(line)
    out: list[str] = []
    for (title, rows), lines in zip(sections, kept, strict=True):
        out += [f"## {title}", *lines]
        if not rows:
            out.append("- (none)")
        elif len(lines) < len(rows):
            out.append(_omitted(len(rows) - len(lines), budget))
        out.append("")
    while out and not out[-1]:
        out.pop()
    return out


def compose(
    *,
    goal: str,
    open_items: Sequence[str],
    decisions: Sequence[dict],
    state: Sequence[str],
    budget: int = HANDOFF_BYTES,
) -> str:
    """The snapshot: goal, open items, the last decisions, then where it stands.
    A row longer than a quarter of the budget is cut, so one long answer cannot
    push out everything else."""
    longest = budget // 4

    def rows(values: Iterable[str]) -> list[str]:
        found = []
        for value in values:
            text = redacted(_flat(value, longest))
            if text:
                found.append(text)
        return found

    chosen = [
        f"{item['text']} — {item['why']}" if item.get("why") else str(item.get("text", ""))
        for item in decisions
    ]
    return "\n".join(
        select_snapshot(
            [
                ("Goal", rows([goal])),
                ("Open items", rows(open_items)),
                ("Decisions", rows(chosen)),
                ("State", rows(state)),
            ],
            budget,
        )
    )


def write_handoff(
    owner: str, scopes: Sequence[str], chat_id: str, text: str, about: str = ""
) -> bool:
    """Rewrite the snapshot of each scope (``chat:<id>``, ``project:<id>``,
    ``agent:<id>``); False when it could not be written (never raises)."""
    if not owner or not scopes:
        return False
    body = text.encode("utf-8")[:HANDOFF_BYTES].decode("utf-8", "ignore")
    written = _now()
    try:
        conn = connect(owner, create=True)
        assert conn is not None
        try:
            conn.executemany(
                "INSERT INTO handoffs (scope, chat_id, text, about, written) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(scope) DO UPDATE SET chat_id = excluded.chat_id, text = excluded.text, "
                "about = excluded.about, written = excluded.written",
                [
                    (scope[:200], chat_id[:100], body, _flat(about, 1000), written)
                    for scope in scopes
                ],
            )
            conn.commit()
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as error:
        logger.warning("Hand-off not written: %s", error)
        return False
    return True


def _handoff(row: Sequence[Any]) -> dict:
    return dict(zip(("scope", "chat_id", "text", "about", "written"), row, strict=True))


def handoff(owner: str, scope: str) -> dict | None:
    rows = _rows(
        owner, "SELECT scope, chat_id, text, about, written FROM handoffs WHERE scope = ?", (scope,)
    )
    return _handoff(rows[0]) if rows else None


def handoffs(owner: str) -> list[dict]:
    rows = _rows(
        owner, "SELECT scope, chat_id, text, about, written FROM handoffs ORDER BY written DESC"
    )
    return [_handoff(row) for row in rows]


def forget_handoff(owner: str, scope: str) -> bool:
    return _change(owner, "DELETE FROM handoffs WHERE scope = ?", (scope,)) > 0


def opening(
    owner: str, *, chat_id: str, workspace_id: str | None, agent_id: str | None, task: str
) -> dict | None:
    """The hand-off a new chat starts with: its project's, else its agent's when
    the new request is about what that one was about. Never its own."""
    from tadbir import niyyah

    if workspace_id:
        found = handoff(owner, f"project:{workspace_id}")
        if found and found["chat_id"] != chat_id:
            return found
    if agent_id:
        found = handoff(owner, f"agent:{agent_id}")
        if found and found["chat_id"] != chat_id and niyyah.related(found["about"], task):
            return found
    return None


def after_run(
    owner: str,
    *,
    chat_id: str,
    workspace_id: str | None,
    agent_id: str | None,
    task: str,
    answer: str,
    history: Sequence[dict] | None,
    goal: str = "",
    open_items: Sequence[str] = (),
) -> bool:
    """Rewrite this chat's snapshot (and its project's and agent's) after a run."""
    try:
        from agents import session_state
        from tadbir import amanah

        if not owner or not chat_id:
            return False
        first = next(
            (
                str(turn.get("content") or "")
                for turn in history or []
                if isinstance(turn, dict)
                and turn.get("role") == "user"
                and str(turn.get("content") or "").strip()
            ),
            "",
        )
        aim = goal or amanah.clean_message(first or task)
        todos = session_state.load(owner, chat_id).get("todos") or []
        pending = [
            str(item.get("content") or "")
            for item in todos
            if isinstance(item, dict) and item.get("status") != "completed"
        ]
        text = compose(
            goal=aim,
            open_items=[*pending, *open_items],
            decisions=_in_scope(owner, chat_id, workspace_id or ""),
            state=[
                f"Last request: {_flat(amanah.clean_message(task), 300)}",
                f"Last answer: {_flat(answer, 600)}",
            ],
        )
        scopes = [
            f"chat:{chat_id}",
            *([f"project:{workspace_id}"] if workspace_id else []),
            *([f"agent:{agent_id}"] if agent_id else []),
        ]
        return write_handoff(owner, scopes, chat_id, text, about=f"{aim}\n{_flat(task, 300)}")
    except Exception:  # noqa: BLE001 - a hand-off never fails the chat it follows
        logger.warning("Hand-off unavailable", exc_info=True)
        return False


def forget_chat(owner: str, chat_id: str) -> dict:
    """Mahw: the chat's decisions, the snapshots it wrote, and any snapshot that
    quotes one of its decisions."""
    texts = [
        str(row[0])
        for row in _rows(owner, "SELECT text FROM decisions WHERE chat_id = ?", (chat_id,))
    ]
    removed = _change(owner, "DELETE FROM decisions WHERE chat_id = ?", (chat_id,))
    dropped = _change(owner, "DELETE FROM handoffs WHERE chat_id = ?", (chat_id,))
    for text in texts:
        dropped += _change(owner, "DELETE FROM handoffs WHERE instr(text, ?) > 0", (text,))
    return {"decisions": removed, "handoffs": dropped}


def ledger(owner: str) -> list[dict]:
    """Daftar's entries: each decision and each hand-off, forgettable one by one."""
    entries: list[dict] = []
    for item in decisions(owner, limit=500):
        scope = (
            "a project"
            if item["workspace_id"]
            else "an agent"
            if item["agent_id"] and not item["chat_id"]
            else "a chat"
        )
        entries.append(
            {
                "id": f"decision:{item['id']}",
                "kind": "decision",
                "content": f"{item['text']} — {item['why']}" if item["why"] else item["text"],
                "source": {
                    "kind": "chat" if item["chat_id"] else "manual",
                    **({"session_id": item["chat_id"]} if item["chat_id"] else {}),
                    "label": (
                        f"you decided, in {scope}"
                        if item["source"] == "person"
                        else f"you said it in {scope}; recorded by your agent"
                    ),
                },
                "created": item["created"],
                "last_used": "",
                "expires": "",
                "editable": False,
                "forgettable": True,
            }
        )
    for item in handoffs(owner):
        kind, _, _key = item["scope"].partition(":")
        entries.append(
            {
                "id": f"handoff:{item['scope']}",
                "kind": "handoff",
                "content": item["text"],
                "source": {
                    "kind": "chat",
                    "session_id": item["chat_id"],
                    "label": f"{_WHOSE.get(kind, 'a')} hand-off, rewritten after each answer",
                },
                "created": item["written"],
                "last_used": "",
                "expires": "",
                "editable": False,
                "forgettable": True,
            }
        )
    return entries


_WHOSE = {"chat": "a chat's", "project": "a project's", "agent": "an agent's"}


def forget_entries(owner: str, ids: Iterable[str]) -> dict[str, int]:
    """Forget Daftar entries ``decision:<id>`` and ``handoff:<scope>``."""
    forgotten = {"decision": 0, "handoff": 0}
    for entry in ids:
        kind, _, key = str(entry).partition(":")
        if kind == "decision" and key.isdigit() and forget_decision(owner, int(key)):
            forgotten["decision"] += 1
        elif kind == "handoff" and key and forget_handoff(owner, key):
            forgotten["handoff"] += 1
    return forgotten
