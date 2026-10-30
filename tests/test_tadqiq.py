"""Tadqiq: a blinded audit of the answers MIZAN gives without the teacher (docs/tadqiq.md)."""

import math
import random
import sqlite3
from copy import deepcopy

import httpx
import pytest

import runtime_settings as rs
from agents.specialized import create_agent
from memory import stateless
from memory.dhikr import DhikrMemorySystem
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from security.izn import IznPermission
from tadbir import ahl_dhikr, sijill, tadqiq


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse([ContentBlock(type="text", text=self.replies.pop(0))], model="fixture")


class Always:
    """A draw that always falls inside the sample."""

    def random(self):
        return 0.0


@pytest.fixture
def audits(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_TADQIQ", "on")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIZAN_AUDIT_RATE", raising=False)
    monkeypatch.setattr(tadqiq, "_set_by_admin", lambda: False)
    return tmp_path


def zero_call(answer="`17*25` = **425**", **extra):
    return {
        "success": True,
        "result": answer,
        "usage": {"lisan": {"zero_call": True, "family": "compute", "language": "en"}},
        **extra,
    }


def rows(path):
    with sqlite3.connect(path / "tadqiq.db") as conn:
        return conn.execute(
            "SELECT family, language, kind, outcome, probability FROM audits ORDER BY id"
        ).fetchall()


# ── which answers are audited ─────────────────────────────────────────────


def test_answers_are_drawn_at_the_configured_rate(audits, monkeypatch):
    monkeypatch.setattr(tadqiq, "_DRAW", random.Random(5))
    draws = 20_000
    drawn = [tadqiq.decide("What is 17 times 25?", zero_call()) for _ in range(draws)]
    hits = [p for p in drawn if p is not None]
    assert set(hits) == {0.03}  # the sampling probability is what is recorded
    expected, spread = draws * 0.03, math.sqrt(draws * 0.03 * 0.97)
    assert abs(len(hits) - expected) < 4 * spread


def test_the_rate_holds_to_the_approved_range_unless_an_administrator_saves_another(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rs, "_baseline", {})
    for value, expected in (("0.5", 0.05), ("0.001", 0.02), ("0.04", 0.04), ("many", 0.03)):
        monkeypatch.setenv("MIZAN_AUDIT_RATE", value)
        assert tadqiq.rate() == expected
    assert tadqiq.window(0.03) == 84  # two weeks of audits at 200 requests a day
    monkeypatch.setenv("MIZAN_AUDIT_RATE", "0.5")
    rs.update({"MIZAN_AUDIT_RATE": "0.5"}, "root")
    assert tadqiq.rate() == 0.5 and tadqiq._set_by_admin()
    rs.update({"MIZAN_AUDIT_RATE": None}, "root")
    assert tadqiq.rate() == 0.05


def test_never_for_evaluations_learning_off_model_answers_or_delegated_runs(audits, monkeypatch):
    monkeypatch.setattr(tadqiq, "_DRAW", Always())
    question = "What is 17 times 25?"
    assert tadqiq.decide(question, zero_call()) == 0.03
    with stateless.bind():
        assert tadqiq.decide(question, zero_call()) is None
    with stateless.no_learning("learning: off"):
        assert tadqiq.decide(question, zero_call()) is None
    model_answer = zero_call()
    model_answer["usage"]["lisan"]["zero_call"] = False
    assert tadqiq.decide(question, model_answer) is None
    assert tadqiq.decide(question, zero_call(), nested=True) is None
    assert tadqiq.decide(question, zero_call(amanah={"ignored": 1})) is None
    monkeypatch.setenv("MIZAN_TADQIQ", "off")
    assert tadqiq.decide(question, zero_call()) is None


async def test_a_question_about_the_deen_is_never_sent_to_the_teacher(audits):
    teacher = ScriptedProvider(["It depends on the scholar you ask."])
    for question, answer in (
        ("Is music haram?", "Scholars differ on music."),
        ("Why is patience praised?", "Allah is with the patient (Quran 2:153)."),
    ):
        outcome = await tadqiq.audit(
            question, answer, teacher, "m", family="converse", language="en", probability=0.03
        )
        assert outcome is None
    assert teacher.requests == []
    assert not (audits / "tadqiq.db").exists() or rows(audits) == []


