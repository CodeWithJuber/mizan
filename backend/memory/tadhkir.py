"""Tadhkir (تذكير, reminding): how firmly MIZAN still holds each memory.

The Prophet ﷺ said: "The example of the person who knows the Qur'an by heart
is like the owner of tied camels. If he keeps them tied, he will control them,
but if he releases them, they will run away" (Bukhari 5031), and "keep on
reciting the Qur'an because it escapes from the hearts of men faster than
camel do" (Bukhari 5032). He "used to repeat it thrice so that the people could
understand it properly" (Bukhari 95), and chose the time to teach "so that we
might not get bored" (Bukhari 68). And of what is kept and what is lost: "As for
the foam, it vanishes, [being] cast off; but as for that which benefits the
people, it remains on the earth" (13:17, Saheeh International).

So a memory is held by being remembered, not by its first writing:

- each time MIZAN recalls a memory to use it, it is held more firmly and for
  longer, and a recall after a gap strengthens more than one the same hour
  (spacing);
- a memory left untouched slips away, and what is never used is the foam;
- a memory the user had to give again had lapsed: it is relearned.

The mathematics is FSRS-6 (the ``fsrs`` package, open-spaced-repetition, MIT),
whose parameters are fitted on hundreds of millions of human reviews. A memory
has a stability S (the days until the chance of recalling it falls to 90%) and
a difficulty D. The chance of recalling it t days after it was last reviewed is

    R(t) = (1 + f·t/S)^(−w₂₀),   f = 0.9^(−1/w₂₀) − 1,

and every remembrance is a review that updates S and D by FSRS's equations,
graded by how it went:
- Good when it was recalled and the answer used it. A memory recalled but not
  used is not reviewed, so what is always near the top of a search does not
  grow by being near the top (``dhikr.settle_reviews``);
- when the user says it again: Good while MIZAN still held it (R ≥ 0.9, FSRS's
  target), Again once its hold had fallen below, since it had lapsed.
Its first writing is graded by its importance (Hard, Good or Easy for the
lower, middle and upper third).

FSRS's default parameters were fitted on flashcard reviews, and memory differs
by person and by material. So every review a memory gets is appended to the
``memory_reviews`` log in the memory's own database (memory id, agent id,
grade, kind, time; no words), and while MIZAN rests (Nawm) FSRS is fitted on
that log (``rest``):

- the earlier half of the scored reviews fits a challenger: FSRS's own
  optimizer (``fsrs[optimizer]``: torch, pandas, tqdm) when it is installed and
  has its mini-batch of reviews, else a light maximum-likelihood fit of six
  parameters (``LIGHT``);
- the later half tests it against the parameters in use. The likelihood ratio
  of those reviews, E = Π p_challenger / p_in_use, is an e-value: if the
  parameters in use are right, E[E] ≤ 1 (the split likelihood-ratio test of
  universal inference, Wasserman, Ramdas & Balakrishnan, PNAS 2020);
- the challenger is adopted only when E reaches k(k+1)/α for the k-th test on
  this log, so over every night ever tested the chance of adopting parameters
  that are no better stays below α = 0.05. log E is the number of reviews
  tested times the drop in log-loss: a margin that chance does not reach.

A fit that passes is put to use only under ``MIZAN_TADHKIR_FIT=apply``. By
default (``shadow``) it is measured and reported, not adopted, because the log
is partly written by the parameters it tests (``applies``): a restatement is
graded Again only when R(t) under the parameters in use fell below 0.9, and
only a memory that was recalled gets a use review.

A memory's stored S and D stay valid: later reviews and R(t) use the
parameters in use from then on. Lessons kept by Talaqqi are not memories and
keep FSRS's defaults.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from fsrs import Card, Rating, ReviewLog, Scheduler, State
from fsrs.scheduler import DEFAULT_PARAMETERS, LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS

DEFAULTS: tuple[float, ...] = tuple(float(value) for value in DEFAULT_PARAMETERS)
GOOD, AGAIN = Rating.Good, Rating.Again
# FSRS's own default desired retention: below it, a memory has lapsed.
RETENTION = 0.9
# The declared chance of ever adopting fitted parameters that are no better.
ALPHA = 0.05
# The parameters the light fit moves: the first stability after a Hard, Good or
# Easy first writing (w1–w3; MIZAN never writes a memory Again), how much a used
# memory's stability grows (w8), the stability after a lapse (w11) and the shape
# of the forgetting curve (w20). The rest keep FSRS's values.
LIGHT = (1, 2, 3, 8, 11, 20)
_ADDITIVE = {8}  # w8 is an exponent and may be 0: it moves by steps, the rest by factors


@lru_cache(maxsize=64)
def _scheduler(parameters: tuple[float, ...] = DEFAULTS) -> Scheduler:
    # Memories are not flashcards: no minute-long learning steps, and no random
    # fuzz on intervals, so the same history always gives the same strength.
    return Scheduler(
        parameters=parameters, learning_steps=(), relearning_steps=(), enable_fuzzing=False
    )


def _chosen(parameters: Sequence[float] | None) -> tuple[float, ...]:
    return DEFAULTS if parameters is None else tuple(float(value) for value in parameters)


def _curve(parameters: tuple[float, ...]) -> tuple[float, float]:
    """The forgetting curve's exponent and factor: R = (1 + f·t/S)^decay."""
    decay = -parameters[20]
    return decay, 0.9 ** (1 / decay) - 1


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        found = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return found.astimezone(UTC) if found.tzinfo else found.replace(tzinfo=UTC)


