"""Qwen3 serverless use-case wiring (all behind the ``QWEN3_ENABLED`` flag).

Use cases:
  1. Chat (SSE)            — Qwen3 is the generation; every response carries
                             the QG understanding layer (root/pattern/role)
                             from ``api.qwen3_understanding`` (existing
                             repo code, nothing rewritten).
  2. WSD                  — Qwen3 as optional reranker over the deterministic
                             sense inventory (``api.ruh_disambiguate``).
  3. I'rab / determination — Qwen3 drafts grounded in the existing
                             morphology analyzer's token evidence, with a
                             machine-checked citation pass.
  4. QG-B grounded Q&A     — Qwen3 draft + QG verification (quote grounding
                             against the source paragraph, root provenance,
                             yaqin tagging). Attested answers only.

Every entry point raises :class:`Qwen3Unavailable` (→ HTTP 503) when the
flag is off or the endpoint cannot serve, so callers fall back to the
pre-existing behavior instead of silently degrading.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from api.qwen3_client import (
    Qwen3Config,
    Qwen3Error,
    Qwen3RequestError,
    Qwen3ResponseError,
    Qwen3Unavailable,
    get_client,
    qwen3_enabled,
)
from api.qwen3_understanding import analyze_understanding
from api.ruh_disambiguate import DisambiguateRequest, DisambiguateResponse

logger = logging.getLogger("mizan.api.qwen3")

router = APIRouter(prefix="/v1/qwen3", tags=["qwen3"])

_ARABIC_RUN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]{2,}")
_CITATION_RE = re.compile(r"\[tok (\d+)\]")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(..., description="'system' | 'user' | 'assistant'")
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    system: str | None = None
    model: str | None = None
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    include_understanding: bool = Field(
        default=True, description="Attach the root/pattern/role understanding layer."
    )


class ChatResponse(BaseModel):
    text: str
    model: str
    usage: dict[str, Any]
    understanding: dict[str, Any] | None = None


class GroundedQARequest(BaseModel):
    question: str = Field(..., min_length=1)
    paragraph: str = Field(..., min_length=1, description="The ONLY source the answer may use.")
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class GroundedQAResponse(BaseModel):
    draft: str
    model: str
    usage: dict[str, Any]
    verification: dict[str, Any]


class GroundedAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Arabic text to analyze.")
    instruction: str | None = Field(
        default=None, description="Extra guidance, e.g. 'focus on the verb forms'."
    )
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class GroundedAnalysisResponse(BaseModel):
    draft: str
    model: str
    usage: dict[str, Any]
    evidence: list[dict[str, Any]]
    citation_check: dict[str, Any]


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def _http_from_qwen3(exc: Qwen3Error) -> HTTPException:
    if isinstance(exc, Qwen3Unavailable):
        return HTTPException(status_code=503, detail={"code": exc.code, "detail": exc.detail})
    if isinstance(exc, (Qwen3RequestError, Qwen3ResponseError)):
        return HTTPException(status_code=502, detail={"code": exc.code, "detail": exc.detail})
    return HTTPException(status_code=500, detail={"code": "qwen3_error", "detail": str(exc)})


# ---------------------------------------------------------------------------
# Use case 1 — Chat (Qwen3 generation + understanding layer)
# ---------------------------------------------------------------------------


async def chat_generate(messages: list[dict[str, str]], **opts: Any) -> dict[str, Any]:
    """Generate a chat completion; attach the understanding layer.

    Raises Qwen3Unavailable when the flag is off or the endpoint fails —
    callers fall back to the previous generation path.
    """
    client = get_client()
    result = await client.generate(messages, **opts)
    out: dict[str, Any] = {
        "text": result.text,
        "model": result.model,
        "usage": result.usage,
        "understanding": None,
    }
    if opts.get("include_understanding", True):
        try:
            out["understanding"] = analyze_understanding(result.text)
        except Exception as exc:  # noqa: BLE001 — analytics must not break chat
            logger.warning("qwen3 understanding layer failed: %s", exc)
    return out


# ---------------------------------------------------------------------------
# Use case 2 — WSD reranker
# ---------------------------------------------------------------------------

_RERANK_SYSTEM = (
    "You are a word-sense disambiguation judge for Arabic. "
    "Given a word, its context, and candidate senses, rank the candidates "
    'best-first. Reply with ONLY a JSON object: {"order": ["<sense_id>", ...]} '
    "containing every candidate sense_id exactly once. No other text."
)


def _rerank_prompt(word: str, context: str, candidates: list[dict[str, Any]]) -> str:
    lines = [
        f"Word: {word}",
        f"Context: {context}",
        "Candidates:",
    ]
    for cand in candidates:
        lines.append(f"- {cand['sense_id']}: {cand.get('gloss_en') or cand.get('gloss_ar') or ''}")
    lines.append('Reply with ONLY the JSON object {"order": [...]}.')
    return "\n".join(lines)


def _parse_rerank_order(text: str, candidates: list[dict[str, Any]]) -> list[str] | None:
    """Validate the model's ordering; None = unusable (caller falls back)."""
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    order = data.get("order")
    valid_ids = [c["sense_id"] for c in candidates]
    if (
        not isinstance(order, list)
        or sorted(order) != sorted(valid_ids)
        or any(not isinstance(s, str) for s in order)
    ):
        return None
    return list(order)


