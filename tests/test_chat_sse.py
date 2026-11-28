"""SSE chat isolation, durable retries, delivery bounds and real disconnects."""

import asyncio
import contextlib
import json
import threading
import time
import uuid
from contextvars import ContextVar
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from api.chat_stream import ChatEventChannel, ChatStreamLedger, StreamDeliveryError
from memory.dhikr import DhikrMemorySystem
from security.auth import MizanAuth, current_user_id


class StreamingAgent:
    id = "sse-agent"
    name = "Khalifah"
    ai_model = "ruh-remote"
    max_tool_turns = 10

    def __init__(self):
        self.calls = []
        self._llm_calls = []
        self._last_tool_results = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False
        self.failure = False
        self.artifacts = []

    async def execute(self, content, context, **callbacks):
        self.calls.append((content, context, current_user_id(), callbacks["model_override"]))
        self.started.set()
        try:
            await callbacks["thinking_callback"]("generation", "Preparing", 0.8, {"ok": True})
            await callbacks["stream_callback"]("", chunk_type="tool_use", tool_name="read_file")
            await callbacks["stream_callback"]("مرحبا\n")
            if self.block:
                await self.release.wait()
            if self.failure:
                raise RuntimeError("private provider diagnostic should not reach the client")
            await callbacks["stream_callback"]("world")
            return {
                "success": True,
                "result": "مرحبا\nworld",
                "usage": {"model": "observed-ruh", "input_tokens": 9, "output_tokens": 2},
                "artifacts": self.artifacts,
            }
        finally:
            if self.block and not self.release.is_set():
                self.cancelled.set()


async def stop_run(main, principal, session="session-a"):
    """The Stop button: cancel the run, then wait until its cleanup finished."""
    lease = main._stream_runs.get((principal.user_id, session))
    stopped = await main.stop_chat(session, main.StopChatRequest(), principal)
    if lease is not None and lease.producer is not None:
        try:
            await asyncio.wait_for(asyncio.shield(lease.producer), 2)
        except asyncio.CancelledError:
            pass
    return stopped


@pytest.fixture
def api(tmp_path, monkeypatch):
    import api.main as main

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("sse-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    users = {
        name: auth.create_user(name, "test-password", roles=["user"]) for name in ("alice", "bob")
    }
    tokens = {name: auth.create_token(user) for name, user in users.items()}
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setenv("DB_PATH", memory.db_path)
    monkeypatch.setattr(main, "active_sessions", {})
    monkeypatch.setattr(main, "_stream_sessions", set())
    monkeypatch.setattr(main, "_stream_runs", {})
    monkeypatch.setattr(main, "chat_agent_for", AsyncMock(side_effect=lambda user, agent: agent))
    manager = SimpleNamespace(broadcast=AsyncMock(), send=AsyncMock())
    monkeypatch.setattr(main, "manager", manager)
    agent = StreamingAgent()
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    return main, TestClient(main.app), tokens, users, memory, agent, manager


def headers(token):
    return {"Authorization": "Bearer " + token}


def message(session="session-a", **overrides):
    return {"session_id": session, "content": "hello", "request_id": str(uuid.uuid4()), **overrides}


def frames(text):
    result = []
    for frame in text.split("\n\n"):
        data = [line[6:] for line in frame.splitlines() if line.startswith("data: ")]
        if data:
            payload = json.loads("\n".join(data))
            assert "event: " + payload["type"] in frame
            result.append(payload)
    return result


async def test_active_run_conflict_preserves_both_request_identities_and_owner_scope(api):
    main, client, tokens, users, _, agent, _ = api
    agent.block = True
    original = message()
    principal = main.auth.verify_token(tokens["alice"])
    response = await main.stream_chat(main.StreamChatMessage(**original), principal)
    await anext(response.body_iterator)
    await asyncio.wait_for(agent.started.wait(), 1)
    lease = main._stream_runs[(users["alice"].id, "session-a")]
    lease.started -= 3600  # Age cannot expire live work or admit another POST.
    rejected = message()
    try:
        with pytest.raises(HTTPException) as error:
            await main.stream_chat(main.StreamChatMessage(**rejected), principal)
        detail = error.value.detail
        assert error.value.status_code == 409 and detail["code"] == "chat_stream_active"
        assert detail["request_id"] == rejected["request_id"]
        assert detail["active_request"]["request_id"] == original["request_id"]
        assert detail["active_request"]["elapsed_ms"] >= 3_600_000
        state = client.get("/api/chat/session-a/run-state", headers=headers(tokens["alice"])).json()
        assert (
            state["state"] == "active" and state["request"]["request_id"] == original["request_id"]
        )
        assert (
            client.get("/api/chat/session-a/run-state", headers=headers(tokens["bob"])).status_code
            == 404
        )
        assert state["request"]["provider_attempt_count"] is None
        wrong_request = client.get(
            "/api/chat/session-a/run-state",
            params={"request_id": rejected["request_id"]},
            headers=headers(tokens["alice"]),
        ).json()
        assert wrong_request["state"] == "active"
        assert wrong_request["request"]["request_id"] == original["request_id"]
        assert len(agent.calls) == 1
    finally:
        await response.close()
    # The reader is gone, but the run is the server's: it is still active.
    assert main._stream_sessions and not agent.cancelled.is_set()
    assert (await stop_run(main, principal))["stopped"] is True
    assert not main._stream_sessions and not main._stream_runs
    state = client.get(
        "/api/chat/session-a/run-state",
        params={"request_id": original["request_id"]},
        headers=headers(tokens["alice"]),
    ).json()
    assert state["state"] == "terminal" and state["history_saved"] is True


async def test_a_stopped_run_holds_its_lease_until_cleanup_finished(api):
    main, _, tokens, _, _, agent, _ = api
    cleanup_started, cleanup_release = asyncio.Event(), asyncio.Event()
    original_execute = agent.execute
    agent.block = True

    async def slow_cleanup(*args, **kwargs):
        try:
            return await original_execute(*args, **kwargs)
        except asyncio.CancelledError:
            cleanup_started.set()
            await cleanup_release.wait()
            raise

    agent.execute = slow_cleanup
    principal = main.auth.verify_token(tokens["alice"])
    response = await main.stream_chat(main.StreamChatMessage(**message()), principal)
    await anext(response.body_iterator)
    await asyncio.wait_for(agent.started.wait(), 1)
    await response.close()
    assert not cleanup_started.is_set()  # closing the stream stops nothing
    stopping = asyncio.create_task(stop_run(main, principal))
    try:
        await asyncio.wait_for(cleanup_started.wait(), 1)
        assert main._stream_sessions and main._stream_runs
        assert not stopping.done()
    finally:
        cleanup_release.set()
        await asyncio.wait_for(stopping, 2)
    assert not main._stream_sessions and not main._stream_runs