def first_grade(importance: float) -> Rating:
    """The first writing's grade: Hard, Good or Easy by the third of importance it falls in."""
    third = min(2, max(0, int(float(importance or 0.0) * 3)))
    return (Rating.Hard, Rating.Good, Rating.Easy)[third]


def learn(
    importance: float, now: datetime | None = None, *, parameters: Sequence[float] | None = None
) -> dict:
    """The strength of a memory as it is first written."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    scheduler = _scheduler(_chosen(parameters))
    card, _log = scheduler.review_card(Card(card_id=1), first_grade(importance), now)
    return _state(card)


def review(
    state: dict | None,
    grade: Rating,
    now: datetime | None = None,
    *,
    parameters: Sequence[float] | None = None,
) -> dict:
    """The strength after a remembrance graded ``grade`` (Good: recalled and used;
    Again: the user had to give it again). A memory with no strength yet is
    first learned. ``parameters``: the FSRS parameters in use (``in_use``)."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    scheduler = _scheduler(_chosen(parameters))
    last = _parse((state or {}).get("last_review"))
    stability = (state or {}).get("stability")
    difficulty = (state or {}).get("difficulty")
    if not stability or not difficulty or last is None:
        card, _log = scheduler.review_card(Card(card_id=1), grade, now)
        return _state(card)
    card = Card(
        card_id=1,
        state=State.Review,
        step=None,
        stability=float(stability),
        difficulty=float(difficulty),
        due=now,
        last_review=min(last, now),
    )
    card, _log = scheduler.review_card(card, grade, now)
    return _state(card)


def retrievability(
    state: dict | None, now: datetime | None = None, *, parameters: Sequence[float] | None = None
) -> float | None:
    """R(t): the chance MIZAN still recalls the memory now, or None when it has no
    strength recorded (a memory kept before Tadhkir)."""
    stability = (state or {}).get("stability")
    last = _parse((state or {}).get("last_review"))
    if not stability or last is None:
        return None
    now = (now or datetime.now(UTC)).astimezone(UTC)
    days = max(0.0, (now - last).total_seconds() / 86400.0)
    decay, factor = _curve(_chosen(parameters))
    return float((1.0 + factor * days / float(stability)) ** decay)


def interval_days(
    state: dict | None, retention: float = 0.9, *, parameters: Sequence[float] | None = None
) -> float | None:
    """Days until the chance of recall falls to ``retention``: when to remind."""
    stability = (state or {}).get("stability")
    if not stability:
        return None
    decay, factor = _curve(_chosen(parameters))
    days: float = float(stability) / factor * (retention ** (1.0 / decay) - 1.0)
    return days


