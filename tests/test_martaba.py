"""Martaba: a trust ladder per agent, report only (ported from ForgeKit's
harness_policy.js; docs/personal-agents.md)."""

import pytest

from agents import agent_settings
from agents.specialized import create_agent
from security.izn import IznPermission
from tadbir import martaba


def climb(state, outcomes):
    for verified in outcomes:
        state = martaba.advance(state, verified=verified)
    return state


def test_twenty_consecutive_verified_runs_promote_one_stage():
    start = martaba.fresh(1)
    assert climb(start, [True] * 19)["stage"] == 1
    promoted = climb(start, [True] * 20)
    assert promoted["stage"] == 2 and promoted["reason"] == "promoted"
    assert promoted["consecutive"] == 0  # the next stage is earned afresh
    assert climb(martaba.fresh(7), [True] * 40)["stage"] == 7


def test_the_pass_rate_must_be_at_least_nine_in_ten():
    shaky = climb(martaba.fresh(1), [False, False, True] * 4)  # 4 of 12, never 3 in a row
    assert shaky["stage"] == 1
    assert climb(shaky, [True] * 20)["stage"] == 1  # 24 of 32 = 0.75
    assert climb(shaky, [True] * 68)["stage"] == 2  # 72 of 80 = 0.9


def test_three_failures_or_one_guard_event_demote_never_below_one():
    stage3 = martaba.fresh(3)
    assert climb(stage3, [False, False])["stage"] == 3
    assert climb(stage3, [False, False, False])["stage"] == 2
    assert climb(martaba.fresh(1), [False] * 9)["stage"] == 1
    flagged = martaba.advance(stage3, verified=True, guard=["fabricated claim"])
    assert flagged["stage"] == 2 and "fabricated claim" in flagged["reason"]


def test_only_runs_mizan_checked_are_counted():
    assert martaba.outcome({"success": True, "result": "words", "task_verified": False}) == (
        None,
        [],
    )
    assert martaba.outcome({"success": True, "task_verified": True})[0] is True
    assert martaba.outcome({"success": False})[0] is False
    leaked = {"success": True, "task_verified": True, "result": "key: sk-" + "a1" * 20}
    assert martaba.outcome(leaked) == (True, ["secret in the answer"])
    made_up = {"success": True, "isnad": {"counts": {"mawdu": 1}}}
    assert martaba.outcome(made_up) == (False, ["fabricated claim"])
    repeated = {"success": True, "amanah": {"ignored": 1, "removed_from_answer": 1}}
    assert martaba.guard_events(repeated) == ["injected payload in the answer"]


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    return create_agent("general", izn=IznPermission())


def abilities(agent):
    names = sorted(schema["name"] for schema in agent.get_tool_schemas())
    return {
        "tools": names,
        "allowed": {name: agent._chat_tool_allowed(name) for name in names},
        "permission_mode": agent_settings.of(agent.config).get("permission_mode"),
        "effective": agent.effective_tools(),
        "max_tool_turns": agent.max_tool_turns,
    }


def test_the_stage_restricts_nothing(agent):
    """The owner chose report only: a stage-1 agent keeps every tool and its mode."""
    before = abilities(agent)
    for _ in range(3):
        martaba.record(agent, {"success": False})
    martaba.record(agent, {"success": True, "isnad": {"counts": {"mawdu": 2}}})
    assert martaba.view(agent)["stage"] == 1
    assert abilities(agent) == before
    for _ in range(20):
        martaba.record(agent, {"success": True, "task_verified": True})
    assert martaba.view(agent)["stage"] == 2
    assert abilities(agent) == before


def test_the_view_is_the_cards_record(agent):
    for _ in range(5):
        martaba.record(agent, {"success": True, "task_verified": True})
    martaba.record(agent, {"success": True, "result": "unchecked words"})  # not counted
    view = martaba.view(agent)
    assert view == {
        "stage": 1, "name": "Observe", "verified": 5, "counted": 5, "pass_rate": 1.0,
        "consecutive": 5, "failures": 0, "to_next": 15, "reason": "recorded",
        "report_only": True,
    }  # fmt: skip


async def test_a_finished_run_is_counted_for_its_agent(agent, monkeypatch):
    async def impl(task, context, *args):
        return {"success": True, "result": "42", "task_verified": True}

    monkeypatch.setattr(agent, "_execute_impl", impl)
    result = await agent.execute("What is 6 times 7?")
    assert result["usage"]["learned"]["martaba"] == 1
    assert martaba.view(agent)["verified"] == 1
