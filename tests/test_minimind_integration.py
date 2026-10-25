"""Worker-contract and routing regressions; no paid endpoint calls."""

import asyncio
import json
from unittest.mock import patch

import pytest

import providers
from agents.base import BaseAgent
from mizan_hybrid.config import HybridConfig
from mizan_hybrid.provider import MizanHybridProvider
from providers_minimind import CHECKPOINT_SHA256, MODEL_ID, MiniMindRemoteProvider


def worker_output(finish="eos", text="sample worker output"):
    return {
        "status": "COMPLETED",
        "output": {
            "response": text,
            "model": {"name": "mizan-minimind-full-sft", "checkpoint_sha256": CHECKPOINT_SHA256},
            "usage": {"prompt_tokens": 19, "completion_tokens": 4},
            "finish_reason": finish,
        },
    }


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.data).encode()


def test_bare_worker_contract_survives_queue_poll_and_stream(monkeypatch):
    requests = []
    responses = iter([{"status": "IN_QUEUE", "id": "job-1"}, worker_output()])

    def open_url(req, **kwargs):
        requests.append(req)
        return Response(next(responses))

    monkeypatch.setattr("urllib.request.urlopen", open_url)
    provider = MiniMindRemoteProvider("test-endpoint", "test-key")
    with provider.stream(
        MODEL_ID,
        4096,
        "Keep answers short",
        [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        temperature=0,
    ) as stream:
        assert list(stream.text_stream) == ["sample worker output"]
        result = stream.get_final_response()
    payload = json.loads(requests[0].data)["input"]
    assert requests[0].full_url.endswith("/run")
    assert json.loads(requests[0].data)["policy"] == {
        "executionTimeout": 60000,
        "ttl": 120000,
    }
    assert payload["max_new_tokens"] == 256
    assert "max_tokens" not in payload
    assert payload["do_sample"] is False
    assert payload["messages"][0]["content"] == "Keep answers short"
    assert requests[1].full_url.endswith("/status/job-1")
    assert result.model == MODEL_ID
    assert result.stop_reason == "end_turn"
    assert result.usage["input_tokens"] == 19


def test_expired_job_status_is_not_retried_for_five_minutes(monkeypatch):
    import urllib.error

    def expired(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.runpod.ai/status/job", 404, "expired", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", expired)
    with pytest.raises(ValueError, match="HTTP 404"):
        MiniMindRemoteProvider("endpoint", "test-key")._poll_until_done("job", {})


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "TIMED_OUT"])
@pytest.mark.parametrize("queued", [True, False])
def test_terminal_job_states_stop_immediately(monkeypatch, status, queued):
    replies = ([{"status": "IN_QUEUE", "id": "job-1"}] if queued else []) + [{"status": status}]
    responses = iter(replies)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(next(responses)))
    with pytest.raises(ValueError, match=status):
        MiniMindRemoteProvider("endpoint", "test-key").create(
            MODEL_ID, 16, "", [{"role": "user", "content": "hi"}]
        )


@pytest.mark.parametrize("change", ["wrong_hash", "missing_text", "wrong_finish"])
def test_malformed_or_wrong_checkpoint_is_rejected(change):
    output = worker_output()
    if change == "wrong_hash":
        output["output"]["model"]["checkpoint_sha256"] = "wrong"
    elif change == "missing_text":
        del output["output"]["response"]
    else:
        output["output"]["finish_reason"] = "unknown"
    with pytest.raises(ValueError):
        MiniMindRemoteProvider("endpoint", "test-key")._parse_output(output)


def test_text_history_preserved_and_unsupported_modalities_rejected():
    provider = MiniMindRemoteProvider("endpoint", "test-key")
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    assert provider._build_input(16, "", history, None, None)["messages"] == history
    with pytest.raises(ValueError, match="tool calling"):
        provider._build_input(16, "", history, [{"name": "search"}], None)
    with pytest.raises(ValueError, match="image"):
        provider._build_input(
            16, "", [{"role": "user", "content": [{"type": "image"}]}], None, None
        )
    with pytest.raises(ValueError, match="final user"):
        provider._build_input(16, "", history[:-1], None, None)