async def test_a_dropped_connection_does_not_stop_the_run_and_its_answer_is_saved(api):
    main, client, tokens, _, memory, agent, _ = api
    agent.block = True
    principal = main.auth.verify_token(tokens["alice"])
    body = message()
    response = await main.stream_chat(main.StreamChatMessage(**body), principal)
    await anext(response.body_iterator)
    await asyncio.wait_for(agent.started.wait(), 1)
    lease = main._stream_runs[(principal.user_id, "session-a")]
    await response.close()  # the phone changed networks
    state = client.get("/api/chat/session-a/run-state", headers=headers(tokens["alice"])).json()
    assert state["state"] == "active"
    # Only the owner can stop it, and only the run it names.
    with pytest.raises(HTTPException):
        await main.stop_chat(
            "session-a", main.StopChatRequest(), main.auth.verify_token(tokens["bob"])
        )
    other = main.StopChatRequest(request_id=uuid.uuid4())
    assert (await main.stop_chat("session-a", other, principal)) == {"stopped": False}
    assert not lease.producer.done()
    agent.release.set()
    await asyncio.wait_for(asyncio.shield(lease.producer), 2)
    assert not agent.cancelled.is_set()
    assert not main._stream_sessions and not main._stream_runs
    stored = await memory.get_messages("session-a")
    assert stored[-1]["content"] == "مرحبا\nworld"
    assert stored[-1]["metadata"]["status"] == "complete"
    state = client.get(
        "/api/chat/session-a/run-state",
        params={"request_id": body["request_id"]},
        headers=headers(tokens["alice"]),
    ).json()
    assert state["state"] == "terminal" and state["history_saved"] is True
    # Stop after the end, or for another chat, does nothing.
    assert (await main.stop_chat("session-a", main.StopChatRequest(), principal)) == {
        "stopped": False
    }


async def test_restart_receipt_is_unknown_and_same_uuid_is_never_replayed(api):
    main, client, tokens, users, memory, agent, _ = api
    body = message()
    await memory.authorize_session("session-a", users["alice"].id, create=True)
    ledger = ChatStreamLedger(memory._get_conn, memory._release_conn)
    ledger.claim(users["alice"].id, body["request_id"], "session-a", "old-message", body)
    ledger.update(users["alice"].id, body["request_id"], "running")
    state = client.get("/api/chat/session-a/run-state", headers=headers(tokens["alice"])).json()
    assert state["state"] == "unknown" and state["history_saved"] is None
    assert state["request"]["provider_attempt_count"] is None
    repeated = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "request_already_submitted"
    assert not agent.calls
    missing = client.get(
        "/api/chat/session-a/run-state",
        params={"request_id": str(uuid.uuid4())},
        headers=headers(tokens["alice"]),
    ).json()
    assert missing == {"state": "idle", "request": None, "history_saved": None}


@pytest.mark.parametrize("usage", [None, [], {"timings": None}, {"timings": []}])
async def test_run_state_tolerates_old_partial_usage_and_finds_older_receipt(api, usage):
    _, client, tokens, users, memory, _, _ = api
    body = message()
    await memory.authorize_session("session-a", users["alice"].id, create=True)
    ledger = ChatStreamLedger(memory._get_conn, memory._release_conn)
    ledger.claim(users["alice"].id, body["request_id"], "session-a", "saved-message", body)
    await memory.save_message(
        "session-a",
        "assistant",
        "Saved",
        metadata={"request_id": body["request_id"], "usage": usage},
    )
    ledger.update(users["alice"].id, body["request_id"], "complete")
    for _ in range(51):
        await memory.save_message("session-a", "assistant", "Later", metadata={})
    result = client.get(
        "/api/chat/session-a/run-state",
        params={"request_id": body["request_id"]},
        headers=headers(tokens["alice"]),
    ).json()
    assert result["state"] == "terminal" and result["history_saved"] is True
    assert result["request"]["provider_attempt_count"] is None


def test_run_budget_cancels_local_execution_and_persists_safe_failure(api, monkeypatch):
    main, client, tokens, _, memory, agent, _ = api
    monkeypatch.setattr("agents.provider_limits.chat_run_seconds", lambda: 0.04)
    agent.block = True
    body = message()
    response = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
    terminal = frames(response.text)[-1]
    assert terminal["type"] == "error" and terminal["code"] == "chat_run_timeout"
    assert terminal["answer_delivered"] is False and terminal["task_verified"] is False
    assert agent.cancelled.is_set() and len(agent.calls) == 1
    assert not main._stream_sessions and not main._stream_runs
    state = client.get("/api/chat/session-a/run-state", headers=headers(tokens["alice"])).json()
    assert state["state"] == "terminal" and state["history_saved"] is True


async def test_unstarted_response_releases_lease_without_provider_execution(api):
    main, client, tokens, _, _, agent, _ = api
    body = message()
    response = await main.stream_chat(
        main.StreamChatMessage(**body), main.auth.verify_token(tokens["alice"])
    )
    await response.close()
    assert not main._stream_sessions and not main._stream_runs and not agent.calls
    state = client.get("/api/chat/session-a/run-state", headers=headers(tokens["alice"])).json()
    assert state["state"] == "terminal" and state["request"]["status"] == "rejected"
    assert state["history_saved"] is False


def test_authentication_precedes_stream_and_work(api):
    _, client, tokens, _, _, agent, _ = api
    assert client.post("/api/chat/stream", json=message()).status_code == 401
    assert (
        client.post("/api/chat/stream", json=message(), headers=headers("invalid")).status_code
        == 401
    )
    assert (
        client.post(
            "/api/chat/stream", json={"content": "hello"}, headers=headers(tokens["alice"])
        ).status_code
        == 422
    )
    assert not agent.calls


async def test_status_for_post_never_received_does_not_claim_session(api):
    _, client, tokens, _, memory, agent, _ = api
    result = client.get("/api/chat/never-received/run-state", headers=headers(tokens["alice"]))
    assert result.status_code == 200
    assert result.json() == {"state": "idle", "request": None, "history_saved": None}
    assert await memory.session_owner("never-received") is None
    assert not agent.calls


