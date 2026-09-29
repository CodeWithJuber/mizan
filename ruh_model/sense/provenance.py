"""Provenance receipts for Ruh sense decisions (torch-free, stdlib only).

The receipt is the anti-hallucination artifact: for every sense decision it
lists *which computed signals* supported the outcome, where each signal came
from, and what share of the final confidence it contributed.

Iron rule: **a receipt only ever contains signals that were actually
computed.** It never invents support. If the trained-model signal was not
wired into a decision, no ``"model"`` entry appears — the absence is the
honest statement.

Known signals (closed set — :func:`build_receipt` rejects anything else):

- ``"inventory"``      — the sense exists in the versioned sense inventory.
- ``"qcsmp_label"``    — support from a Q-CSMP v2 labeled pair (dataset/version).
- ``"lexicon"``        — support from a lexicon entry (source named).
- ``"context_overlap"``— support from deterministic context/keyword overlap.
- ``"model"``          — support from a trained classifier posterior (source named).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

#: Closed vocabulary of provenance signals. Anything else is rejected —
#: inventing a signal name is inventing evidence.
KNOWN_SIGNALS = frozenset(
    {
        "inventory",
        "qcsmp_label",
        "lexicon",
        "context_overlap",
        "model",
    }
)


@dataclass(frozen=True)
class ProvenanceSignal:
    """One computed piece of support for a sense decision.

    ``signal``: one of :data:`KNOWN_SIGNALS`.
    ``source``: where the signal came from, e.g.
        ``"sense-inventory/v1.0.0"`` or ``"mizan-sense-wsd/1.2.1"`` —
        always a concrete dataset/artifact/version, never a vague label.
    ``weight``: the signal's share of the chosen sense's confidence,
        a float in ``[0.0, 1.0]``.
    """

    signal: str
    source: str
    weight: float

    def __post_init__(self) -> None:
        if self.signal not in KNOWN_SIGNALS:
            raise ValueError(
                f"unknown provenance signal {self.signal!r}; known signals: {sorted(KNOWN_SIGNALS)}"
            )
        if not self.source or not self.source.strip():
            raise ValueError("provenance source must be a non-empty dataset/version string")
        w = float(self.weight)
        if not 0.0 <= w <= 1.0:
            raise ValueError(f"provenance weight must be in [0.0, 1.0], got {self.weight!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_receipt(signals: list[ProvenanceSignal]) -> list[dict[str, Any]]:
    """Build the JSON-serializable provenance receipt for one decision.

    The caller passes *only signals it actually computed*, in the order they
    were applied. An empty receipt is valid (e.g. ``unknown_lemma`` — there
    was no decision to support).
    """
    return [s.to_dict() for s in signals]
