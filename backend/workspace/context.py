"""A selected project is bound by authenticated chat code, never by model arguments."""

import threading
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException

from security.auth import current_user_id

from .store import WorkspaceStore

_selected: ContextVar[str | None] = ContextVar("coding_workspace", default=None)
_chat_session: ContextVar[str | None] = ContextVar("workspace_chat_session", default=None)
# Projects a chat run is working in right now, so a delete or restore waits for it.
_running: Counter[tuple[str, str]] = Counter()
_running_lock = threading.Lock()


@contextmanager
def running_in(owner_id: str, workspace_id: str | None):
    """Mark a project busy for the length of a run (nothing when no project is bound)."""
    if not workspace_id:
        yield
        return
    key = (owner_id, workspace_id)
    with _running_lock:
        _running[key] += 1
    try:
        yield
    finally:
        with _running_lock:
            _running[key] -= 1
            if _running[key] <= 0:
                del _running[key]


def busy(owner_id: str, workspace_id: str) -> bool:
    with _running_lock:
        return _running.get((owner_id, workspace_id), 0) > 0


def refuse_if_busy(owner_id: str, workspace_id: str, action: str) -> None:
    if busy(owner_id, workspace_id):
        raise HTTPException(409, f"A chat is working in this project; {action} when it finishes")


def bind_chat_session(session_id: str | None):
    return _chat_session.set(session_id)


def reset_chat_session(token):
    _chat_session.reset(token)


def current_chat_session() -> str | None:
    """The chat session bound by the authenticated route for this run, if any."""
    return _chat_session.get()


def artifact_session(session_id: str) -> str:
    bound = _chat_session.get()
    if bound and session_id and bound != session_id:
        raise HTTPException(403, "Artifacts belong to the current chat session")
    result = bound or session_id
    if not result:
        raise HTTPException(422, "A chat session is required to publish an artifact")
    return result


def authorize_owned_workspace(workspace_id: str, owner_id: str) -> dict:
    store = WorkspaceStore(owner_id)
    return store._metadata(store.project(workspace_id))


def bind_workspace(workspace_id: str | None):
    return _selected.set(workspace_id)


def reset_workspace(token):
    _selected.reset(token)


def bound_workspace_id() -> str | None:
    """Return the server-bound project for tool-policy checks, never a model argument."""
    return _selected.get()


def selected_workspace(workspace_id: str | None) -> str:
    selected = _selected.get()
    if selected and workspace_id and selected != workspace_id:
        raise HTTPException(403, "This chat is scoped to its selected project")
    result = workspace_id or selected
    if not result:
        raise HTTPException(422, "Select or create a coding project first")
    authorize_owned_workspace(result, current_user_id() or "")
    return result