def test_unicode_completion_usage_and_no_websocket_leaks(api):
    main, client, tokens, users, memory, agent, manager = api
    body = message(model_override="ruh-remote", thinking=True)
    response = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = frames(response.text)
    assert events[0]["type"] == "status"
    assert events[0]["streaming_mode"] == "buffered"
    assert [e["chunk"] for e in events if e["type"] == "chat_stream"] == ["مرحبا\n", "world"]
    final = events[-1]
    assert final["type"] == "chat_complete"
    assert final["response"] == "مرحبا\nworld"
    assert final["usage"]["model"] == "observed-ruh"
    assert final["thinking_trace"]["steps"]
    assert all(
        e["request_id"] == body["request_id"] and e["session_id"] == body["session_id"]
        for e in events
    )
    assert all(e["message_id"] == final["message_id"] for e in events)
    stored = asyncio.run(memory.get_messages(body["session_id"]))
    assert [m["role"] for m in stored] == ["user", "assistant"]
    assert stored[-1]["metadata"]["usage"] == final["usage"]
    assert stored[-1]["metadata"]["request_id"] == body["request_id"]
    assert agent.calls[0][2] == users["alice"].id
    assert not main._stream_sessions
    manager.broadcast.assert_not_called()
    manager.send.assert_not_called()


def test_abstention_receipt_survives_stream_and_history(api):
    _, client, tokens, _, memory, agent, _ = api
    original = agent.execute

    async def abstain(*args, **kwargs):
        result = await original(*args, **kwargs)
        result.update(completion_status="abstained", task_verified=False, answer_delivered=True)
        result["usage"].update(owned_status="abstained", completion_status="abstained")
        return result

    agent.execute = abstain
    body = message()
    response = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
    final = frames(response.text)[-1]
    assert final["type"] == "chat_complete"
    assert final["completion_status"] == "abstained"
    assert final["task_verified"] is False
    assert final["usage"]["owned_status"] == "abstained"
    stored = asyncio.run(memory.get_messages(body["session_id"]))[-1]["metadata"]
    assert stored["completion_status"] == "abstained"
    assert stored["task_verified"] is False


def test_shared_council_is_not_accessible_to_ordinary_users(api, monkeypatch):
    main, client, tokens, _, _, _, _ = api
    council = SimpleNamespace(consult=AsyncMock())
    monkeypatch.setattr(main, "shura", council)
    response = client.post(
        "/api/shura", json={"question": "Recall shared notes"}, headers=headers(tokens["alice"])
    )
    assert response.status_code == 403
    council.consult.assert_not_awaited()


def test_cross_user_session_denied_before_agent_call(api):
    _, client, tokens, _, _, agent, _ = api
    assert (
        client.post(
            "/api/chat/stream", json=message(), headers=headers(tokens["alice"])
        ).status_code
        == 200
    )
    result = client.post("/api/chat/stream", json=message(), headers=headers(tokens["bob"]))
    assert result.status_code == 404
    assert "session-a" not in result.text
    assert len(agent.calls) == 1


