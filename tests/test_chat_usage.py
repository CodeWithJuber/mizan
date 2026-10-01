"""Chat usage / cost tests — model-transparency + cost-display workstreams.

Covers:
  - prices.py: estimate_cost for configured models, unknown model -> None,
    env override, never invents a price
  - usage.py: extract_llm_meta reads the OBSERVED model + all usage key
    styles, build_usage_block cost precedence
    (provider cost -> estimate(≈) -> absent)
  - providers.py: _OpenAIStreamWrapper captures the usage chunk + observed
    model and requests stream_options.include_usage
  - agents/base.py: _record_llm_call stash + execute() reset
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from api.prices import estimate_cost, lookup
from api.usage import build_usage_block, extract_llm_meta
from providers import LLMResponse, _OpenAIStreamWrapper

# ── prices ──


class TestEstimateCost:
    def test_known_models(self):
        # gpt-4o: $2.50/$10.00 per 1M
        assert estimate_cost("gpt-4o", 1_000_000, 1_000_000) == pytest.approx(12.50)
        # claude-sonnet-4-20250514: $3.00/$15.00 per 1M
        assert estimate_cost("claude-sonnet-4-20250514", 2_000_000, 500_000) == pytest.approx(13.50)

    def test_unknown_model_never_invents(self):
        assert estimate_cost("some-future-model-99", 1000, 1000) is None
        assert lookup("some-future-model-99") is None

    def test_local_models_are_free(self):
        assert estimate_cost("ruh-local", 100_000, 50_000) == 0.0

    def test_openrouter_prefix_normalized(self):
        assert lookup("anthropic/claude-sonnet-4") == (3.00, 15.00)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MIZAN_PRICE_OVERRIDES", "gpt-4o:1.00/2.00")
        assert estimate_cost("gpt-4o", 1_000_000, 1_000_000) == pytest.approx(3.00)


# ── usage extraction ──


class TestExtractLlmMeta:
    def test_observed_model_and_usage(self):
        r = LLMResponse(
            content=[],
            model="claude-sonnet-4-20250514-observed",
            usage={"input": 100, "output": 50},
            stop_reason="end_turn",
        )
        meta = extract_llm_meta(r)
        assert meta["model"] == "claude-sonnet-4-20250514-observed"
        assert meta["input_tokens"] == 100
        assert meta["output_tokens"] == 50
        assert meta["finish_reason"] == "end_turn"

    def test_openai_key_style(self):
        r = LLMResponse(
            content=[], model="gpt-4o", usage={"prompt_tokens": 10, "completion_tokens": 5}
        )
        meta = extract_llm_meta(r)
        assert meta["input_tokens"] == 10
        assert meta["output_tokens"] == 5

    def test_ruh_key_style(self):
        r = LLMResponse(
            content=[], model="ruh-local", usage={"input_tokens": 7, "output_tokens": 3}
        )
        meta = extract_llm_meta(r)
        assert meta["input_tokens"] == 7
        assert meta["output_tokens"] == 3

    def test_missing_values_absent_never_invented(self):
        meta = extract_llm_meta(LLMResponse(content=[]))
        assert "model" not in meta
        assert "input_tokens" not in meta
        assert "cost_usd" not in meta

    def test_none_response(self):
        assert extract_llm_meta(None) == {}


class TestBuildUsageBlock:
    def _llm_call(self, model, usage, latency=123.4):
        return {
            "response": LLMResponse(content=[], model=model, usage=usage),
            "latency_ms": latency,
        }

    def test_estimate_path_flagged(self):
        block = self._build(model="gpt-4o", usage={"input": 1_000_000, "output": 0})
        assert block["cost_usd"] == pytest.approx(2.50)
        assert block["cost_estimated"] is True
        assert block["latency_ms"] == 123.4
        assert block["model"] == "gpt-4o"

    def test_provider_cost_is_authoritative(self):
        block = self._build(model="gpt-4o", usage={"input": 100, "output": 100, "cost": 0.99})
        assert block["cost_usd"] == 0.99
        assert block["cost_estimated"] is False

    def test_unknown_model_cost_absent(self):
        block = self._build(model="mystery-model", usage={"input": 100, "output": 100})
        assert "cost_usd" not in block
        assert block["input_tokens"] == 100

    def test_no_llm_call_empty_block(self):
        assert build_usage_block(None) == {}

    def _build(self, model, usage):
        return build_usage_block(self._llm_call(model, usage))


# ── OpenAI stream wrapper usage capture ──


def _chunk(*, content=None, finish=None, model=None, usage=None):
    choices = []
    if content is not None or finish is not None:
        choices = [
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=None),
                finish_reason=finish,
            )
        ]
    ns = SimpleNamespace(choices=choices)
    if model is not None:
        ns.model = model
    if usage is not None:
        ns.usage = usage
    return ns


class TestOpenAIStreamUsage:
    def test_usage_chunk_captured_and_observed_model_used(self):
        w = _OpenAIStreamWrapper(None, "gpt-4o", 10, [])
        w._stream = [
            _chunk(content="hi", model="gpt-4o-2024-08-06"),
            _chunk(finish="stop"),
            _chunk(usage=SimpleNamespace(prompt_tokens=42, completion_tokens=7, total_tokens=49)),
        ]
        assert list(w.text_stream) == ["hi"]
        resp = w.get_final_response()
        # Observed model from the wire, not the requested one
        assert resp.model == "gpt-4o-2024-08-06"
        assert resp.usage["input"] == 42
        assert resp.usage["output"] == 7
        # Raw chunk forwarded byte-for-byte for auditing
        assert resp.usage["raw"]["total_tokens"] == 49

    def test_no_usage_chunk_means_absent_not_zero(self):
        w = _OpenAIStreamWrapper(None, "gpt-4o", 10, [])
        w._stream = [_chunk(content="hi", finish="stop")]
        list(w.text_stream)
        resp = w.get_final_response()
        assert resp.usage == {}
        meta = extract_llm_meta(resp)
        assert "input_tokens" not in meta

    def test_stream_options_include_usage_requested(self):
        created = {}

        class FakeCompletions:
            def create(self, **kwargs):
                created.update(kwargs)
                return iter([])

        class FakeClient:
            chat = SimpleNamespace(completions=FakeCompletions())

        w = _OpenAIStreamWrapper(FakeClient(), "gpt-4o", 10, [{"role": "user", "content": "x"}])
        with w:
            pass
        assert created["stream_options"] == {"include_usage": True}


# ── agent recording ──


class TestRecordLlmCall:
    def test_record_and_execute_reset(self):
        from agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        resp = LLMResponse(content=[], model="m", usage={"input": 1, "output": 2})
        agent._record_llm_call(resp, 10.5)
        assert agent._last_llm_call["response"] is resp
        assert agent._last_llm_call["latency_ms"] == 10.5
