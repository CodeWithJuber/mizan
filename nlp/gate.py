"""Single source of truth for when a native sense may enter the agent loop.

JEV `choice` (confidence 0.50, revised 2026-09-29 on Track 3 measured
evidence): top-1 confidence >= 0.80 AND margin over the runner-up >= 0.20.
Track 3 found 17.9% of results WRONG at >= 0.80 confidence (incl. a 0.9994
error) -- confidence is miscalibrated at the top end, so the gate filters
ambiguous low-information cases while the propose/admit framing (confidence
displayed, LLM admits; memory advisory) carries the residual
overconfident-error risk. Single-candidate lemmas pass the margin vacuously
(runner-up = 0.0).

Operators may tighten or loosen the gate from measured evidence with
MIZAN_NLP_MIN_SENSE_CONFIDENCE / MIZAN_NLP_MIN_SENSE_MARGIN; values are
bounded to [0, 1].
"""

from __future__ import annotations

import os

NLP_MIN_SENSE_CONFIDENCE = 0.8
NLP_MIN_SENSE_MARGIN = 0.2


def _bounded(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, "") or default)
    except ValueError:
        return default
    return min(1.0, max(0.0, value))


def sense_gate() -> tuple[float, float]:
    """Current (minimum confidence, minimum margin)."""
    return (
        _bounded("MIZAN_NLP_MIN_SENSE_CONFIDENCE", NLP_MIN_SENSE_CONFIDENCE),
        _bounded("MIZAN_NLP_MIN_SENSE_MARGIN", NLP_MIN_SENSE_MARGIN),
    )


def passes_sense_gate(confidence: float, margin: float) -> bool:
    """True when a native sense is confident and separated enough to use."""
    minimum, minimum_margin = sense_gate()
    return confidence >= minimum and margin >= minimum_margin
