"""Multi-agentic modes + parallel-model compare.

Modes:
  - ``single``        : the existing default ReAct agent path (unchanged;
                        handled by POST /api/chat, nothing new here).
  - ``deep_research`` : planner → workers → aggregator → verifier pipeline.

POST /api/modes/deep-research requires explicit per-request confirmation
(``confirmed: true``), otherwise 409. Every run is budget-gated
(``DEEP_RESEARCH_MAX_COST_USD``, ``DEEP_RESEARCH_MAX_TOKENS``) and emits live
progress/cost events.

POST /api/compare fans one prompt out to up to 4 models concurrently and
returns BLIND-labeled responses (A/B/C/D) without revealing the model
mapping. POST /api/compare/{id}/reveal reveals the mapping, and with
``judge: true`` runs an LLM-judge rubric and returns a merged answer that
explicitly separates CONSENSUS from CONTESTED points.

Progress event shape (sent on the chat WebSocket):
    {"type": "mode_progress", "run_id": str, "stage": str, "detail": str,
     "cost_so_far": float, "tokens_so_far": int}
Stages: planning → researching → aggregating → verifying → done.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from security.auth import current_user_id

logger = logging.getLogger("mizan.modes")

router = APIRouter(tags=["modes"])

# ── Progress broadcast (wired by backend/api/main.py) ────────────────────────

_progress_sink: Callable[[dict], Any] | None = None


def set_progress_sink(sink: Callable[[dict], Any] | None) -> None:
    """Set the callable that delivers mode_progress events (e.g. WS broadcast)."""
    global _progress_sink
    _progress_sink = sink


async def emit_progress(
    run_id: str,
    stage: str,
    detail: str = "",
    cost_so_far: float = 0.0,
    tokens_so_far: int = 0,
) -> dict:
    event = {
        "type": "mode_progress",
        "run_id": run_id,
        "stage": stage,
        "detail": detail,
        "cost_so_far": round(cost_so_far, 6),
        "tokens_so_far": tokens_so_far,
    }
    if _progress_sink is not None:
        try:
            res = _progress_sink(event)
            if asyncio.iscoroutine(res):
                await res
        except Exception:  # noqa: BLE001 - progress must never break the run
            logger.warning("mode progress sink failed", exc_info=True)
    return event


# ── Shared LLM access (reuses the app's existing provider layer) ─────────────


def _chat_completion_sync(
    model: str | None, system: str, messages: list[dict], max_tokens: int
) -> tuple[str, int, int]:
    """Call the existing LLM provider layer (blocking). Returns
    (text, input_tokens_est, output_tokens_est)."""
    # Imported lazily to keep module import cheap and avoid import cycles.
    from providers import create_provider  # noqa: PLC0415

    provider = create_provider(model=model)
    if provider is None:
        raise RuntimeError("no LLM provider configured (set an API key)")
    resolved_model = model or os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
    resp = provider.create(
        model=resolved_model, max_tokens=max_tokens, system=system, messages=messages
    )
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    usage = resp.usage or {}
    in_est = usage.get("input", usage.get("input_tokens", usage.get("prompt_tokens")))
    out_est = usage.get("output", usage.get("output_tokens", usage.get("completion_tokens")))
    if in_est is None:
        in_est = sum(len(str(m.get("content", ""))) for m in messages) // 4 + len(system) // 4
    if out_est is None:
        out_est = len(text) // 4
    return text, in_est, out_est


async def _chat_completion(
    model: str | None, system: str, messages: list[dict], max_tokens: int
) -> tuple[str, int, int]:
    return await asyncio.to_thread(_chat_completion_sync, model, system, messages, max_tokens)


# ── Budget ───────────────────────────────────────────────────────────────────


class BudgetExceeded(Exception):
    pass


class BudgetTracker:
    """Hard-capped token/cost budget for a deep-research run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.max_cost_usd = float(os.getenv("DEEP_RESEARCH_MAX_COST_USD", "0.50"))
        self.max_tokens = int(os.getenv("DEEP_RESEARCH_MAX_TOKENS", "40000"))
        self.usd_per_1m = float(os.getenv("DEEP_RESEARCH_USD_PER_1M_TOKENS", "3.0"))
        self.tokens = 0
        self.cost = 0.0

    def record(self, in_tokens: int, out_tokens: int) -> None:
        self.tokens += in_tokens + out_tokens
        self.cost += (in_tokens + out_tokens) / 1_000_000 * self.usd_per_1m
        if self.tokens > self.max_tokens or self.cost > self.max_cost_usd:
            raise BudgetExceeded(
                f"deep_research budget exceeded: {self.tokens} tokens / "
                f"${self.cost:.4f} (caps: {self.max_tokens} tokens / "
                f"${self.max_cost_usd:.2f})"
            )


