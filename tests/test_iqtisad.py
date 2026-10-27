"""Iqtisad: hard per-user spending limits on paid model calls."""

import json
import math
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from api import iqtisad
from api.iqtisad import BudgetExhausted
from security.auth import TokenPayload, bind_principal, reset_principal
from tadbir import waqt

PRICE = "test-model:10/40"  # $10 per 1M input tokens, $40 per 1M output tokens


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_PRICE_OVERRIDES", PRICE)
    for name in ("MIZAN_BUDGET_DAILY_USD", "MIZAN_BUDGET_MONTHLY_USD", "MIZAN_BUDGET_UNPRICED"):
        monkeypatch.delenv(name, raising=False)
    iqtisad._LEDGERS.clear()
    iqtisad._INFLIGHT.clear()
    return iqtisad.ledger()


@pytest.fixture
def as_user():
    bindings = []

    def bind(user_id="alice", roles=("user",)):
        bindings.append(bind_principal(TokenPayload(user_id, user_id, list(roles), 0, 0, "t")))

    yield bind
    for binding in reversed(bindings):
        reset_principal(binding)


def spend_all(ticket, input_bytes):
    """The worst case a provider can bill: one token per input byte and every
    output token it was allowed."""
    ticket.settle({"input": input_bytes, "output": ticket.max_tokens})


def test_with_no_limit_calls_pass_and_are_recorded(ledger, as_user):
    as_user()
    ticket = iqtisad.admit("test-model", 4000, ("system", [{"role": "user", "content": "hi"}]))
    assert ticket.max_tokens == 4000 and ticket.reserved == 0
    ticket.settle({"input": 10, "output": 100})
    summary = iqtisad.summary("alice", admin=False)
    assert summary["spent_usd"]["day"] == pytest.approx((10 * 10 + 100 * 40) / 1e6)
    assert summary["limits_usd"] == {"day": None, "month": None}


def test_no_sequence_of_calls_can_overspend_the_limit(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0.05")
    as_user()
    request = ("You are helpful.", [{"role": "user", "content": "x" * 400}])
    size = iqtisad._size(request)[0]
    refused = 0
    for _ in range(40):
        try:
            ticket = iqtisad.admit("test-model", 2000, request)
        except BudgetExhausted as exc:
            refused += 1
            assert exc.period == "day" and exc.limit == 0.05
            continue
        spend_all(ticket, size)
    spent = iqtisad.summary("alice", admin=False)["spent_usd"]["day"]
    assert refused > 0
    assert spent <= 0.05 + 1e-9  # never above the limit, even billed at the worst case


def test_the_answer_length_is_capped_to_what_is_left(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0.01")
    as_user()
    ticket = iqtisad.admit("test-model", 100_000, ("s", [{"role": "user", "content": "hi"}]))
    # $0.01 at $40/1M output buys at most 250 output tokens (less the input).
    assert 0 < ticket.max_tokens < 250
    assert ticket.reserved <= 0.01


def test_parallel_calls_cannot_spend_the_same_money(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0.01")
    as_user()
    request = ("s", [{"role": "user", "content": "hi"}])
    first = iqtisad.admit("test-model", 100_000, request)
    with pytest.raises(BudgetExhausted):
        iqtisad.admit("test-model", 100_000, request)  # the first holds the rest
    first.release()  # rejected upstream: nothing charged, money free again
    assert iqtisad.admit("test-model", 100_000, request).max_tokens > 0


def test_a_call_that_cannot_give_a_useful_answer_is_refused(ledger, as_user, monkeypatch):
    as_user()
    for _ in range(5):  # this model's answers are about 500 tokens
        iqtisad.admit("test-model", 4000, "s").settle({"input": 5, "output": 500})
    spent = iqtisad.summary("alice", admin=False)["spent_usd"]["day"]
    # Leave room for about 100 output tokens: far below the usual answer.
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", str(spent + 100 * 40 / 1e6))
    with pytest.raises(BudgetExhausted):
        iqtisad.admit("test-model", 4000, "s")


def test_an_unpriced_model_is_refused_while_a_limit_applies(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "1")
    as_user()
    with pytest.raises(BudgetExhausted) as caught:
        iqtisad.admit("mystery/model-x", 1000, "s")
    assert caught.value.reason == "unpriced"
    monkeypatch.setenv("MIZAN_BUDGET_UNPRICED", "allow")
    assert iqtisad.admit("mystery/model-x", 1000, "s").max_tokens == 1000


def test_own_limits_only_lower_the_budget(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "5")
    ledger.set_limits("alice", "self", 10, None)
    assert iqtisad.effective_limits("alice", admin=False)["day"] == 5
    ledger.set_limits("alice", "self", 1, None)
    assert iqtisad.effective_limits("alice", admin=False)["day"] == 1


def test_administrators_are_limited_only_when_someone_sets_a_limit(ledger, monkeypatch):
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "5")
    assert iqtisad.effective_limits("root", admin=True)["day"] is None
    ledger.set_limits("root", "admin", 2, None)
    assert iqtisad.effective_limits("root", admin=True)["day"] == 2
    ledger.set_limits("bob", "admin", 50, None)  # an admin may raise a user's limit
    assert iqtisad.effective_limits("bob", admin=False)["day"] == 50


def test_the_day_is_the_users_own(ledger, as_user):
    as_user()
    with waqt.bind_timezone("Pacific/Kiritimati"):  # UTC+14: already tomorrow for most
        day, _, renews = iqtisad.periods("alice")
        iqtisad.admit("test-model", 10, "s").settle({"input": 1, "output": 1})
    row = ledger.history("alice", 3)[-1]
    assert row["day"] == day and renews["day"].endswith("+14:00")
    assert ledger.zone("alice") == "Pacific/Kiritimati"  # remembered for unattended runs


def test_a_cut_off_call_is_charged_at_its_bound(ledger, as_user):
    as_user()
    ticket = iqtisad.admit("test-model", 1000, "x" * 100)
    ticket.settle(None, streamed_bytes=40)  # no usage record ever arrived
    spent = iqtisad.summary("alice", admin=False)["spent_usd"]["day"]
    assert spent == pytest.approx((ticket.input_bytes * 10 + 40 * 40) / 1e6)


# ── the providers admit and settle every paid call ─────────────────────


def anthropic_with(handler):
    from providers import AnthropicProvider

    provider = AnthropicProvider(api_key="test-placeholder")
    original = provider._client
    provider._client = original.with_options(
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
    )
    original.close()
    return provider


def test_anthropic_calls_are_capped_and_charged(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_PRICE_OVERRIDES", "claude-haiku-5-5:10/40")
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0.02")
    as_user()
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 20, "output_tokens": 30},
            },
        )

    provider = anthropic_with(respond)
    provider.create("claude-haiku-5-5", 64_000, "s", [{"role": "user", "content": "hi"}])
    assert sent[0]["max_tokens"] < 500  # $0.02 at $40/1M cannot buy 64,000 tokens
    spent = iqtisad.summary("alice", admin=False)["spent_usd"]["day"]
    assert spent == pytest.approx((20 * 10 + 30 * 40) / 1e6)


