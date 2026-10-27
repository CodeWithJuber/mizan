"""An ambiguous provider POST is never replayed, and no-progress is bounded."""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.provider_limits import ProviderLimits, provider_limits
from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse, _OpenAIStreamWrapper


def chunk(*, content=None, reasoning=None, calls=None, finish=None):
    return SimpleNamespace(
        model="fixture-model",
        choices=[
            SimpleNamespace(
                finish_reason=finish,
                delta=SimpleNamespace(content=content, reasoning=reasoning, tool_calls=calls),
            )
        ],
    )


def tool_delta(arguments, *, first=False):
    return chunk(
        calls=[
            SimpleNamespace(
                index=0,
                id="tool-1" if first else None,
                function=SimpleNamespace(
                    name="recall_memory" if first else None, arguments=arguments
                ),
            )
        ]
    )


class SlowChunks:
    def __init__(self, chunks, delay=0.015):
        self.chunks, self.delay = chunks, delay
        self.closed = threading.Event()

    def __iter__(self):
        for item in self.chunks:
            if self.closed.wait(self.delay):
                return
            yield item

    def close(self):
        self.closed.set()


class NativeFixture(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, streams):
        self.streams, self.posts, self.create_posts = list(streams), 0, 0
        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self.post))
        )

    def post(self, **kwargs):
        self.posts += 1
        return self.streams[self.posts - 1]

    def stream(self, **kwargs):
        return _OpenAIStreamWrapper(self.client, "fixture-model", 128, [])

    def create(self, **kwargs):
        self.create_posts += 1
        raise AssertionError("Ambiguous stream must not be replayed")


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    monkeypatch.setattr("agents.base.provider_limits", lambda: ProviderLimits(0.05, 0.05, 0.4))
    result = create_agent("general")
    result.ai_model = "fixture-model"
    return result


@pytest.mark.parametrize("hidden", [True, False])
async def test_hidden_reasoning_or_comments_do_not_hold_a_session_forever(agent, hidden):
    # Reasoning shows the model is working, so only the total budget ends it;
    # comments and keepalives show nothing, so the first-progress wait does.
    item = chunk(reasoning="private hidden trace") if hidden else SimpleNamespace(choices=[])
    stream = SlowChunks([item] * 100)
    provider = NativeFixture([stream])
    agent.ai_client = provider
    result = await asyncio.wait_for(agent.execute("answer", stream_callback=AsyncMock()), 2)
    assert not result["success"]
    assert result["error_code"] == "provider_timeout"
    assert result["provider_timeout_phase"] == ("total" if hidden else "first_progress")
    assert provider.posts == 1 and provider.create_posts == 0
    assert stream.closed.is_set()
    assert result["usage"].get("calls", []) == []
    assert result["usage"]["timings"]["provider_attempts"][0]["outcome"] == "timed_out"
    assert not result["answer_delivered"] and not result["task_verified"]


async def test_reasoning_before_the_answer_can_outlast_the_first_progress_wait(agent):
    # Production: a reasoning model thought past the 60 s first-progress wait
    # and its answer was cut off as "exceeded its wait limit".
    thinking = [chunk(reasoning="working")] * 8  # 8 × 15 ms, well past 50 ms
    stream = SlowChunks(thinking + [chunk(content="Three sides."), chunk(finish="stop")])
    provider = NativeFixture([stream])
    agent.ai_client = provider
    result = await asyncio.wait_for(agent.execute("answer", stream_callback=AsyncMock()), 2)
    assert result["success"] and "Three sides." in result["result"]
    assert provider.posts == 1 and provider.create_posts == 0


async def test_tool_argument_progress_can_outlast_first_text_budget_without_replay(agent):
    parts = ['{"query":', '"kn', "ow", "le", "dge", '"}']
    tools = SlowChunks(
        [tool_delta(part, first=i == 0) for i, part in enumerate(parts)]
        + [chunk(finish="tool_calls")]
    )
    answer = SlowChunks([chunk(content="Found it."), chunk(finish="stop")], delay=0)
    provider = NativeFixture([tools, answer])
    agent.ai_client = provider
    agent._execute_tool_safe = AsyncMock(return_value={"found": True})
    result = await asyncio.wait_for(agent.execute("recall", stream_callback=AsyncMock()), 1)
    assert result["success"]
    assert provider.posts == 2 and provider.create_posts == 0
    agent._execute_tool_safe.assert_awaited_once_with("recall_memory", {"query": "knowledge"})
    assert all(
        attempt["outcome"] == "completed"
        for attempt in result["usage"]["timings"]["provider_attempts"]
    )


