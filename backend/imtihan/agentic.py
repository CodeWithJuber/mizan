"""Agentic Imtihan: tasks an agent must carry out with tools, judged on the final state.

Following the agent-evaluation practice of Artificial Analysis (AutomationBench:
programmatic checks of the final environment state, a guardrail violation
scores 0) and Terminal-Bench (a task passes only when its checks pass), each
task gives:

- **instructions** in markdown, and **seed files** written into a fresh project
- optional **faults** (a tool fails N times: does the agent recover?) and
  **fixtures** (the pages the web tools return: needle-in-a-haystack reading)
- a **judge**: files (exists, unchanged, contains, equals as JSON or CSV), a
  command run in the project's sandbox (its exit code), and the answer (exact
  numbers, required words, the source it must cite, words it must not say)
- **guardrails**: things the agent must not do (delete a file, create one)

Two arms run the same task in their own fresh projects:

- **base**: the same model in a plain tool loop (model chooses every call)
- **mizan**: MIZAN, which plans, acts and checks with the model as its language

Both arms' tool calls pass the same gates and run in the same isolated sandbox.
Each run also measures the four agentic dimensions: tool-call accuracy,
groundedness, error recovery and latency.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import time
from pathlib import Path
from typing import Any

from tadbir import trace

TASKS_FILE = Path(__file__).parent / "agentic" / "tasks.jsonl"
TOOLS = (
    "workspace_glob", "workspace_read", "workspace_write", "workspace_edit", "workspace_grep",
    "workspace_run", "web_browse", "web_search",
)  # fmt: skip
MAX_TURNS = 16
BASE_SYSTEM = (
    "You are a capable assistant working inside a software project. Use the tools to carry "
    "out the user's task completely, then reply with a short final answer."
)
# A tool receipt that says the call itself was wrong (not that the work failed).
_INVALID = re.compile(
    r"unknown tool|not offered|input validation failed|missing required|unexpected keyword|"
    r"invalid (?:argument|parameter|path)|is not permitted|required positional",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
_FENCE = re.compile(r"```.*?```", re.DOTALL)


def load() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    return [json.loads(line) for line in TASKS_FILE.read_text("utf-8").splitlines() if line.strip()]


def is_agentic(task: dict) -> bool:
    return "instructions" in task


# ── The two arms ─────────────────────────────────────────────────────────


async def base_arm(agent: Any, instructions: str, tools: list[dict]) -> dict:
    """The model alone in a plain tool loop: it chooses every call."""
    from agents.base import _model_directed, bounded_tool_result
    from api.usage import build_usage_block, build_usage_summary
    from providers import assistant_turn_content, effective_limits, provider_retry_delay

    provider, model = getattr(agent, "ai_client", None), getattr(agent, "ai_model", None)
    if provider is None:
        return {"text": "", "error": "No hosted language model is configured", "calls": []}
    offered = {tool["name"] for tool in tools}
    messages: list[dict] = [{"role": "user", "content": instructions}]
    calls: list[dict] = []
    usage: list[dict] = []
    text, tool_ms, started = "", 0.0, time.perf_counter()
    max_tokens = max(1, min(4000, effective_limits(provider, model or "")[1]))
    for _turn in range(MAX_TURNS):
        sent = time.perf_counter()
        response = None
        for attempt in range(2):  # one retry after a rate limit, as Lisan gets
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        provider.create, model=model, max_tokens=max_tokens, system=BASE_SYSTEM,
                        messages=messages, tools=tools,
                    ),
                    180,
                )  # fmt: skip
                break
            except Exception as exc:  # noqa: BLE001 - provider errors vary
                delay = provider_retry_delay(exc, attempt)
                if delay is None or attempt:
                    return {"text": text, "error": f"Model error: {type(exc).__name__}",
                            "calls": calls, "usage": build_usage_summary(usage),
                            "tool_ms": tool_ms}  # fmt: skip
                await asyncio.sleep(delay)
        usage.append({"response": response, "latency_ms": (time.perf_counter() - sent) * 1000})
        blocks = list(getattr(response, "content", []) or [])
        text = "".join(getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text")
        uses = [b for b in blocks if getattr(b, "type", "") == "tool_use"]
        if not uses:
            break
        messages.append({"role": "assistant", "content": assistant_turn_content(response)})
        results = []
        for block in uses:
            began = time.perf_counter()
            if block.name not in offered:
                result: Any = {"error": f"Unknown tool {block.name}: it was not offered"}
            else:
                token = _model_directed.set(True)
                try:
                    result = await agent._execute_tool_safe(block.name, dict(block.input or {}))
                except Exception as exc:  # noqa: BLE001 - a receipt, as a real agent sees it
                    result = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                finally:
                    _model_directed.reset(token)
            tool_ms += (time.perf_counter() - began) * 1000
            calls.append({"name": block.name, "input": dict(block.input or {}), "result": result})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": bounded_tool_result(result, 12000),
                }  # fmt: skip
            )
        messages.append({"role": "user", "content": results})
    return {
        "text": text,
        "error": None,
        "calls": calls,
        "usage": build_usage_summary(
            [
                build_usage_block(
                    {"response": u["response"], "latency_ms": round(u["latency_ms"], 1)}
                )
                for u in usage
            ]  # fmt: skip
        ),
        "model_calls": len(usage),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "tool_ms": round(tool_ms, 1),
    }


async def mizan_arm(agent: Any, instructions: str) -> dict:
    from tadbir import muqabala

    agent._last_tool_results = []
    data = await muqabala.mizan_arm(agent, instructions, {"history": []})
    calls = [
        {"name": item.get("name"), "input": {}, "result": item.get("result")}
        for item in list(getattr(agent, "_last_tool_results", []) or [])
    ]
    timings = getattr(agent, "_execution_timings", {}) or {}
    return {**data, "calls": calls, "tool_ms": round(float(timings.get("tool_ms", 0.0)), 1)}


# ── The judge ────────────────────────────────────────────────────────────


_WORDS = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
_NUMBER_WORD = re.compile(r"\b(" + "|".join(_WORDS) + r")\b", re.IGNORECASE)


def _numbers(text: str) -> list[float]:
    """Numbers in the text, written in digits or as words ("three items")."""
    found = []
    for raw in _NUMBER.findall(text or ""):
        try:
            found.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    found += [float(_WORDS[word.lower()]) for word in _NUMBER_WORD.findall(text or "")]
    return found


def _close(value: float, candidates: list[float]) -> bool:
    return any(abs(value - c) <= max(0.005, abs(value) * 1e-6) for c in candidates)


def _json_equal(found: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return (
            isinstance(found, dict)
            and set(found) == set(expected)
            and all(_json_equal(found[key], expected[key]) for key in expected)
        )
    if isinstance(expected, list):
        return (
            isinstance(found, list)
            and len(found) == len(expected)
            and all(_json_equal(a, b) for a, b in zip(found, expected, strict=True))
        )
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        return isinstance(found, int | float) and _close(float(found), [float(expected)])
    return bool(found == expected)


def _read(store: Any, project: str, path: str) -> str | None:
    try:
        return str(store.read(project, path)["content"])
    except Exception:  # noqa: BLE001 - a missing or unreadable file
        return None


async def judge(task: dict, store: Any, project: str, answer: str) -> dict:
    """Objectives met on the final state, and whether any guardrail was broken."""
    spec = task.get("judge", {})
    seeded = task.get("files", {})
    objectives: list[dict] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        objectives.append({"check": name, "pass": bool(passed), "detail": detail[:200]})

    for rule in spec.get("files", []):
        path = rule["path"]
        content = _read(store, project, path)
        if rule.get("unchanged"):
            check(f"{path} unchanged", content == seeded.get(path))
            continue
        if content is None:
            check(f"{path} exists", False, "missing")
            continue
        if "json_equals" in rule:
            try:
                check(f"{path} is correct", _json_equal(json.loads(content), rule["json_equals"]))
            except ValueError:
                check(f"{path} is correct", False, "not valid JSON")
        if "csv_equals" in rule:
            rows = [
                [cell.strip() for cell in row] for row in csv.reader(io.StringIO(content)) if row
            ]
            check(f"{path} is correct", rows == rule["csv_equals"], json.dumps(rows[:4]))
        for word in rule.get("contains", []):
            check(f"{path} mentions {word}", word.lower() in content.lower())
        if rule.get("contains_any"):
            check(
                f"{path} has the content",
                any(w.lower() in content.lower() for w in rule["contains_any"]),
            )
    command = spec.get("command")
    if command:
        from workspace.execution import run_project

        try:
            run = await run_project(store, project, command["run"], "shell", 60)
            check(f"`{command['run']}` passes", run.get("exit_code") == command.get("exit_code", 0),
                  str(run.get("stderr") or run.get("stdout") or "")[-200:])  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - the sandbox is part of the test
            check(f"`{command['run']}` passes", False, f"sandbox: {exc}")
    wanted = spec.get("answer", {})
    lowered = (answer or "").lower()
    for word in wanted.get("contains", []):
        check(f"answer says {word}", word.lower() in lowered)
    numbers = _numbers(answer)
    for value in wanted.get("numbers", []):
        check(f"answer gives {value}", _close(float(value), numbers))
    for url in wanted.get("sources", []):
        check(f"answer cites {url}", url.lower().rstrip("/") in lowered)
    for word in wanted.get("none", []):
        check(f"answer avoids {word}", word.lower() not in lowered)

    broken = []
    for rule in task.get("guardrails", []):
        content = _read(store, project, rule["path"])
        if rule.get("unchanged") and content != seeded.get(rule["path"]):
            broken.append(f"{rule['path']} was changed or deleted")
        if rule.get("absent") and content is not None:
            broken.append(f"{rule['path']} was created")
    met = sum(1 for item in objectives if item["pass"])
    total = len(objectives) or 1
    score = 0.0 if broken else met / total
    return {
        "pass": not broken and met == len(objectives) and bool(objectives),
        "score": round(score, 3),
        "objectives": objectives,
        "guardrails_broken": broken,
    }


# ── The four dimensions ──────────────────────────────────────────────────


def dimensions(task: dict, arm: dict, answer: str) -> dict:
    calls = arm.get("calls") or []
    invalid = sum(
        1 for call in calls
        if isinstance(call.get("result"), dict) and _INVALID.search(str(call["result"].get("error") or ""))
    )  # fmt: skip
    # Groundedness: every number in the answer appears in what the agent was given or read.
    sources = [task.get("instructions", ""), *task.get("files", {}).values()]
    for tool_pages in (task.get("fixtures") or {}).values():
        for page in tool_pages.values():
            sources.append(json.dumps(page, ensure_ascii=False))
    sources += [json.dumps(call.get("result"), ensure_ascii=False, default=str) for call in calls]
    known = _numbers(" ".join(sources))
    # Code and diffs in the answer show work; they state no claim (as in Isnad).
    prose = _FENCE.sub(" ", answer or "")
    claimed = [n for n in _numbers(prose) if abs(n) >= 10 or not float(n).is_integer()]
    grounded = sum(1 for n in claimed if _close(n, known))
    usage = arm.get("usage") or {}
    return {
        "tool_calls": len(calls),
        "invalid_calls": invalid,
        "tool_accuracy": round(1 - invalid / len(calls), 3) if calls else None,
        "numbers_claimed": len(claimed),
        "groundedness": round(grounded / len(claimed), 3) if claimed else None,
        "faulted": bool(task.get("faults")),
        "latency_ms": arm.get("latency_ms"),
        "model_ms": usage.get("latency_ms"),
        "tool_ms": arm.get("tool_ms"),
    }


# ── One task, both arms ──────────────────────────────────────────────────


async def run_task(agent: Any, task: dict, attempt: int, owner: str) -> dict:
    from security.auth import current_user_id
    from workspace.context import bind_workspace, reset_workspace
    from workspace.store import WorkspaceStore

    store = WorkspaceStore(current_user_id() or owner)
    schemas = [s for s in agent.get_tool_schemas() if s.get("name") in TOOLS]
    rows, details = [], {}
    for arm in ("base", "mizan"):
        project = store.create(f"imtihan-{task['id']}-{arm}", reserved=True)["id"]
        try:
            for path, content in task.get("files", {}).items():
                store.write(project, path, content)
            binding = bind_workspace(project)
            try:
                with (
                    trace.bind_faults(task.get("faults")),
                    trace.bind_fixtures(task.get("fixtures")),
                ):
                    if arm == "base":
                        data = await base_arm(agent, task["instructions"], schemas)
                    else:
                        data = await mizan_arm(agent, task["instructions"])
            finally:
                reset_workspace(binding)
            answer = str(data.get("text") or "")
            verdict = await judge(task, store, project, answer)
            measured = dimensions(task, data, answer)
            usage = data.get("usage") or {}
            rows.append({
                "task_id": task["id"], "block": task["block"], "arm": arm, "attempt": attempt,
                "pass": verdict["pass"], "score": verdict["score"],
                "detail": "; ".join(
                    o["check"] for o in verdict["objectives"] if not o["pass"]
                )[:300] or ("guardrail broken" if verdict["guardrails_broken"] else "all objectives met"),
                "latency_ms": data.get("latency_ms"), "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"), "cost_usd": usage.get("cost_usd"),
                "model_calls": data.get("model_calls"), "tool_calls": measured["tool_calls"],
                "agentic": measured, "guardrails_broken": verdict["guardrails_broken"],
                **({"error": str(data["error"])[:300]} if data.get("error") and not answer else {}),
            })  # fmt: skip
            details[arm] = {
                "text": answer[:4000],
                "objectives": verdict["objectives"],
                "calls": [
                    {
                        "name": c.get("name"),
                        "input": c.get("input"),
                        "error": (c.get("result") or {}).get("error")
                        if isinstance(c.get("result"), dict)
                        else None,
                    }
                    for c in (data.get("calls") or [])[:40]
                ],  # fmt: skip
            }
        finally:
            try:
                store.remove(project)
            except Exception:  # noqa: BLE001 - cleanup is best effort
                pass
    return {"rows": rows, "compare": {"prompt": task["instructions"], "agentic": details}}


def summarize(results: list[dict]) -> dict:
    """The four dimensions per arm, over every agentic task that ran."""
    summary: dict[str, Any] = {}
    for arm in ("base", "mizan"):
        rows = [r for r in results if r["arm"] == arm and r.get("agentic")]
        if not rows:
            continue
        measured = [r["agentic"] for r in rows]
        calls = sum(m["tool_calls"] for m in measured)
        invalid = sum(m["invalid_calls"] for m in measured)
        claimed = [m for m in measured if m["groundedness"] is not None]
        faulted = [r for r in rows if r["agentic"]["faulted"]]
        latencies = sorted(float(m["latency_ms"] or 0) for m in measured)
        summary[arm] = {
            "tasks": len(rows),
            "success": round(sum(r["pass"] for r in rows) / len(rows), 3),
            "objectives": round(sum(r["score"] for r in rows) / len(rows), 3),
            "tool_accuracy": round(1 - invalid / calls, 3) if calls else None,
            "groundedness": round(sum(m["groundedness"] for m in claimed) / len(claimed), 3)
            if claimed
            else None,  # fmt: skip
            "recovery": round(sum(r["pass"] for r in faulted) / len(faulted), 3)
            if faulted
            else None,
            "guardrail_violations": sum(1 for r in rows if r.get("guardrails_broken")),
            "latency_median_ms": latencies[len(latencies) // 2] if latencies else None,
            "tool_calls": calls,
        }
    return summary
