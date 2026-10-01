"""Tajwīd analysis API -- text-based rules engine (Ḥafṣ ʿan ʿĀṣim).

Endpoints:
* ``POST /v1/tajwid/analyze`` -- annotate Arabic text (with tashkīl) with
  tajwīd rules: per-annotation rule id, Arabic/English names, character
  spans, and explanatory detail.
* ``GET /v1/tajwid/rules`` -- the rule catalog with classical sources.

Honest scope notes (also surfaced in responses):
* This is a **text-based** engine over vocalized (tashkīl-bearing) input.
  It does not do audio/ASR: the ``ruh_model/tajwid/scaffold.py`` speech
  interface is a separate, unproven prototype (its Q28 bridge is not
  trained) and is not wired here.
* Rules are implemented for **Ḥafṣ ʿan ʿĀṣim min ṭarīq ash-Shāṭibiyyah**
  only. Other qirāʾāt are flagged in ``qiraat_note`` fields where they
  differ (e.g. Warsh), never computed.
* The engine never guesses vowels: without diacritics only letter-shape
  rules run (muqaṭṭaʿāt, sakt places, hamzat al-waṣl, lām shamsiyyah /
  qamariyyah), reported as ``status: "partial"``.
* Rule details carry topic-level classical sources (al-Jazariyyah,
  Tuḥfat al-Aṭfāl, ash-Shāṭibiyyah); the catalog endpoint lists them.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ._ruh_loader import load_ruh_module

_tajwid_mod = load_ruh_module("ruh_model/tajwid/rules.py", "ruh_api_tajwid_rules")

analyze_text = _tajwid_mod.analyze_text
get_rule_catalog = _tajwid_mod.get_rule_catalog
DEFAULT_QIRAAT = _tajwid_mod.QIRAAT_DEFAULT

router = APIRouter(prefix="/v1/tajwid", tags=["ruh-tajwid"])

SUPPORTED_QIRAAT = ("hafs",)
MAX_TEXT_CHARS = 20000

SCOPE_NOTE = (
    "Text-based tajwīd analysis for Ḥafṣ ʿan ʿĀṣim (ash-Shāṭibiyyah). "
    "Not audio/ASR based; other qirāʾāt are flagged, never computed. "
    "The engine does not guess vowels: full analysis needs tashkīl."
)


class AnalyzeRequest(BaseModel):
    """Analyze ``text`` for tajwīd rules."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_CHARS,
        description="Arabic text, preferably with tashkīl (diacritics)",
    )
    qiraat: str = Field(
        default="hafs",
        description="Qirāʾah. Only 'hafs' is implemented; anything else is rejected.",
    )


class Annotation(BaseModel):
    rule_id: str
    rule_name_ar: str
    rule_name_en: str
    category: str
    span: str
    start: int
    end: int
    detail: str
    qiraat_note: str | None = None


class AnalyzeResponse(BaseModel):
    text: str
    qiraat: str
    status: str = Field(
        ...,
        description="'ok' (full analysis) or 'partial' (no diacritics: letter-shape rules only)",
    )
    diacritic_coverage: float
    annotations: list[Annotation]
    rules_applied: list[str]
    note: str | None = None
    scope: str = SCOPE_NOTE


class RuleInfo(BaseModel):
    rule_id: str
    name_ar: str
    name_en: str
    category: str
    description: str
    default_length: str
    sources: list[str]


class RulesResponse(BaseModel):
    qiraat: str = DEFAULT_QIRAAT
    count: int
    rules: list[RuleInfo]
    scope: str = SCOPE_NOTE


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """Annotate Arabic text with tajwīd rules (Ḥafṣ ʿan ʿĀṣim)."""
    if req.qiraat.lower() != "hafs":
        raise HTTPException(
            status_code=422,
            detail=(
                f"qiraat={req.qiraat!r} is not implemented. "
                f"Supported: {', '.join(SUPPORTED_QIRAAT)}. "
                "Other qirāʾāt are flagged in qiraat_note fields, never computed."
            ),
        )
    result = analyze_text(req.text)
    annotations = [
        Annotation(
            rule_id=a["rule_id"],
            rule_name_ar=a["rule_name_ar"],
            rule_name_en=a["rule_name_en"],
            category=a["category"],
            span=a["span"],
            start=a["start"],
            end=a["end"],
            detail=a["detail"],
            qiraat_note=a.get("qiraat_note"),
        )
        for a in result["annotations"]
    ]
    return AnalyzeResponse(
        text=req.text,
        qiraat="hafs",
        status=result["status"],
        diacritic_coverage=result["diacritic_coverage"],
        annotations=annotations,
        rules_applied=result["rules_applied"],
        note=result.get("note"),
    )


@router.get("/rules", response_model=RulesResponse)
def list_rules() -> RulesResponse:
    """Return the tajwīd rule catalog with classical sources."""
    catalog = get_rule_catalog()
    rules = [
        RuleInfo(
            rule_id=r["rule_id"],
            name_ar=r["name_ar"],
            name_en=r["name_en"],
            category=r["category"],
            description=r["description"],
            default_length=r.get("counts") or "",
            sources=list(r["sources"]),
        )
        for r in catalog
    ]
    return RulesResponse(count=len(rules), rules=rules)
