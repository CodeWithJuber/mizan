"""Guarded provider combining a base LLM, own-NLP advisory, and Mizan gates."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from mizan_hybrid.config import HybridConfig
from mizan_hybrid.gates import AuditLog, Decision, Outcome, SourceRegistry, gate_response
from mizan_hybrid.nlp import Analyzer, NLPAdvisory, QCAOwnNLPAnalyzer, format_advisory
from providers import BaseLLMProvider, ContentBlock, LLMResponse

_SAFE_MESSAGES = {
    Outcome.RETRY: "I could not produce a complete, policy-compliant response. Please retry.",
    Outcome.ABSTAIN: "I cannot verify this response against the available source registry.",
    Outcome.HUMAN_REVIEW: "This response requires independent review before it can be returned.",
}


class MizanHybridProvider(BaseLLMProvider):
    """Wrap any existing provider without merging weights or changing its interface.

    Streaming is intentionally inherited from ``BaseLLMProvider``: it buffers
    ``create()`` and yields only the final gated text, never raw model deltas.
    """

    provider_name = "mizan-hybrid"

    def __init__(
        self,
        base: BaseLLMProvider,
        config: HybridConfig,
        *,
        registry: SourceRegistry | None = None,
        analyzer: Analyzer | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        self.base = base
        self.supports_tools = getattr(base, "supports_tools", True)
        self.max_output_tokens = getattr(base, "max_output_tokens", None)
        self.context_window = config.context_window
        self.config = config
        self.registry = registry or SourceRegistry()
        self.analyzer = analyzer or (QCAOwnNLPAnalyzer() if config.nlp_advisory else None)
        self.audit_log = audit_log

    @staticmethod
    def _last_user_text(messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
        return ""

    @staticmethod
    def _response_text(response: LLMResponse) -> str:
        return "\n".join(
            block.text for block in response.content if block.type == "text" and block.text
        )

    @staticmethod
    def _has_tool_use(response: LLMResponse) -> bool:
        return any(block.type == "tool_use" for block in response.content)

    def _advisory(self, messages: list[dict]) -> NLPAdvisory:
        if self.analyzer is None:
            return NLPAdvisory(status="disabled")
        text = self._last_user_text(messages)
        if not text.strip():
            return NLPAdvisory(status="no_input")
        try:
            return self.analyzer.analyze(text)
        except Exception:
            # Analyzer implementations should fail closed; this is a second containment boundary.
            return NLPAdvisory(status="fallback")

    def _metadata(
        self,
        decision: Decision,
        advisory: NLPAdvisory,
        attempts: int,
    ) -> dict[str, Any]:
        return {
            "gate": decision.metadata(),
            "nlp_advisory": advisory.status,
            "attempts": attempts,
            "base_revision": self.config.base_revision,
            "semantic_or_religious_certification": False,
        }

    def _record(self, case_id: str, decision: Decision) -> None:
        if self.audit_log is not None:
            self.audit_log.append(case_id, decision)

    def _safe_response(
        self,
        response: LLMResponse,
        decision: Decision,
        advisory: NLPAdvisory,
        attempts: int,
        case_id: str,
    ) -> LLMResponse:
        self._record(case_id, decision)
        usage = dict(response.usage)
        usage["mizan"] = self._metadata(decision, advisory, attempts)
        return LLMResponse(
            content=[ContentBlock(type="text", text=_SAFE_MESSAGES[decision.outcome])],
            stop_reason="end_turn",
            model=response.model or self.config.base_model,
            usage=usage,
        )

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        advisory = self._advisory(messages)
        advisory_text = format_advisory(advisory)
        selected_model = model or self.config.base_model
        initial_max_tokens = int(max_tokens or 256)
        if self.max_output_tokens is not None:
            initial_max_tokens = min(initial_max_tokens, self.max_output_tokens)
        attempt_max_tokens = initial_max_tokens
        case_id = uuid.uuid4().hex
        response: LLMResponse | None = None
        decision = Decision(Outcome.RETRY, "NOT_RUN", "regenerate", "No attempt ran.")

        for attempt in range(1, self.config.max_gate_retries + 2):
            attempt_system = system + advisory_text
            if attempt > 1:
                attempt_system += (
                    f"\n\n[MIZAN RETRY: {decision.code}] Correct the declared output contract. "
                    "Do not invent citations, evidence, review attestations, or missing text."
                )
            response = self.base.create(
                model=selected_model,
                max_tokens=attempt_max_tokens,
                system=attempt_system,
                messages=messages,
                tools=tools,
                temperature=0.0 if temperature is None else temperature,
            )
            decision = gate_response(
                self.registry,
                self._response_text(response),
                target_language=self.config.target_language,
                finish_reason=response.stop_reason,
                allow_tool_only=self._has_tool_use(response),
            )
            if decision.allowed:
                self._record(case_id, decision)
                response.usage = dict(response.usage)
                response.usage["mizan"] = self._metadata(decision, advisory, attempt)
                return response
            if decision.outcome is not Outcome.RETRY:
                return self._safe_response(response, decision, advisory, attempt, case_id)
            if attempt > self.config.max_gate_retries:
                return self._safe_response(response, decision, advisory, attempt, case_id)
            if decision.code == "NOT_COMPLETE":
                increased = max(attempt_max_tokens + 1, attempt_max_tokens * 2)
                next_max_tokens = min(increased, self.config.retry_max_tokens)
                if self.max_output_tokens is not None:
                    next_max_tokens = min(next_max_tokens, self.max_output_tokens)
                if next_max_tokens <= attempt_max_tokens:
                    return self._safe_response(response, decision, advisory, attempt, case_id)
                attempt_max_tokens = next_max_tokens

        # The loop always returns; this guard prevents accidental future fall-through.
        assert response is not None
        return self._safe_response(response, decision, advisory, 0, case_id)


def create_hybrid_provider_from_env() -> MizanHybridProvider | None:
    """Build the opt-in runtime using existing provider implementations."""
    config = HybridConfig.from_env()
    if not config.configured:
        return None
    if config.base_provider == "mizan-hybrid":
        raise ValueError("MIZAN_BASE_PROVIDER cannot recursively select mizan-hybrid")

    if config.base_provider == "openai-compatible":
        from providers import OpenAICompatibleProvider

        base: BaseLLMProvider | None = OpenAICompatibleProvider(
            api_key=config.base_api_key,
            base_url=config.base_url,
            provider_name="mizan-base",
        )
    else:
        from providers import create_provider

        base = create_provider(config.base_provider, config.base_model)
    if base is None:
        return None

    registry = (
        SourceRegistry.from_file(config.registry_file)
        if config.registry_file is not None
        else SourceRegistry()
    )
    audit_log = AuditLog(Path(config.audit_log_path)) if config.audit_log_path else None
    return MizanHybridProvider(base, config, registry=registry, audit_log=audit_log)
