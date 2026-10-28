"""Tadhkir: memory strength by FSRS, as the hadith of the tied camels describes it."""

from datetime import UTC, datetime, timedelta

import pytest

from memory import tadhkir
from memory.dhikr import DhikrMemorySystem, Memory, rank_memories

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def test_what_is_left_untouched_slips_away():
    held = tadhkir.learn(0.5, NOW)
    week, year = (
        tadhkir.retrievability(held, NOW + timedelta(days=7)),
        tadhkir.retrievability(held, NOW + timedelta(days=365)),
    )
    assert tadhkir.retrievability(held, NOW) == pytest.approx(1.0)
    assert 1.0 > week > year > 0.0


def test_a_recall_after_a_gap_strengthens_more_than_one_the_same_hour():
    held = tadhkir.learn(0.5, NOW)
    same_day = tadhkir.review(held, tadhkir.GOOD, NOW + timedelta(hours=1))
    after_gap = tadhkir.review(held, tadhkir.GOOD, NOW + timedelta(days=5))
    assert after_gap["stability"] > same_day["stability"] >= held["stability"] * 0.99


def test_repetition_keeps_a_memory_held_far_longer():
    once = tadhkir.learn(0.5, NOW)
    kept = once
    for day in (2, 7, 20):  # spaced recalls
        kept = tadhkir.review(kept, tadhkir.GOOD, NOW + timedelta(days=day))
    later = NOW + timedelta(days=80)
    assert tadhkir.retrievability(kept, later) > tadhkir.retrievability(once, later)
    assert tadhkir.interval_days(kept) > tadhkir.interval_days(once)


def test_a_lapse_is_relearned_from_a_lower_stability():
    held = tadhkir.review(tadhkir.learn(0.5, NOW), tadhkir.GOOD, NOW + timedelta(days=3))
    lapsed = tadhkir.review(held, tadhkir.AGAIN, NOW + timedelta(days=30))
    assert lapsed["stability"] < held["stability"]


def test_importance_sets_the_first_grade():
    assert tadhkir.first_grade(0.1).name == "Hard"
    assert tadhkir.first_grade(0.5).name == "Good"
    assert tadhkir.first_grade(0.9).name == "Easy"
    assert tadhkir.learn(0.9, NOW)["stability"] > tadhkir.learn(0.1, NOW)["stability"]


def test_a_memory_kept_before_tadhkir_has_no_strength_yet():
    assert tadhkir.retrievability(None) is None
    assert tadhkir.retrievability({"stability": None, "last_review": ""}) is None


def test_ranking_prefers_the_memory_that_is_still_held():
    old = NOW - timedelta(days=60)
    faded = Memory(id="faded", content="sabr in hardship", recency=old,
                   strength=tadhkir.learn(0.5, old))  # fmt: skip
    held = tadhkir.learn(0.5, old)
    for day in (3, 10, 30, 55):
        held = tadhkir.review(held, tadhkir.GOOD, old + timedelta(days=day))
    kept = Memory(id="kept", content="sabr in hardship", recency=old, strength=held)
    legacy = Memory(id="legacy", content="sabr in hardship", recency=old)  # ACT-R fallback
    order = [m.id for m in rank_memories("sabr", [faded, legacy, kept], NOW)]
    assert order[0] == "kept"


async def test_said_again_is_repeated_not_copied_and_recall_strengthens(tmp_path):
    memory = DhikrMemorySystem(db_path=str(tmp_path / "dhikr.db"))
    first = await memory.remember("My son's name is Yusuf.", importance=0.5)
    again = await memory.remember("my son's name is  Yusuf.", importance=0.5)
    assert again == first
    conn = memory._get_conn()
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        (before,) = conn.execute("SELECT stability FROM memories WHERE id = ?", (first,)).fetchone()
    finally:
        memory._release_conn(conn)
    assert count == 1 and before > 0
    found = await memory.recall("Yusuf")
    assert found and found[0].id == first and found[0].strength["stability"] >= before
