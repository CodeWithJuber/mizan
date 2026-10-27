"""MIZAN learns from its own verified outcomes without touching model weights.

Tajriba keeps verified repair lessons, Tajdid renews Lisan's instructions and
keeps a version only when it proves better, Wazn sends code work to the
cheapest ready model, and Furqan rejects wording that drops a tool's warning.
"""

import random
from copy import deepcopy

import httpx
import pytest

from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import tajdid, tajriba, wazn
from tadbir.engine import Tadbir
from tadbir.express import cautions, furqan
from tadbir.lisan import INSTRUCTIONS


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse([ContentBlock(type="text", text=self.replies.pop(0))], model="fixture")


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIZAN_LISAN_MODELS", raising=False)
    monkeypatch.delenv("MIZAN_HARNESS_EVOLUTION", raising=False)
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    created = create_agent("general", izn=IznPermission())
    created.ai_client = ScriptedProvider()
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": "workspace_run", "description": "", "input_schema": {"type": "object"}}],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
    return created


def sandbox(agent, monkeypatch, *runs):
    queue = list(runs)

    async def run(name, params):
        return queue.pop(0)

    monkeypatch.setattr(agent, "_execute_tool_safe", run)


FAILED = {"stdout": "", "stderr": "NameError: name 'fib' is not defined", "exit_code": 1}
PASSED = {"stdout": "[0, 1, 1, 2, 3]\n", "stderr": "", "exit_code": 0}
WRONG = "```python\nprint(fib(5))\n```"
RIGHT = "```python\nprint([0, 1, 1, 2, 3])\n```"
REQUEST = "Ek python program likho jo 5 fibonacci numbers print kare aur run karo"


def system_prompt(request: dict) -> str:
    return request["system"]


# ── Tajriba: verified repair lessons ────────────────────────────────────


def test_an_error_signature_keeps_the_kind_and_drops_the_users_names_and_values():
    error = "Traceback...\n  File \"/tmp/x.py\", line 3\nKeyError: 'salary_2026' at row 41"
    assert tajriba.signature(error) == "KeyError: <name> at row <n>"


async def test_a_verified_repair_becomes_a_lesson_for_the_next_similar_work(agent, monkeypatch):
    agent.ai_client = ScriptedProvider([WRONG, RIGHT, RIGHT])
    sandbox(agent, monkeypatch, FAILED, PASSED, PASSED)
    first = await agent.execute(REQUEST)
    assert first["task_verified"]
    store = agent.adaptive
    (lesson,) = tajriba.summary(store, "")["items"]
    assert lesson["signature"] == "NameError: name <name> is not defined"

    # The next request of the same kind is written with the verified lesson in view.
    second = await agent.execute(REQUEST.replace("5", "6"))
    assert second["task_verified"]
    prompt = agent.ai_client.requests[2]["messages"][0]["content"]
    assert "Lessons MIZAN verified" in prompt and "+print([0, 1, 1, 2, 3])" in prompt
    # It worked, so the lesson's usefulness rose above its prior.
    assert tajriba.summary(store, "")["items"][0]["usefulness"] > 2 / 3


def test_lessons_are_kept_per_user_and_can_be_forgotten(agent):
    store = agent.adaptive
    tajriba.learn(store, "amina", "build_and_run", "sum", "print(x)", FAILED["stderr"], "print(1)")
    assert tajriba.relevant(store, "amina", "build_and_run", "NameError fib") != []
    assert tajriba.relevant(store, "bilal", "build_and_run", "NameError fib") == []
    tajriba.forget(store, "amina")
    assert tajriba.summary(store, "amina")["lessons"] == 0


# ── Tajdid: instruction renewal with sequential incumbent replacement ───


class RewritingLisan:
    def __init__(self, reply):
        self.reply = reply

    async def ask(self, system, user, max_tokens=1500, **_):
        return self.reply


