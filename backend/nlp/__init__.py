"""
mizan.nlp — Native Qur'anic Arabic sense-disambiguation package
===============================================================

Phase 1 (this branch): interface skeleton only. The trained artifact is
owned by a separate training track; nothing here changes agent behavior
yet — `disambiguate()` raises `ModelNotReadyError` until the artifact
lands (fail-closed, JEV decision logged on the branch).

Public interface
----------------
    from nlp import disambiguate, is_ready, SenseCandidate, ModelNotReadyError

    if is_ready():
        for sense_id, confidence in disambiguate(text, lemma):
            ...

`sense_id` is a string like ``"qcsmp2:ktb:v3"`` (dataset:root:sense).
`confidence` is a float in ``[0.0, 1.0]``.
"""

from nlp.types import DisambiguationResult, SenseCandidate
from nlp.wsd import ModelNotReadyError, disambiguate, is_ready

__all__ = [
    "ModelNotReadyError",
    "SenseCandidate",
    "DisambiguationResult",
    "disambiguate",
    "is_ready",
]

__version__ = "0.1.0"
