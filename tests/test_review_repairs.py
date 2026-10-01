"""Regression controls for the independently reproduced review findings."""

import asyncio
import ipaddress
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from memory.dhikr import DhikrMemorySystem
from memory.memory_pyramid import MemoryPyramid
from security.auth import MizanAuth, TokenPayload, bind_principal, reset_principal
from task_queue.task_queue import MizanTaskQueue


@pytest.fixture
def api_fixture(tmp_path, monkeypatch):
    import api.main as main

    auth = MizanAuth("review-test-key-" * 4, data_dir=str(tmp_path / "users"))
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setattr(main, "active_sessions", {})
    monkeypatch.setattr(main, "active_agents", {})
    monkeypatch.setattr(main, "manager", main.ConnectionManager())
    users = {
        name: auth.create_user(name, "test-password", roles=[role])
        for name, role in [("alice", "user"), ("bob", "user"), ("admin", "admin")]
    }
    tokens = {name: auth.create_token(user) for name, user in users.items()}
    return main, TestClient(main.app), tokens, memory


def header(token):
    return {"Authorization": "Bearer " + token}


def test_sensitive_endpoints_deny_anonymous_and_user_admin_alias(api_fixture):
    _, client, tokens, _ = api_fixture
    for path, body in [
        ("/api/skills/execute", {"skill": "kitab_notebook", "action": "create"}),
        ("/api/knowledge/ingest", {"source": "http://127.0.0.1/"}),
        ("/api/settings", {}),
        ("/api/preferences", {"active_provider": "openai"}),
    ]:
        assert client.post(path, json=body).status_code == 401
    assert client.get("/api/chat/guess").status_code == 401
    assert (
        client.post(
            "/api/preferences", json={"active_provider": "openai"}, headers=header(tokens["alice"])
        ).status_code
        == 403
    )
    assert client.get("/does-not-exist").status_code == 404
    assert client.get("/").status_code == 200
    for path in ("/api/status", "/api/integrations", "/api/nafs/tiers"):
        assert client.get(path, headers=header(tokens["alice"])).status_code == 403
    assert (
        client.get("/api/qalb/trend/another-user", headers=header(tokens["alice"])).status_code
        == 403
    )
    assert (
        client.post(
            "/api/qalb/analyze",
            json={"message": "hello", "user_id": "another-user"},
            headers=header(tokens["alice"]),
        ).status_code
        == 403
    )


async def test_request_local_provider_and_delegation_cycle(monkeypatch):
    from agents import base

    agent = object.__new__(base.BaseAgent)
    agent.ai_model, agent.ai_client = "configured", "original-provider"
    monkeypatch.setattr(base, "create_provider", lambda **kw: kw["model"] + "-provider")
    entered, release = asyncio.Event(), asyncio.Event()

    async def impl(self, task, *args):
        entered.set()
        await release.wait()
        return {"result": [self.ai_model, self.ai_client]}

    agent._execute_impl = MethodType(impl, agent)
    first = asyncio.create_task(agent.execute("first", model_override="requested"))
    await entered.wait()
    assert agent.ai_model == "configured"
    agent.ai_model = "changed-default"
    release.set()
    assert (await first)["result"] == ["requested", "requested-provider"]
    assert agent.ai_model == "changed-default"
    other = object.__new__(base.BaseAgent)
    other.ai_model, other.ai_client = "other", None

    async def a(self, task, *args):
        return await other.execute(task)

    async def b(self, task, *args):
        return await agent.execute(task)

    agent._execute_impl, other._execute_impl = MethodType(a, agent), MethodType(b, other)
    with pytest.raises(ValueError, match="Cyclic"):
        await asyncio.wait_for(agent.execute("cycle"), 1)
    assert not agent._execution_lock.locked() and not other._execution_lock.locked()


async def test_summarization_fallback_records_billed_call():
    from agents.base import BaseAgent
    from providers import ContentBlock, LLMResponse

    agent = object.__new__(BaseAgent)
    agent.ai_model = "requested"
    agent.ai_client = SimpleNamespace(
        create=lambda **kw: LLMResponse(
            [ContentBlock("text", "summary")],
            model="observed",
            usage={"input": 7, "output": 3, "cost": 0.01},
        )
    )

    async def broken(*args):
        raise RuntimeError("stream unavailable")
        yield

    agent._streaming_create = broken
    assert [part async for part in agent._summarize_tool_results("task", [])] == ["summary"]
    assert len(agent._llm_calls) == 1
    assert agent._llm_calls[0]["response"].model == "observed"


