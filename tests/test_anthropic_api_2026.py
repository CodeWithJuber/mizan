"""Claude requests follow API version 2026-10-21 and current model behaviour."""

import json

import anthropic
import httpx2
import pytest

import providers
from providers import (
    AnthropicProvider,
    ProviderRefusal,
    _anthropic_messages,
    assistant_turn_content,
    configured_provider_name,
    model_limits,
    normalize_model_for_provider,
    record_model_limits,
)


def message(content, stop_reason="end_turn", **extra):
    return {
        "id": "msg-fixture",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 11, "output_tokens": 5, "cache_read_input_tokens": 9},
        **extra,
    }


def provider_with(handler):
    provider = AnthropicProvider(api_key="test-placeholder")
    original = provider._client
    provider._client = original.with_options(
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
    )
    original.close()
    return provider


def test_opus_request_has_effort_fallbacks_cache_and_no_sampling(monkeypatch):
    monkeypatch.delenv("MIZAN_CHAT_EFFORT", raising=False)
    seen = []

    def respond(request):
        seen.append((request, json.loads(request.content)))
        return httpx2.Response(
            200,
            json=message(
                [
                    {"type": "thinking", "thinking": "", "signature": "sig-1"},
                    {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"p": 1}},
                ],
                stop_reason="tool_use",
            ),
        )

    provider = provider_with(respond)
    response = provider.create(
        "claude-opus-5-5",
        1024,
        "system",
        [{"role": "user", "content": "hi"}],
        temperature=0.4,
    )
    request, body = seen[0]
    assert "temperature" not in body
    assert body["output_config"] == {"effort": "high"}
    assert body["fallbacks"] == "default"
    assert body["cache_control"] == {"type": "ephemeral"}
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    assert "compact-2026-01-12" in request.headers["anthropic-beta"]
    assert body["context_management"]["edits"][0]["type"] == "compact_20260112"
    assert body["context_management"]["edits"][0]["trigger"]["value"] == 150_000
    # Thinking blocks are kept for the next call of the same tool loop.
    assert assistant_turn_content(response)[0] == {
        "type": "thinking",
        "thinking": "",
        "signature": "sig-1",
    }
    assert response.content[0].type == "tool_use"
    assert response.usage["cache_read"] == 9


def test_older_claude_models_get_no_effort_or_fallbacks():
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=message([{"type": "text", "text": "ok"}]))

    provider_with(respond).create("claude-sonnet-4-5", 64, "s", [{"role": "user", "content": "x"}])
    assert "output_config" not in seen[0]
    assert "fallbacks" not in seen[0]


def test_refusal_is_a_typed_error():
    def respond(request):
        return httpx2.Response(
            200,
            json=message(
                [],
                stop_reason="refusal",
                stop_details={"type": "refusal", "category": "cyber", "explanation": None},
            ),
        )

    with pytest.raises(ProviderRefusal) as error:
        provider_with(respond).create(
            "claude-opus-5-5", 64, "s", [{"role": "user", "content": "x"}]
        )
    assert error.value.category == "cyber"


def test_thinking_binding_rejection_is_retried_once_without_thinking():
    bodies = []

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "messages.1.content.0: Invalid `signature` in `thinking` block. "
                        "The block is bound to a different conversation.",
                    },
                },
            )
        return httpx2.Response(200, json=message([{"type": "text", "text": "done"}]))

    history = [
        {"role": "user", "content": "a"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "old"},
                {"type": "text", "text": "b"},
            ],
        },
        {"role": "user", "content": "c"},
    ]
    response = provider_with(respond).create("claude-opus-5-5", 64, "s", history)
    assert response.content[0].text == "done"
    assert len(bodies) == 2
    assert bodies[1]["messages"][1]["content"] == [{"type": "text", "text": "b"}]


def test_other_bad_requests_are_not_replayed():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx2.Response(
            400,
            json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}},
        )

    with pytest.raises(anthropic.BadRequestError):
        provider_with(respond).create(
            "claude-opus-5-5", 64, "s", [{"role": "user", "content": "x"}]
        )
    assert len(calls) == 1


def test_history_normalization_drops_empty_turns_and_system_entries():
    normalized = _anthropic_messages(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": [{"type": "text", "text": "  "}]},
            {"role": "system", "content": "summary of earlier turns"},
            {"role": "user", "content": "next"},
        ]
    )
    assert [m["role"] for m in normalized] == ["user", "user", "user"]
    assert "summary of earlier turns" in normalized[1]["content"]


def test_openrouter_claude_ids_use_dotted_versions():
    assert (
        normalize_model_for_provider("claude-opus-5-5", "openrouter") == "anthropic/claude-opus-5.5"
    )
    assert (
        normalize_model_for_provider("claude-sonnet-5", "openrouter") == "anthropic/claude-sonnet-5"
    )
    assert normalize_model_for_provider("claude-opus-5-5", "anthropic") == "claude-opus-5-5"


def test_model_limits_static_family_and_live(monkeypatch):
    monkeypatch.setattr(providers, "_MODEL_LIMITS", {})
    assert model_limits("claude-opus-5-5") == (1_000_000, 128_000)
    assert model_limits("claude-haiku-4-5-20251001") == (200_000, 64_000)
    assert model_limits("unknown/model") == (32_768, 8_192)
    record_model_limits("unknown/model", 262_144, 16_384)
    assert model_limits("unknown/model") == (262_144, 16_384)


@pytest.mark.parametrize(
    "value, expected", [("", None), ("auto", None), ("AUTO", None), ("openrouter", "openrouter")]
)
def test_llm_provider_auto_means_detect(monkeypatch, value, expected):
    monkeypatch.setenv("LLM_PROVIDER", value)
    assert configured_provider_name() == expected


def test_openai_direct_uses_completion_token_field_and_default_sampling():
    from providers import _adapt_openai_request

    adapted = _adapt_openai_request(
        "openai", {"model": "gpt-6.1-sol", "max_tokens": 900, "temperature": 0.5}
    )
    assert adapted == {"model": "gpt-6.1-sol", "max_completion_tokens": 900}
    # OpenRouter and Ollama keep the widely supported field and sampling value.
    kept = _adapt_openai_request(
        "openrouter", {"model": "x", "max_tokens": 900, "temperature": 0.5}
    )
    assert kept == {"model": "x", "max_tokens": 900, "temperature": 0.5}
