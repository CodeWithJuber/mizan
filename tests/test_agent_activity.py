"""Live agent activity: tool events, todo lists and Izn approvals (ask/auto_edits/plan)."""

import asyncio
from unittest.mock import MagicMock

import pytest

from agents import events, session_state
from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security import approvals
from security.approvals import ApprovalBroker, ApprovalContext, bind_approvals, request_approval
from security.auth import TokenPayload, bind_principal, reset_principal
from workspace.context import bind_chat_session, reset_chat_session

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")


class Recorder:
    def __init__(self):
        self.events = []

    async def __call__(self, kind, payload):
        self.events.append((kind, payload))


def text(value):
    return LLMResponse(content=[ContentBlock(type="text", text=value)], stop_reason="end_turn")


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fake"

    def __init__(self, script):
        self.script = list(script)

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        return self.script.pop(0)


def agent_with(script):
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Activity", wali=MagicMock(), izn=izn)
    agent.ai_model = "fake-model"
    agent.ai_client = ScriptedProvider(script)
    return agent


def tool_call(name, call_id="call-1", **arguments):
    return LLMResponse(
        content=[ContentBlock(type="tool_use", id=call_id, name=name, input=arguments)],
        stop_reason="tool_use",
    )


async def collect(agen):
    return [chunk async for chunk in agen]


async def test_events_need_a_sink_and_are_bounded():
    await events.emit("tool_start", {"name": "x"})  # no sink: silently nothing
    recorder = Recorder()
    with events.bind_event_sink(recorder):
        await events.emit(
            "tool_start",
            {"name": "x", "input": {"api_key": "sk-secret", "body": "y" * 50_000}},
        )
    kind, payload = recorder.events[0]
    assert kind == "tool_start"
    assert payload["input"]["api_key"] == "[redacted]"
    assert len(payload["input"]["body"]) < 40_000


async def test_tool_start_and_result_are_paired(monkeypatch):
    agent = agent_with([tool_call("list_files", path="."), text("done")])

    async def run_tool(name, params):
        return {"files": ["a.py"], "diff": "+line"}

    agent._execute_tool_safe = run_tool
    recorder = Recorder()
    schemas = [{"name": "list_files", "description": "d", "input_schema": {"type": "object"}}]
    with events.bind_event_sink(recorder):
        await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "go"}], schemas, False, "go")
        )
    kinds = [kind for kind, _ in recorder.events]
    assert kinds == ["tool_start", "tool_result"]
    start, result = recorder.events[0][1], recorder.events[1][1]
    assert start["call_id"] == result["call_id"] == "call-1"
    assert result["ok"] is True and result["diff"] == "+line"


async def test_todo_list_is_saved_emitted_and_shown_next_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    agent = agent_with([])
    recorder = Recorder()
    principal, session = bind_principal(USER), bind_chat_session("chat-1")
    try:
        with events.bind_event_sink(recorder):
            receipt = await agent._tool_todo_write(
                todos=[
                    {"content": "Read the code", "status": "completed"},
                    {"content": "Fix the bug", "status": "in_progress"},
                ]
            )
        assert receipt == {"todos": 2, "completed": 1, "saved": True}
        assert recorder.events[0][0] == "todo"
        messages = agent._build_messages("next step?", {"session_id": "chat-1"})
        assert "[x] Read the code" in messages[-2]["content"]
        assert "[~] Fix the bug" in messages[-2]["content"]
        bad = await agent._tool_todo_write(
            todos=[
                {"content": "a", "status": "in_progress"},
                {"content": "b", "status": "in_progress"},
            ]
        )
        assert "error" in bad
        assert len(session_state.load(USER.user_id, "chat-1")["todos"]) == 2
    finally:
        reset_chat_session(session)
        reset_principal(principal)


def test_mode_matrix():
    assert not ApprovalContext("u", "s", "auto").needs_approval("workspace_run")
    edits = ApprovalContext("u", "s", "auto_edits")
    assert not edits.needs_approval("workspace_edit") and edits.needs_approval("workspace_run")
    ask = ApprovalContext("u", "s", "ask")
    assert ask.needs_approval("workspace_edit") and not ask.needs_approval("workspace_read")
    plan = ApprovalContext("u", "s", "plan")
    assert plan.blocks("workspace_write") and not plan.blocks("workspace_grep")
    assert not ask.needs_approval("mcp__github__list_issues", read_only_hint=True)


async def run_with_decision(agent, context, decision, tool="workspace_run"):
    recorder = Recorder()
    ran = []

    async def handler(**params):
        ran.append(params)
        return {"ok": True}

    agent.tools[tool] = handler
    monkey_allowed = agent._chat_tool_allowed
    agent._chat_tool_allowed = lambda name: True

    async def answer():
        while not any(kind == "approval_request" for kind, _ in recorder.events):
            await asyncio.sleep(0.01)
        request = next(p for kind, p in recorder.events if kind == "approval_request")
        if decision is not None:
            assert approvals.broker.resolve(USER.user_id, request["approval_id"], decision)

    with events.bind_event_sink(recorder), bind_approvals(context):
        answering = asyncio.create_task(answer())
        result = await agent._execute_tool_safe(tool, {"command": "pytest"})
        await answering
    agent._chat_tool_allowed = monkey_allowed
    return result, ran, recorder