def test_an_exhausted_budget_never_reaches_the_provider(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_PRICE_OVERRIDES", "claude-haiku-5-5:10/40")
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0")
    as_user()
    sent = []
    provider = anthropic_with(lambda request: sent.append(request) or httpx2.Response(500))
    with pytest.raises(BudgetExhausted):
        provider.create("claude-haiku-5-5", 1000, "s", [{"role": "user", "content": "hi"}])
    assert sent == []


def test_a_rejected_request_is_not_charged(ledger, as_user, monkeypatch):
    monkeypatch.setenv("MIZAN_PRICE_OVERRIDES", "claude-haiku-5-5:10/40")
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "1")
    as_user()
    provider = anthropic_with(
        lambda request: httpx2.Response(
            529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
        )
    )
    with pytest.raises(anthropic.APIStatusError):
        provider.create("claude-haiku-5-5", 1000, "s", [{"role": "user", "content": "hi"}])
    assert iqtisad.summary("alice", admin=False)["spent_usd"]["day"] == 0
    assert iqtisad._INFLIGHT.get("alice", 0) == 0


def test_openai_compatible_calls_use_the_reported_cost(ledger, as_user, monkeypatch):
    from providers import OpenAICompatibleProvider

    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "1")
    as_user()
    provider = OpenAICompatibleProvider(api_key="test", provider_name="openai")
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            model="test-model",
            choices=[
                SimpleNamespace(
                    finish_reason="stop", message=SimpleNamespace(content="hi", tool_calls=None)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3, cost=0.0123),
        )

    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    provider.create("test-model", 900_000, "s", [{"role": "user", "content": "hi"}])
    assert seen["max_completion_tokens"] < 900_000
    assert iqtisad.summary("alice", admin=False)["spent_usd"]["day"] == pytest.approx(0.0123)


def test_a_broken_stream_is_charged_for_what_it_produced(ledger, as_user, monkeypatch):
    from providers import _AnthropicStreamWrapper

    monkeypatch.setenv("MIZAN_PRICE_OVERRIDES", "claude-haiku-5-5:10/40")
    as_user()
    snapshot = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=50, output_tokens=1),
        stop_reason=None,
        model="claude-haiku-5-5",
    )

    class Stream:
        current_message_snapshot = snapshot

        def __iter__(self):
            yield SimpleNamespace(
                type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="abcd")
            )
            raise ConnectionError("dropped")

    class Manager:
        def __enter__(self):
            return Stream()

        def __exit__(self, *args):
            return False

    wrapper = _AnthropicStreamWrapper(lambda request: Manager(), {"model": "claude-haiku-5-5"})
    wrapper.admit = lambda: iqtisad.admit("claude-haiku-5-5", 1000, "s")
    with pytest.raises(ConnectionError), wrapper as stream:
        for _ in stream.text_stream:
            pass
    spent = iqtisad.summary("alice", admin=False)["spent_usd"]["day"]
    # Input as reported (50); output never reported, so the 4 streamed bytes.
    assert spent == pytest.approx((50 * 10 + 4 * 40) / 1e6)