def _state(card: Card) -> dict:
    return {
        "stability": round(float(card.stability or 0.0), 6),
        "difficulty": round(float(card.difficulty or 0.0), 6),
        "last_review": (card.last_review or datetime.now(UTC)).isoformat(),
    }


# ── The review log, in the memories' own database ─────────────────────────


def ensure(conn: sqlite3.Connection) -> None:
    """The review log and the parameters fitted on it, beside ``memories``. A
    memory's reviews go with it wherever it is deleted (Mahw, Daftar, pruning)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS memory_reviews ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT NOT NULL, "
        "agent_id TEXT NOT NULL DEFAULT '', rating INTEGER NOT NULL, "
        "kind TEXT NOT NULL DEFAULT '', reviewed TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_reviews_memory ON memory_reviews(memory_id)"
    )
    conn.execute(
        "CREATE TRIGGER IF NOT EXISTS memory_reviews_go_with_their_memory "
        "AFTER DELETE ON memories BEGIN "
        "DELETE FROM memory_reviews WHERE memory_id = OLD.id; END"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tadhkir_parameters ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), parameters TEXT NOT NULL, "
        "fitted INTEGER NOT NULL DEFAULT 0, evaluation TEXT NOT NULL DEFAULT '{}', "
        "latest TEXT NOT NULL DEFAULT '{}', tests INTEGER NOT NULL DEFAULT 0, "
        "seen TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL DEFAULT '')"
    )


def log(conn: sqlite3.Connection, reviews: Iterable[tuple[str, str, int, str, str]]) -> int:
    """Append reviews, each (memory id, agent id, grade, kind, ISO time), where
    kind is ``learn`` (first writing), ``use`` (recalled and used) or ``repeat``
    (said again). No words are written, and nothing in a stateless run or under
    ``learning: off``, which keep no learned state. The caller commits."""
    from memory import stateless

    if not stateless.learns():
        return 0
    rows = [
        (str(memory_id), str(agent_id or ""), int(grade), str(kind), str(at))
        for memory_id, agent_id, grade, kind, at in reviews
    ]
    if rows:
        conn.executemany(
            "INSERT INTO memory_reviews (memory_id, agent_id, rating, kind, reviewed) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def _record(conn: sqlite3.Connection) -> dict:
    try:
        row = conn.execute(
            "SELECT parameters, fitted, evaluation, latest, tests, seen FROM tadhkir_parameters "
            "WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row:
        return {"parameters": DEFAULTS, "fitted": False, "evaluation": {}, "latest": {},
                "tests": 0, "seen": ""}  # fmt: skip
    try:
        parameters = tuple(float(value) for value in json.loads(row[0]))
        _scheduler(parameters)  # within FSRS's bounds
    except (TypeError, ValueError):
        parameters = DEFAULTS
    return {
        "parameters": parameters,
        "fitted": bool(row[1]) and parameters != DEFAULTS,
        "evaluation": json.loads(row[2] or "{}"),
        "latest": json.loads(row[3] or "{}"),
        "tests": int(row[4] or 0),
        "seen": str(row[5] or ""),
    }


def in_use(conn: sqlite3.Connection) -> tuple[float, ...]:
    """The parameters this database's memories are reviewed with: fitted on its
    own log once they earned it, else FSRS's defaults."""
    parameters: tuple[float, ...] = _record(conn)["parameters"]
    return parameters


