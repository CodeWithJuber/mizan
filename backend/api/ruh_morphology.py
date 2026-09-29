"""Ruh Morphology Analysis API — study use-case #2 ("the wedge").

``POST /v1/analyze`` -> per-token ``{surface, root, pattern, lemma, pos,
diac, confidence}``. Deterministic rule-based backend (torch-free);
a trained-weight model path can be wired later via ``analyze_with_model``
in ``ruh_model/service/analyze.py``.

HONESTY NOTE (also in the OpenAPI description): accuracy vs CAMeL Tools is
UNVERIFIED — the eval harness (``ruh_model/eval/morphology_eval.py``,
separate track) is pending. Confidence scores are heuristic, never
calibrated. Do not present this endpoint's output as benchmarked.

This module is intentionally importable without torch and without importing
``backend.api.main`` (which pulls the full agent stack). The service module
is loaded by file path; the coordinator wires this router into ``main.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

SERVICE_PATH = Path(__file__).resolve().parents[2] / "ruh_model" / "service" / "analyze.py"


def _load_service() -> object:
    if not SERVICE_PATH.exists():
        raise RuntimeError(
            f"Morphology service module not found at {SERVICE_PATH}. "
            "The ruh_morphology router requires ruh_model/service/analyze.py."
        )
    spec = importlib.util.spec_from_file_location("ruh_morph_service", SERVICE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load service module from {SERVICE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_service = _load_service()
_service_analyze = _service.analyze  # type: ignore[attr-defined]
_service_capabilities = _service.get_capabilities  # type: ignore[attr-defined]

MAX_TEXT_CHARS = 20000
MAX_TOKENS = 2000

EVAL_DISCLAIMER = (
    "Deterministic rule-based morphology (Bayan tables). "
    "Accuracy vs CAMeL Tools UNVERIFIED — eval harness "
    "ruh_model/eval/morphology_eval.py (separate track) pending. "
    "Confidence is heuristic/unverified, never calibrated."
)

router = APIRouter(tags=["ruh-morphology"])


# ---------------------------------------------------------------------------
# Schemas (Pydantic v2)
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Request body for POST /v1/analyze."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_CHARS,
        description="Arabic (or mixed) text to analyze, 1..20000 chars.",
    )
    mode: Literal["deterministic", "nbest"] = Field(
        default="deterministic",
        description="'deterministic' returns the argmax analysis per token; "
        "'nbest' adds scored runner-up candidates per token.",
    )
    domain: Literal["general", "quranic"] = Field(
        default="general",
        description="'quranic' applies conservative confidence (capped) and "
        "low-confidence flags — a wrong Quranic analysis is not a normal bug.",
    )

    @field_validator("text")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class TokenAlternative(BaseModel):
    root: str | None
    pattern: str
    lemma: str | None
    pos: str | None
    confidence: float
    confidence_source: str


class TokenAnalysis(BaseModel):
    surface: str
    root: str | None = Field(
        default=None, description="Trilateral root (e.g. ك-ت-ب as كتب), null when none."
    )
    pattern: str = Field(description="Morphological pattern / shape class, heuristic.")
    lemma: str | None = Field(default=None, description="Citation form when tables provide one.")
    pos: str | None = Field(default=None, description="Coarse POS tag, heuristic.")
    diac: str | None = Field(
        default=None,
        description="Diacritics only if present in the input; never invented.",
    )
    confidence: float = Field(description="Heuristic score 0..1 — NOT calibrated.")
    confidence_source: str = Field(description="Always 'heuristic/unverified' here.")
    flags: list[str] = Field(default_factory=list)
    alternatives: list[TokenAlternative] | None = Field(
        default=None, description="Runner-up candidates (nbest mode only)."
    )


class ModelInfo(BaseModel):
    mode: str
    backend_version: str
    confidence_source: str
    eval_note: str


class AnalyzeResponse(BaseModel):
    tokens: list[TokenAnalysis]
    model_info: ModelInfo


class HealthResponse(BaseModel):
    status: str
    tables_loaded: bool
    root_count: int
    model_available: bool
    model_path: str | None
    mode: str
    backend_version: str
    confidence_source: str
    eval_note: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/v1/analyze",
    response_model=AnalyzeResponse,
    summary="Morphological analysis per token",
    description=EVAL_DISCLAIMER,
)
def analyze_text(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze text into per-token morphology (deterministic, rule-based)."""
    try:
        result = _service_analyze(request.text, mode=request.mode, domain=request.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tokens = result["tokens"]
    if len(tokens) > MAX_TOKENS:
        raise HTTPException(
            status_code=400,
            detail=f"too many tokens ({len(tokens)} > {MAX_TOKENS}); split the text",
        )
    return AnalyzeResponse(**result)


@router.get(
    "/v1/analyze/health",
    response_model=HealthResponse,
    summary="Morphology backend capability probe",
    description="Reports whether root tables loaded and whether trained "
    "model weights are available. " + EVAL_DISCLAIMER,
)
def analyze_health() -> HealthResponse:
    """Probe backend capabilities (tables loaded? model available?)."""
    caps = _service_capabilities()
    return HealthResponse(
        status="ok" if caps["tables_loaded"] else "degraded",
        **caps,
    )