async def test_continuous_text_still_has_total_budget_and_keeps_partial_bytes(agent, monkeypatch):
    monkeypatch.setattr("agents.base.provider_limits", lambda: ProviderLimits(0.05, 0.05, 0.08))
    stream = SlowChunks([chunk(content="x")] * 100)
    provider = NativeFixture([stream])
    agent.ai_client = provider
    emitted = AsyncMock()
    result = await asyncio.wait_for(agent.execute("answer", stream_callback=emitted), 1)
    assert not result["success"] and result["provider_timeout_phase"] == "total"
    assert emitted.await_count > 0
    assert all(call.args[0] == "x" for call in emitted.await_args_list)
    assert provider.posts == 1 and provider.create_posts == 0
    assert stream.closed.is_set()


async def test_reasoning_after_visible_prefix_is_bounded_by_the_total_budget(agent):
    stream = SlowChunks([chunk(content="Partial")] + [chunk(reasoning="hidden")] * 100)
    provider = NativeFixture([stream])
    agent.ai_client = provider
    emitted = AsyncMock()
    result = await asyncio.wait_for(agent.execute("answer", stream_callback=emitted), 2)
    assert result["provider_timeout_phase"] == "total"
    assert emitted.await_args_list[0].args == ("Partial",)
    assert provider.posts == 1 and provider.create_posts == 0
    assert stream.closed.is_set()


async def test_user_cancellation_closes_local_stream_without_another_post(agent):
    stream = SlowChunks([chunk(reasoning="hidden")] * 100)
    provider = NativeFixture([stream])
    agent.ai_client = provider
    running = asyncio.create_task(agent.execute("answer", stream_callback=AsyncMock()))
    for _ in range(100):
        if provider.posts:
            break
        await asyncio.sleep(0.002)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert stream.closed.is_set()
    assert provider.posts == 1 and provider.create_posts == 0
    assert agent._execution_timings["provider_attempts"][0]["outcome"] == "cancelled"
    assert not agent._execution_lock.locked()


async def test_cancelled_wrapper_construction_cannot_start_a_late_post(agent):
    constructing, release, returned = threading.Event(), threading.Event(), threading.Event()

    class DelayedWrapper(NativeFixture):
        def stream(self, **kwargs):
            constructing.set()
            assert release.wait(1)
            wrapper = super().stream(**kwargs)
            returned.set()
            return wrapper

    provider = DelayedWrapper([SlowChunks([chunk(content="Late"), chunk(finish="stop")])])
    agent.ai_client = provider
    running = asyncio.create_task(agent.execute("answer", stream_callback=AsyncMock()))
    try:
        assert await asyncio.to_thread(constructing.wait, 1)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    finally:
        release.set()
    assert await asyncio.to_thread(returned.wait, 1)
    await asyncio.sleep(0.02)
    assert provider.posts == 0 and provider.create_posts == 0


async def test_buffered_provider_is_used_once_without_native_stream_support(agent):
    class Buffered(BaseLLMProvider):
        provider_name = "local-buffered"
        calls = 0

        def create(self, **kwargs):
            self.calls += 1
            return LLMResponse(
                [ContentBlock(type="text", text="Buffered answer")], "end_turn", "local"
            )

    provider = Buffered()
    agent.ai_client = provider
    result = await agent.execute("answer", stream_callback=AsyncMock())
    assert result["success"] and provider.calls == 1


async def test_blocking_timeout_does_not_start_tawbah_provider_retry(agent, monkeypatch):
    monkeypatch.setattr("agents.base.provider_limits", lambda: ProviderLimits(0.05, 0.05, 0.03))
    completed = threading.Event()

    class Blocking(BaseLLMProvider):
        provider_name = "fixture"
        calls = 0

        def create(self, **kwargs):
            self.calls += 1
            time.sleep(0.08)
            completed.set()
            return LLMResponse([ContentBlock(type="text", text="Late answer")], "end_turn", "local")

    provider = Blocking()
    agent.ai_client = provider
    result = await agent.execute("answer")
    assert result["error_code"] == "provider_timeout" and provider.calls == 1
    assert result["usage"].get("calls", []) == []
    assert await asyncio.to_thread(completed.wait, 1)
    assert agent._llm_calls == []  # Late upstream completion cannot mutate the receipt.


@pytest.mark.parametrize("value, expected", [("nan", 60), ("-1", 1), ("999999", 180)])
def test_progress_budget_configuration_is_finite_and_bounded(monkeypatch, value, expected):
    monkeypatch.setenv("MIZAN_LLM_FIRST_PROGRESS_SECONDS", value)
    assert provider_limits().first_progress == expected
