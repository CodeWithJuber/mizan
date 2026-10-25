from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import providers

HYBRID_ENV = {
    "MIZAN_HYBRID_ENABLED": "true",
    "MIZAN_BASE_PROVIDER": "openai-compatible",
    "MIZAN_BASE_MODEL": "Qwen/Qwen3-4B-Instruct-2507",
    "MIZAN_BASE_REVISION": "cdbee75f17c01a7cc42f958dc650907174af0554",
    "MIZAN_BASE_URL": "https://endpoint.example/v1",
    "MIZAN_BASE_API_KEY": "test-secret",
}


def _enable_hybrid(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in HYBRID_ENV.items():
        monkeypatch.setenv(key, value)


def test_factory_delegates_opt_in_hybrid(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = object()
    monkeypatch.setattr(
        "mizan_hybrid.provider.create_hybrid_provider_from_env", lambda: expected
    )

    assert providers.create_provider("mizan-hybrid") is expected


def test_status_and_default_model_use_hybrid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_hybrid(monkeypatch)
    monkeypatch.setenv("DEFAULT_MODEL", "openrouter/free")
    monkeypatch.setattr(providers, "_active_state", {"provider": "", "model": ""})

    status = providers.get_provider_status()
    card = next(p for p in status["providers"] if p["name"] == "mizan-hybrid")

    assert card["configured"] is True
    assert card["default_model"] == HYBRID_ENV["MIZAN_BASE_MODEL"]
    assert card["models"][0]["context"] == 16384
    assert card["semantic_or_religious_certification"] is False
    assert providers.get_default_model("mizan-hybrid") == HYBRID_ENV["MIZAN_BASE_MODEL"]
    assert "test-secret" not in repr(status)


def test_hybrid_health_requires_expected_served_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_hybrid(monkeypatch)
    observed = {}

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"data": [{"id": HYBRID_ENV["MIZAN_BASE_MODEL"]}]}

    class Client:
        def __init__(self, **kwargs) -> None:
            observed["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url: str, headers: dict) -> Response:
            observed["url"] = url
            observed["authorized"] = bool(headers.get("Authorization"))
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    result = asyncio.run(providers.check_provider_health("mizan-hybrid"))

    assert result["healthy"] is True
    assert result["base_revision"] == HYBRID_ENV["MIZAN_BASE_REVISION"]
    assert observed == {
        "timeout": 120,
        "url": "https://endpoint.example/v1/models",
        "authorized": True,
    }


def test_hybrid_health_rejects_wrong_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_hybrid(monkeypatch)

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"data": [{"id": "unrelated/model"}]}

    class Client:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs) -> Response:
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    result = asyncio.run(providers.check_provider_health("mizan-hybrid"))

    assert result["healthy"] is False
    assert "test-secret" not in repr(result)


def test_provider_switch_validation_and_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import main

    for name in ("mizan-hybrid", "ruh", "ruh-remote", "qwen3"):
        main.ProviderSwitchRequest(provider=name, model="test-model")
    with pytest.raises(ValueError):
        main.ProviderSwitchRequest(provider="not-a-provider", model="test-model")

    agent = SimpleNamespace(ai_client=None, ai_model="")
    replacement = object()
    preferences = {}
    events = []

    class Memory:
        async def set_preference(self, key: str, value: str) -> None:
            preferences[key] = value

    class Broadcaster:
        async def broadcast(self, event: dict) -> None:
            events.append(event)

    class EventBus:
        async def emit(self, name: str, event: dict) -> None:
            events.append({"name": name, **event})

    monkeypatch.setattr(main, "active_agents", {"agent": agent})
    monkeypatch.setattr(main, "create_provider", lambda **kwargs: replacement)
    monkeypatch.setattr(main, "memory", Memory())
    monkeypatch.setattr(main, "manager", Broadcaster())
    monkeypatch.setattr(main, "event_bus", EventBus())
    monkeypatch.setattr(providers, "_active_state", {"provider": "", "model": ""})

    request = main.ProviderSwitchRequest(
        provider="mizan-hybrid", model=HYBRID_ENV["MIZAN_BASE_MODEL"]
    )
    result = asyncio.run(main.switch_provider(request))

    assert result["agents_updated"] == 1
    assert agent.ai_client is replacement
    assert agent.ai_model == HYBRID_ENV["MIZAN_BASE_MODEL"]
    assert preferences == {
        "active_provider": "mizan-hybrid",
        "active_model": HYBRID_ENV["MIZAN_BASE_MODEL"],
    }
    assert providers._active_state["provider"] == "mizan-hybrid"
