"""Niyyah (نية): "actions are judged by intentions" (Bukhari 1).

A project or a watcher keeps its goal: the one the person stated (the project's
``goal`` in its metadata, ``PATCH /api/workspaces/{id}``; the watcher's ``goal``,
``PATCH /api/muraqabah/watchers/{id}``), else the project chat's first request
or the watcher's task. Each run's work is read against it (ForgeKit's
anchor.js, made MIZAN's):

- the goal's concepts are its distinctive words (``ahl_dhikr.distinctive``:
  more information than its average word), stemmed (``amal.stem``);
- each action of the run that changed something is one item; its concepts are
  the request's words, the tool's name and its short arguments (paths, ids),
  and the names a program it wrote defines, split at camelCase and symbols;
- an item is on the goal with a noisy-OR of its hits, 1 − (1 − p)^k with
  p = 0.6 per distinct goal concept it shows (a ≥4-letter prefix meets a
  variant, "valid" → "validation", never a bare substring, "port" ↛ "report");
  it is on the goal at p, one hit;
- the run's drift Dₜ is the off-goal share of its items (no change: 0, which
  drains the chart), and a one-sided CUSUM Cₜ = max(0, Cₜ₋₁ + Dₜ − k), k = 0.35,
  alarms at Cₜ > h = 1.0: sustained drift, not one exploratory step.

The alarm is a note under the answer (``usage.niyyah``), never a gate; the
chart is kept per project or watcher with no words (``azm.sqlite3``)
(``docs/coding-workspaces.md``, ``docs/muraqabah.md``).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("mizan.niyyah")

ON_GOAL_P = 0.6
K = 0.35
H = 1.0
OFF_GOAL_SHOWN = 5
# Names a program defines: they say what a file is for, as anchor.js reads them.
_DEFINES = re.compile(r"\b(?:def|class|function|const|let|var|interface|type)\s+([A-Za-z_$][\w$]*)")


def concepts(text: str) -> set[str]:
    """Concept tokens of a text, a path or an identifier: camelCase and symbols
    split, lower-cased, stemmed, three letters or more."""
    from core.adaptive import tokenize

    from .amal import stem

    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text or ""))
    spaced = re.sub(r"[_/.\\:-]+", " ", spaced)
    return {stem(word) for word in tokenize(spaced) if len(word) >= 3}


def goal_concepts(goal: str) -> set[str]:
    """The goal's distinctive concepts (never "the", "with", "app" of every goal)."""
    from .ahl_dhikr import distinctive

    words = " ".join(distinctive(re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", goal or "")))
    return concepts(words)


def on_goal_score(goal: Iterable[str], tokens: set[str]) -> float:
    """Noisy-OR over the distinct goal concepts the item shows."""
    hits = 0
    for concept in goal:
        if concept in tokens:
            hits += 1
        elif len(concept) >= 4 and any(
            token.startswith(concept) or (len(token) >= 4 and concept.startswith(token))
            for token in tokens
        ):
            hits += 1
    return 1 - (1 - ON_GOAL_P) ** hits if hits else 0.0


def related(about: str, request: str) -> bool:
    """The request is about what a hand-off was about: one shared concept or more."""
    goal = goal_concepts(about)
    return bool(goal) and on_goal_score(goal, concepts(request)) >= ON_GOAL_P


def cusum(signals: Sequence[float], k: float = K, h: float = H) -> dict:
    """One-sided CUSUM over drift signals Dₜ ∈ [0, 1]."""
    chart: list[float] = []
    value, first = 0.0, -1
    for index, signal in enumerate(signals):
        value = max(0.0, value + float(signal) - k)
        chart.append(value)
        if first < 0 and value > h:
            first = index
    return {"alarm": first >= 0, "C": chart, "first_alarm": first}


def _targets(call: dict) -> tuple[str, set[str]]:
    found = call.get("params")
    params: dict = found if isinstance(found, dict) else {}
    shown = [
        str(value)
        for value in params.values()
        if isinstance(value, str) and value.strip() and "\n" not in value and len(value) <= 200
    ]
    tokens = concepts(" ".join([str(call.get("tool") or ""), *shown]))
    for value in params.values():
        if isinstance(value, str) and "\n" in value:
            tokens |= {token for name in _DEFINES.findall(value) for token in concepts(name)}
    label = " ".join([str(call.get("tool") or ""), *shown[:1]])[:120]
    return label, tokens


def drift(goal: str, request: str, calls: Sequence[dict]) -> dict:
    """This run's work against the goal: how many changes, the off-goal share,
    and which were off."""
    aim = goal_concepts(goal)
    asked = concepts(request)
    items = [
        _targets(call)
        for call in calls
        if isinstance(call, dict) and call.get("category") != "read" and call.get("ok", True)
    ]
    off = [label for label, tokens in items if on_goal_score(aim, tokens | asked) < ON_GOAL_P]
    return {
        "items": len(items),
        "score": round(len(off) / len(items), 4) if items else 0.0,
        "off_goal": off[:OFF_GOAL_SHOWN],
    }


def step(owner: str, scope: str, signal: float) -> dict:
    """Advance the scope's chart by this run's drift; kept per person, no words.
    With no store the chart starts from zero for this run (still a note)."""
    import sqlite3

    from memory import azm

    previous, runs = 0.0, 0
    conn = None
    try:
        conn = azm.connect(owner, create=True)
        if conn is not None:
            row = conn.execute(
                "SELECT cusum, runs FROM niyyah WHERE scope = ?", (scope,)
            ).fetchone()
            if row:
                previous, runs = float(row[0]), int(row[1])
    except (OSError, sqlite3.Error):
        conn = None
    value = max(0.0, previous + float(signal) - K)
    if conn is not None:
        try:
            conn.execute(
                "INSERT INTO niyyah (scope, cusum, runs, updated) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(scope) DO UPDATE SET cusum = excluded.cusum, runs = excluded.runs, "
                "updated = excluded.updated",
                (scope, value, runs + 1, datetime.now(UTC).isoformat()),
            )
            conn.commit()
        except sqlite3.Error:
            logger.warning("Niyyah chart not kept for %s", scope.partition(":")[0])
        finally:
            conn.close()
    return {"cusum": round(value, 4), "alarm": value > H, "runs": runs + 1}


def _first_request(history: Sequence[dict] | None, task: str) -> str:
    return next(
        (
            str(turn.get("content") or "")
            for turn in history or []
            if isinstance(turn, dict)
            and turn.get("role") == "user"
            and str(turn.get("content") or "").strip()
        ),
        task,
    )


def goal_of(
    owner: str, *, workspace_id: str | None, history: Sequence[dict] | None, task: str
) -> tuple[str, str, str] | None:
    """(scope, goal, where the goal came from) for this run, or None."""
    from automation import muraqabah

    watcher = muraqabah.current_watcher()
    if watcher:
        stated = str(watcher.get("goal") or "").strip()
        return (
            f"watcher:{watcher.get('id')}",
            stated or str(watcher.get("task") or task),
            "stated" if stated else "task",
        )
    if not workspace_id:
        return None
    stated = ""
    try:
        from workspace.store import WorkspaceStore

        stated = str(WorkspaceStore(owner).goal(workspace_id) or "").strip()
    except Exception:  # noqa: BLE001 - a project not readable here keeps the first request
        stated = ""
    if stated:
        return f"project:{workspace_id}", stated, "stated"
    return f"project:{workspace_id}", _first_request(history, task), "first_request"


def note(
    owner: str,
    *,
    workspace_id: str | None,
    history: Sequence[dict] | None,
    task: str,
    calls: Sequence[dict],
) -> dict | None:
    """``usage.niyyah`` for a run in a project or watcher: None outside them, and
    when no work moved and the chart is at rest."""
    from .amanah import clean_message

    found = goal_of(owner, workspace_id=workspace_id, history=history, task=task)
    if found is None:
        return None
    scope, goal, source = found
    goal = clean_message(goal)
    measured = drift(goal, task, calls)
    chart = step(owner, scope, measured["score"])
    if not measured["items"] and not chart["cusum"]:
        return None
    return {
        "scope": scope.partition(":")[0],
        "goal": " ".join(goal.split())[:200],
        "goal_source": source,
        "work": measured["items"],
        "drift": measured["score"],
        "cusum": chart["cusum"],
        "alarm": chart["alarm"],
        "off_goal": measured["off_goal"],
    }


def summary_line(found: dict[str, Any] | None) -> str:
    """The note in words, for a watcher's notice."""
    if not found or not found.get("alarm"):
        return ""
    return f"_Niyyah: this work has drifted from the goal “{found['goal']}”._"
