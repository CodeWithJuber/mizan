"""Real SDK transports with bounded waits and explicit stream completion receipts."""

import json
from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pytest

from providers import AnthropicProvider, OllamaProvider, OpenAICompatibleProvider
from providers_ruh_remote import RuhRemoteProvider

TOOL = {
    "name": "read_file",
    "description": "Read a file",
    "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
}


@pytest.fixture(autouse=True)
def isolated_budget(monkeypatch):
    monkeypatch.delenv("MIZAN_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MIZAN_LLM_MAX_RETRIES", raising=False)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")


@pytest.fixture
def provider_factory():
    clients = []

    def create(kind, handler=None):
        if kind == "anthropic":
            provider = AnthropicProvider(api_key="test-placeholder")
        elif kind == "ollama":
            provider = OllamaProvider()
        else:
            provider = OpenAICompatibleProvider(api_key="test-placeholder")
        original = provider._client
        if handler is not None:
            provider._client = original.with_options(
                http_client=httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
            )
            original.close()
        clients.append(provider._client)
        return provider

    yield create
    for client in clients:
        client.close()


@pytest.mark.parametrize("kind", ["anthropic", "openai", "ollama"])
@pytest.mark.parametrize(
    "seconds, retries, expected_seconds, expected_retries",
    [
        (None, None, 60, 0),
        ("25.5", "1", 25.5, 0),
        ("99999", "99999", 180, 0),
        ("-5", "-2", 1, 0),
        ("nan", "invalid", 60, 0),
        ("inf", "2.5", 60, 0),
    ],
)
def test_sdk_budgets_are_explicit_bounded_and_finite(
    kind, seconds, retries, expected_seconds, expected_retries, monkeypatch, provider_factory
):
    if seconds is not None:
        monkeypatch.setenv("MIZAN_LLM_TIMEOUT_SECONDS", seconds)
    if retries is not None:
        monkeypatch.setenv("MIZAN_LLM_MAX_RETRIES", retries)
    client = provider_factory(kind)._client
    assert client.timeout.read == expected_seconds
    assert client.timeout.write == expected_seconds
    assert client.timeout.pool == expected_seconds
    assert client.timeout.connect == min(expected_seconds, 5)
    assert client.max_retries == expected_retries


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
@pytest.mark.parametrize("streaming", [False, True])
def test_idle_timeout_propagates_without_hidden_sdk_retry(kind, streaming, provider_factory):
    attempts = []

    def respond(request):
        attempts.append(request)
        assert request.extensions["timeout"]["read"] == 60
        raise httpx2.ReadTimeout("upstream idle", request=request)

    provider = provider_factory(kind, respond)
    with pytest.raises((anthropic.APITimeoutError, openai.APITimeoutError)):
        if streaming:
            with provider.stream("test-model", 32, "system", []) as stream:
                list(stream.text_stream)
        else:
            provider.create("test-model", 32, "system", [])
    assert len(attempts) == 1


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
def test_legacy_sdk_retry_setting_cannot_replay_generation_posts(
    kind, monkeypatch, provider_factory
):
    monkeypatch.setenv("MIZAN_LLM_MAX_RETRIES", "1")
    attempts = []

    def respond(request):
        attempts.append(request)
        return httpx2.Response(
            503,
            headers={"retry-after-ms": "1"},
            json={"error": {"type": "unavailable", "message": "temporary failure"}},
        )

    provider = provider_factory(kind, respond)
    with pytest.raises((anthropic.APIStatusError, openai.APIStatusError)):
        provider.create("test-model", 32, "system", [])
    assert len(attempts) == 1


def openai_event(content=None, calls=None, finish=None, usage=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if calls is not None:
        delta["tool_calls"] = calls
    return {
        "id": "test-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "observed-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        "usage": usage,
    }


def sse_body(events, *, openai_protocol=False):
    body = "".join(
        ("" if openai_protocol else f"event: {event['type']}\n")
        + "data: "
        + json.dumps(event)
        + "\n\n"
        for event in events
    )
    return body + ("data: [DONE]\n\n" if openai_protocol else "")


def anthropic_start():
    return {
        "type": "message_start",
        "message": {
            "id": "test-message",
            "type": "message",
            "role": "assistant",
            "model": "observed-model",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 7, "output_tokens": 0},
        },
    }