def test_retry_receipt_survives_backend_memory_restart(api, monkeypatch):
    main, client, tokens, _, memory, agent, _ = api
    body = message()
    assert (
        client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"])).status_code
        == 200
    )
    monkeypatch.setattr(main, "memory", DhikrMemorySystem(memory.db_path))
    monkeypatch.setattr(main, "active_sessions", {})
    repeated = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["status"] == "complete"
    assert repeated.json()["detail"]["same_request"] is True
    changed = client.post(
        "/api/chat/stream", json={**body, "content": "changed"}, headers=headers(tokens["alice"])
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["same_request"] is False
    assert len(agent.calls) == 1


def test_request_uuid_is_scoped_to_owner_not_globally(api):
    _, client, tokens, _, _, agent, _ = api
    body = message()
    assert (
        client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"])).status_code
        == 200
    )
    assert (
        client.post(
            "/api/chat/stream",
            json={**body, "session_id": "session-b"},
            headers=headers(tokens["bob"]),
        ).status_code
        == 200
    )
    assert len(agent.calls) == 2


def test_private_provider_error_is_terminal_and_not_exposed(api):
    main, client, tokens, _, memory, agent, _ = api
    agent.failure = True
    result = client.post("/api/chat/stream", json=message(), headers=headers(tokens["alice"]))
    assert result.status_code == 200
    events = frames(result.text)
    assert events[-1]["type"] == "error"
    assert not any(e["type"] == "chat_complete" for e in events)
    assert "private provider diagnostic" not in result.text
    assert not main._stream_sessions
    stored = asyncio.run(memory.get_messages("session-a"))
    assert stored[-1]["metadata"]["status"] == "error"
    assert stored[-1]["metadata"]["usage_incomplete"] is True


@pytest.mark.parametrize("agent_succeeded", [False, True])
def test_assistant_persistence_failure_still_emits_terminal_error_once(
    api, monkeypatch, agent_succeeded
):
    main, client, tokens, _, memory, agent, _ = api
    original_save = memory.save_message
    assistant_attempts = []

    async def save(session_id, role, *args, **kwargs):
        if role == "assistant":
            assistant_attempts.append(role)
            raise RuntimeError("private storage failure")
        return await original_save(session_id, role, *args, **kwargs)

    monkeypatch.setattr(memory, "save_message", save)
    if not agent_succeeded:

        async def fail(*args, **kwargs):
            return {
                "success": False,
                "error_code": "output_budget_exhausted",
                "usage": {"model": "observed-fixture", "timings": {"total_ms": 12}},
            }

        monkeypatch.setattr(agent, "execute", fail)
    response = client.post("/api/chat/stream", json=message(), headers=headers(tokens["alice"]))
    events = frames(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "history_save_failed"
    assert events[-1]["history_saved"] is False
    assert events[-1]["answer_delivered"] is False
    assert events[-1]["task_verified"] is False
    assert events[-1]["usage"]["model"] == (
        "observed-ruh" if agent_succeeded else "observed-fixture"
    )
    assert not any(event["type"] == "chat_complete" for event in events)
    assert "private storage failure" not in response.text
    assert assistant_attempts == ["assistant"]
    assert [row["role"] for row in asyncio.run(memory.get_messages("session-a"))] == ["user"]
    assert not main._stream_sessions


def test_artifact_events_only_reference_saved_owned_session_artifacts(api):
    from api.artifacts import create_artifact

    _, client, tokens, users, _, agent, _ = api
    own = create_artifact(
        user_id=users["alice"].id,
        session_id="session-a",
        title="Preview",
        kind="html",
        content="<h1>hello</h1>",
    )
    foreign = create_artifact(
        user_id=users["bob"].id,
        session_id="session-a",
        title="Secret",
        kind="markdown",
        content="private",
    )
    other_session = create_artifact(
        user_id=users["alice"].id,
        session_id="different",
        title="Other",
        kind="code",
        content="private",
    )
    agent.artifacts = [own, foreign, other_session, {"id": "made-up"}, own]
    agent._last_tool_results = [{"name": "workspace_artifact", "result": {"artifact": own}}]
    response = client.post("/api/chat/stream", json=message(), headers=headers(tokens["alice"]))
    artifacts = [e["artifact"] for e in frames(response.text) if e["type"] == "artifact"]
    assert len(artifacts) == 1
    assert artifacts[0]["id"] == own["id"]
    assert "content" not in artifacts[0]
    assert "Secret" not in response.text


def test_artifacts_come_from_this_requests_run_and_stay_on_the_message(api, monkeypatch):
    import types

    from agents.base import _agent_runs
    from api.artifacts import create_artifact

    _, client, tokens, users, memory, agent, _ = api

    def saved(title):
        return create_artifact(
            user_id=users["alice"].id, session_id="session-a", title=title, kind="html",
            content=f"<p>{title}</p>",
        )  # fmt: skip

    stale, fresh = saved("Old"), saved("New")
    # A real run works on its own copy (``run_of``); the base agent still holds
    # the previous run's tool results.
    agent._last_tool_results = [{"name": "workspace_artifact", "result": {"artifact": stale}}]
    run = types.SimpleNamespace(
        _last_tool_results=[{"name": "workspace_artifact", "result": {"artifact": fresh}}]
    )
    original = agent.execute

    async def execute(content, context, **callbacks):
        _agent_runs.set({**(_agent_runs.get() or {}), id(agent): run})
        return await original(content, context, **callbacks)

    monkeypatch.setattr(agent, "execute", execute)
    response = client.post("/api/chat/stream", json=message(), headers=headers(tokens["alice"]))
    events = frames(response.text)
    assert [e["artifact"]["id"] for e in events if e["type"] == "artifact"] == [fresh["id"]]
    complete = next(e for e in events if e["type"] == "chat_complete")
    assert complete["artifacts"] == [fresh["id"]]
    stored = asyncio.run(memory.get_messages("session-a"))[-1]["metadata"]
    assert stored["artifacts"] == [fresh["id"]]


def test_workspace_selection_is_authorized_before_execution_and_bound_for_tools(api, monkeypatch):
    import sys

    _, client, tokens, users, _, agent, _ = api
    selection = ContextVar("test_workspace", default=None)
    parent_module, context_module = ModuleType("workspace"), ModuleType("workspace.context")
    checked = []

    def authorize(workspace_id, owner_id):
        checked.append((workspace_id, owner_id))
        if workspace_id != "owned-project" or owner_id != users["alice"].id:
            raise HTTPException(404, "Workspace not found")
        return {"id": workspace_id}

    context_module.authorize_owned_workspace = authorize
    context_module.bind_workspace = selection.set
    context_module.reset_workspace = selection.reset
    context_module.running_in = lambda owner_id, workspace_id: contextlib.nullcontext()
    parent_module.context = context_module
    monkeypatch.setitem(sys.modules, "workspace", parent_module)
    monkeypatch.setitem(sys.modules, "workspace.context", context_module)
    original_execute = agent.execute
    seen_selection = []

    async def execute(*args, **kwargs):
        seen_selection.append(selection.get())
        return await original_execute(*args, **kwargs)

    monkeypatch.setattr(agent, "execute", execute)
    denied = client.post(
        "/api/chat/stream",
        json=message(workspace_id="someone-elses-project"),
        headers=headers(tokens["alice"]),
    )
    assert denied.status_code == 404
    assert not agent.calls
    allowed = client.post(
        "/api/chat/stream",
        json=message(workspace_id="owned-project"),
        headers=headers(tokens["alice"]),
    )
    assert allowed.status_code == 200
    assert seen_selection == ["owned-project"]
    assert agent.calls[-1][1]["workspace_id"] == "owned-project"
    assert checked[-1] == ("owned-project", users["alice"].id)
    assert selection.get() is None


def test_command_without_agents_finishes_without_model_invocation(api, monkeypatch):
    main, client, tokens, _, memory, agent, _ = api
    monkeypatch.setattr(main, "active_agents", {})
    response = client.post(
        "/api/chat/stream", json=message(content="/help"), headers=headers(tokens["alice"])
    )
    assert response.status_code == 200
    assert frames(response.text)[-1]["type"] == "chat_complete"
    assert "Available Commands" in frames(response.text)[-1]["response"]
    assert not agent.calls
    assert len(asyncio.run(memory.get_messages("session-a"))) == 2


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("cancel_during", ["context", "execution"])
async def test_real_asgi_disconnect_keeps_the_run_and_stop_persists_partial(
    api, monkeypatch, spec_version, cancel_during
):
    from providers import LLMResponse

    main, _, tokens, users, memory, agent, _ = api
    agent.block = True
    if cancel_during == "context":

        async def blocked_context(*args, **kwargs):
            await asyncio.Event().wait()

        monkeypatch.setattr(main, "chat_context", blocked_context)
    agent._llm_calls = [
        {
            "response": LLMResponse([], model="observed-partial", usage={"input": 5, "output": 1}),
            "latency_ms": 10,
        }
    ]
    agent._execution_timings = {
        "provider_attempts": [
            {"mode": "stream", "outcome": "cancelled", "latency_ms": 12.5, "error": "private"},
            {"mode": "unknown", "outcome": "failed", "latency_ms": 4},
            {"mode": "create", "outcome": "failed", "latency_ms": float("nan")},
            {"mode": [], "outcome": "failed", "latency_ms": 4},
            {"mode": "create", "outcome": {}, "latency_ms": 4},
            {"mode": "create", "outcome": "failed", "latency_ms": 10**1000},
        ]
    }
    body = message()
    disconnected = asyncio.Event()
    body_sent = False
    chunks = []

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(event):
        if event["type"] == "http.response.body":
            chunks.append(event.get("body", b""))
            trigger = b"event: typing" if cancel_during == "context" else b"event: chat_stream"
            if trigger in event.get("body", b""):
                if spec_version == "2.4":
                    raise OSError("peer closed the connection")
                disconnected.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/chat/stream",
        "raw_path": b"/api/chat/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", ("Bearer " + tokens["alice"]).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    if spec_version == "2.4":
        # BaseHTTPMiddleware can surface the send-side OSError directly,
        # whereas the raw response translates it to ClientDisconnect.
        with pytest.raises((ClientDisconnect, OSError)):
            await asyncio.wait_for(main.app(scope, receive, send), timeout=3)
    else:
        await asyncio.wait_for(main.app(scope, receive, send), timeout=3)
    # The reader is gone; the run is not. Only the Stop button ends it.
    await asyncio.sleep(0)
    assert main._stream_sessions and not agent.cancelled.is_set()
    assert (await stop_run(main, main.auth.verify_token(tokens["alice"])))["stopped"] is True
    if cancel_during == "execution":
        await asyncio.wait_for(agent.cancelled.wait(), timeout=1)
    assert not main._stream_sessions
    assert not any(e["type"] == "chat_complete" for e in frames(b"".join(chunks).decode()))
    stored = await memory.get_messages(body["session_id"])
    assert stored[-1]["content"] == ("مرحبا\n" if cancel_during == "execution" else "")
    metadata = stored[-1]["metadata"]
    assert metadata["status"] == "cancelled"
    assert metadata["cancellation_reason"] == "user_stopped"
    assert metadata["request_elapsed_ms"] >= 0
    if cancel_during == "execution":
        assert metadata["execution_stage"] in {"agent_execution", "delivery"}
        assert metadata["usage"]["input_tokens"] == 5
        assert metadata["usage"]["model"] == "observed-partial"
        assert metadata["usage"]["timings"] == {
            "provider_attempt_count": 1,
            "provider_ms": 12.5,
            "provider_attempts": [{"mode": "stream", "outcome": "cancelled", "latency_ms": 12.5}],
        }
    else:
        assert metadata["execution_stage"] == "context_preparation"
        assert metadata["usage"] == {}  # Never attribute another queued request's counters.
    assert "private" not in json.dumps(metadata)
    assert metadata["usage_incomplete"] is True
    receipt = ChatStreamLedger(memory._get_conn, memory._release_conn).claim(
        users["alice"].id, body["request_id"], body["session_id"], "another", body
    )
    assert receipt["status"] == "cancelled"
    assert len(agent.calls) == int(cancel_during == "execution")


async def test_heartbeat_and_active_request_conflicts_do_not_start_more_calls(api, monkeypatch):
    main, _, tokens, _, memory, agent, _ = api
    monkeypatch.setattr(main, "HEARTBEAT_SECONDS", 0.01)
    agent.block = True
    principal = main.auth.verify_token(tokens["alice"])
    body = message()
    req = main.StreamChatMessage(**body)
    response = await main.stream_chat(req, principal)
    saw_heartbeat = False
    try:
        async for frame in response.body_iterator:
            if frame.startswith(": heartbeat"):
                saw_heartbeat = True
                with pytest.raises(HTTPException) as duplicate:
                    await main.stream_chat(req, principal)
                assert duplicate.value.status_code == 409
                with pytest.raises(HTTPException) as concurrent:
                    await main.stream_chat(main.StreamChatMessage(**message()), principal)
                assert concurrent.value.status_code == 409
                break
    finally:
        await response.close()
        await stop_run(main, principal)
    assert saw_heartbeat
    assert agent.cancelled.is_set()
    assert len(agent.calls) == 1
    assert not main._stream_sessions
    assert (await memory.get_messages("session-a"))[-1]["metadata"]["status"] == "cancelled"


async def test_channel_bounded_backpressure_and_serialized_frame_limit(monkeypatch):
    import api.chat_stream as streams

    monkeypatch.setattr(streams, "SEND_TIMEOUT_SECONDS", 0.01)
    channel = ChatEventChannel(session_id="s", message_id="m", request_id="r")
    for _ in range(streams.MAX_QUEUED_EVENTS):
        await channel.emit("chat_stream", chunk="one")
    # A reader that stops reading is let go: the run is not held up or stopped.
    await channel.emit("chat_stream", chunk="overflow")
    assert channel.detached and channel.queue.qsize() == streams.MAX_QUEUED_EVENTS
    await channel.emit("chat_stream", chunk="after")  # dropped, not an error
    assert channel.queue.qsize() == streams.MAX_QUEUED_EVENTS
    fresh = ChatEventChannel(session_id="s", message_id="m", request_id="r")
    with pytest.raises(StreamDeliveryError, match="delivery limit"):
        await fresh.emit("thinking", content="a" * streams.MAX_FRAME_BYTES)
    channel.close()
    with pytest.raises(StreamDeliveryError, match="disconnected"):
        await channel.emit("chat_stream", chunk="late")


async def test_provider_queue_is_bounded_and_stream_closes_on_cancel():
    from agents.base import BaseAgent
    from providers import LLMResponse

    produced = 0
    closed = threading.Event()

    class ProviderStream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.set()

        def close(self):
            closed.set()

        @property
        def text_stream(self):
            nonlocal produced
            while not closed.is_set():
                produced += 1
                yield "x"

        def get_final_response(self):
            return LLMResponse([])

    agent = object.__new__(BaseAgent)
    agent.ai_model = "fake"
    agent.ai_client = SimpleNamespace(stream=lambda **kwargs: ProviderStream())
    stream = agent._streaming_create("system", [], [], 10, 0.2, {})
    assert await anext(stream) == "x"
    await asyncio.sleep(0.05)
    # One consumed chunk + 64 queued + one waiting provider publish.
    assert produced <= 66
    await stream.aclose()
    deadline = time.monotonic() + 1
    while not closed.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert closed.is_set()


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("blocked_type", ["http.response.start", "http.response.body"])
async def test_actual_transport_deadline_always_releases_capacity(
    monkeypatch, spec_version, blocked_type
):
    import api.chat_stream as streams

    monkeypatch.setattr(streams, "SEND_TIMEOUT_SECONDS", 0.01)
    held = {"request"}
    released = []
    iterator_closed = asyncio.Event()
    send_started = asyncio.Event()

    async def body():
        try:
            yield "data: {}\n\n"
        finally:
            iterator_closed.set()

    def release():
        held.discard("request")
        released.append(True)

    async def receive():
        await asyncio.Event().wait()

    async def send(event):
        if event["type"] == blocked_type:
            send_started.set()
            await asyncio.Event().wait()

    response = streams.ChatStreamingResponse(body(), release_stream=release)
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": spec_version}}
    with pytest.raises((ClientDisconnect, OSError)):
        await asyncio.wait_for(response(scope, receive, send), timeout=0.3)
    assert send_started.is_set()
    assert not held
    assert released == [True]
    if blocked_type == "http.response.body":
        assert iterator_closed.is_set()
    await response.close()
    assert released == [True]


async def test_completed_producer_keeps_capacity_while_transport_drains(api):
    main, _, tokens, _, _, agent, _ = api
    principal = main.auth.verify_token(tokens["alice"])
    response = await main.stream_chat(main.StreamChatMessage(**message()), principal)
    assert await anext(response.body_iterator)
    # The bounded fake agent finishes while the HTTP reader still owns queued frames.
    for _ in range(100):
        if len(agent.calls) == 1 and not any(
            t.get_name().startswith("chat-stream-") for t in asyncio.all_tasks()
        ):
            break
        await asyncio.sleep(0)
    assert main._stream_sessions
    with pytest.raises(HTTPException) as concurrent:
        await main.stream_chat(main.StreamChatMessage(**message()), principal)
    assert concurrent.value.status_code == 409
    await response.close()
    assert not main._stream_sessions


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("middleware_delay", ["await", "blocking"])
async def test_middleware_rendezvous_delay_is_not_a_network_delivery_failure(
    api, monkeypatch, spec_version, middleware_delay
):
    """Exercise the real FastAPI security BaseHTTPMiddleware and outer guard."""
    import api.chat_stream as streams

    main, _, tokens, _, memory, _, _ = api
    monkeypatch.setattr(streams, "SEND_TIMEOUT_SECONDS", 0.02)
    middleware = next(
        entry for entry in main.app.user_middleware if entry.cls.__name__ == "BaseHTTPMiddleware"
    )
    original_dispatch = middleware.kwargs["dispatch"]

    async def delayed_dispatch(request, call_next):
        response = await original_dispatch(request, call_next)
        # The actual network send is ready. Only the middleware consumer of
        # Starlette's internal zero-capacity memory stream is delayed.
        if middleware_delay == "await":
            await asyncio.sleep(0.08)
        else:
            time.sleep(0.08)
        return response

    monkeypatch.setitem(middleware.kwargs, "dispatch", delayed_dispatch)
    monkeypatch.setattr(main.app, "middleware_stack", None)
    payload = message()
    body_sent = False
    received = []

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {
                "type": "http.request",
                "body": json.dumps(payload).encode(),
                "more_body": False,
            }
        await asyncio.Event().wait()

    async def send(event):
        received.append(event)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/chat/stream",
        "raw_path": b"/api/chat/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", ("Bearer " + tokens["alice"]).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    await asyncio.wait_for(main.app(scope, receive, send), timeout=2)
    events = frames(b"".join(event.get("body", b"") for event in received).decode())
    assert events[-1]["type"] == "chat_complete"
    assert events[-1]["response"] == "مرحبا\nworld"
    assert not any(event["type"] == "error" for event in events)
    assert not main._stream_sessions
    assert (await memory.get_messages(payload["session_id"]))[-1]["metadata"][
        "status"
    ] == "complete"


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("blocked_type", ["http.response.start", "http.response.body"])
async def test_full_application_bounds_actual_network_transport(
    api, monkeypatch, spec_version, blocked_type
):
    import api.chat_stream as streams

    main, _, tokens, _, _, _, _ = api
    monkeypatch.setattr(streams, "SEND_TIMEOUT_SECONDS", 0.05)
    payload = message()
    body_sent = False
    send_started = asyncio.Event()

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {
                "type": "http.request",
                "body": json.dumps(payload).encode(),
                "more_body": False,
            }
        await asyncio.Event().wait()

    async def send(event):
        if event["type"] == blocked_type:
            send_started.set()
            assert main._stream_sessions
            await asyncio.sleep(0.01)
            assert main._stream_sessions
            await asyncio.Event().wait()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/chat/stream",
        "raw_path": b"/api/chat/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", ("Bearer " + tokens["alice"]).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    with pytest.raises((ClientDisconnect, OSError)):
        # Outer bound only: the behaviour under test is the 0.05s send
        # timeout above. 0.5s here flaked under full-suite load (the app
        # still has to boot the whole stack before the first frame), so
        # allow scheduling headroom without weakening the assertion.
        await asyncio.wait_for(main.app(scope, receive, send), timeout=5.0)
    assert send_started.is_set()
    assert not main._stream_sessions


def test_stream_restores_history_and_retrieves_owned_prior_sessions(api):
    main, client, tokens, users, memory, agent, _ = api
    alice = users["alice"].id
    bob = users["bob"].id
    asyncio.run(memory.authorize_session("earlier", alice, create=True))
    asyncio.run(memory.save_message("earlier", "user", "Please use Hinglish"))
    asyncio.run(memory.authorize_session("private-bob", bob, create=True))
    asyncio.run(memory.save_message("private-bob", "user", "Bob private request"))
    asyncio.run(memory.authorize_session("restored", alice, create=True))
    asyncio.run(memory.save_message("restored", "user", "old turn"))
    main.active_sessions.clear()
    response = client.post(
        "/api/chat/stream",
        json=message("restored", content="Explain recursion in Hinglish"),
        headers=headers(tokens["alice"]),
    )
    assert frames(response.text)[-1]["type"] == "chat_complete"
    context = agent.calls[-1][1]
    assert context["session_id"] == "restored"
    assert context["history"] == [{"role": "user", "content": "old turn"}]
    assert [m["content"] for m in context["conversation_memory"]] == ["Please use Hinglish"]
    # A request that shares no distinctive word with earlier chats recalls none
    # (the 27 October benchmark: five unrelated snippets for a simple request).
    client.post(
        "/api/chat/stream",
        json=message("restored", content="new task"),
        headers=headers(tokens["alice"]),
    )
    assert agent.calls[-1][1]["conversation_memory"] == []


def test_learner_endpoint_reports_scoped_capture_instead_of_500(api, tmp_path, monkeypatch):
    from learner.ruh_learner import RuhLearner

    _, client, tokens, users, _, _, _ = api
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    learner = RuhLearner.for_owner(users["alice"].id)
    asyncio.run(learner.initialize())
    asyncio.run(learner.capture("request", "candidate", "openrouter", "observed"))
    response = client.get("/api/learner/stats", headers=headers(tokens["alice"]))
    assert response.status_code == 200
    assert response.json()["total_interactions"] == 1
    assert response.json()["exportable_count"] == 0
    assert response.json()["automatic_weight_training"] is False
    assert (
        client.get("/api/learner/stats", headers=headers(tokens["bob"])).json()[
            "total_interactions"
        ]
        == 0
    )
    assert client.get("/api/learner/stats").status_code == 401


def test_saved_artifact_remains_visible_when_generation_later_fails(api, monkeypatch):
    from api.artifacts import create_artifact

    _, client, tokens, users, memory, agent, _ = api
    artifact = create_artifact(
        user_id=users["alice"].id,
        session_id="session-a",
        title="Saved code",
        kind="code",
        content="print(42)",
    )

    async def fail_after_artifact(content, context, **callbacks):
        agent._last_tool_results = [
            {"name": "workspace_artifact", "result": {"artifact": artifact}}
        ]
        await callbacks["stream_callback"](
            "", chunk_type="tool_use", tool_name="workspace_artifact"
        )
        await callbacks["stream_callback"]("Partial answer")
        return {"success": False, "error": "private upstream details"}

    monkeypatch.setattr(agent, "execute", fail_after_artifact)
    response = client.post("/api/chat/stream", json=message(), headers=headers(tokens["alice"]))
    events = frames(response.text)
    assert events[-1]["type"] == "error"
    assert not any(e["type"] == "chat_complete" for e in events)
    assert [e["artifact"]["id"] for e in events if e["type"] == "artifact"] == [artifact["id"]]
    assert "private upstream details" not in response.text
    stored = asyncio.run(memory.get_messages("session-a"))[-1]
    assert stored["content"] == "Partial answer"
    assert stored["metadata"]["status"] == "error"


@pytest.mark.parametrize("transport", ["sse", "rest", "websocket"])
@pytest.mark.parametrize("partial", ["", "Visible partial answer"])
@pytest.mark.parametrize(
    "code",
    ["output_budget_exhausted", "provider_timeout", "chat_run_timeout", "private_unknown_code"],
)
def test_failed_chat_retains_safe_code_final_usage_and_receipt(
    api, monkeypatch, transport, partial, code
):
    main, client, tokens, _, memory, agent, manager = api
    usage = {
        "model": "observed-model",
        "input_tokens": 19000,
        "output_tokens": 2048,
        "reasoning_tokens": 2048,
        "visible_output_tokens": 0,
        "timings": {"queue_wait_ms": 25, "provider_ms": 100, "total_ms": 150},
        "calls": [{"finish_reason": "max_tokens", "output_tokens": 2048}],
    }

    async def fail(content, context, **callbacks):
        if partial:
            await callbacks["stream_callback"](partial)
        return {
            "success": False,
            "error_code": code,
            "error": "private upstream diagnostic",
            "result": "private exception fallback must not become assistant content",
            "completion_status": "incomplete" if code == "output_budget_exhausted" else "failed",
            "answer_delivered": False,
            "task_verified": False,
            "usage": usage,
        }

    monkeypatch.setattr(agent, "execute", fail)
    body = message(session=f"failure-{transport}")
    if transport == "sse":
        response = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
        events = frames(response.text)
        assert not any(event["type"] == "chat_complete" for event in events)
        final = events[-1]
    elif transport == "rest":
        response = client.post("/api/chat", json=body, headers=headers(tokens["alice"]))
        assert response.status_code == 200
        events = [call.args[0] for call in manager.broadcast.await_args_list]
        assert not any(event["type"] == "chat_complete" for event in events)
        final = events[-1]
    else:
        monkeypatch.setattr(main, "manager", main.ConnectionManager())
        monkeypatch.setattr(
            main, "get_provider_status", lambda: {"active": "fixture", "default_model": "fixture"}
        )
        monkeypatch.setattr(
            main,
            "wali",
            SimpleNamespace(
                audit=SimpleNamespace(log=lambda *args: None),
                check_rate_limit=lambda *args: {"allowed": True},
            ),
        )
        with client.websocket_connect("/ws/failure?token=" + tokens["alice"]) as websocket:
            assert websocket.receive_json()["type"] == "connected"
            websocket.send_json({"type": "chat", **body})
            assert websocket.receive_json()["type"] == "typing"
            if partial:
                assert websocket.receive_json()["chunk"] == partial
            final = websocket.receive_json()

    known_code = code in {"output_budget_exhausted", "provider_timeout", "chat_run_timeout"}
    expected_code = code if known_code else "agent_failed"
    assert final["type"] == "error"
    assert final["code"] == expected_code
    assert final["completion_status"] == ("incomplete" if known_code else "failed")
    assert final["answer_delivered"] is False and final["task_verified"] is False
    assert final["usage"]["timings"] == usage["timings"]
    assert final["usage"]["calls"] == usage["calls"]
    assert final["usage"]["reasoning_tokens"] == 2048
    if code == "output_budget_exhausted":
        assert "output limit" in final["message"]
    assert "private" not in json.dumps(final)
    stored = asyncio.run(memory.get_messages(body["session_id"]))[-1]
    assert stored["content"] == partial
    metadata = stored["metadata"]
    assert metadata["status"] == "error" and metadata["partial"] is True
    assert metadata["code"] == expected_code
    assert metadata["message"] == final["message"]
    assert metadata["usage"] == final["usage"]
    assert metadata["completion_status"] == final["completion_status"]
    assert metadata["answer_delivered"] is False and metadata["task_verified"] is False
    if transport == "sse":
        assert metadata["usage_incomplete"] is False


@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_a_chat_answers_when_the_approval_store_cannot_be_opened(api, monkeypatch, transport):
    # Every chat binds an approval context, which reads what the person allowed "always"
    # from $MIZAN_DATA_DIR. A data directory that cannot be created (a non-root server whose
    # MIZAN_DATA_DIR is unset falls back to /data/mizan) must neither fail the chat nor leave
    # a WebSocket client waiting for a frame that never comes.
    main, client, tokens, _, _, agent, _ = api
    monkeypatch.setenv("MIZAN_DATA_DIR", "/proc/mizan-no-such-dir")
    body = message(session=f"no-store-{transport}")
    if transport == "sse":
        response = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
        assert frames(response.text)[-1]["type"] == "chat_complete"
        return

    async def answer(content, context, **callbacks):
        await callbacks["stream_callback"]("ok")
        return {"success": True, "result": "ok", "usage": {}}

    monkeypatch.setattr(agent, "execute", answer)
    monkeypatch.setattr(main, "manager", main.ConnectionManager())
    monkeypatch.setattr(
        main, "get_provider_status", lambda: {"active": "fixture", "default_model": "fixture"}
    )
    monkeypatch.setattr(
        main,
        "wali",
        SimpleNamespace(
            audit=SimpleNamespace(log=lambda *args: None),
            check_rate_limit=lambda *args: {"allowed": True},
        ),
    )
    received: list[dict] = []

    def talk():
        with client.websocket_connect("/ws/no-store?token=" + tokens["alice"]) as websocket:
            received.append(websocket.receive_json())
            websocket.send_json({"type": "chat", **body})
            while received[-1]["type"] not in {"chat_complete", "error"}:
                received.append(websocket.receive_json())

    # In a thread joined with a timeout: before the fix the client waited forever.
    worker = threading.Thread(target=talk, daemon=True)
    worker.start()
    worker.join(30)
    assert not worker.is_alive(), "the WebSocket chat never sent its last frame"
    assert received[-1]["type"] == "chat_complete"
    assert received[-1]["content"] == "ok"


def test_ruh_status_distinguishes_configuration_from_loaded_model(api, monkeypatch, tmp_path):
    main, client, tokens, _, _, agent, _ = api
    agent.ai_client = SimpleNamespace(provider_name="ruh", _loaded=False)
    monkeypatch.setattr(main, "_user_agents", {})
    monkeypatch.setenv("RUH_ENABLED", "true")
    monkeypatch.setenv("RUH_MODEL_PATH", str(tmp_path / "missing-checkpoint"))
    first = client.get("/api/ruh/status", headers=headers(tokens["alice"])).json()
    assert first["enabled"] is True
    assert first["checkpoint_exists"] is False
    assert first["loaded"] is False
    assert first["automatic_weight_training"] is False
    agent.ai_client._loaded = True
    second = client.get("/api/ruh/status", headers=headers(tokens["alice"])).json()
    assert second["loaded"] is True
    assert second["active_chat_models"] == ["ruh: ruh-remote"]


def test_chat_memory_summary_counts_only_authenticated_owners(api):
    _, client, tokens, users, memory, _, _ = api
    for name in ("alice", "bob"):
        asyncio.run(memory.authorize_session(name + "-chat", users[name].id, create=True))
        for _ in range(2 if name == "alice" else 3):
            asyncio.run(memory.save_message(name + "-chat", "user", "private content"))
    response = client.get("/api/chat/memory/summary", headers=headers(tokens["alice"]))
    assert response.status_code == 200
    assert response.json()["stored_chat_messages"] == 2
    assert response.json()["owned_sessions"] == 1
    assert "private content" not in response.text
    assert client.get("/api/chat/memory/summary").status_code == 401


def test_a_message_without_request_id_gets_one_made_and_returned(api):
    # The live benchmark (27 Oct): a client that sent no request_id got 422.
    _, client, tokens, _, _, _, _ = api
    body = message()
    del body["request_id"]
    response = client.post("/api/chat/stream", json=body, headers=headers(tokens["alice"]))
    assert response.status_code == 200
    made = {event["request_id"] for event in frames(response.text)}
    assert len(made) == 1 and uuid.UUID(made.pop())


def test_the_default_stream_carries_the_answer_not_the_agents_telemetry(api):
    # The live benchmark (27 Oct): "Lawwama voice dominant (confidence: 46%)"
    # and similar scores were in every stream. They are sent only when asked for.
    _, client, tokens, _, _, _, _ = api
    response = client.post("/api/chat/stream", json=message(), headers=headers(tokens["alice"]))
    events = frames(response.text)
    assert not [event for event in events if event["type"] == "thinking"]
    final = events[-1]
    assert final["type"] == "chat_complete" and final["response"]
    assert "cognitive" not in final and "thinking_trace" not in final


def test_a_stateless_message_recalls_nothing_and_says_so(api, monkeypatch):
    main, client, tokens, _, memory, _, _ = api
    from memory import stateless

    calls = []

    async def recall(user_id, task, exclude_session=None):
        calls.append(stateless.active())
        return [{"session_id": "other", "content": "a private note", "created_at": ""}]

    monkeypatch.setattr(memory, "recall_conversations", recall)
    response = client.post(
        "/api/chat/stream", json=message(stateless=True), headers=headers(tokens["alice"])
    )
    assert response.status_code == 200
    assert calls == []  # never asked for the user's other chats


# ── API hygiene from the 3.3.0 benchmark ─────────────────────────────────


def test_stop_takes_an_empty_body(api):
    main, client, tokens, users, memory, _, _ = api
    asyncio.run(memory.authorize_session("quiet", users["alice"].id, create=True))
    response = client.post("/api/chat/quiet/stop", headers=headers(tokens["alice"]))
    assert response.status_code == 200 and response.json() == {"stopped": False}


def test_a_rejected_body_is_not_echoed_back(api):
    _, client, tokens, _, _, _, _ = api
    secret = "my private words " * 3
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "s1", "content": "", "note": secret},
        headers=headers(tokens["alice"]),
    )
    assert response.status_code == 422
    body = response.text
    assert '"input"' not in body and secret.strip() not in body