async def rerank_senses(
    word: str, context: str, candidates: list[dict[str, Any]], **opts: Any
) -> list[str] | None:
    """Ask Qwen3 to order candidate senses best-first.

    Returns the validated ordering, or None when the endpoint is unavailable
    or its answer is unusable — the caller keeps the deterministic order.
    """
    if not candidates:
        return None
    client = get_client()
    try:
        result = await client.generate(
            [{"role": "user", "content": _rerank_prompt(word, context, candidates)}],
            system=_RERANK_SYSTEM,
            temperature=0.0,
            max_tokens=256,
            **opts,
        )
    except Qwen3Unavailable:
        return None
    return _parse_rerank_order(result.text, candidates)


def rerank_senses_sync(
    word: str, context: str, candidates: list[dict[str, Any]], **opts: Any
) -> list[str] | None:
    """Sync variant for sync call sites (e.g. the disambiguation endpoint)."""
    if not candidates:
        return None
    client = get_client()
    try:
        result = client.generate_sync(
            [{"role": "user", "content": _rerank_prompt(word, context, candidates)}],
            system=_RERANK_SYSTEM,
            temperature=0.0,
            max_tokens=256,
            **opts,
        )
    except Qwen3Unavailable:
        return None
    return _parse_rerank_order(result.text, candidates)


