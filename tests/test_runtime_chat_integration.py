"""Regressions from production chat failures: continuity, failure truth and capture."""

from unittest.mock import AsyncMock

import pytest

from agents.specialized import create_agent
from learner.ruh_learner import RuhLearner
from memory import stateless
from memory.dhikr import DhikrMemorySystem
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from workspace.context import artifact_session


class ScriptedProvider(BaseLLMProvider):
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


def offer_fixture_tools(agent, monkeypatch, description, *names):
    """Provider fixtures may request only actions actually offered in that turn."""
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [
            {
                "name": name,
                "description": description,
                "input_schema": {"type": "object", "properties": {}},
            }
            for name in names
        ],
    )


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
    offer_fixture_tools(agent, monkeypatch, "Save a file", "workspace_write")
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
        # Training is opt-in (docs/consent.md): without the user's yes, no candidate.
        agent.ai_client = ScriptedProvider([answer("Hello")])
        result = await agent.execute("hi", {"session_id": "session-a"})
        assert result["success"] and "learning_capture" not in result
        unasked = RuhLearner.for_owner("alice")
        await unasked.initialize()
        assert (await unasked.get_stats())["total_interactions"] == 0

        agent.ai_client = ScriptedProvider([answer("Hello")])
        # The binding is available to tools during execution, and reset afterward.
        original = agent.ai_client.create

        def inspect_binding(**kwargs):
            assert artifact_session("") == "session-a"
            return original(**kwargs)

        agent.ai_client.create = inspect_binding
        with stateless.allow_training("training: on"):
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

    offer_fixture_tools(agent, monkeypatch, "Write and run", "workspace_write", "workspace_run")
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


async def test_tool_body_type_error_never_replays_a_committed_action(agent):
    calls = []

    async def save(*args, **kwargs):
        calls.append("saved")
        raise TypeError("serialization failed after save")

    result = await agent._invoke_with_healing(save, {"path": "a.txt"}, "save")
    assert calls == ["saved"]
    assert "serialization failed" in result["error"]


async def test_missing_dependency_does_not_install_or_replay(agent, monkeypatch):
    calls = []
    installer = AsyncMock(return_value=True)
    monkeypatch.setattr(agent, "_auto_install_package", installer)

    async def save(path):
        calls.append(path)
        raise ModuleNotFoundError("No module named 'httpx'")

    result = await agent._invoke_with_healing(save, {"path": "a.txt"}, "save")
    assert calls == ["a.txt"]
    assert "No module named" in result["error"]
    installer.assert_not_awaited()


async def test_signature_style_is_adapted_before_execution(agent):
    calls = []

    async def save(params):
        calls.append(params)
        return {"saved": True}

    assert await agent._invoke_with_healing(save, {"path": "a.txt"}, "save") == {"saved": True}
    assert calls == [{"path": "a.txt"}]


async def test_depleted_heuristic_energy_does_not_block_chat(agent):
    agent.ruh.get_state(agent.id).energy = 0
    agent.ai_client = ScriptedProvider([answer("Here is the requested answer")])
    result = await agent.execute("review the design")
    assert result["success"]
    assert agent.ai_client.calls == 1
    assert agent.current_task is None
    assert agent.state == "resting"
    assert result["task_verified"] is False


