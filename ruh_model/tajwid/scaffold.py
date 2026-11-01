"""Tajwīd Buddy scaffold — interface definitions for root-aware recitation feedback.

**UNPROVEN — Q28 Arabic-speech→root-space trained nahi hai; ye sirf interface
hai, koi working feature nahi.**
(UNPROVEN — the Q28 Arabic-speech→root-space bridge has NOT been trained;
this is an interface only, not a working feature. Koi accuracy claim nahi —
no accuracy claims.)

Intended data flow (once the gate is cleared):

    ASR hypothesis (on-device, whisper-class)
        → root-lattice rescoring ("in this verse only these roots are valid")
        → sense-aware correction ("you substituted a different root —
           here is the meaning drift")

Every function that would need the trained bridge raises
``NotImplementedError`` with the gate spelled out. Pure stdlib — no torch.

Research gate (study #8): Q28 phonetic bridge is trained English→root-space;
Arabic speech→root-space is NOT trained. Required before real work:
recitation-audio dataset + training run + published error rates + scholarly
review of correction behavior (wrong tajweed correction is worse than none).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SCAFFOLD_STATUS",
    "GATE_MESSAGE",
    "ASRToken",
    "ASRHypothesis",
    "RootLattice",
    "RescoredHypothesis",
    "rescore_hypothesis",
    "meaning_drift",
]

GATE_MESSAGE = (
    "Tajwid Buddy is an UNPROVEN scaffold: the Q28 Arabic-speech→root-space "
    "bridge has not been trained. This is an interface only, not a working "
    "feature. Gate: recitation-audio dataset + training run (study #8)."
)

SCAFFOLD_STATUS = {
    "status": "unproven-scaffold",
    "trained": False,
    "gate": "Q28 Arabic-speech→root-space training (recitation-audio dataset + run)",
    "accuracy_claims": None,  # deliberately: no claims until the gate clears
    "detail": GATE_MESSAGE,
}


@dataclass
class ASRToken:
    """One ASR-decoded token with timing and confidence."""

    surface: str
    start_ms: int
    end_ms: int
    confidence: float


@dataclass
class ASRHypothesis:
    """Full-utterance ASR hypothesis feeding the rescorer."""

    transcript: str
    tokens: list[ASRToken] = field(default_factory=list)
    confidence: float = 0.0
    language: str = "ar"


@dataclass
class RootLattice:
    """Verse-constrained set of valid roots for rescoring.

    E.g. for a known verse, only the roots actually present in that verse
    are valid — the lattice re-ranks acoustically ambiguous ASR hypotheses
    toward morphologically valid readings.
    """

    allowed_roots: list[str]  # e.g. ["ك-ت-ب", "ق-ر-أ"]
    verse_ref: str = ""  # e.g. "2:255"
    source: str = "scaffold-unproven"


@dataclass
class RescoredHypothesis:
    """ASR hypothesis re-ranked against the root lattice."""

    hypothesis: ASRHypothesis
    lattice: RootLattice
    root_sequence: list[str] = field(default_factory=list)
    rescore_confidence: float = 0.0
    provenance: str = "scaffold-unproven"


def rescore_hypothesis(hypothesis: ASRHypothesis, lattice: RootLattice) -> RescoredHypothesis:
    """Re-rank an ASR hypothesis against a verse-constrained root lattice.

    SCAFFOLD: raises NotImplementedError until the Q28
    Arabic-speech→root-space bridge is trained (see GATE_MESSAGE).
    """
    raise NotImplementedError(GATE_MESSAGE)


def meaning_drift(expected_root: str, substituted_root: str) -> dict:
    """Describe the meaning drift of a root substitution (sense-aware correction).

    SCAFFOLD: raises NotImplementedError until the Q28
    Arabic-speech→root-space bridge is trained (see GATE_MESSAGE).
    """
    raise NotImplementedError(GATE_MESSAGE)
