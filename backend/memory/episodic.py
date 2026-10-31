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