def test_provider_selection_status_and_api_accept_minimind(monkeypatch):
    monkeypatch.setenv("MINIMIND_ENDPOINT_ID", "endpoint")
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "mizan-minimind")
    monkeypatch.setenv("DEFAULT_MODEL", "stale-other-model")
    monkeypatch.setattr(providers, "_active_state", {"provider": "", "model": ""})
    provider = providers.create_provider("mizan-minimind")
    assert isinstance(provider, MiniMindRemoteProvider)
    status = providers.get_provider_status()
    assert status["default_model"] == MODEL_ID
    card = next(p for p in status["providers"] if p["name"] == "mizan-minimind")
    assert card["configured"] and card["models"][0]["context"] == 2048
    from api.main import ProviderSwitchRequest

    assert (
        ProviderSwitchRequest(provider="mizan-minimind", model=MODEL_ID).provider
        == "mizan-minimind"
    )


def test_hybrid_own_model_metadata_health_and_generation_cap(monkeypatch):
    monkeypatch.setenv("MIZAN_HYBRID_ENABLED", "true")
    monkeypatch.setenv("MIZAN_BASE_PROVIDER", "mizan-minimind")
    monkeypatch.setenv("MIZAN_BASE_MODEL", MODEL_ID)
    monkeypatch.delenv("MIZAN_BASE_REVISION", raising=False)
    monkeypatch.setenv("MINIMIND_ENDPOINT_ID", "endpoint")
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    cfg = HybridConfig.from_env()
    assert cfg.configured and cfg.context_window == 2048
    assert cfg.base_revision != "cdbee75f17c01a7cc42f958dc650907174af0554"
    base = MiniMindRemoteProvider("endpoint", "test-key")
    with patch.object(base, "_run_job", return_value=worker_output("length")) as call:
        hybrid = MizanHybridProvider(base, cfg)
        result = hybrid.create(MODEL_ID, 4096, "", [{"role": "user", "content": "hi"}])
    assert call.call_count == 1  # cannot retry above the worker's hard output limit
    assert result.usage["mizan"]["gate"]["outcome"] == "RETRY"
    assert hybrid.supports_tools is False
    health = asyncio.run(providers.check_provider_health("mizan-hybrid"))
    assert health["probe"] == "configuration_only"


def test_agent_does_not_advertise_tools_to_text_only_checkpoint(monkeypatch):
    provider = MiniMindRemoteProvider("endpoint", "test-key")
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: provider)
    agent = BaseAgent(name="contract-test")
    assert agent.get_tool_schemas() == []
    system = asyncio.run(agent._build_system_prompt())
    assert "You have access to tools" not in system
    assert "You have no tool access" in system


def test_hybrid_model_listing_reads_current_configuration(monkeypatch):
    from api.main import list_provider_models

    monkeypatch.setenv("MIZAN_BASE_PROVIDER", "mizan-minimind")
    monkeypatch.setenv("MIZAN_BASE_MODEL", MODEL_ID)
    result = asyncio.run(list_provider_models("mizan-hybrid"))
    assert result["models"][0]["id"] == MODEL_ID
    assert result["models"][0]["context"] == 2048


def test_existing_ruh_openai_contract_still_parses(monkeypatch):
    from providers_ruh_remote import RuhRemoteProvider

    body = {
        "status": "COMPLETED",
        "output": {
            "choices": [{"message": {"content": "ruh result"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 8},
            "model": "ruh-local",
        },
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(body))
    result = RuhRemoteProvider("endpoint", "test-key").create(
        "ruh-remote", 8, "", [{"role": "user", "content": "test"}]
    )
    assert result.content[0].text == "ruh result" and result.stop_reason == "max_tokens"
