"""Provider failures must not end a chat: gateway fallbacks, safe retries, real limits.

Production (2026-10-26): a free OpenRouter model's upstream returned HTTP 502
("Provider returned error") and every such reply failed with agent_failed.
"""

from unittest.mock import MagicMock

import pytest

import agents.base as agent_base
import providers
from agents.specialized import create_agent
from providers import (
    BaseLLMProvider,
    ContentBlock,
    LLMResponse,
    _adapt_openai_request,
    effective_limits,
    openrouter_fallback_models,
    provider_retry_delay,
)
from providers_minimind import MODEL_ID, MiniMindRemoteProvider
from reasoning.context_engine import (
    SMALL_WINDOW_SCALE,
    SUMMARY_HEADER,
    ContextBudget,
    estimate_tokens,
    message_tokens,
)


class StatusError(Exception):
    """Shape of an SDK APIStatusError: an explicit HTTP error response."""

    def __init__(self, status_code, retry_after=None):
        super().__init__(f"Error code: {status_code} - Provider returned error")
        self.status_code = status_code
        self.response = MagicMock(headers={"retry-after": retry_after} if retry_after else {})


@pytest.fixture
def catalog(monkeypatch):
    entries = {
        "nvidia/nemotron-3.5-super-vl:free": {"free": True, "tools": True, "context": 1_000_000},
        "nvidia/nemotron-3.5-lightning:free": {"free": True, "tools": True, "context": 1_000_000},
        "nvidia/nemotron-3-super-120b-a12b:free": {"free": True, "tools": True, "context": 262_144},
        "google/gemma-4-31b-it:free": {"free": True, "tools": True, "context": 262_144},
        "acme/no-tools:free": {"free": True, "tools": False, "context": 2_000_000},
        "anthropic/claude-opus-5.5": {"free": False, "tools": True, "context": 1_000_000},
    }
    monkeypatch.setattr(providers, "_OPENROUTER_CATALOG", entries)
    monkeypatch.delenv("MIZAN_OPENROUTER_FALLBACKS", raising=False)
    return entries


def test_free_primary_gets_free_same_vendor_fallbacks(catalog):
    fallbacks = openrouter_fallback_models("nvidia/nemotron-3.5-super-vl:free", True)
    assert fallbacks == [
        "nvidia/nemotron-3.5-lightning:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]
    assert all(catalog[model]["free"] for model in fallbacks)
    # Without tools a larger tool-less free model may serve.
    assert "acme/no-tools:free" in openrouter_fallback_models("google/gemma-4-31b-it:free", False)


def test_paid_primary_and_opt_out_add_no_fallbacks(catalog, monkeypatch):
    assert openrouter_fallback_models("anthropic/claude-opus-5.5", True) == []
    monkeypatch.setenv("MIZAN_OPENROUTER_FALLBACKS", "none")
    assert openrouter_fallback_models("nvidia/nemotron-3.5-super-vl:free", True) == []
    monkeypatch.setenv("MIZAN_OPENROUTER_FALLBACKS", "a/b, c/d ,a/b")
    assert openrouter_fallback_models("x/y", True) == ["a/b", "c/d"]


def test_openrouter_request_carries_models_and_keeps_reasoning(catalog):
    kwargs = _adapt_openai_request(
        "openrouter",
        {
            "model": "nvidia/nemotron-3.5-super-vl:free",
            "max_tokens": 4096,
            "tools": [{"type": "function"}],
            "extra_body": {"reasoning": {"max_tokens": 1024}},
        },
    )
    assert kwargs["extra_body"]["reasoning"] == {"max_tokens": 1024}
    assert kwargs["extra_body"]["models"][0] == "nvidia/nemotron-3.5-super-vl:free"
    assert len(kwargs["extra_body"]["models"]) == 3
    # Other providers never receive the OpenRouter extension.
    plain = _adapt_openai_request("ollama", {"model": "qwen3.8", "max_tokens": 10})
    assert "extra_body" not in plain


def test_retry_policy_only_covers_explicit_rejections():
    assert provider_retry_delay(StatusError(502), 0) == pytest.approx(1.5)
    assert provider_retry_delay(StatusError(503), 1) == pytest.approx(3.0)
    assert provider_retry_delay(StatusError(429, "7"), 0) == pytest.approx(7.0)
    assert provider_retry_delay(StatusError(429, "999"), 0) == pytest.approx(20.0)
    for ambiguous in (StatusError(504), StatusError(400), TimeoutError(), ConnectionError()):
        assert provider_retry_delay(ambiguous, 0) is None


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.calls.append({"max_tokens": max_tokens, "messages": list(messages)})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(content=[ContentBlock(type="text", text=item)], stop_reason="end_turn")


def make_agent(provider):
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Resilient", wali=MagicMock(), izn=izn)
    agent.ai_model = "fake-model"
    agent.ai_client = provider
    return agent


async def collect(agen):
    return [chunk async for chunk in agen]


async def test_agent_retries_an_explicit_502_and_answers(monkeypatch):
    monkeypatch.setattr(
        agent_base,
        "provider_retry_delay",
        lambda exc, attempt: 0.0 if getattr(exc, "status_code", 0) == 502 else None,
    )
    provider = ScriptedProvider([StatusError(502), "4"])
    agent = make_agent(provider)
    chunks = await collect(
        agent._agentic_loop("sys", [{"role": "user", "content": "2+2?"}], [], False, "2+2?")
    )
    assert "".join(chunks) == "4"
    assert len(provider.calls) == 2


async def test_agent_gives_up_after_bounded_retries(monkeypatch):
    monkeypatch.setattr(agent_base, "provider_retry_delay", lambda exc, attempt: 0.0)
    provider = ScriptedProvider([StatusError(502)] * 5)
    agent = make_agent(provider)
    with pytest.raises(StatusError):
        await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], False, "hi")
        )
    assert len(provider.calls) == 1 + agent_base._MAX_PROVIDER_RETRIES


