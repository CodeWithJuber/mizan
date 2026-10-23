"""QG understanding layer adapter for Qwen3 responses.

Attaches root/pattern/role analysis to every Qwen3-generated response. This
module contains NO new analysis logic — it only adapts the repo's existing
deterministic layers into one uniform schema:

- root + pattern + wazn : ``qca.morphology_api.analyze_word`` (per-token
  verified/heuristic provenance against the root database)
- role                 : coarse POS from the existing morphology service
  (``ruh_model/service/analyze.py`` via ``api.ruh_morphology``) — a
  heuristic syntactic-role approximation, labeled as such. The QG
  prototype's trained i'rab-role tagger is not vendored in this repo;
  when it lands, it slots in behind ``role`` without schema change.

If either layer is unavailable the entry degrades gracefully (nulls +
``"unavailable"`` provenance) instead of inventing analysis.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mizan.api.qwen3_understanding")

MAX_UNDERSTANDING_TOKENS = 48
MAX_UNDERSTANDING_CHARS = 4000

SOURCE = "qca.morphology_api + ruh_model/service/analyze.py (existing, deterministic)"


def _service_tokens(text: str) -> list[dict[str, Any]] | None:
    """Per-token morphology from the existing service (torch-free)."""
    try:
        from api.ruh_morphology import _service_analyze  # noqa: SLF001
    except Exception as exc:
        logger.warning("qwen3 understanding: morphology service unavailable: %s", exc)
        return None
    try:
        result = _service_analyze(text, mode="deterministic", domain="general")
    except Exception as exc:
        logger.warning("qwen3 understanding: morphology service failed: %s", exc)
        return None
    tokens = result.get("tokens")
    return list(tokens) if isinstance(tokens, list) else None


def _provenance_for(surface: str) -> dict[str, Any]:
    """Root/pattern provenance from the existing QCA layer."""
    try:
        from qca.morphology_api import analyze_word
    except Exception as exc:
        logger.warning("qwen3 understanding: qca.morphology_api unavailable: %s", exc)
        return {
            "root": None,
            "root_provenance": "unavailable",
            "pattern": None,
            "pattern_provenance": "unavailable",
            "wazn": None,
        }
    try:
        analysis = analyze_word(surface)
    except Exception as exc:  # noqa: BLE001 — degrade, never invent
        logger.warning("qwen3 understanding: analyze_word failed for %r: %s", surface, exc)
        return {
            "root": None,
            "root_provenance": "unavailable",
            "pattern": None,
            "pattern_provenance": "unavailable",
            "wazn": None,
        }
    return {
        "root": analysis.get("root") or None,
        "root_provenance": analysis.get("root_provenance", "heuristic"),
        "pattern": analysis.get("pattern"),
        "pattern_provenance": analysis.get("pattern_provenance", "heuristic"),
        "wazn": analysis.get("wazn"),
    }


def analyze_understanding(
    text: str, *, max_tokens: int = MAX_UNDERSTANDING_TOKENS
) -> dict[str, Any]:
    """Root/pattern/role analysis for ``text`` using existing repo layers.

    Returns ``{"tokens": [...], "source": ..., "status": "ok" | "degraded"}``.
    ``role`` is the service's coarse POS (heuristic); ``role_provenance`` is
    ``"unavailable"`` when the service cannot provide it.
    """
    if not text or not text.strip():
        return {"tokens": [], "source": SOURCE, "status": "ok", "note": "empty input"}

    clipped = text[:MAX_UNDERSTANDING_CHARS]
    service_tokens = _service_tokens(clipped)
    degraded = service_tokens is None
    if service_tokens is None:
        # Last resort: whitespace tokens with provenance-only enrichment.
        service_tokens = [{"surface": t} for t in clipped.split()]
    total_tokens = len(service_tokens)
    service_tokens = service_tokens[:max_tokens]

    entries: list[dict[str, Any]] = []
    for tok in service_tokens:
        surface = str(tok.get("surface", ""))
        if not surface:
            continue
        prov = _provenance_for(surface)
        entries.append(
            {
                "surface": surface,
                "root": prov["root"],
                "root_provenance": prov["root_provenance"],
                "pattern": prov["pattern"] or tok.get("pattern"),
                "pattern_provenance": prov["pattern_provenance"],
                "wazn": prov["wazn"],
                "role": tok.get("pos"),
                "role_provenance": "heuristic" if tok.get("pos") else "unavailable",
                "lemma": tok.get("lemma"),
            }
        )

    return {
        "tokens": entries,
        "source": SOURCE,
        "status": "degraded" if degraded else "ok",
        "truncated": len(clipped) < len(text) or total_tokens > max_tokens,
    }
