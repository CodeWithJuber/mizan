"""Niyyah ("actions are by intentions", Bukhari 1): a project or watcher keeps its
goal, each run's work is scored against it, and a CUSUM notes sustained drift
under the answer. It never blocks."""

from __future__ import annotations

import pytest

from tadbir import niyyah

OWNER = "user-amina"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def write(path: str, content: str = "x") -> dict:
    return {"tool": "workspace_write", "category": "edit", "ok": True,
            "params": {"path": path, "content": content}}  # fmt: skip


def test_a_single_hit_is_on_goal_and_more_hits_raise_confidence():
    goal = niyyah.goal_concepts("A todo list app with dark mode")
    assert niyyah.on_goal_score(goal, niyyah.concepts("src/TodoList.jsx")) >= niyyah.ON_GOAL_P
    two = niyyah.on_goal_score(goal, niyyah.concepts("darkMode toggle for the todo list"))
    assert two > niyyah.ON_GOAL_P
    assert niyyah.on_goal_score(goal, niyyah.concepts("billing/invoice.py")) == 0.0
    # A morphological variant meets its goal word ("valid" → "validation"), a
    # mere substring does not ("port" is not "report").
    assert niyyah.on_goal_score({"valid"}, {"validation"}) > 0
    assert niyyah.on_goal_score({"port"}, {"report"}) == 0.0


def test_cusum_alarms_on_sustained_drift_not_on_one_step():
    assert not niyyah.cusum([1.0])["alarm"]  # one exploratory step drains back
    assert not niyyah.cusum([1.0, 0.0, 0.0, 1.0])["alarm"]
    chart = niyyah.cusum([1.0, 1.0])
    assert chart["alarm"] and chart["first_alarm"] == 1
    assert not niyyah.cusum([0.3] * 50)["alarm"]  # below the allowance k = 0.35


def test_only_work_that_changes_something_is_scored():
    calls = [
        {"tool": "workspace_read", "category": "read", "ok": True, "params": {"path": "a.py"}},
        write("src/todo.js"),
        write("billing/invoice.py"),
    ]
    found = niyyah.drift("A todo list app", "keep going", calls)
    assert found["items"] == 2 and found["score"] == 0.5
    assert found["off_goal"] == ["workspace_write billing/invoice.py"]
    assert niyyah.drift("A todo list app", "anything", [])["score"] == 0.0  # nothing moved
    # The request is an overlap signal too.
    on = niyyah.drift("A todo list app", "store each todo in a file", [write("store.py")])
    assert on["score"] == 0.0


def test_a_projects_drift_accumulates_across_runs_and_is_only_a_note(data):
    from workspace.store import WorkspaceStore

    project = WorkspaceStore(OWNER).create("Todo")
    WorkspaceStore(OWNER).set_goal(project["id"], "A todo list app with dark mode")
    off = [write("billing/invoice.py"), write("billing/tax.py")]
    first = niyyah.note(
        OWNER, workspace_id=project["id"], history=[], task="add billing", calls=off
    )
    assert first["goal_source"] == "stated" and first["drift"] == 1.0 and not first["alarm"]
    second = niyyah.note(
        OWNER, workspace_id=project["id"], history=[], task="more billing", calls=off
    )
    assert second["alarm"] and second["cusum"] > niyyah.H
    assert second["off_goal"] == [
        "workspace_write billing/invoice.py",
        "workspace_write billing/tax.py",
    ]
    # Work back on the goal drains the chart.
    back = niyyah.note(
        OWNER,
        workspace_id=project["id"],
        history=[],
        task="dark mode for the todo list",
        calls=[write("src/darkMode.css")],
    )
    assert back["drift"] == 0.0 and back["cusum"] < second["cusum"]


def test_with_no_stated_goal_the_chats_first_request_is_the_goal(data):
    from workspace.store import WorkspaceStore

    project = WorkspaceStore(OWNER).create("Quiz")
    history = [{"role": "user", "content": "Build a quiz game about planets"}]
    found = niyyah.note(
        OWNER, workspace_id=project["id"], history=history, task="go on",
        calls=[write("src/planets.js")],
    )  # fmt: skip
    assert found["goal_source"] == "first_request" and found["drift"] == 0.0
    assert "planets" in found["goal"]
    # Outside a project or watcher there is no goal to keep.
    assert niyyah.note(OWNER, workspace_id=None, history=history, task="x", calls=[]) is None


def test_a_watchers_goal_is_its_own_or_its_task(data):
    from automation import muraqabah

    with muraqabah.watching({"id": "w1", "task": "Summarise new Quran tafsir posts", "goal": ""}):
        found = niyyah.note(OWNER, workspace_id=None, history=[], task="Summarise new Quran "
                            "tafsir posts", calls=[write("notes/tafsir.md")])  # fmt: skip
    assert found["scope"] == "watcher" and found["goal_source"] == "task"
    assert found["drift"] == 0.0


