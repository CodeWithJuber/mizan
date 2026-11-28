"""Athar: replay of verified multi-step tool traces with no model call (ported
from ForgeKit's replay/engine.js and mathcore/sequential.js;
docs/automatic-learning.md)."""

import pytest

from agents.specialized import create_agent
from core.adaptive import AdaptiveStateStore, anytime_lower
from memory import stateless
from security.auth import TokenPayload, bind_principal, reset_principal
from security.izn import IznPermission
from tadbir import athar, itqan, khatimah

AMINA = TokenPayload("amina", "Amina", ["user"], 9999999999, 0, "amina-token")


@pytest.fixture
def store(tmp_path):
    return AdaptiveStateStore(str(tmp_path / "learning.db"))


def done(tool, **params):
    return {"tool": tool, "params": params, "outcome": "done", "receipt": "r" * 64}


PRICE = [
    done("web_search", query="gold price in Karachi"),
    done("http_get", url="https://example.com/gold?city=Karachi&grams=10"),
]


def price(city: str, grams: int):
    return [
        done("web_search", query=f"gold price in {city}"),
        done("http_get", url=f"https://example.com/gold?city={city}&grams={grams}"),
    ]


# ── the bar and the bound ────────────────────────────────────────────────


def test_the_cost_derived_bar():
    assert athar.threshold("read") == pytest.approx((4 + 0.02) / (4 + 1))
    assert athar.threshold("write") == pytest.approx((20 + 0.02) / (20 + 1))
    assert athar.threshold("irreversible") == float("inf")


def test_effects_follow_the_approval_categories():
    assert athar.effect("web_search") == "read"
    assert athar.effect("workspace_write", {"path": "a.py"}) == "write"
    assert athar.effect("workspace_run") == "write"
    assert athar.effect("http_post") == "irreversible"
    assert athar.effect("mcp__mail__send_message") == "irreversible"


def test_the_anytime_bound_needs_a_streak_and_drops_with_a_failure():
    assert anytime_lower(0, 0) == 0.0
    assert anytime_lower(15, 0) < athar.threshold("read") <= anytime_lower(16, 0)
    assert anytime_lower(16, 1) < anytime_lower(16, 0)
    assert all(anytime_lower(n, 0) <= anytime_lower(n + 1, 0) for n in range(30))


# ── reading a request against its family ────────────────────────────────


def test_one_request_seen_replays_only_itself(store):
    athar.learn(store, "Gold price in Karachi for 10 grams", PRICE, intent="web_search")
    (family,) = athar._load(store)
    steps, why = athar.plan(family, "Gold price in Karachi for 10 grams")
    assert why == "" and steps[1]["params"]["url"].endswith("grams=10")
    assert athar.plan(family, "Gold price in Lahore for 12 grams") == (
        None,
        "seen_too_rarely_to_generalise",
    )


def test_two_requests_bind_numbers_and_spans_of_the_persons_words(store):
    athar.learn(store, "Gold price in Karachi for 10 grams", price("Karachi", 10))
    athar.learn(store, "Gold price in Lahore for 12 grams", price("Lahore", 12))
    (family,) = athar._load(store)
    steps, why = athar.plan(family, "Gold price in Quetta for 7 grams")
    assert why == ""
    assert steps[0]["params"]["query"] == "gold price in Quetta"
    assert steps[1]["params"]["url"] == "https://example.com/gold?city=Quetta&grams=7"


def test_an_argument_with_no_known_source_is_never_guessed(store):
    athar.learn(store, "Gold price in Karachi for 10 grams", price("Karachi", 10))
    other = [done("web_search", query="today's rates"), done("http_get", url="https://x.test/a")]
    athar.learn(store, "Gold price in Lahore for 12 grams", other)
    (family,) = athar._load(store)
    assert athar.plan(family, "Gold price in Quetta for 7 grams") == (
        None,
        "argument_without_source",
    )


