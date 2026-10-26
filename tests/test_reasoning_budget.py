"""Reasoning-only receipts must not become warning-only successful chat replies."""

import asyncio
import copy
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2
import pytest

from agents.specialized import create_agent
from core.qalb_processor import QalbState
from providers import BaseLLMProvider, ContentBlock, LLMResponse, OpenAICompatibleProvider

MODEL = "nvidia/nemotron-3.5-super-vl:free"
PRIVATE_REASONING = "private fixture reasoning, never answer content"


def receipt(text="", finish="end_turn", usage=None):
    return LLMResponse(
        [ContentBlock(type="text", text=text)] if text else [], finish, MODEL, usage or {}
    )


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def agent(monkeypatch, tmp_path, mock_wali, mock_izn):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIZAN_CHAT_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    result = create_agent("general", name="Budget fixture", wali=mock_wali, izn=mock_izn)
    result.ai_model = MODEL
    return result


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "provider_name, model, expected",
    [
        ("openrouter", MODEL, {"max_tokens": 1024}),
        ("openrouter", "nvidia/nemotron-3.5-super-vl", {"max_tokens": 1024}),
        ("openrouter", "unverified/reasoning-model", None),
        ("openai", MODEL, None),
    ],
)
def test_real_sdk_caps_only_verified_model_and_keeps_reasoning_out_of_answer(
    streaming, provider_name, model, expected
):
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        # OpenAI's own API takes max_completion_tokens; OpenRouter keeps max_tokens.
        token_field = "max_completion_tokens" if provider_name == "openai" else "max_tokens"
        assert body[token_field] == 4096
        assert body.get("reasoning") == expected
        usage = {
            "prompt_tokens": 19000,
            "completion_tokens": 2048,
            "completion_tokens_details": {"reasoning_tokens": 2048},
        }
        shared = {"id": "fixture", "created": 1, "model": model}
        if streaming:
            events = [
                {
                    **shared,
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"reasoning": PRIVATE_REASONING},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    **shared,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
                    "usage": usage,
                },
            ]
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="".join(f"data: {json.dumps(event)}\n\n" for event in events)
                + "data: [DONE]\n\n",
            )
        return httpx2.Response(
            200,
            json={
                **shared,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning": PRIVATE_REASONING,
                        },
                        "finish_reason": "length",
                    }
                ],
                "usage": usage,
            },
        )

    provider = OpenAICompatibleProvider(api_key="fixture-only", provider_name=provider_name)
    original = provider._client
    provider._client = original.with_options(
        http_client=httpx2.Client(transport=httpx2.MockTransport(respond), trust_env=False)
    )
    original.close()
    try:
        if streaming:
            with provider.stream(model, 4096, "system", []) as stream:
                assert list(stream.text_stream) == []
                result = stream.get_final_response()
        else:
            result = provider.create(model, 4096, "system", [])
    finally:
        provider._client.close()
    assert len(seen) == 1
    assert result.content == []
    assert result.stop_reason == "max_tokens"
    assert result.usage["output"] == 2048
    assert result.usage["reasoning_tokens"] == 2048
    assert result.usage["visible_output_tokens"] == 0
    assert result.usage["reasoning_observed"] is True
    assert PRIVATE_REASONING not in repr(result)


