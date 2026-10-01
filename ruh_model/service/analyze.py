"""Deterministic morphology analysis service (torch-free).

Study use-case #2 — Morphology Analysis API ("the wedge").

Pipeline: text -> Bayan-style word split -> ``ArabicMorphAnalyzer``
(root/pattern candidates from the affix tables in
``ruh_model/tokenizer/morphology.py``) -> candidate scoring against the
``ARABIC_ROOTS`` table (``backend/qca/roots.py``) -> per-token
``{surface, root, pattern, lemma, pos, diac, confidence}``.

Honesty contract (Quran lens: la taqfu — no claim without knowledge):
- Confidence is a RULE-BASED heuristic. It is NOT calibrated by the Mizan
  calibration loss (that needs trained weights + an eval set). Every token
  carries ``confidence_source: "heuristic/unverified"`` — the string
  "calibrated" never appears for these scores.
- Accuracy vs CAMeL Tools is UNVERIFIED. The eval harness
  (``ruh_model/eval/morphology_eval.py``, separate track) is pending.
- ``diac`` only echoes diacritics present in the input. The service never
  invents diacritization (diacritization is every toolkit's weak spot).
- Quranic-domain requests get conservative confidence (capped) plus
  low-confidence flags — a wrong Quranic analysis is not a normal bug.

Model path: ``analyze_with_model`` is the hook for future trained-weight
inference. With no weights configured it raises a clear error.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Version / constants
# ---------------------------------------------------------------------------

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parents[1]


def _read_backend_version() -> str:
    try:
        return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.1.0"


BACKEND_VERSION = _read_backend_version()

#: The only confidence source this module ever reports.
CONFIDENCE_SOURCE_HEURISTIC = "heuristic/unverified"

EVAL_NOTE = (
    "Accuracy vs CAMeL Tools unverified — eval harness "
    "ruh_model/eval/morphology_eval.py (separate track) pending."
)

#: Env var pointing at future Ruh morphology weights.
MODEL_PATH_ENV = "RUHM_MODEL_PATH"

#: Quranic-domain confidence cap (conservative by amana).
QURANIC_CONFIDENCE_CAP = 0.75

#: Below this, a token is flagged low-confidence.
LOW_CONFIDENCE_THRESHOLD = 0.5


class MorphologyModelUnavailable(Exception):
    """Raised when model-mode analysis is requested without weights."""


# ---------------------------------------------------------------------------
# Torch-free bootstrap: load tokenizer modules without executing the real
# ruh_model/__init__.py (which imports torch via ruh_model.model).
# ---------------------------------------------------------------------------

_TOKENIZER: dict[str, Any] = {}


def _bootstrap_torch_free() -> None:
    """Register stub ``ruh_model`` / ``ruh_model.tokenizer`` packages.

    With the stubs in ``sys.modules``, statements like
    ``from ruh_model.tokenizer.morphology import ArabicMorphAnalyzer``
    resolve through the stubs' ``__path__`` and execute ONLY the target
    module file — the real ``__init__`` files (torch import) never run.
    No-op when the real packages are already imported.
    """
    if "ruh_model" in sys.modules or "ruh_model.tokenizer" in sys.modules:
        return
    import types

    ruh_pkg = types.ModuleType("ruh_model")
    ruh_pkg.__path__ = [str(REPO_ROOT / "ruh_model")]
    sys.modules["ruh_model"] = ruh_pkg
    tok_pkg = types.ModuleType("ruh_model.tokenizer")
    tok_pkg.__path__ = [str(REPO_ROOT / "ruh_model" / "tokenizer")]
    sys.modules["ruh_model.tokenizer"] = tok_pkg


def _load_tokenizer_modules() -> dict[str, Any]:
    """Load ArabicMorphAnalyzer + affix tables + ARABIC_ROOTS (cached)."""
    if _TOKENIZER:
        return _TOKENIZER
    _bootstrap_torch_free()
    from ruh_model.tokenizer import morphology as morph_mod
    from ruh_model.tokenizer.root_vocab import _load_roots_module

    roots_mod = _load_roots_module()
    _TOKENIZER.update(
        analyzer_cls=morph_mod.ArabicMorphAnalyzer,
        morph_mod=morph_mod,
        roots=dict(getattr(roots_mod, "ARABIC_ROOTS", {})),
    )
    return _TOKENIZER


def _modules() -> dict[str, Any]:
    return _load_tokenizer_modules()


# ---------------------------------------------------------------------------
# Word splitting (mirrors Bayan's splitter; kept local to stay numpy-free)
# ---------------------------------------------------------------------------

_ARABIC_RE = re.compile("[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
_WORD_SPLIT_RE = re.compile(
    r"[^\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
)
_TASHKEEL_RE = re.compile(
    "[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed]"
)

# Arabic stopwords (mirrors Bayan's set — particles with no trilateral root)
_ARABIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "في",
        "من",
        "إلى",
        "على",
        "عن",
        "مع",
        "هو",
        "هي",
        "هم",
        "هن",
        "أنا",
        "نحن",
        "أنت",
        "أنتم",
        "هذا",
        "هذه",
        "ذلك",
        "تلك",
        "هؤلاء",
        "أولئك",
        "لا",
        "لم",
        "لن",
        "ما",
        "إن",
        "أن",
        "كان",
        "ليس",
        "قد",
        "ثم",
        "أو",
        "بل",
        "لكن",
        "حتى",
    }
)

# Pattern -> derivative-gloss hint (for lemma lookup in ARABIC_ROOTS)
_PATTERN_HINTS: dict[str, str] = {
    "VERB_PAST": "he ",
    "VERB_PRESENT": "he ",
    "ACTIVE_PARTICIPLE": "one who",
    "PASSIVE_PARTICIPLE": "that which",
    "VERBAL_NOUN": "act of",
    "AGENT": "one who",
    "PATIENT": "that which",
    "PLACE_NOUN": "place",
    "INSTRUMENT_NOUN": "tool",
}

# Coarse POS derived from the analyzer's pattern names
_POS_MAP: dict[str, str | None] = {
    "VERB_PAST": "verb",
    "VERB_PRESENT": "verb",
    "VERB_COMMAND": "verb",
    "ACTIVE_PARTICIPLE": "noun",
    "PASSIVE_PARTICIPLE": "noun",
    "VERBAL_NOUN": "noun",
    "NOUN": "noun",
    "ADJECTIVE": "adj",
    "PLACE_NOUN": "noun",
    "INSTRUMENT_NOUN": "noun",
    "DIMINUTIVE": "noun",
    "ABSTRACT_NOUN": "noun",
    "AGENT": "noun",
    "PATIENT": "noun",
    "STOPWORD": None,
    "NON_ARABIC": None,
    "UNKNOWN": None,
}


def _split_words(text: str) -> list[str]:
    """Split text into word tokens (Bayan-style: whitespace/punctuation)."""
    return [w for w in _WORD_SPLIT_RE.split(text) if w]


def _strip_tashkeel_local(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


# ---------------------------------------------------------------------------
# Candidate generation: affix-strip lattice x table validation
# ---------------------------------------------------------------------------


def _prefix_options(word: str, prefixes: list[tuple[str, str]]) -> list[str]:
    """All applicable prefix-strip choices (longest-first), plus no-strip."""
    opts = [""] + [pre for pre, _ in prefixes if word.startswith(pre) and len(word) - len(pre) >= 2]
    seen: list[str] = []
    for opt in opts:
        if opt not in seen:
            seen.append(opt)
    return seen


def _suffix_options(word: str, suffixes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """All applicable suffix-strip choices, plus no-strip."""
    opts: list[tuple[str, str]] = [("", "none")] + [
        (suf, stype) for suf, stype in suffixes if word.endswith(suf) and len(word) - len(suf) >= 2
    ]
    seen: list[tuple[str, str]] = []
    for opt in opts:
        if opt not in seen:
            seen.append(opt)
    return seen


def _candidate_analyses(word: str) -> list[dict[str, Any]]:
    """Generate scored (root, pattern) candidates for one Arabic word.

    For every plausible prefix/suffix strip combination the trilateral root
    is extracted and the pattern classified with the morphology module's own
    tables. A bonus candidate elides a leading ma- (place/instrument nouns
    like مكتبة) when it yields a table-listed root. Candidates whose root is
    listed in ARABIC_ROOTS outrank hallucinated consonant triples — the
    table is the tabayyun (verification) step.
    """
    mods = _modules()
    analyzer = mods["analyzer_cls"]()
    morph_mod = mods["morph_mod"]
    roots: dict[str, Any] = mods["roots"]
    prefixes: list[tuple[str, str]] = morph_mod._PREFIXES
    suffixes: list[tuple[str, str]] = morph_mod._SUFFIXES

    cleaned = morph_mod._normalize_hamza(morph_mod._strip_tashkeel(word))
    candidates: list[dict[str, Any]] = []

    for pre in _prefix_options(cleaned, prefixes):
        after_pre = cleaned[len(pre) :] if pre else cleaned
        for suf, stype in _suffix_options(after_pre, suffixes):
            stem = after_pre[: -len(suf)] if suf else after_pre
            if len(stem) < 2:
                continue
            n_strips = (1 if pre else 0) + (1 if suf else 0)
            root = analyzer._extract_trilateral(stem)
            pattern = analyzer._classify_pattern(cleaned, stem, stype)
            candidates.append(
                {
                    "root": root,
                    "pattern": pattern,
                    "stem": stem,
                    "n_strips": n_strips,
                    "ma_elided": False,
                }
            )
            # ma- elision: مكتب -> كتب for place/instrument nouns
            if stem.startswith("م") and len(stem) >= 4:
                root2 = analyzer._extract_trilateral(stem[1:])
                if root2 in roots and root2 != root:
                    candidates.append(
                        {
                            "root": root2,
                            "pattern": pattern,
                            "stem": stem[1:],
                            "n_strips": n_strips,
                            "ma_elided": True,
                        }
                    )

    for cand in candidates:
        cand["score"] = _score_candidate(cand, roots)

    # Deterministic order: score desc, fewer strips, table-listed root, first seen
    candidates.sort(
        key=lambda c: (
            -c["score"],
            c["n_strips"],
            0 if c["root"] in roots else 1,
        )
    )
    return candidates


def _score_candidate(cand: dict[str, Any], roots: dict[str, Any]) -> float:
    """Heuristic score — NOT a calibrated probability (see module docstring)."""
    score = 0.30
    if cand["root"] in roots:
        score += 0.35
    if len(cand["root"]) == 3:
        score += 0.10
    if cand["pattern"] != "UNKNOWN":
        score += 0.10
    score += 0.05 * (2 - cand["n_strips"])  # prefer fewer affix strips
    return min(score, 0.95)


# ---------------------------------------------------------------------------
# Lemma / POS / diacritics
# ---------------------------------------------------------------------------


def _lemma_for(root: str, pattern: str, stem: str) -> tuple[str | None, str]:
    """Pick a citation-form lemma from ARABIC_ROOTS derivatives.

    Returns (lemma, lemma_source). Sources: "table-gloss" (pattern hint
    matched the derivative gloss), "table-stem" (derivative equals the
    stripped stem), "table-first" (fallback), "none" (root not in table).
    Lemma is returned without diacritics.
    """
    roots: dict[str, Any] = _modules()["roots"]
    entry = roots.get(root)
    if not entry:
        return None, "none"
    derivatives: dict[str, str] = entry.get("derivatives", {}) or {}
    if not derivatives:
        return None, "none"

    hint = _PATTERN_HINTS.get(pattern)
    if hint:
        for form, gloss in derivatives.items():
            if hint in gloss.lower():
                return _strip_tashkeel_local(form), "table-gloss"

    for form in derivatives:
        if _strip_tashkeel_local(form) == stem:
            return _strip_tashkeel_local(form), "table-stem"

    first = next(iter(derivatives))
    return _strip_tashkeel_local(first), "table-first"


# ---------------------------------------------------------------------------
# Per-token analysis
# ---------------------------------------------------------------------------


def _analyze_token(word: str, domain: str) -> dict[str, Any]:
    """Analyze one word into the API token shape (deterministic)."""
    flags: list[str] = []

    if word in _ARABIC_STOPWORDS:
        return {
            "surface": word,
            "root": None,
            "pattern": "STOPWORD",
            "lemma": None,
            "pos": None,
            "diac": None,
            "confidence": 0.95,
            "confidence_source": CONFIDENCE_SOURCE_HEURISTIC,
            "flags": ["stopword"],
        }

    if not _ARABIC_RE.search(word):
        return {
            "surface": word,
            "root": None,
            "pattern": "NON_ARABIC",
            "lemma": None,
            "pos": None,
            "diac": None,
            "confidence": 0.0,
            "confidence_source": CONFIDENCE_SOURCE_HEURISTIC,
            "flags": ["non-arabic"],
        }

    candidates = _candidate_analyses(word)
    best = candidates[0]
    root: str = best["root"]
    pattern: str = best["pattern"]
    lemma, lemma_source = _lemma_for(root, pattern, best["stem"])
    flags.append(f"lemma:{lemma_source}")
    if best["ma_elided"]:
        flags.append("ma-elision")

    confidence = best["score"]
    if domain == "quranic":
        # Quran lens (amana): conservative confidence on Quranic text.
        if confidence > QURANIC_CONFIDENCE_CAP:
            confidence = QURANIC_CONFIDENCE_CAP
            flags.append("quranic-conservative-cap")
        else:
            flags.append("quranic-domain")
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append("low-confidence")

    token: dict[str, Any] = {
        "surface": word,
        "root": root or None,
        "pattern": pattern,
        "lemma": lemma,
        "pos": _POS_MAP.get(pattern),
        "diac": word if _TASHKEEL_RE.search(word) else None,
        "confidence": round(confidence, 3),
        "confidence_source": CONFIDENCE_SOURCE_HEURISTIC,
        "flags": flags,
    }
    return token


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(
    text: str,
    mode: str = "deterministic",
    domain: str = "general",
    nbest: int = 3,
) -> dict[str, Any]:
    """Analyze text into per-token morphology (deterministic, rule-based).

    Args:
        text: Arabic (or mixed) input text.
        mode: "deterministic" (argmax candidate per token) or "nbest"
            (argmax plus up to ``nbest``-1 scored alternatives).
        domain: "general" or "quranic" (conservative confidence + flags).
        nbest: number of candidates returned per token in nbest mode.

    Returns:
        ``{"tokens": [...], "model_info": {...}}``. Token confidence is
        heuristic/unverified — never calibrated.
    """
    if mode not in ("deterministic", "nbest"):
        raise ValueError(f"mode must be 'deterministic' or 'nbest', got {mode!r}")
    if domain not in ("general", "quranic"):
        raise ValueError(f"domain must be 'general' or 'quranic', got {domain!r}")

    tokens: list[dict[str, Any]] = []
    for word in _split_words(text):
        token = _analyze_token(word, domain)
        if mode == "nbest" and token["pattern"] not in ("STOPWORD", "NON_ARABIC"):
            token["alternatives"] = _alternatives(word, token, nbest)
        tokens.append(token)

    return {
        "tokens": tokens,
        "model_info": {
            "mode": mode,
            "backend_version": BACKEND_VERSION,
            "confidence_source": CONFIDENCE_SOURCE_HEURISTIC,
            "eval_note": EVAL_NOTE,
        },
    }


def _alternatives(word: str, best_token: dict[str, Any], nbest: int) -> list[dict[str, Any]]:
    """Scored runner-up candidates for nbest mode (heuristic scores)."""
    seen: list[dict[str, Any]] = []
    for cand in _candidate_analyses(word)[1:nbest]:
        key = (cand["root"], cand["pattern"])
        if any((a["root"], a["pattern"]) == key for a in seen):
            continue
        if key == (best_token["root"], best_token["pattern"]):
            continue
        lemma, _ = _lemma_for(cand["root"], cand["pattern"], cand["stem"])
        seen.append(
            {
                "root": cand["root"],
                "pattern": cand["pattern"],
                "lemma": lemma,
                "pos": _POS_MAP.get(cand["pattern"]),
                "confidence": round(cand["score"], 3),
                "confidence_source": CONFIDENCE_SOURCE_HEURISTIC,
            }
        )
    return seen


def analyze_with_model(
    text: str,
    model_path: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Hook for future trained-weight (Ruh model) morphology inference.

    Raises:
        MorphologyModelUnavailable: when no weights are configured or the
            path does not exist.
        NotImplementedError: when a path IS given but the weights loader is
            not implemented in this build (never silently falls back).
    """
    path = model_path or os.environ.get(MODEL_PATH_ENV)
    if not path or not Path(path).exists():
        raise MorphologyModelUnavailable(
            "No Ruh morphology weights configured. Set model_path or the "
            f"{MODEL_PATH_ENV} env var to a trained weights file. "
            "Deterministic mode (analyze) is the only available backend."
        )
    raise NotImplementedError(
        f"Weights found at {path}, but the Ruh morphology weights loader is "
        "not implemented in this build. Deterministic mode only."
    )


def get_capabilities() -> dict[str, Any]:
    """Backend capability probe (torch-free)."""
    roots: dict[str, Any] = _modules()["roots"]
    model_path = os.environ.get(MODEL_PATH_ENV)
    return {
        "tables_loaded": len(roots) > 0,
        "root_count": len(roots),
        "model_available": bool(model_path and Path(model_path).exists()),
        "model_path": model_path,
        "mode": "deterministic",
        "backend_version": BACKEND_VERSION,
        "confidence_source": CONFIDENCE_SOURCE_HEURISTIC,
        "eval_note": EVAL_NOTE,
    }
