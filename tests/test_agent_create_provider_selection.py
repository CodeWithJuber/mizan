"""Agent creation resolves one provider and never publishes a partial agent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from memory.dhikr import DhikrMemorySystem
from security.auth import MizanAuth


@pytest.fixture
def api(tmp_path, monkeypatch, mock_wali, mock_izn):
    import api.main as main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    monkeypatch.delenv("DEBUG", raising=False)
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("agent-create-test-key-" * 4, data_dir=str(tmp_path / "users"))
    user = auth.create_user("creator", "fixture-password", roles=["admin"])
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setattr(main, "active_agents", {})
    monkeypatch.setattr(main, "balancer", SimpleNamespace(register=Mock()))
    monkeypatch.setattr(main, "shura", SimpleNamespace(members={}))
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock()))
    monkeypatch.setattr(main, "event_bus", SimpleNamespace(emit=AsyncMock()))
    monkeypatch.setattr(main, "wali", mock_wali)
    monkeypatch.setattr(main, "izn", mock_izn)
    monkeypatch.setattr(main, "skill_registry", None)
    monkeypatch.setattr(main, "plugin_manager", None)
    runtime = Mock(
        return_value={
            "active": "openrouter",
            "default_model": "nvidia/runtime-choice:free",
            "providers": [{"name": "ollama", "default_model": "my-local-default"}],
        }
    )
    monkeypatch.setattr(main, "get_provider_status", runtime)
    clients = []

    def build(provider=None, model=None):
        client = SimpleNamespace(
            provider_name=provider or "openrouter", create=Mock(), stream=Mock()
        )
        clients.append(client)
        return client

    factory = Mock(side_effect=build)
    monkeypatch.setattr("agents.base.create_provider", factory)
    # Do not enter app lifespan: this fixture must not initialize live default
    # agents, schedulers or clients. Only the requested route is exercised.
    client = TestClient(main.app, raise_server_exceptions=False)
    headers = {"Authorization": "Bearer " + auth.create_token(user)}
    yield main, client, headers, memory, factory, runtime
    for provider in clients:
        provider.create.assert_not_called()
        provider.stream.assert_not_called()


def create(client, headers, **selection):
    return client.post(
        "/api/agents",
        headers=headers,
        json={"name": "New specialist", "type": "general", **selection},
    )


def assert_published(main, memory, response, provider, model):
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["provider"] == provider and data["model"] == model
    agent = main.active_agents[data["id"]]
    assert agent.config["provider_override"] == {"provider": provider, "model": model}
    profiles = asyncio.run(memory.get_all_agents())
    assert len(profiles) == 1 and profiles[0]["config"] == agent.config
    assert profiles[0]["nafs_level"] == agent.nafs_level
    main.balancer.register.assert_called_once_with(agent.id)
    assert main.shura.members[agent.id] is agent
    main.manager.broadcast.assert_awaited_once()
    main.event_bus.emit.assert_awaited_once()


def test_omitted_model_uses_current_runtime_selection(api):
    main, client, headers, memory, factory, runtime = api
    response = create(client, headers, system_prompt="Reply concisely.")
    factory.assert_called_once_with(provider="openrouter", model="nvidia/runtime-choice:free")
    runtime.assert_called_once_with()
    assert_published(main, memory, response, "openrouter", "nvidia/runtime-choice:free")


def test_explicit_local_custom_model_keeps_provider_and_full_id(api):
    main, client, headers, memory, factory, runtime = api
    model = "local-team/" + "custom-" * 18 + "v2:latest"
    assert 100 < len(model) <= 200
    response = create(client, headers, provider="ollama", model=model)
    factory.assert_called_once_with(provider="ollama", model=model)
    runtime.assert_not_called()
    assert_published(main, memory, response, "ollama", model)


def test_selected_provider_omitted_model_uses_provider_default(api, monkeypatch):
    main, client, headers, memory, factory, _ = api
    monkeypatch.setenv("DEFAULT_MODEL", "foreign-hosted/global-default:free")
    default = Mock(return_value="foreign-hosted/global-default:free")
    monkeypatch.setattr(main, "get_default_model", default)
    response = create(client, headers, provider="ollama")
    default.assert_not_called()
    factory.assert_called_once_with(provider="ollama", model="my-local-default")
    assert_published(main, memory, response, "ollama", "my-local-default")


def test_model_only_creation_uses_runtime_provider_even_if_environment_differs(api, monkeypatch):
    main, client, headers, memory, factory, runtime = api
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    response = create(client, headers, model="vendor/legacy-model")
    factory.assert_called_once_with(provider="openrouter", model="vendor/legacy-model")
    runtime.assert_called_once_with()
    assert_published(main, memory, response, "openrouter", "vendor/legacy-model")


def test_normalized_actual_model_is_persisted_from_creation(api):
    main, client, headers, memory, factory, _ = api
    response = create(client, headers, provider="openrouter", model="claude-sonnet-4-6")
    factory.assert_called_once_with(provider="openrouter", model="claude-sonnet-4-6")
    assert_published(main, memory, response, "openrouter", "anthropic/claude-sonnet-4.6")


def test_missing_selected_provider_default_requires_model_without_guessing(api):
    main, client, headers, memory, factory, _ = api
    response = create(client, headers, provider="qwen3")
    assert response.status_code == 400
    factory.assert_not_called()
    assert not main.active_agents and asyncio.run(memory.get_all_agents()) == []


@pytest.mark.parametrize("failure", [None, RuntimeError("private configuration detail")])
def test_unavailable_provider_cannot_publish_or_persist_an_orphan(api, failure):
    main, client, headers, memory, factory, _ = api
    factory.side_effect = failure
    factory.return_value = None
    response = create(client, headers, provider="qwen3", model="local/custom")
    assert response.status_code == 400 and "private" not in response.text
    assert not main.active_agents and not main.shura.members
    assert asyncio.run(memory.get_all_agents()) == []
    main.balancer.register.assert_not_called()
    main.manager.broadcast.assert_not_awaited()
    main.event_bus.emit.assert_not_awaited()


def test_profile_failure_leaves_agent_unpublished(api, monkeypatch):
    main, client, headers, _, _, _ = api
    monkeypatch.setattr(
        main.memory, "save_agent_profile", AsyncMock(side_effect=RuntimeError("write failed"))
    )
    response = create(client, headers, provider="ollama", model="custom")
    assert response.status_code == 500
    assert not main.active_agents and not main.shura.members
    main.balancer.register.assert_not_called()
    main.manager.broadcast.assert_not_awaited()


def test_owned_only_guard_remains_authoritative_for_explicit_remote_selection(api, monkeypatch):
    import providers

    main, client, headers, memory, _, _ = api
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "true")
    monkeypatch.setattr("agents.base.create_provider", providers.create_provider)
    hosted = Mock(side_effect=AssertionError("Hosted adapter must not be constructed"))
    monkeypatch.setattr(providers, "OpenAICompatibleProvider", hosted)
    response = create(client, headers, provider="openrouter", model="nvidia/explicit-model:free")
    hosted.assert_not_called()
    assert_published(main, memory, response, "mizan-owned", "mizan-owned")


def test_schema_and_auth_rejection_have_no_side_effects(api):
    main, client, headers, memory, factory, _ = api
    assert create(client, {}, provider="ollama", model="custom").status_code == 401
    assert create(client, headers, provider="invented", model="custom").status_code == 422
    assert create(client, headers, provider="ollama", model="").status_code == 422
    factory.assert_not_called()
    assert not main.active_agents and asyncio.run(memory.get_all_agents()) == []
