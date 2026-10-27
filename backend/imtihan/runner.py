"""Run the Imtihan: every task to the base model alone and to MIZAN, scored by rule."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from security.approvals import ApprovalContext, bind_approvals
from tadbir import hadith, muqabala, quran, trace
from tadbir.waqt import bind_timezone

from . import report, scorers

logger = logging.getLogger("mizan.imtihan")

TASKS_DIR = Path(__file__).parent / "tasks"
KEEP_RUNS = 20
MAX_REPEATS = 3
_JOBS: dict[str, dict] = {}


def load_tasks(blocks: list[str] | None = None) -> list[dict]:
    tasks = []
    for path in sorted(TASKS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                tasks.append(json.loads(line))
    order = [
        "exactness", "scripture", "abstention", "honesty", "injection", "knowledge",
        "consistency", "multilingual", "learning", "safety", "code", "arc",
    ]  # fmt: skip
    tasks.sort(key=lambda task: order.index(task["block"]) if task["block"] in order else 99)
    if blocks:
        tasks = [task for task in tasks if task["block"] in blocks]
    return tasks


def catalog() -> list[dict]:
    counts: dict[str, int] = {}
    for task in load_tasks():
        counts[task["block"]] = counts.get(task["block"], 0) + 1
    return [{"block": block, "tasks": count} for block, count in counts.items()]


async def authentic_text(spec: dict) -> str | None:
    """The source text a scripture task is scored against, read from MIZAN's sources."""
    try:
        if spec["source"] == "quran":
            reference = quran.parse_reference(spec["reference"])
            if reference is None:
                return None
            data = await quran.fetch(reference, "en")
            return "\n".join(ayah["arabic"] for ayah in data.get("ayahs", []))
        narration = hadith.parse_reference(spec["reference"])
        if narration is None:
            return None
        data = await hadith.fetch(narration, "en")
        return str(data.get("arabic") or "") or None
    except Exception as exc:  # noqa: BLE001 - the task is reported as unscored
        logger.warning("Imtihan source text unavailable for %s: %s", spec.get("reference"), exc)
        return None


def _arm_row(task: dict, attempt: int, arm: str, data: dict, authentic: str | None) -> dict:
    usage = data.get("usage") or {}
    row: dict[str, Any] = {
        "task_id": task["id"],
        "block": task["block"],
        "arm": arm,
        "attempt": attempt,
        "latency_ms": data.get("latency_ms"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cost_usd": usage.get("cost_usd"),
        "model_calls": data.get("model_calls"),
        "tool_calls": data.get("tool_calls"),
    }
    if data.get("error") and not data.get("text"):
        row.update({"pass": False, "error": str(data["error"])[:300], "detail": "no answer"})
        return row
    scored = scorers.score(task["score"], data.get("text", ""), authentic)
    row.update(
        {
            "pass": bool(scored["pass"]),
            "detail": scored["detail"],
            "confidence": scored.get("confidence"),
        }
    )
    if scored.get("error"):
        row["error"] = scored["detail"]
    return row


async def run_task(agent: Any, task: dict, attempt: int, authentic: str | None) -> dict:
    history = list(task.get("history") or [])
    context = {"history": history}
    with trace.bind_faults(task.get("fault")):
        compared = await muqabala.compare(agent, task["prompt"], context, history)
    rows = [_arm_row(task, attempt, arm, compared[arm], authentic) for arm in report.ARMS]
    for row in rows:
        graded = (compared.get("checks", {}).get("isnad") or {}).get(row["arm"]) or {}
        row["supported"] = graded.get("supported")
        row["fabricated"] = (graded.get("counts") or {}).get("mawdu", 0)
    return {"rows": rows, "compare": muqabala._trimmed(compared)}


async def run_suite(
    agent: Any,
    *,
    owner: str,
    blocks: list[str] | None = None,
    repeats: int = 1,
    progress: Callable[[int, int, str], Awaitable[None] | None] | None = None,
) -> dict:
    tasks = load_tasks(blocks)
    repeats = max(1, min(MAX_REPEATS, int(repeats)))
    total = len(tasks) * repeats
    sources = {
        task["id"]: await authentic_text(task["score"])
        for task in tasks
        if task["score"]["kind"] == "quote"
    }
    results: list[dict] = []
    attempts: list[dict] = []
    done = 0
    approvals = ApprovalContext(owner, f"imtihan-{uuid.uuid4().hex}", "auto")
    with bind_approvals(approvals), bind_timezone("UTC"):
        for attempt in range(1, repeats + 1):
            for task in tasks:
                try:
                    outcome = await run_task(agent, task, attempt, sources.get(task["id"]))
                except Exception as exc:  # noqa: BLE001 - one task never stops the suite
                    logger.warning("Imtihan task %s failed: %s", task["id"], exc)
                    outcome = {
                        "rows": [
                            {
                                "task_id": task["id"],
                                "block": task["block"],
                                "arm": arm,
                                "attempt": attempt,
                                "pass": False,
                                "error": type(exc).__name__,
                            }
                            for arm in report.ARMS
                        ],
                        "compare": None,
                    }
                results.extend(outcome["rows"])
                attempts.append(
                    {"task_id": task["id"], "attempt": attempt, "compare": outcome["compare"]}
                )
                done += 1
                if progress is not None:
                    maybe = progress(done, total, task["id"])
                    if asyncio.iscoroutine(maybe):
                        await maybe
    return {
        "tasks": [
            {key: task[key] for key in ("id", "block", "prompt", "source", "group") if key in task}
            for task in tasks
        ],
        "repeats": repeats,
        "results": results,
        "attempts": attempts,
        "report": report.summarize(results, tasks),
    }


# ── background runs and their history ────────────────────────────────────


def _db() -> sqlite3.Connection:
    directory = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "imtihan"
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "runs.db")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at REAL, status TEXT, "
        "summary TEXT, data TEXT)"
    )
    return connection


