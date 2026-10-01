"""SSE chat isolation, durable retries, delivery bounds and real disconnects."""

import asyncio
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
                await asyncio.Event().wait()
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
            if self.block:
                self.cancelled.set()


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


def test_unicode_completion_usage_and_no_websocket_leaks(api):
    main, client, tokens, users, memory, agent, manager = api
    body = message(model_override="ruh-remote")
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
async def test_real_asgi_disconnect_cancels_agent_and_persists_partial(api, spec_version):
    from providers import LLMResponse

    main, _, tokens, users, memory, agent, _ = api
    agent.block = True
    agent._llm_calls = [
        {
            "response": LLMResponse([], model="observed-partial", usage={"input": 5, "output": 1}),
            "latency_ms": 10,
        }
    ]
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
            if b"event: chat_stream" in event.get("body", b""):
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
    await asyncio.wait_for(agent.cancelled.wait(), timeout=1)
    # Give the detached producer's shielded finalization one scheduling turn.
    await asyncio.sleep(0)
    assert not main._stream_sessions
    assert not any(e["type"] == "chat_complete" for e in frames(b"".join(chunks).decode()))
    stored = await memory.get_messages(body["session_id"])
    assert stored[-1]["content"] == "مرحبا\n"
    assert stored[-1]["metadata"]["status"] == "cancelled"
    assert stored[-1]["metadata"]["usage"]["input_tokens"] == 5
    assert stored[-1]["metadata"]["usage"]["model"] == "observed-partial"
    assert stored[-1]["metadata"]["usage_incomplete"] is True
    receipt = ChatStreamLedger(memory._get_conn, memory._release_conn).claim(
        users["alice"].id, body["request_id"], body["session_id"], "another", body
    )
    assert receipt["status"] == "cancelled"
    assert len(agent.calls) == 1


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
    with pytest.raises(StreamDeliveryError, match="too slow"):
        await channel.emit("chat_stream", chunk="overflow")
    assert channel.queue.qsize() == streams.MAX_QUEUED_EVENTS
    with pytest.raises(StreamDeliveryError, match="delivery limit"):
        await channel.emit("thinking", content="a" * streams.MAX_FRAME_BYTES)
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
        await asyncio.wait_for(main.app(scope, receive, send), timeout=0.5)
    assert send_started.is_set()
    assert not main._stream_sessions