def test_the_goal_is_on_the_project_and_watcher_records(data, tmp_path):
    from automation import muraqabah
    from workspace.store import WorkspaceStore

    store = WorkspaceStore(OWNER)
    project = store.create("Todo")
    assert store.set_goal(project["id"], "  A todo app  ")["goal"] == "A todo app"
    assert store.set_goal(project["id"], "")["goal"] == ""
    watchers = muraqabah.Store(str(tmp_path / "m.db"))
    made = watchers.add(OWNER, "Tafsir", {"kind": "daily", "time": "08:00"}, "Summarise posts")
    assert made["goal"] == ""
    assert watchers.update("user-bilal", made["id"], goal="Learn tafsir") is None  # not theirs
    assert watchers.update(OWNER, made["id"], goal="Learn tafsir daily")["goal"] == (
        "Learn tafsir daily"
    )


def test_an_uncreatable_data_dir_still_notes_without_memory(monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", "/proc/mizan-nope")
    from automation import muraqabah

    with muraqabah.watching({"id": "w1", "task": "Summarise tafsir posts", "goal": ""}):
        found = niyyah.note(OWNER, workspace_id=None, history=[], task="x",
                            calls=[write("billing/invoice.py")])  # fmt: skip
    assert found["drift"] == 1.0 and found["cusum"] == pytest.approx(0.65)


def test_related_reads_a_request_against_what_a_hand_off_was_about():
    assert niyyah.related("Hyderabad prayer times", "What are the prayer times today?")
    assert not niyyah.related("Hyderabad prayer times", "Write a poem about rain")
    assert not niyyah.related("", "anything")


def test_the_api_patches_a_projects_goal_and_keeps_its_name(data, monkeypatch):
    from fastapi.testclient import TestClient

    import api.main as main
    from security.auth import MizanAuth

    auth = MizanAuth("niyyah-test-signing-key-" * 4, data_dir=str(data / "users"))
    amina = auth.create_user("amina", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    client = TestClient(main.app)
    mine = {"Authorization": "Bearer " + auth.create_token(amina)}
    made = client.post("/api/workspaces", json={"name": "Todo"}, headers=mine).json()
    patched = client.patch(
        f"/api/workspaces/{made['id']}", json={"goal": "A todo app"}, headers=mine
    )
    assert patched.status_code == 200 and patched.json()["goal"] == "A todo app"
    renamed = client.patch(f"/api/workspaces/{made['id']}", json={"name": "Todos"}, headers=mine)
    assert renamed.json()["name"] == "Todos" and renamed.json()["goal"] == "A todo app"
    assert client.patch(f"/api/workspaces/{made['id']}", json={}, headers=mine).status_code == 422


async def test_a_run_in_a_project_carries_the_note_and_leaves_a_hand_off(data, monkeypatch):
    from unittest.mock import MagicMock

    from agents.specialized import create_agent
    from memory import azm
    from providers import BaseLLMProvider, ContentBlock, LLMResponse
    from security.auth import TokenPayload, bind_principal, reset_principal
    from workspace.context import bind_workspace, reset_workspace
    from workspace.store import WorkspaceStore

    user = TokenPayload(OWNER, "Amina", ["user"], 9999999999, 0, "t")
    project = WorkspaceStore(OWNER).create("Todo")
    WorkspaceStore(OWNER).set_goal(project["id"], "A todo list app with dark mode")
    schema = {
        "name": "workspace_write",
        "description": "Write a file in the project.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    }

    def turn(name, call_id, **arguments):
        return LLMResponse(
            content=[ContentBlock(type="tool_use", id=call_id, name=name, input=arguments)],
            stop_reason="tool_use",
        )

    class Scripted(BaseLLMProvider):
        provider_name = "fixture"

        def __init__(self, path):
            self.replies = [
                turn("mizan_discover_tools", "d", names=["workspace_write"]),
                turn("workspace_write", "w", path=path, content="x = 1\n"),
                LLMResponse(
                    content=[ContentBlock(type="text", text="Done.")], stop_reason="end_turn"
                ),
            ]

        def create(self, **kwargs):
            return self.replies.pop(0)

    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Niyyah", wali=MagicMock(), izn=izn)
    agent._chat_tool_allowed = lambda name: True
    written = []

    async def write(**params):
        written.append(params["path"])
        return {"ok": True}

    agent.tools["workspace_write"] = write
    monkeypatch.setattr(agent, "get_tool_schemas", lambda: [schema])
    principal, selected = bind_principal(user), bind_workspace(project["id"])
    try:
        usages = []
        for path in ("billing/invoice.py", "billing/tax.py"):
            agent.ai_client, agent.ai_model = Scripted(path), "fixture"
            result = await agent.execute(f"write {path}", {"session_id": "c1"})
            usages.append(result["usage"].get("niyyah"))
    finally:
        reset_workspace(selected)
        reset_principal(principal)
    assert written == ["billing/invoice.py", "billing/tax.py"]
    assert usages[0]["drift"] == 1.0 and not usages[0]["alarm"]
    assert usages[1]["alarm"] and usages[1]["goal"] == "A todo list app with dark mode"
    snapshot = azm.handoff(OWNER, f"project:{project['id']}")
    assert snapshot and "A todo list app with dark mode" in snapshot["text"]
    assert "write billing/tax.py" in snapshot["text"]
