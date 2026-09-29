"""
mizan.nlp — public entry point: disambiguate().

Wired to the real Track-1 artifact (2026-09-29): per-lemma sklearn
LogisticRegression classifiers shipped in ``artifacts/default/``.
The artifact loads lazily as a process-global singleton on first use;
`is_ready()` reflects whether a valid artifact is discoverable.

Fail-closed: if no valid artifact is present, `disambiguate()` raises
`ModelNotReadyError` (the agent loop must fall back to the LLM path —
never swallow silently). Unknown lemmas return an empty candidate list
(the model never saw them; an empty list is the honest answer, not a
guessed sense).
"""

import json
import logging
import re
import threading
import unicodedata

from nlp.artifact import ARTIFACT_ENV_VAR, find_artifact
from nlp.types import SenseCandidate

logger = logging.getLogger("mizan.nlp")

#: Which trained variant is primary. 'a' = surface+context
#: (test acc 0.7592). 'b' = +morph family (test acc 0.7528).
PRIMARY_MODEL = "a"

_MODEL_KEYS = {
    "a": "model_a_surface_ctx",
    "b": "model_b_surface_ctx_morph",
}


class ModelNotReadyError(NotImplementedError):
    """Raised when `disambiguate()` is called before the trained artifact exists.

    The agent loop (Phase 2) must catch this and fall back to the current
    LLM-based understanding path. It must NEVER be swallowed silently.
    """

    def __init__(self, detail: str = "") -> None:
        msg = (
            "mizan.nlp has no trained artifact yet — the training track "
            "has not delivered a manifest. Run with is_ready() first, or "
            "set MIZAN_NLP_ARTIFACT to a validated artifact directory."
        )
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


# ── Frozen feature extractor (must match training exactly) ──────────────
# Copied verbatim from Track 1's mizan_sense_loader.py (trained 2026-09-29).
# DO NOT MODIFY: changing this silently invalidates the trained weights.
# The %-formatting below is byte-identical to the training code — ruff
# UP031 is suppressed file-wide for that reason (verified equivalent).
# ruff: noqa: UP031

_FEAT_A = "char 2-4 grams of (surface, prev surface, next surface) + length bucket (marks kept)"


def _ngrams(s, lo=2, hi=4):
    s = " " + (s or "") + " "
    out = {}
    for n in range(lo, hi + 1):
        for i in range(len(s) - n + 1):
            g = "c%d:%s" % (n, s[i : i + n])
            out[g] = out.get(g, 0) + 1
    return out


def _features(record, variant="a"):
    """Build the frozen feature dict from a Q-CSMP-style record (or kwargs)."""
    d = {}
    for k, s in (
        ("f", record.get("form")),
        ("p", (record.get("prev") or {}).get("form")),
        ("n", (record.get("next") or {}).get("form")),
    ):
        for g, c in _ngrams(s).items():
            d["%s:%s" % (k, g)] = c
    d["len=%s" % (record.get("morph") or {}).get("n_letters")] = 1
    if variant == "b":
        m = record.get("morph") or {}
        d["root=%s" % record.get("root")] = 1
        d["prev_root=%s" % (record.get("prev") or {}).get("root")] = 1
        d["next_root=%s" % (record.get("next") or {}).get("root")] = 1
        d["n_seg=%s" % m.get("n_seg")] = 1
        d["n_letters=%s" % m.get("n_letters")] = 1
        d["pos=%s" % record.get("pos")] = 1
    return d


# ── Text → token plumbing ───────────────────────────────────────────────

_DIACRITICS = re.compile(r"[\u064b-\u0652\u0670\u06d6-\u06ed]")


def _strip_marks(s: str) -> str:
    """Remove Arabic diacritics for lemma/token matching (forms keep them)."""
    return _DIACRITICS.sub("", unicodedata.normalize("NFC", s or ""))


def _locate_token(text: str, lemma: str) -> tuple[str | None, str | None, str | None]:
    """Find the text token corresponding to `lemma`; return (prev, form, next).

    Matching is on diacritic-stripped text so callers may pass either a
    diacritized or undiacritized lemma. Returns (None, None, None) when no
    token matches — the caller then falls back to form=lemma, no context.
    """
    tokens = text.split()
    want = _strip_marks(lemma)
    for i, tok in enumerate(tokens):
        t = _strip_marks(tok)
        if t == want or (want and want in t):
            prev = tokens[i - 1] if i > 0 else None
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            return prev, tok, nxt
    return None, None, None


def _sense_id(lemma: str, sense_slug: str) -> str:
    """Stable sense ID: qcsmp2:<lemma>:<sense-slug> (see artifact.py)."""
    return f"qcsmp2:{lemma}:{sense_slug}"


# ── Lazy singleton artifact loading ─────────────────────────────────────

_lock = threading.Lock()
_BUNDLE = None  # the unpickled joblib dict
_META = None  # manifest dict
_STRIPPED_LEMMA_INDEX: dict | None = None
_LOAD_ERROR: str | None = None


