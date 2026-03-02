"""Intelligent router: routes queries to Ruh Model or external LLM based on confidence."""

import logging
from dataclasses import dataclass

from providers import BaseLLMProvider, LLMResponse

logger = logging.getLogger("mizan.router")


@dataclass
class RouteDecision:
    """Records which provider was used and why."""

    provider_used: str
    confidence: float
    reason: str


class IntelligentRouter:
    """Routes queries to the best available provider.

    Strategy:
    - If Ruh Model is available and tools are not needed, try Ruh first.
    - Falls back to external provider on Ruh failure or when tools are required.
    """

    def __init__(
        self,
        ruh_provider: BaseLLMProvider | None = None,
        external_provider: BaseLLMProvider | None = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        self._ruh = ruh_provider
        self._external = external_provider
        self._threshold = confidence_threshold
        self._stats: dict[str, int] = {"ruh": 0, "external": 0, "fallback": 0}

    def route(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> tuple[LLMResponse, RouteDecision]:
        """Route to best provider. Returns (response, decision)."""
        if not self._ruh:
            return self._route_external(
                model, max_tokens, system, messages, tools, temperature,
                reason="ruh_not_available",
            )

        # Ruh Model doesn't support tool_use yet
        if tools:
            return self._route_external(
                model, max_tokens, system, messages, tools, temperature,
                reason="tools_required",
            )

        return self._try_ruh_with_fallback(
            model, max_tokens, system, messages, temperature,
        )

    def _route_external(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float | None,
        reason: str,
    ) -> tuple[LLMResponse, RouteDecision]:
        """Route directly to external provider."""
        if not self._external:
            raise RuntimeError("No external provider configured")
        response = self._external.create(
            model, max_tokens, system, messages, tools, temperature,
        )
        decision = RouteDecision("external", 0.0, reason)
        self._stats["external"] += 1
        return response, decision

    def _try_ruh_with_fallback(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        temperature: float | None,
    ) -> tuple[LLMResponse, RouteDecision]:
        """Try Ruh Model first; fall back to external on failure."""
        try:
            response = self._ruh.create(
                model, max_tokens, system, messages, temperature=temperature,
            )
            decision = RouteDecision("ruh", 0.5, "ruh_available")
            self._stats["ruh"] += 1
            return response, decision
        except Exception as exc:
            logger.warning("Ruh Model failed, falling back to external: %s", exc)
            return self._route_external(
                model, max_tokens, system, messages, None, temperature,
                reason=f"ruh_failed: {exc}",
            )

    @property
    def stats(self) -> dict[str, int]:
        """Routing statistics by provider."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset routing counters."""
        self._stats = {"ruh": 0, "external": 0, "fallback": 0}
