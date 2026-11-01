"""RootSpace Reader API (use case #5, Build 4) -- BETA.

Endpoints:
* ``GET /v1/reader/lookup?ref=...&word=...`` -- fetch the precomputed
  annotation for one word occurrence from the offline annotation DB.
* ``POST /v1/reader/build`` -- annotate a small text and store it
  (synchronous; for corpus-scale builds use
  ``scripts/build_annotations.py`` instead).

BETA / UNVERIFIED -- honest OpenAPI notes:
* root/pattern come from the rule-based ``ArabicMorphAnalyzer``; never
  measured against a gold standard. Confidence values are deterministic
  heuristics, not measured accuracy.
* Per-occurrence ``sense_id`` is scholar-eval pending: without a
  scholar-evaluated sense inventory the API returns ``sense_id: null``
  with ``sense_pending: true`` rather than guessing. Do NOT present
  annotations as verified tafsir.

The annotation DB path is ``data/ruh_reader.sqlite`` under the repo
root by default, overridable with the ``RUH_READER_DB`` env var
(tests use a tmp path). This router is standalone; wire it into the
main FastAPI app with ``app.include_router(router)`` when ready.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ._ruh_loader import load_ruh_module, repo_root

_store_mod = load_ruh_module("ruh_model/reader/store.py", "ruh_api_reader_store")
_annotator_mod = load_ruh_module("ruh_model/reader/annotator.py", "ruh_api_reader_annotator")

AnnotationStore = _store_mod.AnnotationStore
annotate_text = _annotator_mod.annotate_text
BETA_NOTE = _store_mod.BETA_NOTE

router = APIRouter(prefix="/v1/reader", tags=["ruh-reader (beta)"])

# Synchronous builds are for small inputs only; corpus-scale annotation
# belongs in scripts/build_annotations.py.
MAX_BUILD_WORDS = 5000


class BuildRequest(BaseModel):
    """Annotate ``text`` and store it under ``ref_id``."""

    ref_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Document key, e.g. '1:1' for surah:ayah or any corpus id",
    )
    text: str = Field(
        ...,
        min_length=1,
        max_length=60000,
        description="Text to annotate (small inputs only; see MAX_BUILD_WORDS)",
    )


class BuildResponse(BaseModel):
    ref_id: str
    words: int
    db_path: str
    db_bytes: int | None
    beta: bool = True
    note: str = BETA_NOTE


class LookupResponse(BaseModel):
    ref: str
    word_index: int
    annotation: dict | None
    beta: bool = True
    note: str = BETA_NOTE


def _db_path() -> Path:
    """Resolve the annotation DB path (env override wins; read per call).

    The DB is runtime data: in the container it lives on the ``mizan-data``
    volume (``/data``, see docker-compose.prod.yml). An existing volume DB
    wins over the repo-relative default so a ``repo_root()`` layout change
    can never silently orphan it.
    """
    override = os.environ.get("RUH_READER_DB")
    if override:
        return Path(override)
    volume_db = Path("/data/ruh_reader.sqlite")
    if volume_db.exists():
        return volume_db
    return repo_root() / "data" / "ruh_reader.sqlite"


@router.get(
    "/lookup",
    response_model=LookupResponse,
    summary="Look up one precomputed word annotation (beta)",
    description=(
        "Returns the stored annotation for ``(ref, word)`` or "
        "``annotation: null`` when absent. BETA: root/pattern are "
        "rule-based heuristics; per-occurrence sense is scholar-eval "
        "pending and returned as null until a verified inventory exists."
    ),
)
def lookup(
    ref: str = Query(..., min_length=1, max_length=200, description="Document key"),
    word: int = Query(..., ge=0, description="0-based word index"),
) -> LookupResponse:
    with AnnotationStore(_db_path()) as store:
        annotation = store.get(ref, word)
    return LookupResponse(ref=ref, word_index=word, annotation=annotation)


@router.post(
    "/build",
    response_model=BuildResponse,
    summary="Annotate a small text into the annotation DB (beta)",
    description=(
        "Synchronous build for small inputs only (<= 5000 words; larger "
        "inputs get HTTP 413 -- use scripts/build_annotations.py). BETA: "
        "annotations are rule-based and unverified; senses stay pending "
        "without a scholar-evaluated inventory."
    ),
)
def build(request: BuildRequest) -> BuildResponse:
    annotations = annotate_text(request.text, ref_id=request.ref_id)
    if len(annotations) > MAX_BUILD_WORDS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{len(annotations)} words exceeds the synchronous build "
                f"limit of {MAX_BUILD_WORDS}; use "
                "scripts/build_annotations.py for corpus-scale builds."
            ),
        )
    path = _db_path()
    with AnnotationStore(path) as store:
        store.put_many(request.ref_id, annotations)
        stats = store.stats()
    return BuildResponse(
        ref_id=request.ref_id,
        words=len(annotations),
        db_path=str(path),
        db_bytes=stats["db_bytes"],
    )
