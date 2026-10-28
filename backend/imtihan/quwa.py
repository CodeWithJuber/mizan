"""Quwa (قوى, faculties): the Imtihan read as a profile of ten cognitive faculties.

Google DeepMind's cognitive framework (Burnell et al., "Measuring Progress
Toward AGI: A Cognitive Framework", arXiv:2605.28405, 27 May 2026) describes
general intelligence as ten faculties and scores a system on each as the share
of a human sample it outperforms, on the same items under the same conditions.
Quwa does that with the Imtihan's own items:

- every task belongs to one faculty: its own ``faculty`` field, else its
  block's (``faculties.json``). Injection and safety measure what a system is
  inclined to do, not what it can do, so they are reported beside the profile
  (``propensity``) and never on it.
- per faculty and arm: the pass rate, its Wilson interval and the number of
  items, so an axis built from few items shows how little it can tell.
- the human panel: people answer the same text items (Developer → AGI Test →
  Human panel, ``/api/imtihan/panel``), scored by the same rules. A system's
  percentile is the share of panel members it outperforms on the items each of
  them answered (ties count half). Its Morris level is read from the lower end
  of that interval, so no level is claimed that the panel does not support.
- anchors: published human results of the benchmarks some blocks are drawn
  from (ARC-AGI-2, TruthfulQA), shown as context and never used as the
  percentile, since they were measured on other items.

The panel's answers are kept in ``$MIZAN_DATA_DIR/imtihan/panel.db`` under the
pseudonym the administrator gives each person; nothing else about them.
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import report, scorers

_FILE = Path(__file__).with_name("faculties.json")


@lru_cache(maxsize=1)
def data() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(_FILE.read_text(encoding="utf-8"))
    return found


def faculties() -> list[dict]:
    return list(data()["faculties"])


def faculty_of(task: dict) -> str | None:
    """The faculty a task measures, or None for a propensity block."""
    if task.get("block") in data()["propensity"]:
        return None
    named = task.get("faculty") or data()["blocks"].get(task.get("block", ""))
    return str(named) if named else None


def answerable(task: dict) -> bool:
    """A person can answer it in words: not a sandboxed project, not a game, not code
    that is run against tests."""
    spec = task.get("score") or {}
    return bool(
        task.get("prompt")
        and "instructions" not in task
        and "game" not in task
        and faculty_of(task)
        and not (spec.get("kind") == "locked" and spec.get("task") == "coding")
    )


def level(low: float | None) -> str | None:
    """The highest Morris level the lower end of the percentile interval reaches, or
    None below Competent (the 50th percentile)."""
    if low is None:
        return None
    for step in data()["levels"]:
        if low >= step["at"]:
            return str(step["level"])
    return None


def _by_task(results: list[dict], arm: str, ids: set[str]) -> dict[str, float]:
    """Each task's pass rate over its attempts, for one arm."""
    seen: dict[str, list[bool]] = {}
    for row in results:
        if row["arm"] == arm and row["task_id"] in ids and not row.get("error"):
            seen.setdefault(row["task_id"], []).append(bool(row["pass"]))
    return {task_id: sum(values) / len(values) for task_id, values in seen.items()}


def percentile(system: dict[str, float], panel: dict[str, dict[str, bool]]) -> dict | None:
    """The share of panel members the system outperforms on the items each answered."""
    beaten = 0.0
    compared = 0
    for answers in panel.values():
        common = [task_id for task_id in answers if task_id in system]
        if not common:
            continue
        mine = sum(system[task_id] for task_id in common) / len(common)
        theirs = sum(answers[task_id] for task_id in common) / len(common)
        compared += 1
        beaten += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0
    if not compared:
        return None
    interval = report.wilson(beaten, compared)
    return {
        "people": compared,
        "percentile": round(beaten / compared, 3),
        "interval": interval,
        "level": level(interval[0]),
    }


def _human(panel: dict[str, dict[str, bool]], ids: set[str]) -> dict | None:
    rates = [
        sum(answers[task_id] for task_id in common) / len(common)
        for answers in panel.values()
        if (common := [task_id for task_id in answers if task_id in ids])
    ]
    if not rates:
        return None
    return {
        "people": len(rates),
        "mean": round(sum(rates) / len(rates), 3),
        "median": round(statistics.median(rates), 3),
    }


