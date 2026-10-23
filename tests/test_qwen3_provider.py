"""Tests for the Qwen3 provider registration (Qwen3 = generation in chat)."""

import pytest

from api.qwen3_client import Qwen3Result, Qwen3Unavailable
from providers import (
    Qwen3ServerlessProvider,
    create_provider,
    get_default_model,
    get_provider_status,
)


@pytest.fixture
def qwen3_env(monkeypatch):
    monkeypatch.setenv("QWEN3_ENABLED", "1")
    monkeypatch.setenv("QWEN3_ENDPOINT_URL", "https://qwen3-test.runpod.net")
    monkeypatch.setenv("QWEN3_API_KEY", "test-key-123")
    monkeypatch.setenv("QWEN3_BACKOFF_BASE", "0")
    monkeypatch.delenv("QWEN3_MODEL", raising=False)
    # get_default_model() honors a global DEFAULT_MODEL override (e.g. from
    # a repo-root .env that other tests can create via the doctor fix);
    # clear it so the per-provider default assertions stay hermetic.
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)


class TestCreateProvider:
    def test_none_when_disabled(self, monkeypatch):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        assert create_provider(provider="qwen3", model="qwen3-0.6b-quran") is None

    def test_none_when_unconfigured(self, monkeypatch):
        monkeypatch.setenv("QWEN3_ENABLED", "1")
        monkeypatch.delenv("QWEN3_ENDPOINT_URL", raising=False)
        assert create_provider(provider="qwen3", model="qwen3-0.6b-quran") is None

    def test_returns_provider_when_enabled(self, qwen3_env):
        provider = create_provider(provider="qwen3", model="qwen3-0.6b-quran")
        assert isinstance(provider, Qwen3ServerlessProvider)
        assert provider.provider_name == "qwen3"

    def test_explicit_only_no_model_autodetect_hijack(self, qwen3_env, monkeypatch):
        # A bare "qwen3:8b" ollama model name must NOT route here implicitly.
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        # Sandbox no_proxy carries wildcard-IPv6 entries that crash httpx2's
        # URL parser (see AGENTS.md); OllamaProvider's constructor parses them.
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        provider = create_provider(provider=None, model="qwen3:8b")
        assert not isinstance(provider, Qwen3ServerlessProvider)


class TestProviderCreate:
    def test_create_returns_llm_response(self, qwen3_env, monkeypatch):
        def fake_generate_sync(self, messages, **opts):
            assert opts["system"] == "sys"
            assert messages == [{"role": "user", "content": "hi"}]
            return Qwen3Result(text="salam", model="qwen3-0.6b-quran", usage={"t": 1}, raw={})

        monkeypatch.setattr("api.qwen3_client.Qwen3Client.generate_sync", fake_generate_sync)
        provider = create_provider(provider="qwen3", model="qwen3-0.6b-quran")
        resp = provider.create(
            model="qwen3-0.6b-quran",
            max_tokens=64,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert resp.content[0].type == "text"
        assert resp.content[0].text == "salam"
        assert resp.model == "qwen3-0.6b-quran"
        assert resp.stop_reason == "end_turn"

    def test_create_unavailable_raises(self, qwen3_env, monkeypatch):
        def fake_generate_sync(self, messages, **opts):
            raise Qwen3Unavailable("qwen3_exhausted", "down")

        monkeypatch.setattr("api.qwen3_client.Qwen3Client.generate_sync", fake_generate_sync)
        provider = create_provider(provider="qwen3", model="qwen3-0.6b-quran")
        with pytest.raises(RuntimeError, match="qwen3 unavailable"):
            provider.create(
                model="qwen3-0.6b-quran",
                max_tokens=64,
                system="",
                messages=[{"role": "user", "content": "hi"}],
            )


class TestProviderRegistry:
    def test_status_lists_qwen3(self, qwen3_env):
        status = get_provider_status()
        entry = next(p for p in status["providers"] if p["name"] == "qwen3")
        assert entry["configured"] is True
        assert entry["default_model"] == "qwen3-0.6b-quran"

    def test_status_unconfigured_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        status = get_provider_status()
        entry = next(p for p in status["providers"] if p["name"] == "qwen3")
        assert entry["configured"] is False

    def test_default_model(self, qwen3_env):
        assert get_default_model("qwen3") == "qwen3-0.6b-quran"