async def test_agent_never_replays_an_ambiguous_failure():
    provider = ScriptedProvider([TimeoutError("read timed out"), "late"])
    agent = make_agent(provider)
    with pytest.raises(TimeoutError):
        await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], False, "hi")
        )
    assert len(provider.calls) == 1


def test_failed_run_reports_provider_unavailable():
    from api.main import chat_failure_payload

    payload = chat_failure_payload({"error_code": "provider_unavailable"})
    assert payload["code"] == "provider_unavailable"
    assert "retries" in payload["message"]


def test_declared_provider_window_overrides_model_table():
    minimind = MiniMindRemoteProvider(endpoint_id="abcdefghijklmn", api_key="test")
    assert effective_limits(minimind, MODEL_ID) == (2048, 256)
    # A mock or undeclared provider keeps the model table's values.
    assert effective_limits(MagicMock(), "claude-opus-5-5") == (1_000_000, 128_000)


def test_small_window_budget_leaves_room_for_prompt_and_output():
    budget = ContextBudget.for_window(2048, reserved_tokens=256 + 512)
    assert budget.history_tokens * SMALL_WINDOW_SCALE <= 2048 - 768 - 64
    assert budget.summary_tokens < budget.history_tokens
    large = ContextBudget.for_window(1_000_000, reserved_tokens=16_000 + 250_000)
    assert large.history_tokens == 150_000


class SmallWindowProvider(ScriptedProvider):
    provider_name = "small"
    context_window = 2048
    max_output_tokens = 256


def test_request_is_fitted_to_a_2048_token_window():
    agent = make_agent(SmallWindowProvider([]))
    turn = "details " * 60
    messages = [{"role": "user", "content": f"{SUMMARY_HEADER}\nolder work\n[END]"}]
    for index in range(40):
        role = "user" if index % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"turn {index}: {turn}"})
    current = f"{agent_base.CURRENT_REQUEST_START}\nKya hua?\n{agent_base.CURRENT_REQUEST_END}"
    messages.append({"role": "user", "content": current})
    max_tokens = agent._fit_request_to_window("system prompt " * 20, messages, [], 256)

    assert messages[0]["content"].startswith(SUMMARY_HEADER)
    assert messages[-1]["content"] == current
    assert "turn 39" in messages[-2]["content"]
    used = estimate_tokens("system prompt " * 20) + sum(message_tokens(m) for m in messages)
    assert used * SMALL_WINDOW_SCALE + max_tokens <= 2048
    assert 64 <= max_tokens <= 256


async def test_small_window_agent_sends_a_fitting_request():
    provider = SmallWindowProvider(["theek hai"])
    agent = make_agent(provider)
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}: " + "x " * 300}
        for i in range(60)
    ]
    messages = agent._build_messages("Kya hua?", {"history": history})
    chunks = await collect(agent._agentic_loop("short system", messages, [], False, "Kya hua?"))
    assert "".join(chunks) == "theek hai"
    sent = provider.calls[0]
    used = estimate_tokens("short system") + sum(message_tokens(m) for m in sent["messages"])
    assert used * SMALL_WINDOW_SCALE + sent["max_tokens"] <= 2048
    assert sent["max_tokens"] <= 256


async def test_streaming_run_also_recovers_from_an_explicit_502(monkeypatch):
    monkeypatch.setattr(
        agent_base,
        "provider_retry_delay",
        lambda exc, attempt: 0.0 if getattr(exc, "status_code", 0) == 502 else None,
    )
    provider = ScriptedProvider([StatusError(502), "streamed answer"])
    agent = make_agent(provider)
    chunks = await collect(
        agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], True, "hi")
    )
    assert "".join(chunks) == "streamed answer"
    assert len(provider.calls) == 2