# ── comparing ────────────────────────────────────────────────────────────


async def test_printed_numbers_agree_or_disagree_by_tathabbut():
    program = "**Code**\n```python\nprint(fib(30))\n```\n\nRan in 12 ms.\n\n**Output**\n```text\n832040\n```"
    request = "Print the 30th Fibonacci number, where F1 = 1 and F2 = 1."
    assert await tadqiq.compare(request, program, "The 30th Fibonacci number is 832,040.") == (
        "numbers",
        "agree",
    )
    assert await tadqiq.compare(request, program, "F30 = 514229") == ("numbers", "disagree")
    # The teacher wrote a program instead of a result: nothing to compare.
    teacher_code = "```python\nprint(30)\n```"
    assert await tadqiq.compare(request, program, teacher_code) == ("numbers", "unsettled")
    # An answer that is a number, not a sentence; the request's own numbers are set aside.
    computed = "`17*25` = **425**\n\n_Computed exactly by MIZAN_"
    assert await tadqiq.compare("What is 17 times 25?", computed, "17 × 25 = 425") == (
        "numbers",
        "agree",
    )
    assert await tadqiq.compare("What is 17 times 25?", computed, "It is 435.") == (
        "numbers",
        "disagree",
    )


async def fake_nli(pairs):
    """Entailment when both name the same moon, contradiction when they name
    different ones, neither otherwise."""
    readings = []
    for premise, hypothesis in pairs:
        said = {moon for moon in ("Titan", "Rhea") if moon in premise}
        claimed = {moon for moon in ("Titan", "Rhea") if moon in hypothesis}
        if said and claimed and said == claimed:
            readings.append({"entailment": 0.97, "neutral": 0.02, "contradiction": 0.01})
        elif said and claimed:
            readings.append({"entailment": 0.01, "neutral": 0.04, "contradiction": 0.95})
        else:
            readings.append({"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05})
    return readings


async def test_words_agree_or_disagree_by_the_nli_model_both_ways(monkeypatch):
    monkeypatch.setattr(ahl_dhikr, "nli", fake_nli)
    question = "What is the largest moon of Saturn?"
    answer = (
        "The largest moon of Saturn is Titan.\n\n"
        "_Answered from what the teacher taught on 2026-10-30, with no language-model call_"
    )
    assert await tadqiq.compare(question, answer, "Titan is the largest moon of Saturn.") == (
        "text",
        "agree",
    )
    assert await tadqiq.compare(question, answer, "Saturn's largest moon is Rhea.") == (
        "text",
        "disagree",
    )
    # A reply about something else is no evidence either way (ahl_dhikr.about).
    unrelated = "I cannot browse the internet right now, sorry about that."
    assert await tadqiq.compare(question, answer, unrelated) == ("text", "unsettled")


async def test_without_the_nli_model_nothing_is_settled(monkeypatch):
    async def missing(pairs):
        return None

    monkeypatch.setattr(ahl_dhikr, "nli", missing)
    answer = "The largest moon of Saturn is Titan."
    assert await tadqiq.compare("Largest moon of Saturn?", answer, answer) == (
        "text",
        "unsettled",
    )


# ── in a chat ─────────────────────────────────────────────────────────────


@pytest.fixture
def agent(monkeypatch, audits):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(audits / "memory.db"))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    created = create_agent(
        "general", izn=IznPermission(), memory=DhikrMemorySystem(str(audits / "a.db"))
    )
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": "workspace_run", "description": "", "input_schema": {"type": "object"}}],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
    return created


@pytest.fixture
def alice():
    token = bind_principal(TokenPayload("alice", "alice", ["user"], 9999999999, 0, "t"))
    yield "alice"
    reset_principal(token)


PROGRAM = "```python\nprint(sum(range(1, 11)))\n```"
CHECK = "```python\nprint(10 * 11 // 2)\n```"
REQUEST = "Ek python program likho jo 1 se 10 tak ka sum print kare aur run karo"


async def test_a_zero_call_answer_is_audited_afterwards_blinded(agent, audits, monkeypatch, alice):
    async def run(name, params):
        return {"stdout": "55\n", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    monkeypatch.setattr(tadqiq, "_DRAW", Always())
    agent.ai_client = ScriptedProvider([PROGRAM, CHECK])
    first = await agent.execute(REQUEST)
    await tadqiq.drain()
    assert first["usage"]["lisan"]["calls"] == 2  # the teacher answered: nothing to audit
    assert len(agent.ai_client.requests) == 2

    agent.ai_client = teacher = ScriptedProvider(["Jawab 55 hai."])
    again = await agent.execute(REQUEST)
    assert again["usage"]["lisan"]["zero_call"] is True  # the audit is not the answer's call
    await tadqiq.drain()
    (asked,) = teacher.requests
    # Blinded: the teacher is given the request alone, never MIZAN's answer.
    assert asked["messages"] == [{"role": "user", "content": REQUEST}]
    assert "55" not in asked["system"] and "Output" not in str(asked)
    ((family, _language, kind, outcome, probability),) = rows(audits)
    assert (kind, outcome, probability) == ("numbers", "agree", 0.03)
    assert family == again["usage"]["lisan"]["family"]
    # Kept with no content: neither the request nor either answer.
    raw = (audits / "tadqiq.db").read_bytes()
    assert b"python program" not in raw and b"Jawab" not in raw


async def test_a_spent_budget_refuses_the_audit_before_it_is_sent(audits, monkeypatch, alice):
    from api import iqtisad, prices
    from providers import _admit

    sent = []

    class Metered(ScriptedProvider):
        def create(self, **kwargs):
            ticket = _admit(kwargs["model"], kwargs["max_tokens"], kwargs["messages"])
            sent.append(kwargs)
            ticket.settle({"input": 10, "output": 10})
            return super().create(**kwargs)

    monkeypatch.setenv("MIZAN_BUDGET_DAILY_USD", "0.0001")
    monkeypatch.setattr(prices, "lookup", lambda model: (4.0, 20.0))
    iqtisad._LEDGERS.clear()
    outcome = await tadqiq.audit(
        "What is the largest moon of Saturn?",
        "The largest moon of Saturn is Titan.",
        Metered(["Titan."]),
        "teacher-model",
        family="fact",
        language="en",
        probability=0.03,
    )
    assert outcome == "refused" and sent == []
    assert rows(audits) == [("fact", "en", "none", "refused", 0.03)]
    family = tadqiq.report()["families"][0]
    assert family["refused"] == 1 and family["spend_usd"] == 0 and family["settled"] == 0


# ── the monitor ───────────────────────────────────────────────────────────


def test_the_monitor_parameters_follow_from_the_target():
    p1, up, down, h = tadqiq.design(0.10, 84)
    assert math.isclose(p1, 0.20)
    assert math.isclose(up, math.log(2)) and math.isclose(down, math.log(0.8 / 0.9))
    # H - 1 + e^-H = 84 · KL(0.2 || 0.1), then half a disagreement's step back.
    information = 84 * (0.2 * math.log(2) + 0.8 * math.log(0.8 / 0.9))
    level = h + up / 2
    assert math.isclose(level - 1 + math.exp(-level), information, rel_tol=1e-9)
    assert round(h, 2) == 4.37
    # Never less evidence than 1/α, however high the baseline.
    assert tadqiq.design(0.45, 84)[3] == pytest.approx(math.log(20))


def _stream(rate, shift_at, length, audits, rng):
    """Feed one simulated family; the audit index of its first alarm, or None."""
    state = tadqiq.fresh()
    for index in range(length):
        disagreed = rng.random() < rate + (
            0.10 if shift_at is not None and index >= shift_at else 0
        )
        if tadqiq.observe(state, disagreed, audits):
            return index
    return None


def test_by_simulation_a_rise_is_found_in_about_two_weeks_and_a_steady_family_stays_quiet():
    audits, runs = 84, 150  # 3 % of 200 requests a day for 14 days
    rng = random.Random(2026)
    start = 2 * audits  # the baseline is learned first, behind a guard of one window
    year = audits * 365 // 14
    quiet = [_stream(0.02, None, start + year, audits, rng) for _ in range(runs)]
    assert sum(alarm is not None for alarm in quiet) / runs <= 0.05
    shift_at = start + audits  # the rise comes after two weeks of watching
    early, delays = 0, []
    for _ in range(runs):
        alarm = _stream(0.02, shift_at, shift_at + 6 * audits, audits, rng)
        if alarm is not None and alarm < shift_at:
            early += 1  # a false alarm before the change
            continue
        delays.append(6 * audits if alarm is None else alarm - shift_at)
    assert early / runs <= 0.05
    assert sum(delay < 6 * audits for delay in delays) / len(delays) >= 0.95
    assert sum(delays) / len(delays) <= 1.25 * audits  # about two weeks on average


def test_an_alarm_is_noted_for_administrators_in_no_ones_chat(audits, monkeypatch):
    from workspace.context import bind_chat_session, reset_chat_session

    monkeypatch.setattr(tadqiq, "window", lambda probability=None: 10)
    sijill.clear(sijill.ADMINS)
    token = bind_chat_session("someones-chat")
    try:
        for _ in range(20):  # the baseline: ten in the guard, ten behind it
            assert not tadqiq.record("compute", "en", "numbers", "agree", 0.03)
        raised = [tadqiq.record("compute", "en", "numbers", "disagree", 0.03) for _ in range(6)]
    finally:
        reset_chat_session(token)
    assert raised.count(True) == 1  # noted once, when it crosses
    (note,) = sijill.since(sijill.ADMINS)
    assert note["kind"] == "tadqiq" and note["chat"] == "" and "compute" in note["summary"]
    monitor = tadqiq.report()["families"][0]["monitor"]
    assert monitor["status"] == "watching" and monitor["alarm"] and monitor["alarms"] == 1
    assert monitor["statistic"] >= monitor["threshold"]


# ── the endpoint ──────────────────────────────────────────────────────────


async def test_the_report_is_for_administrators_only(audits, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    from api import main

    tadqiq.record("compute", "en", "numbers", "agree", 0.03, 0.002, 1)
    tadqiq.record("compute", "ur", "numbers", "disagree", 0.03, 0.003, 1)
    tadqiq.record("fact", "en", "text", "unsettled", 0.05, None, 1)
    sijill.clear(sijill.ADMINS)
    sijill.note("tadqiq", {"detail": "Audit alarm: test"}, sijill.ADMINS)
    owner = main.auth.create_user("tadqiq-owner", "pw", roles=["admin"])
    person = main.auth.create_user("tadqiq-person", "pw", roles=["user"])
    as_owner = {"Authorization": f"Bearer {main.auth.create_token(owner)}"}
    as_person = {"Authorization": f"Bearer {main.auth.create_token(person)}"}
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/tadbir/audit")).status_code == 401
        assert (await client.get("/api/tadbir/audit", headers=as_person)).status_code == 403
        shown = await client.get("/api/tadbir/audit?days=7", headers=as_owner)
        assert shown.status_code == 200, shown.text
        body = shown.json()
        compute = next(item for item in body["families"] if item["family"] == "compute")
        assert (compute["audited"], compute["settled"], compute["disagreements"]) == (2, 2, 1)
        assert compute["interval"][0] < 0.5 < compute["interval"][1]
        assert compute["spend_usd"] == pytest.approx(0.005)
        assert compute["answers_represented"] == pytest.approx(2 / 0.03, abs=0.1)
        assert compute["monitor"]["status"] == "learning the baseline"
        assert body["rate"] == 0.03 and body["design"]["window_audits"] == 84
        # The alarm note reaches administrators' live learning record, not a person's.
        live = await client.get("/api/tadbir/learning/live", headers=as_owner)
        assert any(note["kind"] == "tadqiq" for note in live.json()["notes"])
        theirs = await client.get("/api/tadbir/learning/live", headers=as_person)
        assert not any(note["kind"] == "tadqiq" for note in theirs.json()["notes"])
