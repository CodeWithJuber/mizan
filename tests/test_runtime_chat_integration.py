"""Regressions from production chat failures: continuity, failure truth and capture."""

from unittest.mock import AsyncMock

import pytest

from agents.specialized import create_agent
from learner.ruh_learner import RuhLearner
from memory.dhikr import DhikrMemorySystem
from providers import ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from workspace.context import artifact_session


class ScriptedProvider:
    provider_name = "test-provider"
    supports_tools = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def answer(text):
    return LLMResponse([ContentBlock(type="text", text=text)], "end_turn", "observed-model")


@pytest.fixture
def agent(mock_wali, mock_izn, monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    result = create_agent("general", name="Runtime test", wali=mock_wali, izn=mock_izn)
    result.ai_model = "requested-model"
    return result


async def test_provider_failure_is_not_a_successful_lesson(agent, monkeypatch):
    agent.ai_client = ScriptedProvider([RuntimeError("upstream 502")] * 3)
    reflection = AsyncMock()
    monkeypatch.setattr(agent, "_tafakkur", reflection)
    chunks = AsyncMock()
    result = await agent.execute("hello", stream_callback=chunks)
    assert result["success"] is False
    assert agent.success_count == 0
    assert agent.error_count == 1
    assert reflection.await_args.args[2] is False
    chunks.assert_not_awaited()


async def test_partial_stream_failure_does_not_replay_request(agent, monkeypatch):
    agent.ai_client = ScriptedProvider([])

    async def broken_stream(*args):
        yield "Partial answer"
        raise RuntimeError("upstream 502")

    monkeypatch.setattr(agent, "_streaming_create", broken_stream)
    chunks = AsyncMock()
    result = await agent.execute("hello", stream_callback=chunks)
    assert result["success"] is False
    assert agent.ai_client.calls == 0
    assert [c.args[0] for c in chunks.await_args_list] == ["Partial answer"]
    assert agent.success_count == 0


async def test_completed_tool_is_not_repeated_after_provider_failure(agent, monkeypatch):
    provider = ScriptedProvider(
        [
            LLMResponse(
                [ContentBlock(type="tool_use", id="t1", name="workspace_write", input={})],
                "tool_use",
                "test",
            ),
            RuntimeError("upstream 502"),
        ]
    )
    agent.ai_client = provider
    execute_tool = AsyncMock(return_value={"saved": True})
    monkeypatch.setattr(agent, "_execute_tool_safe", execute_tool)
    result = await agent.execute("save a file", stream_callback=AsyncMock())
    assert not result["success"]
    assert provider.calls == 2
    execute_tool.assert_awaited_once()
    assert agent.success_count == 0


async def test_chat_capture_is_owned_unreviewed_and_bound_to_session(agent):
    alice = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "test")
    token = bind_principal(alice)
    try:
        agent.ai_client = ScriptedProvider([answer("Hello")])
        # The binding is available to tools during execution, and reset afterward.
        original = agent.ai_client.create

        def inspect_binding(**kwargs):
            assert artifact_session("") == "session-a"
            return original(**kwargs)

        agent.ai_client.create = inspect_binding
        result = await agent.execute("hi", {"session_id": "session-a"})
        assert result["success"]
        assert result["learning_capture"] == "unreviewed_candidate"
        learner = RuhLearner.for_owner("alice")
        records = await learner.get_recent()
        assert records[0]["model"] == "observed-model"
        assert records[0]["quality_score"] == 0
        assert (await learner.get_stats())["exportable_count"] == 0
        other = RuhLearner.for_owner("bob")
        await other.initialize()
        assert (await other.get_stats())["total_interactions"] == 0
        with pytest.raises(Exception, match="chat session is required"):
            artifact_session("")
    finally:
        reset_principal(token)


async def test_conversation_recall_survives_restart_without_cross_user_or_assistant_claims(
    tmp_path,
):
    path = str(tmp_path / "memory.db")
    memory = DhikrMemorySystem(path)
    for session, owner in (("alice-old", "alice"), ("bob-old", "bob"), ("current", "alice")):
        assert await memory.authorize_session(session, owner, create=True)
    source_id = await memory.save_message("alice-old", "user", "Use Hinglish for explanations")
    await memory.save_message("alice-old", "assistant", "I have achieved AGI")
    await memory.save_message("bob-old", "user", "Bob's private Hinglish note")
    await memory.save_message("legacy", "user", "unowned note")
    await memory.save_message("current", "user", "current task")
    restarted = DhikrMemorySystem(path)
    hits = await restarted.recall_conversations("alice", "Hinglish", exclude_session="current")
    assert len(hits) == 1
    assert hits[0]["message_id"] == source_id
    assert hits[0]["source"] == "prior_user_statement"
    assert hits[0]["session_id"] == "alice-old"
    assert not await restarted.recall_conversations("", "Hinglish", exclude_session="current")
    counts = await restarted.conversation_counts("alice")
    assert counts == {"owned_sessions": 2, "stored_chat_messages": 3}


async def test_restarted_session_uses_latest_history_in_chronological_order(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    for n in range(60):
        await memory.save_message("conversation", "user", f"turn {n}")
    latest = await memory.get_messages("conversation", limit=10)
    assert [m["content"] for m in latest] == [f"turn {n}" for n in range(50, 60)]


def test_message_builder_does_not_repeat_history(agent):
    messages = agent._build_messages(
        "unique current input 918",
        {
            "session_id": "s",
            "history": [{"role": "user", "content": "previous request"}],
            "conversation_memory": [{"content": "Use Hinglish", "source": "prior_user_statement"}],
        },
    )
    text = "\n".join(m["content"] for m in messages)
    assert text.count("previous request") == 1
    assert text.count("unique current input 918") == 1
    assert "Use Hinglish" in text
    assert "not verified facts" in text


async def test_workspace_write_finishes_before_run_in_same_model_turn(agent, monkeypatch):
    import asyncio

    written = False
    order = []

    async def execute_tool(name, params):
        nonlocal written
        if name == "workspace_write":
            await asyncio.sleep(0.01)
            written = True
        else:
            assert written, "Run raced the file write"
        order.append(name)
        return {"ok": True}

    monkeypatch.setattr(agent, "_execute_tool_safe", execute_tool)
    agent.ai_client = ScriptedProvider(
        [
            LLMResponse(
                [
                    ContentBlock(type="tool_use", id="write", name="workspace_write", input={}),
                    ContentBlock(type="tool_use", id="run", name="workspace_run", input={}),
                ],
                "tool_use",
                "observed-model",
            ),
            answer("Done"),
        ]
    )
    result = await agent.execute("write and run", stream_callback=AsyncMock())
    assert result["success"]
    assert order == ["workspace_write", "workspace_run"]


async def test_stream_without_final_receipt_does_not_replay(agent, monkeypatch):
    agent.ai_client = ScriptedProvider([])

    async def incomplete_stream(*args):
        yield "Saved prefix"

    monkeypatch.setattr(agent, "_streaming_create", incomplete_stream)
    chunks = AsyncMock()
    result = await agent.execute("hello", stream_callback=chunks)
    assert not result["success"]
    assert agent.ai_client.calls == 0
    assert [c.args[0] for c in chunks.await_args_list] == ["Saved prefix"]
