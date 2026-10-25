"""Provider changes refresh private agents without rewriting running requests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from agents.specialized import create_agent
from security.auth import TokenPayload


@pytest.fixture
def settings_api(monkeypatch, tmp_path, mock_wali, mock_izn):
    import api.main as main

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_user_agents", {})
    monkeypatch.setattr(main, "wali", mock_wali)
    monkeypatch.setattr(main, "izn", mock_izn)
    monkeypatch.setattr(main, "skill_registry", None)
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock()))
    monkeypatch.setattr(main, "event_bus", SimpleNamespace(emit=AsyncMock()))
    memory = SimpleNamespace(set_preference=AsyncMock(), save_agent_profile=AsyncMock())
    monkeypatch.setattr(main, "memory", memory)
    template = create_agent("general", name="Original", wali=mock_wali, izn=mock_izn)
    template.ai_client = SimpleNamespace(provider_name="original")
    template.ai_model = "original-model"
    monkeypatch.setattr(main, "active_agents", {template.id: template})
    user = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "test")
    return main, template, user, memory


async def test_cached_user_override_survives_until_admin_configuration_changes(settings_api):
    main, template, user, _ = settings_api
    private = await main.chat_agent_for(user, template)
    private_memory = private.memory
    local_provider = SimpleNamespace(provider_name="user-choice")
    private.ai_client, private.ai_model = local_provider, "user-model"
    assert await main.chat_agent_for(user, template) is private
    assert private.ai_client is local_provider

    template._config_revision = 1
    template.name = "Updated"
    template.config["system_prompt"] = "Use the configured identity"
    template.ai_client = SimpleNamespace(provider_name="updated")
    template.ai_model = "updated-model"
    refreshed = await main.chat_agent_for(user, template)
    assert refreshed is private
    assert refreshed.memory is private_memory
    assert refreshed.ai_client is template.ai_client
    assert refreshed.ai_model == "updated-model"
    assert refreshed.name == "Updated"
    assert refreshed.config == template.config
    assert refreshed.config is not template.config


async def test_refresh_waits_for_running_private_agent(settings_api):
    main, template, user, _ = settings_api
    private = await main.chat_agent_for(user, template)
    original = private.ai_client
    async with main.agent_settings_lock(private):
        template._config_revision = 1
        template.ai_client = SimpleNamespace(provider_name="replacement")
        task = asyncio.create_task(main.chat_agent_for(user, template))
        await asyncio.sleep(0)
        assert not task.done()
        assert private.ai_client is original
    assert await task is private
    assert private.ai_client is template.ai_client


async def test_agent_model_is_normalized_and_persisted(settings_api, monkeypatch):
    main, template, _, memory = settings_api
    provider = SimpleNamespace(provider_name="openrouter")
    monkeypatch.setattr(main, "create_provider", lambda **kwargs: provider)
    result = await main.set_agent_model(
        template.id,
        main.AgentModelRequest(provider="openrouter", model="claude-opus-4-6"),
    )
    assert result["model"] == "anthropic/claude-opus-4.6"
    assert template.ai_model == result["model"]
    saved = memory.save_agent_profile.await_args.args[0]["config"]
    assert saved["model"] == result["model"]
    assert saved["provider_override"] == {"provider": "openrouter", "model": result["model"]}


async def test_invalid_update_is_atomic(settings_api, monkeypatch):
    main, template, _, memory = settings_api
    monkeypatch.setattr(main, "create_provider", lambda **kwargs: None)
    with pytest.raises(HTTPException) as exc:
        await main.update_agent(
            template.id, main.AgentUpdate(name="Should not change", model="unavailable")
        )
    assert exc.value.status_code == 400
    assert template.name == "Original"
    assert template.ai_model == "original-model"
    memory.save_agent_profile.assert_not_awaited()


async def test_global_switch_refreshes_cached_users_and_clears_persisted_override(
    settings_api, monkeypatch
):
    main, template, user, memory = settings_api
    private = await main.chat_agent_for(user, template)
    template.config["provider_override"] = {"provider": "old", "model": "old"}
    provider = SimpleNamespace(provider_name="openrouter")
    monkeypatch.setattr(main, "create_provider", lambda **kwargs: provider)
    await main.switch_provider(
        main.ProviderSwitchRequest(provider="openrouter", model="claude-sonnet-4-6")
    )
    await main.chat_agent_for(user, template)
    assert private.ai_client is provider
    assert private.ai_model == "anthropic/claude-sonnet-4.6"
    assert "provider_override" not in template.config
    memory.save_agent_profile.assert_awaited_once()
    memory.set_preference.assert_any_await("active_model", "anthropic/claude-sonnet-4.6")
