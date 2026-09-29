"""
mizan.nlp — Native Qur'anic Arabic sense-disambiguation package
===============================================================

Wired to the real Track-1 artifact (per-lemma sklearn LogisticRegression,
trained 2026-09-29 on Q-CSMP v2, shipped in ``nlp/artifacts/default/``).

Public interface
----------------
    from nlp import disambiguate, is_ready, SenseCandidate, ModelNotReadyError

    if is_ready():
        for sense_id, confidence in disambiguate(text, lemma):
            ...

`sense_id` is a string like ``"qcsmp2:يَوْم:judgment-day"``
(``<dataset>:<lemma>:<sense-slug>``). `confidence` is a float in
``[0.0, 1.0]``; candidates are sorted by confidence, descending, and
sum to ≈1.0.

Fail-closed: `disambiguate()` raises `ModelNotReadyError` when no valid
artifact is present (the agent loop must fall back to the LLM path).
Unknown lemmas return an empty list — the model has no opinion rather
than a guessed sense.
"""

from nlp.types import DisambiguationResult, SenseCandidate
from nlp.wsd import ModelNotReadyError, artifact_version, disambiguate, is_ready

__all__ = [
    "DisambiguationResult",
    "ModelNotReadyError",
    "SenseCandidate",
    "artifact_version",
    "disambiguate",
    "is_ready",
]

__version__ = "0.2.0"
