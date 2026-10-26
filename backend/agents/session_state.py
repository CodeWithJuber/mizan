"""Small per-chat state that must outlive one run (todo list, active skills).

Chat history stores text only, so a plan written with ``todo_write`` or a
skill activated in one turn would otherwise vanish on the next. State lives
under ``$MIZAN_DATA_DIR/session_state/<sha256(user)>/<sha256(session)>.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
MAX_TODOS = 50
TODO_STATUSES = ("pending", "in_progress", "completed")


def _path(user_id: str, session_id: str) -> Path:
    root = Path(os.getenv("MIZAN_DATA_DIR", "data")) / "session_state"
    user = hashlib.sha256(user_id.encode()).hexdigest()
    session = hashlib.sha256(session_id.encode()).hexdigest()
    return root / user / f"{session}.json"


def load(user_id: str, session_id: str) -> dict[str, Any]:
    if not user_id or not session_id:
        return {}
    path = _path(user_id, session_id)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return {}
    with os.fdopen(fd) as handle:
        try:
            data = json.load(handle)
        except ValueError:
            return {}
    return data if isinstance(data, dict) else {}


def update(user_id: str, session_id: str, key: str, value: Any) -> dict[str, Any]:
    if not user_id or not session_id:
        return {}
    path = _path(user_id, session_id)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = load(user_id, session_id)
        data[key] = value
        temporary = path.parent / f".{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, ensure_ascii=False)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return data


def normalize_todos(items: Any) -> list[dict]:
    """Validate a todo list: content (≤500 chars) and a known status."""
    if not isinstance(items, list):
        raise ValueError("todos must be a list")
    todos = []
    for item in items[:MAX_TODOS]:
        if not isinstance(item, dict):
            raise ValueError("each todo must be an object")
        content = str(item.get("content", "")).strip()
        status = str(item.get("status", "pending"))
        if not content:
            raise ValueError("each todo needs content")
        if status not in TODO_STATUSES:
            raise ValueError(f"status must be one of {', '.join(TODO_STATUSES)}")
        todos.append({"content": content[:500], "status": status})
    if sum(item["status"] == "in_progress" for item in todos) > 1:
        raise ValueError("only one todo can be in_progress at a time")
    return todos


def todo_block(todos: list[dict]) -> str:
    """Prompt block that keeps the current plan visible across turns."""
    if not todos:
        return ""
    marks = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
    lines = [f"{marks.get(t['status'], '[ ]')} {t['content']}" for t in todos]
    return "[CURRENT TODO LIST — your own plan for this chat]\n" + "\n".join(lines) + "\n[END TODO]"