# ── Deep research pipeline ───────────────────────────────────────────────────


class DeepResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = Field(None, max_length=100)
    confirmed: bool = Field(default=False, description="Explicit per-request user confirmation")
    max_subquestions: int = Field(default=4, ge=2, le=5)
    model: str | None = Field(None, max_length=200)


class DeepResearchResponse(BaseModel):
    run_id: str
    query: str
    answer: str
    subquestions: list[str]
    worker_outputs: list[dict]
    unsupported_claims: list[str]
    tokens_used: int
    cost_usd: float


_PLANNER_SYSTEM = (
    "You are a research planner. Break the user's question into focused "
    "sub-questions that can be answered independently. Respond with a JSON "
    "array of strings only, no other text."
)

_WORKER_SYSTEM = (
    "You are a research worker. Answer the sub-question directly and "
    "concisely. Use only what you know from training; do NOT invent "
    "citations, URLs, quotes, statistics, or paper titles. If you are "
    "unsure, say so explicitly instead of guessing."
)

_AGGREGATOR_SYSTEM = (
    "You are a research synthesizer. Combine the worker findings into one "
    "coherent answer. Every factual claim must be traceable to the worker "
    "findings below; do not add new claims of your own. List key claims as "
    "bullet points (one per line, starting with '- ')."
)

_JUDGE_RUBRIC = """You are an impartial judge comparing model answers.
Score EACH answer 1-10 on:
- factual_accuracy: correctness of claims; penalize invented citations/stats
- relevance_completeness: addresses the prompt fully
- clarity_concision: clear, well-structured, not bloated
- safety_honesty: no deception, appropriate uncertainty

Then list CONSENSUS points (claims all/most answers agree on) and CONTESTED
points (claims answers disagree on or only one makes).

Respond ONLY with valid JSON:
{"scores": {"A": {"factual_accuracy": n, "relevance_completeness": n,
"clarity_concision": n, "safety_honesty": n, "total": n}, ...},
"consensus": ["..."], "contested": ["..."], "winner": "A"|"B"|..., "reason": "..."}
"""


async def _plan_subquestions(
    query: str, max_n: int, model: str | None, budget: BudgetTracker
) -> list[str]:
    text, in_t, out_t = await _chat_completion(
        model,
        _PLANNER_SYSTEM,
        [{"role": "user", "content": query}],
        max_tokens=600,
    )
    budget.record(in_t, out_t)
    try:
        items = json.loads(text)
        if isinstance(items, list):
            return [str(x).strip() for x in items if str(x).strip()][:max_n]
    except (json.JSONDecodeError, ValueError):
        pass
    # Deterministic fallback: split on sentence boundaries.
    import re

    parts = [p.strip() for p in re.split(r"[.?!]\s+", query) if p.strip()]
    return (parts or [query])[:max_n]


async def _worker_answer(
    subq: str, model: str | None, budget: BudgetTracker, sem: asyncio.Semaphore
) -> dict:
    async with sem:
        try:
            text, in_t, out_t = await _chat_completion(
                model,
                _WORKER_SYSTEM,
                [{"role": "user", "content": subq}],
                max_tokens=1200,
            )
            budget.record(in_t, out_t)
            return {"subquestion": subq, "answer": text, "ok": True}
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - one failed worker ≠ failed run
            logger.warning("deep-research worker failed: %s", e)
            return {"subquestion": subq, "answer": "", "ok": False, "error": str(e)[:200]}


async def _aggregate(
    query: str, worker_outputs: list[dict], model: str | None, budget: BudgetTracker
) -> str:
    findings = "\n\n".join(
        f"[{i + 1}] Sub-question: {w['subquestion']}\nFinding: {w['answer']}"
        for i, w in enumerate(worker_outputs)
        if w.get("ok")
    )
    text, in_t, out_t = await _chat_completion(
        model,
        _AGGREGATOR_SYSTEM,
        [{"role": "user", "content": f"Question: {query}\n\nWorker findings:\n{findings}"}],
        max_tokens=2000,
    )
    budget.record(in_t, out_t)
    return text


