"""Which tool calls ask a person: read actions of action tools, and the diff a change shows.

``workspace_git`` and ``workspace_sandbox`` take an ``action``; status, diff, log and
logs only observe, so they run without a prompt and in plan mode. "Always" allows one
action of such a tool, not all of them. An approval prompt for a project edit or write
carries the diff the change would make.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from agents import events
from agents.specialized import create_agent
from security import approvals
from security.approvals import ApprovalContext, always_key, bind_approvals, tool_category
from security.auth import TokenPayload, bind_principal, reset_principal
from workspace.context import bind_workspace, reset_workspace
from workspace.store import WorkspaceStore

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")


@pytest.mark.parametrize(
    ("tool", "params", "category"),
    [
        ("workspace_git", {"action": "status"}, "read"),
        ("workspace_git", {"action": "diff"}, "read"),
        ("workspace_git", {"action": "log"}, "read"),
        ("workspace_git", {}, "read"),  # the tool's default action is status
        ("workspace_git", {"action": "commit", "message": "x"}, "execute"),
        ("workspace_git", {"action": "init"}, "execute"),
        ("workspace_sandbox", {"action": "status"}, "read"),
        ("workspace_sandbox", {"action": "logs", "port": 5173}, "read"),
        ("workspace_sandbox", {"action": "serve", "command": "npm run dev"}, "execute"),
        ("workspace_sandbox", {"action": "start"}, "execute"),
        ("workspace_edit", {"path": "a.py"}, "edit"),
        ("workspace_read", {"path": "a.py"}, "read"),
        ("workspace_run", {"command": "ls"}, "execute"),
    ],
)
def test_the_action_decides_whether_a_call_only_observes(tool, params, category):
    assert tool_category(tool, params=params) == category


def test_reads_never_ask_and_plan_mode_allows_them():
    for mode in ("ask", "auto_edits", "plan"):
        context = ApprovalContext("u", "s", mode)
        assert not context.needs_approval("workspace_git", params={"action": "status"})
        assert not context.blocks("workspace_sandbox", params={"action": "logs"})
    ask = ApprovalContext("u", "s", "ask")
    assert ask.needs_approval("workspace_git", params={"action": "commit"})
    assert ApprovalContext("u", "s", "plan").blocks("workspace_git", params={"action": "commit"})


def test_always_allows_one_action_not_the_whole_tool():
    context = ApprovalContext("u", "s", "ask")
    commit = {"action": "commit", "message": "save"}
    context.always.add(always_key("workspace_git", commit))
    assert always_key("workspace_git", commit) == "workspace_git:commit"
    assert not context.needs_approval("workspace_git", params=commit)
    assert context.needs_approval("workspace_git", params={"action": "init"})
    assert always_key("workspace_run", {"command": "ls"}) == "workspace_run"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    store = WorkspaceStore(USER.user_id)
    workspace = store.create("App")["id"]
    store.write(workspace, "app.js", "const theme = 'light';\nrender(theme);\n")
    principal, selected = bind_principal(USER), bind_workspace(workspace)
    yield store, workspace
    reset_workspace(selected)
    reset_principal(principal)


def test_preview_is_the_diff_the_change_would_make(project):
    store, workspace = project
    edit = {"path": "app.js", "old_string": "'light'", "new_string": "'dark'"}
    preview = store.preview_change(workspace, "workspace_edit", edit)
    assert preview["new_file"] is False and preview["truncated"] is False
    assert "-const theme = 'light';" in preview["diff"]
    assert "+const theme = 'dark';" in preview["diff"]
    assert store.read(workspace, "app.js")["content"].startswith("const theme = 'light'")
    created = store.preview_change(
        workspace, "workspace_write", {"path": "style.css", "content": "body {}\n"}
    )
    assert created["new_file"] is True and "+body {}" in created["diff"]
    # A change that would be refused shows no preview (the prompt still shows the input).
    assert store.preview_change(workspace, "workspace_edit", {**edit, "old_string": "x"}) is None
    assert store.preview_change(workspace, "workspace_write", {"path": ".git/config"}) is None


async def test_the_approval_prompt_carries_the_preview(project):
    store, workspace = project
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Preview", wali=MagicMock(), izn=izn)
    agent._chat_tool_allowed = lambda name: True
    seen = []

    async def sink(kind, payload):
        seen.append((kind, payload))
        if kind == "approval_request":
            approvals.broker.resolve(USER.user_id, payload["approval_id"], "deny")

    edit = {"path": "app.js", "old_string": "'light'", "new_string": "'dark'"}
    with events.bind_event_sink(sink), bind_approvals(ApprovalContext(USER.user_id, "s", "ask")):
        result = await agent._execute_tool_safe("workspace_edit", edit)
    await asyncio.sleep(0)
    assert result["declined"] is True
    request = next(payload for kind, payload in seen if kind == "approval_request")
    assert request["category"] == "edit"
    assert "+const theme = 'dark';" in request["preview"]["diff"]
    assert store.read(workspace, "app.js")["content"].startswith("const theme = 'light'")
