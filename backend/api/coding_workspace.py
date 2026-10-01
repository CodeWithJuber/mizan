"""Owner-scoped coding projects and an honest isolation/hardware capability API."""

from __future__ import annotations

import base64
import os
import shutil
from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.artifacts import create_artifact, get_artifact, require_auth, validate_image
from security.auth import TokenPayload
from workspace.execution import capabilities, run_project
from workspace.store import WorkspaceStore

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


class ArtifactPublish(FilePath):
    session_id: str = Field(min_length=1, max_length=100)
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