def _extract_claims(answer: str) -> list[str]:
    claims = []
    for line in answer.splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ", "• ")):
            claim = s[2:].strip()
            if claim:
                claims.append(claim)
    return claims


def _verify_claims(answer: str, worker_outputs: list[dict]) -> list[str]:
    """Flag claims with no keyword support in worker outputs (honest check:
    no invented citations, no LLM judgement — pure overlap)."""
    corpus = " ".join(w.get("answer", "") for w in worker_outputs).lower()
    import re

    unsupported = []
    for claim in _extract_claims(answer):
        words = [w for w in re.findall(r"[a-zA-Z]{4,}", claim.lower()) if w]
        if not words:
            continue
        hits = sum(1 for w in words if w in corpus)
        if hits / len(words) < 0.3:
            unsupported.append(claim)
    return unsupported


async def run_deep_research(
    query: str,
    model: str | None = None,
    max_subquestions: int = 4,
    run_id: str | None = None,
) -> DeepResearchResponse:
    """Planner → workers → aggregator → verifier pipeline with budget + events."""
    run_id = run_id or f"dr-{uuid.uuid4().hex[:12]}"
    budget = BudgetTracker(run_id)

    await emit_progress(run_id, "planning", "breaking query into sub-questions")
    try:
        subqs = await _plan_subquestions(query, max_subquestions, model, budget)
        await emit_progress(
            run_id, "researching", f"{len(subqs)} workers", budget.cost, budget.tokens
        )
        sem = asyncio.Semaphore(4)
        worker_outputs = await asyncio.gather(
            *(_worker_answer(q, model, budget, sem) for q in subqs)
        )
        ok_outputs = [w for w in worker_outputs if w.get("ok")]
        if not ok_outputs:
            raise RuntimeError("all research workers failed")

        await emit_progress(
            run_id, "aggregating", "synthesizing findings", budget.cost, budget.tokens
        )
        answer = await _aggregate(query, ok_outputs, model, budget)

        await emit_progress(run_id, "verifying", "checking claims", budget.cost, budget.tokens)
        unsupported = _verify_claims(answer, ok_outputs)

        await emit_progress(run_id, "done", "research complete", budget.cost, budget.tokens)
        return DeepResearchResponse(
            run_id=run_id,
            query=query,
            answer=answer,
            subquestions=subqs,
            worker_outputs=ok_outputs,
            unsupported_claims=unsupported,
            tokens_used=budget.tokens,
            cost_usd=round(budget.cost, 6),
        )
    except BudgetExceeded as e:
        await emit_progress(run_id, "done", f"stopped: {e}", budget.cost, budget.tokens)
        raise HTTPException(402, str(e)) from e


@router.post("/api/modes/deep-research", response_model=DeepResearchResponse)
async def deep_research(req: DeepResearchRequest):
    """Run the deep_research pipeline. Requires confirmed=true (else 409)."""
    if not req.confirmed:
        raise HTTPException(
            409,
            "deep_research requires explicit confirmation: resubmit with "
            "'confirmed: true'. Estimated budget: up to "
            f"${float(os.getenv('DEEP_RESEARCH_MAX_COST_USD', '0.50')):.2f} / "
            f"{os.getenv('DEEP_RESEARCH_MAX_TOKENS', '40000')} tokens.",
        )
    return await run_deep_research(
        req.query, model=req.model, max_subquestions=req.max_subquestions
    )


# ── Parallel-model compare ───────────────────────────────────────────────────


_COMPARE_STORE: dict[str, dict] = {}
_COMPARE_TTL_S = 3600
_LABELS = ["A", "B", "C", "D"]


class CompareRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    models: list[str] = Field(..., min_length=2, max_length=4)
    judge: bool = Field(default=False, description="Run the LLM judge rubric too")


class BlindResult(BaseModel):
    label: str
    response: str


class CompareResponse(BaseModel):
    compare_id: str
    results: list[BlindResult]


class RevealRequest(BaseModel):
    choice: str | None = Field(None, description="User's pick, e.g. 'A'")
    judge: bool = Field(default=False, description="Run the LLM judge rubric")


class JudgeScores(BaseModel):
    factual_accuracy: int
    relevance_completeness: int
    clarity_concision: int
    safety_honesty: int
    total: int


