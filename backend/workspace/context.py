"""A selected project is bound by authenticated chat code, never by model arguments."""

from contextvars import ContextVar

from fastapi import HTTPException

from security.auth import current_user_id

from .store import WorkspaceStore

_selected: ContextVar[str | None] = ContextVar("coding_workspace", default=None)


def authorize_owned_workspace(workspace_id: str, owner_id: str) -> dict:
    store = WorkspaceStore(owner_id)
    return store._metadata(store.project(workspace_id))


def bind_workspace(workspace_id: str | None):
    return _selected.set(workspace_id)


def reset_workspace(token):
    _selected.reset(token)


def selected_workspace(workspace_id: str | None) -> str:
    selected = _selected.get()
    if selected and workspace_id and selected != workspace_id:
        raise HTTPException(403, "This chat is scoped to its selected project")
    result = workspace_id or selected
    if not result:
        raise HTTPException(422, "Select or create a coding project first")
    authorize_owned_workspace(result, current_user_id() or "")
    return result