async def test_ask_mode_waits_and_resumes_on_allow():
    agent = agent_with([])
    context = ApprovalContext(USER.user_id, "chat-1", "auto_edits")
    result, ran, recorder = await run_with_decision(agent, context, "allow")
    assert result == {"ok": True} and ran == [{"command": "pytest"}]
    assert (
        "approval_resolved",
        {"approval_id": recorder.events[0][1]["approval_id"], "decision": "allow"},
    ) in recorder.events


async def test_deny_and_timeout_return_receipts(monkeypatch):
    agent = agent_with([])
    context = ApprovalContext(USER.user_id, "chat-1", "ask")
    result, ran, _ = await run_with_decision(agent, context, "deny")
    assert result["declined"] is True and not ran
    monkeypatch.setattr(approvals, "APPROVAL_TIMEOUT_SECONDS", 0.05)
    result, ran, _ = await run_with_decision(agent, context, None)
    assert result["declined"] is True and not ran


async def test_always_allow_is_scoped_to_the_session_context():
    agent = agent_with([])
    context = ApprovalContext(USER.user_id, "chat-1", "ask")
    await run_with_decision(agent, context, "always")
    assert "workspace_run" in context.always
    assert not context.needs_approval("workspace_run")
    assert ApprovalContext(USER.user_id, "chat-2", "ask").needs_approval("workspace_run")


async def test_cross_user_resolution_rejected():
    broker = ApprovalBroker()
    approval_id, future = broker.open(ApprovalContext("alice", "s"), "workspace_run")
    assert not broker.resolve("mallory", approval_id, "allow")
    assert not broker.resolve("alice", approval_id, "sure")
    assert broker.pending_for("mallory") == []
    assert broker.resolve("alice", approval_id, "deny")
    assert await future == "deny"


async def test_plan_mode_filters_and_enforces():
    agent = agent_with([])
    agent._chat_tool_allowed = lambda name: True
    with bind_approvals(ApprovalContext(USER.user_id, "chat-1", "plan")):
        names = {schema["name"] for schema in agent.get_tool_schemas()}
        assert "write_file" not in names and "bash" not in names
        assert "read_file" in names and "todo_write" in names
        refused = await agent._execute_tool_safe("write_file", {"path": "/tmp/x", "content": "y"})
        assert refused["plan_mode"] is True
        messages = agent._build_messages("plan it", {})
        assert "PLAN MODE" in messages[-2]["content"]


async def test_without_a_sink_legacy_runs_are_not_prompted():
    agent = agent_with([])
    ran = []

    async def handler(**params):
        ran.append(params)
        return {"ok": True}

    agent.tools["workspace_run"] = handler
    agent._chat_tool_allowed = lambda name: True
    assert await agent._execute_tool_safe("workspace_run", {"command": "ls"}) == {"ok": True}
    # A context without a deliverable sink can never silently approve.
    with bind_approvals(ApprovalContext(USER.user_id, "s", "ask")):
        result = await agent._execute_tool_safe("workspace_run", {"command": "ls"})
    assert result["declined"] is True and len(ran) == 1


async def test_request_approval_without_sink_denies():
    assert await request_approval(ApprovalContext("u", "s", "ask"), "x", {}) == "deny"


@pytest.fixture
def sse_api(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi.testclient import TestClient

    import api.main as main
    from memory.dhikr import DhikrMemorySystem
    from security.auth import MizanAuth

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("activity-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    user = auth.create_user("alice", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setenv("DB_PATH", memory.db_path)
    monkeypatch.setattr(main, "active_sessions", {})
    monkeypatch.setattr(main, "_stream_sessions", set())
    monkeypatch.setattr(main, "_stream_runs", {})
    monkeypatch.setattr(main, "chat_agent_for", AsyncMock(side_effect=lambda user, agent: agent))
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock(), send=AsyncMock()))

    class Agent:
        id, name, ai_model = "activity-agent", "Khalifah", "fake"
        _llm_calls, _last_tool_results = [], []

        async def execute(self, content, context, **callbacks):
            mode = approvals.current_approvals()
            await events.emit(
                "todo",
                {"todos": [{"content": "x", "status": "pending"}], "mode": mode and mode.mode},
            )
            await callbacks["stream_callback"]("ok")
            return {"success": True, "result": "ok", "usage": {}}

    monkeypatch.setattr(main, "active_agents", {"activity-agent": Agent()})
    return TestClient(main.app), {"Authorization": "Bearer " + auth.create_token(user)}


def test_stream_forwards_activity_and_binds_permission_mode(sse_api):
    import json
    import uuid

    client, headers = sse_api
    body = {
        "session_id": "s1",
        "content": "hi",
        "request_id": str(uuid.uuid4()),
        "permission_mode": "ask",
    }
    response = client.post("/api/chat/stream", json=body, headers=headers)
    payloads = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    todo = next(p for p in payloads if p["type"] == "todo")
    assert todo["mode"] == "ask" and todo["todos"][0]["content"] == "x"
    bad = {**body, "request_id": str(uuid.uuid4()), "permission_mode": "yolo"}
    assert client.post("/api/chat/stream", json=bad, headers=headers).status_code == 422
    assert (
        client.post(
            "/api/chat/approvals/" + "a" * 32, json={"decision": "allow"}, headers=headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/chat/approvals/" + "a" * 32, json={"decision": "maybe"}, headers=headers
        ).status_code
        == 422
    )
    assert client.get("/api/chat/approvals", headers=headers).json() == {"pending": []}
