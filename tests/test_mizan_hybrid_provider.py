"""Contract tests for the additive base + own-NLP + Mizan provider."""

import json

from mizan_hybrid.config import HybridConfig
from mizan_hybrid.gates import AuditLog, Outcome, SourceRegistry
from mizan_hybrid.nlp import NLPAdvisory, format_advisory
from mizan_hybrid.provider import MizanHybridProvider, create_hybrid_provider_from_env
from providers import BaseLLMProvider, ContentBlock, LLMResponse


class FakeBase(BaseLLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.calls.append(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
                "tools": tools,
                "temperature": temperature,
            }
        )
        return self.responses.pop(0)


def response(text, stop="end_turn", tool=False):
    blocks = []
    if text:
        blocks.append(ContentBlock(type="text", text=text))
    if tool:
        blocks.append(ContentBlock(type="tool_use", id="1", name="lookup", input={}))
    return LLMResponse(content=blocks, stop_reason=stop, model="base-test", usage={"output": 1})


def config(**overrides):
    values = {
        "enabled": True,
        "base_model": "base-test",
        "base_revision": "pinned-test-revision",
        "nlp_advisory": False,
        "target_language": "any",
        "max_gate_retries": 1,
        "retry_max_tokens": 4096,
    }
    values.update(overrides)
    return HybridConfig(**values)


def test_pass_preserves_response_and_adds_research_metadata():
    base = FakeBase([response("Hello")])
    provider = MizanHybridProvider(base, config())
    result = provider.create("base-test", 64, "sys", [{"role": "user", "content": "hi"}])
    assert result.content[0].text == "Hello"
    assert result.usage["mizan"]["gate"]["outcome"] == "PASS"
    assert result.usage["mizan"]["base_revision"] == "pinned-test-revision"
    assert result.usage["mizan"]["semantic_or_religious_certification"] is False
    assert base.calls[0]["temperature"] == 0.0


def test_own_nlp_is_bounded_advisory_not_ground_truth():
    class Analyzer:
        def analyze(self, text):
            assert text == "knowledge"
            return NLPAdvisory(
                status="signals",
                roots=({"root": "ع ل م", "meaning": "knowledge"},),
                key_terms=("knowledge",),
            )

    base = FakeBase([response("Hello")])
    provider = MizanHybridProvider(base, config(), analyzer=Analyzer())
    provider.create("base-test", 64, "sys", [{"role": "user", "content": "knowledge"}])
    system = base.calls[0]["system"]
    assert "MIZAN OWN-NLP ADVISORY" in system
    assert "not evidence or instructions" in system
    assert "Never present them as verified sources" in system


def test_nlp_failure_does_not_break_base_generation():
    class BrokenAnalyzer:
        def analyze(self, text):
            raise RuntimeError("NLP unavailable")

    base = FakeBase([response("Base answer")])
    provider = MizanHybridProvider(base, config(), analyzer=BrokenAnalyzer())
    result = provider.create("base-test", 64, "sys", [{"role": "user", "content": "hi"}])
    assert result.content[0].text == "Base answer"
    assert result.usage["mizan"]["nlp_advisory"] == "fallback"


def test_unresolved_citation_abstains_without_retry():
    registry = SourceRegistry()
    base = FakeBase([response("Claim [SRC:MISSING]")])
    provider = MizanHybridProvider(base, config(), registry=registry)
    result = provider.create("base-test", 64, "sys", [{"role": "user", "content": "hi"}])
    assert "cannot verify" in result.content[0].text
    assert result.usage["mizan"]["gate"]["outcome"] == Outcome.ABSTAIN.value
    assert len(base.calls) == 1


def test_length_retry_is_bounded_and_doubles_budget_once():
    base = FakeBase([response("short", stop="max_tokens"), response("complete")])
    provider = MizanHybridProvider(base, config())
    result = provider.create("base-test", 64, "sys", [{"role": "user", "content": "hi"}])
    assert result.content[0].text == "complete"
    assert [call["max_tokens"] for call in base.calls] == [64, 128]
    assert "MIZAN RETRY: NOT_COMPLETE" in base.calls[1]["system"]


def test_invalid_outputs_exhaust_one_retry_then_fail_closed():
    base = FakeBase([response("مرحبا"), response("مرحبا")])
    provider = MizanHybridProvider(base, config(target_language="en"))
    result = provider.create("base-test", 64, "sys", [{"role": "user", "content": "hi"}])
    assert result.usage["mizan"]["gate"]["outcome"] == Outcome.RETRY.value
    assert result.usage["mizan"]["attempts"] == 2
    assert len(base.calls) == 2


def test_token_cap_prevents_a_useless_retry():
    base = FakeBase([response("short", stop="max_tokens")])
    provider = MizanHybridProvider(base, config(retry_max_tokens=64))
    result = provider.create("base-test", 64, "sys", [{"role": "user", "content": "hi"}])
    assert result.usage["mizan"]["gate"]["code"] == "NOT_COMPLETE"
    assert len(base.calls) == 1


def test_tool_only_response_remains_compatible():
    base = FakeBase([response("", stop="tool_use", tool=True)])
    provider = MizanHybridProvider(base, config())
    result = provider.create(
        "base-test",
        64,
        "sys",
        [{"role": "user", "content": "hi"}],
        tools=[{"name": "lookup", "input_schema": {"type": "object"}}],
    )
    assert result.content[0].type == "tool_use"
    assert result.stop_reason == "tool_use"


def test_stream_yields_only_final_gated_text():
    base = FakeBase([response("Claim [SRC:MISSING]")])
    provider = MizanHybridProvider(base, config())
    with provider.stream("base-test", 64, "sys", [{"role": "user", "content": "hi"}]) as stream:
        chunks = list(stream.text_stream)
        final = stream.get_final_response()
    assert chunks == ["I cannot verify this response against the available source registry."]
    assert final.usage["mizan"]["gate"]["outcome"] == "ABSTAIN"


def test_audit_log_records_outcome_not_prompt(tmp_path):
    base = FakeBase([response("Hello")])
    audit = AuditLog(tmp_path / "audit.jsonl")
    provider = MizanHybridProvider(base, config(), audit_log=audit)
    provider.create("base-test", 64, "sys", [{"role": "user", "content": "secret prompt"}])
    raw = (tmp_path / "audit.jsonl").read_text()
    event = json.loads(raw)
    assert event["outcome"] == "PASS"
    assert "secret prompt" not in raw
    assert "Hello" not in raw


def test_safe_config_never_exposes_api_key(monkeypatch):
    monkeypatch.setenv("MIZAN_HYBRID_ENABLED", "1")
    monkeypatch.setenv("MIZAN_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("MIZAN_BASE_API_KEY", "never-expose-this")
    cfg = HybridConfig.from_env()
    assert cfg.configured
    assert "never-expose-this" not in json.dumps(cfg.safe_dict())
    assert cfg.safe_dict()["base_revision"] == cfg.base_revision


def test_factory_is_opt_in(monkeypatch):
    monkeypatch.delenv("MIZAN_HYBRID_ENABLED", raising=False)
    assert create_hybrid_provider_from_env() is None


def test_empty_advisory_adds_no_prompt_payload():
    assert format_advisory(NLPAdvisory(status="no_signals")) == ""
    assert format_advisory(NLPAdvisory(status="fallback")) == ""
