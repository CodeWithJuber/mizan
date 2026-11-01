"""Legacy WS/REST must preserve owner boundaries and stop after delivery failure."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agents.specialized import create_agent
from memory.dhikr import DhikrMemorySystem
from providers import ContentBlock, LLMResponse
from security.auth import MizanAuth, bind_principal, current_user_id, reset_principal


@pytest.fixture
def legacy_api(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    import api.main as main

    auth = MizanAuth("legacy-delivery-test-key-" * 4, data_dir=str(tmp_path / "users"))
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setattr(main, "active_sessions", {})
    monkeypatch.setattr(main, "active_agents", {})
    monkeypatch.setattr(main, "_user_agents", {})
    monkeypatch.setattr(main, "manager", main.ConnectionManager())
    monkeypatch.setattr(main.wali, "check_rate_limit", lambda *args: {"allowed": True})
    monkeypatch.setattr(
        main, "get_provider_status", lambda: {"active": "test", "default_model": "test-model"}
    )
    users = {
        name: auth.create_user(name, "test-password", roles=[role])
        for name, role in [("alice", "user"), ("admin", "admin")]
    }
    tokens = {name: auth.create_token(user) for name, user in users.items()}
    return main, TestClient(main.app), tokens, memory


class FakeWebSocket:
    def __init__(self, messages, *, fail_stream_number=None):
        self.messages = list(messages)
        self.sent = []
        self.fail_stream_number = fail_stream_number
        self.stream_attempts = 0
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, **kwargs):
        pass

    async def receive_json(self):
        if self.messages:
            return self.messages.pop(0)
        raise WebSocketDisconnect(code=1000)

    async def send_json(self, data):
        if data.get("type") == "chat_stream":
            self.stream_attempts += 1
            if self.stream_attempts == self.fail_stream_number:
                raise RuntimeError("reader disconnected")
        self.sent.append(data)


async def run_socket(main, socket, token):
    outer = bind_principal(SimpleNamespace(user_id="outside-request", roles=[]))
    try:
        try:
            await main.websocket_endpoint(socket, "untrusted-client-label", token=token)
        except asyncio.CancelledError:
            # Endpoint may propagate cancellation after committing partial history.
            pass
        assert current_user_id() == "outside-request"
        assert not main.manager.connections
        assert not main.manager.owners
    finally:
        reset_principal(outer)


@pytest.mark.parametrize("message_type", ["task", "multimodal"])
async def test_nonadmin_socket_cannot_reach_shared_execution_or_perception(
    legacy_api, monkeypatch, message_type
):
    main, _, tokens, _ = legacy_api
    shared = SimpleNamespace(
        id="shared-agent",
        name="Shared",
        execute=AsyncMock(return_value={"success": True, "result": "private result"}),
        qca=SimpleNamespace(process_input_multimodal=AsyncMock(return_value={"private": True})),
    )
    monkeypatch.setattr(main, "active_agents", {shared.id: shared})
    socket = FakeWebSocket(
        [
            {
                "type": message_type,
                "agent_id": shared.id,
                "session_id": "ordinary-user-session",
                "task": "Read shared memory",
                "content": "Read shared perception",
            },
            {"type": "ping"},
        ]
    )
    await run_socket(main, socket, tokens["alice"])
    shared.execute.assert_not_awaited()
    shared.qca.process_input_multimodal.assert_not_awaited()
    assert any(event["type"] == "error" for event in socket.sent)
    assert any(event["type"] == "pong" for event in socket.sent)
    assert not any(
        event["type"] in {"task_started", "task_done", "perception_result"} for event in socket.sent
    )


async def test_failed_socket_delivery_stops_continuation_and_learning_and_saves_partial(
    legacy_api, monkeypatch, mock_wali, mock_izn
):
    main, _, tokens, memory = legacy_api
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", name="Delivery test", wali=mock_wali, izn=mock_izn)
    agent.ai_client = SimpleNamespace(provider_name="test")
    agent.ai_model = "test-model"
    continuation = AsyncMock()
    capture = AsyncMock()
    monkeypatch.setattr("learner.ruh_learner.RuhLearner.capture", capture)
    monkeypatch.setattr(agent, "_tafakkur", AsyncMock())

    async def controlled_think(*args, **kwargs):
        yield "Visible prefix"
        yield " pending continuation"
        await continuation()
        agent._record_llm_call(
            LLMResponse([ContentBlock("text", "Complete answer")], model="observed-model"), 1
        )
        yield "Complete answer"

    monkeypatch.setattr(agent, "think", controlled_think)
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    socket = FakeWebSocket(
        [{"type": "chat", "session_id": "cancelled-session", "content": "Perform a task"}],
        fail_stream_number=2,
    )
    await run_socket(main, socket, tokens["admin"])
    continuation.assert_not_awaited()
    capture.assert_not_awaited()
    assert agent.success_count == 0
    assert agent.current_task is None
    assert agent.state == "resting"
    assert not agent._execution_lock.locked()
    assert not any(event["type"] == "chat_complete" for event in socket.sent)
    visible = [event["chunk"] for event in socket.sent if event["type"] == "chat_stream"]
    assert visible == ["Visible prefix"]
    stored = await memory.get_messages("cancelled-session")
    assert stored[-1]["role"] == "assistant"
    assert stored[-1]["content"].startswith("Visible prefix")
    assert "Complete answer" not in stored[-1]["content"]
    assert stored[-1]["metadata"]["status"] == "cancelled"


async def test_socket_execution_setup_exception_is_terminal_and_persisted(legacy_api, monkeypatch):
    main, _, tokens, memory = legacy_api
    agent = SimpleNamespace(
        id="setup-agent",
        name="Setup test",
        ai_model="test-model",
        max_tool_turns=10,
        execute=AsyncMock(side_effect=ValueError("private setup diagnostic")),
    )
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    socket = FakeWebSocket([{"type": "chat", "session_id": "ws-setup-error", "content": "hello"}])
    await run_socket(main, socket, tokens["admin"])
    agent.execute.assert_awaited_once()
    assert any(event["type"] == "error" for event in socket.sent)
    assert not any(event["type"] == "chat_complete" for event in socket.sent)
    assert "private setup diagnostic" not in str(socket.sent)
    stored = await memory.get_messages("ws-setup-error")
    assert stored[-1]["role"] == "assistant"
    assert stored[-1]["metadata"]["status"] == "error"


@pytest.mark.parametrize("prefix", ["", "Partial response"])
def test_rest_execution_exception_has_terminal_error_and_persisted_partial(
    legacy_api, monkeypatch, prefix
):
    main, client, tokens, memory = legacy_api

    async def fail(*args, **kwargs):
        if prefix:
            await kwargs["stream_callback"](prefix)
        raise ValueError("private setup diagnostic")

    agent = SimpleNamespace(
        id="rest-agent",
        name="REST test",
        ai_model="test-model",
        max_tool_turns=10,
        execute=AsyncMock(side_effect=fail),
    )
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    broadcast = AsyncMock()
    monkeypatch.setattr(main.manager, "broadcast", broadcast)
    response = client.post(
        "/api/chat",
        json={"session_id": "rest-error", "content": "hello", "model_override": "unavailable"},
        headers={"Authorization": "Bearer " + tokens["admin"]},
    )
    assert response.status_code == 200
    agent.execute.assert_awaited_once()
    events = [call.args[0] for call in broadcast.await_args_list]
    assert any(event["type"] == "error" for event in events)
    assert not any(event["type"] == "chat_complete" for event in events)
    assert "private setup diagnostic" not in str(events)
    stored = asyncio.run(memory.get_messages("rest-error"))
    assert stored[-1]["role"] == "assistant"
    assert stored[-1]["content"] == prefix
    assert stored[-1]["metadata"]["status"] == "error"
