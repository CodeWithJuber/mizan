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

The same night seeks a second witness for what only one site has said
(``witness``): "And bring to witness two witnesses" (2:282). A sentence of the
person's ``ilm`` that a single host settled is shown under an answer but is not
given to Lisan as knowledge until an independent host agrees
(``ahl_dhikr.evidence_for``). The most needed of these claims are asked of
Wikipedia while MIZAN rests; a site is never its own second witness, and a
question about the deen is never asked outside.

Last, FSRS is fitted on the review log of the person's memories and tested
against the parameters in use on their later reviews, by a margin chance does
not reach (``memory.tadhkir.rest``). A fit that passes is reported; it is put to
use only under ``MIZAN_TADHKIR_FIT=apply`` (``tadhkir.applies``).

Then MIZAN's own language reader (``ruh_reader.rest``) learns the person's
own words that they let it train on (``training: on``) and that a named
reviewer accepted, with a quarter of every batch replayed from the seeds; the
new version replaces the current one only when it is no worse on held-out
seeds, and the previous one is kept. Nothing happens without trained weights
or under ``MIZAN_RUH_READER=off``.

The night has a budget (``LESSONS`` and ``WITNESSES`` per person, ``SECONDS`` in
all), stops as soon as a request is running, and keeps to each person's
choices: under ``learning: off`` nothing is changed. ``MIZAN_NAWM``: ``on``
(default) or ``off``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from memory import stateless, tadhkir
from memory.dhikr import memory_activation_weight

from . import ahl_dhikr, ruh_reader, sijill, talaqqi

LESSONS = 5  # replayed per person per night
WITNESSES = 5  # claims per person whose second witness is sought per night
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


async def witness(
    store: Any,
    user_id: str,
    *,
    deadline: float | None = None,
    idle: Callable[[], bool] = lambda: True,
    limit: int = WITNESSES,
) -> dict:
    """Seek a second, independent witness for the claims one site settled,
    the most recently used first. Returns how many were sought and found."""
    report = {"sought": 0, "corroborated": 0}
    if not stateless.learns():
        return report
    now = datetime.now(UTC)
    lone = [
        (claim, entry["items"][0])
        for claim, entry in ahl_dhikr.witnesses(store, user_id).items()
        if entry["grade"] == "hasan" and entry["items"][0].get("verdict") == "supported"
    ]
    lone.sort(
        key=lambda pair: memory_activation_weight(_age_seconds(pair[1].get("used"), now), 0),
        reverse=True,
    )
    for claim, _item in lone[:limit]:
        if not idle() or (deadline is not None and time.monotonic() > deadline):
            break
        report["sought"] += 1
        await ahl_dhikr.consult(
            claim,
            [{"text": claim, "grade": "daif", "kind": "sentence"}],
            store=store,
            user_id=user_id,
            language="en",
        )
        if ahl_dhikr.witnesses(store, user_id).get(claim, {}).get("grade") == "sahih":
            report["corroborated"] += 1
            detail = "While resting, a second independent source agreed with a fact: now knowledge"
            sijill.note("nawm", {"detail": detail}, owner=user_id)
    return report


async def night(
    store: Any,
    user_id: str,
    *,
    deadline: float | None = None,
    idle: Callable[[], bool] = lambda: True,
) -> dict:
    """One person's night: lessons replayed, second witnesses sought, then FSRS
    fitted on the review log of their memory, which shares the store's database
    (``tadhkir.rest``: adopted only on held-out evidence, and only when fits are
    applied; else a passing fit is counted as ``shadow``), then the language
    reader's night (``ruh_reader.rest``)."""
    lessons = await replay(store, user_id, deadline=deadline, idle=idle)
    witnesses = await witness(store, user_id, deadline=deadline, idle=idle)
    fit = await tadhkir.rest(getattr(store, "db_path", None), deadline=deadline, idle=idle)
    status = fit.get("status")
    try:
        read = await ruh_reader.rest(user_id, deadline=deadline, idle=idle)
    except Exception:  # noqa: BLE001 - the reader's night never ends the rest of it
        read = {"status": "failed"}
    if read.get("status") == "promoted":
        detail = "While resting, the language reader learned from your reviewed words"
        sijill.note("nawm", {"detail": detail}, owner=user_id)
    return {
        **lessons,
        **witnesses,
        "fitted": int(status == "adopted"),
        "shadow": int(status == "shadow"),
        "reader_learned": int(read.get("learned") or 0),
    }
