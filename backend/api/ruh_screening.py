"""Bank Sharia-doc screening API — screening/flagging ONLY. PILOT/BETA.

Study #4 (ruh-usecase-deep-20260929): Sharia-compliance text screening for
Islamic banks. This module is the *screening* primitive — it flags
Sharia-salient spans in a document so a human scholar can review them faster.
It is NOT a compliance engine and it is NOT a scholar.

STATUS: **pilot/beta, unverified**. No buyer verified (research 2026-09-29).
Scholar review is REQUIRED for every flagged document before any downstream
use. Flags in v0.1 are lexical (pattern-based), not model judgments.

BINDING RULE (Quran lens: amana — stewardship over religious content):
the model NEVER issues a fatwa/ruling/hukm. This is code-enforced, not a
prompt suggestion:

* ``detect_ruling_intent`` scans the request for ruling/fatwa/hukm requests
  (Arabic + English keyword + pattern list). On a match the request is
  REFUSED with a fixed message — no screening runs, no partial answer.
* ``ruling`` is ALWAYS ``None`` in every response. There is no code path
  that can set it to anything else.
* JEV (jev-1.13.0, 2026-09-29, ``allow`` @ 0.86): compliance-*question*
  phrasing such as "is this clause Sharia-compliant?" is NOT a ruling
  request — it goes through screening (flags + ``ruling: None``) because
  flagging is not ruling and over-refusal would kill the pilot. Explicit
  verdict requests ("is it halal?", "give me a fatwa", "ما حكم ...؟")
  are always refused.

Mount (without touching ``backend/api/main.py``)::

    from api.ruh_screening import router
    app.include_router(router)   # exposes POST /v1/screen
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Fixed strings — never change without scholar + product sign-off
# ---------------------------------------------------------------------------

REFUSAL_MESSAGE = "Rulings require a qualified scholar. This tool only flags text for review."

BETA_NOTE = (
    "beta/unverified — pilot build (ruh-usecase-deep-20260929 study #4), "
    "no buyer verified. Every flagged document requires review by a qualified "
    "Sharia scholar before any downstream use. Flags are lexical, not model "
    "judgments; confidence values are provisional."
)

SCREENING_VERSION = "screen-lexicon-v0.1-beta"

__all__ = [
    "REFUSAL_MESSAGE",
    "BETA_NOTE",
    "SCREENING_VERSION",
    "detect_ruling_intent",
    "screen_document",
    "router",
]

# ---------------------------------------------------------------------------
# Intent guard — ruling/fatwa/hukm request detection (Arabic + English)
# ---------------------------------------------------------------------------


def _normalize_arabic(text: str) -> str:
    """Strip tashkeel and normalize alef/hamza variants for pattern matching."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = text.replace("ى", "ي")
    return text


# Arabic: verb-of-asking + fatwa/hukm constructions. Checked against the
# *normalized* text (tashkeel stripped, alef variants folded).
_RULING_PATTERNS_AR = [
    r"افت\w*(وني|ني|نا)\b",  # أفتني / أفتونا / أفتوني — "give me/us a fatwa"
    r"\bما\s+حكم\b",  # ما حكم — "what is the ruling"
    r"\bهل\s+يجوز\b",  # هل يجوز — "is it permissible"
    r"\bهل\s+يحل\b",
    r"\bهل\s+يحرم\b",  # هل يحرم — "is it forbidden"
    r"(اعطني|اريد|نريد|نحتاج)\s+\S{0,10}\s*فتو[يى]",  # أعطني/أريد فتوى
    r"\bطلب\s+فتو[يى]",  # طلب فتوى — "fatwa request"
    r"\bافتنا\s+في\b",  # افتنا في — "give us a fatwa about"
    r"\bما\s+قولكم\s+في\b",  # "what do you say about"
    r"\bالحكم\s+الشرعي\b",  # الحكم الشرعي — "the Sharia ruling"
    r"حلال\s+ام\s+حرام",  # حلال أم حرام — "halal or haram"
    r"فتو[يى]\s*[؟?]",  # bare "فتوى؟" — asking for one
]

# English: explicit verdict requests. Deliberately narrow — compliance
# *questions* ("is this Sharia-compliant?", "does this contain riba?") are
# screening inputs, not ruling requests (JEV allow @ 0.86).
_RULING_PATTERNS_EN = [
    r"\b(is|are)\b[^.?]{0,40}\bhalal\b",
    r"\b(is|are)\b[^.?]{0,40}\bharam\b",
    r"\bhalal\s+or\s+haram\b",
    r"\bwhat\s+is\s+the\s+(sharia|shariah|islamic)\s+ruling\b",
    r"\b(sharia|shariah|islamic)\s+ruling\s+on\b",
    r"\b(give|issue|provide)\b.{0,40}\bruling\b",
    r"\b(need|want|give me|request|issue|provide|looking for|seeking)\b"
    r".{0,30}\bfatw[ae]s?\b",
    r"\bfatw[ae]s?\b.{0,30}\b(please|on this|about this|for this)\b",
    r"\bwhat\s+is\s+the\s+hukm\b",
    r"\bgive\b.{0,20}\bhukm\b",
    r"\bis\s+it\s+permissible\s+in\s+islam\b",
]

_COMPILED_AR = [re.compile(p) for p in _RULING_PATTERNS_AR]
_COMPILED_EN = [re.compile(p, re.IGNORECASE) for p in _RULING_PATTERNS_EN]


