"""Majlis (مجلس): MIZAN's agents share the work, and MIZAN learns who does it best.

MIZAN, not a language model, decides which agent takes each part of a
request. Every agent that can do the work (it holds the tool, and the
user's permissions allow it) is a candidate. MIZAN picks one by Thompson
sampling over a Beta posterior per (agent, kind of work). The prior favours
the role made for that work: Katib for code, Mundhir for research, Mubashir
for reading pages, and Khalifah for the Quran, hadith and dates. Each
result MIZAN verifies, or fails to verify, updates the posterior, so routing
follows evidence. Learning here never needs a language model or chat
transcripts; it stores only counts.
"""

from __future__ import annotations

import random
from typing import Any

from core.adaptive import BetaEstimator, thompson_choice

# The role made for each kind of work.
ROLE_FOR = {
    "run_code": "katib",
    "build_and_run": "katib",
    "qiyas": "katib",
    "silsila": "katib",
    "build_project": "katib",
    "compute": "katib",
    "web_search": "mundhir",
    "web_read": "mubashir",
    "browse": "mubashir",
    "quran": "khalifah",
    "quran_search": "khalifah",
    "quran_count": "khalifah",
    "hadith": "khalifah",
    "waqt": "khalifah",
    "salah": "khalifah",
    "watch": "khalifah",
    "recall": "khalifah",
    "remember": "khalifah",
    "capabilities": "khalifah",
    "edit_project": "katib",
    "project_task": "katib",
    "run_file": "katib",
    "hf_hub": "mundhir",
    "use_tool": "khalifah",
}
ROLE_NAMES = {
    "katib": "code",
    "mundhir": "research",
    "mubashir": "web",
    "khalifah": "steward",
    "rasul": "communication",
}
# The tool an agent must be able to use for the work.
NEEDS = {
    "run_code": "workspace_run",
    "build_and_run": "workspace_run",
    "qiyas": "workspace_run",
    "build_project": "workspace_write",
    "web_search": "web_search",
    "web_read": "web_browse",
    "browse": "shahid_read",
    "recall": "recall_memory",
    "edit_project": "workspace_write",
    "project_task": "workspace_run",
    "run_file": "workspace_run",
    "hf_hub": "hf_repos",
}
# Prior pseudo-counts (successes, failures): strong for the specialist, good
# for Khalifah (which can do every kind of work), weak for the rest.
SPECIALIST_PRIOR = (20.0, 2.0)
STEWARD_PRIOR = (10.0, 4.0)
OTHER_PRIOR = (2.0, 4.0)
FORGETTING = 0.98
_RNG = random.Random()


def members(coordinator: Any) -> list[Any]:
    """The coordinating agent and every agent in its registry, once each."""
    seen: dict[str, Any] = {str(coordinator.id): coordinator}
    for agent in (getattr(coordinator, "_agent_registry", None) or {}).values():
        if getattr(agent, "id", None) and agent.id not in seen:
            seen[str(agent.id)] = agent
    return list(seen.values())


def able(agent: Any, intent: str) -> bool:
    tool = NEEDS.get(intent)
    if tool is None:
        return True
    try:
        names = {str(item.get("name", "")) for item in agent.get_tool_schemas()}
        return tool in names and bool(agent._chat_tool_allowed(tool))
    except Exception:  # noqa: BLE001 - an agent that cannot answer is not a candidate
        return False


def _key(agent: Any, intent: str) -> str:
    return f"majlis:{agent.id}:{intent}"


def prior(agent: Any, intent: str) -> tuple[float, float]:
    role = getattr(agent, "role", "")
    if role == ROLE_FOR.get(intent):
        return SPECIALIST_PRIOR
    return STEWARD_PRIOR if role == "khalifah" else OTHER_PRIOR


def posterior(coordinator: Any, agent: Any, intent: str) -> BetaEstimator:
    alpha, beta = prior(agent, intent)
    defaults = {
        "alpha": alpha,
        "beta": beta,
        "prior_alpha": alpha,
        "prior_beta": beta,
        "forgetting": FORGETTING,
    }
    try:
        return coordinator.adaptive.beta(_key(agent, intent), **defaults)
    except Exception:  # noqa: BLE001 - no store: the prior alone decides
        return BetaEstimator(**defaults)


def choose(coordinator: Any, intent: str, rng: random.Random | None = None) -> Any:
    """The agent MIZAN gives this kind of work to."""
    candidates = [agent for agent in members(coordinator) if able(agent, intent)]
    if not candidates:
        return coordinator
    if len(candidates) == 1:
        return candidates[0]
    posteriors = {str(a.id): posterior(coordinator, a, intent) for a in candidates}
    chosen = thompson_choice([str(a.id) for a in candidates], posteriors, rng or _RNG)
    return next(a for a in candidates if str(a.id) == chosen)


def record(coordinator: Any, agent: Any, intent: str, verified: bool) -> float:
    """One verified or unverified result; returns the agent's new success estimate."""
    estimate = posterior(coordinator, agent, intent).update(verified)
    try:
        coordinator.adaptive.put(_key(agent, intent), estimate.to_dict())
    except Exception:  # noqa: BLE001 - routing still works from the prior
        pass
    if agent is not coordinator:
        # The agent that did the work is the one whose record grows.
        agent.total_tasks += 1
        if verified:
            agent.success_count += 1
        try:
            agent.evolve_nafs()
        except Exception:  # noqa: BLE001 - evolution is best effort
            pass
    return float(estimate.mean)


def report(coordinator: Any) -> list[dict]:
    """What MIZAN has learned about who does which work."""
    rows = []
    for agent in members(coordinator):
        for intent in sorted(ROLE_FOR):
            estimate = posterior(coordinator, agent, intent)
            rows.append(
                {
                    "agent": agent.name,
                    "role": getattr(agent, "role", ""),
                    "intent": intent,
                    "success_estimate": round(float(estimate.mean), 3),
                    "evidence": round(float(estimate.evidence), 2),
                    "specialist": getattr(agent, "role", "") == ROLE_FOR.get(intent),
                }
            )
    return rows
