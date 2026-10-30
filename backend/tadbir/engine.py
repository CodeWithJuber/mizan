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

import ast
import asyncio
import base64
import difflib
import json
import math
import os
import re
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agents.events import emit, summarize
from agents.execution_contract import tool_result_failed

from . import (
    amal,
    amanah,
    calc,
    express,
    fahm,
    fihris,
    hadith,
    hifz,
    hudud,
    isnad,
    majlis,
    project,
    qasd,
    qiyas,
    quran,
    sarf,
    shahid,
    silsila,
    taallum,
    tajdid,
    tajriba,
    talaqqi,
    tathabbut,
    trace,
    waqt,
    wazn,
)
from .express import cautions, fence, furqan, phrase
from .lisan import INSTRUCTIONS, Lisan, LisanUnavailable, language_name, long_files

MODES = ("mizan", "hybrid", "strict", "llm")
_RENEWALS: set[asyncio.Task] = set()  # instruction renewals running in the background
MAX_REPAIRS = 2
# Tools that read or run (no outside effect), safe to call again after a passing failure.
_RETRYABLE = frozenset(
    {"workspace_run", "workspace_read", "workspace_glob", "workspace_grep", "web_browse",
     "web_search", "web_read", "http_get", "hf_repos", "hf_files", "hf_preview", "hf_import",
     "shahid_read"}
)  # fmt: skip
_TRANSIENT = re.compile(
    r"\b(?:busy|try again|temporar\w*|unavailable|overloaded|rate.?limit\w*|too many requests|"
    r"502|503|504|429)\b",
    re.IGNORECASE,
)
RETRY_DELAYS = (0.5, 2.0)
# Questions a program answers better than reading: the cheapest, a total, a count…
_ANALYTIC = re.compile(
    r"\b(?:cheapest|lowest|highest|most|least|largest|smallest|biggest|maximum|minimum|total|"
    r"sum|average|mean|median|count|how\s+many|rank\w*|top\s+\d+|sorted|best[- ]rated|"
    r"rated\s+(?:\d|at\s+least|above|below)|(?:\d|stars?)\s+or\s+(?:more|less|higher|lower))\b",
    re.IGNORECASE,
)


def orchestration_mode() -> str:
    value = os.getenv("MIZAN_ORCHESTRATION", "mizan").strip().lower()
    value = "mizan" if value == "strict" else value  # strict is the former name
    return value if value in MODES else "mizan"


def full_orchestration() -> bool:
    """MIZAN performs every action; the model may only answer in words."""
    return orchestration_mode() == "mizan"


TYPED_KINDS = {"ts", "tsx", "jsx", "mts", "cts"}


