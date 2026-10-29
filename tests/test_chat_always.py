""" "Always in this chat" holds for the chat's later messages, can be revoked, and is
erased with the chat.

The web chat binds ``approvals.chat_context``: it is interactive, seeds what the person
allowed before in this chat (``chat_always`` in held_actions.db) and keeps new grants.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from agents import events
from memory.dhikr import DhikrMemorySystem
from security import approvals
from security.approvals import bind_approvals, chat_always_store, chat_context, request_approval
from security.auth import MizanAuth


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


async def allow_always(context, tool, params):
    async def sink(kind, payload):
        if kind == "approval_request":
            approvals.broker.resolve(context.user_id, payload["approval_id"], "always")

    with events.bind_event_sink(sink), bind_approvals(context):
        return await request_approval(context, tool, params)


async def test_always_carries_to_the_next_message_of_the_same_chat_only(data):
    first = chat_context("alice", "chat-1", "ask")
    assert first.interactive and first.persist_always
    assert await allow_always(first, "workspace_run", {"command": "npm test"}) == "always"
    assert not first.needs_approval("workspace_run")

    later = chat_context("alice", "chat-1", "ask")  # the chat's next message
    assert not later.needs_approval("workspace_run")
    assert chat_context("alice", "chat-2", "ask").needs_approval("workspace_run")
    assert chat_context("bob", "chat-1", "ask").needs_approval("workspace_run")
    listed = chat_always_store().list("alice", "chat-1")
    assert [item["tool"] for item in listed] == ["workspace_run"]


async def test_revoking_applies_to_a_run_going_on_now(data):
    running = chat_context("alice", "chat-1", "ask")
    await allow_always(running, "workspace_git", {"action": "commit", "message": "x"})
    assert not running.needs_approval("workspace_git", params={"action": "commit"})
    assert chat_always_store().remove("alice", "chat-1", "workspace_git:commit")
    assert running.needs_approval("workspace_git", params={"action": "commit"})
    assert not chat_always_store().remove("alice", "chat-1", "workspace_git:commit")


@pytest.fixture
def api(data, monkeypatch):
    import api.main as main

    memory = DhikrMemorySystem(str(data / "memory.db"))
    auth = MizanAuth("always-test-signing-key-" * 4, data_dir=str(data / "users"))
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
    return main, TestClient(main.app), users, tokens, memory


def test_list_revoke_and_erase_with_the_chat(api):
    main, client, users, tokens, memory = api
    amina = users["amina"].id
    asyncio.run(memory.authorize_session("chat-1", amina, create=True))
    asyncio.run(memory.save_message("chat-1", "user", "build it"))
    chat_always_store().add(amina, "chat-1", "workspace_run")
    chat_always_store().add(amina, "chat-1", "workspace_git:commit")

    listed = client.get("/api/chat/chat-1/always", headers=tokens["amina"]).json()
    assert [item["tool"] for item in listed["always"]] == ["workspace_run", "workspace_git:commit"]
    assert client.get("/api/chat/chat-1/always", headers=tokens["other"]).status_code == 404
    assert (
        client.delete("/api/chat/chat-1/always/workspace_run", headers=tokens["other"]).status_code
        == 404
    )
    revoked = client.delete("/api/chat/chat-1/always/workspace_run", headers=tokens["amina"])
    assert revoked.json() == {"session_id": "chat-1", "revoked": "workspace_run"}
    again = client.delete("/api/chat/chat-1/always/workspace_run", headers=tokens["amina"])
    assert again.status_code == 404

    erased = client.delete("/api/chat/chat-1", headers=tokens["amina"])
    assert erased.status_code == 200, erased.text
    assert erased.json()["removed"]["always allowed"] == 1
    assert chat_always_store().keys(amina, "chat-1") == set()


def test_the_web_chat_seeds_what_was_allowed_before(api, monkeypatch):
    main, client, users, tokens, memory = api
    amina = users["amina"].id
    chat_always_store().add(amina, "chat-1", "workspace_run")
    seen = []

    class Agent:
        id, name, ai_model, max_tool_turns = "a", "Khalifah", "test", 10
        _llm_calls: list = []
        _last_tool_results: list = []

        async def execute(self, content, context, **callbacks):
            seen.append(approvals.current_approvals())
            return {"success": True, "result": "ok", "usage": {}}

    monkeypatch.setattr(main, "active_agents", {"a": Agent()})
    body = {
        "session_id": "chat-1",
        "content": "run the tests",
        "request_id": str(uuid.uuid4()),
        "permission_mode": "ask",
    }
    assert client.post("/api/chat/stream", json=body, headers=tokens["amina"]).status_code == 200
    (context,) = seen
    assert context.interactive and context.persist_always
    assert "workspace_run" in context.always