def _save(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tadhkir_parameters "
        "(id, parameters, fitted, evaluation, latest, tests, seen, updated) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
        (
            json.dumps(list(record["parameters"])),
            int(record["fitted"]),
            json.dumps(record["evaluation"]),
            json.dumps(record["latest"]),
            int(record["tests"]),
            record["seen"],
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def report(conn: sqlite3.Connection) -> dict:
    """The parameters in use, whether they were fitted, the test that earned
    them and the latest night's test."""
    record = _record(conn)
    try:
        (logged,) = conn.execute("SELECT COUNT(*) FROM memory_reviews").fetchone()
    except sqlite3.OperationalError:
        logged = 0
    return {
        "parameters": list(record["parameters"]),
        "fitted": record["fitted"],
        "evaluation": record["evaluation"] or None,
        "latest": record["latest"] or None,
        "tests": record["tests"],
        "reviews_logged": int(logged),
        "defaults": list(DEFAULTS),
        "alpha": ALPHA,
        "mode": "apply" if applies() else "shadow",
    }


def unfit(conn: sqlite3.Connection, earliest: Any) -> int:
    """Erased reviews (Mahw), the earliest logged at ``earliest``, leave nothing
    derived from them: fitted parameters adopted after that time go back to
    FSRS's defaults, and the next night fits again on the log that is kept.
    Returns 1 when a fitted set was dropped."""
    record = _record(conn)
    erased = _parse(earliest)
    adopted = _parse((record["evaluation"] or {}).get("date"))
    if not record["fitted"] or erased is None or (adopted is not None and erased > adopted):
        return 0
    record.update(parameters=DEFAULTS, fitted=False, evaluation={}, seen="")
    _save(conn, record)
    return 1


# ── Fitting FSRS on the log ───────────────────────────────────────────────

Event = tuple[datetime, Rating]


def histories(rows: Iterable[tuple[str, int, str, str]]) -> dict[str, list[Event]]:
    """Each memory's reviews in time order, from rows (memory id, grade, kind,
    ISO time) in the order they were logged. Only a history that begins with its
    first writing can be replayed: a memory kept before the log, or written
    under ``learning: off``, is left out."""
    grouped: dict[str, list[tuple[datetime, int, str]]] = {}
    for memory_id, grade, kind, stamp in rows:
        at = _parse(stamp)
        if at is None or int(grade) not in (1, 2, 3, 4):
            continue
        grouped.setdefault(str(memory_id), []).append((at, int(grade), str(kind)))
    found: dict[str, list[Event]] = {}
    for memory_id, events in grouped.items():
        events.sort(key=lambda event: event[0])  # stable: same-moment rows keep their order
        if events[0][2] == "learn":
            found[memory_id] = [(at, Rating(grade)) for at, grade, _kind in events]
    return found


def _scored(previous: datetime | None, at: datetime) -> bool:
    # A review at least a whole day after the last one: what FSRS scores. A
    # same-day review says little about forgetting.
    return previous is not None and (at - previous).days >= 1


def _loss(held: float, recalled: bool) -> float:
    chance = held if recalled else 1.0 - held
    # log clamped at −100, as torch's BCELoss (FSRS's optimizer) clamps it
    return -max(math.log(chance), -100.0) if chance > 0 else 100.0


def losses(
    found: dict[str, list[Event]],
    parameters: Sequence[float],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[float]:
    """The log-loss of each scored review in [since, until), predicted by R(t)
    under ``parameters`` from the memory's own history before it. Again counts
    as not recalled, every other grade as recalled."""
    scheduler = _scheduler(_chosen(parameters))
    result = []
    for events in found.values():
        card = Card(card_id=1)
        for at, grade in events:
            if until is not None and at >= until:
                break
            if _scored(card.last_review, at) and (since is None or at >= since):
                held = float(scheduler.get_card_retrievability(card, at))
                result.append(_loss(held, grade != AGAIN))
            card, _log = scheduler.review_card(card, grade, at)
    return result


def _scored_times(found: dict[str, list[Event]]) -> list[datetime]:
    return sorted(
        at
        for events in found.values()
        for (previous, _), (at, _grade) in zip(events, events[1:], strict=False)
        if _scored(previous, at)
    )


def split(found: dict[str, list[Event]]) -> datetime | None:
    """The moment halfway through the scored reviews: the earlier half fits,
    the later half tests (the even split of universal inference). None when the
    log cannot be split in two."""
    times = _scored_times(found)
    if len(times) < 2 or times[len(times) // 2] <= times[0]:
        return None
    return times[len(times) // 2]


def _moved(index: int, value: float, step: float) -> float:
    low, high = LOWER_BOUNDS_PARAMETERS[index], UPPER_BOUNDS_PARAMETERS[index]
    moved = value + step if index in _ADDITIVE else value * math.exp(step)
    return float(min(high, max(low, moved)))


def light_fit(
    found: dict[str, list[Event]],
    until: datetime,
    start: Sequence[float] = DEFAULTS,
    stop: Callable[[], bool] = lambda: False,
) -> tuple[float, ...] | None:
    """Maximum likelihood over ``LIGHT`` on the reviews before ``until``, by a
    compass search (each parameter moved up or down by a factor, the factor
    halved when no move lowers the log-loss; Kolda, Lewis & Torczon 2003).
    Pure Python, for an install without FSRS's optimizer. None when ``stop``."""
    point = list(_chosen(start))

    def objective(candidate: list[float]) -> float:
        found_losses = losses(found, candidate, until=until)
        return sum(found_losses) / max(1, len(found_losses))

    best = objective(point)
    step = math.log(2.0)
    while step >= math.log(2.0) / 64:  # until a move is under 1.1%
        improved = False
        for index in LIGHT:
            for sign in (1.0, -1.0):
                if stop():
                    return None
                trial = list(point)
                trial[index] = _moved(index, point[index], sign * step)
                if trial[index] == point[index]:
                    continue
                loss = objective(trial)
                if loss < best:
                    point, best, improved = trial, loss, True
                    break
        if not improved:
            step /= 2
    return tuple(point)


def _clamped(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(
        float(min(high, max(low, float(value))))
        for value, low, high in zip(
            values, LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS, strict=True
        )
    )


def optimizer_fit(
    found: dict[str, list[Event]], until: datetime, seconds: float | None = None
) -> tuple[tuple[float, ...] | None, str, float]:
    """FSRS's own optimizer (all 21 parameters, by gradient descent) on the
    reviews before ``until``. Returns (parameters or None, why not, seconds it
    ran). None when it is not installed, declines (fewer scored reviews than its
    mini-batch of 512) or has not finished within ``seconds``."""
    from importlib.util import find_spec

    # Checked before importing: torch alone (as in the production image) would
    # be loaded for nothing when pandas or tqdm is missing.
    if not all(find_spec(name) for name in ("torch", "pandas", "tqdm")):
        return None, "not installed", 0.0
    import fsrs

    logs = [
        ReviewLog(card_id=number, rating=grade, review_datetime=at, review_duration=None)
        for number, events in enumerate(found.values(), start=1)
        for at, grade in events
        if at < until
    ]
    try:
        optimizer = fsrs.Optimizer(logs)
    except ImportError:
        return None, "not installed", 0.0
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["parameters"] = optimizer.compute_optimal_parameters()
        except Exception as exc:  # noqa: BLE001 - a failed fit leaves the light fit
            outcome["error"] = exc

    began = time.monotonic()
    worker = threading.Thread(target=run, name="tadhkir-optimizer", daemon=True)
    worker.start()
    worker.join(seconds)
    ran = time.monotonic() - began
    if worker.is_alive():
        return None, "did not finish in the night's time", ran
    if "error" in outcome:
        return None, f"failed: {type(outcome['error']).__name__}", ran
    fitted = _clamped(outcome["parameters"])
    if fitted == DEFAULTS:
        return None, "fewer scored reviews than its mini-batch", ran
    return fitted, "", ran


def applies() -> bool:
    """Whether a fit that passed its test is put to use (``MIZAN_TADHKIR_FIT``:
    ``shadow``, the default, measures and reports it; ``apply`` adopts it). The
    log is partly written by the parameters it tests: a restatement is graded
    Again only when R(t) under the parameters in use fell below 0.9, and only a
    recalled memory gets a use review. Until a grade is read independently of
    them, a passing fit is evidence that it reproduces its own grading, not
    that it predicts this person's forgetting better."""
    return os.getenv("MIZAN_TADHKIR_FIT", "shadow").strip().lower() == "apply"


def needed(test: int) -> float:
    """The e-value the ``test``-th test on a log must reach: k(k+1)/α. These
    spend α/(k(k+1)), which sums to α over every test ever made."""
    return test * (test + 1) / ALPHA


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def refit(
    conn: sqlite3.Connection,
    *,
    stop: Callable[[], bool] = lambda: False,
    seconds: float | None = None,
    optimizer: bool = True,
    apply: bool | None = None,
) -> dict:
    """One night's fit of this database's log: a challenger fitted on the
    earlier half, tested against the parameters in use on the later half, and
    adopted only when its e-value reaches ``needed`` and fits are applied
    (``apply``, by default ``applies()``). Returns what happened."""
    ensure(conn)
    rows = conn.execute(
        "SELECT id, memory_id, rating, kind, reviewed FROM memory_reviews ORDER BY id"
    ).fetchall()
    seen = f"{len(rows)}:{rows[-1][0] if rows else 0}"
    record = _record(conn)
    if record["seen"] == seen:
        return {"status": "unchanged", "reviews": len(rows)}
    found = histories(row[1:] for row in rows)
    cut = split(found)
    if cut is None:
        record["seen"] = seen
        _save(conn, record)
        return {"status": "too few reviews", "reviews": len(rows)}
    current = record["parameters"]
    began = time.monotonic()
    pace = (record["latest"] or {}).get("optimizer_seconds_per_review")
    challenger: tuple[float, ...] | None = None
    method, optimizer_said = "light fit", "not tried"
    if optimizer:
        # FSRS's optimizer cannot be stopped once started: it starts only when
        # the pace it showed on this log before says it finishes in time.
        before = sum(1 for events in found.values() for at, _grade in events if at < cut)
        if seconds is not None and pace is not None and float(pace) * before > seconds:
            optimizer_said = "would not finish in the night's time"
        else:
            challenger, why, ran = optimizer_fit(found, cut, seconds)
            optimizer_said = why or "used"
            if ran and before:
                pace = ran / before
            if challenger is not None:
                method = "fsrs optimizer"
    if challenger is None:

        def halt() -> bool:
            return stop() or (seconds is not None and time.monotonic() - began > seconds)

        challenger = light_fit(found, cut, current, halt)
    paced = {"optimizer_seconds_per_review": pace} if pace is not None else {}
    if challenger is None:
        record["latest"] = {**(record["latest"] or {}), **paced}
        _save(conn, record)  # the log is fitted again next night
        return {"status": "stopped", "reviews": len(rows)}
    tested_in_use = losses(found, current, since=cut)
    tested = losses(found, challenger, since=cut)
    tested_defaults = tested_in_use if current == DEFAULTS else losses(found, DEFAULTS, since=cut)
    test = record["tests"] + 1
    log_e = sum(tested_in_use) - sum(tested)
    adopted = log_e >= math.log(needed(test))
    evaluation = {
        "date": datetime.now(UTC).isoformat(),
        "method": method,
        "optimizer": optimizer_said,
        "reviews": len(rows),
        "memories": len(found),
        "fitted_on": sum(1 for at in _scored_times(found) if at < cut),
        "tested_on": len(tested),
        "split": cut.isoformat(),
        "log_loss": {
            "in_use": _mean(tested_in_use),
            "defaults": _mean(tested_defaults),
            "fitted": _mean(tested),
        },
        "e_value": math.exp(min(log_e, 700.0)),
        "needed": needed(test),
        "test": test,
        "adopted": adopted,
        "parameters": [round(value, 6) for value in challenger],
    }
    applied = adopted and (applies() if apply is None else apply)
    if adopted and not applied:
        evaluation.update(adopted=False, would_adopt=True, mode="shadow")
    record["latest"] = {**evaluation, **paced}
    record.update(tests=test, seen=seen)
    if applied:
        record.update(parameters=challenger, fitted=challenger != DEFAULTS, evaluation=evaluation)
    _save(conn, record)
    status = "adopted" if applied else "shadow" if adopted else "kept"
    return {"status": status, **evaluation}


async def rest(
    db_path: str | None,
    *,
    deadline: float | None = None,
    idle: Callable[[], bool] = lambda: True,
) -> dict:
    """Nawm's part for one memory database: FSRS fitted on its review log in a
    worker thread, only while no request runs and within the night's time, and
    never in a stateless run or under ``learning: off``."""
    from memory import stateless

    if not db_path or not stateless.learns() or not idle():
        return {"status": "skipped"}
    seconds = None if deadline is None else deadline - time.monotonic()
    if seconds is not None and seconds <= 0:
        return {"status": "skipped"}

    def stop() -> bool:
        return not idle() or (deadline is not None and time.monotonic() > deadline)

    def work() -> dict:
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            kept = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memories'"
            ).fetchone()
            return refit(conn, stop=stop, seconds=seconds) if kept else {"status": "no memories"}
        finally:
            conn.close()

    return await asyncio.to_thread(work)


# ── Simulated logs: what the fit recovers, and what the guard refuses ─────


def simulate(
    parameters: Sequence[float],
    *,
    memories: int = 400,
    days: int = 360,
    seed: int = 0,
    start: datetime | None = None,
) -> list[tuple[str, int, str, str]]:
    """A review log as MIZAN writes it, drawn from FSRS with ``parameters``.
    Each memory is written at a uniform time in ``days`` and graded by a uniform
    importance; it is reused after gaps drawn log-uniformly from an hour to 90
    days (the same chat, then days and weeks later), and at each reuse it is
    recalled with probability R(t): a Good use if so, else the person gives it
    again (Again). Rows are (memory id, grade, kind, ISO time)."""
    rng = random.Random(seed)
    scheduler = _scheduler(_chosen(parameters))
    origin = start or datetime(2026, 1, 1, tzinfo=UTC)
    end = origin + timedelta(days=days)
    rows: list[tuple[str, int, str, str]] = []
    for number in range(memories):
        at = origin + timedelta(days=rng.uniform(0, days))
        grade = first_grade(rng.random())
        card, _log = scheduler.review_card(Card(card_id=1), grade, at)
        rows.append((f"m{number}", int(grade), "learn", at.isoformat()))
        while True:
            at = at + timedelta(days=math.exp(rng.uniform(math.log(1 / 24), math.log(90))))
            if at >= end:
                break
            recalled = rng.random() < float(scheduler.get_card_retrievability(card, at))
            grade = GOOD if recalled else AGAIN
            card, _log = scheduler.review_card(card, grade, at)
            rows.append((f"m{number}", int(grade), "use" if recalled else "repeat", at.isoformat()))
    rows.sort(key=lambda row: row[3])
    return rows


def measure(
    truth: Sequence[float], *, seed: int = 0, optimizer: bool = True, memories: int = 400
) -> dict:
    """A night's fit on a log simulated from ``truth``, in a scratch database,
    with the held-out log-loss of ``truth`` itself beside it (the floor)."""
    rows = simulate(truth, seed=seed, memories=memories)
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY)")
        ensure(conn)
        conn.executemany(
            "INSERT INTO memory_reviews (memory_id, agent_id, rating, kind, reviewed) "
            "VALUES (?, '', ?, ?, ?)",
            rows,
        )
        found = refit(conn, optimizer=optimizer, apply=True)  # a simulated log is not circular
    finally:
        conn.close()
    cut = _parse(found.get("split"))
    if cut is not None:
        found["log_loss"]["truth"] = _mean(losses(histories(rows), truth, since=cut))
    return found


def _person(changes: dict[int, float]) -> tuple[float, ...]:
    return _clamped([changes.get(index, value) for index, value in enumerate(DEFAULTS)])


# A person who forgets faster than flashcard learners: shorter first holds
# (w1–w3), easier first difficulty (w4), less growth per use (w8–w10), a lower
# hold after a lapse (w11) and a steeper curve (w20). Three of these lie outside
# what the light fit moves.
FASTER = _person({1: 0.6, 2: 1.1, 3: 3.5, 4: 5.0, 8: 1.3, 9: 0.3, 10: 1.2, 11: 1.0, 20: 0.35})


if __name__ == "__main__":  # cd backend && python -m memory.tadhkir [--light] [seeds]
    import sys

    use_optimizer = "--light" not in sys.argv
    seeds = next((int(arg) for arg in sys.argv[1:] if arg.isdigit()), 3)
    shown = ("method", "fitted_on", "tested_on", "log_loss", "e_value", "needed", "adopted")
    for name, truth in (("a different person", FASTER), ("FSRS's defaults", DEFAULTS)):
        for seed in range(seeds):
            found = measure(truth, seed=seed, optimizer=use_optimizer)
            print(name, seed, json.dumps({key: found.get(key) for key in shown}), flush=True)