def test_the_budget_message_says_when_it_renews():
    from api.main import chat_failure_payload

    payload = chat_failure_payload(
        {
            "error_code": "budget_exhausted",
            "budget": {
                "period": "day",
                "limit_usd": 2.0,
                "spent_usd": 2.0,
                "resets_at": "2026-10-28T00:00:00+05:30",
                "reason": "limit",
            },
        }
    )
    assert payload["code"] == "budget_exhausted"
    assert "$2.00" in payload["message"] and "2026-10-28T00:00:00+05:30" in payload["message"]
    assert payload["budget"]["period"] == "day"


def test_live_catalog_prices_are_used(tmp_path, monkeypatch):
    from api import prices

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIZAN_PRICE_OVERRIDES", raising=False)
    monkeypatch.setattr(prices, "_LIVE", {})
    monkeypatch.setattr(prices, "_LIVE_LOADED", False)
    kept = prices.record_live(
        {
            "deepseek/deepseek-chat-v3-0324": ("0.0000003", "0.0000012"),
            "openrouter/auto": ("-1", "-1"),
        }
    )
    assert kept == 1
    rate_in, rate_out = prices.lookup("deepseek/deepseek-chat-v3-0324")
    assert math.isclose(rate_in, 0.3) and math.isclose(rate_out, 1.2)
    assert prices.lookup("openrouter/auto") is None
    monkeypatch.setattr(prices, "_LIVE", {})
    monkeypatch.setattr(prices, "_LIVE_LOADED", False)  # a restart reads the saved copy
    assert prices.lookup("deepseek/deepseek-chat-v3-0324") is not None


@pytest.fixture
def spending_api(tmp_path, monkeypatch, ledger):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from security.auth import MizanAuth

    auth = MizanAuth("iqtisad-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    alice = auth.create_user("alice", "test-password", roles=["user"])
    root = auth.create_user("root", "test-password", roles=["admin"])
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "3")

    def headers(user):
        return {"Authorization": "Bearer " + auth.create_token(user)}

    return TestClient(main.app), alice, headers(alice), root, headers(root)


def test_users_see_and_lower_their_own_budget(spending_api):
    client, alice, alice_headers, _, _ = spending_api
    summary = client.get("/api/iqtisad", headers=alice_headers).json()
    assert summary["limits_usd"]["day"] == 3 and summary["spent_usd"]["day"] == 0
    lowered = client.put(
        "/api/iqtisad/limits", json={"daily_usd": 1.5, "monthly_usd": None}, headers=alice_headers
    ).json()
    assert lowered["limits_usd"]["day"] == 1.5 and lowered["own_limits_usd"]["day"] == 1.5
    raised = client.put(
        "/api/iqtisad/limits", json={"daily_usd": 50, "monthly_usd": None}, headers=alice_headers
    ).json()
    assert raised["limits_usd"]["day"] == 3  # the server's limit still applies
    assert client.get("/api/iqtisad/all", headers=alice_headers).status_code == 403
    assert (
        client.put(
            f"/api/iqtisad/limits/{alice.id}", json={"daily_usd": 9}, headers=alice_headers
        ).status_code
        == 403
    )


def test_administrators_set_limits_for_users(spending_api):
    client, alice, alice_headers, _, root_headers = spending_api
    response = client.put(
        f"/api/iqtisad/limits/{alice.id}", json={"daily_usd": 0.5}, headers=root_headers
    )
    assert response.status_code == 200
    assert client.get("/api/iqtisad", headers=alice_headers).json()["limits_usd"]["day"] == 0.5
    assert (
        client.put(
            "/api/iqtisad/limits/no-such-user", json={"daily_usd": 1}, headers=root_headers
        ).status_code
        == 404
    )
    assert client.get("/api/iqtisad/all", headers=root_headers).status_code == 200


async def test_an_exhausted_budget_ends_the_run_with_its_own_code(ledger, monkeypatch):
    from unittest.mock import MagicMock

    from agents.specialized import create_agent

    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0")
    binding = bind_principal(TokenPayload("alice", "alice", ["user"], 0, 0, "t"))
    agent = create_agent("general", name="Budgeted", wali=MagicMock(), izn=MagicMock())

    class Provider:
        provider_name = "anthropic"

        def create(self, **kwargs):
            iqtisad.admit("test-model", kwargs["max_tokens"], "s")

        def stream(self, **kwargs):
            iqtisad.admit("test-model", kwargs["max_tokens"], "s")

    agent.ai_client = Provider()
    agent.ai_model = "test-model"
    try:
        result = await agent.execute("Tell me a story about patience")
    finally:
        reset_principal(binding)
    assert result["success"] is False and result["error_code"] == "budget_exhausted"
    assert result["budget"]["period"] == "day"
