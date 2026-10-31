"""Tadrib phase 2: the teacher's licence, the lesson, the check, the e-process
and the student (docs/tadrib.md)."""

from __future__ import annotations

import ast
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core.adaptive import BettingEProcess  # noqa: E402
from tadbir.tadrib import licence  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# ── the teacher's licence ────────────────────────────────────────────────


def _assigned(path: Path, name: str):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


def test_the_licence_rules_are_mizan_replys():
    data = ROOT / "mizan_reply" / "data.py"
    assert set(licence.TEACHER_LICENCES) == _assigned(data, "TEACHER_LICENCES")
    assert set(licence.FORBIDDEN_TEACHERS) == _assigned(data, "FORBIDDEN_TEACHERS")


@pytest.mark.parametrize(
    "model, allowed",
    [
        ("deepseek/deepseek-chat-v3-0324", True),
        ("anthropic/claude-opus-5-5", False),
        ("claude-opus-5-5", False),
        ("openai/gpt-5", False),
        ("gpt-5", False),
        ("deepseek/deepseek-r1-distill-llama-70b", False),
        ("some/unknown-model", False),
        ("", False),
    ],
)
def test_only_a_licensed_teacher_teaches(model, allowed):
    assert licence.allowed(model) is allowed


# ── the lesson and the check ─────────────────────────────────────────────


@pytest.fixture
def no_deen(monkeypatch):
    from tadbir.tadrib import student

    monkeypatch.setattr(student, "about_the_deen", lambda message: False)
    return student


def test_a_lone_converse_is_a_lesson_and_scripture_never_is(no_deen):
    student = no_deen
    assert (
        student.target([{"intent": "converse", "text": "hi"}], "hi there", "en")
        == '{"steps":[{"intent":"converse"}]}'
    )
    quran = [{"intent": "quran", "surah": 1, "ayah_start": 1, "ayah_end": 1}]
    assert student.target(quran, "surah 1 ayah 1", "en") is None
    mixed = [{"intent": "converse"}, {"intent": "compute", "expression": "2+3"}]
    assert student.target(mixed, "hi, what is 2+3", "en") is None


def test_a_step_mizan_refuses_makes_no_lesson(no_deen):
    student = no_deen
    # a bare number is no calculation
    assert student.target([{"intent": "compute", "expression": "7"}], "seven", "en") is None
    # a link the user never wrote
    step = {"intent": "web_read", "url": "https://example.com/x"}
    assert student.target([step], "read that page for me", "en") is None


def test_a_lesson_keeps_only_the_schemas_fields(no_deen):
    student = no_deen
    message = "what is 12 times 7"
    step = {"intent": "compute", "expression": "12*7", "text": message, "extra": "x"}
    assert json.loads(student.target([step], message, "en")) == {
        "steps": [{"intent": "compute", "expression": "12*7"}]
    }


def test_agreement_is_the_same_actions_with_the_same_values(no_deen):
    student = no_deen
    message = "what is 12 times 7"
    taught = '{"steps":[{"intent":"compute","expression":"12*7"}]}'
    assert student.agree(
        '{"steps":[{"intent":"compute","expression":"7 * 12"}]}', taught, message, "en"
    )
    assert not student.agree(
        '{"steps":[{"intent":"compute","expression":"12*8"}]}', taught, message, "en"
    )
    assert not student.agree('{"steps":[{"intent":"converse"}]}', taught, message, "en")
    assert not student.agree('{"steps":[{"intent":"compute"', taught, message, "en")
    assert not student.agree(None, taught, message, "en")
    assert student.same('{"steps":[{"intent":"compute","expression":"12*7"}]}', taught)


# ── the e-process ────────────────────────────────────────────────────────


