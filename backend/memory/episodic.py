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


# ── shadow: the person's episodes, kept and counted, not yet recalled ────
# (test 2 passed; the owner's decision of 31 Oct 2026: shadow first)

FILE = "episodes.sqlite3"
RECENT = 500  # earlier episodes a new statement is read against
# Unattended runs that replay a task the person wrote earlier (a schedule, a
# trigger, the queue, a watcher; ``ApprovalContext.origin``): their words are not the person speaking now, and keeping
# them each time would count the same words as having come up again.
REPLAYED = ("schedule", "trigger", "queue", "watcher")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS episodes_chat ON episodes (chat_id);
CREATE TABLE IF NOT EXISTS repeats (
    episode INTEGER NOT NULL,
    chat_id TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS repeats_episode ON repeats (episode);
CREATE INDEX IF NOT EXISTS repeats_chat ON repeats (chat_id);
"""


def mode() -> str:
    """``shadow`` (default): episodes are kept and counted, never recalled.
    ``off``: nothing is kept."""
    import os

    value = os.getenv("MIZAN_EPISODIC", "shadow").strip().lower()
    return value if value in ("shadow", "off") else "shadow"


def path_of(owner: str):
    from pathlib import Path

    from memory.mahw import private_dir

    return Path(private_dir(owner)) / FILE


def _open(owner: str):
    import sqlite3

    path = path_of(owner)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    return conn


def gate(message: str) -> tuple[str, str]:
    """(verdict, the person's own words): ``ok`` when this run may keep an episode:
    learning is on, the run is not stateless and not a replayed task; never an
    injection, pasted text or scripture (the gates Tadrib's lessons pass, without
    training's)."""
    from memory import stateless
    from tadbir import amanah, ruh_reader
    from tadbir.tadrib import lesson_text

    if mode() == "off":
        return "off", ""
    if stateless.active() or not stateless.learns():
        return "no consent", ""
    from security.approvals import current_approvals

    run = current_approvals()
    if run is not None and run.deferred and run.origin.split(":")[0] in REPLAYED:
        return "replayed", ""
    if amanah.scan_message(message or ""):
        return "injection", ""
    text = lesson_text(message or "").strip()
    if not text:
        return "no words", ""
    if ruh_reader.scripture(text):
        return "scripture", ""
    return "ok", text


def hear_now(owner: str, chat_id: str, message: str) -> dict:
    """Keep the statement as a weak episode, and strengthen every earlier episode
    of this person it brings up again (``came_up_again``)."""
    from datetime import UTC, datetime

    from tadbir.ahl_dhikr import about

    if not owner or not chat_id:
        return {"kept": False, "why": "no owner"}
    verdict, text = gate(message)
    if verdict != "ok":
        return {"kept": False, "why": verdict}
    at = datetime.now(UTC).isoformat()
    conn = _open(owner)
    try:
        earlier = conn.execute(
            "SELECT id, text FROM episodes ORDER BY id DESC LIMIT ?", (RECENT,)
        ).fetchall()
        again = [episode for episode, words in earlier if about(words, text)]
        conn.executemany(
            "INSERT INTO repeats (episode, chat_id, at) VALUES (?, ?, ?)",
            [(episode, chat_id, at) for episode in again],
        )
        conn.execute(
            "INSERT INTO episodes (chat_id, text, created) VALUES (?, ?, ?)", (chat_id, text, at)
        )
        conn.commit()
    finally:
        conn.close()
    return {"kept": True, "came_up_again": len(again), "mode": mode()}


async def hear(owner: str, chat_id: str, message: str) -> dict:
    import asyncio

    return await asyncio.to_thread(hear_now, owner, chat_id, message)


def forget_chat(owner: str, chat_id: str) -> dict:
    """Mahw: the chat's episodes, and every repeat the chat gave, are deleted."""
    path = path_of(owner)
    if not path.exists():
        return {"episodes": 0, "repeats": 0}
    conn = _open(owner)
    try:
        repeats = conn.execute(
            "DELETE FROM repeats WHERE chat_id = ? "
            "OR episode IN (SELECT id FROM episodes WHERE chat_id = ?)",
            (chat_id, chat_id),
        ).rowcount
        episodes = conn.execute("DELETE FROM episodes WHERE chat_id = ?", (chat_id,)).rowcount
        conn.commit()
    finally:
        conn.close()
    return {"episodes": episodes, "repeats": repeats}


def counts(owner: str) -> dict:
    """How many episodes this person has, and how many came up again (lasting)."""
    if not path_of(owner).exists():
        return {"episodes": 0, "lasting": 0}
    conn = _open(owner)
    try:
        (episodes,) = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
        (lasting,) = conn.execute("SELECT COUNT(DISTINCT episode) FROM repeats").fetchone()
    finally:
        conn.close()
    return {"episodes": int(episodes), "lasting": int(lasting)}


# ── does strength say which episode is needed? (read before recall uses it) ──
#
# Recall from episodes would rank them by FSRS retrievability R(t), with each
# time an episode came up again counted as a Good review. Before it may, real
# use must show that R says which episode a person needs. Each moment some
# episodes come up again (a "need") is read as a draw from the person's episodes
# that were alive then (the RECENT latest, as ``hear_now`` reads them):
#
#   strength:  P(k) = R_k / Σ R          (repeats strengthen, Nawm's model)
#   recency:   P(k) = R0_k / Σ R0        (R0: as written, never strengthened)
#   uniform:   P(k) = 1 / n
#
# The product over needs of P_strength(k) / P_null(k) is a test martingale under
# that null (its expectation given the past is Σ_k P_null(k)·P_s(k)/P_null(k) = 1),
# so it may be read at any time: Ville's inequality bounds the chance it ever
# reaches 1/α under the null by α. Strength must beat both nulls; the smaller
# e-value is valid against either (a uniform world can make recency look wrong
# without strength being right, which the simulation in docs/episodic-memory.md
# shows). When several episodes come up at one moment, their ratios are averaged
# (an average of e-values is an e-value).

ALPHA = 0.05


def _weights(state: dict, alive: list, at) -> tuple[dict, dict]:
    from memory import tadhkir

    decay, factor = tadhkir._curve(tadhkir.DEFAULTS)
    strong, written = {}, {}
    for key in alive:
        card, last, first, created = state[key]
        days = (at - last).total_seconds() / 86400.0
        strong[key] = (1.0 + factor * days / float(card.stability)) ** decay
        days = (at - created).total_seconds() / 86400.0
        written[key] = (1.0 + factor * days / first) ** decay
    return strong, written


def strength(episodes, repeats, recent: int = RECENT) -> dict:
    """One person's needs read against strength: ``episodes`` as (key, created)
    and ``repeats`` as (key, at), datetimes. Returns the needs read and the log
    e-values against recency and against uniform."""
    from fsrs import Card, Rating

    from memory import tadhkir

    scheduler = tadhkir._scheduler(tadhkir.DEFAULTS)
    # at one moment, needs are read before the episode written then (it was not
    # among those read against) and before any of them is strengthened
    events = sorted(
        [(at, 0, key) for key, at in repeats] + [(at, 1, key) for key, at in episodes],
        key=lambda event: (event[0], event[1]),
    )
    state: dict = {}
    order: list = []
    against_recency = against_uniform = 0.0
    needs = index = 0
    while index < len(events):
        at, kind, key = events[index]
        if kind == 1:
            card, _log = scheduler.review_card(Card(card_id=1), Rating.Hard, at)
            state[key] = [card, at, float(card.stability), at]
            order.append(key)
            index += 1
            continue
        moment = []
        while index < len(events) and events[index][:2] == (at, 0):
            moment.append(events[index][2])
            index += 1
        alive = order[-recent:]
        needed = [key for key in dict.fromkeys(moment) if key in state and key in alive]
        if needed and len(alive) >= 2:
            strong, written = _weights(state, alive, at)
            total, total_written = sum(strong.values()), sum(written.values())
            ratios = [(strong[k] / total) / (written[k] / total_written) for k in needed]
            uniform = [strong[k] / total * len(alive) for k in needed]
            against_recency += math.log(sum(ratios) / len(ratios))
            against_uniform += math.log(sum(uniform) / len(uniform))
            needs += 1
        for key in needed:
            card, _log = scheduler.review_card(state[key][0], tadhkir.GOOD, at)
            state[key][0], state[key][1] = card, at
    return {"needs": needs, "log_e": {"recency": against_recency, "uniform": against_uniform}}


def _histories():
    """Every person's episodes and repeats (no words), one person at a time."""
    import sqlite3
    from datetime import datetime

    from memory.mahw import private_dir

    root = private_dir("x").parent
    for path in sorted(root.glob(f"*/{FILE}")) if root.exists() else []:
        conn = sqlite3.connect(path)
        try:
            episodes = [
                (key, datetime.fromisoformat(created))
                for key, created in conn.execute("SELECT id, created FROM episodes")
            ]
            repeats = [
                (key, datetime.fromisoformat(at))
                for key, at in conn.execute("SELECT episode, at FROM repeats")
            ]
        except sqlite3.Error:
            continue
        finally:
            conn.close()
        yield episodes, repeats


def strength_report() -> dict:
    """Every person's needs, pooled (one person's e-process times another's):
    the e-value against each null, the smaller one deciding. Recall from
    episodes is proposed to the owner only when it reaches 1/α (it is never
    turned on by this report)."""
    people = needs = episodes = 0
    recency = uniform = 0.0
    for kept, repeats in _histories():
        found = strength(kept, repeats)
        people += 1
        episodes += len(kept)
        needs += found["needs"]
        recency += found["log_e"]["recency"]
        uniform += found["log_e"]["uniform"]

    def e(log: float) -> float:
        return math.exp(min(log, 700.0))

    smaller = min(recency, uniform)
    return {
        "people": people,
        "episodes": episodes,
        "needs": needs,
        "e_value": {"against_recency": e(recency), "against_uniform": e(uniform)},
        "e": e(smaller),
        "needed": 1 / ALPHA,
        "strength_says_need": smaller >= math.log(1 / ALPHA),
    }


def simulate(kind: str, *, episodes: int = 300, days: int = 360, rate: float = 0.3, seed: int = 0):
    """(episodes, repeats) drawn by thinning a rate-``rate`` proposal: each episode
    needed at λ·R with its repeats as Good reviews (``strength``), at λ·R0 as
    written (``recency``), or at λ (``uniform``)."""
    import random
    from datetime import UTC, datetime, timedelta

    from fsrs import Card, Rating

    from memory import tadhkir

    if kind not in ("strength", "recency", "uniform"):
        raise ValueError("kind is strength, recency or uniform")
    rng = random.Random(seed)
    scheduler = tadhkir._scheduler(tadhkir.DEFAULTS)
    decay, factor = tadhkir._curve(tadhkir.DEFAULTS)
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    finish = origin + timedelta(days=days)
    kept, repeats = [], []
    for number in range(episodes):
        created = origin + timedelta(days=rng.uniform(0, days))
        card, _log = scheduler.review_card(Card(card_id=1), Rating.Hard, created)
        first, last, proposal = float(card.stability), created, created
        kept.append((number, created))
        while True:
            proposal += timedelta(days=rng.expovariate(rate))
            if proposal >= finish:
                break
            if kind == "strength":
                days_since, stability = (proposal - last).total_seconds() / 86400.0, card.stability
            else:
                days_since, stability = (proposal - created).total_seconds() / 86400.0, first
            held = (1.0 + factor * days_since / float(stability)) ** decay
            if kind == "uniform" or rng.random() < held:
                repeats.append((number, proposal))
                if kind == "strength":
                    card, _log = scheduler.review_card(card, tadhkir.GOOD, proposal)
                    last = proposal
    return kept, repeats
