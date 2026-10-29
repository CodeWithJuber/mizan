"""A chat bound to a project: binding, a checkpoint before each turn, and new projects.

``PATCH /api/chat/{id}`` binds or unbinds; ``POST /api/chat/stream`` uses the chat's
project when the message names none, saves the project before the turn (the user
message records that checkpoint for "Rewind"), keeps the project busy while it runs,
and binds a project MIZAN made in a chat that had none.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from memory.dhikr import DhikrMemorySystem
from security.auth import MizanAuth
from workspace import context as workspace_context
from workspace.store import WorkspaceStore


class ProjectAgent:
    """Records the project bound while it runs; may report a project it made."""

    id = "project-agent"
    name = "Khalifah"
    ai_model = "test"
    max_tool_turns = 10

    def __init__(self):
        self.seen: list[tuple[str | None, bool]] = []
        self.made: str | None = None
        self.owner = ""
        self._llm_calls: list = []
        self._last_tool_results: list = []

    async def execute(self, content, context, **callbacks):
        bound = workspace_context.bound_workspace_id()
        self.seen.append((bound, bool(bound) and workspace_context.busy(self.owner, bound)))
        await callbacks["stream_callback"]("done")
        result = {"success": True, "result": "done", "usage": {"model": "test"}}
        if self.made:
            result["workspace_id"] = self.made
        return result


@pytest.fixture
def api(tmp_path, monkeypatch):
    import api.main as main

    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("binding-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    users = {name: auth.create_user(name, "pw", roles=["user"]) for name in ("amina", "other")}
    tokens = {
        name: {"Authorization": "Bearer " + auth.create_token(user)} for name, user in users.items()
    }
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setenv("DB_PATH", memory.db_path)
    monkeypatch.setattr(main, "active_sessions", {})
    monkeypatch.setattr(main, "_stream_sessions", set())
    monkeypatch.setattr(main, "_stream_runs", {})
    monkeypatch.setattr(main, "chat_agent_for", AsyncMock(side_effect=lambda user, agent: agent))
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock(), send=AsyncMock()))
    agent = ProjectAgent()
    agent.owner = users["amina"].id
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    return main, TestClient(main.app), tokens, users, memory, agent


def send(client, token, session="chat-1", **extra):
    body = {"session_id": session, "content": "add dark mode", "request_id": str(uuid.uuid4())}
    response = client.post("/api/chat/stream", json={**body, **extra}, headers=token)
    assert response.status_code == 200, response.text
    events = []
    for frame in response.text.split("\n\n"):
        data = [line[6:] for line in frame.splitlines() if line.startswith("data: ")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events


def project(user, name="App", files=None):
    store = WorkspaceStore(user.id)
    created = store.create(name)["id"]
    for path, content in (files or {"index.html": "<h1>hi</h1>\n"}).items():
        store.write(created, path, content)
    return store, created


def test_patch_binds_unbinds_and_lists_a_chats_project(api):
    main, client, tokens, users, memory, _ = api
    _, mine = project(users["amina"])
    _, theirs = project(users["other"])
    send(client, tokens["amina"], "chat-1")
    send(client, tokens["amina"], "chat-2")

    bound = client.patch("/api/chat/chat-1", json={"workspace_id": mine}, headers=tokens["amina"])
    assert bound.status_code == 200 and bound.json() == {
        "session_id": "chat-1",
        "workspace_id": mine,
    }
    rows = client.get("/api/chat/sessions/list", headers=tokens["amina"]).json()["sessions"]
    assert {row["session_id"]: row["workspace_id"] for row in rows} == {
        "chat-1": mine,
        "chat-2": None,
    }
    only = client.get(
        "/api/chat/sessions/list", params={"workspace_id": mine}, headers=tokens["amina"]
    ).json()["sessions"]
    assert [row["session_id"] for row in only] == ["chat-1"]
    assert client.get("/api/chat/chat-1", headers=tokens["amina"]).json()["workspace_id"] == mine

    # Someone else's project, or someone else's chat, is not found.
    assert (
        client.patch(
            "/api/chat/chat-2", json={"workspace_id": theirs}, headers=tokens["amina"]
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/chat/chat-1", json={"workspace_id": theirs}, headers=tokens["other"]
        ).status_code
        == 404
    )
    # Title and project together; then null unbinds.
    both = client.patch(
        "/api/chat/chat-2", json={"title": "Site", "workspace_id": mine}, headers=tokens["amina"]
    )
    assert both.json() == {"session_id": "chat-2", "workspace_id": mine, "title": "Site"}
    cleared = client.patch("/api/chat/chat-1", json={"workspace_id": None}, headers=tokens["amina"])
    assert cleared.json() == {"session_id": "chat-1", "workspace_id": None}
    assert client.get("/api/chat/chat-1", headers=tokens["amina"]).json()["workspace_id"] is None
    for body in ({}, {"title": None}, {"workspace_id": ""}):
        refused = client.patch("/api/chat/chat-2", json=body, headers=tokens["amina"])
        assert refused.status_code == 422, body


def test_a_bound_chat_works_on_its_project_with_a_checkpoint_before_each_turn(api):
    main, client, tokens, users, memory, agent = api
    store, mine = project(users["amina"])
    first = send(client, tokens["amina"], "chat-1", workspace_id=mine)
    # Sending with a project binds the chat; the next message needs no id.
    second = send(client, tokens["amina"], "chat-1")
    assert agent.seen == [(mine, True), (mine, True)]  # bound and busy while it ran
    assert not workspace_context.busy(users["amina"].id, mine)

    marks = [event for event in first + second if event["type"] == "checkpoint"]
    assert [mark["reused"] for mark in marks] == [False, True]
    assert marks[0]["checkpoint_id"] == marks[1]["checkpoint_id"]  # nothing changed between
    saved = store.checkpoints(mine)
    assert len(saved) == 1 and saved[0]["kind"] == "turn"
    assert saved[0]["message"] == "Before a chat message"  # never the chat's words
    assert saved[0]["origin"]["session_id"] == "chat-1"
    done = next(event for event in second if event["type"] == "chat_complete")
    assert done["workspace_id"] == mine
    assert done["checkpoint"] == {"workspace_id": mine, "id": marks[1]["checkpoint_id"]}
    history = client.get("/api/chat/chat-1", headers=tokens["amina"]).json()["messages"]
    asked = [m for m in history if m["role"] == "user"]
    assert all(m["metadata"]["checkpoint"]["workspace_id"] == mine for m in asked)


def test_a_deleted_project_unbinds_the_chat_and_the_chat_goes_on(api):
    main, client, tokens, users, memory, agent = api
    store, mine = project(users["amina"])
    send(client, tokens["amina"], "chat-1", workspace_id=mine)
    store.remove(mine)
    events = send(client, tokens["amina"], "chat-1")
    assert agent.seen[-1] == (None, False)
    assert any(event["type"] == "chat_complete" for event in events)
    assert not any(event["type"] == "checkpoint" for event in events)
    assert client.get("/api/chat/chat-1", headers=tokens["amina"]).json()["workspace_id"] is None
    # Naming a project that is gone is refused, not ignored.
    body = {"session_id": "chat-1", "content": "x", "workspace_id": mine}
    gone = client.post("/api/chat/stream", json=body, headers=tokens["amina"])
    assert gone.status_code == 404


def test_a_project_mizan_makes_becomes_the_chats_project(api):
    main, client, tokens, users, memory, agent = api
    _, made = project(users["amina"], "Todo")
    agent.made = made
    events = send(client, tokens["amina"], "chat-new")
    assert next(e for e in events if e["type"] == "chat_complete")["workspace_id"] == made
    assert client.get("/api/chat/chat-new", headers=tokens["amina"]).json()["workspace_id"] == made
    agent.made = None
    send(client, tokens["amina"], "chat-new")
    assert agent.seen[-1] == (made, True)


def test_a_bound_project_cannot_be_deleted_or_restored_mid_run(api):
    _, _, _, users, _, _ = api
    store, mine = project(users["amina"])
    saved = store.checkpoint(mine, "x")
    from api import coding_workspace

    app_client = TestClient(_workspace_app(coding_workspace, users["amina"]))
    with workspace_context.running_in(users["amina"].id, mine):
        assert app_client.delete(f"/api/workspaces/{mine}").status_code == 409
        restore = app_client.post(
            f"/api/workspaces/{mine}/checkpoints/{saved['id']}/restore", json={}
        )
        assert restore.status_code == 409
    assert app_client.delete(f"/api/workspaces/{mine}").status_code == 200


def _workspace_app(module, user):
    from fastapi import FastAPI

    from security.auth import TokenPayload

    app = FastAPI()
    app.include_router(module.router)
    principal = TokenPayload(user.id, user.username, ["user"], 9999999999, 0, "t")
    app.dependency_overrides[module.require_auth] = lambda: principal
    return app