def test_openai_stream_keeps_tool_arguments_and_final_usage_with_budget(provider_factory):
    events = [
        openai_event(content="Reading."),
        openai_event(
            calls=[
                {
                    "index": 0,
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":'},
                }
            ]
        ),
        openai_event(
            calls=[{"index": 0, "function": {"arguments": '"src/main.py"}'}}],
            finish="tool_calls",
        ),
        {
            **openai_event(),
            "choices": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        },
    ]

    def respond(request):
        assert request.extensions["timeout"]["read"] == 60
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["tools"][0]["function"]["parameters"] == TOOL["input_schema"]
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=sse_body(events, openai_protocol=True),
        )

    with provider_factory("openai", respond).stream(
        "test-model", 32, "system", [], [TOOL]
    ) as stream:
        assert list(stream.text_stream) == ["Reading."]
        final = stream.get_final_response()
    assert final.stop_reason == "tool_use"
    assert final.content[1].input == {"path": "src/main.py"}
    assert final.model == "observed-model"
    assert final.usage["input"] == 7 and final.usage["output"] == 3


def test_anthropic_stream_keeps_tools_and_final_usage_with_budget(provider_factory):
    events = [
        anthropic_start(),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Reading."},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "call-1", "name": "read_file", "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"path":"src/main.py"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 3},
        },
        {"type": "message_stop"},
    ]

    def respond(request):
        assert request.extensions["timeout"]["read"] == 60
        body = json.loads(request.content)
        # Streamed tool input shows progress; API 2026-10-21 has no sampling params.
        assert body["tools"] == [{**TOOL, "eager_input_streaming": True}]
        assert "temperature" not in body
        assert body["cache_control"] == {"type": "ephemeral"}
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, text=sse_body(events)
        )

    with provider_factory("anthropic", respond).stream(
        "test-model", 32, "system", [], [TOOL]
    ) as stream:
        assert list(stream.text_stream) == ["Reading."]
        final = stream.get_final_response()
    assert final.stop_reason == "tool_use"
    assert final.content[1].input == {"path": "src/main.py"}
    assert final.model == "observed-model"
    assert final.usage == {"input": 7, "output": 3}


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
@pytest.mark.parametrize("partial", [False, True])
def test_stream_without_finish_receipt_fails_even_after_visible_text(
    kind, partial, provider_factory
):
    events = []
    if partial and kind == "openai":
        events = [openai_event(content="Partial")]
    elif partial:
        events = [
            anthropic_start(),
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Partial"},
            },
        ]

    def respond(request):
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=sse_body(events, openai_protocol=kind == "openai"),
        )

    visible = []
    with provider_factory(kind, respond).stream("test-model", 32, "system", []) as stream:
        with pytest.raises(RuntimeError, match="completion record"):
            visible.extend(stream.text_stream)
            stream.get_final_response()
    assert visible == (["Partial"] if partial else [])


def test_custom_openai_error_chunk_is_not_silently_skipped():
    from providers import _OpenAIStreamWrapper

    stream = _OpenAIStreamWrapper(None, "test-model", 32, [])
    stream._stream = [SimpleNamespace(error={"message": "upstream failed"}, choices=[])]
    with pytest.raises(RuntimeError, match="upstream error"):
        list(stream.text_stream)
    with pytest.raises(RuntimeError, match="no completed response"):
        stream.get_final_response()


@pytest.mark.parametrize("arguments", ["{broken", "[]", "null", '"text"', "42", None])
def test_nonstream_tool_arguments_are_never_replaced_with_invented_defaults(
    arguments, provider_factory
):
    def respond(request):
        return httpx2.Response(
            200,
            json={
                "id": "test-tool-response",
                "object": "chat.completion",
                "created": 1,
                "model": "observed-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "read_file", "arguments": arguments},
                                }
                            ],
                        },
                    }
                ],
            },
        )

    provider = provider_factory("openai", respond)
    with pytest.raises(ValueError, match="tool arguments"):
        provider.create("test-model", 32, "system", [], [TOOL])


@pytest.mark.parametrize("finish", [None, "unknown", "content_filter"])
def test_ruh_remote_does_not_invent_success_without_valid_finish(finish):
    provider = RuhRemoteProvider("test-endpoint", "test-placeholder")
    response = provider._parse_output(
        {"output": {"choices": [{"message": {"content": "partial"}, "finish_reason": finish}]}}
    )
    assert response.stop_reason == "incomplete"
