"""Real agent tools for private persistent coding projects and saved artifacts."""

from __future__ import annotations

import builtins
import shlex
from typing import cast

from fastapi import HTTPException

from api.coding_workspace import hardware, publish_artifact
from security.auth import TokenPayload, current_user_id, request_has_role
from workspace.context import artifact_session, selected_workspace
from workspace.execution import run_project
from workspace.store import WorkspaceStore

from ..base import SkillBase, SkillManifest


def allows_user_workspace_tool(
    tool_name: str, registry, *, native_tools: dict | None = None
) -> bool:
    """Allow only this shipped skill's actual bound methods in the user chat dispatcher.

    A similarly named plugin/native tool never inherits this exception. The
    individual methods still check the principal, selected owner and editor role.
    """
    if registry is None or tool_name in (native_tools or {}):
        return False
    skill = registry.get_skill("coding_workspace")
    if type(skill) is not CodingWorkspaceSkill:
        return False
    trusted = skill.get_tools().get(tool_name)
    if trusted is None:
        return False
    actual = registry.get_all_tools().get(tool_name)
    method_name = tool_name.removeprefix("workspace_")
    expected = getattr(CodingWorkspaceSkill, method_name, None)
    return (
        actual is trusted
        and getattr(actual, "__self__", None) is skill
        and getattr(actual, "__func__", None) is expected
    )


_WEB_METHODS = {"web_browse": "browse", "web_search": "search"}


def allows_user_web_tool(tool_name: str, registry, *, native_tools: dict | None = None) -> bool:
    """Allow the shipped, address-checked web tools for every signed-in user.

    Only WebBrowseSkill's own bound methods qualify; a plugin or native tool
    using the same name never inherits this exception.
    """
    method_name = _WEB_METHODS.get(tool_name)
    if registry is None or method_name is None or tool_name in (native_tools or {}):
        return False
    from skills.builtin.web_browse import WebBrowseSkill

    skill = registry.get_skill("web_browse")
    if type(skill) is not WebBrowseSkill:
        return False
    trusted = skill.get_tools().get(tool_name)
    actual = registry.get_all_tools().get(tool_name)
    return (
        trusted is not None
        and actual is trusted
        and getattr(actual, "__self__", None) is skill
        and getattr(actual, "__func__", None) is getattr(WebBrowseSkill, method_name)
    )


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
                "edit",
                "glob",
                "grep",
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

    async def read(
        self,
        workspace_id: str | None = None,
        path: str = "",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict:
        store = self.store()
        if offset is None and limit is None:
            return cast(dict, store.read(selected_workspace(workspace_id), path))
        return cast(
            dict,
            store.read_lines(selected_workspace(workspace_id), path, offset or 1, limit or 2000),
        )

    async def edit(
        self,
        workspace_id: str | None = None,
        path: str = "",
        old_string: str = "",
        new_string: str = "",
        replace_all: bool = False,
        expected_sha256: str | None = None,
    ) -> dict:
        return cast(
            dict,
            self.store(edit=True).edit(
                selected_workspace(workspace_id),
                path,
                old_string,
                new_string,
                bool(replace_all),
                expected_sha256,
            ),
        )

    async def glob(self, workspace_id: str | None = None, pattern: str = "**/*") -> dict:
        return cast(dict, self.store().glob(selected_workspace(workspace_id), pattern))

    async def grep(
        self,
        workspace_id: str | None = None,
        pattern: str = "",
        path_glob: str | None = None,
        ignore_case: bool = False,
        max_matches: int = 100,
    ) -> dict:
        return cast(
            dict,
            self.store().grep(
                selected_workspace(workspace_id),
                pattern,
                path_glob,
                bool(ignore_case),
                max_matches,
            ),
        )

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
                session_id=artifact_session(session_id),
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
                "Create a persistent private project only when no suitable selected/existing project is available; call workspace_list before creating another project.",
                {"name": string},
                ["name"],
            ),
            ("list", "List the requesting user's coding projects.", {}, []),
            ("tree", "Inspect project files before modifying them.", project, ["workspace_id"]),
            (
                "read",
                "Read a project file and its hash for safe subsequent edits. With offset/limit "
                "it returns numbered lines (1-based) of large files.",
                {
                    **project,
                    "path": string,
                    "offset": {"type": "integer", "minimum": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                },
                ["workspace_id", "path"],
            ),
            (
                "edit",
                "Change a file by replacing exact text: old_string must match the file exactly "
                "(copy it from workspace_read) and be unique unless replace_all is true. Prefer "
                "this over rewriting whole files. Returns a unified diff.",
                {
                    **project,
                    "path": string,
                    "old_string": string,
                    "new_string": string,
                    "replace_all": {"type": "boolean"},
                    "expected_sha256": string,
                },
                ["workspace_id", "path", "old_string", "new_string"],
            ),
            (
                "glob",
                "Find project files by glob pattern, e.g. **/*.py or src/**/*.tsx.",
                {**project, "pattern": string},
                ["workspace_id", "pattern"],
            ),
            (
                "grep",
                "Search project text files with a regular expression; returns path, line "
                "number and text. Narrow with path_glob.",
                {
                    **project,
                    "pattern": string,
                    "path_glob": string,
                    "ignore_case": {"type": "boolean"},
                    "max_matches": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                ["workspace_id", "pattern"],
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
                "Publish an existing project code, HTML, markdown or raster image file as a saved preview artifact in the current chat. Omit session_id during chat; it is bound by the server.",
                {**project, "path": string, "session_id": string, "title": string},
                ["workspace_id", "path"],
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
