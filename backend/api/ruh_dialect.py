"""Dialect normalization API (use case #6) -- BETA.

``POST /v1/normalize`` maps one dialectal Arabic word into root-space
``{surface, dialect, root, pattern, confidence, foreign, needs_review}``
via explicit per-region affix tables + the shared rule-based analyzer.

BETA / UNVERIFIED -- honest OpenAPI notes:
* Ruh's analyzer has NEVER been run on dialectal text; the NADI/MADAR
  eval harness (separate track) has not reported. Every normalization
  is provisional -- this API is deterministic tables, not a measured
  model.
* Non-Semitic loans (Maghrebi French stock) return ``foreign: true,
  root: null`` -- a root is never hallucinated for them.
* Unknown forms return low confidence + ``needs_review: true``.

This router is standalone; wire it into the main FastAPI app with
``app.include_router(router)`` when ready.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ._ruh_loader import load_ruh_module

_normalize_mod = load_ruh_module("ruh_model/dialect/normalize.py", "ruh_api_dialect_normalize")

normalize_word = _normalize_mod.normalize

router = APIRouter(prefix="/v1", tags=["ruh-dialect (beta)"])

BETA_NOTE = (
    "BETA/UNVERIFIED: deterministic affix tables + rule-based analyzer; "
    "never evaluated on real dialectal text (NADI/MADAR eval pending). "
    "Do not use for consequential decisions."
)

DialectHint = Literal["egyptian", "levantine", "gulf", "maghrebi"]


class NormalizeRequest(BaseModel):
    """One dialectal word to normalize into root-space."""

    word: str = Field(..., min_length=1, max_length=100, description="Single dialectal word")
    dialect_hint: DialectHint | None = Field(
        default=None,
        description="Region hint; omit for auto-detect (may misattribute)",
    )


class NormalizeResponse(BaseModel):
    surface: str
    dialect: str
    root: str | None
    pattern: str
    confidence: float
    foreign: bool
    needs_review: bool
    beta: bool = True
    note: str = BETA_NOTE


@router.post(
    "/normalize",
    response_model=NormalizeResponse,
    summary="Normalize a dialectal word to root-space (beta)",
    description=(
        "Deterministic per-region affix stripping + rule-based root "
        "extraction. BETA: never evaluated on real dialectal text "
        "(NADI/MADAR eval pending); foreign loans return "
        "``foreign: true, root: null``; unknowns get ``needs_review``."
    ),
)
def normalize(request: NormalizeRequest) -> NormalizeResponse:
    result = normalize_word(request.word, dialect_hint=request.dialect_hint)
    return NormalizeResponse(**result, beta=True)
