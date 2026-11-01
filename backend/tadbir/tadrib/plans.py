"""Which teacher plans are lessons, and when two plans are the same (Tadrib
phase 2, docs/tadrib.md). No torch: MIZAN checks plans whether or not a
student runs.

The first task is ``plan_steps``: mapping a message to MIZAN's actions. The
teacher's plan becomes a lesson only when MIZAN's own checks pass every step
(``fahm.validate_parsed``), or when it is a lone ``converse``; a plan with a
Quran or hadith step, or a message about the deen, is never a lesson (the
owner's decision of 31 Oct 2026).

Two plans agree (``agree``) when they have the same actions in the same order,
each passing MIZAN's checks, with the same structured values (the arithmetic's
value, the link, the schedule, the kind of project). Words a step carries for a
person to read or a tool to search (a ``need``, a ``query``) are compared too,
by ``same``, but only reported.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

SCRIPTURE = frozenset({"quran", "quran_search", "hadith"})
# The fields each action may carry (Lisan.plan_steps' schema); "text" only in a plan of several.
FIELDS = {
    "compute": ("expression",),
    "silsila": (),
    "build_and_run": ("request", "language"),
    "build_project": ("kind",),
    "edit_project": ("request",),
    "web_search": ("query",),
    "web_read": ("url",),
    "watch": ("when", "task", "title"),
    "use_tool": ("need",),
}


def about_the_deen(message: str) -> bool:
    from .. import qasd

    try:
        return qasd.facet("deen", message) or qasd.facet("ruling", message)
    except Exception:  # noqa: BLE001 - a facet model that cannot load decides nothing
        return False


def target(steps: Sequence[dict], message: str, language: str) -> str | None:
    """The answer the student learns: the teacher's steps in a fixed form, or
    None when the plan is no lesson (a step MIZAN's checks refuse, scripture,
    the deen, or conversation mixed with actions)."""
    from .. import fahm

    if not steps or about_the_deen(message):
        return None
    intents = [str(step.get("intent", "")) for step in steps]
    if intents == ["converse"]:
        return json.dumps({"steps": [{"intent": "converse"}]}, separators=(",", ":"))
    kept = []
    for step in steps:
        intent = str(step.get("intent", ""))
        if intent in SCRIPTURE or intent not in FIELDS:
            return None
        if fahm.validate_parsed(step, message, language) is None:
            return None
        item: dict[str, Any] = {"intent": intent}
        item.update({key: step[key] for key in FIELDS[intent] if key in step})
        if len(steps) > 1 and str(step.get("text") or "").strip():
            item["text"] = str(step["text"]).strip()
        kept.append(item)
    return json.dumps({"steps": kept}, ensure_ascii=False, separators=(",", ":"))


def parse(answer: str | None) -> list[dict] | None:
    if not answer:
        return None
    try:
        value = json.loads(answer)
    except (json.JSONDecodeError, TypeError):
        return None
    steps = value.get("steps") if isinstance(value, dict) else None
    if not isinstance(steps, list) or not steps or len(steps) > 4:
        return None
    return [step for step in steps if isinstance(step, dict)] or None


def _key(step: dict, message: str, language: str) -> tuple | None:
    """What must match for two plans to be the same: the action and its
    structured values, after MIZAN's own checks."""
    from .. import calc, fahm

    intent = str(step.get("intent", ""))
    if intent == "converse":
        return ("converse",)
    if intent in SCRIPTURE or intent not in FIELDS:
        return None
    understood = fahm.validate_parsed(step, message, language)
    if understood is None:
        return None
    entities = understood.entities
    if intent == "compute":
        try:
            value = calc.render(calc.evaluate(calc.normalize(str(entities["expression"]))))
        except Exception:  # noqa: BLE001
            return None
        return (intent, value)
    if intent == "build_and_run":
        return (intent, entities.get("code_language"))
    if intent == "build_project":
        return (intent, entities.get("kind"))
    if intent == "watch":
        return (intent, json.dumps(entities.get("trigger"), sort_keys=True, default=str))
    if intent == "web_read":
        return (intent, entities.get("url"))
    return (intent,)


def understood(answer: str | None, message: str, language: str) -> list[tuple] | None:
    """The plan's keys, or None when any step fails MIZAN's checks."""
    steps = parse(answer)
    if steps is None:
        return None
    if [str(step.get("intent", "")) for step in steps].count("converse") and len(steps) > 1:
        return None
    keys = [_key(step, message, language) for step in steps]
    return None if any(key is None for key in keys) else keys  # type: ignore[return-value]


def valid(answer: str | None, message: str, language: str) -> bool:
    return understood(answer, message, language) is not None


def agree(answer: str | None, taught: str | None, message: str, language: str) -> bool:
    """The student's plan is the teacher's: same actions, same structured values."""
    if taught is None:
        return False
    mine = understood(answer, message, language)
    return mine is not None and mine == understood(taught, message, language)


def same(answer: str | None, taught: str | None) -> bool:
    """Word for word the same plan (free-text fields included)."""
    first, second = parse(answer), parse(taught)
    return first is not None and first == second


def digest_of(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