def test_a_session_id_outside_the_safe_characters_is_refused(api):
    _, client, tokens, _, _, _, _ = api
    response = client.post(
        "/api/chat/stream",
        json=message("bad id/../x"),
        headers=headers(tokens["alice"]),
    )
    assert response.status_code == 422


def test_the_chat_list_pages(api):
    _, client, tokens, users, memory, _, _ = api
    for name in ("one", "two", "three"):
        asyncio.run(memory.authorize_session(name, users["alice"].id, create=True))
        asyncio.run(memory.save_message(name, "user", f"chat {name}"))
    first = client.get(
        "/api/chat/sessions/list", params={"limit": 2}, headers=headers(tokens["alice"])
    ).json()
    assert len(first["sessions"]) == 2 and first["next_offset"] == 2
    rest = client.get(
        "/api/chat/sessions/list",
        params={"limit": 2, "offset": first["next_offset"]},
        headers=headers(tokens["alice"]),
    ).json()
    assert len(rest["sessions"]) == 1 and rest["next_offset"] is None


def test_public_health_says_only_whether_mizan_is_up(api):
    _, client, tokens, _, _, _, _ = api
    public = client.get("/api/health").json()
    assert set(public) == {"status"}
    # A signed-in user who is not an administrator sees no more.
    assert set(client.get("/api/health", headers=headers(tokens["alice"])).json()) == {"status"}