def test_nonstream_provider_cost_and_mounted_modes_contract(monkeypatch):
    from api import modes
    from providers import OpenAICompatibleProvider

    provider = object.__new__(OpenAICompatibleProvider)
    message = SimpleNamespace(content="answer", tool_calls=None)
    completion = SimpleNamespace(
        model="observed",
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3, cost=0.01),
    )
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: completion))
    )
    response = provider.create("requested", 10, "", [{"role": "user", "content": "hello"}])
    assert response.model == "observed" and response.usage["cost"] == 0.01
    monkeypatch.setattr("providers.create_provider", lambda **kw: provider)
    assert modes._chat_completion_sync(
        "requested", "", [{"role": "user", "content": "hello"}], 10
    ) == ("answer", 7, 3)


def test_chat_usage_persisted_across_restart(api_fixture, monkeypatch):
    main, client, tokens, memory = api_fixture
    usage = {
        "model": "observed",
        "input_tokens": 9,
        "output_tokens": 4,
        "cost_usd": 0.01,
        "cost_estimated": False,
        "calls": [{"model": "observed"}],
    }
    agent = SimpleNamespace(
        id="test-agent",
        name="Test",
        max_tool_turns=10,
        execute=AsyncMock(return_value={"success": True, "result": "answer", "usage": usage}),
    )
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    response = client.post(
        "/api/chat",
        json={"session_id": "usage-session", "content": "hello"},
        headers=header(tokens["admin"]),
    )
    assert response.status_code == 200
    restored = DhikrMemorySystem(memory.db_path)
    messages = asyncio.run(restored.get_messages("usage-session"))
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["metadata"]["usage"] == usage


async def test_training_drains_real_stderr_flood(tmp_path, monkeypatch):
    import sys

    import training_manager as module

    monkeypatch.setattr(module, "_HISTORY_FILE", tmp_path / "history.json")
    manager = module.TrainingManager()
    manager._state.running = True
    manager._process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        'import sys; sys.stderr.write(\'x\'*2000000); print(\'{"type":"start","epochs":2}\')',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait_for(manager._monitor_output(), 5)
    assert manager._process.returncode == 0 and not manager._state.running
    assert manager._state.total_epochs == 2


def test_sandbox_retains_bounded_output_and_reaps_timeout():
    import sys

    from api.sandbox import MAX_OUTPUT_BYTES, _bounded_process

    stdout, stderr, status, expired = _bounded_process(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x'*2000000); sys.stderr.write('y'*2000000)",
        ],
        5,
    )
    assert status == 0 and not expired
    assert "truncated" in stdout and "truncated" in stderr
    assert len(stdout) < MAX_OUTPUT_BYTES + 200 and len(stderr) < MAX_OUTPUT_BYTES + 200
    _, stderr, status, expired = _bounded_process(
        [sys.executable, "-c", "import time; time.sleep(10)"], 1
    )
    assert status == 124 and expired and "timed out" in stderr


def test_http_session_ownership_and_legacy_claim(api_fixture):
    _, client, tokens, memory = api_fixture
    body = {"session_id": "test-owned", "content": "/help"}
    assert client.post("/api/chat", json=body, headers=header(tokens["alice"])).status_code == 200
    assert client.get("/api/chat/test-owned", headers=header(tokens["alice"])).status_code == 200
    assert client.get("/api/chat/test-owned", headers=header(tokens["bob"])).status_code == 404
    assert client.post("/api/chat", json=body, headers=header(tokens["bob"])).status_code == 404
    listing = client.get("/api/chat/sessions/list", headers=header(tokens["bob"])).json()
    assert listing["sessions"] == []
    restored = DhikrMemorySystem(memory.db_path)
    assert asyncio.run(restored.authorize_session("test-owned", "intruder", create=True)) is False
    asyncio.run(memory.save_message("legacy-private", "user", "old confidential data"))
    assert (
        client.post(
            "/api/chat",
            json={**body, "session_id": "legacy-private"},
            headers=header(tokens["bob"]),
        ).status_code
        == 404
    )


def test_websocket_auth_and_duplicate_labels(api_fixture):
    main, client, tokens, _ = api_fixture
    for suffix in ("", "?token=invalid"):
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            client.websocket_connect("/ws/shared" + suffix),
        ):
            pass
        assert exc.value.code == 4401
    with client.websocket_connect("/ws/shared?token=" + tokens["alice"]) as alice:
        assert alice.receive_json()["authenticated"]
        with client.websocket_connect("/ws/shared?token=" + tokens["bob"]) as bob:
            assert bob.receive_json()["authenticated"]
            assert len(main.manager.connections) == 2
            alice.send_json({"type": "chat", "session_id": "alice-session", "content": "/help"})
            assert alice.receive_json()["type"] == "command_result"
            bob.send_json({"type": "command", "command": "/new", "session_id": "alice-session"})
            assert bob.receive_json()["type"] == "error"
            bob.send_json({"type": "ping"})
            assert bob.receive_json() == {"type": "pong"}