@pytest.mark.parametrize("streaming", [False, True])
async def test_agent_sdk_request_reserves_answer_budget_and_delivers_answer(agent, streaming):
    """A local protocol fixture checks the entire request/receipt path, not model quality."""
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        # Unlisted model: fallback output cap (8192) is the default budget.
        assert body["max_tokens"] == 8192
        assert body["reasoning"] == {"max_tokens": 1024}
        shared = {"id": "fixture", "created": 1, "model": MODEL}
        usage = {
            "prompt_tokens": 19000,
            "completion_tokens": 1028,
            "completion_tokens_details": {"reasoning_tokens": 1024},
        }
        if streaming:
            events = [
                {
                    **shared,
                    "object": "chat.completion.chunk",
                    "choices": [
                        {"index": 0, "delta": {"content": "Salaam, 42."}, "finish_reason": "stop"}
                    ],
                    "usage": usage,
                }
            ]
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="".join(f"data: {json.dumps(event)}\n\n" for event in events)
                + "data: [DONE]\n\n",
            )
        return httpx2.Response(
            200,
            json={
                **shared,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Salaam, 42."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            },
        )

    provider = OpenAICompatibleProvider(api_key="fixture-only", provider_name="openrouter")
    original = provider._client
    provider._client = original.with_options(
        http_client=httpx2.Client(transport=httpx2.MockTransport(respond), trust_env=False)
    )
    original.close()
    agent.ai_client = provider
    try:
        result = await agent.execute(
            "6 times 7", stream_callback=AsyncMock() if streaming else None
        )
    finally:
        provider._client.close()
    assert len(requests) == 1
    assert result["success"]
    assert result["result"] == "Salaam, 42."
    assert result["completion_status"] == "unverified_answer"
    assert result["answer_delivered"] is True and result["task_verified"] is False


@pytest.mark.parametrize(
    "max_tokens, expected",
    [(256, {"enabled": False}), (2048, {"max_tokens": 512}), (16384, {"max_tokens": 1024})],
)
def test_reasoning_cap_reserves_visible_budget_at_operator_limits(max_tokens, expected):
    from providers import _answer_reasoning_options

    assert _answer_reasoning_options("openrouter", MODEL, max_tokens) == {
        "extra_body": {"reasoning": expected}
    }


def test_truncated_structured_tool_call_is_not_promoted_to_executable_receipt():
    # Complete JSON is insufficient if the provider says its turn was cut off.
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(id="save", function=SimpleNamespace(name="save", arguments="{}"))
        ],
    )
    response = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="length")])
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.provider_name = "openrouter"
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))
    )
    with pytest.raises(ValueError, match="incomplete tool call"):
        provider.create(MODEL, 4096, "system", [])


@pytest.mark.parametrize("streaming", [False, True])
async def test_empty_length_receipt_does_not_continue_or_capture(agent, monkeypatch, streaming):
    agent.ai_client = ScriptedProvider(
        [receipt(finish="max_tokens", usage={"output": 2048, "reasoning_tokens": 2048})] * 3
    )
    reflection = AsyncMock()
    monkeypatch.setattr(agent, "_tafakkur", reflection)
    # Even a misleading generic recovery plan cannot replay this completed,
    # billed provider turn as a whole new task.
    monkeypatch.setattr(agent, "_plan_error_correction", lambda *args: {"retryable": True})
    chunks = AsyncMock() if streaming else None
    result = await agent.execute("Say salaam", stream_callback=chunks)
    assert len(agent.ai_client.requests) == 1
    assert result["success"] is False
    assert result["completion_status"] == "incomplete"
    assert result["error_code"] == "output_budget_exhausted"
    assert "before producing answer text" in result["error"]
    assert not result["answer_delivered"] and not result["capture_eligible"]
    assert not result["task_verified"]
    assert agent.success_count == 0
    assert reflection.await_args.args[2] is False
    assert result["usage"]["timings"]["provider_attempt_count"] == 1
    if chunks:
        chunks.assert_not_awaited()


@pytest.mark.parametrize("streaming", [False, True])
async def test_visible_continuation_is_bounded_text_only_and_unreviewable_when_cut(
    agent, streaming
):
    agent.ai_client = ScriptedProvider([receipt(f"part {i} ", "max_tokens") for i in range(5)])
    result = await agent.execute(
        "Write a long answer", stream_callback=AsyncMock() if streaming else None
    )
    assert result["success"]
    assert result["completion_status"] == "incomplete"
    assert not result["capture_eligible"] and not result["task_verified"]
    assert agent.success_count == 0
    assert len(agent.ai_client.requests) == 3
    assert all(not request["tools"] for request in agent.ai_client.requests[1:])
    assert "part 0 part 1 part 2" in result["result"]
    assert "length limit" in result["result"]


async def test_continuation_cannot_repeat_completed_action_even_if_model_requests_it(
    agent, monkeypatch
):
    action = LLMResponse(
        [ContentBlock(type="tool_use", id="save", name="workspace_write", input={})],
        "tool_use",
        MODEL,
    )
    agent.ai_client = ScriptedProvider(
        [action, receipt("Saved; explanation ", "max_tokens"), action]
    )
    tool = AsyncMock(return_value={"saved": True})
    monkeypatch.setattr(agent, "_execute_tool_safe", tool)
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{"name": "workspace_write", "description": "Save it once", "input_schema": {}}],
    )
    result = await agent.execute("Save it once")
    assert not result["success"]
    assert "text-only continuation" in result["error"]
    assert len(agent.ai_client.requests) == 3
    assert not agent.ai_client.requests[-1]["tools"]
    tool.assert_awaited_once()


