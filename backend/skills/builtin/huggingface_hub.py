"""Hugging Face Hub tools: list, inspect, preview and import datasets, read by MIZAN.

The code sandbox has no network; these tools read the Hub on the server and
put a file (or, for a large text file, its first rows) into the user's project,
where a program can use it. Read-only; the owner's token is used for admins only.
"""

from __future__ import annotations

from typing import cast

from fastapi import HTTPException

from knowledge import hf_hub
from security.auth import current_user_id, request_has_role
from workspace.context import bound_workspace_id, selected_workspace
from workspace.store import MAX_FILE_BYTES, WorkspaceStore

from ..base import SkillBase, SkillManifest

_METHODS = {
    "hf_repos": "repos",
    "hf_files": "files",
    "hf_preview": "preview",
    "hf_import": "import_file",
}


def allows_user_hf_tool(tool_name: str, registry, *, native_tools: dict | None = None) -> bool:
    """The shipped, read-only Hub tools are open to every signed-in user (public repos)."""
    method_name = _METHODS.get(tool_name)
    if registry is None or method_name is None or tool_name in (native_tools or {}):
        return False
    skill = registry.get_skill("huggingface_hub")
    if type(skill) is not HuggingFaceHubSkill:
        return False
    trusted = skill.get_tools().get(tool_name)
    actual = registry.get_all_tools().get(tool_name)
    return (
        trusted is not None
        and actual is trusted
        and getattr(actual, "__self__", None) is skill
        and getattr(actual, "__func__", None) is getattr(HuggingFaceHubSkill, method_name)
    )


class HuggingFaceHubSkill(SkillBase):
    manifest = SkillManifest(
        name="huggingface_hub",
        version="1.0.0",
        description="Read datasets and models from Hugging Face and import files into a project.",
        permissions=["network:https://huggingface.co", "workspace:write:own"],
        tags=["datasets", "huggingface", "training"],
    )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._tools = {name: getattr(self, method) for name, method in _METHODS.items()}

    async def execute(self, params: dict, context: dict | None = None) -> dict:
        data = dict(params)
        tool = self._tools.get(f"hf_{data.pop('action', 'repos')}")
        if tool is None:
            return {"error": "Unknown Hugging Face action"}
        return cast(dict, await tool(**data))

    async def repos(self, owner: str = "", kind: str = "datasets") -> dict:
        try:
            return cast(dict, await hf_hub.repos(owner, kind))
        except Exception as exc:  # noqa: BLE001 - a receipt, not a crash
            return {"error": str(exc)[:300]}

    async def files(self, repo: str = "", kind: str = "datasets", revision: str = "main") -> dict:
        try:
            return cast(dict, await hf_hub.files(repo, kind, revision))
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)[:300]}

    async def preview(self, repo: str = "", rows: int = 5) -> dict:
        try:
            return cast(dict, await hf_hub.preview(repo, rows))
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)[:300]}

    async def import_file(
        self,
        repo: str = "",
        path: str = "",
        kind: str = "datasets",
        revision: str = "main",
        save_as: str = "",
        workspace_id: str | None = None,
    ) -> dict:
        """Put one Hub file into the project (a large text file: its first whole rows)."""
        user_id = current_user_id()
        if not user_id:
            return {"error": "Authentication required"}
        if not request_has_role("user"):
            return {"error": "Importing into a project requires the user or administrator role"}
        store = WorkspaceStore(user_id)
        try:
            if workspace_id or bound_workspace_id():
                project = selected_workspace(workspace_id)
            else:
                from skills.builtin.coding_workspace import scratch_project

                project = scratch_project(store)
            got = await hf_hub.fetch(repo, path, kind, revision, max_bytes=MAX_FILE_BYTES)
            name = save_as.strip().lstrip("/") or "hf/" + f"{repo.split('/')[-1]}/{path}"
            if got["sampled"]:
                stem, dot, suffix = name.rpartition(".")
                name = f"{stem}.sample.{suffix}" if dot else f"{name}.sample"
            saved = store.write_bytes(project, name, got["bytes"])
        except hf_hub.HubError as exc:
            return {"error": str(exc)[:300]}
        except HTTPException as exc:
            return {"error": str(exc.detail)[:300], "status": exc.status_code}
        return {
            "workspace_id": project,
            "path": name,
            "source": got["url"].replace("/resolve/", "/blob/"),
            "bytes": len(got["bytes"]),
            "size_on_hub": got["size"],
            "sampled": got["sampled"],
            "rows": got["rows"],
            "sha256": saved.get("sha256"),
        }

    def get_tool_schemas(self) -> list[dict]:
        string = {"type": "string"}
        kind = {"type": "string", "enum": ["datasets", "models", "spaces"]}
        return [
            {
                "name": "hf_repos",
                "description": "List the datasets, models or spaces of a Hugging Face user or organisation (default: the owner's own account).",
                "input_schema": {"type": "object", "properties": {"owner": string, "kind": kind}},
            },
            {
                "name": "hf_files",
                "description": "List the files and sizes of a Hugging Face repository (owner/name).",
                "input_schema": {
                    "type": "object",
                    "properties": {"repo": string, "kind": kind, "revision": string},
                    "required": ["repo"],
                },
            },
            {
                "name": "hf_preview",
                "description": "The first rows of a Hugging Face dataset, from the Hub's dataset viewer.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo": string,
                        "rows": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["repo"],
                },
            },
            {
                "name": "hf_import",
                "description": "Import one file from a Hugging Face repository into the selected project (or the Scratch project), so code can use it offline. A large text file becomes a sample of its first rows.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo": string,
                        "path": string,
                        "kind": kind,
                        "revision": string,
                        "save_as": string,
                        "workspace_id": string,
                    },
                    "required": ["repo", "path"],
                },
            },
        ]
