"""Adjudicated benchmark harness — Q-CSMP v2 → expert-adjudicated WSD benchmark.

Study #10 (ruh-usecase-deep-20260929, JEV qcsmp_benchmark @ 0.77): the
credibility foundation. Q-CSMP v2 pilot (Zenodo DOI 10.5281/zenodo.23024527,
CC-BY-4.0, 28,841 records, 48 lemmas, 115 lemma-senses) has keyword-rule
labels — 38/95 sense groups heuristic-flagged suspect. The card's own
prerequisite: expert adjudication with inter-annotator agreement κ ≥ 0.61
before any peer-reviewed publication.

This module runs the adjudication protocol:

* phase-0 track's ``ruh_model/eval/adjudication.py`` provides the protocol
  (annotator workflow, item schema). It is NOT merged yet — the import is
  wrapped in try/except and the runner degrades gracefully with a clear
  message until it lands.
* ``cohens_kappa`` (pure stdlib) scores annotator agreement.
* ``summarize_adjudication`` checks the result against the κ ≥ 0.61 gate.

Honest caveats (from research, carried here as code comments, not claims):
the pilot's own Δ_Q = −0.0555 (root features LOST at pilot scale) — lead
with it; adjudication may shrink the dataset; auto-labels are never tafsir;
ARR/NAACL Oct-2026 not feasible, target OSACT 8 / ArabicNLP 2027.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "KAPPA_TARGET",
    "ADJUDICATION_UNAVAILABLE_MESSAGE",
    "AdjudicationResult",
    "cohens_kappa",
    "run_adjudication_protocol",
    "summarize_adjudication",
]

# The Zenodo card's own prerequisite: κ ≥ 0.61 before peer-reviewed publication.
KAPPA_TARGET = 0.61

ADJUDICATION_UNAVAILABLE_MESSAGE = (
    "Adjudication protocol unavailable: ruh_model/eval/adjudication.py "
    "(phase-0 track) is not merged yet. This runner degrades gracefully until "
    "it lands — no adjudication has been performed."
)

try:
    # Phase-0 track code — merge pending. Importing through the ruh_model
    # package requires torch; in torch-less envs this raises ImportError and
    # we fall through to the graceful path below.
    from ruh_model.eval.adjudication import (  # type: ignore[import-not-found]
        AdjudicationProtocol,
    )

    _PHASE0_AVAILABLE = True
except ImportError:
    AdjudicationProtocol = None  # type: ignore[assignment,misc]
    _PHASE0_AVAILABLE = False


@dataclass
class AdjudicationResult:
    """One adjudicated item: two annotator labels + the resolved label."""

    item_id: str
    annotator_a: str
    annotator_b: str
    adjudicated_label: str
    agreement: bool = field(init=False)

    def __post_init__(self) -> None:
        self.agreement = self.annotator_a == self.annotator_b


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Cohen's κ for two annotators (pure stdlib).

    Returns 1.0 on perfect agreement, ≤ 0 on chance-level agreement.
    """
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("label lists must be non-empty and the same length")
    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    expected = 0.0
    for label in set(labels_a) | set(labels_b):
        pa = sum(1 for a in labels_a if a == label) / n
        pb = sum(1 for b in labels_b if b == label) / n
        expected += pa * pb
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def run_adjudication_protocol(items: list[dict], protocol=None) -> dict:
    """Run the adjudication protocol over pilot items.

    Until the phase-0 ``ruh_model/eval/adjudication.py`` merges, returns a
    graceful ``status="unavailable"`` payload — never a fabricated result.
    """
    active_protocol = protocol if protocol is not None else AdjudicationProtocol
    if active_protocol is None:
        return {
            "status": "unavailable",
            "message": ADJUDICATION_UNAVAILABLE_MESSAGE,
            "items_seen": len(items),
        }
    # Phase-0 protocol drives; this harness only wraps + scores it.
    results = active_protocol.adjudicate(items)  # expected: list[AdjudicationResult]-likes
    return {"status": "complete", "results": results, "summary": summarize_adjudication(results)}


def summarize_adjudication(results: list[AdjudicationResult]) -> dict:
    """Score adjudication results against the κ ≥ 0.61 publication gate."""
    if not results:
        return {
            "status": "empty",
            "n": 0,
            "kappa_target": KAPPA_TARGET,
            "meets_prerequisite": False,
            "verdict": "no adjudicated items — nothing to score",
        }
    labels_a = [r.annotator_a for r in results]
    labels_b = [r.annotator_b for r in results]
    kappa = cohens_kappa(labels_a, labels_b)
    agreement_rate = sum(1 for r in results if r.agreement) / len(results)
    meets = kappa >= KAPPA_TARGET
    return {
        "status": "scored",
        "n": len(results),
        "agreement_rate": agreement_rate,
        "cohens_kappa": kappa,
        "kappa_target": KAPPA_TARGET,
        "meets_prerequisite": meets,
        "verdict": (
            "meets κ ≥ 0.61 prerequisite for peer-reviewed publication"
            if meets
            else "BELOW κ ≥ 0.61 — more adjudication rounds needed before publication"
        ),
    }