async def test_cancellation_clears_in_progress_state(agent, monkeypatch):
    import asyncio

    started = asyncio.Event()

    async def waiting(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
        yield "unreachable"

    monkeypatch.setattr(agent, "think", waiting)
    task = asyncio.create_task(agent.execute("hello"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert agent.current_task is None
    assert agent.state == "resting"
    assert not agent._execution_lock.locked()


async def test_tool_marker_without_stream_is_not_an_answer(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        [
            LLMResponse(
                [ContentBlock(type="tool_use", id="t1", name="workspace_write", input={})],
                "tool_use",
                "observed-model",
            ),
            LLMResponse([], "end_turn", "observed-model"),
        ]
    )
    monkeypatch.setattr(agent, "_execute_tool_safe", AsyncMock(return_value={"error": "denied"}))
    summary = AsyncMock()

    async def empty_summary(*args):
        await summary()
        if False:
            yield ""

    monkeypatch.setattr(agent, "_summarize_tool_results", empty_summary)
    result = await agent.execute("save a file")
    assert not result["success"]
    assert agent.success_count == 0
    summary.assert_awaited_once()
    assert agent.ai_client.calls == 2


async def test_provider_failure_does_not_retry_even_without_visible_text(agent):
    agent.ai_client = ScriptedProvider([RuntimeError("upstream unavailable"), answer("   ")])
    result = await agent.execute("hello")
    assert not result["success"]
    assert agent.success_count == 0
    assert agent.ai_client.calls == 1


async def test_summary_without_final_receipt_fails_without_replaying(agent, monkeypatch):
    agent.ai_client = ScriptedProvider([])

    async def missing_receipt(*args):
        yield "A partial summary"

    monkeypatch.setattr(agent, "_streaming_create", missing_receipt)
    chunks = []
    with pytest.raises(RuntimeError, match="completion record"):
        async for chunk in agent._summarize_tool_results("task", [{"name": "read", "result": {}}]):
            chunks.append(chunk)
    assert chunks == ["A partial summary"]
    assert agent.ai_client.calls == 0


async def test_abstention_is_delivered_without_success_learning_or_capture(agent, monkeypatch):
    from mizan_owned.provider import ABSTAIN

    agent.ai_client = ScriptedProvider(
        [
            LLMResponse(
                [ContentBlock(type="text", text=ABSTAIN)],
                "end_turn",
                "mizan-owned",
                {"owned_status": "abstained"},
            )
        ]
    )
    reflection = AsyncMock()
    monkeypatch.setattr(agent, "_tafakkur", reflection)
    token = bind_principal(TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "test"))
    try:
        result = await agent.execute("hello", {"session_id": "s"})
    finally:
        reset_principal(token)
    assert result["success"]  # Transport delivered the limitation honestly.
    assert result["completion_status"] == "abstained"
    assert result["usage"]["completion_status"] == "abstained"
    assert result["task_verified"] is False
    assert not result["capture_eligible"]
    assert "learning_capture" not in result
    assert agent.success_count == 0
    assert agent.shukr.stats(agent.id)["total_successes"] == 0
    reflection.assert_not_awaited()


async def test_no_configured_provider_is_an_error_not_a_fake_response(agent):
    agent.ai_client = None
    result = await agent.execute("hello")
    assert not result["success"]
    assert "No response model" in result["error"]
    assert agent.success_count == 0


async def test_failed_tool_receipt_is_not_a_verified_observation(agent, monkeypatch):
    from unittest.mock import Mock

    offer_fixture_tools(agent, monkeypatch, "Run the program", "workspace_run")
    observation = Mock(wraps=agent.yaqin.tag_observation)
    monkeypatch.setattr(agent.yaqin, "tag_observation", observation)
    monkeypatch.setattr(agent, "_execute_tool_safe", AsyncMock(return_value={"exit_code": 1}))
    agent.ai_client = ScriptedProvider(
        [
            LLMResponse(
                [ContentBlock(type="tool_use", id="t1", name="workspace_run", input={})],
                "tool_use",
                "observed-model",
            ),
            answer("The command failed."),
        ]
    )
    result = await agent.execute("run the program")
    assert result["success"]
    assert result["task_verified"] is False
    observation.assert_not_called()


async def test_pre_execution_tool_failure_does_not_repeat_other_actions(agent, monkeypatch):
    offer_fixture_tools(agent, monkeypatch, "Hello", "save", "failing_check")
    calls = []

    async def execute_tool(name, params):
        calls.append(name)
        if name == "failing_check":
            raise RuntimeError("permission service unavailable")
        return {"saved": True}

    monkeypatch.setattr(agent, "_execute_tool_safe", execute_tool)
    agent.ai_client = ScriptedProvider(
        [
            LLMResponse(
                [
                    ContentBlock(type="tool_use", id="t1", name="save", input={}),
                    ContentBlock(type="tool_use", id="t2", name="failing_check", input={}),
                ],
                "tool_use",
                "observed-model",
            )
        ]
    )
    result = await agent.execute("save and failing_check")
    assert not result["success"]
    assert calls == ["save", "failing_check"]
    assert agent.ai_client.calls == 1


def test_explicit_preferences_are_attributed_once_and_override_old_context(agent):
    messages = agent._build_messages(
        "Use English just for this reply",
        {
            "history": [{"role": "assistant", "content": "I am AGI"}],
            "user_preferences": [
                {"key": "language", "value": "Hinglish", "source": "explicit_user_preference"}
            ],
        },
    )
    text = messages[-1]["content"]
    assert '"value": "Hinglish"' not in str(messages)
    assert "[CURRENT USER REQUEST]\nUse English just for this reply\n" in text
    assert "Context:" not in text


async def test_council_runs_beside_an_active_execution_and_cannot_use_tools(agent, monkeypatch):
    import asyncio

    agent.ai_client = ScriptedProvider([])
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def execute_impl(task, *args):
        calls.append(task)
        if task == "first":
            entered.set()
            await release.wait()
            assert agent.get_tool_schemas()  # the council's read-only mode is its own
        else:
            assert agent.get_tool_schemas() == []
            result = await agent._execute_tool_safe("write_file", {"path": "should-not-exist"})
            assert "read-only council" in result["error"]
        return {"success": True, "result": "Advice"}

    monkeypatch.setattr(agent, "_execute_impl", execute_impl)
    first = asyncio.create_task(agent.execute("first"))
    await entered.wait()
    # The council does not wait for the active run: each run has its own copy.
    result = await asyncio.wait_for(agent.evaluate("the plan", {}), 1)
    assert calls == ["first", "Evaluate: the plan"] and not first.done()
    release.set()
    await first
    assert result["response"] == "Advice"
    assert result["task_verified"] is False
    assert agent.get_tool_schemas()  # Evaluation mode cannot leak to later requests.


def test_saved_agent_provider_override_survives_default_provider_change(monkeypatch):
    from unittest.mock import Mock

    from agents.base import BaseAgent

    provider = ScriptedProvider([])
    provider.provider_name = "openrouter"
    factory = Mock(return_value=provider)
    monkeypatch.setattr("agents.base.create_provider", factory)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    agent = BaseAgent(
        config={
            "provider_override": {"provider": "openrouter", "model": "anthropic/claude-example"}
        }
    )
    factory.assert_called_once_with(provider="openrouter", model="anthropic/claude-example")
    assert agent.ai_client is provider
    assert agent.ai_model == "anthropic/claude-example"


async def test_request_model_override_is_normalized_for_actual_adapter(agent, monkeypatch):
    from unittest.mock import Mock

    agent.ai_client = ScriptedProvider([])
    provider = ScriptedProvider([answer("Hello")])
    provider.provider_name = "openrouter"
    create = Mock(wraps=provider.create)
    provider.create = create
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: provider)
    result = await agent.execute("hello", model_override="claude-sonnet-4-20250514")
    assert result["success"]
    assert create.call_args.kwargs["model"] == "anthropic/claude-sonnet-4"
    assert agent.ai_model == "requested-model"


@pytest.mark.parametrize("provider_succeeds", [True, False])
async def test_secondary_task_telemetry_cannot_change_provider_outcome(agent, provider_succeeds):
    from types import SimpleNamespace
    from unittest.mock import Mock

    save_task = AsyncMock(side_effect=RuntimeError("task metrics DB unavailable"))
    encode = Mock(side_effect=RuntimeError("pathway cache unavailable"))
    agent.memory = SimpleNamespace(
        save_task=save_task,
        masalik=SimpleNamespace(
            stats=lambda: {"total_concepts": 0, "total_pathways": 0, "hikmah_pathways": 0},
            encode=encode,
        ),
    )
    agent.ai_client = ScriptedProvider(
        [answer("The requested answer")]
        if provider_succeeds
        else [RuntimeError("original upstream failure")] * 2
    )
    result = await agent.execute("hello")
    assert result["success"] is provider_succeeds
    assert agent.success_count == int(provider_succeeds)
    assert agent.error_count == int(not provider_succeeds)
    assert agent.ai_client.calls == 1
    save_task.assert_awaited_once()
    encode.assert_called_once()
    if provider_succeeds:
        assert "The requested answer" in result["result"]
    else:
        assert result["error"] == "original upstream failure"
