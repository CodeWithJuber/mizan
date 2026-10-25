"""Provider identity, model version and tool-capability regressions."""

from types import SimpleNamespace

import pytest

from agents.specialized import create_agent
from api.commands import cmd_model
from providers import (
    ContentBlock,
    LLMResponse,
    Qwen3ServerlessProvider,
    create_provider,
    normalize_model_for_provider,
)
from providers_ruh_remote import RuhRemoteProvider


@pytest.fixture
def provider_env(monkeypatch):
    """Never use local credentials or make a model request in these checks."""
    monkeypatch.delenv("MIZAN_OWNED_ONLY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-placeholder")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-placeholder")
    monkeypatch.setattr(
        "providers.AnthropicProvider", lambda **kwargs: SimpleNamespace(provider_name="anthropic")
    )
    monkeypatch.setattr(
        "providers.OpenAICompatibleProvider",
        lambda **kwargs: SimpleNamespace(provider_name=kwargs["provider_name"]),
    )


@pytest.mark.parametrize(
    "model, expected",
    [
        ("anthropic/claude-opus-4.6", "openrouter"),
        ("anthropic/claude-sonnet-4.6", "openrouter"),
        ("claude-opus-4-6", "anthropic"),
    ],
)
def test_namespaced_model_keeps_its_route_when_both_keys_exist(provider_env, model, expected):
    assert create_provider(model=model).provider_name == expected


@pytest.mark.parametrize("model", ["claude-opus-4-6", "claude-sonnet-4-6"])
async def test_model_command_preserves_requested_generation(provider_env, monkeypatch, model):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    agent = SimpleNamespace(ai_model="old", ai_client=None)
    result = await cmd_model(args=model, agent=agent)
    assert agent.ai_client.provider_name == "openrouter"
    assert agent.ai_model == "anthropic/" + model.removesuffix("-6") + ".6"
    assert agent.ai_model in result


def test_explicit_and_owned_routes_still_take_precedence(provider_env, monkeypatch):
    assert create_provider(provider="anthropic", model="claude-opus-4-6").provider_name == (
        "anthropic"
    )
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "1")
    assert create_provider(model="anthropic/claude-opus-4.6").provider_name == "mizan-owned"


def test_normalization_leaves_other_explicit_model_versions_unchanged():
    model = "example/model-version:free"
    assert normalize_model_for_provider(model, "openrouter") == model


@pytest.mark.parametrize("requested", [None, "claude-sonnet-4-6"])
def test_research_modes_use_selected_provider_or_normalized_explicit_model(monkeypatch, requested):
    from api.modes import _chat_completion_sync

    calls = []

    def factory(**selection):
        calls.append(selection)

        def complete(**request):
            calls.append(request)
            return LLMResponse(
                [ContentBlock(type="text", text="answer")],
                "end_turn",
                request["model"],
                {"input": 1, "output": 2},
            )

        return SimpleNamespace(provider_name=selection["provider"] or "openrouter", create=complete)

    monkeypatch.setattr("providers.create_provider", factory)
    monkeypatch.setattr(
        "providers.get_provider_status",
        lambda: {"active": "mizan-owned", "default_model": "mizan-owned"},
    )
    assert _chat_completion_sync(requested, "sys", [], 32) == ("answer", 1, 2)
    if requested is None:
        assert calls[0] == {"provider": "mizan-owned", "model": "mizan-owned"}
        assert calls[1]["model"] == "mizan-owned"
    else:
        assert calls[0] == {"provider": None, "model": requested}
        assert calls[1]["model"] == "anthropic/claude-sonnet-4.6"


@pytest.mark.parametrize(
    "provider",
    [
        Qwen3ServerlessProvider(config=SimpleNamespace()),
        RuhRemoteProvider(endpoint_id="test-endpoint", api_key="test-placeholder"),
    ],
    ids=["qwen3", "ruh-remote"],
)
async def test_text_only_adapter_does_not_advertise_tools(
    provider, monkeypatch, mock_wali, mock_izn
):
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", name="Capability test", wali=mock_wali, izn=mock_izn)
    agent.ai_client = provider
    agent.ai_model = "test-model"
    assert agent.get_tool_schemas() == []
    prompt = await agent._build_system_prompt()
    assert "You have no tool access in this model." in prompt
    assert "You have access to tools." not in prompt
    assert f"provided by {provider.provider_name}" in prompt
