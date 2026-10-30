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


def stability_of(memory, mem_id):
    conn = memory._get_conn()
    try:
        return conn.execute(
            "SELECT stability, access_count FROM memories WHERE id = ?", (mem_id,)
        ).fetchone()
    finally:
        memory._release_conn(conn)


async def test_in_a_run_only_the_memory_the_answer_used_is_strengthened(tmp_path):
    """Recall is not use: what is always near the top of a search must not grow
    by being near the top, only by being used (the testing effect)."""
    from memory.dhikr import defer_reviews, settle_reviews

    memory = DhikrMemorySystem(db_path=str(tmp_path / "dhikr.db"))
    son = await memory.remember("My son's name is Yusuf.", importance=0.5)
    city = await memory.remember("My son Yusuf studies in Hyderabad.", importance=0.5)
    before = {mem_id: stability_of(memory, mem_id) for mem_id in (son, city)}
    token = defer_reviews()
    found = await memory.recall("Yusuf", limit=5)
    assert {item.id for item in found} >= {son, city}
    assert stability_of(memory, son) == before[son]  # held until the answer is known
    assert settle_reviews(token, "Yusuf is studying in Hyderabad this year.") == 1
    assert stability_of(memory, city)[1] == before[city][1] + 1  # used
    assert stability_of(memory, son) == before[son]  # recalled, not used


async def test_said_again_after_its_hold_lapsed_is_relearned(tmp_path):
    memory = DhikrMemorySystem(db_path=str(tmp_path / "dhikr.db"))
    first = await memory.remember("My son's name is Yusuf.", importance=0.5)
    old = datetime.now(UTC) - timedelta(days=400)
    held = tadhkir.learn(0.5, old)
    conn = memory._get_conn()
    try:
        conn.execute(
            "UPDATE memories SET stability = ?, difficulty = ?, last_review = ? WHERE id = ?",
            (held["stability"], held["difficulty"], held["last_review"], first),
        )
        conn.commit()
    finally:
        memory._release_conn(conn)
    assert tadhkir.retrievability(held) < tadhkir.RETENTION
    await memory.remember("My son's name is Yusuf.", importance=0.5)
    lapsed = tadhkir.review(held, tadhkir.AGAIN)
    good = tadhkir.review(held, tadhkir.GOOD)
    (stability, _count) = stability_of(memory, first)
    assert stability == pytest.approx(lapsed["stability"]) and stability < good["stability"]
