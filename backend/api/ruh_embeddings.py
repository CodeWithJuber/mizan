"""Root-embeddings API — BETA/unverified.

Study #13 (ruh-usecase-deep-20260929): morphology-aware vectors for Arabic
RAG. **BOLD WARNING: good WSD ≠ good embeddings.** Ruh was trained for
sense disambiguation, not retrieval; embedding quality is completely
unproven and the ArabicMTEB-style eval this offering requires has NOT been
run. Do not present these vectors as production-quality.

Current implementation: a DETERMINISTIC FALLBACK pooled from token hashes —
a stable placeholder so the API shape, dims contract, and downstream
integration can be built and tested while the real ISM-pooled encoder is
pending. It is explicitly NOT a trained embedding:

* same input → same output (deterministic, testable);
* L2-normalized, fixed dims (default 256);
* carries ``source: "deterministic-fallback-v0 (NOT a trained embedding)"``
  on every vector and ``note: "beta/unverified"`` on every response.

Gate (from research): run the ArabicMTEB-style eval BEFORE any launch
claim; Matryoshka truncatable dims are standard practice but unverified
for Ruh.

Mount (without touching ``backend/api/main.py``)::

    from api.ruh_embeddings import router
    app.include_router(router)   # exposes POST /v1/embed
"""

from __future__ import annotations

import hashlib
import math
import re

BETA_NOTE = "beta/unverified"
FALLBACK_SOURCE = "deterministic-fallback-v0 (NOT a trained embedding)"
DEFAULT_DIMS = 256

__all__ = [
    "BETA_NOTE",
    "FALLBACK_SOURCE",
    "DEFAULT_DIMS",
    "embed_texts",
    "router",
]

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _token_vector(token: str, dims: int) -> list[float]:
    """Deterministic pseudo-random unit vector seeded by the token bytes."""
    out: list[float] = []
    counter = 0
    while len(out) < dims:
        digest = hashlib.sha256(f"{token}#{counter}".encode()).digest()
        out.extend(b / 255.0 - 0.5 for b in digest)
        counter += 1
    return out[:dims]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_texts(texts: list[str], dims: int = DEFAULT_DIMS) -> dict:
    """Embed texts with the deterministic fallback (model absent).

    Tokenizes on word characters, mean-pools per-token seeded vectors, and
    L2-normalizes. Deterministic: identical input always yields identical
    output. This is a shape-compatible placeholder — NOT a trained embedding.
    """
    if dims <= 0:
        raise ValueError("dims must be positive")
    vectors = []
    for text in texts:
        tokens = _TOKEN_RE.findall(text or "")
        if not tokens:
            vec = [0.0] * dims
        else:
            acc = [0.0] * dims
            for tok in tokens:
                tv = _token_vector(tok, dims)
                for i, v in enumerate(tv):
                    acc[i] += v
            vec = [v / len(tokens) for v in acc]
        vectors.append(
            {
                "vector": _normalize(vec),
                "dims": dims,
                "source": FALLBACK_SOURCE,
            }
        )
    return {"vectors": vectors, "dims": dims, "note": BETA_NOTE}


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
    router = APIRouter(tags=["ruh-embeddings (BETA/unverified)"])

    @router.post(
        "/v1/embed",
        summary="Embed texts (BETA — deterministic fallback, unverified quality)",
        description=(
            "**BETA/unverified. BOLD: good WSD ≠ good embeddings.** Ruh was "
            "trained for sense disambiguation, not retrieval — embedding quality "
            "is completely unproven and the ArabicMTEB-style eval is still pending. "
            "Current vectors come from a deterministic token-hash fallback "
            "(stable placeholder, NOT a trained embedding) so integrations can "
            "be built against the API shape. Do not use for production retrieval."
        ),
        response_description="Vectors with dims, source labels, and beta note.",
    )
    def embed_endpoint(payload: dict) -> dict:
        """POST /v1/embed — body ``{"texts": [...], "dims": 256}``."""
        texts = payload.get("texts", [])
        dims = int(payload.get("dims", DEFAULT_DIMS))
        return embed_texts([str(t) for t in texts], dims=dims)
