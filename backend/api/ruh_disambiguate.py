"""Ruh sense-disambiguation API router: ``POST /v1/disambiguate``.

Standalone router (the coordinator wires it into ``backend/api/main.py``).
Torch-free: the sense modules are loaded by file path so this router works
in minimal ``[dev, nlp]`` installs where ``ruh_model/__init__.py``'s torch
import would fail.

Response shape::

    POST /v1/disambiguate  {"word": "عين", "context": "...", "top_k": 3}
    ->
    {
      "word": "عين", "lemma": "عين", "status": "ok",
      "sense_id": "qcsmp2:آيَة:verse", "confidence": 0.83,
      "gloss_ar": null, "gloss_en": "verse",
      "alternatives": [{"sense_id": ..., "gloss_ar": ..., "gloss_en": ..., "confidence": ...}],
      "provenance": [{"signal": "inventory", "source": "sense-inventory/v1.0.0", "weight": 1.0}, ...],
      "inventory_version": "1.0.0",
      "threshold_used": 0.8,
      "abstained": false
    }

``status`` is ``"ok"`` | ``"uncertain"`` | ``"unknown_lemma"``. On
``"uncertain"``/``"unknown_lemma"`` the API abstains (``sense_id`` null)
instead of guessing — a wrong sense stated as fact is worse than "I don't
know" (amāna).
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("mizan.api.ruh_disambiguate")

REPO_ROOT = Path(__file__).resolve().parents[2]
SENSE_DIR = REPO_ROOT / "ruh_model" / "sense"

HONEST_NOTE = (
    "Word-in-context → verified sense, with a provenance receipt naming the "
    "computed signals behind the decision.\n\n"
    "PROVISIONAL — read before relying on this endpoint:\n"
    "• Scoring is deterministic context-overlap over the versioned sense "
    "inventory (Q-CSMP v2, 96 senses, 48 lemmas). The trained-model signal "
    "is NOT wired yet (see the `model` provenance signal: it only appears "
    "when a classifier posterior was actually mixed in).\n"
    "• The Q-CSMP pilot reported accuracy 0.7592 (95% CI 0.7241–0.7927) on "
    "minimal-pair data with keyword-rule labels. Real prose is harder; "
    "12/88 rare senses had 0 recall; no external benchmark exists. "
    "Independent eval is pending — treat every confidence as provisional.\n"
    "• Arabic glosses (`gloss_ar`) are null until scholar-reviewed. The "
    "inventory never invents them.\n"
    "• Conservative abstention: confidence below threshold → "
    "`status: 'uncertain'`, `sense_id: null`, with alternatives. "
    "Thresholds are tiered — 0.6 general, 0.8 religious/Quranic-flagged."
)

router = APIRouter(prefix="/v1", tags=["ruh"])


class DisambiguateRequest(BaseModel):
    word: str = Field(..., min_length=1, description="Word/lemma to disambiguate (Arabic).")
    context: str = Field(
        ..., min_length=1, description="Surrounding text (verse, sentence, passage)."
    )
    top_k: int = Field(default=3, ge=1, le=10, description="How many alternatives to return.")
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Override the tiered abstention bar (0.6 general / 0.8 religious).",
    )


class SenseAlternativeOut(BaseModel):
    sense_id: str
    gloss_ar: str | None
    gloss_en: str
    confidence: float


class ProvenanceOut(BaseModel):
    signal: str
    source: str
    weight: float


class DisambiguateResponse(BaseModel):
    word: str
    lemma: str
    status: str
    sense_id: str | None
    confidence: float | None
    gloss_ar: str | None
    gloss_en: str | None
    alternatives: list[SenseAlternativeOut]
    provenance: list[ProvenanceOut]
    inventory_version: str
    threshold_used: float | None
    abstained: bool


def _load_sense_module(name: str):
    """Load a ruh_model/sense module by file path (torch-free)."""
    key = f"ruh_api_sense_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = SENSE_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sense module {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_lock = threading.Lock()
_INVENTORY = None
_INVENTORY_ERROR: str | None = None


def _inventory_path() -> Path | None:
    """Newest built ``sense_inventory.v*.jsonl`` under ruh_model/sense/data."""
    data_dir = SENSE_DIR / "data"
    candidates = sorted(data_dir.glob("sense_inventory.v*.jsonl"))
    return candidates[-1] if candidates else None


def get_inventory():
    """Lazy singleton: the versioned sense inventory (503 when not built)."""
    global _INVENTORY, _INVENTORY_ERROR
    if _INVENTORY is not None or _INVENTORY_ERROR is not None:
        if _INVENTORY is None:
            raise HTTPException(status_code=503, detail=_INVENTORY_ERROR)
        return _INVENTORY
    with _lock:
        if _INVENTORY is not None or _INVENTORY_ERROR is not None:
            if _INVENTORY is None:
                raise HTTPException(status_code=503, detail=_INVENTORY_ERROR)
            return _INVENTORY
        path = _inventory_path()
        if path is None:
            _INVENTORY_ERROR = "sense inventory not built — run scripts/build_sense_inventory.py"
            logger.error(_INVENTORY_ERROR)
            raise HTTPException(status_code=503, detail=_INVENTORY_ERROR)
        try:
            inv_mod = _load_sense_module("inventory")
            _INVENTORY = inv_mod.load_inventory_jsonl(path)
            logger.info(
                "ruh sense inventory loaded: v%s (%d senses, %d lemmas) from %s",
                _INVENTORY.version,
                len(_INVENTORY),
                len(_INVENTORY.lemmas()),
                path,
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — fail closed with a clear 503
            _INVENTORY_ERROR = f"sense inventory failed to load: {exc}"
            logger.error(_INVENTORY_ERROR)
            raise HTTPException(status_code=503, detail=_INVENTORY_ERROR) from exc
        return _INVENTORY


@router.post(
    "/disambiguate",
    response_model=DisambiguateResponse,
    summary="Disambiguate a word's sense in context (with provenance)",
    description=HONEST_NOTE,
)
def disambiguate_word(req: DisambiguateRequest) -> DisambiguateResponse:
    inventory = get_inventory()
    dis_mod = _load_sense_module("disambiguate")
    result = dis_mod.disambiguate(
        req.word,
        req.context,
        inventory,
        top_k=req.top_k,
        threshold=req.threshold,
    )
    d = result.to_dict()
    return DisambiguateResponse(
        word=d["word"],
        lemma=d["lemma"],
        status=d["status"],
        sense_id=d["sense_id"],
        confidence=d["confidence"],
        gloss_ar=d["gloss_ar"],
        gloss_en=d["gloss_en"],
        alternatives=[SenseAlternativeOut(**a) for a in d["alternatives"]],
        provenance=[ProvenanceOut(**p) for p in d["provenance"]],
        inventory_version=d["inventory_version"],
        threshold_used=d["threshold_used"],
        abstained=d["abstained"],
    )
