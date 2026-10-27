"""Owner-scoped Agent Skills: list, inspect, install, write, enable and remove."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from agent_skills import installer, loader
from api.artifacts import require_auth
from security.auth import TokenPayload

router = APIRouter(prefix="/api/agent-skills", tags=["agent skills"])


def require_editor(user: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not user.has_min_role("user"):
        raise HTTPException(403, "Managing skills requires the user or administrator role")
    return user


class SkillInstall(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    overwrite: bool = False


class SkillWrite(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1024)
    body: str = Field(default="", max_length=200_000)
    overwrite: bool = False


class SkillToggle(BaseModel):
    enabled: bool


def _owned_workspace(user: TokenPayload, workspace_id: str | None) -> str | None:
    if not workspace_id:
        return None
    from workspace.context import authorize_owned_workspace

    authorize_owned_workspace(workspace_id, user.user_id)
    return workspace_id


@router.get("")
async def list_skills(
    workspace_id: str | None = Query(default=None, max_length=100),
    user: TokenPayload = Depends(require_auth),
):
    workspace = _owned_workspace(user, workspace_id)
    active = loader.available_skills(user.user_id, workspace, include_disabled=True)
    disabled = loader.disabled_skills(user.user_id)
    every = loader.all_skills(user.user_id, workspace)
    return {
        "skills": [
            {**skill.summary(), "enabled": name not in disabled} for name, skill in active.items()
        ],
        "shadowed": [
            skill.summary()
            for skill in every
            if active.get(skill.name) is not None and active[skill.name] is not skill
        ],
    }


@router.get("/{name}")
async def get_skill(
    name: str,
    workspace_id: str | None = Query(default=None, max_length=100),
    user: TokenPayload = Depends(require_auth),
):
    skills = loader.available_skills(
        user.user_id, _owned_workspace(user, workspace_id), include_disabled=True
    )
    skill = skills.get(name)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    return {**skill.summary(), "body": skill.body}


@router.get("/{name}/file")
async def get_skill_file(
    name: str,
    path: str = Query(min_length=1, max_length=300),
    workspace_id: str | None = Query(default=None, max_length=100),
    user: TokenPayload = Depends(require_auth),
):
    skills = loader.available_skills(
        user.user_id, _owned_workspace(user, workspace_id), include_disabled=True
    )
    skill = skills.get(name)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    try:
        data = skill.read(path)
    except Exception:
        raise HTTPException(404, "File not found in this skill") from None
    return {"path": path, "content": data.decode("utf-8", "replace")}


@router.post("/install")
async def install_skill(body: SkillInstall, user: TokenPayload = Depends(require_editor)):
    try:
        archive, subpath = await installer.fetch_github_archive(body.url)
        installed = installer.install_archive(
            user.user_id, archive, subpath, overwrite=body.overwrite
        )
    except installer.InstallError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"installed": installed}


@router.post("/upload")
async def upload_skill(
    archive: UploadFile = File(...),
    overwrite: bool = Query(default=False),
    user: TokenPayload = Depends(require_editor),
):
    data = await archive.read(installer.MAX_DOWNLOAD_BYTES + 1)
    if len(data) > installer.MAX_DOWNLOAD_BYTES:
        raise HTTPException(413, "Archive is larger than 30 MB")
    try:
        installed = installer.install_archive(user.user_id, data, overwrite=overwrite)
    except installer.InstallError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"installed": installed}


@router.post("")
async def write_skill(body: SkillWrite, user: TokenPayload = Depends(require_editor)):
    try:
        return installer.write_skill(
            user.user_id, body.name, body.description, body.body, overwrite=body.overwrite
        )
    except installer.InstallError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/{name}/enabled")
async def toggle_skill(name: str, body: SkillToggle, user: TokenPayload = Depends(require_editor)):
    if name not in loader.available_skills(user.user_id, include_disabled=True):
        raise HTTPException(404, "Skill not found")
    disabled = loader.set_enabled(user.user_id, name, body.enabled)
    return {"name": name, "enabled": name not in disabled}


@router.delete("/{name}")
async def delete_skill(name: str, user: TokenPayload = Depends(require_editor)):
    if not installer.delete_skill(user.user_id, name):
        raise HTTPException(404, "Only your installed skills can be removed")
    return {"deleted": name}