async def test_failures_lead_to_a_challenger_that_must_keep_the_contract(agent):
    for _ in range(tajdid.EVOLVE_AFTER):
        tajdid.record("write_code", "base", False, "NameError: name <name> is not defined")
    assert tajdid.wants_challenger("write_code")

    # A rewrite that drops the reply format or a placeholder is never tried.
    assert not await tajdid.evolve("write_code", INSTRUCTIONS["write_code"], RewritingLisan(
        "Write a {language} program. Define every name before use."
    ))  # fmt: skip
    for _ in range(tajdid.EVOLVE_AFTER):
        tajdid.record("write_code", "base", False, "NameError")
    better = (
        "Write one complete {language} program for the request; define every function before "
        "calling it. Standard library only, print the results, no input. Reply with exactly "
        "one fenced code block and nothing else."
    )
    assert await tajdid.evolve("write_code", INSTRUCTIONS["write_code"], RewritingLisan(better))
    (row,) = [r for r in tajdid.report() if r["task"] == "write_code"]
    assert row["challenger"]["text"] == better and row["challenger"]["trials"] == 0


def _challenge(task: str, text: str) -> str:
    state = tajdid._state(task)
    state["challenger"] = {"id": "c1", "text": text, "posterior": None, "trials": 0}
    tajdid._put(task, state)
    return "c1"


def test_a_challenger_replaces_the_incumbent_only_when_proven_better(agent):
    text = INSTRUCTIONS["write_code"] + " Define every name before use."
    variant = _challenge("write_code", text)
    for _ in range(tajdid.MIN_TRIALS - 1):
        tajdid.record("write_code", variant, True)
        tajdid.record("write_code", "base", False)
    # Not enough trials yet: no decision.
    assert tajdid._state("write_code")["incumbent"]["id"] == "base"
    for _ in range(4):
        tajdid.record("write_code", variant, True)
        tajdid.record("write_code", "base", False)
    state = tajdid._state("write_code")
    assert state["incumbent"]["id"] == variant and state["challenger"] is None
    assert state["history"][-1]["promoted"] == variant
    # Lisan now writes with the promoted instruction.
    assert tajdid.instruction("write_code", INSTRUCTIONS["write_code"]) == (variant, text)


def test_a_worse_challenger_is_retired_and_the_incumbent_stays(agent):
    variant = _challenge("fix_code", INSTRUCTIONS["fix_code"] + " Be brief.")
    for _ in range(20):
        tajdid.record("fix_code", variant, False)
        tajdid.record("fix_code", "base", True)
    state = tajdid._state("fix_code")
    assert state["incumbent"]["id"] == "base" and state["challenger"] is None
    assert state["history"][-1]["retired"] == variant


def test_renewal_can_be_switched_off(agent, monkeypatch):
    _challenge("write_code", INSTRUCTIONS["write_code"] + " Define names first.")
    monkeypatch.setenv("MIZAN_HARNESS_EVOLUTION", "off")
    rng = random.Random(0)
    picks = {tajdid.instruction("write_code", "x", rng)[0] for _ in range(30)}
    assert picks == {"base"}


async def test_the_engine_credits_the_instruction_version_with_the_sandbox_verdict(
    agent, monkeypatch
):
    agent.ai_client = ScriptedProvider([WRONG, RIGHT])
    sandbox(agent, monkeypatch, FAILED, PASSED)
    await agent.execute(REQUEST)
    rows = {row["task"]: row for row in tajdid.report()}
    assert rows["write_code"]["incumbent_trials"] == 1  # the first program failed
    assert rows["write_code"]["failures_since_renewal"] == 1
    assert rows["fix_code"]["incumbent_trials"] == 1  # the repair verified
    assert rows["fix_code"]["failures_since_renewal"] == 0


# ── Wazn: the cheapest ready model, a stronger one after a failure ─────


def test_a_failed_attempt_moves_one_step_to_a_stronger_model(agent, monkeypatch):
    monkeypatch.setenv("MIZAN_LISAN_MODELS", "small, medium, large")
    for _ in range(30):
        wazn.record("write_code", "small", True)
    rng = random.Random(3)
    assert wazn.choose("write_code", 0, "agent-model", rng) == "small"
    assert wazn.choose("write_code", 1, "agent-model", rng) == "medium"
    assert wazn.choose("write_code", 5, "agent-model", rng) == "large"


