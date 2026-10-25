"""A selected project is bound by authenticated chat code, never by model arguments."""

from contextvars import ContextVar

from fastapi import HTTPException

from security.auth import current_user_id

from .store import WorkspaceStore

_selected: ContextVar[str | None] = ContextVar("coding_workspace", default=None)
_chat_session: ContextVar[str | None] = ContextVar("workspace_chat_session", default=None)


def bind_chat_session(session_id: str | None):
    return _chat_session.set(session_id)


def reset_chat_session(token):
    _chat_session.reset(token)


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
