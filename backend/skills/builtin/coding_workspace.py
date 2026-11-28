"""Real agent tools for private persistent coding projects and saved artifacts."""

from __future__ import annotations

import builtins
import secrets
import shlex
from datetime import UTC, datetime
from typing import cast

from fastapi import HTTPException

from agents.events import emit
from api.coding_workspace import hardware, publish_artifact
from security.auth import TokenPayload, current_user_id, request_has_role
from workspace import forgekit, session_client
from workspace.context import artifact_session, bound_workspace_id, selected_workspace
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
SCRATCH_PROJECT = "Scratch"
# ForgeKit's reads of a project: a fixed command MIZAN writes, in the sandbox, that runs
# none of the project's code and changes none of its files (ForgeKit's own state is put
# back), so they observe like git status (agents/base.py ``_read_only_hint``).
# workspace_verify runs the project's tests (its code), so it is an execution, like
# workspace_run.
FORGEKIT_READS = frozenset({"workspace_impact", "workspace_docs_check"})
VERIFY_TIMEOUT = 600
# What a verification keeps with the files it tested (never their output).
VERIFICATION_KEPT = (
    "tree", "verdict", "passed", "commands", "counts", "test_integrity", "baseline", "forge",
    "checked_at", "sandbox",
)  # fmt: skip