def _esbuild(paths: list[str]) -> str:
    """A shell command that parses each file with esbuild (the project's own copy, else
    a global one), stopping at the first error; 127 when there is none."""
    files = " ".join(shlex.quote(path) for path in paths)
    return (
        "if [ -x node_modules/.bin/esbuild ]; then E=node_modules/.bin/esbuild; "
        "elif command -v esbuild >/dev/null 2>&1; then E=esbuild; "
        "else echo 'esbuild is not in the sandbox' >&2; exit 127; fi; "
        f'for f in {files}; do "$E" "$f" --log-level=error --outfile=/dev/null || exit 1; done'
    )


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
    # Pictures MIZAN made for this answer (a browser screenshot), by kept id.
    images: list[dict] = field(default_factory=list)
    # How much of ``text`` reached the chat already (the model's words in a coding
    # handoff stream as it writes them); the rest is streamed when the outcome is done.
    streamed: int = 0
    # The text holds the model's own words: Sidq checks them even when MIZAN verified
    # the work.
    model_words: bool = False


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
        # The agent's own ReAct loop (BaseAgent._model_turn), for a coding request beyond
        # MIZAN's recipes; None where no one is there to approve its changes.
        self._model: Callable[[str], Awaitable[str]] | None = None

    # ── entry point ──────────────────────────────────────────────────────

    async def handle(
        self,
        task: str,
        stream_callback=None,
        history: list[dict] | None = None,
        model_turn: Callable[[str], Awaitable[str]] | None = None,
    ) -> dict | None:
        mode = orchestration_mode()
        if mode == "llm" or not isinstance(task, str) or not task.strip():
            return None
        self._model = model_turn
        self._stream = stream_callback
        started = time.time()
        if _button() and self._handoff_ready():
            # A button ("Approve plan and run", "Fix with MIZAN"), never the words: the
            # model works on the chat's project with its tools, and MIZAN checks it.
            parts, example = None, None
            understanding = fahm.Understanding(
                "workspace_agent",
                fahm.detect_language(task),
                1.0,
                # A new project is named from the request the plan answered.
                {
                    "understood_by": "button",
                    "name": project.project_name(_earlier_request(history) or task),
                },
            )
        else:
            task, parts, understanding, example = await self._understand(task, history)
        handler = getattr(self, f"_{understanding.intent}", None)
        # What MIZAN read, kept on the run for its usage record even when the request
        # goes on to the language model (usage.lisan.family/language).
        self.agent._understood = {
            "intent": understanding.intent,
            "language": understanding.language,
            "by": understanding.entities.get("understood_by", "fahm"),
        }
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
                # An answer MIZAN learned from sources before is given again with
                # no model call (Talaqqi); otherwise, words only: in "mizan" mode
                # the agent answers with no tools.
                reused = (
                    await self._talaqqi(task, understanding, history)
                    if understanding.intent == "converse"
                    else None
                )
                if reused is None:
                    return None
                outcome = reused
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
        if stream_callback and outcome.text[outcome.streamed :]:
            await stream_callback(outcome.text[outcome.streamed :])
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
            **({"images": outcome.images} if outcome.images else {}),
            **({"model_words": True} if outcome.model_words else {}),
            # An answer learned from sources and given again (Talaqqi).
            **(
                {"talaqqi": outcome.facts["talaqqi"]}
                if isinstance(outcome.facts, dict) and outcome.facts.get("talaqqi")
                else {}
            ),
            # A project made for this request: the chat is bound to it.
            **(
                {"workspace_id": outcome.facts["workspace_id"]}
                if isinstance(outcome.facts, dict) and outcome.facts.get("workspace_id")
                else {}
            ),
            "orchestration": {
                "by": "mizan",
                "mode": mode,
                **understanding.to_dict(),
                "plan": deepcopy(self.plan.items) if self.plan else [],
                "verified": outcome.verified,
                "language_model_calls": self.lisan.calls,
                "language_model_tasks": dict(self.lisan.by_task),
                "agents": self.workers,
            },
        }

    async def _understand(
        self, task: str, history: list[dict] | None
    ) -> tuple[str, list[tuple[str, fahm.Understanding]] | None, fahm.Understanding, dict | None]:
        """What the request asks, by Fahm, the chat, and (for wording) Lisan: the request
        (a follow-up takes up an earlier one), its parts, the understanding, and the
        learned example it came from, if any."""
        # Reading the request is CPU work (naive Bayes over every clause): it runs
        # off the event loop, so other chats and /api/health never wait for it.
        overlay = self._learned_intents()
        parts = await asyncio.to_thread(fahm.understand_parts, task)
        understanding = await asyncio.to_thread(fahm.understand, task, history, overlay)
        if parts is None and understanding.intent == "again_follow":
            # "?", "Jawab nahi aaya": the request before this one got no answer,
            # so MIZAN takes it up again; with nothing unanswered it is words.
            unanswered = _unanswered_request(history)
            if unanswered:
                task = unanswered
                parts = await asyncio.to_thread(fahm.understand_parts, task)
                understanding = await asyncio.to_thread(fahm.understand, task, history, overlay)
            else:
                understanding = fahm.Understanding("converse", understanding.language, 0.0)
        if parts is None and understanding.intent in {"silsila_follow", "search_bare"}:
            # "Find the next number", "karo koshish", "dhundo pahle": a follow-up
            # about what was asked earlier in this chat, which MIZAN takes from
            # the history.
            topicless = understanding.intent == "search_bare"
            earlier = silsila.from_history(history)
            if earlier:
                harder = understanding.entities.get("harder") or silsila.harder(task)
                understanding = fahm.Understanding(
                    "silsila",
                    understanding.language,
                    understanding.confidence,
                    {
                        "sequence": earlier,
                        "understood_by": "conversation",
                        **({"effort": "deep"} if harder else {}),
                    },
                )
            elif not topicless:
                understanding = fahm.Understanding("converse", understanding.language, 0.0)
            else:
                # "Dhundo pahle": search for what the user asked before, not these words.
                topic = _earlier_request(history)
                understanding = (
                    fahm.Understanding(
                        "web_search",
                        understanding.language,
                        0.7,
                        {"query": topic[:300], "understood_by": "conversation"},
                    )
                    if topic
                    else fahm.Understanding("converse", understanding.language, 0.0)
                )
        if parts is None and understanding.intent == "run_follow":
            # "Run this code": the program shown most recently in this chat.
            program = _earlier_program(history)
            understanding = (
                fahm.Understanding(
                    "run_code",
                    understanding.language,
                    understanding.confidence,
                    {
                        "code": program[0],
                        "code_language": program[1],
                        "understood_by": "conversation",
                    },
                )
                if program
                else fahm.Understanding("converse", understanding.language, 0.0)
            )
        if parts is None and understanding.intent == "recall":
            # Working memory before long-term memory: what the user said earlier
            # in this chat is recalled from the chat itself.
            said = _said_in_chat(task, history)
            if said:
                understanding.entities["said"] = said
        if parts is not None:
            understanding = fahm.Understanding(
                "compound",
                fahm.detect_language(task),
                min(u.confidence for _part, u in parts),
                {"parts": [{"text": part, "intent": u.intent} for part, u in parts]},
            )
        example: dict | None = None
        if (
            parts is None
            and self.lisan.available
            and await asyncio.to_thread(fahm.partly_understood, task, understanding)
        ):
            # Several requests and MIZAN's recognisers place only some: Lisan
            # maps the whole message into steps, which MIZAN validates.
            planned = await self._lisan_plan(task, understanding, history)
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
        if (
            parts is None
            and understanding.intent == "converse"
            and len(task) <= 2000
            and fahm.actionable(understanding)
        ):
            learned = self._learned_understanding(task, understanding)
            if learned is not None:
                understanding, example = learned
            elif self.lisan.available:
                # Lisan only translates the wording into MIZAN's actions; MIZAN
                # validates every step before acting on it.
                planned = await self._lisan_plan(task, understanding, history)
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
        return task, parts, understanding, example

    # ── Majlis: the agent that fits does the work ────────────────────────

    def _runner(self, worker: Any) -> Tadbir:
        runner = Tadbir(worker, lisan=self.lisan, coordinator=self.coordinator)
        runner._stream = self._stream
        runner._model = self._model
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
        # Who did the work is metadata (orchestration.agents), never the answer's text.
        outcome.isnad = self._isnad(outcome, intent)
        return outcome

    def _lisan_outcome(self, task: str, worked: bool, feedback: str = "") -> None:
        """Credit the instruction version (Tajdid) and model (Wazn) with MIZAN's verdict."""
        info = self.lisan.last.pop(task, None)
        if info is None:
            return
        tajdid.record(task, info.get("variant", "base"), worked, feedback)
        wazn.record(task, info.get("model"), worked)
        trace.event(
            "learn", "tajdid", task=task, variant=info.get("variant"), model=info.get("model"),
            worked=worked,
        )  # fmt: skip
        if tajdid.wants_challenger(task) and task in INSTRUCTIONS:
            renewal = asyncio.create_task(tajdid.evolve(task, INSTRUCTIONS[task], self.lisan))
            _RENEWALS.add(renewal)
            renewal.add_done_callback(_RENEWALS.discard)

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
        # Qasd learns the wording of a request that Lisan or the conversation had
        # to place and MIZAN then verified, so the next one is understood alone.
        label = _qasd_label(task, u, source)
        if (
            outcome.verified
            and label
            and qasd.learn(store, user, task, label, bool(fahm._selected_project()))
        ):
            trace.event("learn", "qasd", intent=label, by=source)

    def _learned_intents(self) -> Any:
        from security.auth import current_user_id

        return qasd.overlay(getattr(self.coordinator, "adaptive", None), current_user_id() or "")

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
            for delay in RETRY_DELAYS:
                # A passing failure (busy, 503, rate limit) of a tool that only reads
                # or runs: wait and call it again rather than give up, unless calling
                # again would ask the person again.
                if not _transient(name, result) or _asks(name, params):
                    break
                trace.event("recover", "retry", tool=name, error=str(result["error"])[:200])
                await asyncio.sleep(delay)
                result = trace.injected_fault(name) or await self.agent._execute_tool_safe(
                    name, params
                )
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
        if amanah.untrusted(name):
            # Outside text: an instruction aimed at the AI is removed before
            # anything (Lisan, the user, memory) reads the result.
            result, found = amanah.guard_value(result, name)
            if found:
                trace.event("verify", "amanah", tool=name, findings=found)
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
                fihris.Unavailable,
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
        warnings = cautions(facts.get("result"))
        if furqan(text, json.dumps(facts, ensure_ascii=False), warnings=warnings):
            return fallback, False
        return text, True

    async def _lisan_plan(
        self, task: str, fallback: fahm.Understanding, history: list[dict] | None = None
    ) -> list[tuple[str, fahm.Understanding]]:
        """Lisan's steps that pass MIZAN's validation, with the words each covers."""
        earlier = "\n".join(
            f"- {amanah.clean_message(text)[:300]}" for text in qasd.earlier_messages(history)[-3:]
        )
        try:
            # Pasted text may carry an instruction; it never chooses MIZAN's actions.
            steps = await self.lisan.plan_steps(amanah.clean_message(task), earlier)
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
        text = f"`{shown}` = **{rendered}**"
        if u.entities.get("explain"):
            # The working comes from MIZAN's own evaluation, never from the model.
            working = calc.steps(expression)
            text += f"\n\n**{phrase('steps', u.language)}**\n" + "\n".join(
                f"{number}. {line}" for number, line in enumerate(working, 1)
            )
        text += f"\n\n_{phrase('computed', u.language)}_"
        return Outcome(text, True, {"expression": expression, "value": rendered})

    async def _sarf(self, task: str, u: fahm.Understanding) -> Outcome:
        """Root, wazn, part of speech and meaning of Arabic words, read from the
        Quranic Arabic Corpus: the analyzer /api/v1/root-analyze uses."""
        await self._begin(
            ["Understand the question (Fahm)", "Read the Quranic Arabic Corpus (MIZAN)", "Reply"]
        )
        try:
            corpus = await sarf.corpus()
        except sarf.Unavailable as exc:
            return Outcome(phrase("sarf_unavailable", u.language, reason=str(exc)), False, {})
        await self._step()
        lines: list[str] = []
        found = []
        for word in u.entities.get("words") or []:
            item = sarf.analyze_word(corpus, word)
            found.append(item)
            if not item.get("root"):
                lines.append(phrase("sarf_no_root", u.language, word=word, pos=item.get("pos", "")))
                continue
            lines.append(
                phrase(
                    "sarf_word",
                    u.language,
                    word=word,
                    root=item["root_letters"],
                    pattern=item.get("pattern") or "—",
                    pos=item.get("pos", ""),
                )
                + (f" · “{item['gloss']}”" if item.get("gloss") else "")
            )
            if item.get("meaning"):
                lines.append(
                    phrase(
                        "sarf_meaning",
                        u.language,
                        meaning=item["meaning"],
                        count=item.get("root_occurrences", 0),
                    )
                )
            for other in item.get("alternatives") or []:
                lines.append(
                    phrase(
                        "sarf_also",
                        u.language,
                        pattern=other.get("pattern") or "—",
                        pos=other.get("pos", ""),
                        share=round(100 * float(other.get("share") or 0)),
                    )
                )
            if item.get("source") == "inferred":
                lines.append(phrase("sarf_inferred", u.language))
        lines.append(f"\n_{phrase('sarf_source', u.language)}_")
        facts = {
            "words": [
                {key: item.get(key) for key in ("surface", "root_letters", "pattern", "pos")}
                for item in found
            ]
        }
        return Outcome("\n".join(lines), True, facts)

    async def _run(self, code: str, language: str) -> dict:
        return await self._tool(
            "workspace_run", {"command": code, "language": language, "timeout_s": 60}
        )

    async def _run_or_check(self, code: str, language: str) -> tuple[dict, str | None]:
        """Run the program; one that opens a window (the sandbox has no screen)
        is compiled instead, and the toolkit is returned so the reply says so."""
        toolkit = _window_toolkit(code) if language == "python" else None
        if toolkit is None:
            return await self._run(code, language), None
        encoded = base64.b64encode(code.encode()).decode()
        check = (
            "import base64\n"
            f"compile(base64.b64decode('{encoded}').decode(), 'main.py', 'exec')\n"
            "print('main.py compiles')\n"
        )
        return await self._run(check, "python"), toolkit

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
        request = str(u.entities.get("request") or task)
        # Tajriba: verified lessons from earlier repairs of similar work.
        lessons = tajriba.relevant(store, owner, "build_and_run", request)
        try:
            code = await self.lisan.write_code(request, language, tajriba.render(lessons))
        except LisanUnavailable as exc:
            raise Defer from exc
        await self._step()
        tries = 1
        run, toolkit = await self._run_or_check(code, language)
        await self._step()
        first = _ran_clean(run)
        if _code_ran(run):
            self._lisan_outcome("write_code", first, _signature(run))
            tajriba.credit(store, owner, lessons, first)
        failing: tuple[str, str] | None = None
        while (run.get("exit_code") != 0 or run.get("error")) and tries <= MAX_REPAIRS:
            if run.get("declined") or "not permitted" in str(run.get("error", "")):
                break
            if run.get("error") and not run.get("stderr"):
                break  # the sandbox itself failed; rewriting the code cannot help
            error = str(run.get("stderr") or run.get("error") or run.get("stdout", ""))
            failing = failing or (code, error)
            known = tajriba.relevant(store, owner, "build_and_run", tajriba.signature(error))
            try:
                code = await self.lisan.fix_code(
                    task, language, code, error, tajriba.render(known), attempt=tries
                )
            except LisanUnavailable:
                break
            tries += 1
            run, toolkit = await self._run_or_check(code, language)
            if _code_ran(run):
                self._lisan_outcome("fix_code", _ran_clean(run), _signature(run))
                tajriba.credit(store, owner, known, _ran_clean(run))
        # A program that was only compiled is not verified: it never ran.
        verified = run.get("exit_code") == 0 and not run.get("error") and toolkit is None
        checked: bool | None = None
        other = ""
        if verified:
            # Running cleanly says the code works, not that it read the request
            # right: an independent derivation must agree (Tathabbut).
            checked, run, code, other = await self._tathabbut(request, task, language, code, run)
            # Printed numbers are verified only when the independent program agreed:
            # a check that could not run (or printed nothing) proves nothing.
            unchecked = checked is None and tathabbut.applies(str(run.get("stdout", "")))
            verified = checked is True or (checked is None and not unchecked)
        if verified and failing is not None:
            # Rewrite the failed attempt into a verified lesson (Terminal-RSI's self-rewrite).
            lesson = tajriba.learn(store, owner, "build_and_run", request, *failing, code)
            if lesson:
                trace.event("learn", "tajriba", signature=lesson["signature"])
        parts = [
            f"**{phrase('code', u.language)}**\n{fence(code, language)}",
            self._run_text(run, u.language),
        ]
        if toolkit is not None and _ran_clean(run):
            parts.append(phrase("gui_checked", u.language, toolkit=toolkit))
        if tries > 1 and verified:
            parts.append(f"_{phrase('repaired', u.language, tries=tries)}_")
        if checked is True:
            parts.append(f"_{phrase('tathabbut_agreed', u.language)}_")
        elif checked is False:
            parts.append(f"_{phrase('tathabbut_disagrees', u.language, other=other)}_")
        elif verified is False and run.get("exit_code") == 0 and toolkit is None:
            parts.append(f"_{phrase('tathabbut_unchecked', u.language)}_")
        if verified:
            hifz.keep(
                store,
                owner,
                task,
                language,
                code,
                str(run.get("stdout", "")),
                checked=bool(checked),
            )
            trace.event("learn", "hifz", kept=True, language=language)
        facts = {"run": _run_facts(run), "attempts": tries}
        if checked is not None:
            facts["cross_check"] = {"agreed": checked, "other": other}
        return Outcome("\n\n".join(parts), verified, facts)

    async def _tathabbut(
        self, request: str, task: str, language: str, code: str, run: dict
    ) -> tuple[bool | None, dict, str, str]:
        """An independent program for the same request must print the numbers
        this one printed (N-version programming). On disagreement the first
        program is repaired once with what the second printed. Returns whether
        they agreed (None: nothing to compare), the run and code kept, and what
        the independent program printed."""
        printed = str(run.get("stdout", ""))
        if not tathabbut.applies(printed):
            return None, run, code, ""
        try:
            second = await self.lisan.cross_check(request, language)
        except LisanUnavailable:
            return None, run, code, ""
        check = await self._run(second, language) if second.strip() else {}
        said = str(check.get("stdout", "")).strip()
        agreed = tathabbut.agree(printed, said) if _ran_clean(check) else None
        trace.event("verify", "tathabbut", agreed=agreed)
        if agreed is not False:
            return agreed, run, code, said[:200]
        error = (
            f"The program ran, but an independent program written for the same request "
            f"printed:\n{said[:500]}\nwhile this one printed:\n{printed.strip()[:500]}\n"
            "One of them misreads the request (a starting value, an index, an inclusive or "
            "exclusive bound). Re-read the request and return the corrected program."
        )
        try:
            fixed = await self.lisan.fix_code(task, language, code, error, attempt=1)
        except LisanUnavailable:
            return False, run, code, said[:200]
        rerun, _toolkit = await self._run_or_check(fixed, language)
        if _ran_clean(rerun) and tathabbut.agree(str(rerun.get("stdout", "")), said):
            trace.event("verify", "tathabbut", agreed=True, repaired=True)
            return True, rerun, fixed, said[:200]
        return False, run, code, said[:200]

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
        if worked and not kept.get("checked") and tathabbut.applies(str(run.get("stdout", ""))):
            # Kept before Tathabbut: an independent program must agree once.
            try:
                second = await self.lisan.cross_check(" ".join(kept["tokens"]), language)
            except LisanUnavailable:
                second = ""
            check = await self._run(second, language) if second.strip() else {}
            agreed = (
                tathabbut.agree(str(run.get("stdout", "")), str(check.get("stdout", "")))
                if _ran_clean(check)
                else None
            )
            trace.event("verify", "tathabbut", agreed=agreed, kept=True)
            if agreed is False:
                hifz.drop(store, owner, kept)
                return None  # it answered another question: Lisan writes a new one
            if agreed is None:
                return None  # not checked: a new program is written and checked
            hifz.mark_checked(store, owner, kept)
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

    async def _talaqqi(
        self, task: str, u: fahm.Understanding, history: list[dict] | None
    ) -> Outcome | None:
        """An answer the teacher gave once and the sources confirmed, given again
        with no language-model call after its claims are checked (Talaqqi)."""
        from memory import stateless
        from security.auth import current_user_id

        from . import ahl_dhikr

        if stateless.active() or not talaqqi.opens_chat(history) or not ahl_dhikr.enabled():
            return None
        if not ahl_dhikr.factual(task) or ahl_dhikr.ruling(task) or ahl_dhikr.religious(task):
            return None
        store, owner = self.coordinator.adaptive, current_user_id() or ""
        kept = talaqqi.recall(store, owner, task, u.language)
        if kept is None:
            return None

        async def outside(query: str) -> list[ahl_dhikr.Passage]:
            pool: list[ahl_dhikr.Passage] = []
            try:
                pool += await ahl_dhikr.wikipedia(query, u.language)
            except Exception:  # noqa: BLE001 - one source unreachable settles nothing
                pass
            if self._allowed("web_search"):
                pool += ahl_dhikr.web_from(await self._tool("web_search", {"query": query[:300]}))
            return pool

        status, findings = await talaqqi.recheck(kept, outside)
        trace.event("learn", "talaqqi", status=status, reused=status in ("held", "confirmed"))
        if status == "contradicted":
            talaqqi.drop(store, owner, kept)
            return None  # a source now says otherwise: the teacher is asked again
        if status not in ("held", "confirmed"):
            return None  # not settled now: the teacher answers this time
        item = talaqqi.reused(store, owner, kept, findings, confirmed=status == "confirmed")
        from . import sijill

        sijill.note(
            "talaqqi",
            {
                "detail": "Gave an answer it learned from sources, with no model call"
                + (" (sources asked again)" if status == "confirmed" else "")
            },
        )
        self.agent._understood = {**(self.agent._understood or {}), "by": "talaqqi"}
        await self._begin(
            [
                "Recall an answer MIZAN learned from sources (Talaqqi)",
                "Check its claims against the sources"
                if status == "confirmed"
                else "Check each claim still has the source that confirmed it",
                "Reply",
            ]
        )
        await self._step()
        await self._step()
        sources = sorted({f.passage.title for f in findings if f.passage is not None})
        note = phrase(
            "talaqqi_reused",
            u.language,
            kept=str(item.get("kept", ""))[:10],
            sources=", ".join(sources[:3]),
        )
        ledger = ahl_dhikr.regrade(isnad.ledger(item["answer"]), findings)
        return Outcome(
            f"{item['answer']}\n\n_{note}_",
            True,
            {
                "talaqqi": {
                    "kept": item.get("kept", ""),
                    "teacher": item.get("teacher", ""),
                    "reused": item.get("reused", 0),
                    "checked": "sources" if status == "confirmed" else "kept sources",
                }
            },
            provenance="evidence",
            isnad=ledger,
        )

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
        except LisanUnavailable:
            # The model gave no rule (often its reasoning used the whole output
            # limit). Handing the puzzle to the agent loop would spend a larger
            # budget the same way: MIZAN says plainly that no rule was found.
            await self._step()
            return Outcome(
                phrase("qiyas_no_rule", u.language, total=total), False, {"examples": total}
            )
        await self._step()
        best: tuple[int, str, dict | None] = (-1, program, None)
        attempts = 0
        for attempts in range(1, MAX_REPAIRS + 2):  # noqa: B007 - attempts is reported
            run = await self._run(qiyas.harness(program, puzzle), "python")
            report = qiyas.read(str(run.get("stdout", "")))
            fitted = qiyas.passed(report, puzzle)
            trace.event("verify", "qiyas", examples=total, reproduced=fitted, attempt=attempts)
            if _code_ran(run):
                self._lisan_outcome(
                    "propose_rule" if attempts == 1 else "revise_rule",
                    fitted == total,
                    _signature(run) or f"reproduced {max(0, fitted)} of {total} examples",
                )
            if fitted > best[0]:
                best = (fitted, program, report)
            if fitted == total or run.get("declined") or attempts > MAX_REPAIRS:
                break
            wrong = qiyas.failures(report, puzzle, str(run.get("stderr") or run.get("error", "")))
            try:
                program = await self.lisan.revise_rule(examples, program, wrong, attempt=attempts)
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
        if u.entities.get("gap"):
            return await self._silsila_missing(u)
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
        # "Karo koshish": the user asked MIZAN to try harder, so Lisan gets more rounds.
        rounds = MAX_REPAIRS * 3 if u.entities.get("effort") == "deep" else MAX_REPAIRS
        if not rules and not matches and can_test:
            try:
                program = await self.lisan.propose_sequence_rule(seq)
            except LisanUnavailable:
                program = ""
            while program and tries <= rounds:
                tries += 1
                run = await self._run(silsila.harness(program, seq), "python")
                report = silsila.read(str(run.get("stdout", "")))
                trace.event("verify", "silsila.lisan", attempt=tries, report=report)
                if _code_ran(run):
                    self._lisan_outcome(
                        "propose_sequence_rule" if tries == 1 else "revise_sequence_rule",
                        silsila.proven(report, seq),
                        _signature(run) or silsila.feedback(report).split("\n")[0],
                    )
                if silsila.proven(report, seq):
                    tested = (program, report or {})
                    break
                if run.get("declined") or (run.get("error") and not run.get("stderr")):
                    break
                if tries > rounds:
                    break
                try:
                    program = await self.lisan.revise_sequence_rule(
                        seq,
                        program,
                        silsila.feedback(report, str(run.get("stderr", ""))),
                        attempt=tries,
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

    async def _silsila_missing(self, u: fahm.Understanding) -> Outcome:
        """A term missing inside a sequence, from a rule proven on every known
        term, those after the gap included."""
        seq: list[int] = u.entities["sequence"]
        positions: list[int] = u.entities["positions"]
        gap: int = u.entities["gap"]
        await self._begin(
            [
                f"Read the {len(seq)} known terms and where one is missing (MIZAN)",
                "Try MIZAN's exact methods: polynomials in n and in the n-th prime",
                "Look the terms up in the OEIS",
                "Reply",
            ]
        )
        await self._step()
        rules = silsila.missing_rules(seq, positions, gap)
        trace.event("verify", "silsila.own", rules=[rule.to_dict() for rule in rules], gap=gap)
        await self._step()
        matches = await self._external(
            "oeis_search",
            {"terms": seq, "positions": positions},
            silsila.oeis_missing(seq, positions, gap),
            lambda found: f"{len(found)} matching sequence(s)",
        )
        await self._step()
        language = u.language
        terms = silsila.shown(seq, positions, gap)
        candidates = [
            (
                rule.next,
                phrase(
                    "silsila_rule",
                    language,
                    formula=rule.formula,
                    method=rule.method,
                    total=len(seq),
                ),
            )
            for rule in rules
        ]
        candidates += [
            (match["next"], phrase("silsila_oeis", language, id=match["id"], name=match["name"]))
            for match in matches
        ]
        if not candidates:
            text = phrase("silsila_missing_none", language, total=len(seq), terms=terms)
            return Outcome(text, False, {"sequence": seq, "gap": gap, "rules": []}, succeeded=False)
        answers = sorted({value for value, _ in candidates})
        lines = [
            phrase("silsila_missing", language, value=answers[0], terms=terms)
            if len(answers) == 1
            else phrase("silsila_missing_several", language, total=len(seq), terms=terms)
        ]
        lines += [f"- **{value}**: {reason}" for value, reason in candidates]
        facts = {
            "sequence": seq,
            "positions": positions,
            "gap": gap,
            "missing": answers,
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

        if u.entities.get("kind") == "stack" or (_planning() and bound_workspace_id()):
            # Beyond MIZAN's blueprints (React, a server): the model builds it with the
            # project's tools, and MIZAN checks what it made. A plan for the chat's
            # project is the model's too: it reads the project and proposes.
            return await self._workspace_agent(task, u)
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
            # The chat shows (and binds) the new project at once, not only at the end.
            await emit("workspace", {"workspace_id": workspace_id, "name": name, "created": True})
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
            fixed, _refused = self._repairs(reply, files, set(files))
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
                    await self.lisan.fill_arguments(amanah.clean_message(task), need, tool, error),
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

        # Plan mode offers reads only: MIZAN's own recipe cannot write there, but the
        # model can still read the project and propose (the handoff's plan).
        planning = _planning()
        needed = ("workspace_glob", "workspace_read") + (() if planning else ("workspace_write",))
        if not bound_workspace_id() or not self.lisan.available:
            raise Defer
        if not all(self._allowed(name) for name in needed):
            raise Defer
        request = str(u.entities.get("request") or task)
        listing = await self._tool("workspace_glob", {"pattern": "**/*"})
        files = [f for f in listing.get("files", []) if isinstance(f, dict)]
        paths = [str(f.get("path", "")) for f in files]
        if listing.get("error"):
            raise Defer
        if (planning or not project.recipe_sized(files)) and self._handoff_ready():
            # More than Lisan can see at once, or a project that installs and builds
            # (package.json): the model works on it with the project's tools. In plan
            # mode it reads the project and proposes, whatever its size.
            return await self._workspace_agent(task, u)
        if planning:
            raise Defer
        chosen = project.relevant_files(files, request)
        if not chosen:
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
        for_lisan: dict[str, str] = {}
        carriers: set[str] = set()  # files with text that tried to instruct the AI
        shas: dict[str, str | None] = {}
        for path in chosen:
            document = await self._tool("workspace_read", {"path": path})
            if isinstance(document.get("content"), str) and not document.get("error"):
                originals[path] = document["content"]
                shas[path] = document.get("sha256")
                clean, findings = amanah.neutralize(document["content"])
                if findings:
                    carriers.add(path)
                    amanah.taint([{**item, "source": f"file {path}"} for item in findings])
                for_lisan[path] = clean
        await self._step()
        # A long file changes only by edit blocks; a whole-file reply for it is dropped.
        long = long_files(for_lisan)
        try:
            reply = await self.lisan.edit_files(request, for_lisan, paths, u.language)
        except LisanUnavailable as exc:
            return Outcome(phrase("project_failed", u.language, reason=str(exc)), False, {})
        changes, refused = self._changed_files(reply, paths, originals, request, long)
        if not changes:
            # Lisan put the file in a block without its path, or gave a snippet: ask once
            # more, reminding it how MIZAN reads files.
            try:
                reply = await self.lisan.edit_files(
                    request, for_lisan, paths, u.language, reminder=True
                )
            except LisanUnavailable as exc:
                return Outcome(phrase("project_failed", u.language, reason=str(exc)), False, {})
            changes, refused = self._changed_files(reply, paths, originals, request, long)
        held: list[str] = []
        if carriers:
            # A file tried to instruct the AI: only what the user named may be created,
            # and the file that carried the instruction changes only if the user named it.
            named = {name.split("/")[-1] for name in fahm.named_files(request)}
            held = sorted(
                path
                for path in changes
                if path.split("/")[-1] not in named and (path not in originals or path in carriers)
            )
            for path in held:
                changes.pop(path)
            if held:
                trace.event("verify", "amanah", held=held)
        if not changes:
            text = phrase("edit_nothing", u.language)
            if refused:
                text += "\n\n" + phrase("edit_refused", u.language, items="; ".join(refused))
            if held:
                text += "\n\n" + phrase(
                    "amanah_held_files", u.language, files=", ".join(f"`{p}`" for p in held)
                )
            return Outcome(text, False, {}, tool_backed=False)
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
            fixed, _refused = self._repairs(reply, current, set(changes))
            if not fixed:
                fixed = {
                    path: content
                    for path, content in project.infer_file(
                        reply, {path: current[path] for path in changes}, list(changes)
                    ).items()
                    if path not in long_files({path: current[path]})
                }
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
        if held:
            listed = ", ".join(f"`{path}`" for path in held)
            lines += ["", f"_{phrase('amanah_held_files', u.language, files=listed)}_"]
        if refused:
            lines += ["", f"_{phrase('edit_refused', u.language, items='; '.join(refused))}_"]
        if problem and not verified:
            lines += ["", fence(problem[-1500:], "text")]
        return Outcome(
            "\n".join(lines),
            verified,
            {"files": sorted(changes), "repairs": rounds},
            succeeded=not problem,
        )

    # ── Coding beyond MIZAN's recipes: the model with the project's tools ──

    def _handoff_ready(self) -> bool:
        """The model may work on a project here: someone is reading this chat and answers
        its approval prompts, the setting is on, and the project's tools are allowed."""
        from agents.events import has_event_sink
        from security.approvals import current_approvals

        approvals = current_approvals()
        if approvals is None or not approvals.interactive or approvals.deferred:
            return False
        # Plan mode reads the project and proposes; it changes nothing.
        needed = _HANDOFF_READS + (() if approvals.mode == "plan" else _HANDOFF_WRITES)
        return bool(
            os.getenv("MIZAN_WORKSPACE_AGENT", "on").strip().lower() != "off"
            and full_orchestration()
            and self._model is not None
            and not self._nested
            and has_event_sink()
            and all(self._allowed(name) for name in needed)
        )

    async def _workspace_agent(self, task: str, u: fahm.Understanding) -> Outcome:
        """The model works on the chat's project (made here when the chat has none) with
        the project's tools only, every change through the chat's permission mode; MIZAN
        then checks each file that changed, gives the model one turn to repair what
        failed, and reports what its checks found. Verified only when checks ran and
        all passed."""
        from agents.base import workspace_only
        from security.auth import current_user_id
        from workspace import context as workspace_context

        if not self._handoff_ready() or self._model is None:
            raise Defer
        model = self._model
        owner = current_user_id() or ""
        workspace_id = workspace_context.bound_workspace_id()
        create = not workspace_id
        planning = _planning()
        if create and (planning or not self._allowed("workspace_create")):
            raise Defer  # a plan for a project that does not exist yet is words
        name = str(u.entities.get("name") or project.project_name(task))
        if planning:
            assert workspace_id is not None
            await self._begin(["Read the project and propose a plan (model)"])
            with workspace_context.running_in(owner, workspace_id), workspace_only(workspace_id):
                words = await model(_handoff_prompt(task, {}, u.language))
            return Outcome(
                words,
                False,
                {"plan": True},
                tool_backed=False,
                provenance="evidence",
                streamed=len(words),
                model_words=True,
            )
        await self._begin(
            [
                *(["Create the project and bind it to this chat (MIZAN)"] if create else []),
                "Work on the project with its tools (model)",
                "Check the changed files; one repair turn if a check fails (MIZAN)",
                "Save a checkpoint and reply",
            ]
        )
        binding = None
        if create:
            made = await self._tool("workspace_create", {"name": name})
            if tool_result_failed(made) or not made.get("id"):
                reason = str(made.get("error") or "the project could not be created")
                return Outcome(phrase("project_failed", u.language, reason=reason), False, {})
            workspace_id = str(made["id"])
            binding = workspace_context.bind_workspace(workspace_id)
            await emit("workspace", {"workspace_id": workspace_id, "name": name, "created": True})
            await self._step()
        assert workspace_id is not None
        prompt = _handoff_prompt(task, _button(), u.language)
        try:
            with workspace_context.running_in(owner, workspace_id):
                before = await asyncio.to_thread(_project_hashes, owner, workspace_id)
                with workspace_only(workspace_id):
                    words = await model(prompt)
                await self._step()
                after = await asyncio.to_thread(_project_hashes, owner, workspace_id)
                checks, problem, changed, removed = await self._handoff_checks(
                    owner, workspace_id, before, after
                )
                repaired = False
                if problem:
                    # One repair turn, the problems shown to the model as data.
                    repaired = True
                    with workspace_only(workspace_id):
                        words += "\n\n" + await model(_repair_prompt(problem, u.language))
                    after = await asyncio.to_thread(_project_hashes, owner, workspace_id)
                    checks, problem, changed, removed = await self._handoff_checks(
                        owner, workspace_id, before, after
                    )
                await self._step()
                if changed or removed:
                    await self._tool(
                        "workspace_checkpoint",
                        {"workspace_id": workspace_id, "message": f"MIZAN: {task[:60]}"},
                    )
        finally:
            if binding is not None:
                workspace_context.reset_workspace(binding)
        verified = bool(checks) and all(ok is True for _label, ok, _detail in checks)
        lines = ["", "---", f"**{phrase('handoff_checked', u.language)}**"]
        if changed:
            listed = ", ".join(f"`{path}`" for path in changed[:20])
            lines.append(phrase("handoff_changed", u.language, files=listed))
        if removed:
            listed = ", ".join(f"`{path}`" for path in removed[:20])
            lines.append(phrase("handoff_removed", u.language, files=listed))
        if not changed and not removed:
            lines.append(phrase("handoff_nothing", u.language))
        for label, ok, detail in checks:
            mark = "✓" if ok else "✗" if ok is False else "–"
            note = (
                f" ({phrase('check_not_run', u.language, reason=detail)})"
                if ok is None and detail
                else ""
            )
            lines.append(f"- {mark} {label}{note}")
        if repaired:
            lines += ["", f"_{phrase('handoff_repaired', u.language)}_"]
        if problem:
            lines += ["", phrase("handoff_unverified", u.language), fence(problem[-1500:], "text")]
        report = "\n".join(lines)
        if self._stream:
            await self._stream(report)
        return Outcome(
            words + report,
            verified,
            {
                **({"workspace_id": workspace_id} if create else {}),
                "files": changed,
                "removed": removed,
                "repairs": int(repaired),
            },
            succeeded=bool(changed or removed) and not problem,
            provenance="evidence",
            streamed=len(words + report),
            model_words=True,
        )

    async def _handoff_checks(
        self, owner: str, workspace_id: str, before: dict[str, str], after: dict[str, str]
    ) -> tuple[list[tuple[str, bool | None, str]], str, list[str], list[str]]:
        """MIZAN's checks of what the model changed, and whether the servers it started
        still run: (checks, problems, changed paths, removed paths)."""
        changed = sorted(path for path, sha in after.items() if before.get(path) != sha)
        removed = sorted(set(before) - set(after))
        texts = await asyncio.to_thread(_project_texts, owner, workspace_id, changed)
        checks, problem = await self._check_edit(texts, texts, sorted(after))
        problems = [problem] if problem else []
        served = any(
            item.get("name") == "workspace_sandbox"
            and isinstance(item.get("result"), dict)
            and item["result"].get("preview_url")
            for item in getattr(self.coordinator, "_last_tool_results", []) or []
        )
        if served:
            status = await self._tool(
                "workspace_sandbox", {"workspace_id": workspace_id, "action": "status"}
            )
            for service in status.get("services") or []:
                if not isinstance(service, dict):
                    continue
                port = service.get("port")
                alive = bool(service.get("alive", True))
                checks.append((phrase("check_service", "en", port=port), alive, ""))
                if not alive:
                    problems.append(
                        f"The server on port {port} stopped (command: {service.get('command')})."
                        " Read its logs with workspace_sandbox action=logs."
                    )
        return checks, "\n\n".join(problems), changed, removed

    def _changed_files(
        self,
        reply: str,
        paths: list[str],
        originals: dict[str, str],
        request: str,
        long: set[str],
    ) -> tuple[dict[str, str], list[str]]:
        """The files Lisan's reply changes, and the edits that did not apply. A file Lisan
        saw as long never comes back whole: only its edit blocks count."""
        whole = project.extract_files(reply, set(paths), new_files=True) or project.infer_file(
            reply, originals, fahm.named_files(request)
        )
        edited, refused = project.apply_edits(
            project.extract_edits(reply, set(originals)), originals
        )
        files = {path: content for path, content in whole.items() if path not in long}
        files.update(edited)
        changed = {path: c for path, c in files.items() if c != originals.get(path)}
        return changed, refused

    @staticmethod
    def _repairs(
        reply: str, current: dict[str, str], targets: set[str]
    ) -> tuple[dict[str, str], list[str]]:
        """Lisan's corrections of ``targets``: whole files for short ones, edit blocks."""
        long = long_files({path: current[path] for path in targets if path in current})
        whole = {
            path: content
            for path, content in project.extract_files(reply, targets).items()
            if path not in long
        }
        edited, refused = project.apply_edits(
            project.extract_edits(reply, targets & set(current)), current
        )
        return {**whole, **edited}, refused

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
        typed = sorted(p for p in changes if p.rsplit(".", 1)[-1].lower() in TYPED_KINDS)
        if typed:
            # One esbuild run reads every TypeScript/JSX file (syntax, not types); exit 127
            # means the sandbox has no esbuild, reported as not run.
            commands.insert(0, ("types:" + ", ".join(typed), _esbuild(typed)))
        if any(p.endswith(".py") for p in changes) and any(
            p.split("/")[-1].startswith("test_") and p.endswith(".py") for p in known
        ):
            commands.append(("tests", "python -m unittest -q"))
        commands = commands[:6]
        for (subject, command), (code, output, error) in zip(
            commands,
            await self._run_checks([command for _subject, command in commands]),
            strict=True,
        ):
            label = (
                phrase("check_tests", "en")
                if subject == "tests"
                else phrase("check_compiles", "en", path=subject[6:])
                if subject.startswith("types:")
                else phrase("check_syntax", "en", path=subject)
            )
            if error:
                checks.append((label, None, error))
                continue
            if subject.startswith("types:") and code == 127:
                checks.append((label, None, "esbuild is not in the sandbox"))
                continue
            checks.append((label, code == 0, ""))
            if code != 0:
                problems.append(f"`{command}` failed:\n{output[-2000:]}")
        return checks, "\n\n".join(problems)

    async def _run_checks(self, commands: list[str]) -> list[tuple[int | None, str, str]]:
        """Each check's (exit code, output, error), all in one sandbox run so the person
        is asked once, not once per check."""
        if not commands:
            return []
        if not self._allowed("workspace_run"):
            return [(None, "", "the sandbox is not available in this chat")] * len(commands)
        mark = f"@@mizan-check-{uuid.uuid4().hex}"
        script = commands[0] if len(commands) == 1 else _batched(commands, mark)
        run = await self._tool(
            "workspace_run",
            {"command": script, "language": "shell", "timeout_s": 60 * min(len(commands), 2)},
        )
        if run.get("error"):
            return [(None, "", str(run["error"])[:200])] * len(commands)
        if len(commands) == 1:
            output = (str(run.get("stdout", "")) + str(run.get("stderr", ""))).strip()
            return [(run.get("exit_code"), output, "")]
        return _batch_results(str(run.get("stdout", "")), len(commands), mark)

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

    async def _run_file(self, task: str, u: fahm.Understanding) -> Outcome:
        """Run a file of the selected project in its sandbox and show exactly what it printed."""
        from workspace.context import bound_workspace_id

        if not bound_workspace_id() or not self._allowed("workspace_run"):
            raise Defer
        path = str(u.entities["path"]).strip().lstrip("./")
        await self._begin(
            [
                "Find the file in the project (MIZAN)",
                f"Run `{path}` in the project's sandbox",
                "Reply with its exact output",
            ]
        )
        if self._allowed("workspace_glob"):
            listing = await self._tool("workspace_glob", {"pattern": "**/*"})
            files = {
                str(f.get("path")): int(f.get("size", 0))
                for f in listing.get("files", [])
                if isinstance(f, dict)
            }
            found = _in_project(path, files) if files else path
            if found is None:
                return Outcome(phrase("run_file_missing", u.language, path=path), False, {})
            path = found
        if not project.editable(path):
            raise Defer
        await self._step()
        runner = {"py": "python", "sh": "bash"}.get(path.rsplit(".", 1)[-1].lower(), "node")
        run = await self._tool(
            "workspace_run",
            {
                "command": f"{runner} {shlex.quote(path)} < /dev/null",
                "language": "shell",
                "timeout_s": 60,
            },
        )
        await self._step()
        text = f"{phrase('ran_file', u.language, path=path)}\n\n{self._run_text(run, u.language)}"
        return Outcome(
            text, _ran_clean(run), {"path": path, "run": _run_facts(run)}, succeeded=_code_ran(run)
        )

    async def _project_task(self, task: str, u: fahm.Understanding) -> Outcome:
        """Work on the project's own files: Lisan writes the program, MIZAN runs and checks it.

        The program runs in the project's sandbox within Hudud's limits (it may write
        only the files the request names), MIZAN checks the exit code, that each output
        exists and parses, and that nothing else changed, repairs what fails, and words
        the reply from what the program printed (Furqan checks the numbers).
        """
        from security.auth import current_user_id
        from workspace.context import bound_workspace_id

        needed = ("workspace_glob", "workspace_read", "workspace_run")
        if not bound_workspace_id() or not self.lisan.available:
            raise Defer
        if not all(self._allowed(name) for name in needed):
            raise Defer
        request = str(u.entities.get("request") or task)
        listing = await self._tool("workspace_glob", {"pattern": "**/*"})
        if listing.get("error"):
            raise Defer
        before = {
            str(f.get("path")): int(f.get("size", 0))
            for f in listing.get("files", [])
            if isinstance(f, dict)
        }
        named = [str(name) for name in u.entities.get("files") or fahm.named_files(request)]
        inputs = [found for name in named if (found := _in_project(name, before))]
        creates = [name for name in named if _in_project(name, before) is None]
        writable = creates + [path for path in inputs if _writes_to(request, path)]
        if not inputs:
            missing = ", ".join(f"`{name}`" for name in named)
            return Outcome(phrase("task_missing", u.language, files=missing), False, {})
        await self._begin(
            [
                "Read the files the request names (MIZAN)",
                "Write the program (Lisan)",
                "Run it on the project within the request's limits (Hudud)",
                "Check the outputs; repair what fails (MIZAN)",
                "Reply from what the program found",
            ]
        )
        previews: dict[str, str] = {}
        for path in inputs[:6]:
            document = await self._tool("workspace_read", {"path": path})
            content = document.get("content")
            if isinstance(content, str) and not document.get("error"):
                clean, findings = amanah.neutralize(content)
                if findings:
                    amanah.taint([{**item, "source": f"file {path}"} for item in findings])
                previews[path] = _preview(clean)
        await self._step()
        store, owner = self.coordinator.adaptive, current_user_id() or ""
        lessons = tajriba.relevant(store, owner, "project_task", request)
        try:
            code = await self.lisan.project_program(
                request, previews, writable, tajriba.render(lessons)
            )
        except LisanUnavailable as exc:
            return Outcome(phrase("project_failed", u.language, reason=str(exc)), False, {})
        await self._step()
        run, problem, changed = await self._task_run(code, writable, set(before))
        if _code_ran(run):
            self._lisan_outcome("project_program", not problem, _signature(run))
            tajriba.credit(store, owner, lessons, not problem)
        await self._step()
        tries, failing = 1, None
        context = f"{request}\n\nFiles (the start of each):\n" + "\n\n".join(
            f"{path}:\n{preview[:1500]}" for path, preview in previews.items()
        )
        while problem and tries <= MAX_REPAIRS:
            if run.get("declined") or (run.get("error") and not run.get("stderr")):
                break  # the sandbox itself failed; a new program cannot help
            failing = failing or (code, problem)
            try:
                code = await self.lisan.fix_code(context, "python", code, problem, attempt=tries)
            except LisanUnavailable:
                break
            tries += 1
            run, problem, changed = await self._task_run(code, writable, set(before))
        verified = not problem
        if verified and failing is not None:
            lesson = tajriba.learn(store, owner, "project_task", request, *failing, code)
            if lesson:
                trace.event("learn", "tajriba", signature=lesson["signature"])
        written = [path for path in changed if path in writable or path in creates]
        outputs: dict[str, str] = {}
        for path in written[:4]:
            document = await self._tool("workspace_read", {"path": path})
            if isinstance(document.get("content"), str):
                outputs[path] = _preview(document["content"], 20, 1500)
        stdout = str(run.get("stdout", ""))
        facts = {"program_output": stdout[-4000:], "files_written": outputs}
        fallback = "\n\n".join(
            part
            for part in (
                phrase("task_done", u.language) if verified else "",
                self._run_text(run, u.language),
            )
            if part
        )
        answer = fallback
        if verified and stdout.strip():
            answer, _phrased = await self._phrase_with_lisan(task, facts, u.language, fallback)
        parts = [answer]
        if not verified and problem:
            parts.append(phrase("task_failed", u.language, reason=problem[-600:]))
        if outputs:
            parts.append(
                f"**{phrase('task_files', u.language)}**\n"
                + "\n".join(
                    f"- `{path}`\n{fence(preview, '')}" for path, preview in outputs.items()
                )
            )
        parts.append(f"**{phrase('code', u.language)}**\n{fence(code, 'python')}")
        if tries > 1 and verified:
            parts.append(f"_{phrase('repaired', u.language, tries=tries)}_")
        return Outcome(
            "\n\n".join(parts),
            verified,
            {"run": _run_facts(run), "files": sorted(outputs), "attempts": tries},
            succeeded=verified,
        )

    async def _task_run(
        self, code: str, writable: list[str], before: set[str]
    ) -> tuple[dict, str, list[str]]:
        """Run a project program within Hudud's limits; the run, the first problem, what changed."""
        run = await self._run(hudud.guard(code, writable), "python")
        changed = [str(path) for path in run.get("changed_files") or []]
        if not _ran_clean(run):
            error = str(run.get("stderr") or run.get("error") or run.get("stdout", ""))
            if hudud.refused(error):
                error += (
                    "\n\nThe program may write only these files: "
                    + (", ".join(writable) or "none")
                    + ". Do not delete, rename or change any other file."
                )
            return run, error[-3000:], changed
        problems = []
        stray = [path for path in changed if path not in writable]
        if stray:
            problems.append(f"The program changed files the request did not name: {stray}")
        for name in writable:
            if name not in before and name not in changed:
                problems.append(f"The program did not write {name}.")
                continue
            kind = name.rsplit(".", 1)[-1].lower()
            if kind not in {"json", "csv"}:
                continue
            document = await self._tool("workspace_read", {"path": name})
            content = str(document.get("content") or "")
            if kind == "json":
                try:
                    json.loads(content)
                except ValueError as exc:
                    problems.append(f"{name} is not valid JSON: {exc}")
            elif not content.strip():
                problems.append(f"{name} is empty.")
        return run, "\n".join(problems), changed

    async def _hf_hub(self, task: str, u: fahm.Understanding) -> Outcome:
        """Hugging Face, read by MIZAN on the server (its code sandbox has no network)."""
        action = u.entities.get("action")
        tool = {"repos": "hf_repos", "files": "hf_files", "import": "hf_import"}.get(str(action))
        if tool is None or not self._allowed(tool):
            raise Defer
        language = u.language
        if action == "repos":
            await self._begin(["Ask Hugging Face for the account's repositories (MIZAN)", "Reply"])
            parts: list[str] = []
            owner = str(u.entities.get("owner") or "")
            for kind in u.entities.get("kinds") or ["datasets"]:
                found = await self._tool("hf_repos", {"owner": owner, "kind": kind})
                if found.get("error"):
                    return Outcome(phrase("hf_failed", language, reason=found["error"]), False, {})
                owner = str(found.get("owner") or owner)
                rows = found.get("repos") or []
                lines = [phrase("hf_repos", language, kind=kind, owner=owner, count=len(rows))]
                lines += [
                    f"- [{row['id']}](https://huggingface.co/{'' if kind == 'models' else kind + '/'}"
                    f"{row['id']})"
                    + (" · private" if row.get("private") else "")
                    + (f" · {row['downloads']} downloads" if row.get("downloads") else "")
                    for row in rows
                ]
                parts.append("\n".join(lines))
            await self._step()
            return Outcome("\n\n".join(parts), True, {"owner": owner}, provenance="evidence")
        repo, kind = str(u.entities["repo"]), str(u.entities.get("kind") or "datasets")
        if action == "files":
            await self._begin(
                ["List the repository's files (MIZAN)", "Read its first rows", "Reply"]
            )
            listing = await self._tool("hf_files", {"repo": repo, "kind": kind})
            if listing.get("error"):
                return Outcome(phrase("hf_failed", language, reason=listing["error"]), False, {})
            await self._step()
            shown = listing.get("files") or []
            lines = [
                phrase("hf_files", language, repo=repo, count=listing.get("total", len(shown)),
                       size=_size(int(listing.get("bytes") or 0))),
                *[f"- `{item['path']}` · {_size(int(item.get('size') or 0))}" for item in shown[:40]],
            ]  # fmt: skip
            if len(shown) > 40:
                lines.append(f"- … {len(shown) - 40} more")
            if kind == "datasets" and self._allowed("hf_preview"):
                sample = await self._tool("hf_preview", {"repo": repo, "rows": 2})
                if sample.get("rows"):
                    text = json.dumps(sample["rows"], ensure_ascii=False, indent=1)[:1500]
                    lines += ["", f"**{phrase('hf_preview', language, split=sample.get('split'))}**",
                              fence(text, "json")]  # fmt: skip
            await self._step()
            lines += ["", f"_{phrase('hf_next', language, repo=repo)}_"]
            return Outcome("\n".join(lines), True, {"repo": repo}, provenance="evidence")
        await self._begin(
            ["Read the file from Hugging Face (MIZAN)", "Save it into your project", "Reply"]
        )
        params = {"repo": repo, "kind": kind, "path": u.entities["path"],
                  "revision": u.entities.get("revision") or "main"}  # fmt: skip
        imported = await self._tool("hf_import", params)
        await self._step()
        if imported.get("error"):
            return Outcome(phrase("hf_failed", language, reason=imported["error"]), False, {})
        rows = f", {imported['rows']} rows" if imported.get("rows") is not None else ""
        lines = [
            phrase("hf_imported", language, source_path=u.entities["path"], repo=repo,
                   path=imported["path"], size=_size(int(imported.get("bytes") or 0)), rows=rows),
        ]  # fmt: skip
        if imported.get("sampled"):
            lines.append(
                phrase("hf_sampled", language, total=_size(int(imported.get("size_on_hub") or 0)))
            )
        lines.append(
            f"`sha256 {str(imported.get('sha256') or '')[:16]}…` · {imported.get('source')}"
        )
        await self._step()
        return Outcome("\n\n".join(lines), True, {"imported": imported["path"]})

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
        # The translation the person names ("Urdu tarjuma", "Arabic mein"),
        # else the one of the language they write in.
        edition = quran.requested_translation(task) or u.language
        data, error = await self._from_source(
            "quran_text",
            reference.label,
            lambda: quran.fetch(reference, edition),
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
        elif u.entities.get("question"):
            answer = await self._ayah_answer(task, data, u.language)
            if answer:
                lines += ["", f"**{phrase('quran_answer', u.language)}**", answer]
        return Outcome("\n".join(lines), True, {"reference": data["reference"]})

    async def _quran_count(self, task: str, u: fahm.Understanding) -> Outcome:
        """Ayah counts from MIZAN's surah index (the Hafs count of 6236)."""
        surah = u.entities.get("surah")
        await self._begin(["Read the count from MIZAN's surah index", "Reply with the count"])
        await self._step()
        if surah:
            name, arabic, count = quran.SURAHS[surah - 1]
            text = phrase(
                "quran_count_surah", u.language, name=name, arabic=arabic, number=surah, count=count
            )
            facts = {"surah": surah, "ayahs": count}
        else:
            text = phrase(
                "quran_count_whole", u.language, surahs=len(quran.SURAHS), ayahs=quran.TOTAL_AYAHS
            )
            facts = {"surahs": len(quran.SURAHS), "ayahs": quran.TOTAL_AYAHS}
        await self._step()
        return Outcome(text, True, facts)

    async def _quran_search(self, task: str, u: fahm.Understanding) -> Outcome:
        """Ayahs found by their words in MIZAN's own index, then quoted verbatim
        from the source and the question answered from the ayah's words."""

        async def search() -> dict:
            found = await fihris.find(u.entities.get("query") or task)
            return {"matches": found.matches, "absent": found.absent, "nearest": found.nearest}

        def summary(data: dict) -> str:
            if data["absent"]:
                return "no ayah uses " + ", ".join(data["absent"])
            return ", ".join(match.label for match in data["matches"]) or "no ayah"

        found, error = await self._from_source(
            "quran_index", (u.entities.get("query") or task)[:120], search, summary
        )
        if error is not None:
            return Outcome(phrase("quran_unavailable", u.language, reason=error), False, {})
        if found["absent"]:
            # Established from MIZAN's own index of the whole Quran: no ayah
            # uses these words in the Arabic, the transliteration or the
            # translations. The nearest ayah is named for what it shares only.
            nearest = found["nearest"]
            shared = [word for word in nearest.words if word not in found["absent"]]
            lines = [
                phrase(
                    "quran_search_absent",
                    u.language,
                    words=", ".join(f"“{word}”" for word in found["absent"]),
                )
            ]
            if shared:
                lines.append(
                    phrase(
                        "quran_search_nearest",
                        u.language,
                        shared=", ".join(f"“{word}”" for word in shared),
                        reference=f"{quran.SURAHS[nearest.surah - 1][0]} {nearest.label}",
                        words=", ".join(f"“{word}”" for word in found["absent"]),
                    )
                )
            return Outcome(
                "\n\n".join(lines),
                True,
                {"absent": found["absent"], "nearest": nearest.label, "shared": shared},
            )
        matches = found["matches"]
        if not matches:
            return Outcome(phrase("quran_search_none", u.language), False, {})
        best = matches[0]
        reference = quran.Reference(best.surah, best.ayah, best.ayah)
        quoted = await self._quran(
            task,
            fahm.Understanding(
                "quran", u.language, u.confidence, {"reference": reference, "question": True}
            ),
        )
        lines = [
            f"_{phrase('quran_found', u.language, words=', '.join(best.words))}_",
            "",
            quoted.text,
        ]
        # Other ayahs are shown only when they are as likely as chance among
        # the matches (softmax of their standardised scores), not every weak hit.
        top = max(match.score for match in matches)
        weights = [math.exp(match.score - top) for match in matches]
        others = [
            f"{quran.SURAHS[match.surah - 1][0]} {match.label}"
            for match, weight in zip(matches[1:], weights[1:], strict=True)
            if weight / sum(weights) >= 1 / len(matches)
        ]
        if others:
            lines += ["", f"_{phrase('quran_also', u.language, refs=' · '.join(others))}_"]
        return Outcome(
            "\n".join(lines),
            quoted.verified,
            {**quoted.facts, "found_by": best.words, "also": [m.label for m in matches[1:]]},
        )

    async def _ayah_answer(self, task: str, data: dict, language: str) -> str:
        """The question answered from the ayah's translation only (reading, not tafsir)."""
        translation = "\n".join(
            f"({ayah['number']}) {ayah['translation']}"
            for ayah in data["ayahs"]
            if ayah.get("translation")
        )
        if translation:
            # The model reads the translation only; it is told the Arabic is
            # already shown, so it never says the Arabic is not available.
            translation = (
                "(The Arabic text of these ayahs is shown to the person above this answer, "
                "verbatim from the source.)\n" + translation
            )
        else:  # an Arabic question: the ayah's own Arabic is the source
            translation = "\n".join(
                f"({ayah['number']}) {ayah['arabic']}" for ayah in data["ayahs"]
            )
        if not translation or not self.lisan.available:
            return ""
        source = [
            {
                "title": f"{data['reference']} ({data.get('translation') or 'translation'})",
                "url": "",
                "text": translation,
            }
        ]
        try:
            draft = await self.lisan.answer_from_sources(task, source, language)
        except LisanUnavailable:
            return ""
        # Furqan: no number, name or citation the translation does not hold.
        if furqan(draft, json.dumps(source, ensure_ascii=False), max_citation=1):
            return ""
        return draft

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

    async def _watch(self, task: str, u: fahm.Understanding) -> Outcome:
        """A standing request: MIZAN saves a watcher (Muraqabah) and says when it runs."""
        from automation import muraqabah
        from security.auth import current_user_id

        owner = current_user_id()
        if not owner or muraqabah.inside_watcher():
            raise Defer  # a watcher's own task never creates watchers
        await self._begin(["Understand the standing request (MIZAN)", "Save the watcher", "Reply"])
        store = muraqabah.default_store()
        trigger = u.entities["trigger"]
        if store.place(owner) is None:
            place = muraqabah.city_in(task)
            if place is not None:
                store.set_place(owner, place)
            elif trigger["kind"] == "prayer":
                return Outcome(phrase("watch_need_place", u.language), False, {}, tool_backed=False)
        try:
            watcher = store.add(owner, u.entities["title"], trigger, u.entities["task"])
        except ValueError as exc:
            reason = str(exc)
            return Outcome(phrase("watch_failed", u.language, reason=reason), False, {}, tool_backed=False)  # fmt: skip
        await self._step()
        place = store.place(owner)
        due = watcher.get("next_due")
        upcoming = (
            datetime.fromisoformat(due).astimezone(place.zone if place else UTC).strftime("%a %d %b, %H:%M")
            if due
            else "—"
        )  # fmt: skip
        text = phrase("watch_created", u.language, title=watcher["title"], when=watcher["when"], next=upcoming)  # fmt: skip
        return Outcome(text, True, {"watcher": watcher["id"], "when": watcher["when"]}, tool_backed=False)  # fmt: skip

    async def _salah(self, task: str, u: fahm.Understanding) -> Outcome:
        """Prayer times computed by MIZAN for the user's place (or a city named in the message)."""
        from automation import muraqabah
        from security.auth import current_user_id

        owner = current_user_id()
        place = await muraqabah.place_named(task)
        if place is None and owner:
            place = muraqabah.default_store().place(owner)
        if place is None:
            return Outcome(phrase("salah_need_place", u.language), False, {}, tool_backed=False)
        await self._begin(["Compute the prayer times for your place (MIZAN)", "Reply"])
        now = datetime.now(UTC)
        day = now.astimezone(place.zone).date()
        times = muraqabah.prayer_times(place, day)
        asked = u.entities.get("prayer")
        upcoming = next((name for name in muraqabah.PRAYERS if times[name] > now), None)
        lines = [
            phrase(
                "salah_header", u.language, place=place.label, date=waqt.gregorian_text(day),
                hijri=waqt.hijri_text(waqt.to_hijri(day)),
            ),
            "",
        ]  # fmt: skip
        for name in ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"):
            label = (
                name.title() if not (name == "dhuhr" and day.weekday() == 4) else "Dhuhr (Jumu'ah)"
            )
            row = f"{label}: {times[name]:%H:%M}"
            if name == asked:
                row = f"**{row}**"
            lines.append(f"- {row}" + (" ←" if name == upcoming else ""))
        lines += [
            "",
            "_"
            + phrase(
                "salah_method", u.language, method=place.method.replace("_", " ").title(),
                asr="Hanafi" if place.hanafi else "Shafi'i",
            )
            + "_",
        ]  # fmt: skip
        facts = {"place": place.label, "times": {k: f"{v:%H:%M}" for k, v in times.items()}}
        return Outcome("\n".join(lines), True, facts, tool_backed=False)

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
        # The user's own links, in order: when one page is gone, read the next one.
        urls = [str(u.entities["url"])]
        urls += [str(url) for url in u.entities.get("urls") or [] if str(url) not in urls]
        page: dict = {}
        used, failed = urls[0], []
        for url in urls[:4]:
            page = await self._tool("web_browse", {"url": url})
            if not page.get("error"):
                used = url
                break
            failed.append((url, str(page["error"])[:160]))
        await self._step()
        if page.get("error"):
            return Outcome(phrase("page_failed", u.language, reason=page["error"]), False, {})
        text = str(page.get("content", ""))
        sources = [
            {
                "title": page.get("title") or used,
                "url": page.get("url") or used,
                "text": _passages(text, task),
            }
        ]
        computed = None
        if _ANALYTIC.search(task) and _tabular(text):
            computed = await self._compute_from_page(task, text)
        outcome = await self._answer_from(task, sources, u, computed=computed)
        if failed:
            note = phrase(
                "page_fallback", u.language, failed=failed[0][0], reason=failed[0][1], url=used
            )
            outcome.text = f"_{note}_\n\n{outcome.text}"
        return outcome

    async def _browse(self, task: str, u: fahm.Understanding) -> Outcome:
        """Shahid: use the page in MIZAN's browser sandbox, show what was done, answer from it."""
        if not self._allowed("shahid_read"):
            raise Defer
        await self._begin(
            [
                "Plan the browser steps (Lisan); MIZAN checks each one",
                "Use the page in MIZAN's browser sandbox (Shahid)",
                "Ask before sending anything to the site",
                "Write the answer from the page (Lisan)",
                "Reply with the page, a screenshot and the receipts",
            ]
        )
        origins = list(u.entities["origins"])
        url = str(u.entities["url"])
        steps, problem = None, ""
        for attempt in range(MAX_REPAIRS):
            try:
                proposed = await self.lisan.browse_steps(
                    amanah.clean_message(task), url, origins, problem
                )
            except LisanUnavailable:
                break
            steps, problem = shahid.plan(proposed, origins, task)
            trace.event("verify", "browse_plan", ok=steps is not None, attempt=attempt + 1)
            if steps is not None:
                break
        if steps is None:
            # Reading the page needs no plan: MIZAN goes there and reads it.
            steps, problem = shahid.plan([{"do": "goto", "url": url}], origins, task)
        await self._step()
        page = await self._tool("shahid_read", {"origins": origins, "steps": steps})
        await self._step()
        if page.get("error"):
            if "not installed" in str(page["error"]):
                # No browser sandbox on this server yet: read the page instead.
                return await self._web_read(task, u)
            return Outcome(phrase("page_failed", u.language, reason=page["error"]), False, {})
        sent = False
        held = shahid.held_summary(page)
        if held:
            approved = [str(item["request"]) for item in held if item.get("request")]
            submitted = await self._tool(
                "shahid_submit", {"origins": origins, "steps": steps, "approved": approved}
            )
            if submitted.get("error"):
                listing = "; ".join(str(item["request"]) for item in held)
                note = phrase("browse_held", u.language, requests=listing)
                outcome = await self._page_answer(task, page, u)
                outcome.text = f"_{note}_\n\n{outcome.text}"
                return _with_screenshot(outcome, page)
            page, sent = submitted, True
        await self._step()
        outcome = await self._page_answer(task, page, u)
        visited = [step.get("url") for step in page.get("steps") or [] if step.get("url")]
        note = phrase(
            "browse_witness",
            u.language,
            steps=len(page.get("steps") or []),
            pages=len(dict.fromkeys(visited)),
        )
        if sent:
            note += " " + phrase("browse_sent", u.language)
        outcome.text = f"{outcome.text}\n\n_{note}_"
        return _with_screenshot(outcome, page)

    async def _page_answer(self, task: str, page: dict, u: fahm.Understanding) -> Outcome:
        text = str(page.get("text", ""))
        final = str(page.get("final_url") or u.entities.get("url") or "")
        title = next(
            (step.get("title") for step in reversed(page.get("steps") or []) if step.get("title")),
            final,
        )
        sources = [{"title": title, "url": final, "text": _passages(text, task)}]
        return await self._answer_from(task, sources, u)

    async def _compute_from_page(self, task: str, page: str) -> dict | None:
        """Lisan writes ``solve(page)``; MIZAN runs it on the page and checks what it returns."""
        if not self._allowed("workspace_run") or not self.lisan.available:
            return None
        try:
            program = await self.lisan.page_program(task, page)
        except LisanUnavailable:
            return None
        for attempt in range(MAX_REPAIRS + 1):
            run = await self._run(_page_harness(program, page), "python")
            result = _page_result(str(run.get("stdout", "")))
            if _ran_clean(run) and result is not None:
                invented = _ungrounded(result, page)
                if not invented:
                    trace.event("verify", "page_program", ok=True, attempt=attempt + 1)
                    self._lisan_outcome("page_program", attempt == 0)
                    return result
                problem = f"These values are not in the page: {invented}. Use only the page's text."
            elif not _code_ran(run):
                return None  # the sandbox itself failed
            else:
                problem = str(run.get("stderr") or "") or "solve(page) returned nothing"
            trace.event("verify", "page_program", ok=False, attempt=attempt + 1, problem=problem)
            if attempt == MAX_REPAIRS:
                break
            try:
                program = await self.lisan.fix_code(
                    f"Write `solve(page)` returning a dict that answers: {task}\n\nThe page's "
                    f"start:\n{page[:3000]}",
                    "python",
                    program,
                    problem,
                    attempt=attempt + 1,
                )
            except LisanUnavailable:
                return None
        self._lisan_outcome("page_program", False)
        return None

    async def _answer_from(
        self,
        task: str,
        sources: list[dict],
        u: fahm.Understanding,
        computed: dict | None = None,
    ) -> Outcome:
        listing = "\n".join(
            f"{index}. [{s['title'] or s['url']}]({s['url']})"
            for index, s in enumerate(sources, start=1)
        )
        source_block = f"**{phrase('sources', u.language)}**\n{listing}"
        answer, verified = "", False
        evidence = json.dumps(
            {"sources": sources, **({"computed": computed} if computed else {})},
            ensure_ascii=False,
        )
        if self.lisan.available:
            try:
                draft = await self.lisan.answer_from_sources(
                    task, sources, u.language, computed=computed
                )
                if not furqan(draft, evidence, max_citation=len(sources)):
                    answer, verified = draft, True
            except LisanUnavailable:
                pass
        await self._step()
        if not answer and computed:
            answer = "\n".join(f"- **{key}**: {value}" for key, value in computed.items())
        if computed:
            answer += f"\n\n_{phrase('page_computed', u.language)}_"
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
        ignored = [item for item in amanah.tainted() if amanah.untrusted(item.get("source", ""))]
        notice = (
            f"\n\n_{phrase('amanah_ignored', u.language, count=len(ignored))}_" if ignored else ""
        )
        return Outcome(
            f"{answer}\n\n{source_block}{notice}",
            verified,
            {"sources": len(sources)},
            provenance="evidence",
        )

    async def _remember(self, task: str, u: fahm.Understanding) -> Outcome:
        """Keep what the user asked MIZAN to remember, in their own words, as a
        note tied to this chat (deleting the chat forgets it too)."""
        from security.approvals import current_approvals
        from workspace.context import current_chat_session

        approvals = current_approvals()
        store = getattr(self.agent, "memory", None)
        if store is None or (approvals is not None and approvals.deferred):
            raise Defer  # no store, or a watcher's task: nobody asked in person
        from memory import stateless

        if stateless.active():
            # A test chat keeps nothing: say so rather than claim it was saved.
            return Outcome(phrase("not_remembered", u.language), True, {"note": None})
        session = current_chat_session()
        await self._begin(["Save to your notes", "Reply"])
        note = u.entities["note"]
        memory_id = await store.remember(
            note,
            memory_type="semantic",
            importance=0.8,
            tags=["remembered"],
            source=f"chat:{session}" if session else "chat",
        )
        await self._step()
        trace.event("learn", "daftar", note=memory_id)
        return Outcome(phrase("remembered", u.language), True, {"note": memory_id})

    async def _recall(self, task: str, u: fahm.Understanding) -> Outcome:
        said = u.entities.get("said") or []
        if said:
            await self._begin(["Read this chat", "Reply"])
            statements = "\n".join(f"- {text}" for text in said)
            await self._step()
            fallback = f"{phrase('memories', u.language)}\n\n{statements}"
            text, _phrased = await self._phrase_with_lisan(
                task, {"said_earlier_in_this_chat": statements}, u.language, fallback
            )
            return Outcome(text, True, {"memories": True, "from": "chat"}, provenance="evidence")
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


def _size(count: int) -> str:
    value = float(count)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} bytes" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{count} bytes"


def _batched(commands: list[str], mark: str) -> str:
    """One shell script running each check in its own subshell, its output and exit
    code between markers (``mark`` is new for each run, so output cannot forge one)."""
    return "; ".join(
        f"echo '{mark} {index}'; ( {command} ) 2>&1; echo \"{mark} {index} exit $?\""
        for index, command in enumerate(commands)
    )


def _batch_results(stdout: str, count: int, mark: str) -> list[tuple[int | None, str, str]]:
    results: list[tuple[int | None, str, str]] = []
    for index in range(count):
        found = re.search(
            rf"^{mark} {index}\n(.*?)^{mark} {index} exit (\d+)$", stdout, re.M | re.S
        )
        if found is None:
            results.append((None, "", "the check did not finish"))
        else:
            results.append((int(found.group(2)), found.group(1).strip(), ""))
    return results


def _asks(name: str, params: dict) -> bool:
    """A call of this tool waits for the person reading the chat."""
    from security.approvals import current_approvals

    approvals = current_approvals()
    return approvals is not None and approvals.needs_approval(name, params=params)


def _transient(name: str, result: Any) -> bool:
    return (
        name in _RETRYABLE
        and isinstance(result, dict)
        and bool(result.get("error"))
        and not result.get("declined")
        and bool(_TRANSIENT.search(str(result["error"])))
    )


def _in_project(name: str, files: dict[str, int]) -> str | None:
    """The project path a file name the user wrote refers to, if it is there."""
    name = name.strip().lstrip("./")
    if name in files:
        return name
    same = [path for path in files if path.split("/")[-1] == name.split("/")[-1]]
    return same[0] if len(same) == 1 else None


def _preview(content: str, lines: int = 40, limit: int = 4000) -> str:
    """The start of a file, enough for Lisan to see its format."""
    rows = content.splitlines()
    shown = "\n".join(rows[:lines])[:limit]
    more = len(rows) - min(len(rows), lines)
    return shown + (f"\n… ({more} more lines, {len(rows)} in all)" if more > 0 else "")


def _writes_to(message: str, name: str) -> bool:
    """The request asks to write this (existing) file: "save to X", "update X"."""
    escaped = re.escape(name.split("/")[-1])
    return bool(
        re.search(
            r"\b(?:save|write|update|overwrite|append|replace|store|put|export|output|rewrite)\b"
            r"[^.?!\n]{0,60}?" + escaped + "|" + escaped + r"[^.?!\n]{0,25}?\b(?:update|overwrite)",
            message,
            re.IGNORECASE,
        )
    )


def _passages(text: str, request: str, budget: int = 6000) -> str:
    """A long page cut to the lines that answer the request (BM25), in page order."""
    if len(text) <= budget:
        return text
    from core.adaptive import bm25_scores, tokenize

    rows = [row for row in text.splitlines() if row.strip()]
    scores = bm25_scores(tokenize(request), [tokenize(row) for row in rows])
    keep: set[int] = set(range(min(3, len(rows))))  # the title and opening
    used = sum(len(rows[i]) for i in keep)
    for index in sorted(range(len(rows)), key=lambda i: scores[i], reverse=True):
        if scores[index] <= 0 or used + len(rows[index]) > budget:
            continue
        keep.add(index)
        used += len(rows[index])
    out: list[str] = []
    for index in sorted(keep):
        if out and index - 1 not in keep:
            out.append("…")
        out.append(rows[index])
    return "\n".join(out)


def _tabular(text: str) -> bool:
    """Rows of data: many lines that share a separator."""
    rows = text.splitlines()
    return any(sum(1 for row in rows if row.count(sep) >= 2) >= 8 for sep in ("|", "\t", ",", ";"))


def _page_harness(program: str, page: str) -> str:
    """Run Lisan's ``solve(page)`` on the page MIZAN read, within Hudud's limits."""
    return hudud.guard(
        f"{program}\n\nimport json as _json\n_PAGE = _json.loads({json.dumps(page)!r})\n"
        "print('MIZAN_RESULT ' + _json.dumps(solve(_PAGE), default=str, ensure_ascii=False))\n",
        [],
    )


def _page_result(stdout: str) -> dict | None:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("MIZAN_RESULT "):
            try:
                value = json.loads(line[len("MIZAN_RESULT ") :])
            except ValueError:
                return None
            if isinstance(value, dict) and value:
                return value
            return {"answer": value} if value not in (None, "", [], {}) else None
    return None


def _ungrounded(result: dict, page: str) -> list[str]:
    """The names in a computed result when none of them is in the page (an invented item).

    Links and other values that only describe the answer are not checked; an
    answer must name at least one thing the page itself says.
    """
    folded = " ".join(page.split()).lower()
    names = [
        " ".join(value.split())
        for value in result.values()
        if isinstance(value, str)
        and re.search(r"[^\W\d_]{3,}", value)
        and not re.match(r"https?://", value.strip())
    ]
    if not names or any(name.lower() in folded for name in names):
        return []
    return [name[:80] for name in names]


# What the model needs to work on a project; without them the request is answered in words.
_HANDOFF_READS = ("workspace_glob", "workspace_read")
_HANDOFF_WRITES = ("workspace_edit", "workspace_write")


def _planning() -> bool:
    """Plan mode: the person asked for a plan, so nothing in the project changes."""
    from security.approvals import current_approvals

    return getattr(current_approvals(), "mode", "") == "plan"


def _button() -> dict:
    """What a button the person pressed with this message asked for (plan_approved, fix)."""
    from security.approvals import current_approvals

    return dict(getattr(current_approvals(), "button", None) or {})


def _project_hashes(owner: str, workspace_id: str) -> dict[str, str]:
    """Every file of the project (not .git) by SHA-256 of its bytes."""
    import hashlib

    from workspace.store import WorkspaceStore

    files = WorkspaceStore(owner).files(workspace_id)
    return {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}


def _project_texts(owner: str, workspace_id: str, paths: list[str]) -> dict[str, str]:
    """The changed text files MIZAN can check (not binary, vendored or build output)."""
    from workspace.store import WorkspaceStore

    store = WorkspaceStore(owner)
    texts: dict[str, str] = {}
    for path in paths:
        if not project.editable(path):
            continue
        try:
            texts[path] = store.read_bytes(workspace_id, path).decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return texts


def _handoff_prompt(task: str, button: dict, language: str) -> str:
    """The person's request as the model reads it, with what a button sent and the
    language MIZAN read it in (Lughah), which the reply is written in."""
    reply = f"\n\n(Reply to the person in {language_name(language)}.)"
    fix = button.get("fix")
    if isinstance(fix, dict) and str(fix.get("error") or "").strip():
        source = str(fix.get("source") or "preview")
        return (
            f"{task}\n\nThe {source} showed this error; find its cause in the project and "
            f"fix it:\n{amanah.fence(str(fix['error'])[:8000], source)}{reply}"
        )
    if button.get("plan_approved"):
        return (
            f"{task}\n\nThe person approved the plan in your previous answer: carry it out "
            f"now in the project.{reply}"
        )
    return task + reply


def _repair_prompt(problem: str, language: str) -> str:
    return (
        "MIZAN checked the files you changed and this failed. Fix the cause in the project "
        "(the files, not the check), then say what you changed in "
        f"{language_name(language)}:\n" + amanah.fence(problem[-6000:], "MIZAN's checks")
    )


def _qasd_label(task: str, u: fahm.Understanding, source: str | None) -> str | None:
    """The Qasd class a verified request teaches, when Lisan or the chat placed it.

    Fahm's own choices are not fed back to it (that would only confirm itself)."""
    if source == "conversation":
        return {"web_search": "search_bare", "run_code": "run_follow"}.get(
            u.intent, "silsila_follow"
        )
    if source != "lisan":
        return None
    if u.intent == "quran":
        return "quran_explain" if u.entities.get("explain") else "quran"
    if u.intent == "hadith":
        return "hadith_explain" if u.entities.get("explain") else "hadith"
    return u.intent


def _earlier_program(history: list[dict] | None) -> tuple[str, str] | None:
    """The program in the most recent message of this chat that shows one: of
    its runnable blocks, the longest (a whole program rather than a fragment)."""
    for turn in list(reversed(history or []))[:8]:
        programs = fahm.fenced_programs(str(turn.get("content") or ""))
        if programs:
            return max(programs, key=lambda found: len(found[0]))
    return None


def _with_screenshot(outcome: Outcome, page: dict) -> Outcome:
    """The page as MIZAN's browser saw it, kept with the chat (Shahid)."""
    if page.get("screenshot_sha"):
        outcome.images = [{"sha": page["screenshot_sha"], "media_type": "image/png"}]
    return outcome


def _said_in_chat(task: str, history: list[dict] | None, limit: int = 40) -> list[str]:
    """The user's earlier statements in this chat, oldest first, when one of them
    speaks of what the request asks (it holds more than half of the request's
    distinctive information, ``Dhikr.about``); otherwise none. All of them are
    given, in order, so a later correction or the order of what was said is
    kept. Outside text that Amanah reads as an instruction aimed at the AI is
    never recalled."""
    from memory.dhikr import about

    asked = task.strip()
    earlier = [
        text
        for text in (
            str(turn.get("content") or "").strip()
            for turn in history or []
            if isinstance(turn, dict) and turn.get("role") == "user"
        )
        if text and text != asked and not text.startswith("/")
    ][-limit:]
    said = [text[:1000] for text in earlier if not amanah.scan(text, "this chat")]
    rows = [(index, None, text) for index, text in enumerate(said)]
    return said if about(task, rows) else []


def _unanswered_request(history: list[dict] | None) -> str | None:
    """The user's last message when no answer followed it (a reply that failed
    or came back empty is not kept in the history)."""
    turns = [turn for turn in history or [] if turn.get("role") in {"user", "assistant"}]
    if turns and turns[-1].get("role") == "user":
        text = str(turns[-1].get("content") or "").strip()
        return text or None
    return None


def _earlier_request(history: list[dict] | None) -> str | None:
    """The user's most recent message in this chat that names a topic of its own."""
    for turn in list(reversed(history or []))[:8]:
        if turn.get("role") != "user":
            continue
        text = str(turn.get("content") or "").strip()
        if text and not fahm.bare_search(text) and len(re.findall(r"\w+", text)) >= 2:
            return text
    return None


def _matches(stdout: str, value: calc.Number) -> bool:
    printed = stdout.strip().splitlines()[-1].strip() if stdout.strip() else ""
    if printed == calc.render(value):
        return True
    try:
        return math.isclose(float(printed), float(value), rel_tol=1e-9, abs_tol=1e-12)
    except (ValueError, OverflowError):
        return False


def _code_ran(run: dict) -> bool:
    """The program itself ran (a verdict on the code), not a sandbox or permission failure."""
    return not run.get("declined") and not (run.get("error") and not run.get("stderr"))


# Python packages that open a window; MIZAN's sandbox has no screen to show one.
_WINDOW_TOOLKITS = {
    "tkinter": "tkinter", "turtle": "turtle", "customtkinter": "customtkinter",
    "PyQt5": "PyQt", "PyQt6": "PyQt", "PySide2": "PySide", "PySide6": "PySide",
    "wx": "wxPython", "kivy": "Kivy", "pygame": "pygame", "PySimpleGUI": "PySimpleGUI",
    "dearpygui": "Dear PyGui", "flet": "Flet", "arcade": "Arcade", "pyglet": "pyglet",
}  # fmt: skip


def _window_toolkit(code: str) -> str | None:
    """The window toolkit a Python program imports, read from its syntax tree."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # let the run report the syntax error
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            toolkit = _WINDOW_TOOLKITS.get(name.split(".")[0])
            if toolkit:
                return toolkit
    return None


def _ran_clean(run: dict) -> bool:
    return run.get("exit_code") == 0 and not run.get("error")


def _signature(run: dict) -> str:
    if _ran_clean(run):
        return ""
    return tajriba.signature(str(run.get("stderr") or run.get("error") or ""))


def _run_facts(run: dict) -> dict:
    return {
        key: (str(run[key])[:2000] if isinstance(run.get(key), str) else run.get(key))
        for key in ("exit_code", "stdout", "stderr", "error", "duration_ms", "sandbox")
        if key in run
    }
