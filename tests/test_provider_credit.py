"""A provider that is out of credit (HTTP 402) is named as such, and asked once
more within what the account can still pay for."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.provider_limits import ProviderLimits
from agents.specialized import create_agent
from providers import BaseLLMProvider, _OpenAIStreamWrapper, affordable_tokens
from tests.test_chat_provider_deadlines import SlowChunks, chunk


class OutOfCredit(Exception):
    status_code = 402


AFFORDABLE = OutOfCredit(
    "Error code: 402 - This request requires more credits, or fewer max_tokens. You requested "
    "up to 32000 tokens, but can only afford 1570."
)
IN_FLIGHT = OutOfCredit(
    "Error code: 402 - This request would exceed your available credits given your current "
    "in-flight requests."
)


def test_the_affordable_limit_is_read_from_the_refusal():
    assert affordable_tokens(AFFORDABLE) == 1570
    assert affordable_tokens(IN_FLIGHT) is None
    assert affordable_tokens(RuntimeError("can only afford 1570")) is None  # not a 402


class Fixture(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, refusal):
        self.refusal, self.limits = refusal, []
        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self.post))
        )

    def post(self, **kwargs):
        self.limits.append(kwargs["max_tokens"])
        if len(self.limits) == 1:
            raise self.refusal
        return SlowChunks([chunk(content="Salaam."), chunk(finish="stop")], delay=0)

    def stream(self, **kwargs):
        return _OpenAIStreamWrapper(self.client, "fixture-model", 32000, [])

    def create(self, **kwargs):
        raise AssertionError("not used")


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    monkeypatch.setattr("agents.base.provider_limits", lambda: ProviderLimits(5, 5, 10))
    result = create_agent("general")
    result.ai_model = "fixture-model"
    return result


async def test_a_402_with_an_affordable_limit_is_asked_once_more_within_it(agent):
    provider = Fixture(AFFORDABLE)
    agent.ai_client = provider
    result = await agent.execute("salaam", stream_callback=AsyncMock())
    assert result["success"] and "Salaam." in result["result"]
    assert provider.limits == [32000, 1570]


async def test_a_402_with_nothing_affordable_says_the_account_is_out_of_credit(agent):
    provider = Fixture(IN_FLIGHT)
    agent.ai_client = provider
    result = await agent.execute("salaam", stream_callback=AsyncMock())
    assert not result["success"] and result["error_code"] == "provider_credit"
    assert provider.limits == [32000]  # never resent without a limit it can pay for