def scratch_project(store: WorkspaceStore) -> str:
    """The user's private Scratch project, for running code from a plain chat."""
    for item in store.list():
        if item.get("name") == SCRATCH_PROJECT:
            return str(item["id"])
    # Running code from a chat must never fail because the user has many projects.
    return str(store.create(SCRATCH_PROJECT, reserved=True)["id"])


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
                "sandbox",
                "git",
                "checkpoint",
                "diff",
                "artifact",
                "hardware",
                "verify",
                "impact",
                "docs_check",
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
        store = self.store(edit=True)
        if workspace_id or bound_workspace_id():
            project = selected_workspace(workspace_id)
        else:
            # A plain chat has no project: run in the user's own Scratch project.
            project = scratch_project(store)
        user_id = current_user_id() or ""
        if await session_client.running(user_id, project):
            # The project's live session keeps installed packages and services.
            return cast(
                dict,
                await session_client.execute(
                    user_id, project, command, language, max(1, min(int(timeout_s), 900))
                ),
            )
        return cast(
            dict,
            await run_project(store, project, command, language, min(int(timeout_s), 120)),
        )

    async def sandbox(
        self,
        workspace_id: str | None = None,
        action: str = "status",
        port: int = 5173,
        command: str = "",
        mode: str = "base",
    ) -> dict:
        """Manage the project's server sandbox session and its dev servers."""
        self.store(edit=action not in {"status", "logs"})
        project = selected_workspace(workspace_id)
        user_id = current_user_id() or ""
        if action == "status":
            return cast(dict, await session_client.status(user_id, project))
        if action == "start":
            return cast(dict, await session_client.start(user_id, project))
        if action == "stop":
            return cast(dict, await session_client.stop(user_id, project))
        if not 1024 <= int(port) <= 65535:
            raise HTTPException(422, "port must be between 1024 and 65535")
        if action == "serve":
            if not command.strip():
                raise HTTPException(422, "command is required to serve")
            result: dict = await session_client.start_service(
                user_id, project, int(port), command, "root" if mode == "root" else "base"
            )
            result["note"] = (
                "The preview opens in the Coding workspace Preview panel (Server tab). "
                "Check workspace_sandbox action=logs if it does not load."
            )
            # The chat opens the server's preview as soon as it starts.
            await emit(
                "preview",
                {"workspace_id": project, "port": int(port), "preview_url": result["preview_url"]},
            )
            return result
        if action == "stop_service":
            return cast(dict, await session_client.stop_service(user_id, project, int(port)))
        if action == "logs":
            return cast(dict, await session_client.service_logs(user_id, project, int(port)))
        raise HTTPException(422, "Unknown sandbox action")

    async def checkpoint(
        self, workspace_id: str | None = None, message: str = "Agent checkpoint"
    ) -> dict:
        return cast(
            dict,
            self.store(edit=True).checkpoint(
                selected_workspace(workspace_id), message, kind="agent"
            ),
        )

    async def git(
        self,
        workspace_id: str | None = None,
        action: str = "status",
        message: str = "Workspace update",
    ) -> dict:
        # Reads never write: no index refresh (GIT_OPTIONAL_LOCKS=0) and nothing applied back.
        reads = {
            "status": "GIT_OPTIONAL_LOCKS=0 git status --short",
            "diff": "GIT_OPTIONAL_LOCKS=0 git diff --no-ext-diff",
            "log": "GIT_OPTIONAL_LOCKS=0 git log -10 --oneline",
        }
        if action in reads:
            store = self.store()
            project = selected_workspace(workspace_id)
            user_id = current_user_id() or ""
            if await session_client.running(user_id, project):
                return cast(
                    dict,
                    await session_client.execute(user_id, project, reads[action], "shell", 30),
                )
            return cast(
                dict,
                await run_project(store, project, reads[action], "shell", 30, apply=False),
            )
        commands = {"init": "git init"}
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

    # ── ForgeKit in the project's sandbox (workspace/forgekit.py) ─────────

    @staticmethod
    async def _forgekit(
        store: WorkspaceStore, project: str, args: builtins.list[str], *, git: str, timeout: int
    ) -> tuple[dict, str, dict]:
        """ForgeKit's JSON, the git baseline it compared with, and the run itself. In the
        live session when one runs (installed packages are there); otherwise a one-shot
        run that copies nothing back."""
        user_id = current_user_id() or ""
        mark = secrets.token_hex(16)
        session = await session_client.running(user_id, project)
        limit = max(30, min(int(timeout), 900 if session else 120))
        # ForgeKit stops 20 s before the run does, so its state is always put back.
        script = forgekit.command(args, mark, git=git, limit=limit - 20)
        if session:
            run = await session_client.execute(user_id, project, script, "shell", limit)
        else:
            run = await run_project(store, project, script, "shell", limit, apply=False)
        data, _code, baseline = forgekit.read(str(run.get("stdout", "")), mark)
        return data, baseline, run

    async def verify(
        self, workspace_id: str | None = None, timeout_s: int = VERIFY_TIMEOUT
    ) -> dict:
        """Run the project's own tests with ForgeKit and keep the verdict with the files it
        tested (their tree digest): a later edit makes a new tree, so the verdict is stale."""
        store = self.store(edit=True)
        project = selected_workspace(workspace_id)
        _tree, tested = store.content_tree(project)
        try:
            data, baseline, run = await self._forgekit(
                store, project, ["verify"], git="snapshot", timeout=int(timeout_s)
            )
            found = forgekit.verification(data)
        except forgekit.ForgeKitError as exc:
            return cast(dict, exc.result())
        tree, now = store.content_tree(project)
        moved = {path for path in tested.keys() | now.keys() if tested.get(path) != now.get(path)}
        # Bound when ForgeKit saw no change to the code while the tests ran and every file
        # that changed in the store is one the run itself wrote (its outputs), not an edit.
        bound = not found["mutated"] and moved <= set(run.get("changed_files") or [])
        result = {
            **found,
            "baseline": baseline,
            "tree": tree,
            "bound": bound,
            "checked_at": datetime.now(UTC).isoformat(timespec="microseconds"),
            "sandbox": str(run.get("sandbox") or ""),
        }
        if bound:
            store.record_verification(project, {key: result[key] for key in VERIFICATION_KEPT})
        else:
            result["note"] = (
                "The project's files changed while the tests ran, so this verdict is not "
                "bound to them and was not kept; run workspace_verify again on a quiet project"
            )
        result["recorded"] = bound
        return result

    async def impact(
        self, workspace_id: str | None = None, symbol: str | None = None, path: str | None = None
    ) -> dict:
        """The files ForgeKit's code graph predicts an edit to ``symbol`` or ``path`` touches."""
        store = self.store()
        project = selected_workspace(workspace_id)
        try:
            args = forgekit.impact_args(symbol, path)
            data, _baseline, run = await self._forgekit(
                store, project, args, git="any", timeout=120
            )
            return {**forgekit.impact(data), "sandbox": str(run.get("sandbox") or "")}
        except forgekit.ForgeKitError as exc:
            return cast(dict, exc.result())

    async def docs_check(self, workspace_id: str | None = None) -> dict:
        """The project's docs that its uncommitted changes made stale (against git's HEAD)."""
        store = self.store()
        project = selected_workspace(workspace_id)
        try:
            data, _baseline, run = await self._forgekit(
                store, project, ["docs", "sync", "--base", "HEAD"], git="require", timeout=120
            )
            return {**forgekit.docs(data), "sandbox": str(run.get("sandbox") or "")}
        except forgekit.ForgeKitError as exc:
            return cast(dict, exc.result())

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
                "Run Python, JavaScript or shell in an isolated project sandbox without host "
                "secrets; for Python pass the code as command with language python. Without a "
                "selected project it runs in the user's private Scratch project. With a running sandbox session (workspace_sandbox start) commands run "
                "there: installed packages persist and allowlisted package registries are "
                "reachable (npm, PyPI, GitHub), timeout up to 900 s. Otherwise a fresh offline "
                "container runs it (timeout up to 120 s). Returns real output and saves "
                "generated files. Never claim success when unavailable.",
                {
                    **project,
                    "command": string,
                    "language": {"type": "string", "enum": ["shell", "python", "javascript"]},
                    "timeout_s": {"type": "integer", "minimum": 1, "maximum": 900},
                },
                ["workspace_id", "command"],
            ),
            (
                "sandbox",
                "Server sandbox session for this project: start/stop/status; serve runs a "
                "dev server on a port and returns its preview URL (mode base: the server is "
                "told its base path via $MIZAN_PREVIEW_PREFIX/<port>/, e.g. "
                "`npx vite --host 127.0.0.1 --port $PORT --base $MIZAN_PREVIEW_PREFIX/$PORT/`; "
                "mode root strips that prefix for simple servers such as "
                "`python3 -m http.server $PORT --bind 127.0.0.1`); logs shows its output; "
                "stop_service ends it. Servers must listen on 127.0.0.1:$PORT.",
                {
                    **project,
                    "action": {
                        "type": "string",
                        "enum": ["status", "start", "stop", "serve", "stop_service", "logs"],
                    },
                    "port": {"type": "integer", "minimum": 1024, "maximum": 65535},
                    "command": string,
                    "mode": {"type": "string", "enum": ["base", "root"]},
                },
                ["action"],
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
            (
                "verify",
                "Run the project's own tests with ForgeKit (forge verify) in its sandbox. "
                "Returns the verdict (PASS, FAIL, INCOMPLETE, NOT_CONFIGURED when it finds no "
                "test command, SUSPECT when a change weakened the tests), each test command "
                "it ran with pass/fail counts, and the digest of the files it tested. MIZAN "
                "keeps the verdict with those files, so any later edit makes it stale. Start "
                "the sandbox session first when the tests need installed packages. Say tests "
                "pass only when the verdict is PASS.",
                {**project, "timeout_s": {"type": "integer", "minimum": 30, "maximum": 900}},
                ["workspace_id"],
            ),
            (
                "impact",
                "Before changing a shared name or file, list the project files an edit to it "
                "will probably touch (ForgeKit's code graph, forge impact). Give symbol (a "
                "function, class or Class.method) or path, not both.",
                {**project, "symbol": string, "path": string},
                ["workspace_id"],
            ),
            (
                "docs_check",
                "List the project's docs that its uncommitted changes made stale: docs that "
                "mention a name the changes touched (ForgeKit's forge docs sync, against the "
                "project's git HEAD). Needs the project's git history (workspace_git).",
                project,
                ["workspace_id"],
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
