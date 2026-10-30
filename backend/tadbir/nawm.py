"""Nawm (نوم, sleep): while MIZAN rests, what it learned is gone over again.

"And made your sleep [a means for] rest" (78:9); "And of His signs is your
sleep by night and day and your seeking of His bounty" (30:23, Saheeh
International).

In sleep the brain replays what it lived, and not uniformly: Mattar and Daw
(Nature Neuroscience 21, 2018) explained the order of hippocampal replay as the
value of revisiting each memory, the product of two terms. **Need** is how likely
the memory is to be used soon; **Gain** is how much revisiting it would change
what is done with it.

MIZAN replays the answers a teacher taught once (Talaqqi) the same way, while
no request is running:

- Need: the lesson's ACT-R base-level activation from how often it was given
  (n uses over its lifetime L, B = ln(n/(1−d)) − d·ln L, ``memory_activation_weight``);
- Gain: the chance its sources no longer bear it out, 1 − R(t), where R(t) is
  its FSRS retrievability (``memory.tadhkir``). Only a lesson whose R(t) has
  fallen below FSRS's target of 0.9 is replayed: one above it would be given
  on its sources anyway.

Each replayed lesson's claims are asked of Wikipedia again and read by the NLI
model, as a reuse would (``talaqqi.recheck``):

- every claim supported: the lesson is held more firmly (an FSRS Good review),
  so the person who asks next is answered at once, and it is not counted as
  given;
- a claim contradicted: the lesson is dropped before anyone is given it;
- otherwise (a source unreachable, a sentence not found): it is left as it was,
  and checked again when asked.

The night has a budget (``LESSONS`` per person, ``SECONDS`` in all), stops as
soon as a request is running, and keeps to each person's choices: under
``learning: off`` nothing is changed. ``MIZAN_NAWM``: ``on`` (default) or
``off``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from memory import stateless, tadhkir
from memory.dhikr import memory_activation_weight

from . import ahl_dhikr, sijill, talaqqi

LESSONS = 5  # replayed per person per night
SECONDS = 300.0  # the whole night's replay, every person together


def enabled() -> bool:
    return os.getenv("MIZAN_NAWM", "on").strip().lower() not in {"off", "0", "false", "no"}


def _age_seconds(stamp: Any, now: datetime) -> float:
    try:
        then = datetime.fromisoformat(str(stamp))
    except ValueError:
        return 1.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(1.0, (now - then).total_seconds())


def need(item: dict, now: datetime | None = None) -> float:
    """How likely the lesson is to be asked for soon (ACT-R activation)."""
    now = now or datetime.now(UTC)
    age = _age_seconds(item.get("kept"), now)
    return float(memory_activation_weight(age, int(item.get("reused", 0))))


def gain(item: dict, now: datetime | None = None) -> float:
    """The chance its sources no longer bear it out: 1 − R(t)."""
    held = tadhkir.retrievability(item.get("strength"), now)
    return 1.0 if held is None else 1.0 - held


def queue(items: list[dict], now: datetime | None = None) -> list[dict]:
    """The lessons whose hold fell below FSRS's target, by Need × Gain."""
    due = [item for item in items if item.get("claims") and talaqqi.due(item, now)]
    return sorted(due, key=lambda item: need(item, now) * gain(item, now), reverse=True)


async def replay(
    store: Any,
    user_id: str,
    *,
    outside: Callable[[str], Awaitable[list[ahl_dhikr.Passage]]] | None = None,
    deadline: float | None = None,
    idle: Callable[[], bool] = lambda: True,
    limit: int = LESSONS,
) -> dict:
    """One person's night: their most needed lapsed lessons asked of the
    sources again. Returns what happened to each."""
    report = {"replayed": 0, "confirmed": 0, "dropped": 0, "unsettled": 0}
    if not stateless.learns():
        return report  # learning: off, or an evaluation: nothing is changed

    async def wikipedia(query: str) -> list[ahl_dhikr.Passage]:
        return await ahl_dhikr.wikipedia(query, "en", deadline)

    ask = outside or wikipedia
    for item in queue(talaqqi.answers(store, user_id))[:limit]:
        if not idle() or (deadline is not None and time.monotonic() > deadline):
            break
        status, findings = await talaqqi.recheck(item, ask)
        report["replayed"] += 1
        # The note names no request: it is made outside any chat, so erasing
        # the chat (Mahw) could not find it.
        if status == "confirmed":
            talaqqi.refreshed(store, user_id, item, findings)
            report["confirmed"] += 1
            detail = "Replayed a learned answer while resting; its sources still hold"
            sijill.note("nawm", {"detail": detail}, owner=user_id)
        elif status == "contradicted":
            talaqqi.drop(store, user_id, item)
            report["dropped"] += 1
            detail = "Replayed a learned answer while resting; a source now says otherwise: dropped"
            sijill.note("nawm", {"detail": detail}, owner=user_id)
        else:
            report["unsettled"] += 1
    return report
