"""Tadrib phase 2b: MIZAN's own reading of which action a message asks for,
answered only when it is sure (docs/tadrib.md, "Phase 2b")."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from tadbir.tadrib import choice  # noqa: E402

WEATHER = [
    "what is the weather today",
    "will it rain tomorrow",
    "how hot is it outside",
    "is it cold in the morning",
    "weather forecast for the weekend",
]
GREETING = [
    "hello how are you",
    "thank you so much friend",
    "good morning to you",
    "nice to meet you",
    "you are very kind",
]


def _plan(*intents: str) -> str:
    return json.dumps({"steps": [{"intent": intent} for intent in intents]})


def test_the_action_is_the_plans_intents_in_order():
    assert choice.action_of(_plan("web_search")) == "web_search"
    assert choice.action_of(_plan("web_search", "compute")) == "web_search+compute"
    assert choice.action_of("not json") is None
    assert choice.action_of(json.dumps({"steps": []})) is None
    assert choice.action_of(None) is None


def test_it_reads_the_action_it_learned_and_answers_only_when_sure():
    lessons = [(text, "use_tool") for text in WEATHER] + [(text, "converse") for text in GREETING]
    reader = choice.Choice(lessons)
    action, probability = reader.read("what is the weather tomorrow")
    assert action == "use_tool"
    assert 0.0 < probability <= 1.0
    assert reader.answer("what is the weather tomorrow") == (
        "use_tool" if probability >= choice.SURE else None
    )


def test_before_any_lesson_it_never_answers():
    reader = choice.Choice()
    assert reader.read("hello") == (None, 0.0)
    assert reader.answer("hello") is None
    reader.learn("hello there", "converse")
    assert reader.read("hello there")[0] == "converse"


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def folders(tmp_path, monkeypatch):
    from tadbir.tadrib import plans

    monkeypatch.setattr(plans, "about_the_deen", lambda message: "zakat" in message)
    before, work = tmp_path / "before", tmp_path / "work"
    before.mkdir()
    work.mkdir()
    earlier = []
    for index, text in enumerate(WEATHER * 4):
        earlier.append(
            {"source": f"w{index}", "language": "en", "text": text, "target": _plan("use_tool")}
        )
    for index, text in enumerate(GREETING * 4):
        earlier.append(
            {"source": f"g{index}", "language": "en", "text": text, "target": _plan("converse")}
        )
    earlier.append(
        {"source": "z", "language": "en", "text": "zakat on gold", "target": _plan("web_search")}
    )
    _write(before / "lessons.jsonl", earlier)
    _write(
        before / "again.jsonl",
        [
            {"source": "w0", "language": "en", "target": _plan("use_tool")},
            {"source": "g0", "language": "en", "target": _plan("compute")},
            {"source": "x", "language": "hi"},
        ],
    )
    fresh = [
        {
            "source": "f1",
            "language": "en",
            "text": "what is the weather now",
            "target": _plan("use_tool"),
        },
        {"source": "f2", "language": "en", "text": "hello my friend", "target": _plan("converse")},
        {
            "source": "f3",
            "language": "en",
            "text": "zakat on silver",
            "target": _plan("web_search"),
        },
        {
            "source": "f4",
            "language": "hi",
            "text": "kal mausam kaisa rahega",
            "target": _plan("use_tool"),
        },
    ]
    _write(work / "lessons.jsonl", fresh)
    return before, work


def test_the_teachers_bar_is_its_agreement_with_itself_on_the_action(folders):
    import tadrib_choice

    before, _work = folders
    bar = tadrib_choice.teacher_bar(before)
    assert bar["en"] == 0.5  # one of two second answers chose the same action
    assert bar["hi"] == 0.0  # no second answer with a plan
    assert bar["ur"] == 0.0


def test_the_run_reads_before_it_learns_and_never_learns_the_deen(folders):
    import tadrib_choice

    before, work = folders
    report = tadrib_choice.run(work, before)
    assert report["earlier_lessons"] == 40  # the zakat lesson is dropped
    assert report["fresh_lessons"] == 3
    assert report["sure"] == choice.SURE
    english = report["by_language"]["en"]
    assert english["n"] == 2
    assert english["agreement_all"] == 1.0
    assert report["by_language"]["hi"]["n"] == 1
    rows = [json.loads(line) for line in (work / "choice.rows.jsonl").read_text().splitlines()]
    assert [row["taught"] for row in rows] == ["use_tool", "converse", "use_tool"]
    assert json.loads((work / "choice.json").read_text()) == report