def profile(
    results: list[dict], tasks: list[dict], panel: dict[str, dict[str, bool]] | None = None
) -> dict[str, Any]:
    """Per faculty: items, blocks, each arm's rate and interval, and against the panel."""
    panel = panel or {}
    owner = {task["id"]: faculty_of(task) for task in tasks}
    blocks_of: dict[str, set[str]] = {}
    for task in tasks:
        if owner[task["id"]]:
            blocks_of.setdefault(owner[task["id"]] or "", set()).add(task["block"])
    anchors = data()["anchors"]
    rows: list[dict[str, Any]] = []
    for spec in faculties():
        ids = {task_id for task_id, name in owner.items() if name == spec["key"]}
        entry: dict[str, Any] = {
            key: spec[key] for key in ("key", "name", "arabic", "script", "ayah", "words")
        }
        entry["composite"] = bool(spec.get("composite"))
        entry["items"] = len(ids)
        entry["blocks"] = sorted(blocks_of.get(spec["key"], set()))
        for arm in report.ARMS:
            scored = [
                row
                for row in results
                if row["arm"] == arm and row["task_id"] in ids and not row.get("error")
            ]
            passed = sum(1 for row in scored if row["pass"])
            entry[arm] = {
                "scored": len(scored),
                "passed": passed,
                "rate": round(passed / len(scored), 3) if scored else None,
                "interval": report.wilson(passed, len(scored)),
                "human": percentile(_by_task(results, arm, ids), panel),
            }
        rates = [entry[arm]["rate"] for arm in report.ARMS]
        entry["delta"] = round(rates[1] - rates[0], 3) if None not in rates else None  # type: ignore[operator]
        entry["panel"] = _human(panel, ids)
        entry["anchors"] = [
            {"block": block, **anchors[block]} for block in entry["blocks"] if block in anchors
        ]
        rows.append(entry)
    propensity: dict[str, Any] = {}
    for block in data()["propensity"]:
        ids = {task["id"] for task in tasks if task["block"] == block}
        if not ids:
            continue
        propensity[block] = {}
        for arm in report.ARMS:
            scored = [
                row
                for row in results
                if row["arm"] == arm and row["task_id"] in ids and not row.get("error")
            ]
            passed = sum(1 for row in scored if row["pass"])
            propensity[block][arm] = {
                "rate": round(passed / len(scored), 3) if scored else None,
                "interval": report.wilson(passed, len(scored)),
            }
    return {
        "framework": data()["framework"],
        "translation": data()["translation"],
        "levels_source": data()["levels_source"],
        "faculties": rows,
        "propensity": propensity,
        "panel_people": len(panel),
    }


# ── the human panel ──────────────────────────────────────────────────────


def _db() -> sqlite3.Connection:
    directory = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "imtihan"
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "panel.db")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS answers (person TEXT, task_id TEXT, answer TEXT, "
        "pass INTEGER, detail TEXT, by TEXT, created REAL, PRIMARY KEY (person, task_id))"
    )
    return connection


def panel_tasks() -> list[dict]:
    from . import runner

    return [
        {
            "id": task["id"],
            "block": task["block"],
            "faculty": faculty_of(task),
            "prompt": task["prompt"],
            "history": task.get("history") or [],
        }
        for task in runner.load_tasks()
        if answerable(task)
    ]


async def record(person: str, answers: dict[str, str], by: str) -> list[dict]:
    """Scores a person's answers by the items' own rules and keeps them."""
    import asyncio

    from . import runner

    known = {task["id"]: task for task in runner.load_tasks() if answerable(task)}
    scored: list[dict] = []
    for task_id, answer in answers.items():
        task = known.get(task_id)
        if task is None:
            continue
        authentic = (
            await runner.authentic_text(task["score"])
            if task["score"].get("kind") == "quote"
            else None
        )
        if task["score"].get("kind") == "quote" and not authentic:
            continue  # the source could not be read: not scored, not kept
        verdict = scorers.score(task["score"], answer, authentic)
        scored.append(
            {
                "task_id": task_id,
                "pass": bool(verdict["pass"]),
                "detail": verdict["detail"],
                "answer": answer,
            }
        )

    def save() -> None:
        with _db() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO answers VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        person,
                        s["task_id"],
                        s["answer"],
                        int(s["pass"]),
                        s["detail"],
                        by,
                        time.time(),
                    )
                    for s in scored
                ],
            )

    await asyncio.to_thread(save)
    return [{key: value for key, value in s.items() if key != "answer"} for s in scored]


def panel() -> dict[str, dict[str, bool]]:
    with _db() as connection:
        rows = connection.execute("SELECT person, task_id, pass FROM answers").fetchall()
    found: dict[str, dict[str, bool]] = {}
    for person, task_id, passed in rows:
        found.setdefault(person, {})[task_id] = bool(passed)
    return found


def people() -> list[dict]:
    owner = {task["id"]: task["faculty"] for task in panel_tasks()}
    listed = []
    for person, answers in sorted(panel().items()):
        by_faculty: dict[str, list[bool]] = {}
        for task_id, passed in answers.items():
            if owner.get(task_id):
                by_faculty.setdefault(owner[task_id] or "", []).append(passed)
        listed.append(
            {
                "person": person,
                "answered": len(answers),
                "faculties": {
                    name: round(sum(values) / len(values), 3) for name, values in by_faculty.items()
                },
            }
        )
    return listed


def forget(person: str) -> int:
    with _db() as connection:
        return connection.execute("DELETE FROM answers WHERE person = ?", (person,)).rowcount


def with_panel(run: dict) -> dict:
    """A stored run's profile recomputed against the panel as it is now."""
    result = run.get("result") or {}
    if not result.get("results") or not result.get("tasks"):
        return run
    found = panel()
    if not found:
        return run
    profile_now = profile(result["results"], result["tasks"], found)
    return {
        **run,
        "result": {**result, "report": {**result.get("report", {}), "faculties": profile_now}},
    }
