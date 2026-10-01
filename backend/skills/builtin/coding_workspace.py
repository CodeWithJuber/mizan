"""Real agent tools for private persistent coding projects and saved artifacts."""

from __future__ import annotations

import builtins
import shlex
from typing import cast

from fastapi import HTTPException

from api.coding_workspace import hardware, publish_artifact
from security.auth import TokenPayload, current_user_id, request_has_role
from workspace.context import selected_workspace
from workspace.execution import run_project
from workspace.store import WorkspaceStore

from ..base import SkillBase, SkillManifest


class CodingWorkspaceSkill(SkillBase):
    manifest = SkillManifest(
        name="coding_workspace",
        description="Persistent private coding projects, isolated execution, checkpoints and preview artifacts.",
        permissions=["workspace:read:own", "workspace:write:own", "workspace:execute:isolated"],
        tags=["كاتب", "Development"],
    )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._tools = {
            f"workspace_{name}": getattr(self, name)
            for name in (
                "create",
                "list",
                "tree",
                "read",
                "write",
                "run",
                "git",
                "checkpoint",
                "diff",
                "artifact",
                "hardware",
            )
        }

    @staticmethod
    def store(*, edit: bool = False) -> WorkspaceStore:
        user_id = current_user_id()
        if not user_id:
            raise HTTPException(401, "Authentication required")
        if edit and not request_has_role("user"):
            raise HTTPException(403, "Project editing requires the user or administrator role")
        return WorkspaceStore(user_id)

    async def execute(self, params: dict, context: dict | None = None) -> dict:
        data = dict(params)
        action = data.pop("action", "list")
        tool = self._tools.get(f"workspace_{action}")
        if not tool:
            return {"error": "Unknown coding workspace action"}
        # Never trust a user_id supplied in a tool call/context.
        data.pop("user_id", None)
        try:
            return cast(dict, await tool(**data))
        except HTTPException as exc:
            return {"error": exc.detail, "status": exc.status_code}

    async def create(self, name: str = "Agent project") -> dict:
        return cast(dict, self.store(edit=True).create(name))

    async def list(self) -> dict:
        return {"workspaces": self.store().list()}

    async def tree(self, workspace_id: str | None = None) -> dict:
        return cast(dict, self.store().tree(selected_workspace(workspace_id)))

    async def read(self, workspace_id: str | None = None, path: str = "") -> dict:
        return cast(dict, self.store().read(selected_workspace(workspace_id), path))

    async def write(
        self,
        workspace_id: str | None = None,
        path: str = "",
        content: str = "",
        expected_sha256: str | None = None,
    ) -> dict:
        return cast(
            dict,
            self.store(edit=True).write(
                selected_workspace(workspace_id), path, content, expected_sha256
            ),
        )

    async def run(
        self,
        workspace_id: str | None = None,
        command: str = "",
        language: str = "shell",
        timeout_s: int = 30,
    ) -> dict:
        return cast(
            dict,
            await run_project(
                self.store(edit=True),
                selected_workspace(workspace_id),
                command,
                language,
                timeout_s,
            ),
        )

    async def checkpoint(
        self, workspace_id: str | None = None, message: str = "Agent checkpoint"
    ) -> dict:
        return cast(
            dict, self.store(edit=True).checkpoint(selected_workspace(workspace_id), message)
        )

    async def git(
        self,
        workspace_id: str | None = None,
        action: str = "status",
        message: str = "Workspace update",
    ) -> dict:
        commands = {
            "status": "git status --short",
            "diff": "git diff --no-ext-diff",
            "log": "git log -10 --oneline",
            "init": "git init",
        }
        if action == "commit":
            if not message or len(message) > 200:
                raise HTTPException(422, "Commit message must be 1..200 characters")
            command = (
                "git add -A && git -c user.name=Mizan -c user.email=workspace@localhost commit -m "
                + shlex.quote(message)
            )
        elif action in commands:
            command = commands[action]
        else:
            raise HTTPException(422, "Unsupported workspace git action")
        return await self.run(
            workspace_id=workspace_id, command=command, language="shell", timeout_s=30
        )

    async def diff(self, workspace_id: str | None = None, checkpoint_id: str = "") -> dict:
        return cast(dict, self.store().diff(selected_workspace(workspace_id), checkpoint_id))

    async def artifact(
        self,
        workspace_id: str | None = None,
        path: str = "",
        session_id: str = "",
        title: str | None = None,
    ) -> dict:
        store = self.store(edit=True)
        return cast(
            dict,
            publish_artifact(
                store,
                selected_workspace(workspace_id),
                user_id=current_user_id() or "",
                path=path,
                session_id=session_id,
                title=title,
            ),
        )

    async def hardware(self) -> dict:
        self.store()  # Requires an authenticated principal even with a stale role binding.
        if not request_has_role("admin"):
            raise HTTPException(403, "Administrator role required")
        return cast(dict, hardware(TokenPayload(current_user_id() or "", "", ["admin"], 0, 0, "")))

    def get_tool_schemas(self) -> builtins.list[dict]:
        string = {"type": "string"}
        project = {
            "workspace_id": {
                "type": "string",
                "description": "Private project ID returned by workspace_create",
            }
        }
        definitions = [
            (
                "create",
                "Create a persistent private project before coding; files survive chat and server restarts.",
                {"name": string},
                ["name"],
            ),
            ("list", "List the requesting user's coding projects.", {}, []),
            ("tree", "Inspect project files before modifying them.", project, ["workspace_id"]),
            (
                "read",
                "Read a project file and its hash for safe subsequent edits.",
                {**project, "path": string},
                ["workspace_id", "path"],
            ),
            (
                "write",
                "Create or update a private project file; use expected_sha256 to protect intervening edits.",
                {**project, "path": string, "content": string, "expected_sha256": string},
                ["workspace_id", "path", "content"],
            ),
            (
                "run",
                "Run Python, JavaScript or shell in an isolated project sandbox without network or host secrets. Returns real output and saves generated files. Never claim success when unavailable.",
                {
                    **project,
                    "command": string,
                    "language": {"type": "string", "enum": ["shell", "python", "javascript"]},
                    "timeout_s": {"type": "integer", "minimum": 1, "maximum": 120},
                },
                ["workspace_id", "command"],
            ),
            (
                "checkpoint",
                "Preserve project files before a substantial change; retain the five latest snapshots.",
                {**project, "message": string},
                ["workspace_id"],
            ),
            (
                "git",
                "Run git status, diff, log, init or a local commit inside the isolated project. Git history is persisted with project files; remote network operations are unavailable.",
                {
                    **project,
                    "action": {
                        "type": "string",
                        "enum": ["status", "diff", "log", "init", "commit"],
                    },
                    "message": string,
                },
                ["action"],
            ),
            (
                "diff",
                "Review actual changes against a project checkpoint.",
                {**project, "checkpoint_id": string},
                ["workspace_id", "checkpoint_id"],
            ),
            (
                "artifact",
                "Publish an existing project code, HTML, markdown or raster image file as an owner-scoped saved preview artifact; returns the persisted artifact.",
                {**project, "path": string, "session_id": string, "title": string},
                ["workspace_id", "path", "session_id"],
            ),
            (
                "hardware",
                "Inspect backend CPU, memory and disk availability. Requires administrator role; does not grant unrestricted host access.",
                {},
                [],
            ),
        ]
        return [
            {
                "name": f"workspace_{name}",
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": [key for key in required if key != "workspace_id"],
                },
            }
            for name, description, properties, required in definitions
        ]
