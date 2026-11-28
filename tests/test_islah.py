"""Islah: lessons for all work, learned from the person's corrections
(ported from ForgeKit's lessons.js and cortex.js; docs/automatic-learning.md)."""

import pytest

from core.adaptive import AdaptiveStateStore
from memory import stateless
from tadbir import islah

DAY = 86400.0
T0 = 1_800_000_000.0


@pytest.fixture
def store(tmp_path):
    return AdaptiveStateStore(str(tmp_path / "learning.db"))


def answer(store, chat="c1", request="convert the recipe to metric units", **extra):
    return islah.observe(
        store,
        chat=chat,
        request=request,
        tools=extra.pop("tools", ["workspace_write"]),
        files=extra.pop("files", ["recipe.md"]),
        signals=extra.pop("signals", []),
        shown=extra.pop("shown", []),
        now=extra.pop("now", T0),
        **extra,
    )


# ── the pure core ────────────────────────────────────────────────────────


def test_one_family_never_fires_however_many_signals():
    assert islah.score(["complaint", "complaint", "complaint"])["fires"] is False
    assert islah.classify(["complaint", "complaint", "complaint"]) == "discard"
    assert islah.classify(["restored", "denied"]) == "discard"  # both are undo


def test_noisy_or_thresholds_as_lessons_js():
    weak = islah.score(["complaint", "check_fixed"])
    assert weak["fires"] and weak["p"] == pytest.approx(1 - 0.65 * 0.55, abs=1e-4)
    assert islah.classify(["complaint", "check_fixed"]) == "accumulate"  # 0.6425
    assert islah.classify(["restored", "check_fixed"]) == "distill"  # 0.725
    assert islah.classify(["check_fixed"]) == "discard"


def test_the_lifecycle_candidate_active_quarantined_retired():
    lesson = {"status": "candidate", "evidence": 0, "contradictions": 0, "confirmed": T0}
    lesson = islah.confirm(lesson, T0)
    assert lesson["status"] == "active" and lesson["evidence"] == 1
    # Validity (1 + evidence) / (2 + evidence + contradictions): 2/4, 2/5, 2/6 …
    for _ in range(3):
        lesson = islah.contradict(lesson, T0)
    assert lesson["status"] == "active"
    lesson = islah.contradict(lesson, T0)  # 2/7 < 0.3
    assert lesson["status"] == "quarantined"
    once = islah.confirm(lesson, T0)
    assert once["status"] == "quarantined"
    assert islah.confirm(once, T0)["status"] == "active"
    assert islah.contradict(lesson, T0)["status"] == "retired"


def test_an_unconfirmed_lesson_fades_with_a_45_day_half_life():
    lesson = {"evidence": 0, "contradictions": 0, "confirmed": T0}
    assert islah.confidence(lesson, T0) == pytest.approx(0.5)
    assert islah.confidence(lesson, T0 + 45 * DAY) == pytest.approx(0.25)


def test_a_correction_is_read_conservatively():
    assert islah.complaint("No, I meant Celsius not Fahrenheit")
    assert islah.complaint("That's not what I asked")
    assert islah.complaint("yeh galat hai")
    assert not islah.complaint("no thanks")
    assert not islah.complaint("What is the capital of France?")
    assert not islah.complaint("no")
    assert not islah.complaint("wrong " + "word " * 40)


# ── episodes and lessons ─────────────────────────────────────────────────


def test_two_families_distil_a_candidate_and_a_recurrence_makes_it_active(store):
    # The run itself fixed a failed check; the person then restored the project.
    answer(store, signals=["check_fixed"], workspace="p1")
    made = islah.signal(store, "restored", workspace="p1", now=T0 + 60)
    assert made["lesson"]
    (lesson,) = islah.summary(store, T0)["items"]
    assert lesson["status"] == "candidate"
    # A candidate is never shown.
    assert islah.relevant(store, "convert another recipe to metric", ["workspace_write"]) == []
    # The same mistake again, on work where the lesson was not in view: confirmed.
    answer(store, chat="c2", signals=["check_fixed"], workspace="p1", now=T0 + DAY)
    islah.signal(store, "restored", workspace="p1", now=T0 + DAY + 60)
    (lesson,) = islah.summary(store, T0 + DAY)["items"]
    assert lesson["status"] == "active" and lesson["evidence"] == 1
    shown = islah.relevant(
        store, "convert my soup recipe to metric", ["workspace_write"], now=T0 + DAY
    )
    assert [item["id"] for item in shown] == [lesson["id"]]
    assert "Lessons MIZAN learned" in islah.render(shown)


def test_a_weak_pair_needs_a_recurrence_and_keeps_the_persons_words(store):
    answer(store, signals=["check_fixed"])
    first = islah.hear(store, "c1", "No, use grams not ounces", now=T0 + 30)
    assert first == {"complaint": True, "lesson": None, "replay": ""}  # 0.64: accumulate
    answer(store, chat="c1", signals=["check_fixed"], now=T0 + 120)
    second = islah.hear(store, "c1", "No, grams please", now=T0 + 150)
    assert second["lesson"]
    (lesson,) = islah.summary(store, T0)["items"]
    assert 'the person said "No, grams please"' in lesson["corrected"]


def test_only_the_first_message_after_an_answer_is_heard(store):
    answer(store)
    assert islah.hear(store, "c1", "thanks", now=T0 + 10) == {
        "complaint": False,
        "lesson": None,
        "replay": "",
    }
    assert islah.hear(store, "c1", "No, that's wrong", now=T0 + 20) is None
    assert islah.hear(store, "other-chat", "No, that's wrong", now=T0 + 20) is None


def test_undoing_work_done_with_a_lesson_in_view_contradicts_it(store):
    lesson = {
        "id": "L1",
        "trigger": {"keywords": ["recipe"], "tools": [], "files": []},
        "corrected": "For recipe: use grams.",
        "status": "active",
        "evidence": 1,
        "contradictions": 0,
        "confirmed": T0,
        "chats": ["c0"],
    }
    store.put(islah.KEY, {"episodes": [], "lessons": [lesson]})
    answer(store, shown=["L1"], workspace="p9")
    found = islah.signal(store, "restored", workspace="p9", now=T0 + 5)
    assert found["contradicted"] == 1
    assert islah.summary(store, T0)["items"][0]["contradictions"] == 1


def test_a_stateless_run_keeps_nothing(store):
    with stateless.bind():
        answer(store, signals=["check_fixed"], workspace="p1")
        islah.signal(store, "restored", workspace="p1", now=T0 + 1)
    assert islah.summary(store, T0)["lessons"] == 0
    assert islah._load(store)["episodes"] == []


def test_mahw_erases_the_lessons_an_erased_chat_taught(store):
    answer(store, chat="secret", signals=["check_fixed"], workspace="p1")
    islah.signal(store, "restored", workspace="p1", now=T0 + 1)
    answer(store, chat="kept", request="write the poem in urdu", signals=["check_fixed"],
           workspace="p2", now=T0 + 2, tools=["web_search"], files=[])  # fmt: skip
    islah.signal(store, "restored", workspace="p2", now=T0 + 3)
    assert islah.summary(store, T0)["lessons"] == 2
    assert islah.forget_chat(store, "secret") == 1
    assert [item["chats"] for item in islah._load(store)["lessons"]] == [["kept"]]
    assert all(episode["chat"] != "secret" for episode in islah._load(store)["episodes"])
