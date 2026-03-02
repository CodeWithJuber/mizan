"""Tests for the IntelligentRouter query routing."""

from unittest.mock import MagicMock

import pytest

from providers import BaseLLMProvider, ContentBlock, LLMResponse
from router.intelligent_router import IntelligentRouter, RouteDecision


def _make_llm_response(text: str, model: str = "test-model") -> LLMResponse:
    """Helper to create a minimal LLMResponse."""
    return LLMResponse(
        content=[ContentBlock(type="text", text=text)],
        stop_reason="end_turn",
        model=model,
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def _make_mock_provider(name: str, response_text: str) -> MagicMock:
    """Helper to create a mock BaseLLMProvider."""
    provider = MagicMock(spec=BaseLLMProvider)
    provider.provider_name = name
    provider.create.return_value = _make_llm_response(response_text, model=name)
    return provider


class TestRoutingToRuh:
    """Test that queries route to ruh provider when available."""

    def test_routes_to_ruh_when_available_and_no_tools(self) -> None:
        """Should use ruh provider when it exists and no tools are needed."""
        ruh = _make_mock_provider("ruh", "Local response")
        external = _make_mock_provider("external", "External response")
        router = IntelligentRouter(ruh_provider=ruh, external_provider=external)

        response, decision = router.route(
            model="ruh-local",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert decision.provider_used == "ruh"
        assert response.content[0].text == "Local response"
        ruh.create.assert_called_once()
        external.create.assert_not_called()

    def test_ruh_increments_stats(self) -> None:
        """Routing to ruh should increment the ruh stat counter."""
        ruh = _make_mock_provider("ruh", "response")
        router = IntelligentRouter(ruh_provider=ruh)

        router.route(
            model="ruh-local",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "test"}],
        )

        assert router.stats["ruh"] == 1
        assert router.stats["external"] == 0


class TestFallbackToExternal:
    """Test fallback to external provider."""

    def test_routes_to_external_when_ruh_not_available(self) -> None:
        """Should fall back to external when ruh_provider is None."""
        external = _make_mock_provider("external", "External response")
        router = IntelligentRouter(ruh_provider=None, external_provider=external)

        response, decision = router.route(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system="sys",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert decision.provider_used == "external"
        assert decision.reason == "ruh_not_available"
        assert response.content[0].text == "External response"

    def test_routes_to_external_when_tools_required(self) -> None:
        """Should use external provider when tools are requested."""
        ruh = _make_mock_provider("ruh", "Local")
        external = _make_mock_provider("external", "Tool response")
        router = IntelligentRouter(ruh_provider=ruh, external_provider=external)

        tools = [{"name": "bash", "description": "Run commands", "input_schema": {}}]
        response, decision = router.route(
            model="ruh-local",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "list files"}],
            tools=tools,
        )

        assert decision.provider_used == "external"
        assert decision.reason == "tools_required"
        ruh.create.assert_not_called()
        external.create.assert_called_once()

    def test_falls_back_on_ruh_failure(self) -> None:
        """Should route to external when ruh.create() raises an exception."""
        ruh = MagicMock(spec=BaseLLMProvider)
        ruh.create.side_effect = RuntimeError("Model not loaded")

        external = _make_mock_provider("external", "Fallback response")
        router = IntelligentRouter(ruh_provider=ruh, external_provider=external)

        response, decision = router.route(
            model="ruh-local",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "test"}],
        )

        assert decision.provider_used == "external"
        assert "ruh_failed" in decision.reason
        assert response.content[0].text == "Fallback response"

    def test_raises_when_no_external_configured(self) -> None:
        """Should raise RuntimeError when external provider is also None."""
        router = IntelligentRouter(ruh_provider=None, external_provider=None)

        with pytest.raises(RuntimeError, match="No external provider configured"):
            router.route(
                model="test",
                max_tokens=100,
                system="sys",
                messages=[{"role": "user", "content": "test"}],
            )


class TestConfidenceThreshold:
    """Test that the router respects the confidence threshold setting."""

    def test_default_confidence_threshold(self) -> None:
        """Default confidence threshold should be 0.7."""
        router = IntelligentRouter()
        assert router._threshold == 0.7

    def test_custom_confidence_threshold(self) -> None:
        """Custom threshold should be stored correctly."""
        router = IntelligentRouter(confidence_threshold=0.9)
        assert router._threshold == 0.9


class TestRouterStats:
    """Test routing statistics tracking."""

    def test_initial_stats_are_zero(self) -> None:
        """All stats should start at zero."""
        router = IntelligentRouter()
        assert router.stats == {"ruh": 0, "external": 0, "fallback": 0}

    def test_stats_accumulate(self) -> None:
        """Stats should accumulate across multiple route calls."""
        ruh = _make_mock_provider("ruh", "response")
        external = _make_mock_provider("external", "response")
        router = IntelligentRouter(ruh_provider=ruh, external_provider=external)

        messages = [{"role": "user", "content": "test"}]

        # Two ruh calls
        router.route("m", 100, "s", messages)
        router.route("m", 100, "s", messages)
        # One external call (via tools)
        router.route("m", 100, "s", messages, tools=[{"name": "t"}])

        assert router.stats["ruh"] == 2
        assert router.stats["external"] == 1

    def test_reset_stats_clears_counters(self) -> None:
        """reset_stats() should zero all counters."""
        ruh = _make_mock_provider("ruh", "response")
        router = IntelligentRouter(ruh_provider=ruh)

        router.route("m", 100, "s", [{"role": "user", "content": "x"}])
        assert router.stats["ruh"] == 1

        router.reset_stats()
        assert router.stats == {"ruh": 0, "external": 0, "fallback": 0}

    def test_stats_returns_copy(self) -> None:
        """stats property should return a copy, not the internal dict."""
        router = IntelligentRouter()
        stats = router.stats
        stats["ruh"] = 999

        assert router.stats["ruh"] == 0


class TestRouteDecision:
    """Test the RouteDecision dataclass."""

    def test_route_decision_fields(self) -> None:
        """RouteDecision should store provider, confidence, and reason."""
        decision = RouteDecision(
            provider_used="ruh",
            confidence=0.85,
            reason="high_confidence",
        )
        assert decision.provider_used == "ruh"
        assert decision.confidence == 0.85
        assert decision.reason == "high_confidence"