def test_the_e_process_stays_small_when_the_rate_is_p0_and_grows_above_it():
    rng = random.Random(0)
    crossed = 0
    for _ in range(300):
        test = BettingEProcess(0.8)
        for _ in range(600):
            test.update(1.0 if rng.random() < 0.8 else 0.0)
            assert test.value > 0
            if test.value >= 20:
                crossed += 1
                break
    assert crossed / 300 <= 0.1  # Ville: at most 5%, with room for sampling error
    better = BettingEProcess(0.8)
    for _ in range(600):
        better.update(1.0 if rng.random() < 0.97 else 0.0)
    assert better.value >= 20


def test_the_e_process_does_not_bet_before_the_student_is_good():
    test = BettingEProcess(0.9)
    for _ in range(200):
        test.update(0.0)
    assert test.value == pytest.approx(1.0)


# ── the student (needs torch) ────────────────────────────────────────────


@pytest.fixture
def tiny():
    pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    return net.Reader(net.Config(d_model=32, layers=1, heads=2, d_ff=64, context=64, dropout=0.0))


LESSONS = [
    ("what is 12 times 7", '{"steps":[{"intent":"compute","expression":"12*7"}]}'),
    ("hello, how are you", '{"steps":[{"intent":"converse"}]}'),
    ("search the news about rain", '{"steps":[{"intent":"web_search","query":"rain news"}]}'),
]


def test_the_student_learns_only_the_answer_and_rebuilds_bit_for_bit(tiny):
    from tadbir.tadrib import student

    setting = student.Setting(steps=1, lr=1e-2, replay=2, micro=2)
    items = [(m, a, student.digest_of(m)) for m, a in LESSONS]
    first = student.Student(tiny, setting)
    for item in items:
        first.learn(*item)
    again = student.Student(tiny, setting)
    again.rebuild(items)
    assert student.same_weights(first.model, again.model)
    # forgetting the second lesson equals never having learned it
    never = student.Student(tiny, setting)
    for item in (items[0], items[2]):
        never.learn(*item)
    first.rebuild([items[0], items[2]])
    assert student.same_weights(first.model, never.model)


def test_the_answers_mask_covers_only_the_answer():
    pytest.importorskip("torch")
    from tadbir.tadrib import student

    tokens, start = student.encode("hi", '{"a":1}')
    _inputs, labels, mask = student._batch([(tokens, start)])
    learned = labels[0][mask[0]].tolist()
    assert learned == [*b'{"a":1}', student.net.END]


def test_the_student_memorises_a_lesson():
    pytest.importorskip("torch")
    from tadbir.ruh_reader import net
    from tadbir.tadrib import student

    base = net.Reader(net.Config(d_model=64, layers=2, heads=2, d_ff=128, context=64, dropout=0.0))
    learner = student.Student(base, student.Setting(steps=4, lr=1e-2, replay=0, micro=1))
    message, answer = LESSONS[1]
    for round_ in range(80):
        learner.learn(message, answer, student.digest_of(f"{message}{round_}"))
    said, mean_logp = learner.answer(message)
    assert said == answer and mean_logp > -1.0


# ── Lisan keeps the exchange ─────────────────────────────────────────────


async def test_lisan_keeps_each_tasks_last_exchange():
    from tadbir.lisan import Lisan

    reply = '{"steps":[{"intent":"converse"}]}'

    class Provider:
        provider_name = "test"

        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=reply)],
                stop_reason="end_turn",
                model="deepseek/deepseek-chat-v3-0324",
                usage={"input": 10, "output": 5},
            )

    agent = SimpleNamespace(
        ai_client=Provider(),
        ai_model="deepseek/deepseek-chat-v3-0324",
        _record_llm_call=lambda response, latency: None,
        _add_execution_time=lambda key, started: 0.0,
    )
    lisan = Lisan(agent)
    steps = await lisan.plan_steps("hello there")
    assert steps == [{"intent": "converse"}]
    kept = lisan.exchange["plan_steps"]
    assert kept["reply"] == reply and kept["user"] == "hello there"
    assert kept["model"] == "deepseek/deepseek-chat-v3-0324"
