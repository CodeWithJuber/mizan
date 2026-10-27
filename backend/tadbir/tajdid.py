"""Tajdid (تجديد): MIZAN renews Lisan's instructions, and keeps a new version only when it proves better.

Lisan's instruction for each kind of code work is MIZAN's harness for the
language model. Following HERD (arXiv:2610.31401), the harness evolves; and,
as in sequential incumbent replacement, a new version must earn its place:

1. The incumbent instruction keeps a Beta posterior of how often its work
   verified (MIZAN's sandbox and checks are the critic).
2. After repeated failures, Lisan rewrites the instruction from the failure
   signatures (self-rewrite). MIZAN accepts the rewrite as a challenger only
   if it keeps the output contract (fenced code, the same placeholders) and
   stays within length.
3. Incumbent and challenger share traffic by Thompson sampling. When the
   challenger has enough trials and P(challenger better) >= 0.95 it becomes
   the incumbent; at <= 0.05 it is retired.

The fixed parts never change: Lisan's base prompt, MIZAN's verification and
every safety gate. Only the wording of the task instruction evolves, for all
users together; no user text is stored, only error signatures.
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import time
from pathlib import Path
from typing import Any

from core.adaptive import AdaptiveStateStore, BetaEstimator

# The kinds of work whose outcome MIZAN verifies exactly, and the phrases
# every version of their instruction must keep.
CONTRACTS: dict[str, tuple[str, ...]] = {
    "write_code": ("fenced code block",),
    "fix_code": ("fenced code block",),
    "propose_rule": ("transform(grid)", "fenced code block"),
    "revise_rule": ("fenced code block",),
    "propose_sequence_rule": ("def a(n)", "fenced code block"),
    "revise_sequence_rule": ("fenced code block",),
}
MIN_TRIALS = 12
PROMOTE = 0.95
RETIRE = 0.05
EVOLVE_AFTER = 5
MAX_FAILURES = 8
_PRIOR = {"alpha": 2.0, "beta": 1.0, "prior_alpha": 2.0, "prior_beta": 1.0, "forgetting": 1.0}
_RNG = random.Random()
_STORES: dict[str, AdaptiveStateStore] = {}


def enabled() -> bool:
    """New instruction versions are tried (``MIZAN_HARNESS_EVOLUTION``, default on)."""
    return os.getenv("MIZAN_HARNESS_EVOLUTION", "on").strip().lower() not in {
        "off", "0", "false", "no",
    }  # fmt: skip


def store() -> AdaptiveStateStore:
    """The harness state shared by every user (counts and instruction text only)."""
    directory = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan"))
    path = str(directory / "harness.db")
    if path not in _STORES:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            _STORES[path] = AdaptiveStateStore(path)
        except OSError:
            _STORES[path] = AdaptiveStateStore(None)
    return _STORES[path]


def _state(task: str) -> dict:
    data = store().get(f"tajdid:{task}") or {}
    data.setdefault("incumbent", {"id": "base", "text": None, "posterior": None})
    data.setdefault("challenger", None)
    data.setdefault("failures", [])
    data.setdefault("since", 0)
    data.setdefault("history", [])
    return data


def _put(task: str, state: dict) -> None:
    store().put(f"tajdid:{task}", state)


def _beta(variant: dict) -> BetaEstimator:
    return BetaEstimator.from_dict(variant.get("posterior"), **_PRIOR)


def instruction(task: str, default: str, rng: random.Random | None = None) -> tuple[str, str]:
    """(variant id, instruction template) for this call."""
    if task not in CONTRACTS:
        return "base", default
    try:
        state = _state(task)
    except Exception:  # noqa: BLE001 - no store: the built-in instruction
        return "base", default
    incumbent = state["incumbent"]
    chosen = incumbent
    challenger = state["challenger"]
    if challenger and enabled():
        generator = rng or _RNG
        if _sample(challenger, generator) > _sample(incumbent, generator):
            chosen = challenger
    return chosen["id"], chosen.get("text") or default


def _sample(variant: dict, rng: random.Random) -> float:
    estimate = _beta(variant)
    return rng.betavariate(max(estimate.alpha, 1e-6), max(estimate.beta, 1e-6))


def probability_better(
    challenger: dict, incumbent: dict, draws: int = 4000, rng: random.Random | None = None
) -> float:
    generator = rng or random.Random(1)
    wins = sum(
        1 for _ in range(draws) if _sample(challenger, generator) > _sample(incumbent, generator)
    )
    return wins / draws


def record(task: str, variant: str, worked: bool, feedback: str = "") -> None:
    """One verified or failed result of work done under a version of the instruction."""
    if task not in CONTRACTS:
        return
    try:
        state = _state(task)
    except Exception:  # noqa: BLE001
        return
    target = state["incumbent"]
    if state["challenger"] and state["challenger"]["id"] == variant:
        target = state["challenger"]
    elif target["id"] != variant:
        return  # a version that is no longer in use
    target["posterior"] = _beta(target).update(worked).to_dict()
    target["trials"] = int(target.get("trials", 0)) + 1
    if not worked and target is state["incumbent"]:
        state["since"] = int(state["since"]) + 1
        if feedback:
            state["failures"] = (state["failures"] + [feedback[:160]])[-MAX_FAILURES:]
    _decide(state)
    _put(task, state)


def _decide(state: dict) -> None:
    challenger = state["challenger"]
    if not challenger or int(challenger.get("trials", 0)) < MIN_TRIALS:
        return
    p = probability_better(challenger, state["incumbent"])
    if p >= PROMOTE:
        state["history"] = (state["history"] + [
            {"at": time.time(), "promoted": challenger["id"], "replaced": state["incumbent"]["id"],
             "p_better": round(p, 3)}
        ])[-20:]  # fmt: skip
        state["incumbent"] = challenger
        state["challenger"] = None
        state["since"] = 0
        state["failures"] = []
    elif p <= RETIRE:
        state["history"] = (state["history"] + [
            {"at": time.time(), "retired": challenger["id"], "p_better": round(p, 3)}
        ])[-20:]  # fmt: skip
        state["challenger"] = None
        state["since"] = 0


def wants_challenger(task: str) -> bool:
    if task not in CONTRACTS:
        return False
    try:
        state = _state(task)
    except Exception:  # noqa: BLE001
        return False
    return enabled() and state["challenger"] is None and int(state["since"]) >= EVOLVE_AFTER


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def valid(task: str, current: str, proposed: str) -> bool:
    """A rewrite keeps the output contract, the placeholders and a sensible length."""
    if not proposed.strip() or len(proposed) > max(2 * len(current), 600):
        return False
    if any(phrase.lower() not in proposed.lower() for phrase in CONTRACTS.get(task, ())):
        return False
    if _placeholders(proposed) != _placeholders(current):
        return False
    try:
        proposed.format(**{name: "x" for name in _placeholders(current)})
    except (KeyError, IndexError, ValueError):
        return False
    return True


async def evolve(task: str, default: str, lisan: Any) -> bool:
    """Ask Lisan to rewrite the incumbent instruction from its recent failures."""
    if not wants_challenger(task):
        return False
    state = _state(task)
    current = state["incumbent"].get("text") or default
    failures = "\n".join(f"- {item}" for item in state["failures"]) or "- (no detail)"
    try:
        reply = await lisan.ask(
            "You improve an instruction that MIZAN gives its language faculty for one kind of "
            "work. Rewrite it so the work fails less often, given the failures MIZAN recorded. "
            "Keep every requirement, keep each {placeholder} exactly as written, keep the "
            "required reply format, and do not make it much longer. Reply with the new "
            "instruction only, no commentary.",
            f"Instruction:\n{current}\n\nRecent failures (error signatures):\n{failures}",
            max_tokens=900,
        )
    except Exception:  # noqa: BLE001 - no rewrite this time
        return False
    proposed = reply.strip().strip("`").strip()
    if not valid(task, current, proposed):
        state["since"] = 0  # try again after more evidence
        _put(task, state)
        return False
    state["challenger"] = {
        "id": hashlib.sha256(proposed.encode()).hexdigest()[:10],
        "text": proposed,
        "posterior": None,
        "trials": 0,
        "created": time.time(),
    }
    state["since"] = 0
    _put(task, state)
    return True


def report() -> list[dict]:
    rows = []
    for task in CONTRACTS:
        try:
            state = _state(task)
        except Exception:  # noqa: BLE001
            continue
        incumbent, challenger = state["incumbent"], state["challenger"]
        row: dict[str, Any] = {
            "task": task,
            "incumbent": incumbent["id"],
            "incumbent_success": round(float(_beta(incumbent).mean), 3),
            "incumbent_trials": int(incumbent.get("trials", 0)),
            "failures_since_renewal": int(state["since"]),
            "history": state["history"][-5:],
        }
        if challenger:
            row["challenger"] = {
                "id": challenger["id"],
                "text": challenger["text"],
                "success": round(float(_beta(challenger).mean), 3),
                "trials": int(challenger.get("trials", 0)),
                "p_better": round(probability_better(challenger, incumbent), 3),
            }
        rows.append(row)
    return rows


def reset(task: str) -> None:
    store().put(f"tajdid:{task}", {})