async def test_a_reader_that_fell_behind_still_gets_the_final_answer():
    channel = ChatEventChannel(session_id="s", message_id="m", request_id="r")
    await channel.emit("chat_stream", chunk="a")
    channel.detach()
    await channel.emit("chat_stream", chunk="b")  # dropped: the reader is behind
    await channel.emit("chat_complete", response="ab")
    frames_left = [channel.queue.get_nowait() for _ in range(channel.queue.qsize())]
    assert len(frames_left) == 1 and "chat_complete" in frames_left[0]


async def test_runs_cut_off_by_a_restart_read_as_cancelled(api):
    _, client, tokens, users, memory, _, _ = api
    body = message()
    await memory.authorize_session("session-a", users["alice"].id, create=True)
    ledger = ChatStreamLedger(memory._get_conn, memory._release_conn)
    ledger.claim(users["alice"].id, body["request_id"], "session-a", "old-message", body)
    ledger.update(users["alice"].id, body["request_id"], "running")
    assert ledger.interrupt_unfinished() == 1  # what the app does at boot
    state = client.get(
        "/api/chat/session-a/run-state",
        params={"request_id": body["request_id"]},
        headers=headers(tokens["alice"]),
    ).json()
    assert state["state"] == "terminal" and state["request"]["status"] == "cancelled"
