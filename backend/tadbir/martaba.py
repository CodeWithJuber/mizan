"""Martaba (مرتبة): a trust ladder each agent climbs by its record. Report only.

"And for all there are degrees (darajat) for what they have done" (6:132).
Ported from ForgeKit's harness_policy.js ``advanceHarnessTrust``: an agent
(and each person's private copy of it, which keeps its own record) starts at
stage 1 of 7 and

- is **promoted** one stage after 20 consecutive verified runs with a pass
  rate of at least 0.9 over the runs counted since it reached its stage;
- is **demoted** one stage (never below 1) after 3 failures in a row, or at
  once on a guard event: a secret in the answer, an injected instruction's
  payload the answer repeated (a gate it got past), or a claim Isnad marked
  mawdu' (an action, citation or link the answer made up).

A run is counted only when MIZAN checked it: verified (its own checks passed)
or failed (it errored or answered nothing). An answer in words that nothing
checked is no evidence either way and is not counted.

The owner chose report only: the stage is shown on the agent's card and in
``GET /api/agents/{id}``, and it **never restricts anything**. No tool is
hidden, no permission mode or approval changes, whatever the stage
(``tests/test_martaba.py`` holds this).
"""

from __future__ import annotations

import re
from typing import Any

STAGES = {
    1: "Observe",
    2: "Assist",
    3: "Draft",
    4: "Act",
    5: "Reach",
    6: "Trusted",
    7: "Steward",
}
REQUIRED_RUNS = 20
MIN_PASS_RATE = 0.9
MAX_FAILURES = 3
INITIAL = 1
# Credential shapes an answer should never carry (report only).
_SECRET = re.compile(
    r"\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    r"AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{35})\b"
)


def fresh(stage: int, reason: str = "initial") -> dict:
    return {
        "stage": max(1, min(7, int(stage))),
        "verified": 0,
        "total": 0,
        "consecutive": 0,
        "failures": 0,
        "reason": reason,
        "runs": 0,
    }


def advance(state: dict, *, verified: bool, guard: list[str] | None = None) -> dict:
    """One counted run (ForgeKit's advanceHarnessTrust)."""
    guard = list(guard or [])
    runs = int(state.get("runs", 0)) + 1
    state = {**fresh(INITIAL), **state, "runs": runs}
    state["total"] += 1
    if verified:
        state["verified"] += 1
    state["consecutive"] = state["consecutive"] + 1 if verified and not guard else 0
    state["failures"] = 0 if verified else state["failures"] + 1
    state["reason"] = "recorded"
    if guard or state["failures"] >= MAX_FAILURES:
        demoted = fresh(state["stage"] - 1, "demoted: " + (", ".join(guard) or "3 failures"))
        return {**demoted, "runs": runs}
    if (
        state["stage"] < 7
        and state["consecutive"] >= REQUIRED_RUNS
        and state["verified"] / state["total"] >= MIN_PASS_RATE
    ):
        return {**fresh(state["stage"] + 1, "promoted"), "runs": runs}
    return state


def guard_events(result: dict) -> list[str]:
    """What in this run's result is a guard event."""
    found = []
    text = result.get("result")
    if isinstance(text, str) and _SECRET.search(text):
        found.append("secret in the answer")
    satr = result.get("satr")
    if isinstance(satr, dict) and (satr.get("covered") or satr.get("hits")):
        found.append("secret covered")
    amanah = result.get("amanah")
    if isinstance(amanah, dict) and amanah.get("removed_from_answer"):
        found.append("injected payload in the answer")
    isnad = result.get("isnad")
    counts = isnad.get("counts") if isinstance(isnad, dict) else None
    if isinstance(counts, dict) and counts.get("mawdu"):
        found.append("fabricated claim")
    return found


def outcome(result: dict) -> tuple[bool | None, list[str]]:
    """(verified, guard events): verified True/False when MIZAN checked the run,
    None when nothing did (not counted)."""
    guard = guard_events(result)
    if result.get("success") is False or result.get("completion_status") == "failed":
        return False, guard
    if result.get("task_verified"):
        return True, guard
    return (False if guard else None), guard


def _key(agent: Any) -> str:
    base = getattr(agent, "_run_base", agent)
    return f"martaba:{getattr(base, '_template_id', None) or getattr(base, 'id', '')}"


def state_of(agent: Any) -> dict:
    try:
        data = agent.adaptive.get(_key(agent))
    except Exception:  # noqa: BLE001 - no store: the agent starts at stage 1
        data = None
    return {**fresh(INITIAL), **data} if isinstance(data, dict) else fresh(INITIAL)


def record(agent: Any, result: dict) -> dict | None:
    """Count one finished run of this agent, when MIZAN checked it."""
    verified, guard = outcome(result)
    if verified is None:
        return None
    state = advance(state_of(agent), verified=verified, guard=guard)
    try:
        agent.adaptive.put(_key(agent), state)
    except Exception:  # noqa: BLE001 - the record is best effort
        pass
    return state


def view(agent: Any) -> dict:
    """The stage and record as the agent card shows them."""
    state = state_of(agent)
    total = int(state.get("total", 0))
    return {
        "stage": state["stage"],
        "name": STAGES[state["stage"]],
        "verified": state["verified"],
        "counted": total,
        "pass_rate": round(state["verified"] / total, 3) if total else None,
        "consecutive": state["consecutive"],
        "failures": state["failures"],
        "to_next": max(0, REQUIRED_RUNS - state["consecutive"]) if state["stage"] < 7 else 0,
        "reason": state.get("reason", "initial"),
        "report_only": True,
    }
