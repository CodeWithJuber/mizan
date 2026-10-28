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
3. Incumbent and challenger share traffic by Thompson sampling. Their results
   are paired in the order they arrive, and over the pairs where they differ
   MIZAN keeps an e-value (``core.adaptive.paired_e_value``): the challenger
   becomes the incumbent when the evidence that it is better reaches 1/α, and
   is retired when the evidence that the incumbent is better does, or when a
   declared budget of disagreements passes without either.

Why not "P(better) >= 0.95" after every result: looked at again and again, such
a rule promotes a version that is no better far more often than 5% of the time.
The Quran asks that a report be verified before it is acted on, "lest you harm a
people out of ignorance" (49:6), and al-Tabari reads it as "give it respite until
you know its soundness; do not hasten to accept it". The e-value is that respite
in numbers: it may be read after every result, and by Ville's inequality the
chance it ever wrongly reaches 1/α stays below α. Each new challenger spends half
of what is left of α (α_k = α·2^-k), so over all challengers ever tried the chance
of a single false promotion is at most α.

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

from core.adaptive import AdaptiveStateStore, BetaEstimator, paired_e_value

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
ALPHA = 0.05  # the declared chance of ever promoting a version that is not better
# A declared evaluation budget: about twice the disagreements a sequential test
# needs to detect a 65/35 split (α 0.05, power 0.8). A challenger that has not
# shown it is better by then is retired rather than tried forever.
MAX_DISAGREEMENTS = 80
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
    data.setdefault("judged", 0)  # challengers decided so far (α spending)
    data.setdefault("pairs", _fresh_pairs())
    return data


def _fresh_pairs() -> dict:
    return {"challenger": [], "incumbent": [], "wins": 0, "losses": 0, "ties": 0}


def threshold(judged: int) -> float:
    """1/α_k for the k-th challenger: α_k = α·2^-k, so Σ_k α_k ≤ α."""
    return 1.0 / (ALPHA * 2.0 ** -(judged + 1))


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
    if state["challenger"]:
        _pair(
            state["pairs"], "challenger" if target is state["challenger"] else "incumbent", worked
        )
    if not worked and target is state["incumbent"]:
        state["since"] = int(state["since"]) + 1
        if feedback:
            state["failures"] = (state["failures"] + [feedback[:160]])[-MAX_FAILURES:]
    _decide(state)
    _put(task, state)


def _pair(pairs: dict, arm: str, worked: bool) -> None:
    """Pair the k-th result of each version in the order they arrive. The pairing
    never looks at the outcomes, so where neither version is better each
    disagreement is a fair coin, whatever the versions' common success rate."""
    pairs[arm] = (pairs[arm] + [int(worked)])[-200:]
    while pairs["challenger"] and pairs["incumbent"]:
        mine, theirs = pairs["challenger"].pop(0), pairs["incumbent"].pop(0)
        key = "wins" if mine > theirs else "losses" if theirs > mine else "ties"
        pairs[key] = int(pairs[key]) + 1


def evidence(state: dict) -> dict:
    pairs = state["pairs"]
    wins, losses = int(pairs["wins"]), int(pairs["losses"])
    return {
        "wins": wins,
        "losses": losses,
        "ties": int(pairs["ties"]),
        "better": round(paired_e_value(wins, losses), 3),
        "worse": round(paired_e_value(losses, wins), 3),
        "threshold": round(threshold(int(state["judged"])), 1),
    }


def _decide(state: dict) -> None:
    challenger = state["challenger"]
    if not challenger:
        return
    found = evidence(state)
    decided = None
    if found["better"] >= found["threshold"]:
        decided = {"promoted": challenger["id"], "replaced": state["incumbent"]["id"]}
        state["incumbent"] = challenger
        state["failures"] = []
    elif (
        found["worse"] >= found["threshold"] or found["wins"] + found["losses"] >= MAX_DISAGREEMENTS
    ):
        decided = {"retired": challenger["id"]}
    if decided is None:
        return
    state["history"] = (
        state["history"] + [{"at": time.time(), **decided, "e_value": found["better"],
                             "pairs": found["wins"] + found["losses"]}]
    )[-20:]  # fmt: skip
    state["challenger"] = None
    state["since"] = 0
    state["judged"] = int(state["judged"]) + 1
    state["pairs"] = _fresh_pairs()


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
    state["pairs"] = _fresh_pairs()  # only results under both versions are compared
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
                "evidence": evidence(state),
            }
        rows.append(row)
    return rows


def reset(task: str) -> None:
    store().put(f"tajdid:{task}", {})
