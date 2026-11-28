"""Owner-scoped coding projects and an honest isolation/hardware capability API."""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator

from api.artifacts import create_artifact, get_artifact, require_auth, validate_image
from security.auth import TokenPayload
from workspace import session_client
from workspace.context import refuse_if_busy
from workspace.execution import capabilities, run_project
from workspace.store import MAX_FILES, MAX_PROTECTED, WorkspaceStore

router = APIRouter(prefix="/api/workspaces", tags=["coding workspaces"])


def require_editor(user: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not user.has_min_role("user"):
        raise HTTPException(403, "Project editing requires the user or administrator role")
    return user


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class FileWrite(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=1024 * 1024)
    expected_sha256: str | None = Field(default=None, max_length=64)


class FilePath(BaseModel):
    path: str = Field(min_length=1, max_length=512)


class FileRename(FilePath):
    new_path: str = Field(min_length=1, max_length=512)


class RunRequest(BaseModel):
    command: str = Field(min_length=1, max_length=10000)
    language: Literal["python", "javascript", "shell"] = "shell"
    timeout_s: int = Field(default=30, ge=1, le=120)


class CheckpointCreate(BaseModel):
    message: str = Field(default="Project checkpoint", min_length=1, max_length=200)


class CheckpointRestore(BaseModel):
    # Only these files (a path the checkpoint lacks is deleted); none means the whole project.
    paths: list[str] | None = Field(default=None, max_length=MAX_FILES)


class WorkspaceUpdate(BaseModel):
    """A new name and/or the project's protected paths (an empty list protects nothing)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    protected_paths: list[str] | None = Field(default=None, max_length=MAX_PROTECTED)

    @model_validator(mode="after")
    def one_change(self) -> WorkspaceUpdate:
        if self.name is None and self.protected_paths is None:
            raise ValueError("Send a name or protected_paths")
        return self


class ArtifactPublish(FilePath):
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    title: str | None = Field(default=None, min_length=1, max_length=200)


def publish_artifact(
    store: WorkspaceStore,
    workspace_id: str,
    *,
    user_id: str,
    path: str,
    session_id: str,
    title: str | None = None,
) -> dict:
    suffix = Path(path).suffix.lower()
    language = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".css": "css",
        ".json": "json",
        ".sh": "bash",
    }.get(suffix)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        data = store.read_bytes(workspace_id, path)
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }[suffix]
        content = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        validate_image(content)
        kind = "image"
    else:
        content = store.read(workspace_id, path)["content"]
        kind = (
            "html"
            if suffix in {".html", ".htm"}
            else "markdown"
            if suffix in {".md", ".txt"}
            else "code"
        )
    if not content or len(content) > 500000:
        raise HTTPException(413, "Artifact content must be 1..500000 characters")
    created = create_artifact(
        user_id=user_id,
        session_id=session_id,
        title=title or Path(path).name,
        kind=kind,
        content=content,
        language=language,
    )
    return {"artifact": get_artifact(user_id=user_id, artifact_id=created["id"])}


@router.get("")
async def list_workspaces(user: TokenPayload = Depends(require_auth)) -> dict:
    return {
        "workspaces": WorkspaceStore(user.user_id).list(),
        "capabilities": await capabilities(admin=user.has_role("admin")),
    }


@router.post("", status_code=201)
def create_workspace(body: WorkspaceCreate, user: TokenPayload = Depends(require_editor)) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).create(body.name))


@router.patch("/{workspace_id}")
def update_workspace(
    workspace_id: str, body: WorkspaceUpdate, user: TokenPayload = Depends(require_editor)
) -> dict:
    """Rename a project or set its protected paths: a change the agent makes to one of
    them asks the person in every permission mode (docs/coding-workspaces.md)."""
    return cast(
        dict,
        WorkspaceStore(user.user_id).update_project(
            workspace_id, name=body.name, protected_paths=body.protected_paths
        ),
    )


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: str, user: TokenPayload = Depends(require_editor)) -> dict:
    """Delete a whole project, its checkpoints and its sandbox session."""
    store = WorkspaceStore(user.user_id)
    store.project(workspace_id)
    refuse_if_busy(user.user_id, workspace_id, "delete it")
    if await session_client.running(user.user_id, workspace_id):
        try:
            await session_client.stop(user.user_id, workspace_id)
        except HTTPException:
            pass  # the runner reaps sessions whose project is gone
    store.remove(workspace_id)
    return {"deleted": True, "id": workspace_id}


@router.get("/{workspace_id}/export.zip")
async def export_workspace(
    workspace_id: str, user: TokenPayload = Depends(require_auth)
) -> Response:
    """The project's files (not git's folder) as a zip."""
    name, data = await asyncio.to_thread(WorkspaceStore(user.user_id).export_zip, workspace_id)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/hardware")
def hardware(user: TokenPayload = Depends(require_auth)) -> dict:
    if not user.has_role("admin"):
        raise HTTPException(403, "Administrator role required")
    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable"}:
                memory[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    disk = shutil.disk_usage(os.getenv("MIZAN_DATA_DIR", "data"))
    return {
        "scope": "backend-container",
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": memory.get("MemTotal"),
        "memory_available_bytes": memory.get("MemAvailable"),
        "disk_total_bytes": disk.total,
        "disk_available_bytes": disk.free,
        "gpus": [],
        "host_shell": False,
        "operations": ["isolated_project_run", "project_file_management", "project_checkpoint"],
    }


@router.get("/{workspace_id}/tree")
def tree(workspace_id: str, user: TokenPayload = Depends(require_auth)) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).tree(workspace_id))


@router.get("/{workspace_id}/file")
def read_file(
    workspace_id: str,
    path: str = Query(min_length=1, max_length=512),
    user: TokenPayload = Depends(require_auth),
) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).read(workspace_id, path))


_PREVIEW_SKIP = ("node_modules/", "dist/", "build/", ".next/", ".git/", "__pycache__/", ".venv/")
MAX_PREVIEW_BYTES = 3 * 1024 * 1024


@router.get("/{workspace_id}/files")
def text_files(workspace_id: str, user: TokenPayload = Depends(require_auth)) -> dict:
    """The project's text files in one response (for browser previews), bounded."""
    store = WorkspaceStore(user.user_id)
    files: dict[str, str] = {}
    total, skipped = 0, 0
    for entry in store.tree(workspace_id)["files"]:
        path = entry["path"]
        if entry["kind"] != "file" or any(
            path.startswith(d) or f"/{d}" in path for d in _PREVIEW_SKIP
        ):
            continue
        if total + entry["size"] > MAX_PREVIEW_BYTES:
            skipped += 1
            continue
        try:
            data = store.read_bytes(workspace_id, path)
        except HTTPException:
            skipped += 1
            continue
        if b"\x00" in data[:4096]:
            continue
        files[path] = data.decode("utf-8", "replace")
        total += len(data)
    return {"files": files, "skipped": skipped, "bytes": total}