def detect_ruling_intent(text: str) -> bool:
    """Return True if the request asks for a ruling/fatwa/hukm.

    Scans the request *text* (not ``doc_type`` — a doc_type like
    "fatwa-compliance checklist" is a legitimate screening input, per
    track-04 research). Fail-closed: ambiguous verdict requests refuse.
    """
    if not text or not text.strip():
        return False
    ar = _normalize_arabic(text)
    if any(p.search(ar) for p in _COMPILED_AR):
        return True
    return any(p.search(text) for p in _COMPILED_EN)


# ---------------------------------------------------------------------------
# Screening engine — flagging only (lexical v0.1, beta)
# ---------------------------------------------------------------------------

# (surface pattern, is_regex, reason, sense_receipt, confidence)
# Receipts follow the "verified sense with receipts" product shape from the
# research: which signal supports this flag. In v0.1 the signal is the
# lexicon itself — honestly labeled, low confidence.
_LEXICON: list[tuple[str, bool, str, str, float]] = [
    (
        "ربو",
        False,
        "Possible riba (usury/interest) language",
        f"root:ر-ب-و|src:{SCREENING_VERSION}",
        0.35,
    ),
    (
        "غرر",
        False,
        "Possible gharar (excessive uncertainty) language",
        f"root:غ-ر-ر|src:{SCREENING_VERSION}",
        0.35,
    ),
    (
        "ميسر",
        False,
        "Possible maysir (gambling) language",
        f"root:م-ي-س|src:{SCREENING_VERSION}",
        0.35,
    ),
    ("قمار", False, "Gambling language", f"root:ق-م-ر|src:{SCREENING_VERSION}", 0.40),
    ("رشو", False, "Possible bribery language", f"root:ر-ش-و|src:{SCREENING_VERSION}", 0.35),
    (
        r"\busury\b",
        True,
        "English 'usury' — screen for riba-adjacent meaning",
        f"root:ر-ب-و|src:{SCREENING_VERSION}",
        0.35,
    ),
    (
        r"\briba\b",
        True,
        "English 'riba' — screen for riba-adjacent meaning",
        f"root:ر-ب-و|src:{SCREENING_VERSION}",
        0.40,
    ),
    (
        r"\binterests?\b",
        True,
        "English 'interest' — screen for riba-adjacent meaning",
        f"root:ر-ب-و|src:{SCREENING_VERSION}",
        0.30,
    ),
    (
        r"\bgambling\b",
        True,
        "English 'gambling' — screen for maysir-adjacent meaning",
        f"root:م-ي-س|src:{SCREENING_VERSION}",
        0.40,
    ),
    (
        r"\bbribe\w*\b",
        True,
        "English 'bribe*' — screen for bribery-adjacent meaning",
        f"root:ر-ش-و|src:{SCREENING_VERSION}",
        0.35,
    ),
]


def _find_flags(text: str) -> list[dict]:
    """Lexical flag scan. Returns flags sorted by span start, no overlaps."""
    hits: list[tuple[int, int, str, str, str, float]] = []
    for surface, is_regex, reason, receipt, confidence in _LEXICON:
        if is_regex:
            for m in re.finditer(surface, text, re.IGNORECASE):
                hits.append((m.start(), m.end(), m.group(0), reason, receipt, confidence))
        else:
            start = 0
            while True:
                idx = text.find(surface, start)
                if idx < 0:
                    break
                hits.append((idx, idx + len(surface), surface, reason, receipt, confidence))
                start = idx + 1
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    flags: list[dict] = []
    occupied: list[tuple[int, int]] = []
    for s, e, surf, reason, receipt, confidence in hits:
        if any(s < oe and e > os for os, oe in occupied):
            continue
        occupied.append((s, e))
        flags.append(
            {
                "span": [s, e],
                "surface": surf,
                "reason": reason,
                "sense_receipt": receipt,
                "confidence": confidence,
            }
        )
    return flags


def screen_document(text: str, doc_type: str | None = None) -> dict:
    """Screen a document: refuse ruling requests, otherwise flag spans.

    Returns either ``{"refused": True, "reason": ...}`` or
    ``{"refused": False, "flags": [...], "ruling": None, "note": ...,
    "doc_type": ...}``. ``ruling`` is ALWAYS None — no code path changes it.
    """
    text = text or ""
    if detect_ruling_intent(text):
        return {"refused": True, "reason": REFUSAL_MESSAGE}
    return {
        "refused": False,
        "flags": _find_flags(text),
        "ruling": None,
        "doc_type": doc_type,
        "note": BETA_NOTE,
    }


# ---------------------------------------------------------------------------
# FastAPI router (optional dependency — module stays importable without it)
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter

    _FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - CI installs fastapi via main deps
    APIRouter = None  # type: ignore[assignment,misc]
    _FASTAPI_AVAILABLE = False

router = None
if _FASTAPI_AVAILABLE:
    router = APIRouter(tags=["ruh-screening (PILOT/BETA)"])

    @router.post(
        "/v1/screen",
        summary="Screen a document for Sharia-salient spans (flagging only)",
        description=(
            "**PILOT/BETA — unverified.** No buyer verified (research 2026-09-29). "
            "Flags Sharia-salient spans (e.g. riba/gharar/maysir-adjacent language) "
            "for scholar review. **The model never issues rulings**: requests asking "
            "for a fatwa/ruling/hukm are refused, and `ruling` is always null. "
            "**Scholar review required** for every flagged document before any "
            "downstream use. Flags in v0.1 are lexical, not model judgments."
        ),
        response_description="Refusal object or flag list with ruling=null.",
    )
    def screen_endpoint(payload: dict) -> dict:
        """POST /v1/screen — body ``{"text": ..., "doc_type": ...}``."""
        text = payload.get("text", "")
        return screen_document(str(text), payload.get("doc_type"))