def maybe_rerank_disambiguation(
    word: str, context: str, alternatives: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Flag-gated rerank for the /v1/disambiguate endpoint.

    Returns None when the flag is off or Qwen3 cannot rerank — the caller
    keeps the deterministic result untouched (the fallback).
    """
    if not qwen3_enabled():
        return None
    order = rerank_senses_sync(word, context, alternatives)
    if order is None:
        logger.info("qwen3 rerank unavailable/invalid; keeping deterministic sense order")
        return None
    by_id = {a["sense_id"]: a for a in alternatives}
    reordered = [by_id[sid] for sid in order if sid in by_id]
    if len(reordered) != len(alternatives):
        return None
    return {
        "alternatives": reordered,
        "info": {
            "applied": True,
            "model": Qwen3Config.from_env().model,
            "order": order,
            "reason": None,
        },
    }


# ---------------------------------------------------------------------------
# Use case 3 — I'rab / determination grounded in the morphology analyzer
# ---------------------------------------------------------------------------

_IRAB_SYSTEM = (
    "You are an Arabic grammar (sarf/i'rab) analyst. You are given token "
    "evidence from a deterministic morphology analyzer — root, pattern, "
    "lemma, POS per token, indexed as [tok N]. Ground EVERY grammatical "
    "claim in that evidence and cite tokens as [tok N]. Never invent roots, "
    "patterns, or roles that contradict the evidence; if the evidence is "
    "silent, say so."
)

MAX_ANALYSIS_CHARS = 2000
MAX_ANALYSIS_TOKENS = 120


def _morphology_evidence(text: str) -> list[dict[str, Any]] | None:
    try:
        from api.ruh_morphology import _service_analyze  # noqa: SLF001
    except Exception as exc:
        logger.warning("qwen3 grounded-analysis: morphology service unavailable: %s", exc)
        return None
    try:
        result = _service_analyze(text[:MAX_ANALYSIS_CHARS], mode="deterministic", domain="general")
    except Exception as exc:  # noqa: BLE001 — evidence failure is a 503, not a crash
        logger.warning("qwen3 grounded-analysis: morphology service failed: %s", exc)
        return None
    tokens = result.get("tokens")
    if not isinstance(tokens, list):
        return None
    evidence = []
    for i, tok in enumerate(tokens[:MAX_ANALYSIS_TOKENS]):
        evidence.append(
            {
                "i": i,
                "surface": tok.get("surface"),
                "root": tok.get("root"),
                "pattern": tok.get("pattern"),
                "lemma": tok.get("lemma"),
                "pos": tok.get("pos"),
                "diac": tok.get("diac"),
            }
        )
    return evidence


async def grounded_analysis(
    text: str, instruction: str | None = None, **opts: Any
) -> dict[str, Any]:
    """Qwen3 i'rab analysis grounded in the existing morphology analyzer.

    The draft is checked for [tok N] citations against the evidence table.
    Raises Qwen3Unavailable when the flag is off or the endpoint fails.
    """
    evidence = _morphology_evidence(text)
    if evidence is None:
        raise Qwen3Unavailable("qwen3_no_evidence", "morphology analyzer unavailable")
    user_content = (
        "Token evidence (index, surface, root, pattern, lemma, pos):\n"
        + json.dumps(evidence, ensure_ascii=False)
        + "\n\nAnalyze the grammar (sarf/i'rab) of the text below. "
        "Cite every claim as [tok N]."
        + (f"\nExtra instruction: {instruction}" if instruction else "")
        + f"\n\nText: {text[:MAX_ANALYSIS_CHARS]}"
    )
    client = get_client()
    result = await client.generate(
        [{"role": "user", "content": user_content}],
        system=_IRAB_SYSTEM,
        temperature=opts.pop("temperature", 0.3),
        max_tokens=opts.pop("max_tokens", 1024),
        **opts,
    )
    cited = [int(n) for n in _CITATION_RE.findall(result.text)]
    valid = [n for n in cited if 0 <= n < len(evidence)]
    citation_check = {
        "cited": cited,
        "valid_citations": valid,
        "invalid_citations": [n for n in cited if n not in valid],
        "evidence_tokens": len(evidence),
    }
    return {
        "draft": result.text,
        "model": result.model,
        "usage": result.usage,
        "evidence": evidence,
        "citation_check": citation_check,
    }


# ---------------------------------------------------------------------------
# Use case 4 — QG-B grounded Q&A (Qwen3 draft + QG verification)
# ---------------------------------------------------------------------------

_GROUNDED_QA_SYSTEM = (
    "You are Mizan's Quranic study assistant. Answer the question using ONLY "
    "the paragraph below as your source. Quote the Arabic verbatim when you "
    "rely on it. If the paragraph does not contain the answer, say so "
    "explicitly — never invent verses, quotes, or facts."
)


def _verify_draft(question: str, paragraph: str, draft: str) -> dict[str, Any]:
    """QG verification pass over a Qwen3 draft.

    - Every Arabic quote in the draft must occur verbatim in the source
      paragraph (substring check on normalized text).
    - Every Arabic token's root is resolved through the existing QCA layer
      with verified/heuristic provenance.
    """

    def norm(s: str) -> str:
        return " ".join(s.split())

    para_norm = norm(paragraph)
    quotes: list[dict[str, Any]] = []
    for span in _ARABIC_RUN_RE.findall(draft):
        span_norm = norm(span)
        if len(span_norm) >= 2:
            quotes.append({"quote": span_norm, "found_in_source": span_norm in para_norm})
    # Deduplicate while keeping order.
    seen: set[str] = set()
    unique_quotes: list[dict[str, Any]] = []
    for q in quotes:
        if q["quote"] not in seen:
            seen.add(q["quote"])
            unique_quotes.append(q)

    roots: list[dict[str, Any]] = []
    try:
        from qca.morphology_api import analyze_word

        for span in unique_quotes[:20]:
            for token in span["quote"].split()[:8]:
                try:
                    analysis = analyze_word(token)
                except Exception:  # noqa: BLE001,S110 — skip unanalyzable tokens
                    continue
                roots.append(
                    {
                        "token": token,
                        "root": analysis.get("root") or None,
                        "root_provenance": analysis.get("root_provenance", "heuristic"),
                    }
                )
    except Exception as exc:
        logger.warning("qwen3 grounded-qa: root verification unavailable: %s", exc)

    if not unique_quotes:
        attested = False
        reason = "no verifiable Arabic quotes in the draft"
    elif all(q["found_in_source"] for q in unique_quotes):
        attested = True
        reason = "all draft quotes verified verbatim in the source paragraph"
    else:
        attested = False
        reason = "some draft quotes do not occur in the source paragraph"

    return {
        "question": question,
        "quotes": unique_quotes,
        "roots": roots,
        "attested": attested,
        "attestation_reason": reason,
        "yaqin": {
            # The draft itself is inferential (Ilm al-Yaqin); quotes found
            # verbatim in the source are witnessed (Ayn al-Yaqin).
            "draft": "ilm_al_yaqin",
            "verified_quotes": "ayn_al_yaqin",
        },
    }


async def grounded_qa(question: str, paragraph: str, **opts: Any) -> dict[str, Any]:
    """Attested Q&A: Qwen3 drafts from the paragraph, QG verifies.

    Raises Qwen3Unavailable when the flag is off or the endpoint fails.
    """
    user_content = f"Paragraph (your only source):\n{paragraph}\n\nQuestion: {question}"
    client = get_client()
    result = await client.generate(
        [{"role": "user", "content": user_content}],
        system=_GROUNDED_QA_SYSTEM,
        temperature=opts.pop("temperature", 0.3),
        max_tokens=opts.pop("max_tokens", 1024),
        **opts,
    )
    return {
        "draft": result.text,
        "model": result.model,
        "usage": result.usage,
        "verification": _verify_draft(question, paragraph, result.text),
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


@router.get("/health", summary="Qwen3 integration status (never exposes the API key)")
async def qwen3_health(probe: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = await get_client().health(probe=probe)
    return report


@router.post("/chat", response_model=ChatResponse, summary="Qwen3 chat + understanding layer")
async def qwen3_chat(req: ChatRequest) -> ChatResponse:
    try:
        out = await chat_generate(
            [m.model_dump() for m in req.messages],
            system=req.system,
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            include_understanding=req.include_understanding,
        )
    except Qwen3Error as exc:
        raise _http_from_qwen3(exc) from exc
    return ChatResponse(**out)


def _sse_frame(kind: str, data: dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream", summary="Qwen3 chat as SSE, with a terminal understanding event")
async def qwen3_chat_stream(req: ChatRequest) -> StreamingResponse:
    if not qwen3_enabled():
        raise HTTPException(
            status_code=503, detail={"code": "qwen3_disabled", "detail": "QWEN3_ENABLED is not set"}
        )
    client = get_client()
    messages = [m.model_dump() for m in req.messages]

    async def event_gen():
        yield _sse_frame("start", {"model": client.config.model})
        parts: list[str] = []
        try:
            async for delta in client.generate_stream(
                messages,
                system=req.system,
                model=req.model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            ):
                parts.append(delta)
                yield _sse_frame("token", {"delta": delta})
        except Qwen3Error as exc:
            yield _sse_frame("error", {"code": exc.code, "detail": exc.detail})
            return
        text = "".join(parts)
        if req.include_understanding:
            try:
                yield _sse_frame("understanding", analyze_understanding(text))
            except Exception as exc:  # noqa: BLE001 — analytics must not break the stream
                logger.warning("qwen3 stream understanding failed: %s", exc)
        yield _sse_frame("done", {"model": client.config.model, "usage": {}})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post(
    "/grounded-qa",
    response_model=GroundedQAResponse,
    summary="Attested Q&A: Qwen3 draft + QG verification",
)
async def qwen3_grounded_qa(req: GroundedQARequest) -> GroundedQAResponse:
    try:
        out = await grounded_qa(
            req.question,
            req.paragraph,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
    except Qwen3Error as exc:
        raise _http_from_qwen3(exc) from exc
    return GroundedQAResponse(**out)


@router.post(
    "/grounded-analysis",
    response_model=GroundedAnalysisResponse,
    summary="I'rab analysis grounded in morphology evidence, with citation check",
)
async def qwen3_grounded_analysis(req: GroundedAnalysisRequest) -> GroundedAnalysisResponse:
    try:
        out = await grounded_analysis(
            req.text,
            req.instruction,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
    except Qwen3Error as exc:
        raise _http_from_qwen3(exc) from exc
    return GroundedAnalysisResponse(**out)


@router.post("/disambiguate", summary="WSD with Qwen3 rerank (explicit opt-in path)")
async def qwen3_disambiguate(req: DisambiguateRequest) -> DisambiguateResponse:
    """Same deterministic pipeline as /v1/disambiguate, then Qwen3 reranks.

    Unlike /v1/disambiguate (where rerank is best-effort), this endpoint
    requires Qwen3: 503 when the flag is off or rerank fails.
    """
    from api import ruh_disambiguate as rd

    if not qwen3_enabled():
        raise HTTPException(
            status_code=503, detail={"code": "qwen3_disabled", "detail": "QWEN3_ENABLED is not set"}
        )
    inventory = rd.get_inventory()
    dis_mod = rd._load_sense_module("disambiguate")  # noqa: SLF001
    result = dis_mod.disambiguate(
        req.word, req.context, inventory, top_k=req.top_k, threshold=req.threshold
    )
    d = result.to_dict()
    resp = rd.response_from_result(d)
    reranked = maybe_rerank_disambiguation(req.word, req.context, list(d["alternatives"]))
    if reranked is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "qwen3_rerank_failed", "detail": "Qwen3 rerank unavailable"},
        )
    resp.alternatives = [rd.SenseAlternativeOut(**a) for a in reranked["alternatives"]]
    resp.qwen3 = rd.Qwen3RerankInfo(**reranked["info"])
    return resp
