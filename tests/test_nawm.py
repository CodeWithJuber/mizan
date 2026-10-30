"""Nawm: while MIZAN rests, what it learned is replayed by Need × Gain (78:9, 30:23)."""

from datetime import UTC, datetime, timedelta

import pytest

from core.adaptive import AdaptiveStateStore
from memory import stateless, tadhkir
from tadbir import ahl_dhikr, nawm, talaqqi
from tadbir.ahl_dhikr import Finding, Passage

TITAN = "Titan is the largest moon of Saturn, larger than the planet Mercury."
WIKI = Passage(TITAN, "Titan (moon)", "https://en.wikipedia.org/wiki/Titan_(moon)", "wikipedia")


@pytest.fixture
def store(tmp_path):
    return AdaptiveStateStore(str(tmp_path / "adaptive.db"))


async def moons(pairs):
    readings = []
    for premise, hypothesis in pairs:
        said = {m for m in ("Titan", "Rhea") if m in premise}
        claimed = {m for m in ("Titan", "Rhea") if m in hypothesis}
        if said and claimed and said == claimed:
            readings.append({"entailment": 0.97, "neutral": 0.02, "contradiction": 0.01})
        elif said and claimed:
            readings.append({"entailment": 0.01, "neutral": 0.04, "contradiction": 0.95})
        else:
            readings.append({"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05})
    return readings


def kept(store, question, claim, *, days_ago, reused=0):
    talaqqi.keep(
        store, "u1", question, "en", [Finding(claim, "supported", 0.97, WIKI)], teacher="t"
    )
    items = talaqqi.answers(store, "u1")
    then = datetime.now(UTC) - timedelta(days=days_ago)
    for item in items:
        if item["answer"].startswith(claim):
            item["strength"] = tadhkir.learn(0.5, then)
            item["kept"] = then.isoformat(timespec="seconds")
            item["reused"] = reused
    store.put(talaqqi._key("u1"), {"answers": items})


def test_need_and_gain_order_the_night():
    now = datetime.now(UTC)
    old = (now - timedelta(days=60)).isoformat()
    often = {"kept": old, "reused": 9, "strength": tadhkir.learn(0.5, now - timedelta(days=30))}
    seldom = {"kept": old, "reused": 0, "strength": tadhkir.learn(0.5, now - timedelta(days=30))}
    fresh = {"kept": old, "reused": 9, "strength": tadhkir.learn(0.5, now)}
    assert nawm.need(often, now) > nawm.need(seldom, now)
    assert nawm.gain(often, now) > nawm.gain(fresh, now)
    for item in (often, seldom, fresh):
        item["claims"] = [{"claim": "x"}]
    # The fresh one is still held (R ≥ 0.9): it is not replayed at all.
    assert nawm.queue([seldom, fresh, often], now) == [often, seldom]


async def test_a_lapsed_lesson_its_sources_still_hold_is_held_more_firmly(store, monkeypatch):
    monkeypatch.setattr(ahl_dhikr, "nli", moons)
    kept(store, "What is the largest moon of Saturn?", "The largest moon of Saturn is Titan.",
         days_ago=40, reused=2)  # fmt: skip
    before = talaqqi.answers(store, "u1")[0]
    assert talaqqi.due(before)

    async def outside(query):
        return [WIKI]

    report = await nawm.replay(store, "u1", outside=outside)
    assert report == {"replayed": 1, "confirmed": 1, "dropped": 0, "unsettled": 0}
    after = talaqqi.answers(store, "u1")[0]
    assert not talaqqi.due(after) and after["reused"] == 2  # held again, not counted as given
    assert after["refreshed"]


async def test_a_lesson_a_source_now_contradicts_is_dropped_before_anyone_is_given_it(
    store, monkeypatch
):
    monkeypatch.setattr(ahl_dhikr, "nli", moons)
    kept(store, "What is the largest moon of Saturn?", "The largest moon of Saturn is Titan.",
         days_ago=40)  # fmt: skip

    async def outside(query):
        return [
            Passage("The largest moon of Saturn is Rhea.", "Rhea", "https://x.example/r", "web")
        ]

    assert (await nawm.replay(store, "u1", outside=outside))["dropped"] == 1
    assert talaqqi.answers(store, "u1") == []


async def test_the_night_stops_for_a_request_and_keeps_each_persons_choice(store, monkeypatch):
    monkeypatch.setattr(ahl_dhikr, "nli", moons)
    kept(store, "What is the largest moon of Saturn?", "The largest moon of Saturn is Titan.",
         days_ago=40)  # fmt: skip
    asked = []

    async def outside(query):
        asked.append(query)
        return [WIKI]

    # A request is running: nothing is replayed.
    assert (await nawm.replay(store, "u1", outside=outside, idle=lambda: False))["replayed"] == 0
    # learning: off: nothing is replayed or changed.
    with stateless.no_learning("learning: off"):
        assert (await nawm.replay(store, "u1", outside=outside))["replayed"] == 0
    assert asked == [] and talaqqi.due(talaqqi.answers(store, "u1")[0])


NASA = Passage(
    "Titan is the largest moon of Saturn.", "Titan", "https://science.nasa.gov/titan", "web"
)
CLAIM = "The largest moon of Saturn is Titan."


async def test_a_fact_one_site_settled_gets_its_second_witness_while_resting(store, monkeypatch):
    """2:282: one site's word is shown but not given as knowledge; a second,
    independent site agreeing makes it knowledge (sahih)."""
    asked = []

    async def wikipedia(question, language, deadline=None):
        asked.append(question)
        return [WIKI]

    monkeypatch.setattr(ahl_dhikr, "nli", moons)
    monkeypatch.setattr(ahl_dhikr, "wikipedia", wikipedia)
    monkeypatch.setattr(ahl_dhikr, "order", lambda store: ["wikipedia", "web"])
    ahl_dhikr.keep(
        store, "u1", "Which moon of Saturn is largest?", [Finding(CLAIM, "supported", 0.9, NASA)]
    )
    assert ahl_dhikr.witnesses(store, "u1")[CLAIM]["grade"] == "hasan"
    report = await nawm.witness(store, "u1")
    assert report == {"sought": 1, "corroborated": 1} and asked
    entry = ahl_dhikr.witnesses(store, "u1")[CLAIM]
    assert entry["grade"] == "sahih" and entry["hosts"] == ["en.wikipedia.org", "science.nasa.gov"]


async def test_a_site_is_not_sought_as_its_own_second_witness(store, monkeypatch):
    asked = []

    async def wikipedia(question, language, deadline=None):
        asked.append(question)
        return [WIKI]

    monkeypatch.setattr(ahl_dhikr, "nli", moons)
    monkeypatch.setattr(ahl_dhikr, "wikipedia", wikipedia)
    monkeypatch.setattr(ahl_dhikr, "order", lambda store: ["wikipedia", "web"])
    ahl_dhikr.keep(
        store, "u1", "Which moon of Saturn is largest?", [Finding(CLAIM, "supported", 0.9, WIKI)]
    )
    assert (await nawm.witness(store, "u1"))["corroborated"] == 0
    assert asked == []  # Wikipedia is never asked to confirm Wikipedia