@router.put("/{workspace_id}/file")
def write_file(
    workspace_id: str, body: FileWrite, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(
        dict,
        WorkspaceStore(user.user_id).write(
            workspace_id, body.path, body.content, body.expected_sha256
        ),
    )


@router.post("/{workspace_id}/directory", status_code=201)
def create_directory(
    workspace_id: str, body: FilePath, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).directory(workspace_id, body.path))


@router.post("/{workspace_id}/rename")
def rename_file(
    workspace_id: str, body: FileRename, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).rename(workspace_id, body.path, body.new_path))


@router.delete("/{workspace_id}/file")
def delete_file(
    workspace_id: str,
    path: str = Query(min_length=1, max_length=512),
    user: TokenPayload = Depends(require_editor),
) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).delete(workspace_id, path))


@router.post("/{workspace_id}/run")
async def execute_project(
    workspace_id: str, body: RunRequest, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(
        dict,
        await run_project(
            WorkspaceStore(user.user_id), workspace_id, body.command, body.language, body.timeout_s
        ),
    )


@router.post("/{workspace_id}/checkpoint", status_code=201)
def checkpoint(
    workspace_id: str, body: CheckpointCreate, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).checkpoint(workspace_id, body.message))


@router.get("/{workspace_id}/checkpoints")
def checkpoints(workspace_id: str, user: TokenPayload = Depends(require_auth)) -> dict:
    return {"checkpoints": WorkspaceStore(user.user_id).checkpoints(workspace_id)}


@router.post("/{workspace_id}/checkpoints/{checkpoint_id}/restore")
async def restore_checkpoint(
    workspace_id: str,
    checkpoint_id: str,
    body: CheckpointRestore,
    user: TokenPayload = Depends(require_editor),
) -> dict:
    """Bring files back to a checkpoint (all, or ``paths``); the current state is saved first."""
    store = WorkspaceStore(user.user_id)
    refuse_if_busy(user.user_id, workspace_id, "restore")
    result = cast(
        dict, await asyncio.to_thread(store.restore, workspace_id, checkpoint_id, body.paths)
    )
    if (result["restored"] or result["removed"]) and await session_client.running(
        user.user_id, workspace_id
    ):
        try:
            result["session"] = await session_client.reconcile(user.user_id, workspace_id)
        except HTTPException as exc:
            result["session"] = {"warning": f"The sandbox session was not updated: {exc.detail}"}
    return result


@router.get("/{workspace_id}/checkpoints/{checkpoint_id}/file")
def checkpoint_file(
    workspace_id: str,
    checkpoint_id: str,
    path: str = Query(min_length=1, max_length=512),
    user: TokenPayload = Depends(require_auth),
) -> dict:
    """One file as it was in a checkpoint."""
    return cast(dict, WorkspaceStore(user.user_id).file_at(workspace_id, checkpoint_id, path))


@router.get("/{workspace_id}/diff")
def diff(
    workspace_id: str,
    checkpoint_id: str = Query(min_length=32, max_length=32),
    user: TokenPayload = Depends(require_auth),
) -> dict:
    return cast(dict, WorkspaceStore(user.user_id).diff(workspace_id, checkpoint_id))


@router.post("/{workspace_id}/artifact", status_code=201)
def artifact(
    workspace_id: str, body: ArtifactPublish, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(
        dict,
        publish_artifact(
            WorkspaceStore(user.user_id), workspace_id, user_id=user.user_id, **body.model_dump()
        ),
    )