def test_a_model_that_keeps_failing_loses_the_work(agent, monkeypatch):
    monkeypatch.setenv("MIZAN_LISAN_MODELS", "small,large")
    for _ in range(30):
        wazn.record("fix_code", "small", False)
    rng = random.Random(1)
    assert {wazn.choose("fix_code", 0, None, rng) for _ in range(20)} == {"large"}
    monkeypatch.delenv("MIZAN_LISAN_MODELS")
    assert wazn.choose("fix_code", 0, "agent-model") == "agent-model"


async def test_the_repair_is_asked_of_a_stronger_model(agent, monkeypatch):
    monkeypatch.setenv("MIZAN_LISAN_MODELS", "small,large")
    for _ in range(30):
        wazn.record("write_code", "small", True)
        wazn.record("fix_code", "small", True)
    agent.ai_client = ScriptedProvider([WRONG, RIGHT])
    sandbox(agent, monkeypatch, FAILED, PASSED)
    result = await agent.execute(REQUEST)
    assert result["task_verified"]
    assert [request["model"] for request in agent.ai_client.requests] == ["small", "large"]
    rows = {(row["task"], row["model"]): row for row in wazn.report()}
    assert rows[("fix_code", "large")]["evidence"] > 0


# ── Furqan: a warning in a tool's result may not be dropped ────────────


def test_wording_that_drops_a_tools_warning_is_rejected():
    result = '{"rows": 3, "warnings": ["column price has 2 null values"], "error": null}'
    warnings = cautions(result)
    assert warnings == ["warnings: ['column price has 2 null values']"]
    assert furqan("The table has 3 rows.", result, warnings=warnings)
    assert not furqan("3 rows; warning: price has null values.", result, warnings=warnings)
    assert not furqan("Teen rows hain, lekin price me null values hain.", result, warnings=warnings)
    assert cautions('{"stdout": "done", "stderr": "", "error": null}') == []
    assert cautions("ok\nDeprecationWarning: utcnow() is deprecated") == [
        "DeprecationWarning: utcnow() is deprecated"
    ]


async def test_a_tool_answer_keeps_mizans_wording_when_lisan_drops_the_warning(agent):
    engine = Tadbir(agent)
    agent.ai_client = ScriptedProvider(["Your backup finished."])
    facts = {
        "tool": "backup",
        "arguments": {},
        "result": '{"done": true, "warning": "3 files were skipped: permission denied"}',
    }
    text, phrased = await engine._phrase_with_lisan("backup", facts, "en", "MIZAN's own")
    assert (text, phrased) == ("MIZAN's own", False)


# ── The admin view ─────────────────────────────────────────────────────


async def test_the_harness_report_is_for_admins_and_can_be_reset(agent, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    from api import main

    monkeypatch.setitem(main.active_agents, "fixture", agent)
    admin = main.auth.create_token(main.auth.create_user("harnessadmin", "pw", roles=["admin"]))
    member = main.auth.create_token(main.auth.create_user("harnessuser", "pw", roles=["user"]))
    _challenge("write_code", INSTRUCTIONS["write_code"] + " Define names first.")
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {admin}"}
        denied = await client.get(
            "/api/tadbir/harness", headers={"Authorization": f"Bearer {member}"}
        )
        assert denied.status_code == 403
        report = (await client.get("/api/tadbir/harness", headers=headers)).json()
        rows = {row["task"]: row for row in report["instructions"]}
        assert rows["write_code"]["challenger"]["id"] == "c1" and report["evolution"] is True
        assert (await client.delete("/api/tadbir/harness/nope", headers=headers)).status_code == 404
        await client.delete("/api/tadbir/harness/write_code", headers=headers)
        report = (await client.get("/api/tadbir/harness", headers=headers)).json()
        assert (
            "challenger" not in {row["task"]: row for row in report["instructions"]}["write_code"]
        )
        lessons = await client.get(
            "/api/tadbir/lessons", headers={"Authorization": f"Bearer {member}"}
        )
        assert lessons.status_code == 200 and lessons.json()["lessons"] == 0
