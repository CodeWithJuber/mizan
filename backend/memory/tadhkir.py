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
graded by how it went: Good when it was recalled and used, Again when the user
had to say it again. Its first writing is graded by its importance (Hard, Good
or Easy for the lower, middle and upper third).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fsrs import Card, Rating, Scheduler, State
from fsrs.scheduler import DEFAULT_PARAMETERS

# Memories are not flashcards: no minute-long learning steps, and no random
# fuzz on intervals, so the same history always gives the same strength.
_SCHEDULER = Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False)
_DECAY = -DEFAULT_PARAMETERS[20]
_FACTOR = 0.9 ** (1 / _DECAY) - 1
GOOD, AGAIN = Rating.Good, Rating.Again


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        found = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def first_grade(importance: float) -> Rating:
    """The first writing's grade: Hard, Good or Easy by the third of importance it falls in."""
    third = min(2, max(0, int(float(importance or 0.0) * 3)))
    return (Rating.Hard, Rating.Good, Rating.Easy)[third]


def learn(importance: float, now: datetime | None = None) -> dict:
    """The strength of a memory as it is first written."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    card, _log = _SCHEDULER.review_card(Card(card_id=1), first_grade(importance), now)
    return _state(card)


def review(state: dict | None, grade: Rating, now: datetime | None = None) -> dict:
    """The strength after a remembrance graded ``grade`` (Good: recalled and used;
    Again: the user had to give it again). A memory with no strength yet is
    first learned."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    last = _parse((state or {}).get("last_review"))
    stability = (state or {}).get("stability")
    difficulty = (state or {}).get("difficulty")
    if not stability or not difficulty or last is None:
        card, _log = _SCHEDULER.review_card(Card(card_id=1), grade, now)
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
    card, _log = _SCHEDULER.review_card(card, grade, now)
    return _state(card)


def retrievability(state: dict | None, now: datetime | None = None) -> float | None:
    """R(t): the chance MIZAN still recalls the memory now, or None when it has no
    strength recorded (a memory kept before Tadhkir)."""
    stability = (state or {}).get("stability")
    last = _parse((state or {}).get("last_review"))
    if not stability or last is None:
        return None
    now = (now or datetime.now(UTC)).astimezone(UTC)
    days = max(0.0, (now - last).total_seconds() / 86400.0)
    return float((1.0 + _FACTOR * days / float(stability)) ** _DECAY)


def interval_days(state: dict | None, retention: float = 0.9) -> float | None:
    """Days until the chance of recall falls to ``retention``: when to remind."""
    stability = (state or {}).get("stability")
    if not stability:
        return None
    return float(stability) / _FACTOR * (retention ** (1.0 / _DECAY) - 1.0)


def _state(card: Card) -> dict:
    return {
        "stability": round(float(card.stability or 0.0), 6),
        "difficulty": round(float(card.difficulty or 0.0), 6),
        "last_review": (card.last_review or datetime.now(UTC)).isoformat(),
    }