async def test_reasoning_only_tool_summary_is_not_retried_or_treated_as_answer(agent, monkeypatch):
    action = LLMResponse(
        [ContentBlock(type="tool_use", id="read", name="read_file", input={})], "tool_use", MODEL
    )
    agent.ai_client = ScriptedProvider([action, receipt(), receipt(finish="max_tokens")])
    tool = AsyncMock(return_value={"content": "fixture result"})
    monkeypatch.setattr(agent, "_execute_tool_safe", tool)
    result = await agent.execute("Read once and summarize")
    assert not result["success"]
    assert result["error_code"] == "output_budget_exhausted"
    assert len(agent.ai_client.requests) == 3  # action, empty end_turn, one summary attempt
    assert not result["capture_eligible"]
    tool.assert_awaited_once()


@pytest.mark.parametrize("qalb_budget", [2048, 3000, 4096])
async def test_qalb_tone_does_not_control_output_budget(agent, monkeypatch, qalb_budget):
    agent.ai_client = ScriptedProvider([receipt("Salaam")])
    agent.config["temperature"] = 0.2
    monkeypatch.setattr(
        agent.qalb_processor,
        "process",
        lambda **kwargs: SimpleNamespace(
            max_tokens=qalb_budget, temperature=0.3, state=QalbState.QABD
        ),
    )
    result = await agent.execute("hello")
    assert result["success"]
    assert agent.ai_client.requests[0]["max_tokens"] == 8192
    assert agent.ai_client.requests[0]["temperature"] == 0.2
    assert result["metric_provenance"]["accuracy"] == "not_measured"


@pytest.mark.parametrize(
    "configured, expected",
    # Bounded by the model's output cap (8192 for this unlisted model).
    [(128, 256), (4096, 4096), (999999, 8192), ("bad", 8192), (True, 8192)],
)
def test_operator_budget_is_explicit_and_bounded(agent, configured, expected):
    agent.config["max_output_tokens"] = configured
    assert agent._output_token_budget() == expected


def test_environment_budget_is_used_unless_agent_has_explicit_override(agent, monkeypatch):
    monkeypatch.setenv("MIZAN_CHAT_MAX_OUTPUT_TOKENS", "6144")
    assert agent._output_token_budget() == 6144
    agent.config["max_output_tokens"] = 3072
    assert agent._output_token_budget() == 3072


async def test_queue_wait_and_failed_stream_attempt_are_measured_without_unlocking(agent):
    entered, release = threading.Event(), threading.Event()
    provider = ScriptedProvider([receipt("first"), receipt("second")])
    original_create = provider.create

    def blocking_create(**kwargs):
        if not provider.requests:
            entered.set()
            assert release.wait(2), "fixture release deadline exceeded"
        return original_create(**kwargs)

    provider.create = blocking_create
    agent.ai_client = provider
    first = asyncio.create_task(agent.execute("first"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        second = asyncio.create_task(agent.execute("second"))
        await asyncio.sleep(0.03)
        assert not second.done()
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
    finally:
        release.set()
        if not first.done():
            first.cancel()
    timing = results[1]["usage"]["timings"]
    assert timing["queue_wait_ms"] >= 20
    assert timing["provider_attempt_count"] == 1
    assert timing["total_ms"] >= timing["queue_wait_ms"] + timing["provider_ms"]
    assert timing["execution_ms"] == pytest.approx(
        timing["provider_ms"] + timing["tool_ms"] + timing["other_execution_ms"], abs=0.2
    )

    # A failed streaming attempt previously disappeared from provider timings.
    class StreamFailure(ScriptedProvider):
        def stream(self, **kwargs):
            raise RuntimeError("fixture unsupported streaming")

    agent.ai_client = StreamFailure([receipt("fallback answer")])
    result = await agent.execute("hello", stream_callback=AsyncMock())
    assert not result["success"]
    attempts = result["usage"]["timings"]["provider_attempts"]
    assert [(attempt["mode"], attempt["outcome"]) for attempt in attempts] == [
        ("stream", "failed"),
    ]
    assert result["usage"].get("calls", []) == []  # Ambiguous failures are not retried.
    assert not agent.ai_client.requests