def _load_artifact() -> bool:
    """Load the artifact once (process-global). True on success.

    The manifest is fully validated (schema + files + sha256) BEFORE the
    joblib is unpickled. The artifact is first-party (shipped in-repo or
    operator-set via MIZAN_NLP_ARTIFACT); untrusted paths are never loaded.
    """
    global _BUNDLE, _META, _STRIPPED_LEMMA_INDEX, _LOAD_ERROR
    if _BUNDLE is not None or _LOAD_ERROR is not None:
        return _BUNDLE is not None
    with _lock:
        if _BUNDLE is not None or _LOAD_ERROR is not None:
            return _BUNDLE is not None
        artifact_dir = find_artifact()
        if artifact_dir is None:
            _LOAD_ERROR = (
                f"no valid artifact: {ARTIFACT_ENV_VAR} unset/invalid and no "
                "packaged artifacts/default/"
            )
            return False
        try:
            import joblib  # local import: only needed when the artifact exists

            with open(artifact_dir / "manifest.json", encoding="utf-8") as f:
                manifest = json.load(f)
            _META = manifest
            _BUNDLE = joblib.load(artifact_dir / manifest.get("model_file", "model.joblib"))
            key_a = _MODEL_KEYS["a"]
            _STRIPPED_LEMMA_INDEX = {
                _strip_marks(k): k for k in _BUNDLE["models"][key_a]["per_lemma"]
            }
        except Exception as exc:  # noqa: BLE001 — fail closed: never half-load
            _BUNDLE = None
            _META = None
            _STRIPPED_LEMMA_INDEX = None
            _LOAD_ERROR = f"artifact load failed: {exc}"
            logger.warning("mizan.nlp artifact load failed: %s", exc)
            return False
        logger.info(
            "mizan.nlp artifact loaded: %s v%s (%s lemmas, %s senses)",
            manifest.get("name"),
            manifest.get("version"),
            manifest.get("num_lemmas"),
            manifest.get("num_senses"),
        )
        return True


def _lemma_key(lemma: str) -> str | None:
    """Resolve a caller lemma to the artifact's per-lemma key.

    Exact match first (artifact keys are diacritized), then a
    diacritic-stripped match so undiacritized lemmas also resolve.
    """
    per_lemma = _BUNDLE["models"][_MODEL_KEYS[PRIMARY_MODEL]]["per_lemma"]
    if lemma in per_lemma:
        return lemma
    return _STRIPPED_LEMMA_INDEX.get(_strip_marks(lemma))


def is_ready() -> bool:
    """True once a valid trained artifact is discoverable and loadable."""
    return _load_artifact()


def disambiguate(text: str, lemma: str) -> list[SenseCandidate]:
    """Disambiguate which sense of `lemma` is used in `text`.

    Args:
        text: Arabic context (a verse, sentence, or passage).
        lemma: The lemma whose occurrence should be disambiguated
               (undiacritized or diacritized Arabic).

    Returns:
        List of ``SenseCandidate`` sorted by confidence, descending.
        Empty list if the lemma was never seen in training (graceful —
        the model has no opinion rather than a guessed one).

    Raises:
        TypeError: if `text` or `lemma` is not a string.
        ValueError: if either is empty/whitespace.
        ModelNotReadyError: when no valid artifact is present.
    """
    if not isinstance(text, str) or not isinstance(lemma, str):
        raise TypeError(
            f"disambiguate() expects str, str — got {type(text).__name__}, {type(lemma).__name__}"
        )
    if not text.strip() or not lemma.strip():
        raise ValueError("disambiguate() requires non-empty text and lemma")

    if not _load_artifact():
        raise ModelNotReadyError(_LOAD_ERROR or "")

    key = _lemma_key(lemma)
    if key is None:
        # Unknown lemma: the model never saw it — honest empty result.
        return []

    per = _BUNDLE["models"][_MODEL_KEYS[PRIMARY_MODEL]]["per_lemma"][key]
    prev_form, form, next_form = _locate_token(text, lemma)
    if form is None:
        # Lemma not found as a token in text: fall back to the bare lemma
        # as the form with no context (documented degradation).
        form, prev_form, next_form = lemma, None, None
    record = {
        "form": form,
        "prev": {"form": prev_form},
        "next": {"form": next_form},
        "root": None,
        "pos": None,
        "morph": {"n_seg": None, "n_letters": len(_strip_marks(form))},
    }
    X = per["vec"].transform([_features(record, variant=PRIMARY_MODEL)])
    probs = per["clf"].predict_proba(X)[0]
    order = sorted(range(len(probs)), key=lambda j: probs[j], reverse=True)
    return [
        SenseCandidate(
            sense_id=_sense_id(key, per["labels"][j]),
            confidence=float(probs[j]),
            lemma=lemma,
        )
        for j in order
    ]


def artifact_version() -> str:
    """Version string of the loaded artifact ('' if none loaded)."""
    if not _load_artifact():
        return ""
    return str((_META or {}).get("version", ""))


def reset_for_tests() -> None:
    """Drop the cached artifact (tests only — forces a fresh load)."""
    global _BUNDLE, _META, _STRIPPED_LEMMA_INDEX, _LOAD_ERROR
    with _lock:
        _BUNDLE = None
        _META = None
        _STRIPPED_LEMMA_INDEX = None
        _LOAD_ERROR = None