class RevealResponse(BaseModel):
    compare_id: str
    mapping: dict[str, str]
    results: list[BlindResult]
    user_choice: str | None = None
    judge: dict | None = None
    merged_answer: str | None = None


def _prune_compare_store() -> None:
    now = time.time()
    for cid in [c for c, v in _COMPARE_STORE.items() if now - v["created_at"] > _COMPARE_TTL_S]:
        del _COMPARE_STORE[cid]


async def _one_completion(model: str, prompt: str, sem: asyncio.Semaphore) -> str:
    async with sem:
        try:
            text, _, _ = await _chat_completion(
                model,
                "Answer directly and helpfully.",
                [{"role": "user", "content": prompt}],
                max_tokens=1500,
            )
            return text
        except Exception as e:  # noqa: BLE001
            logger.warning("compare completion failed for %s: %s", model, e)
            return f"[model unavailable: {str(e)[:150]}]"


def _merge_answer(judge_data: dict) -> str:
    consensus = judge_data.get("consensus", [])
    contested = judge_data.get("contested", [])
    out = ["## CONSENSUS (models agree)"]
    out += [f"- {c}" for c in consensus] or ["- (none identified)"]
    out += ["", "## CONTESTED (models disagree or single-source)"]
    out += [f"- {c}" for c in contested] or ["- (none identified)"]
    return "\n".join(out)


async def _run_judge(prompt: str, blind: list[BlindResult]) -> dict:
    labeled = "\n\n".join(f"[{r.label}] {r.response}" for r in blind)
    text, _, _ = await _chat_completion(
        None,
        _JUDGE_RUBRIC,
        [{"role": "user", "content": f"Prompt: {prompt}\n\nAnswers:\n{labeled}"}],
        max_tokens=1500,
    )
    try:
        data = json.loads(text)
        return {
            "scores": data.get("scores", {}),
            "consensus": data.get("consensus", []),
            "contested": data.get("contested", []),
            "winner": data.get("winner"),
            "reason": data.get("reason", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "scores": {},
            "consensus": [],
            "contested": [],
            "winner": None,
            "reason": "judge output was not valid JSON; raw output withheld",
        }


@router.post("/api/compare", response_model=CompareResponse)
async def compare(req: CompareRequest):
    """Fan one prompt out to N models concurrently; blind labels only."""
    if len(set(req.models)) != len(req.models):
        raise HTTPException(400, "models must be distinct")
    _prune_compare_store()
    compare_id = f"cmp-{uuid.uuid4().hex[:12]}"
    sem = asyncio.Semaphore(4)
    texts = await asyncio.gather(*(_one_completion(m, req.prompt, sem) for m in req.models))
    mapping = {label: model for label, model in zip(_LABELS, req.models, strict=False)}
    results = [
        BlindResult(label=label, response=text) for label, text in zip(_LABELS, texts, strict=False)
    ]
    _COMPARE_STORE[compare_id] = {
        "created_at": time.time(),
        "owner_id": current_user_id(),
        "prompt": req.prompt,
        "mapping": mapping,
        "results": results,
    }
    resp = CompareResponse(compare_id=compare_id, results=results)
    if req.judge:
        return await reveal(compare_id, RevealRequest(judge=True, choice=None))
    return resp


@router.post("/api/compare/{compare_id}/reveal", response_model=RevealResponse)
async def reveal(compare_id: str, req: RevealRequest):
    """Reveal the model mapping; optionally run the LLM judge rubric."""
    entry = _COMPARE_STORE.get(compare_id)
    from security.auth import current_user_id

    if entry is None or entry.get("owner_id") != current_user_id():
        raise HTTPException(404, "unknown or expired compare_id")
    if req.choice is not None and req.choice not in entry["mapping"]:
        raise HTTPException(400, f"choice must be one of {list(entry['mapping'])}")
    out = RevealResponse(
        compare_id=compare_id,
        mapping=entry["mapping"],
        results=entry["results"],
        user_choice=req.choice,
    )
    if req.judge:
        judge_data = await _run_judge(entry["prompt"], entry["results"])
        out.judge = judge_data
        out.merged_answer = _merge_answer(judge_data)
    return out


@router.get("/api/modes", response_model=list[str])
async def list_modes():
    """Available agent modes: 'single' (default ReAct path) and 'deep_research'."""
    return ["single", "deep_research"]
