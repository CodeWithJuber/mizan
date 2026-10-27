"""Sijill (سجل): the live record of what MIZAN learns, as it learns it.

Every learning step MIZAN takes from a verified outcome is noted here for the
user whose work it came from: wording learned (Ta'allum), a program kept or
re-run (Hifz), a repair lesson (Tajriba), an instruction tried or renewed
(Tajdid), routing evidence for an agent (Majlis), a game level remembered
(Mustakshif), a claim corrected before it was shown (Sidq). Nothing here
trains weights; it is the visible trace of learning without them.

Notes are held in memory (the last 200 per user) and read by the Learning
page, which polls ``/api/tadbir/learning/live``.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from typing import Any

MAX_NOTES = 200
_LOCK = threading.Lock()
_NOTES: dict[str, deque[dict]] = {}
_SEQUENCE = itertools.count(1)


def _summary(kind: str, attributes: dict[str, Any]) -> str:
    worked = attributes.get("worked")
    if kind == "taallum":
        if attributes.get("reused"):
            return "Reused wording it learned before" + (
                " (verified again)" if worked else " (it failed; unlearned)"
            )
        if attributes.get("kept"):
            return f"Learned how this request is phrased ({attributes.get('intent', 'request')})"
        return "Saw a request it could not verify; learned nothing"
    if kind == "hifz":
        if attributes.get("reused"):
            reliability = attributes.get("reliability")
            share = (
                f", reliability {round(float(reliability) * 100)}%"
                if reliability is not None
                else ""
            )
            return (
                "Re-ran a program it verified before"
                + (" and it held" if worked else "; it no longer holds")
                + share
            )
        return (
            f"Kept a verified {attributes.get('language', '')} program to re-run next time".replace(
                "  ", " "
            )
        )
    if kind == "tajriba":
        return f"Learned a repair lesson for: {str(attributes.get('signature', ''))[:120]}"
    if kind == "tajdid":
        variant = attributes.get("variant") or "base"
        return f"Scored instruction '{variant}' for {attributes.get('task', 'code work')}" + (
            " (worked)" if worked else " (failed)" if worked is False else ""
        )
    if kind == "majlis":
        return (
            f"Routing evidence: {attributes.get('agent', 'an agent')} on {attributes.get('intent', 'a task')}"
            + (" worked" if worked else " failed")
        )
    if kind == "game":
        return str(attributes.get("detail") or "Remembered how a game level is won")
    if kind == "sidq":
        return str(attributes.get("detail") or "Corrected a claim before it was shown")
    return kind


def note(kind: str, attributes: dict[str, Any] | None = None, owner: str | None = None) -> None:
    """Record one learning step for the user whose work it came from."""
    if owner is None:
        try:
            from security.auth import current_user_id

            owner = current_user_id() or ""
        except Exception:  # noqa: BLE001 - outside a request there is no user
            owner = ""
    details = {
        k: v for k, v in (attributes or {}).items() if isinstance(v, str | int | float | bool)
    }
    entry = {
        "seq": next(_SEQUENCE),
        "at": time.time(),
        "kind": kind,
        "summary": _summary(kind, attributes or {}),
        "details": details,
    }
    with _LOCK:
        _NOTES.setdefault(owner, deque(maxlen=MAX_NOTES)).append(entry)


def since(owner: str, after: int = 0, limit: int = 100) -> list[dict]:
    """The user's notes newer than ``after``, oldest first."""
    with _LOCK:
        notes = [dict(item) for item in _NOTES.get(owner, ()) if item["seq"] > after]
    return notes[-max(1, min(limit, MAX_NOTES)) :]


def clear(owner: str) -> None:
    with _LOCK:
        _NOTES.pop(owner, None)