def _summary(run: dict) -> dict:
    data = run.get("result") or {}
    found = data.get("report", {})
    return {
        "id": run["id"],
        "created_at": run["created_at"],
        "status": run["status"],
        "model": run.get("model"),
        "repeats": run.get("repeats"),
        "blocks": run.get("blocks"),
        "index": found.get("index"),
        "error": run.get("error"),
    }


def _save(run: dict) -> None:
    with _db() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?)",
            (
                run["id"],
                run["created_at"],
                run["status"],
                json.dumps(_summary(run), ensure_ascii=False),
                json.dumps(run.get("result") or {}, ensure_ascii=False, default=str),
            ),
        )
        connection.execute(
            "DELETE FROM runs WHERE id NOT IN "
            "(SELECT id FROM runs ORDER BY created_at DESC LIMIT ?)",
            (KEEP_RUNS,),
        )


def _list() -> list[dict]:
    with _db() as connection:
        rows = connection.execute("SELECT summary FROM runs ORDER BY created_at DESC").fetchall()
    return [json.loads(row[0]) for row in rows]


def _load(run_id: str) -> dict | None:
    with _db() as connection:
        row = connection.execute(
            "SELECT summary, data FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
    if not row:
        return None
    return {**json.loads(row[0]), "result": json.loads(row[1])}


def start(agent: Any, *, owner: str, blocks: list[str] | None, repeats: int) -> dict:
    """Start a run in the background; its progress is readable while it runs."""
    if any(job["status"] == "running" for job in _JOBS.values()):
        raise RuntimeError("An Imtihan run is already in progress")
    run_id = uuid.uuid4().hex
    tasks = load_tasks(blocks)
    run: dict[str, Any] = {
        "id": run_id,
        "created_at": time.time(),
        "status": "running",
        "model": getattr(agent, "ai_model", None),
        "blocks": blocks or sorted({task["block"] for task in tasks}),
        "repeats": max(1, min(MAX_REPEATS, int(repeats))),
        "progress": {"done": 0, "total": len(tasks) * max(1, min(MAX_REPEATS, int(repeats)))},
    }

    async def advance(done: int, total: int, task_id: str) -> None:
        run["progress"] = {"done": done, "total": total, "current": task_id}

    async def work() -> None:
        try:
            run["result"] = await run_suite(
                agent, owner=owner, blocks=blocks, repeats=run["repeats"], progress=advance
            )
            run["status"] = "complete"
        except asyncio.CancelledError:
            run["status"] = "cancelled"
        except Exception as exc:  # noqa: BLE001 - reported on the run
            logger.exception("Imtihan run failed")
            run["status"], run["error"] = "failed", type(exc).__name__
        finally:
            try:
                await asyncio.to_thread(_save, run)
            except Exception:  # noqa: BLE001
                logger.warning("Imtihan run could not be saved")

    run["task"] = asyncio.create_task(work())
    _JOBS[run_id] = run
    return public(run)


def public(run: dict) -> dict:
    return {key: value for key, value in run.items() if key != "task"}


def cancel(run_id: str) -> bool:
    run = _JOBS.get(run_id)
    if not run or run["status"] != "running":
        return False
    run["task"].cancel()
    return True


async def runs() -> list[dict]:
    live = [
        {**_summary(run), "progress": run.get("progress")}
        for run in _JOBS.values()
        if run["status"] == "running"
    ]
    return live + await asyncio.to_thread(_list)


async def get(run_id: str) -> dict | None:
    run = _JOBS.get(run_id)
    if run is not None and run["status"] == "running":
        return public(run)
    return await asyncio.to_thread(_load, run_id)
