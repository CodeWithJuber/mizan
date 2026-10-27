"""Tadbir (تدبير): MIZAN's own orchestration of a request.

    Fahm (understand) → plan → act through MIZAN's tools → verify → express

MIZAN decides every step and runs every tool itself, through the same
``_execute_tool_safe`` gate as the agent loop (permissions, Fitrah, Izn,
approvals). The language model (Lisan) is called only for language: writing
or repairing a program, or wording an answer from verified facts; MIZAN
checks that wording (Furqan) and falls back to its own templates. Quran and
hadith text never pass through a language model.

Modes (``MIZAN_ORCHESTRATION``): ``mizan`` (default) performs every action
itself and lets the model answer the rest in words, with no tools at all;
``hybrid`` hands what MIZAN does not recognise to the model-driven agent
loop; ``llm`` turns Tadbir off. ``strict`` is the former name of ``mizan``.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import math
import os
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from agents.events import emit, summarize
from agents.execution_contract import tool_result_failed

from . import (
    amal,
    calc,
    express,
    fahm,
    hadith,
    hifz,
    isnad,
    majlis,
    project,
    qiyas,
    quran,
    silsila,
    taallum,
    trace,
    waqt,
)
from .express import fence, furqan, phrase
from .lisan import Lisan, LisanUnavailable

MODES = ("mizan", "hybrid", "strict", "llm")
MAX_REPAIRS = 2


def orchestration_mode() -> str:
    value = os.getenv("MIZAN_ORCHESTRATION", "mizan").strip().lower()
    value = "mizan" if value == "strict" else value  # strict is the former name
    return value if value in MODES else "mizan"


def full_orchestration() -> bool:
    """MIZAN performs every action; the model may only answer in words."""
    return orchestration_mode() == "mizan"


class Defer(Exception):  # noqa: N818 - control flow, not an error
    """MIZAN cannot complete this recipe; let the general agent loop try."""


@dataclass
class Outcome:
    text: str
    verified: bool
    facts: dict[str, Any] = field(default_factory=dict)
    tool_backed: bool = True
    # Whether the work itself succeeded, for routing evidence, when MIZAN can
    # confirm that but not the result's meaning (a tool ran without error).
    succeeded: bool | None = None
    # "evidence" when Lisan worded the answer from evidence MIZAN gathered:
    # each claim is then graded against it (Isnad). Otherwise a verified
    # outcome is MIZAN's own established work.
    provenance: str | None = None
    isnad: list[dict] = field(default_factory=list)


class Plan:
    """MIZAN's step list, shown live in the chat's Activity card."""

    def __init__(self, steps: list[str]):
        self.items = [{"content": step, "status": "pending"} for step in steps]
        self.current = -1

    async def advance(self) -> None:
        if 0 <= self.current < len(self.items):
            self.items[self.current]["status"] = "completed"
        self.current += 1
        if self.current < len(self.items):
            self.items[self.current]["status"] = "in_progress"
        await emit("todo", {"todos": deepcopy(self.items)})

    async def finish(self) -> None:
        for item in self.items:
            item["status"] = "completed"
        self.current = len(self.items)
        await emit("todo", {"todos": deepcopy(self.items)})

    async def mark(self, index: int, status: str) -> None:
        """One step's status, for steps that agents run side by side."""
        self.items[index]["status"] = status
        await emit("todo", {"todos": deepcopy(self.items)})


