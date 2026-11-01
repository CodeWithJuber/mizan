"""
mizan.nlp — result types.

Keep these types stable: the Phase-2 agent-loop wiring and the training
track both depend on them. Changes require a minor version bump.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SenseCandidate:
    """One sense hypothesis for a lemma occurrence.

    ``sense_id``: stable identifier, e.g. ``"qcsmp2:ktb:v3"`` — the
    ``<dataset>:<root>:<sense>`` triple. The training track owns the
    inventory and must keep every shipped ID immutable.

    ``confidence``: float in ``[0.0, 1.0]`` — calibrated posterior P(sense |
    context). Must sum to ≈1.0 across the returned list when more than one
    candidate is returned.

    Supports tuple unpacking so the contract reads as the task's
    ``list of (sense_id, confidence)``::

        for sense_id, confidence in disambiguate(text, lemma): ...
    """

    sense_id: str
    confidence: float
    lemma: str = ""
    gloss: str = ""

    def __iter__(self):
        yield self.sense_id
        yield self.confidence


@dataclass(frozen=True)
class DisambiguationResult:
    """Full disambiguation outcome for one (text, lemma) call."""

    text: str
    lemma: str
    candidates: tuple = field(default_factory=tuple)
    artifact_version: str = ""

    @property
    def best(self) -> SenseCandidate | None:
        """Highest-confidence candidate, or None if the list is empty."""
        if not self.candidates:
            return None
        return max(self.candidates, key=lambda c: c.confidence)
