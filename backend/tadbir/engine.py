"""Tadbir (تدبير): MIZAN's own orchestration of a request.

    Fahm (understand) → plan → act through MIZAN's tools → verify → express

MIZAN decides every step and runs every tool itself, through the same
``_execute_tool_safe`` gate as the agent loop (permissions, Fitrah, Izn,
approvals). The language model (Lisan) is called only for language: writing
or repairing a program, or wording an answer from verified facts; MIZAN
checks that wording (Furqan) and falls back to its own templates. Quran text
never passes through a language model.

Modes (``MIZAN_ORCHESTRATION``): ``mizan`` (default) handles every request
it understands and hands the rest to the general agent loop; ``strict`` also
answers the rest itself through Lisan with no tool control by the model;
``llm`` turns Tadbir off.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from agents.events import emit, summarize
from agents.execution_contract import tool_result_failed

from . import calc, express, fahm, quran
from .express import fence, furqan, phrase
from .lisan import Lisan, LisanUnavailable

MODES = ("mizan", "strict", "llm")
MAX_REPAIRS = 2


def orchestration_mode() -> str:
    value = os.getenv("MIZAN_ORCHESTRATION", "mizan").strip().lower()
    return value if value in MODES else "mizan"


class Defer(Exception):  # noqa: N818 - control flow, not an error
    """MIZAN cannot complete this recipe; let the general agent loop try."""


@dataclass
class Outcome:
    text: str
    verified: bool
    facts: dict[str, Any] = field(default_factory=dict)
    tool_backed: bool = True


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


class Tadbir:
    def __init__(self, agent: Any):
        self.agent = agent
        self.lisan = Lisan(agent)
        self.plan: Plan | None = None
        self._stream = None

    # ── entry point ──────────────────────────────────────────────────────

    async def handle(self, task: str, stream_callback=None) -> dict | None:
        mode = orchestration_mode()
        if mode == "llm" or not isinstance(task, str) or not task.strip():
            return None
        understanding = fahm.understand(task)
        self._stream = stream_callback
        started = time.time()
        if understanding.intent == "converse" and self.lisan.available and fahm.actionable(task):
            # Lisan only translates the wording into MIZAN's intent schema;
            # MIZAN validates every field before acting on it.
            understanding = await self._lisan_understanding(task, understanding)
        handler = getattr(self, f"_{understanding.intent}", None)
        try:
            if understanding.intent == "converse" or handler is None:
                if mode != "strict":
                    return None
                outcome = await self._converse(task, understanding)
            else:
                outcome = await handler(task, understanding)
        except Defer:
            return None
        if self.plan is not None:
            await self.plan.finish()
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
            "orchestration": {
                "by": "mizan",
                "mode": mode,
                **understanding.to_dict(),
                "plan": deepcopy(self.plan.items) if self.plan else [],
                "verified": outcome.verified,
                "language_model_calls": self.lisan.calls,
            },
        }

    # ── shared actions ───────────────────────────────────────────────────

    async def _begin(self, steps: list[str]) -> None:
        self.plan = Plan(steps)
        await self.plan.advance()

    async def _step(self) -> None:
        if self.plan is not None:
            await self.plan.advance()

    async def _tool(self, name: str, params: dict) -> dict:
        """Run one tool through the agent's full safety gate, visibly."""
        call_id = uuid.uuid4().hex
        await emit("tool_start", {"call_id": call_id, "name": name, "input": params})
        if self._stream:
            await self._stream("", chunk_type="tool_use", tool_name=name)
        started = time.perf_counter()
        result = await self.agent._execute_tool_safe(name, params)
        self.agent._add_execution_time("tool_ms", started)
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
        self.agent._last_tool_results.append({"name": name, "result": result})
        return result if isinstance(result, dict) else {"result": result}

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

    async def _lisan_understanding(
        self, task: str, fallback: fahm.Understanding
    ) -> fahm.Understanding:
        try:
            parsed = await self.lisan.parse_intent(task)
        except LisanUnavailable:
            return fallback
        understood = fahm.validate_parsed(parsed, task, fallback.language)
        return understood or fallback

    # ── recipes ──────────────────────────────────────────────────────────

    async def _capabilities(self, task: str, u: fahm.Understanding) -> Outcome:
        await self._begin(["Read MIZAN's live tool registry", "Reply"])
        names = {name for name in self._tool_names() if self._allowed(name)}
        lines = []
        if {"workspace_run"} & names:
            lines.append("code")
        lines.append("calc")
        lines.append("quran")
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
            if orchestration_mode() != "strict":
                raise Defer from exc
            return Outcome(str(exc), False, {"expression": expression}, tool_backed=False)
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
            code = await self.lisan.write_code(task, language)
        except LisanUnavailable as exc:
            raise Defer from exc
        await self._step()
        tries = 1
        run = await self._run(code, language)
        await self._step()
        while (run.get("exit_code") != 0 or run.get("error")) and tries <= MAX_REPAIRS:
            if run.get("declined") or "not permitted" in str(run.get("error", "")):
                break
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
        return Outcome("\n\n".join(parts), verified, {"run": _run_facts(run), "attempts": tries})

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
        call_id = uuid.uuid4().hex
        await emit(
            "tool_start",
            {"call_id": call_id, "name": "quran_text", "input": {"reference": reference.label}},
        )
        started = time.perf_counter()
        try:
            data = await quran.fetch(reference, u.language)
        except quran.QuranUnavailable as exc:
            await emit(
                "tool_result",
                {
                    "call_id": call_id,
                    "name": "quran_text",
                    "ok": False,
                    "summary": str(exc),
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            return Outcome(phrase("quran_unavailable", u.language, reason=str(exc)), False, {})
        await emit(
            "tool_result",
            {
                "call_id": call_id,
                "name": "quran_text",
                "ok": True,
                "summary": f"{len(data['ayahs'])} ayah(s)",
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
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
        return Outcome(f"{answer}\n\n{source_block}", verified, {"sources": len(sources)})

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
        return Outcome(text, True, {"memories": True})

    async def _converse(self, task: str, u: fahm.Understanding) -> Outcome:
        await self._begin(["Answer in words (Lisan)"])
        try:
            text = await self.lisan.converse(task, u.language)
        except LisanUnavailable as exc:
            text = str(exc)
        return Outcome(text, False, {}, tool_backed=False)


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