class Tadbir:
    def __init__(self, agent: Any, *, lisan: Lisan | None = None, coordinator: Any = None):
        # ``agent`` does the work through its own tool gate; ``coordinator`` is
        # the agent the user is talking to, whose chat receipts and metrics
        # record everything. Lisan is MIZAN's one language faculty.
        self.agent = agent
        self.coordinator = coordinator or agent
        self.lisan = lisan or Lisan(self.coordinator)
        self.plan: Plan | None = None
        self.workers: list[dict] = []
        self._stream = None
        self._nested = False
        self._assignment: str | None = None

    # ── entry point ──────────────────────────────────────────────────────

    async def handle(
        self, task: str, stream_callback=None, history: list[dict] | None = None
    ) -> dict | None:
        mode = orchestration_mode()
        if mode == "llm" or not isinstance(task, str) or not task.strip():
            return None
        parts = fahm.understand_parts(task)
        understanding = fahm.understand(task)
        if parts is None and understanding.intent in {"converse", "web_search"}:
            # "Find the next number", "search number theory": a follow-up about the
            # sequence asked earlier in this chat, which MIZAN takes from the history.
            earlier = silsila.from_history(history) if silsila.follow_up(task) else None
            if earlier:
                understanding = fahm.Understanding(
                    "silsila",
                    understanding.language,
                    0.8,
                    {"sequence": earlier, "understood_by": "conversation"},
                )
        self._stream = stream_callback
        started = time.time()
        if parts is not None:
            understanding = fahm.Understanding(
                "compound",
                fahm.detect_language(task),
                min(u.confidence for _part, u in parts),
                {"parts": [{"text": part, "intent": u.intent} for part, u in parts]},
            )
        example: dict | None = None
        if parts is None and self.lisan.available and fahm.partly_understood(task):
            # Several requests and MIZAN's recognisers place only some: Lisan
            # maps the whole message into steps, which MIZAN validates.
            planned = await self._lisan_plan(task, understanding)
            if len(planned) > 1:
                parts = planned
                understanding = fahm.Understanding(
                    "compound",
                    understanding.language,
                    0.6,
                    {
                        "parts": [{"text": part, "intent": u.intent} for part, u in parts],
                        "understood_by": "lisan_plan",
                    },
                )
        if parts is None and understanding.intent == "converse" and fahm.actionable(task):
            learned = self._learned_understanding(task, understanding)
            if learned is not None:
                understanding, example = learned
            elif self.lisan.available:
                # Lisan only translates the wording into MIZAN's actions; MIZAN
                # validates every step before acting on it.
                planned = await self._lisan_plan(task, understanding)
                if len(planned) == 1:
                    understanding = planned[0][1]
                elif planned:
                    parts = planned
                    understanding = fahm.Understanding(
                        "compound",
                        understanding.language,
                        0.6,
                        {
                            "parts": [{"text": part, "intent": u.intent} for part, u in parts],
                            "understood_by": "lisan_plan",
                        },
                    )
        handler = getattr(self, f"_{understanding.intent}", None)
        trace.event(
            "understand",
            understanding.intent,
            language=understanding.language,
            confidence=understanding.confidence,
            entities=understanding.to_dict()["entities"],
            by=understanding.entities.get("understood_by", "fahm"),
        )
        try:
            if parts is not None:
                outcome = await self._compound(parts)
            elif understanding.intent == "converse" or handler is None:
                # Words only: in "mizan" mode the agent answers with no tools.
                return None
            else:
                outcome = await self._delegate(task, understanding)
        except Defer:
            return None
        self._learn(task, understanding, example, outcome)
        if self.plan is not None:
            await self.plan.finish()
        trace.event(
            "plan",
            "result",
            steps=[item["content"] for item in self.plan.items] if self.plan else [],
            verified=outcome.verified,
            tool_backed=outcome.tool_backed,
            facts=outcome.facts,
        )
        if stream_callback:
            await stream_callback(outcome.text)
        status = (
            "verified_by_mizan"
            if outcome.verified
            else "evidence_observed"
            if outcome.tool_backed
            else "unverified_answer"
        )
        return {
            "success": True,
            "result": outcome.text,
            "duration_ms": (time.time() - started) * 1000,
            "agent": self.agent.name,
            "metrics_kind": "mizan_orchestration",
            "completion_status": status,
            "answer_delivered": True,
            "task_verified": outcome.verified,
            "capture_eligible": False,
            "orchestrator": "mizan",
            **({"isnad": isnad.summary(outcome.isnad)} if outcome.isnad else {}),
            "orchestration": {
                "by": "mizan",
                "mode": mode,
                **understanding.to_dict(),
                "plan": deepcopy(self.plan.items) if self.plan else [],
                "verified": outcome.verified,
                "language_model_calls": self.lisan.calls,
                "agents": self.workers,
            },
        }

    # ── Majlis: the agent that fits does the work ────────────────────────

    def _runner(self, worker: Any) -> Tadbir:
        runner = Tadbir(worker, lisan=self.lisan, coordinator=self.coordinator)
        runner._stream = self._stream
        return runner

    def _credit(self, worker: Any, intent: str, outcome: Outcome, language: str) -> Outcome:
        worked = outcome.verified if outcome.succeeded is None else outcome.succeeded
        estimate = majlis.record(self.coordinator, worker, intent, worked)
        trace.event(
            "learn", "majlis", agent=worker.name, intent=intent, worked=worked, estimate=estimate
        )
        role = majlis.ROLE_NAMES.get(getattr(worker, "role", ""), "general")
        self.workers.append(
            {"agent": worker.name, "role": role, "intent": intent, "verified": outcome.verified}
        )
        if worker is not self.coordinator:
            note = phrase("done_by_agent", language, name=worker.name, role=role)
            outcome.text = f"{outcome.text}\n\n_{note}_"
        outcome.isnad = self._isnad(outcome, intent)
        return outcome

    def _isnad(self, outcome: Outcome, intent: str) -> list[dict]:
        """Every claim of this outcome, graded by what supports it."""
        established = outcome.verified and outcome.provenance != "evidence"
        evidence = ""
        if not established:
            receipts = getattr(self.coordinator, "_last_tool_results", []) or []
            evidence = "\n".join(
                [json.dumps(outcome.facts, ensure_ascii=False, default=str)]
                + [summarize(receipt.get("result"), 20000) for receipt in receipts]
            )
        sources = outcome.facts.get("sources")
        return isnad.ledger(
            outcome.text,
            established=established,
            basis=isnad.BASIS.get(intent, "MIZAN verified it"),
            evidence=evidence,
            verified=outcome.verified,
            max_citation=sources if isinstance(sources, int) else 0,
        )

    async def _delegate(self, task: str, u: fahm.Understanding) -> Outcome:
        """One request: MIZAN chooses the agent, which runs MIZAN's recipe."""
        worker = majlis.choose(self.coordinator, u.intent)
        role = majlis.ROLE_NAMES.get(getattr(worker, "role", ""), "general")
        with trace.span("invoke_agent", worker.name, role=role, intent=u.intent) as record:
            if worker is self.agent:
                outcome = await getattr(self, f"_{u.intent}")(task, u)
            else:
                runner = self._runner(worker)
                runner._assignment = f"MIZAN gives this to {worker.name} ({role} agent)"
                try:
                    outcome = await getattr(runner, f"_{u.intent}")(task, u)
                finally:
                    self.plan = runner.plan
            record["attributes"]["verified"] = outcome.verified
        return self._credit(worker, u.intent, outcome, u.language)

    # ── Ta'allum: learning from verified work ────────────────────────────

    def _learned_understanding(
        self, task: str, fallback: fahm.Understanding
    ) -> tuple[fahm.Understanding, dict] | None:
        from security.auth import current_user_id

        found = taallum.recall(self.coordinator.adaptive, current_user_id() or "", task)
        if found is None:
            return None
        parsed, example = found
        understood = fahm.validate_parsed(parsed, task, fallback.language)
        if understood is None:
            return None
        understood.entities["understood_by"] = "mizan_learned"
        return understood, example

    def _learn(
        self, task: str, u: fahm.Understanding, example: dict | None, outcome: Outcome
    ) -> None:
        from security.auth import current_user_id

        store, user = self.coordinator.adaptive, current_user_id() or ""
        source = u.entities.get("understood_by")
        if source == "lisan":
            taallum.learn(store, user, task, u, outcome.verified)
            trace.event("learn", "taallum", kept=outcome.verified, intent=u.intent)
        elif source == "mizan_learned" and example is not None:
            taallum.reweigh(store, user, example, outcome.verified)
            trace.event("learn", "taallum", reused=True, worked=outcome.verified)

    # ── shared actions ───────────────────────────────────────────────────

    async def _begin(self, steps: list[str]) -> None:
        if self._nested:
            return  # a part of a compound request: the compound plan is shown
        if self._assignment:
            steps = [self._assignment, *steps]
        self.plan = Plan(steps)
        await self.plan.advance()
        if self._assignment:
            await self.plan.advance()

    async def _step(self) -> None:
        if self.plan is not None and not self._nested:
            await self.plan.advance()

    async def _compound(self, parts: list[tuple[str, fahm.Understanding]]) -> Outcome:
        """Several independent requests: each part to its agent, agents side by side."""
        assigned = [(part, u, majlis.choose(self.coordinator, u.intent)) for part, u in parts]
        self.plan = Plan(
            [f"{worker.name}: {part[:70]} ({u.intent})" for part, u, worker in assigned]
        )
        plan = self.plan
        results: list[Outcome | None] = [None] * len(assigned)
        groups: dict[str, list[int]] = {}
        for index, (_part, _u, worker) in enumerate(assigned):
            groups.setdefault(str(worker.id), []).append(index)

        async def run(indices: list[int]) -> None:
            # One agent does its parts in order; different agents work in parallel.
            for index in indices:
                part, u, worker = assigned[index]
                await plan.mark(index, "in_progress")
                runner = self._runner(worker)
                runner._nested = True
                with trace.span("invoke_agent", worker.name, intent=u.intent, part=part) as record:
                    try:
                        outcome = await getattr(runner, f"_{u.intent}")(part, u)
                    except Defer:
                        outcome = None
                    record["attributes"]["done"] = outcome is not None
                results[index] = outcome
                await plan.mark(index, "completed")

        await asyncio.gather(*(run(indices) for indices in groups.values()))
        if all(outcome is None for outcome in results):
            raise Defer  # nothing done: the agent loop takes the whole request
        texts: list[str] = []
        facts: list[dict] = []
        verified = True
        for (part, u, worker), outcome in zip(assigned, results, strict=True):
            if outcome is None:
                outcome = Outcome(phrase("part_not_done", u.language, part=part), False, {})
            else:
                outcome = self._credit(worker, u.intent, outcome, u.language)
            texts.append(outcome.text)
            facts.append(outcome.facts)
            verified = verified and outcome.verified
        ledger = [claim for outcome in results if outcome is not None for claim in outcome.isnad]
        return Outcome("\n\n---\n\n".join(texts), verified, {"parts": facts}, isnad=ledger)

    async def _tool(self, name: str, params: dict) -> dict:
        """Run one tool through the agent's full safety gate, visibly."""
        call_id = uuid.uuid4().hex
        await emit("tool_start", {"call_id": call_id, "name": name, "input": params})
        if self._stream:
            await self._stream("", chunk_type="tool_use", tool_name=name)
        started = time.perf_counter()
        with trace.span("execute_tool", name, input=params, agent=self.agent.name) as record:
            result = trace.injected_fault(name) or await self.agent._execute_tool_safe(name, params)
            if trace.active():
                record["attributes"]["ok"] = not tool_result_failed(result)
                record["attributes"]["result"] = summarize(result, 4000)
        self.coordinator._add_execution_time("tool_ms", started)
        await emit(
            "tool_result",
            {
                "call_id": call_id,
                "name": name,
                "ok": not tool_result_failed(result),
                "summary": summarize(result),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        self.coordinator._last_tool_results.append({"name": name, "result": result})
        return result if isinstance(result, dict) else {"result": result}

    async def _from_source(
        self,
        name: str,
        reference: str,
        fetch: Callable[[], Awaitable[dict]],
        summary: Callable[[dict], str],
    ) -> tuple[dict, str | None]:
        """Fetch from one of MIZAN's authentic text sources, shown like a tool call."""
        call_id = uuid.uuid4().hex
        await emit(
            "tool_start", {"call_id": call_id, "name": name, "input": {"reference": reference}}
        )
        started = time.perf_counter()
        data: dict = {}
        error: str | None = None
        with trace.span("execute_tool", name, reference=reference, source=True) as record:
            try:
                data = await fetch()
            except (
                quran.QuranUnavailable,
                hadith.HadithUnavailable,
                hadith.HadithNotFound,
            ) as exc:
                error = str(exc)
            record["attributes"]["ok"] = error is None
            record["attributes"]["result"] = error or summary(data)
        await emit(
            "tool_result",
            {
                "call_id": call_id,
                "name": name,
                "ok": error is None,
                "summary": error or summary(data),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return data, error

    def _allowed(self, name: str) -> bool:
        try:
            return bool(self.agent._chat_tool_allowed(name)) and name in self._tool_names()
        except Exception:  # noqa: BLE001
            return False

    def _tool_names(self) -> set[str]:
        return {str(item.get("name", "")) for item in self.agent.get_tool_schemas()}

    async def _phrase_with_lisan(
        self, request: str, facts: dict, language: str, fallback: str
    ) -> tuple[str, bool]:
        """Lisan's wording when Furqan accepts it; otherwise MIZAN's own."""
        if not self.lisan.available:
            return fallback, False
        try:
            text = await self.lisan.express(request, facts, language)
        except LisanUnavailable:
            return fallback, False
        if furqan(text, json.dumps(facts, ensure_ascii=False)):
            return fallback, False
        return text, True

    async def _lisan_plan(
        self, task: str, fallback: fahm.Understanding
    ) -> list[tuple[str, fahm.Understanding]]:
        """Lisan's steps that pass MIZAN's validation, with the words each covers."""
        try:
            steps = await self.lisan.plan_steps(task)
        except LisanUnavailable:
            return []
        planned = []
        for step in steps:
            understood = fahm.validate_parsed(step, task, fallback.language)
            if understood is None:
                continue
            words = str(step.get("text") or "").strip()[:500]
            planned.append((words if len(steps) > 1 and words else task, understood))
        return planned

    # ── recipes ──────────────────────────────────────────────────────────

    async def _capabilities(self, task: str, u: fahm.Understanding) -> Outcome:
        await self._begin(["Read MIZAN's live tool registry", "Reply"])
        names = {name for name in self._tool_names() if self._allowed(name)}
        lines = []
        if {"workspace_run"} & names:
            lines.append("code")
        lines.append("calc")
        lines.append("quran")
        lines.append("hadith")
        lines.append("waqt")
        if {"web_search", "web_browse"} & names:
            lines.append("web")
        if {"workspace_write", "workspace_edit"} & names:
            lines.append("files")
        if {"recall_memory"} & names:
            lines.append("memory")
        if "activate_skill" in names or any(n.startswith("mcp__") for n in names):
            lines.append("connectors")
        await self._step()
        language = u.language
        bullets = "\n".join(
            f"- {express.CAPABILITY_LINES[key].get(language, express.CAPABILITY_LINES[key]['en'])}"
            for key in lines
        )
        text = f"{phrase('capabilities', language)}\n\n{bullets}\n\n{phrase('capabilities_tail', language)}"
        return Outcome(text, True, {"capabilities": lines})

    async def _compute(self, task: str, u: fahm.Understanding) -> Outcome:
        await self._begin(
            ["Understand the arithmetic (Fahm)", "Calculate exactly (MIZAN)", "Reply"]
        )
        shown = str(u.entities["expression"]).strip()
        expression = calc.normalize(shown)
        try:
            value = calc.evaluate(expression)
        except calc.CalcError as exc:
            raise Defer from exc
        await self._step()
        rendered = calc.render(value)
        text = f"`{shown}` = **{rendered}**\n\n_{phrase('computed', u.language)}_"
        return Outcome(text, True, {"expression": expression, "value": rendered})

    async def _run(self, code: str, language: str) -> dict:
        return await self._tool(
            "workspace_run", {"command": code, "language": language, "timeout_s": 60}
        )

    def _run_text(self, run: dict, language: str) -> str:
        if run.get("error"):
            return phrase("not_run", language, reason=str(run["error"])[:300])
        code = run.get("exit_code")
        status = (
            phrase("ran_ok", language, ms=run.get("duration_ms", 0))
            if code == 0
            else phrase("ran_failed", language, code=code)
        )
        output = (str(run.get("stdout", "")) + str(run.get("stderr", ""))).strip()
        return f"{status}\n\n**{phrase('output', language)}**\n{fence(output or '(no output)', 'text')}"

    async def _run_code(self, task: str, u: fahm.Understanding) -> Outcome:
        if not self._allowed("workspace_run"):
            raise Defer
        generated = u.entities.get("generated_by") == "mizan"
        expression = u.entities.get("expression")
        await self._begin(
            [
                "Write the code (MIZAN)" if generated else "Read the code from the message",
                "Run it in MIZAN's isolated sandbox",
                "Check the result against MIZAN's own calculation"
                if expression
                else "Check the exit code and output",
                "Reply",
            ]
        )
        code, language = u.entities["code"], u.entities["code_language"]
        await self._step()
        run = await self._run(code, language)
        await self._step()
        verified = run.get("exit_code") == 0 and not run.get("error")
        notes = []
        if expression and verified:
            verified = _matches(
                str(run.get("stdout", "")), calc.evaluate(calc.normalize(expression))
            )
            if verified:
                notes.append(f"_{phrase('cross_checked', u.language)}_")
        text = "\n\n".join(
            [
                f"**{phrase('code', u.language)}**\n{fence(code, language)}",
                self._run_text(run, u.language),
                *notes,
            ]
        )
        return Outcome(text, verified, {"run": _run_facts(run)})

    async def _build_and_run(self, task: str, u: fahm.Understanding) -> Outcome:
        if not self._allowed("workspace_run") or not self.lisan.available:
            raise Defer
        language = u.entities["code_language"]
        from security.auth import current_user_id

        store, owner = self.coordinator.adaptive, current_user_id() or ""
        kept = hifz.recall(store, owner, task, language)
        if kept is not None:
            reused = await self._reuse_program(u, kept, store, owner)
            if reused is not None:
                return reused
        await self._begin(
            [
                "Understand the request (Fahm)",
                "Write the program (Lisan)",
                "Run it in MIZAN's isolated sandbox",
                "Check the result; repair if it failed",
                "Reply",
            ]
        )
        await self._step()
        try:
            code = await self.lisan.write_code(str(u.entities.get("request") or task), language)
        except LisanUnavailable as exc:
            raise Defer from exc
        await self._step()
        tries = 1
        run = await self._run(code, language)
        await self._step()
        while (run.get("exit_code") != 0 or run.get("error")) and tries <= MAX_REPAIRS:
            if run.get("declined") or "not permitted" in str(run.get("error", "")):
                break
            if run.get("error") and not run.get("stderr"):
                break  # the sandbox itself failed; rewriting the code cannot help
            error = str(run.get("stderr") or run.get("error") or run.get("stdout", ""))
            try:
                code = await self.lisan.fix_code(task, language, code, error)
            except LisanUnavailable:
                break
            tries += 1
            run = await self._run(code, language)
        verified = run.get("exit_code") == 0 and not run.get("error")
        parts = [
            f"**{phrase('code', u.language)}**\n{fence(code, language)}",
            self._run_text(run, u.language),
        ]
        if tries > 1 and verified:
            parts.append(f"_{phrase('repaired', u.language, tries=tries)}_")
        if verified:
            hifz.keep(store, owner, task, language, code, str(run.get("stdout", "")))
            trace.event("learn", "hifz", kept=True, language=language)
        return Outcome("\n\n".join(parts), verified, {"run": _run_facts(run), "attempts": tries})

    async def _reuse_program(
        self, u: fahm.Understanding, kept: dict, store: Any, owner: str
    ) -> Outcome | None:
        """Re-run a program MIZAN verified before; its output must match again."""
        language = kept["language"]
        await self._begin(
            [
                "Recall a program MIZAN verified before (Hifz)",
                "Run it in MIZAN's isolated sandbox",
                "Check the output matches what was verified",
                "Reply",
            ]
        )
        await self._step()
        run = await self._run(kept["code"], language)
        await self._step()
        worked = (
            run.get("exit_code") == 0
            and not run.get("error")
            and hifz.matches(kept, str(run.get("stdout", "")))
        )
        reliability = hifz.record(store, owner, kept, worked)
        trace.event("learn", "hifz", reused=True, worked=worked, reliability=reliability)
        if not worked:
            return None  # the kept program no longer holds: Lisan writes a new one
        parts = [
            f"**{phrase('code', u.language)}**\n{fence(kept['code'], language)}",
            self._run_text(run, u.language),
            f"_{phrase('hifz_reused', u.language, runs=int(kept.get('runs', 1)) + 1)}_",
        ]
        return Outcome("\n\n".join(parts), True, {"run": _run_facts(run), "reused": True})

    async def _qiyas(self, task: str, u: fahm.Understanding) -> Outcome:
        """Infer the rule from the examples; accept it only if it reproduces every one."""
        if not self._allowed("workspace_run") or not self.lisan.available:
            raise Defer
        puzzle = u.entities["puzzle"]
        examples = qiyas.describe(puzzle)
        total = len(puzzle["train"])
        await self._begin(
            [
                "Read the worked examples (MIZAN)",
                "Propose the rule as a program (Lisan)",
                f"Test the rule on all {total} examples in the sandbox (MIZAN)",
                "Revise the rule from the examples it got wrong",
                "Reply",
            ]
        )
        await self._step()
        try:
            program = await self.lisan.propose_rule(examples)
        except LisanUnavailable as exc:
            raise Defer from exc
        await self._step()
        best: tuple[int, str, dict | None] = (-1, program, None)
        attempts = 0
        for attempts in range(1, MAX_REPAIRS + 2):  # noqa: B007 - attempts is reported
            run = await self._run(qiyas.harness(program, puzzle), "python")
            report = qiyas.read(str(run.get("stdout", "")))
            fitted = qiyas.passed(report, puzzle)
            trace.event("verify", "qiyas", examples=total, reproduced=fitted, attempt=attempts)
            if fitted > best[0]:
                best = (fitted, program, report)
            if fitted == total or run.get("declined") or attempts > MAX_REPAIRS:
                break
            wrong = qiyas.failures(report, puzzle, str(run.get("stderr") or run.get("error", "")))
            try:
                program = await self.lisan.revise_rule(examples, program, wrong)
            except LisanUnavailable:
                break
        await self._step()
        fitted, program, report = best
        outputs = qiyas.test_outputs(report)
        proven = fitted == total and outputs is not None
        if proven:
            head = phrase("qiyas_proven", u.language, total=total)
        elif outputs is not None:
            head = phrase("qiyas_unproven", u.language, fitted=max(0, fitted), total=total)
        else:
            head = phrase("qiyas_no_rule", u.language, total=total)
        # The rule's program first and the answer last, as puzzle answers are read.
        parts = [head, f"**{phrase('code', u.language)}**\n{fence(program, 'python')}"]
        for index, grid in enumerate(outputs or [], 1):
            label = phrase("qiyas_answer", u.language, n=index)
            parts.append(f"**{label}**\n{fence(qiyas.render(grid), 'json')}")
        facts = {
            "examples": total,
            "reproduced": max(0, fitted),
            "attempts": attempts,
            "test_outputs": outputs,
        }
        return Outcome("\n\n".join(parts), proven, facts, succeeded=proven)

    async def _silsila(self, task: str, u: fahm.Understanding) -> Outcome:
        """A sequence's next term, from a rule proven on every given term."""
        seq: list[int] = u.entities["sequence"]
        can_test = self._allowed("workspace_run") and self.lisan.available
        await self._begin(
            [
                f"Read the {len(seq)} terms (MIZAN)",
                "Try MIZAN's exact methods: polynomials in n and in the n-th prime, recurrences",
                "Look the terms up in the OEIS",
                "Test Lisan's proposed rule on every term in the sandbox",
                "Reply",
            ]
        )
        await self._step()
        rules = silsila.own_rules(seq)
        trace.event("verify", "silsila.own", rules=[rule.to_dict() for rule in rules])
        await self._step()
        matches = await self._external(
            "oeis_search",
            {"terms": seq},
            silsila.oeis(seq),
            lambda found: f"{len(found)} matching sequence(s)",
        )
        await self._step()
        tested: tuple[str, dict] | None = None
        tries = 0
        if not rules and not matches and can_test:
            try:
                program = await self.lisan.propose_sequence_rule(seq)
            except LisanUnavailable:
                program = ""
            while program and tries <= MAX_REPAIRS:
                tries += 1
                run = await self._run(silsila.harness(program, seq), "python")
                report = silsila.read(str(run.get("stdout", "")))
                trace.event("verify", "silsila.lisan", attempt=tries, report=report)
                if silsila.proven(report, seq):
                    tested = (program, report or {})
                    break
                if run.get("declined") or (run.get("error") and not run.get("stderr")):
                    break
                if tries > MAX_REPAIRS:
                    break
                try:
                    program = await self.lisan.revise_sequence_rule(
                        seq, program, silsila.feedback(report, str(run.get("stderr", "")))
                    )
                except LisanUnavailable:
                    break
        await self._step()
        language = u.language
        candidates: list[tuple[int, str]] = []
        for rule in rules:
            candidates.append(
                (
                    rule.next,
                    phrase(
                        "silsila_rule",
                        language,
                        formula=rule.formula,
                        method=rule.method,
                        total=len(seq),
                    ),
                )  # fmt: skip
            )
        for match in matches:
            candidates.append(
                (
                    match["next"],
                    phrase("silsila_oeis", language, id=match["id"], name=match["name"]),
                )
            )
        if tested is not None:
            program, report = tested
            candidates.append(
                (
                    int(report["next"]),
                    phrase(
                        "silsila_tested",
                        language,
                        rule=silsila.rule_comment(program) or "—",
                        total=len(seq),
                    ),
                )  # fmt: skip
            )
        terms = ", ".join(str(value) for value in seq)
        if not candidates:
            tried = phrase("silsila_tried_lisan", language, tries=tries) if tries else ""
            text = phrase("silsila_none", language, total=len(seq), terms=terms, lisan=tried)
            return Outcome(text, False, {"sequence": seq, "rules": []}, succeeded=False)
        answers = sorted({value for value, _ in candidates})
        lines = []
        if len(answers) == 1:
            lines.append(phrase("silsila_next", language, value=answers[0], terms=terms))
        else:
            lines.append(phrase("silsila_several", language, total=len(seq), terms=terms))
        for value, reason in candidates:
            lines.append(f"- **{value}**: {reason}")
        facts = {
            "sequence": seq,
            "next": answers,
            "rules": [rule.to_dict() for rule in rules],
            "oeis": matches,
        }
        return Outcome("\n".join(lines), True, facts)

    async def _external(
        self, name: str, params: dict, work: Awaitable[Any], summary: Callable[[Any], str]
    ) -> Any:
        """A read from an outside reference MIZAN trusts (not a user tool), shown like a tool call."""
        call_id = uuid.uuid4().hex
        await emit("tool_start", {"call_id": call_id, "name": name, "input": params})
        started = time.perf_counter()
        with trace.span("execute_tool", name, input=params, source=True) as record:
            result = await work
            record["attributes"]["result"] = summary(result)
            record["attributes"]["ok"] = True
        await emit(
            "tool_result",
            {
                "call_id": call_id,
                "name": name,
                "ok": True,
                "summary": summary(result),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return result

    async def _build_project(self, task: str, u: fahm.Understanding) -> Outcome:
        from workspace.context import bound_workspace_id

        blueprint = project.BLUEPRINTS[u.entities["kind"]]
        needed = ["workspace_write"] + ([] if bound_workspace_id() else ["workspace_create"])
        if not self.lisan.available or not all(self._allowed(name) for name in needed):
            raise Defer
        workspace_id = bound_workspace_id()
        if workspace_id:
            # An existing project is changed, never overwritten.
            if not self._allowed("workspace_glob"):
                raise Defer
            listing = await self._tool("workspace_glob", {"pattern": "**/*"})
            if listing.get("error"):
                raise Defer
            if listing.get("total", 0):
                return await self._edit_project(
                    task, fahm.Understanding("edit_project", u.language, u.confidence, {})
                )
        name = str(u.entities["name"])
        plan = [(spec.path, spec.purpose) for spec in blueprint.files]
        await self._begin(
            [
                "Choose the project's files (MIZAN)",
                *(f"Write {spec.path} (Lisan)" for spec in blueprint.files),
                "Save the files to the project",
                "Check the project; repair what fails (MIZAN)",
                "Save a checkpoint and reply",
            ]
        )
        files: dict[str, str] = {}
        try:
            for spec in blueprint.files:
                await self._step()
                files[spec.path] = await self.lisan.write_file(
                    task, blueprint.label, plan, spec.path, dict(files), u.language
                )
        except LisanUnavailable as exc:
            return Outcome(phrase("project_failed", u.language, reason=str(exc)), False, {})
        linked = False
        if blueprint.kind == "web":
            files["index.html"], linked = project.link_assets(files["index.html"])
        await self._step()
        new_project = not workspace_id
        if new_project:
            created = await self._tool("workspace_create", {"name": name})
            if tool_result_failed(created) or not created.get("id"):
                reason = str(created.get("error") or "the project could not be created")
                return Outcome(phrase("project_failed", u.language, reason=reason), False, {})
            workspace_id = str(created["id"])
        for path, content in files.items():
            if error := await self._save(workspace_id, path, content):
                return Outcome(phrase("project_failed", u.language, reason=error), False, {})
        await self._step()
        checks, problem = await self._check_project(blueprint, workspace_id, files)
        rounds = 0
        while problem and rounds < MAX_REPAIRS:
            try:
                reply = await self.lisan.fix_files(task, blueprint.label, files, problem)
            except LisanUnavailable:
                break
            fixed = project.extract_files(reply, set(files))
            if not fixed:
                break
            rounds += 1
            for path, content in fixed.items():
                if blueprint.kind == "web" and path == "index.html":
                    content, _added = project.link_assets(content)
                files[path] = content
                if error := await self._save(workspace_id, path, content):
                    return Outcome(phrase("project_failed", u.language, reason=error), False, {})
            checks, problem = await self._check_project(blueprint, workspace_id, files)
        await self._step()
        if self._allowed("workspace_checkpoint"):
            await self._tool(
                "workspace_checkpoint",
                {"workspace_id": workspace_id, "message": f"MIZAN built {name}"},
            )
        verified = all(ok is True for _key, ok, _detail in checks)
        lines = [
            phrase("project_new" if new_project else "project_current", u.language, name=name),
            "",
            f"**{phrase('project_files', u.language)}**",
            *(f"- `{path}` ({content.count(chr(10))} lines)" for path, content in files.items()),
            "",
            f"**{phrase('project_checks', u.language)}**",
        ]
        for key, ok, detail in checks:
            mark = "✓" if ok else "✗" if ok is False else "–"
            note = f" ({phrase('check_not_run', u.language, reason=detail)})" if ok is None else ""
            lines.append(f"- {mark} {phrase(key, u.language)}{note}")
        if linked:
            lines.append(f"- ✓ {phrase('check_linked', u.language)}")
        if rounds:
            lines += ["", f"_{phrase('project_repaired', u.language, count=rounds)}_"]
        if problem and not verified:
            lines += ["", fence(problem[-1500:], "text")]
        lines += ["", phrase(f"project_open_{blueprint.kind}", u.language)]
        return Outcome(
            "\n".join(lines),
            verified,
            {"workspace_id": workspace_id, "files": sorted(files), "repairs": rounds},
        )

    async def _use_tool(self, task: str, u: fahm.Understanding) -> Outcome:
        """Any other action: MIZAN picks the tool and checks its arguments."""
        need = str(u.entities.get("need") or task)
        tools = amal.candidates(self.agent, self._chat_allowed)
        tool = amal.choose(self.agent, tools, need, task)
        trace.event(
            "plan",
            "amal.choose",
            need=need,
            candidates=len(tools),
            chosen=tool["name"] if tool else None,
        )
        if tool is None:
            raise Defer
        name = str(tool["name"])
        await self._begin(
            [
                f"Choose the tool: {name} (MIZAN)",
                "Fill in its arguments (Lisan)",
                "Check them against the tool's schema (MIZAN)",
                f"Run {name}",
                "Reply",
            ]
        )
        await self._step()
        arguments: dict = {}
        error = ""
        for _attempt in range(2):
            try:
                arguments = amal.restrict(
                    await self.lisan.fill_arguments(task, need, tool, error),
                    tool.get("input_schema"),
                )
            except LisanUnavailable as exc:
                return Outcome(phrase("tool_not_prepared", u.language, tool=name, reason=str(exc)), False, {}, tool_backed=False)  # fmt: skip
            issues = amal.problems(arguments, tool.get("input_schema"))
            trace.event("verify", "schema", tool=name, accepted=not issues, problems=issues)
            if not issues:
                break
            error = "; ".join(issues)
        else:
            reason = error[:300]
            return Outcome(phrase("tool_not_prepared", u.language, tool=name, reason=reason), False, {"tool": name}, tool_backed=False)  # fmt: skip
        await self._step()
        await self._step()
        result = await self._tool(name, arguments)
        failed = tool_result_failed(result)
        await self._step()
        if failed:
            reason = str(result.get("error") or result.get("detail") or "")[:300]
            text = phrase("tool_failed", u.language, tool=name, reason=reason)
        else:
            facts = amal.facts(name, arguments, result)
            fallback = f"**{name}**\n{fence(facts['result'][:3000], 'json')}"
            text, _phrased = await self._phrase_with_lisan(task, facts, u.language, fallback)
        return Outcome(text, False, {"tool": name}, succeeded=not failed, provenance="evidence")

    def _chat_allowed(self, name: str) -> bool:
        try:
            return bool(self.agent._chat_tool_allowed(name))
        except Exception:  # noqa: BLE001
            return False

    async def _edit_project(self, task: str, u: fahm.Understanding) -> Outcome:
        """Change the selected project: MIZAN reads, saves, checks and repairs."""
        from workspace.context import bound_workspace_id

        needed = ("workspace_glob", "workspace_read", "workspace_write")
        if not bound_workspace_id() or not self.lisan.available:
            raise Defer
        if not all(self._allowed(name) for name in needed):
            raise Defer
        request = str(u.entities.get("request") or task)
        listing = await self._tool("workspace_glob", {"pattern": "**/*"})
        files = [f for f in listing.get("files", []) if isinstance(f, dict)]
        paths = [str(f.get("path", "")) for f in files]
        chosen = project.relevant_files(files, request)
        if listing.get("error") or not chosen:
            raise Defer
        await self._begin(
            [
                "Read the project's files (MIZAN)",
                "Write the change (Lisan)",
                "Save the changed files",
                "Check the project; repair what fails (MIZAN)",
                "Save a checkpoint and reply",
            ]
        )
        originals: dict[str, str] = {}
        shas: dict[str, str | None] = {}
        for path in chosen:
            document = await self._tool("workspace_read", {"path": path})
            if isinstance(document.get("content"), str) and not document.get("error"):
                originals[path] = document["content"]
                shas[path] = document.get("sha256")
        await self._step()
        try:
            reply = await self.lisan.edit_files(request, originals, paths, u.language)
        except LisanUnavailable as exc:
            return Outcome(phrase("project_failed", u.language, reason=str(exc)), False, {})
        changes = {
            path: content
            for path, content in project.extract_files(reply, set(paths), new_files=True).items()
            if content != originals.get(path)
        }
        if not changes:
            return Outcome(phrase("edit_nothing", u.language), False, {}, tool_backed=False)
        await self._step()
        current = dict(originals)
        for path, content in changes.items():
            if error := await self._save_edit(path, content, shas):
                return Outcome(phrase("project_failed", u.language, reason=error), False, {})
            current[path] = content
        await self._step()
        everything = sorted(set(paths) | set(changes))
        checks, problem = await self._check_edit(changes, current, everything)
        rounds = 0
        while problem and rounds < MAX_REPAIRS:
            try:
                reply = await self.lisan.fix_files(
                    task, "project", {p: current[p] for p in changes}, problem
                )
            except LisanUnavailable:
                break
            fixed = project.extract_files(reply, set(changes))
            if not fixed:
                break
            rounds += 1
            for path, content in fixed.items():
                if error := await self._save_edit(path, content, shas):
                    return Outcome(phrase("project_failed", u.language, reason=error), False, {})
                current[path] = changes[path] = content
            checks, problem = await self._check_edit(changes, current, everything)
        await self._step()
        if self._allowed("workspace_checkpoint"):
            await self._tool("workspace_checkpoint", {"message": f"MIZAN: {task[:60]}"})
        verified = bool(checks) and all(ok is True for _label, ok, _detail in checks)
        diff: list[str] = []
        for path, content in changes.items():
            diff += difflib.unified_diff(
                originals.get(path, "").splitlines(),
                content.splitlines(),
                f"a/{path}" if path in originals else "/dev/null",
                f"b/{path}",
                lineterm="",
            )
        shown = "\n".join(diff[:120]) + ("\n…" if len(diff) > 120 else "")
        lines = [
            phrase("edit_done", u.language, count=len(changes)),
            "",
            f"**{phrase('edit_changes', u.language)}**",
            fence(shown or "(no textual difference)", "diff"),
            "",
            f"**{phrase('project_checks', u.language)}**",
        ]
        for label, ok, detail in checks or [(phrase("edit_no_checks", u.language), None, "")]:
            mark = "✓" if ok else "✗" if ok is False else "–"
            note = (
                f" ({phrase('check_not_run', u.language, reason=detail)})"
                if ok is None and detail
                else ""
            )
            lines.append(f"- {mark} {label}{note}")
        if rounds:
            lines += ["", f"_{phrase('project_repaired', u.language, count=rounds)}_"]
        if problem and not verified:
            lines += ["", fence(problem[-1500:], "text")]
        return Outcome(
            "\n".join(lines),
            verified,
            {"files": sorted(changes), "repairs": rounds},
            succeeded=not problem,
        )

    async def _save_edit(self, path: str, content: str, shas: dict[str, str | None]) -> str | None:
        params: dict = {"path": path, "content": content}
        if shas.get(path):
            params["expected_sha256"] = shas[path]  # never overwrite a newer version
        saved = await self._tool("workspace_write", params)
        if tool_result_failed(saved):
            return str(saved.get("error") or saved.get("detail") or f"{path} could not be saved")
        shas[path] = saved.get("sha256")
        return None

    async def _check_edit(
        self, changes: dict[str, str], current: dict[str, str], everything: list[str]
    ) -> tuple[list[tuple[str, bool | None, str]], str]:
        """MIZAN's checks on the changed files, as (label, passed, detail); first problems."""
        checks: list[tuple[str, bool | None, str]] = []
        problems: list[str] = []
        commands: list[tuple[str, str]] = []
        known = set(everything)
        for path, content in changes.items():
            kind = path.rsplit(".", 1)[-1].lower()
            if kind in {"html", "htm"}:
                missing = sorted(project.local_references(content) - known)
                checks.append((phrase("check_refs", "en", path=path), not missing, ""))
                if missing:
                    problems.append(f"{path} loads files that do not exist: {', '.join(missing)}")
            elif kind == "css":
                balanced = project.css_balanced(content)
                checks.append((phrase("check_css_file", "en", path=path), balanced, ""))
                if not balanced:
                    problems.append(f"{path} has unbalanced braces")
            elif kind == "json":
                try:
                    json.loads(content)
                    checks.append((phrase("check_json", "en", path=path), True, ""))
                except ValueError as exc:
                    checks.append((phrase("check_json", "en", path=path), False, ""))
                    problems.append(f"{path} is not valid JSON: {exc}")
            elif kind in {"js", "mjs", "cjs"}:
                commands.append((path, f"node --check {shlex.quote(path)}"))
            elif kind == "py":
                commands.append((path, f"python -m py_compile {shlex.quote(path)}"))
        if any(p.endswith(".py") for p in changes) and any(
            p.split("/")[-1].startswith("test_") and p.endswith(".py") for p in known
        ):
            commands.append(("tests", "python -m unittest -q"))
        for subject, command in commands[:6]:
            label = (
                phrase("check_tests", "en")
                if subject == "tests"
                else phrase("check_syntax", "en", path=subject)
            )
            if not self._allowed("workspace_run"):
                checks.append((label, None, "the sandbox is not available in this chat"))
                continue
            run = await self._tool(
                "workspace_run", {"command": command, "language": "shell", "timeout_s": 60}
            )
            if run.get("error"):
                checks.append((label, None, str(run["error"])[:200]))
                continue
            passed = run.get("exit_code") == 0
            checks.append((label, passed, ""))
            if not passed:
                output = (str(run.get("stdout", "")) + str(run.get("stderr", ""))).strip()
                problems.append(f"`{command}` failed:\n{output[-2000:]}")
        return checks, "\n\n".join(problems)

    async def _save(self, workspace_id: str, path: str, content: str) -> str | None:
        saved = await self._tool(
            "workspace_write", {"workspace_id": workspace_id, "path": path, "content": content}
        )
        if tool_result_failed(saved):
            return str(saved.get("error") or f"{path} could not be saved")
        return None

    async def _check_project(
        self, blueprint: project.Blueprint, workspace_id: str, files: dict[str, str]
    ) -> tuple[list[tuple[str, bool | None, str]], str]:
        """MIZAN's checks as (phrase key, passed or None if not run, detail); first problem."""
        checks: list[tuple[str, bool | None, str]] = []
        problems: list[str] = []
        commands: list[tuple[str, str]] = []
        if blueprint.kind == "web":
            html, css, js = files["index.html"], files["style.css"], files["app.js"]
            scan = project.scan_html(html)
            checks.append(
                ("check_links", "style.css" in scan.styles and "app.js" in scan.scripts, "")
            )
            missing = project.missing_ids(html, js)
            checks.append(("check_ids", not missing, ", ".join(missing)))
            if missing:
                problems.append(
                    "app.js looks up element ids that index.html does not have: "
                    + ", ".join(missing)
                    + ". Ids in index.html: "
                    + (", ".join(sorted(scan.ids)) or "none")
                )
            balanced = project.css_balanced(css)
            checks.append(("check_css", balanced, ""))
            if not balanced:
                problems.append("style.css has unbalanced braces")
            commands.append(("check_js", "node --check app.js"))
        else:
            commands += [
                ("check_tests", "python -m unittest -q"),
                ("check_main", "timeout 20 python main.py < /dev/null"),
            ]
        for key, command in commands:
            if not self._allowed("workspace_run"):
                checks.append((key, None, "the sandbox is not available in this chat"))
                continue
            run = await self._tool(
                "workspace_run",
                {
                    "workspace_id": workspace_id,
                    "command": command,
                    "language": "shell",
                    "timeout_s": 60,
                },
            )
            if run.get("error"):
                checks.append((key, None, str(run["error"])[:200]))
                continue
            passed = run.get("exit_code") == 0
            checks.append((key, passed, ""))
            if not passed:
                output = (str(run.get("stdout", "")) + str(run.get("stderr", ""))).strip()
                problems.append(f"`{command}` failed (exit code {run.get('exit_code')}):\n{output}")
        return checks, "\n\n".join(problems)

    async def _quran(self, task: str, u: fahm.Understanding) -> Outcome:
        reference: quran.Reference = u.entities["reference"]
        await self._begin(
            [
                f"Find {reference.label} in MIZAN's surah index",
                "Fetch the authentic Arabic text and translation",
                "Reply with the exact text",
            ]
        )
        await self._step()
        data, error = await self._from_source(
            "quran_text",
            reference.label,
            lambda: quran.fetch(reference, u.language),
            lambda found: f"{len(found['ayahs'])} ayah(s)",
        )
        if error is not None:
            return Outcome(phrase("quran_unavailable", u.language, reason=error), False, {})
        await self._step()
        lines = [f"**{data['reference']}** · {data['surah_arabic']}", ""]
        for ayah in data["ayahs"]:
            lines.append(f"> {ayah['arabic']} ﴿{ayah['number']}﴾")
            if ayah["translation"]:
                lines.append(f"({ayah['number']}) {ayah['translation']}")
            lines.append("")
        source = phrase(
            "quran_source",
            u.language,
            source=data["source"],
            translation=data["translation"] or "—",
        )
        lines.append(f"_{source}_")
        first, last = data.get("shown", (0, 0))
        if data.get("requested", 0) > last - first + 1:
            surah_name = quran.SURAHS[reference.surah - 1][0]
            lines.append(
                "\n_"
                + phrase(
                    "quran_partial",
                    u.language,
                    first=first,
                    last=last,
                    requested=data["requested"],
                    label=f"Surah {surah_name}",
                    next_first=last + 1,
                    next_last=min(last + quran.MAX_AYAHS, data["total"]),
                )
                + "_"
            )
        if u.entities.get("explain"):
            lines.append(f"\n_{phrase('quran_no_tafsir', u.language)}_")
        return Outcome("\n".join(lines), True, {"reference": data["reference"]})

    async def _hadith(self, task: str, u: fahm.Understanding) -> Outcome:
        reference: hadith.HadithRef = u.entities["reference"]
        await self._begin(
            [
                f"Find {reference.label} in MIZAN's collection index",
                "Fetch the Arabic text, translation and grades",
                "Reply with the exact text and its grading",
            ]
        )
        await self._step()
        data, error = await self._from_source(
            "hadith_text",
            reference.label,
            lambda: hadith.fetch(reference, u.language),
            lambda found: str(found["reference"]),
        )
        if error is not None:
            return Outcome(phrase("hadith_unavailable", u.language, reason=error), False, {})
        await self._step()
        heading = f"**{data['reference']}** · {data['collection_arabic']}"
        place = [data["section"]] if data["section"] else []
        if data.get("book") and data.get("in_book"):
            place.append(f"Book {data['book']}, hadith {data['in_book']}")
        lines = [heading]
        if place:
            lines.append(f"_{' · '.join(place)}_")
        lines += ["", f"> {data['arabic']}"]
        if data["translation"]:
            lines += ["", data["translation"]]
        if data["clipped"]:
            lines += ["", f"_{phrase('hadith_clipped', u.language)}_"]
        lines.append("")
        grades = data["grades"]
        if grades:
            lines.append(f"**{phrase('hadith_grades', u.language)}**")
            lines += [f"- {g['name']}: {g['grade']}" for g in grades]
            if any(hadith.is_weak(g["grade"]) for g in grades):
                lines += ["", f"**{phrase('hadith_weak', u.language)}**"]
        elif data["sahih_collection"]:
            lines.append(f"_{phrase('hadith_sahih', u.language, collection=data['collection'])}_")
        else:
            lines.append(f"_{phrase('hadith_ungraded', u.language)}_")
        narrations = data["narrations"]
        if narrations:
            shown = data["reference"].rsplit(" ", 1)[-1]
            others = [n for n in narrations if n != shown]
            lines += [
                "",
                "_"
                + phrase(
                    "hadith_narrations",
                    u.language,
                    number=reference.number,
                    count=len(narrations),
                    first=narrations[0],
                    last=narrations[-1],
                    shown=shown,
                    example=f"{data['collection']} {others[0] if others else shown}",
                )
                + "_",
            ]
        source = f"_{phrase('hadith_source', u.language, source=data['source'])}_"
        if data["link"]:
            source += f" · [{data['link'].removeprefix('https://')}]({data['link']})"
        lines += ["", source]
        if u.entities.get("explain"):
            item = hadith.BY_KEY[reference.collection]
            commentary = item.commentary_ar if u.language in {"ur", "ar"} else item.commentary
            note = (
                phrase("hadith_no_sharh", u.language, commentary=commentary)
                if commentary
                else phrase("hadith_no_sharh_any", u.language)
            )
            lines.append(f"\n_{note}_")
        return Outcome("\n".join(lines), True, {"reference": data["reference"]})

    async def _waqt(self, task: str, u: fahm.Understanding) -> Outcome:
        request: waqt.WaqtRequest = u.entities["request"]
        language = u.language
        await self._begin(["Read the clock and the Hijri calendar (MIZAN)", "Reply"])
        current, zone = waqt.now()
        today = current.date()
        lines: list[str] = []
        try:
            if request.kind == "today":
                hijri = waqt.to_hijri(today)
                lines.append(
                    phrase(
                        "waqt_today",
                        language,
                        gregorian=waqt.gregorian_text(today),
                        hijri=waqt.hijri_text(hijri),
                        hijri_ar=waqt.hijri_arabic(hijri),
                    )
                )
                if request.with_time:
                    time_text = f"{current:%H:%M}"
                    lines.append(phrase("waqt_time", language, time=time_text, zone=zone or "UTC"))
            elif request.kind == "to_hijri" and request.gregorian is not None:
                hijri = waqt.to_hijri(request.gregorian)
                lines.append(
                    f"**{waqt.gregorian_text(request.gregorian)}** = **{waqt.hijri_text(hijri)}** "
                    f"({waqt.hijri_arabic(hijri)})"
                )
            elif request.kind == "to_gregorian" and request.hijri is not None:
                year, month, day = request.hijri
                when = waqt.to_gregorian(year, month, day)
                hijri = waqt.to_hijri(when)
                lines.append(
                    f"**{waqt.hijri_text(hijri)}** ({waqt.hijri_arabic(hijri)}) = "
                    f"**{waqt.gregorian_text(when)}**"
                )
            else:
                keys = ["eid_fitr", "eid_adha"] if request.event == "eid" else [request.event]
                asked_year = request.hijri[0] if request.hijri else 0
                for key in keys:
                    name, month, day = waqt.EVENTS[key]
                    if asked_year:
                        year, when = asked_year, waqt.to_gregorian(asked_year, month, day)
                    else:
                        year, when = waqt.next_occurrence(month, day, today)
                    days = (when - today).days
                    relative = (
                        phrase("waqt_today_word", language)
                        if days == 0
                        else phrase("waqt_in_days", language, days=days)
                        if days > 0
                        else phrase("waqt_days_ago", language, days=-days)
                    )
                    lines.append(
                        phrase(
                            "waqt_event",
                            language,
                            event=name,
                            hijri=f"{day} {waqt.MONTHS[month - 1]} {year} AH",
                            gregorian=waqt.gregorian_text(when),
                            relative=relative,
                        )
                    )
        except waqt.OutOfRange:
            return Outcome(phrase("waqt_range", language), False, {})
        await self._step()
        notes = [phrase("waqt_hijri_note", language)]
        if request.kind == "event" and request.event in {"eid", "eid_fitr", "ramadan"}:
            notes.append(phrase("waqt_sighting", language))
        if zone is None and request.kind in {"today", "event"}:
            notes.append(phrase("waqt_utc_note", language))
        text = "\n\n".join(lines) + "\n\n" + "\n\n".join(f"_{note}_" for note in notes)
        return Outcome(text, True, {"zone": zone or "UTC", "kind": request.kind})

    async def _web_search(self, task: str, u: fahm.Understanding) -> Outcome:
        if not self._allowed("web_search"):
            raise Defer
        await self._begin(
            [
                "Search the web (MIZAN)",
                "Write the answer from the sources (Lisan)",
                "Check citations and numbers (Furqan)",
                "Reply with sources",
            ]
        )
        found = await self._tool("web_search", {"query": u.entities["query"]})
        await self._step()
        if found.get("error"):
            return Outcome(phrase("page_failed", u.language, reason=found["error"]), False, {})
        results = [r for r in found.get("results", []) if isinstance(r, dict)][:6]
        if not results:
            if u.entities.get("understood_by") in {"lisan", "mizan_learned"}:
                raise Defer  # a search MIZAN chose found nothing: answer in words instead
            return Outcome(phrase("no_results", u.language), False, {})
        sources = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "text": r.get("snippet", "")}
            for r in results
        ]
        return await self._answer_from(task, sources, u)

    async def _web_read(self, task: str, u: fahm.Understanding) -> Outcome:
        if not self._allowed("web_browse"):
            raise Defer
        await self._begin(
            [
                "Read the page (MIZAN)",
                "Write the answer from the page (Lisan)",
                "Check citations and numbers (Furqan)",
                "Reply with the source",
            ]
        )
        page = await self._tool("web_browse", {"url": u.entities["url"]})
        await self._step()
        if page.get("error"):
            return Outcome(phrase("page_failed", u.language, reason=page["error"]), False, {})
        sources = [
            {
                "title": page.get("title") or u.entities["url"],
                "url": page.get("url") or u.entities["url"],
                "text": str(page.get("content", ""))[:8000],
            }
        ]
        return await self._answer_from(task, sources, u)

    async def _answer_from(self, task: str, sources: list[dict], u: fahm.Understanding) -> Outcome:
        listing = "\n".join(
            f"{index}. [{s['title'] or s['url']}]({s['url']})"
            for index, s in enumerate(sources, start=1)
        )
        source_block = f"**{phrase('sources', u.language)}**\n{listing}"
        answer, verified = "", False
        if self.lisan.available:
            try:
                draft = await self.lisan.answer_from_sources(task, sources, u.language)
                if not furqan(
                    draft, json.dumps(sources, ensure_ascii=False), max_citation=len(sources)
                ):
                    answer, verified = draft, True
            except LisanUnavailable:
                pass
        await self._step()
        if not answer:
            if len(sources) == 1:
                excerpt = sources[0]["text"][:800].strip()
                answer = f"{phrase('page_excerpt', u.language)}\n\n> {excerpt}"
            else:
                answer = (
                    phrase("found", u.language)
                    + "\n\n"
                    + "\n".join(
                        f"{index}. **{s['title']}** — {s['text'][:240]}"
                        for index, s in enumerate(sources, start=1)
                    )
                )
        return Outcome(
            f"{answer}\n\n{source_block}",
            verified,
            {"sources": len(sources)},
            provenance="evidence",
        )

    async def _recall(self, task: str, u: fahm.Understanding) -> Outcome:
        if not self._allowed("recall_memory"):
            raise Defer
        await self._begin(["Search MIZAN's memory", "Reply"])
        found = await self._tool("recall_memory", {"query": u.entities["query"][:300]})
        await self._step()
        memories = str(found.get("result") or found.get("error") or "")
        if not memories or memories.startswith(
            ("No relevant", "No memory", "Memory recall failed")
        ):
            return Outcome(memories or "—", False, {})
        fallback = f"{phrase('memories', u.language)}\n\n{memories[:3000]}"
        text, _phrased = await self._phrase_with_lisan(
            task, {"memories": memories[:6000]}, u.language, fallback
        )
        return Outcome(text, True, {"memories": True}, provenance="evidence")


def _matches(stdout: str, value: calc.Number) -> bool:
    printed = stdout.strip().splitlines()[-1].strip() if stdout.strip() else ""
    if printed == calc.render(value):
        return True
    try:
        return math.isclose(float(printed), float(value), rel_tol=1e-9, abs_tol=1e-12)
    except (ValueError, OverflowError):
        return False


def _run_facts(run: dict) -> dict:
    return {
        key: (str(run[key])[:2000] if isinstance(run.get(key), str) else run.get(key))
        for key in ("exit_code", "stdout", "stderr", "error", "duration_ms", "sandbox")
        if key in run
    }