async def test_notebook_owner_spoof_and_fail_closed(monkeypatch, tmp_path):
    from api import sandbox
    from skills.builtin.kitab_notebook import KitabNotebookSkill

    skill = KitabNotebookSkill()
    assert "error" in await skill.create_notebook({"title": "anonymous"})
    principal = TokenPayload("admin-a", "admin", ["admin"], 9999999999, 0, "x")
    binding = bind_principal(principal)
    try:
        nb = await skill.create_notebook({"title": "safe", "user_id": "spoofed"})
        assert skill.notebooks[nb["id"]].owner == "admin-a"
        cell = await skill.add_cell(
            {
                "notebook_id": nb["id"],
                "source": f"from pathlib import Path; Path({str(tmp_path / 'proof')!r}).write_text('bad')",
            }
        )
        monkeypatch.setattr(sandbox, "detect_provider", lambda: None)
        result = await skill.execute_cell({"notebook_id": nb["id"], "cell_id": cell["cell"]["id"]})
        assert result["cell"]["status"] == "error"
        assert not (tmp_path / "proof").exists()
        assert (await skill.executor.execute_shell("echo bad"))["output_type"] == "error"
    finally:
        reset_principal(binding)
    other = bind_principal(TokenPayload("admin-b", "admin", ["admin"], 9999999999, 0, "y"))
    try:
        assert "error" in await skill.get_notebook({"notebook_id": nb["id"]})
        assert (await skill.list_notebooks())["notebooks"] == []
    finally:
        reset_principal(other)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "224.0.0.1"]
)
async def test_ssrf_resolved_private_rejected(monkeypatch, address):
    from knowledge.ingest import _public_destination

    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(return_value=[(0, 0, 0, "", (address, 80))]),
    )
    with pytest.raises(ValueError, match="non-public"):
        await _public_destination("https://example.test/")


async def test_public_destination_is_pinned_and_tls_hostname_retained(monkeypatch):
    from knowledge.ingest import _public_destination

    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]),
    )
    destination, host, tls = await _public_destination("https://example.test/path")
    assert ipaddress.ip_address(destination.host).is_global
    assert host == tls == "example.test"


async def test_ssrf_redirect_rechecks_and_stream_size_is_bounded(monkeypatch):
    import httpx

    from knowledge import ingest

    loop = asyncio.get_running_loop()
    dns = AsyncMock(
        side_effect=[[(0, 0, 0, "", ("93.184.216.34", 80))], [(0, 0, 0, "", ("127.0.0.1", 80))]]
    )
    monkeypatch.setattr(loop, "getaddrinfo", dns)
    real_client = httpx.AsyncClient
    calls = []

    def redirect(request):
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "public.test"
        return httpx.Response(302, headers={"location": "http://internal.test/"})

    def factory(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(redirect), **kwargs)

    monkeypatch.setattr(ingest.httpx, "AsyncClient", factory)
    with pytest.raises(ValueError, match="non-public"):
        await ingest.extract_url("http://public.test/")
    assert len(calls) == 1 and dns.await_count == 2

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 512
            yield b"x" * 600

    monkeypatch.setattr(
        loop, "getaddrinfo", AsyncMock(return_value=[(0, 0, 0, "", ("93.184.216.34", 80))])
    )
    monkeypatch.setattr(ingest, "MAX_FETCH_BYTES", 1024)
    monkeypatch.setattr(
        ingest.httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=Body())), **kw
        ),
    )
    with pytest.raises(ValueError, match="size limit"):
        await ingest.extract_url("http://public.test/")


async def test_graph_recall_and_interrupted_queue(tmp_path):
    graph = SimpleNamespace(
        search_entities=AsyncMock(return_value=[{"name": "Known entity", "type": "concept"}])
    )
    hits = await MemoryPyramid(knowledge_graph=graph).query_async("Known")
    assert len(hits) == 1 and hits[0].source_layer == "graph"
    queue = MizanTaskQueue(str(tmp_path / "queue.db"))
    await queue.initialize()
    task_id = await queue.enqueue({"effect": "do-once"})
    await queue.dequeue()
    restored = MizanTaskQueue(queue._db_path)
    await restored.initialize()
    task = await restored.get_task(task_id)
    assert task.status == "failed" and "Interrupted" in task.error
    assert await restored.dequeue() is None