def test_a_constant_holding_a_word_this_request_does_not_say_is_not_used(store):
    # Both earlier requests named Karachi; their constant is Karachi's, not Quetta's.
    athar.learn(store, "Gold price in Karachi for 10 grams", price("Karachi", 10))
    athar.learn(store, "Gold price in Karachi for 12 grams", price("Karachi", 12))
    (family,) = athar._load(store)
    assert athar.plan(family, "Gold price in Quetta for 7 grams")[0] is None
    assert athar.plan(family, "Gold price in Karachi for 7 grams")[0] is not None


def test_another_form_with_the_same_tools_starts_its_own_family(store):
    athar.learn(store, "Gold price in Karachi for 10 grams", price("Karachi", 10))
    weather = [done("web_search", query="weather Lahore"), done("http_get", url="https://w")]
    athar.learn(store, "What is the weather like in Lahore tonight", weather)
    assert [len(f["examples"]) for f in athar._load(store)] == [1, 1]


def test_a_trace_holding_a_credential_is_never_kept(store):
    keyed = [done("http_get", url="https://api.test/x", headers={"Authorization": "Bearer z"})]
    assert athar.learn(store, "Fetch my api data", keyed) is None
    leaked = [done("http_get", url="https://api.test/x?key=sk-ant-" + "a" * 30)]
    assert athar.learn(store, "Fetch my api data", leaked) is None
    assert athar._load(store) == []


# ── evidence: test, then train ───────────────────────────────────────────


CITIES = ("Multan", "Sukkur", "Peshawar", "Hyderabad")


def teach(store, runs: int):
    athar.learn(store, "Gold price in Karachi for 10 grams", price("Karachi", 10))
    athar.learn(store, "Gold price in Lahore for 12 grams", price("Lahore", 12))
    for n in range(runs):
        city = CITIES[n % len(CITIES)]
        athar.learn(store, f"Gold price in {city} for {n + 1} grams", price(city, n + 1))


def test_each_verified_run_first_tests_the_prediction(store):
    teach(store, 3)
    (family,) = athar._load(store)
    assert (family["s"], family["f"]) == (3, 0)
    wrong = [done("web_search", query="gold price in Gilgit"), done("http_get", url="https://y")]
    athar.learn(store, "Gold price in Gilgit for 9 grams", wrong)
    assert athar._load(store)[0]["f"] == 1


def test_replay_waits_for_the_bound_to_clear_the_bar(store):
    teach(store, 13)  # 13 agreeing runs (the first two only taught the form)
    assert athar.decide(store, "Gold price in Quetta for 7 grams")["reason"] == (
        "not_enough_evidence"
    )
    teach(store, 1)  # three more agreeing runs: 16, the streak the read bar needs
    found = athar.decide(store, "Gold price in Quetta for 7 grams")
    assert found["replay"] and found["lower_bound"] >= found["threshold"]


def test_an_irreversible_step_stops_the_trace(store):
    send = lambda city, grams: [  # noqa: E731
        *price(city, grams),
        done("mcp__mail__send_message", to="me@example.com", body=f"{city} {grams}"),
    ]
    athar.learn(store, "Gold price in Karachi for 10 grams", send("Karachi", 10))
    athar.learn(store, "Gold price in Lahore for 12 grams", send("Lahore", 12))
    for n in range(30):
        city = CITIES[n % len(CITIES)]
        athar.learn(store, f"Gold price in {city} for {n + 1} grams", send(city, n + 1))
    found = athar.decide(store, "Gold price in Quetta for 7 grams")
    assert found["replay"] is False and found["reason"] == "irreversible_step"
    assert found["stops_at"] == 2


# ── a replay in a real run ───────────────────────────────────────────────


class CountingProvider:
    provider_name = "fixture"
    supports_tools = True

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):  # pragma: no cover - a replay never gets here
        self.calls += 1
        raise AssertionError("a replay makes no model call")


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    made = create_agent("general", izn=IznPermission())
    made.ai_client = CountingProvider()
    calls = []

    async def checked(name, params):
        calls.append((name, params))
        if "fail" in str(params):
            return {"error": "the page is gone"}
        return {"text": f"{name} answered {params}"}

    monkeypatch.setattr(made, "_execute_tool_checked", checked)
    made.tool_calls = calls
    return made


@pytest.fixture
def amina():
    token = bind_principal(AMINA)
    yield
    reset_principal(token)


