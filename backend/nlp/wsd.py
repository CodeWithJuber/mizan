"""
mizan.nlp — public entry point: disambiguate().

Phase 1: STUB. Raises `ModelNotReadyError` until the trained artifact
lands. Fail-closed by design (JEV decision on this branch, conf 0.91):
a stub that returned fake low-confidence senses could leak into the
agent loop as if it were real signal.
"""

import logging

from nlp.types import SenseCandidate

logger = logging.getLogger("mizan.nlp")

#: Env var pointing at a directory containing the trained artifact
#: (manifest.json + model.safetensors + tokenizer.json + sense_inventory.json).
ARTIFACT_ENV_VAR = "MIZAN_NLP_ARTIFACT"


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


def is_ready() -> bool:
    """True once a valid trained artifact is discoverable.

    Phase 1: always False. Phase 2: checks ARTIFACT_ENV_VAR and the
    packaged default artifact dir for a valid manifest.json.
    """
    return False


def disambiguate(text: str, lemma: str) -> list[SenseCandidate]:
    """Disambiguate which sense of `lemma` is used in `text`.

    Args:
        text: Arabic context (a verse, sentence, or passage).
        lemma: The lemma whose occurrence should be disambiguated
               (undiacritized or diacritized Arabic).

    Returns:
        List of ``SenseCandidate`` sorted by confidence, descending.

    Raises:
        TypeError: if `text` or `lemma` is not a string.
        ValueError: if either is empty/whitespace.
        ModelNotReadyError: until the trained artifact lands (Phase 1).

    Phase 2 (after the training track delivers):
        this will load the artifact once (process-global, lazy) and run
        native inference — no LLM round-trip.
    """
    if not isinstance(text, str) or not isinstance(lemma, str):
        raise TypeError(
            f"disambiguate() expects str, str — got {type(text).__name__}, {type(lemma).__name__}"
        )
    if not text.strip() or not lemma.strip():
        raise ValueError("disambiguate() requires non-empty text and lemma")

    # ── Phase 1 stub: fail closed ──────────────────────────────────────
    raise ModelNotReadyError(f"called with text[:40]={text[:40]!r}, lemma={lemma!r}")
