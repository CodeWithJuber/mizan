"""Production, 30 Oct 2026: every agent was switched to MIZAN's own Ruh model,
which returned one empty token, and the chat said only "The agent could not
complete this request". An empty answer now names its cause and the way back."""

import pytest

from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission


class Silent(BaseLLMProvider):
    def __init__(self, name):
        self.provider_name = name

    def create(self, **kwargs):
        return LLMResponse([ContentBlock(type="text", text="")], model=f"{self.provider_name}-m")


@pytest.mark.parametrize(
    ("provider", "code"), [("ruh", "own_model_not_ready"), ("openrouter", "empty_answer")]
)
async def test_an_empty_answer_names_its_cause(monkeypatch, tmp_path, provider, code):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = Silent(provider)
    result = await agent.execute("What is the largest moon of Saturn?")
    assert not result["success"] and result["error_code"] == code
    # Imported once DB_PATH points at a writable folder (CI has no /data).
    from api.main import chat_failure_payload

    payload = chat_failure_payload(result)
    assert payload["code"] == code
    if provider == "ruh":
        assert "Settings → Providers" in payload["message"]
