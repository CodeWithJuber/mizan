"""The choice of action, learned from the teacher (Tadrib phase 2b, docs/tadrib.md).

Phase 2 showed that a small byte student learns the form of a plan but not
the teacher's choice of action. The choice is a classification, and MIZAN
already classifies by evidence (Tamyiz: weighted naive Bayes over the same
features as Qasd). Here it learns, from the teacher's verified plans
(``plans.target``), which action a message asks for: ``converse``,
``use_tool``, ``watch``, ``web_search``, ``compute``, … (a plan of several
actions is one label, its actions joined by ``+``).

It answers only when it is sure: when its posterior for the action is at
least ``SURE`` (fixed before any test). Below that the teacher is asked, as
now. Every answer it gives can still be checked by MIZAN, and the teacher's
answer to every lesson is learned (``learn``), so what it is unsure of today
it may be sure of later.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

SURE = 0.9


def action_of(answer: str | None) -> str | None:
    """The plan's actions joined by ``+``, or None when it is not a plan."""
    if not answer:
        return None
    try:
        steps = json.loads(answer).get("steps")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None
    if not isinstance(steps, list) or not steps:
        return None
    return "+".join(str(step.get("intent", "")) for step in steps if isinstance(step, dict))


class Choice:
    """MIZAN's own reading of which action a message asks for."""

    def __init__(self, lessons: Iterable[tuple[str, str]] = ()):
        from core.tamyiz import Tamyiz

        from .. import qasd

        rows = [(text, action) for text, action in lessons if text and action]
        self.model = Tamyiz(qasd._features)
        if len({action for _text, action in rows}) >= 2:
            self.model.fit(rows)
        else:
            for text, action in rows:
                self.model.learn(text, action)

    def read(self, message: str) -> tuple[str | None, float]:
        """The most probable action and its probability (None before any lesson)."""
        found = self.model.posterior(message)
        if not found:
            return None, 0.0
        action = max(found, key=lambda label: found[label])
        return action, float(found[action])

    def answer(self, message: str) -> str | None:
        """The action, only when the reading is sure; else None (the teacher is asked)."""
        action, probability = self.read(message)
        return action if action is not None and probability >= SURE else None

    def learn(self, message: str, action: str) -> None:
        self.model.learn(message, action)