async def test_a_repeated_request_is_replayed_with_no_model_call(agent, amina, monkeypatch):
    monkeypatch.setenv("MIZAN_REPLAY", "on")
    teach(khatimah.store("amina"), 16)
    result = await agent.execute("Gold price in Quetta for 7 grams", {"session_id": "w1"})
    assert result["orchestrator"] == "mizan" and result["replay"]["steps"] == 2
    assert result["completion_status"] == "evidence_observed" and not result["task_verified"]
    assert agent.ai_client.calls == 0
    assert [name for name, _ in agent.tool_calls] == ["web_search", "http_get"]
    assert agent.tool_calls[1][1]["url"] == "https://example.com/gold?city=Quetta&grams=7"
    # The replayed run is no new evidence about itself.
    assert athar._load(khatimah.store("amina"))[0]["s"] == 16


async def test_a_failed_step_drops_the_family_and_the_agent_runs(agent, amina, monkeypatch):
    monkeypatch.setenv("MIZAN_REPLAY", "on")
    store = khatimah.store("amina")
    teach(store, 16)
    family = athar._load(store)[0]
    (seen,) = family["examples"] = [
        {**e, "steps": [*e["steps"][:1], done("http_get", url="https://fail.test")]}
        for e in family["examples"][:1]
    ]
    store.put(athar.KEY, {"families": [family]})
    replayed = await athar.replay(agent, seen["request"])
    assert replayed is None and athar._load(store) == []
    assert [name for name, _ in agent.tool_calls] == ["web_search", "http_get"]


async def test_replay_off_and_stateless_runs_never_replay(agent, amina, monkeypatch):
    teach(khatimah.store("amina"), 16)
    monkeypatch.setenv("MIZAN_REPLAY", "off")
    assert await athar.replay(agent, "Gold price in Quetta for 7 grams") is None
    monkeypatch.setenv("MIZAN_REPLAY", "on")
    with stateless.bind():
        assert await athar.replay(agent, "Gold price in Quetta for 7 grams") is None
    assert agent.tool_calls == []


async def test_a_corrected_replay_drops_its_family(agent, amina, monkeypatch):
    monkeypatch.setenv("MIZAN_REPLAY", "on")
    store = khatimah.store("amina")
    teach(store, 16)
    await agent.execute("Gold price in Quetta for 7 grams", {"session_id": "w1"})
    khatimah.before_run("No, that's wrong, I asked for 24 karat", {"session_id": "w1"})
    assert athar._load(store) == []


# ── what a verified run teaches ──────────────────────────────────────────


async def test_a_verified_run_with_tools_is_learned_from_its_own_trace(agent, amina, monkeypatch):
    async def impl(task, context, *args):
        await agent._execute_tool_safe("web_search", {"query": "gold price in Karachi"})
        return {
            "success": True,
            "result": "Rs 250,000",
            "task_verified": True,
            "orchestration": {"intent": "web_search"},
        }

    monkeypatch.setattr(agent, "_execute_impl", impl)
    result = await agent.execute("Gold price in Karachi", {"session_id": "c1"})
    learned = result["usage"]["learned"]
    assert learned["athar"]["family"] and learned["itqan"]["verified_runs"] == 1
    (family,) = athar._load(khatimah.store("amina"))
    assert family["tools"] == ["web_search"] and family["intent"] == "web_search"
    with stateless.bind():
        await agent.execute("Gold price in Karachi", {"session_id": "c1"})
    assert len(athar._load(khatimah.store("amina"))[0]["examples"]) == 1
    assert itqan.summary(khatimah.store("amina"))["counting"] == 1


def test_mahw_takes_the_erased_chats_runs_out_of_every_family(store):
    athar.learn(store, "Gold price in Karachi for 10 grams", price("Karachi", 10), chat="secret")
    athar.learn(store, "Gold price in Lahore for 12 grams", price("Lahore", 12), chat="kept")
    assert athar.forget_chat(store, "secret") == 1
    (family,) = athar._load(store)
    assert [e["chat"] for e in family["examples"]] == ["kept"]
    assert (family["s"], family["f"]) == (0, 0)
