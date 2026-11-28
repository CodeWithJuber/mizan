"""Protected paths: a change to a project's secrets, keys or CI asks a person, in every mode.

Each project keeps its own list (defaults ``.env``, ``.env.*``, ``*.pem``, ``*.key``,
``id_rsa*``, ``.git/**``, ``.github/workflows/**``), editable on the project's PATCH
route. A write or edit to one asks the person even in ``auto`` mode, is held when no one
is watching, and is refused with no one to ask; ``.git`` itself stays refused outright.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agents import events
from agents.specialized import create_agent
from api import coding_workspace as api
from security import approvals
from security.approvals import ApprovalContext, bind_approvals, collecting_held
from security.auth import TokenPayload, bind_principal, reset_principal
from skills.builtin.coding_workspace import CodingWorkspaceSkill
from skills.registry import SkillRegistry
from workspace.context import bind_workspace, reset_workspace
from workspace.store import DEFAULT_PROTECTED, WorkspaceStore, protected_match

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        (".env", ".env"),
        ("config/.env", ".env"),
        (".env.local", ".env.*"),
        ("certs/server.pem", "*.pem"),
        ("deploy/app.key", "*.key"),
        ("id_rsa", "id_rsa*"),
        ("keys/id_rsa.pub", "id_rsa*"),
        (".git/config", ".git/**"),
        (".github/workflows/ci.yml", ".github/workflows/**"),
    ],
)
def test_default_patterns_match(path, pattern):
    assert protected_match(path, DEFAULT_PROTECTED) == pattern


@pytest.mark.parametrize(
    "path",
    ["src/app.py", "environment.py", ".envrc", "README.md", "keyboard.js", "docs/.github/x.yml"],
)
def test_ordinary_files_are_not_protected(path):
    assert protected_match(path, DEFAULT_PROTECTED) is None


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    approvals._HELD_STORES.clear()
    store = WorkspaceStore(USER.user_id)
    workspace = store.create("App")["id"]
    store.write(workspace, ".env", "MODE=dev\n")
    store.write(workspace, "src/app.py", "print(1)\n")
    return store, workspace


def test_each_project_keeps_its_own_list(project):
    store, workspace = project
    assert store.protected_paths(workspace) == list(DEFAULT_PROTECTED)
    other = store.create("Other")["id"]
    saved = store.update_project(workspace, protected_paths=["secrets/**", "*.pem", "*.pem"])
    assert saved["protected_paths"] == ["secrets/**", "*.pem"]
    assert store.protected_paths(workspace) == ["secrets/**", "*.pem"]
    assert store.protected_paths(other) == list(DEFAULT_PROTECTED)
    assert store.update_project(workspace, protected_paths=[])["protected_paths"] == []
    for bad in (["../x"], ["/etc/passwd"], [""], ["a" * 300], ["x"] * 101):
        with pytest.raises(HTTPException) as refused:
            store.update_project(workspace, protected_paths=bad)
        assert refused.value.status_code == 422


def test_the_patch_route_takes_the_list(project, monkeypatch):
    store, workspace = project
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: USER
    client = TestClient(app, raise_server_exceptions=False)
    base = f"/api/workspaces/{workspace}"
    changed = client.patch(base, json={"protected_paths": [".env", "infra/**"]})
    assert changed.status_code == 200, changed.text
    assert changed.json()["protected_paths"] == [".env", "infra/**"]
    renamed = client.patch(base, json={"name": "Renamed"})
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["protected_paths"] == [".env", "infra/**"]
    listed = client.get("/api/workspaces").json()["workspaces"]
    assert {item["id"]: item["protected_paths"] for item in listed}[workspace] == [
        ".env",
        "infra/**",
    ]
    assert client.patch(base, json={}).status_code == 422
    assert client.patch(base, json={"protected_paths": ["../up"]}).status_code == 422


# ── The gate ───────────────────────────────────────────────────────────────


@pytest.fixture
def agent(project):
    store, workspace = project
    registry = SkillRegistry()
    registry.register(CodingWorkspaceSkill())
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent(
        "general", name="Katib", wali=MagicMock(), izn=izn, skill_registry=registry
    )
    agent._chat_tool_allowed = lambda name: True
    principal, bound = bind_principal(USER), bind_workspace(workspace)
    yield agent, store, workspace
    reset_workspace(bound)
    reset_principal(principal)


async def decide(decision, context, call):
    asked = []

    async def sink(kind, payload):
        if kind == "approval_request":
            asked.append(payload)
            approvals.broker.resolve(context.user_id, payload["approval_id"], decision)

    with events.bind_event_sink(sink), bind_approvals(context):
        return await call(), asked


async def test_a_protected_write_asks_even_in_auto_mode(agent):
    agent, store, workspace = agent
    context = ApprovalContext("alice", "chat", "auto", interactive=True)
    params = {"workspace_id": workspace, "path": ".env", "content": "MODE=prod\n"}

    def call():
        return agent._execute_tool_safe("workspace_write", params)

    declined, asked = await decide("deny", context, call)
    assert declined.get("declined")
    assert store.read(workspace, ".env")["content"] == "MODE=dev\n"
    assert ".env" in asked[0]["reason"] and asked[0]["preview"]["path"] == ".env"
    written, _asked = await decide("allow", context, call)
    assert "error" not in written
    assert store.read(workspace, ".env")["content"] == "MODE=prod\n"


async def test_an_ordinary_edit_in_auto_mode_asks_no_one(agent):
    agent, store, workspace = agent
    context = ApprovalContext("alice", "chat", "auto", interactive=True)
    params = {
        "workspace_id": workspace,
        "path": "src/app.py",
        "old_string": "print(1)",
        "new_string": "print(2)",
    }
    edited, asked = await decide(
        "deny", context, lambda: agent._execute_tool_safe("workspace_edit", params)
    )
    assert asked == [] and "error" not in edited
    assert store.read(workspace, "src/app.py")["content"] == "print(2)\n"


async def test_a_protected_edit_is_held_when_no_one_watches(agent):
    agent, store, workspace = agent
    params = {
        "workspace_id": workspace,
        "path": ".env",
        "old_string": "MODE=dev",
        "new_string": "MODE=prod",
    }
    with approvals.unattended("alice", "watch-1", "watcher"), collecting_held() as held:
        result = await agent._execute_tool_safe("workspace_edit", params)
    assert result["held_for_approval"] and held[0]["tool"] == "workspace_edit"
    assert store.read(workspace, ".env")["content"] == "MODE=dev\n"


async def test_a_protected_write_with_no_one_to_ask_is_refused(agent):
    agent, store, workspace = agent
    params = {"workspace_id": workspace, "path": "certs/a.pem", "content": "x"}
    result = await agent._execute_tool_safe("workspace_write", params)
    assert result.get("approval_required") and "certs/a.pem" in result["error"]


async def test_git_stays_refused_not_asked(agent):
    agent, store, workspace = agent
    context = ApprovalContext("alice", "chat", "auto", interactive=True)
    params = {"workspace_id": workspace, "path": ".git/config", "content": "x"}
    result, asked = await decide(
        "allow", context, lambda: agent._execute_tool_safe("workspace_write", params)
    )
    assert asked == [] and "git" in str(result["error"])


async def test_an_emptied_list_protects_nothing(agent):
    agent, store, workspace = agent
    store.update_project(workspace, protected_paths=[])
    context = ApprovalContext("alice", "chat", "auto", interactive=True)
    params = {"workspace_id": workspace, "path": ".env", "content": "MODE=x\n"}
    result, asked = await decide(
        "deny", context, lambda: agent._execute_tool_safe("workspace_write", params)
    )
    assert asked == [] and "error" not in result


async def test_a_covered_secret_is_never_written_back(agent):
    """A file read through Satr shows [redacted:…] where its secret was; writing that
    text back would replace the secret with the placeholder, so it is refused."""
    agent, store, workspace = agent
    store.update_project(workspace, protected_paths=[])
    params = {
        "workspace_id": workspace,
        "path": "src/app.py",
        "content": "KEY=[redacted:api_key]\n",
    }
    result = await agent._execute_tool_safe("workspace_write", params)
    assert "redacted" in result["error"]
    assert store.read(workspace, "src/app.py")["content"] == "print(1)\n"
