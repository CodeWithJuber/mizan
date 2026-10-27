"""Wazn (وزن): the cheapest model that is ready for the work, and a stronger one when it fails.

Cost-aware readiness, measured on MIZAN's own verified outcomes: an admin
lists candidate models for Lisan, cheapest first (``MIZAN_LISAN_MODELS``).
For each kind of work and model, MIZAN keeps a Beta posterior of how often
the work verified. A call goes to the cheapest model whose sampled success
reaches the readiness level (``MIZAN_LISAN_READINESS``, default 0.7); each
failed attempt at the same work moves one step to a stronger model instead
of asking the same model again. With no list, Lisan uses the agent's model.
"""

from __future__ import annotations

import os
import random
from typing import Any

from core.adaptive import BetaEstimator

from .tajdid import CONTRACTS, store

_PRIOR = {"alpha": 2.0, "beta": 1.0, "prior_alpha": 2.0, "prior_beta": 1.0, "forgetting": 0.99}
_RNG = random.Random()


def models() -> list[str]:
    raw = os.getenv("MIZAN_LISAN_MODELS", "")
    return [name.strip() for name in raw.split(",") if name.strip()][:6]


def readiness() -> float:
    try:
        return min(0.99, max(0.05, float(os.getenv("MIZAN_LISAN_READINESS", "0.7"))))
    except ValueError:
        return 0.7


def _key(task: str, model: str) -> str:
    return f"wazn:{task}:{model}"


def _posterior(task: str, model: str) -> BetaEstimator:
    try:
        return BetaEstimator.from_dict(store().get(_key(task, model)), **_PRIOR)
    except Exception:  # noqa: BLE001
        return BetaEstimator(**_PRIOR)


def choose(task: str, attempt: int, default: str | None, rng: random.Random | None = None) -> Any:
    """The model for this call: cheapest ready one, one step stronger per failed attempt."""
    candidates = models()
    if not candidates or not task:
        return default
    generator = rng or _RNG
    level = readiness()
    start = len(candidates) - 1
    for index, model in enumerate(candidates):
        estimate = _posterior(task, model)
        sample = generator.betavariate(max(estimate.alpha, 1e-6), max(estimate.beta, 1e-6))
        if sample >= level:
            start = index
            break
    return candidates[min(start + max(0, attempt), len(candidates) - 1)]


def record(task: str, model: str | None, worked: bool) -> None:
    if not model or model not in models():
        return
    try:
        store().put(_key(task, model), _posterior(task, model).update(worked).to_dict())
    except Exception:  # noqa: BLE001
        pass


def report() -> list[dict]:
    rows = []
    for task in CONTRACTS:
        for model in models():
            estimate = _posterior(task, model)
            rows.append(
                {
                    "task": task,
                    "model": model,
                    "success": round(float(estimate.mean), 3),
                    "evidence": round(float(estimate.evidence), 2),
                }  # fmt: skip
            )
    return rows
