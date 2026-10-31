"""Episodic encoding: which of a person's own words become memories by themselves
(docs/episodic-memory.md; the owner's decision of 31 Oct 2026: tested first, then
shadow).

Until now a memory entered ``memories`` only when the person asked ("remember
this"). People do not remember that way: an experience is encoded as it happens,
and what is new is encoded more strongly than what was already known (prediction
error); sleep then keeps or lets go of it. MIZAN already has the second half
(Nawm, FSRS strength in ``memory/tadhkir.py``). This is the first half.

Policies (fixed before any measurement):

- ``all``: every statement of the person is kept.
- ``informative``: a statement is kept when it carries a word more informative
  than an average running word of *conversation* (the background: how many
  turns of other conversations each word appears in), so "ok", "thanks" and
  "haan", which conversation is full of, never are.
- ``novel``: an informative statement is kept only when most of its distinctive
  information is not already in what was kept of this person
  (``ahl_dhikr.about``), so a thing said again strengthens the old memory
  (Tadhkir's repeat review) instead of being written twice.

No word lists and no thresholds: "informative" is above the background's average
word, and "new" is more than half of a statement's own information.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

POLICIES = ("all", "informative", "novel")


def came_up_again(statements: Sequence[str], later: Sequence[Sequence[str]]) -> list[bool]:
    """Test 2's rule (docs/episodic-memory.md): a statement becomes a lasting
    memory when it came up again, that is when some later turn of the
    conversation, by either speaker, holds most of its distinctive information
    (``ahl_dhikr.about``). ``later[i]`` is every turn after statement ``i`` that
    MIZAN has heard. A thing that came up once stays a weak trace that Nawm lets
    fade; one that came up again is strengthened, as Tadhkir's repeat review
    strengthens a note said again (Anderson & Schooler 1991: past frequency
    predicts need)."""
    from tadbir.ahl_dhikr import about

    return [
        any(about(statement, turn) for turn in after)
        for statement, after in zip(statements, later, strict=True)
    ]


@dataclass
class Background:
    """How many turns of conversation each word appears in."""

    counts: dict[str, int]
    turns: int

    @classmethod
    def of(cls, turns: Iterable[str]) -> Background:
        from core.adaptive import tokenize

        counts: dict[str, int] = {}
        total = 0
        for turn in turns:
            words = set(tokenize(turn))
            if words:
                total += 1
                for word in words:
                    counts[word] = counts.get(word, 0) + 1
        return cls(counts, total)

    def information(self, word: str) -> float:
        return math.log((self.turns + 1) / (self.counts.get(word, 0) + 1))

    def average(self) -> float:
        """The information of an average running word of conversation."""
        occurrences = sum(self.counts.values()) or 1
        return (
            sum(count * self.information(word) for word, count in self.counts.items()) / occurrences
        )


def informative(statement: str, background: Background, average: float | None = None) -> bool:
    from core.adaptive import tokenize

    floor = background.average() if average is None else average
    return any(background.information(word) > floor for word in tokenize(statement))


def keep(
    statements: Sequence[str],
    policy: str,
    background: Background | None = None,
    known: Sequence[str] = (),
) -> list[bool]:
    """Which of these statements (in order, one person's) the policy keeps; ``known``
    is what was kept of the person before."""
    from tadbir.ahl_dhikr import about

    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {', '.join(POLICIES)}")
    if policy != "all" and background is None:
        raise ValueError("this policy needs the conversation background")
    floor = background.average() if background is not None else 0.0
    kept = list(known)
    found: list[bool] = []
    for statement in statements:
        if policy == "all":
            chosen = bool(statement.strip())
        elif background is None or not informative(statement, background, floor):
            chosen = False
        elif policy == "informative":
            chosen = True
        else:
            chosen = not kept or not about(statement, " ".join(kept))
        if chosen:
            kept.append(statement)
        found.append(chosen)
    return found
