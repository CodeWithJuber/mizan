"""Episodic encoding: which of a person's own words become memories by themselves
(docs/episodic-memory.md)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from memory import episodic  # noqa: E402

# A small background of other conversations: "ok", "thanks" and "I" are in most turns.
BACKGROUND = episodic.Background.of(
    [
        "ok thanks",
        "ok sounds good",
        "thanks a lot",
        "I am fine thanks",
        "ok I will",
        "I think so too",
        "thanks, I agree",
        "ok see you",
    ]
)

TALK = [
    "ok",
    "I work as a stunt double in Atlanta.",
    "thanks!",
    "I work as a stunt double in Atlanta, as I said.",
    "My daughter Amina starts school in Lahore next week.",
]


def test_every_policy_keeps_in_order_and_all_keeps_every_statement():
    assert episodic.keep(TALK, "all") == [True] * len(TALK)
    with pytest.raises(ValueError):
        episodic.keep(TALK, "everything")


def test_a_statement_with_no_informative_word_is_never_kept():
    with pytest.raises(ValueError):
        episodic.keep(TALK, "informative")  # informative only against a background
    kept = episodic.keep(TALK, "informative", BACKGROUND)
    assert kept[0] is False and kept[2] is False
    assert kept[1] and kept[4]


def test_a_thing_said_again_is_not_written_twice():
    kept = episodic.keep(TALK, "novel", BACKGROUND)
    assert kept == [False, True, False, False, True]
    # what was kept before counts as known
    assert episodic.keep(TALK[3:4], "novel", BACKGROUND, known=TALK[1:2]) == [False]
