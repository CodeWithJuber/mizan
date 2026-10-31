"""Talaqqi: what the teacher taught once, MIZAN keeps and answers alone (2:37, 96:4-5)."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from agents.specialized import create_agent
from core.adaptive import AdaptiveStateStore
from memory import mahw, stateless
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import ahl_dhikr, talaqqi
from tadbir.ahl_dhikr import Finding, Passage

QUESTION = "What is the largest moon of Saturn?"
ANSWER = "The largest moon of Saturn is Titan."
TITAN = "Titan is the largest moon of Saturn, larger than the planet Mercury."
WIKI = Passage(TITAN, "Titan (moon)", "https://en.wikipedia.org/wiki/Titan_(moon)", "wikipedia")


async def fake_nli(pairs):
    """Entailment when premise and hypothesis name the same moon, contradiction
    when they name different ones, neither otherwise."""
    readings = []
    for premise, hypothesis in pairs:
        said = {moon for moon in ("Titan", "Rhea") if moon in premise}
        claimed = {moon for moon in ("Titan", "Rhea") if moon in hypothesis}
        if said and claimed and said == claimed:
            readings.append({"entailment": 0.97, "neutral": 0.02, "contradiction": 0.01})
        elif said and claimed:
            readings.append({"entailment": 0.01, "neutral": 0.04, "contradiction": 0.95})
        else:
            readings.append({"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05})
    return readings


@pytest.fixture
def store(tmp_path):
    return AdaptiveStateStore(str(tmp_path / "adaptive.db"))


@pytest.fixture
def sources(monkeypatch):
    asked = []

    async def wikipedia(question, language, deadline=None):
        asked.append(question)
        return [WIKI]

    monkeypatch.setattr(ahl_dhikr, "nli", fake_nli)
    monkeypatch.setattr(ahl_dhikr, "wikipedia", wikipedia)
    monkeypatch.setattr(ahl_dhikr, "order", lambda store: ["wikipedia"])
    return asked


def supported(claim=ANSWER):
    return Finding(claim, "supported", 0.97, WIKI)


# ── the store ─────────────────────────────────────────────────────────────


def test_only_what_a_source_confirmed_is_kept_and_only_when_it_answers(store):
    unknown = Finding("Its surface pressure is about 1.5 times that of Earth.", "unknown")
    mercury = supported("It is also larger than the planet Mercury by diameter")
    contradicted = Finding("The largest moon of Saturn is Rhea.", "contradicted", 0.9, WIKI)
    assert not talaqqi.keep(store, "u1", QUESTION, "en", [])
    assert not talaqqi.keep(store, "u1", QUESTION, "en", [unknown])
    # A teacher a source contradicted is not kept, even where it was right.
    assert not talaqqi.keep(store, "u1", QUESTION, "en", [supported(), contradicted])
    # Confirmed sentences that do not answer the question are not a lesson.
    assert not talaqqi.keep(store, "u1", QUESTION, "en", [mercury])
    assert talaqqi.keep(store, "u1", QUESTION, "en", [supported(), unknown, mercury], teacher="m")
    (item,) = talaqqi._load(store, "u1")
    # What no source confirmed is never repeated without the teacher (49:6).
    assert item["answer"] == (
        "The largest moon of Saturn is Titan. "
        "It is also larger than the planet Mercury by diameter."
    )
    assert item["received"] == "sama" and item["teacher"] == "m"
    assert [claim["url"].endswith("Titan_(moon)") for claim in item["claims"]] == [True, True]
    assert talaqqi._load(store, "u2") == []  # each user's own


def test_only_the_same_question_is_answered_from_it(store):
    talaqqi.keep(store, "u1", QUESTION, "en", [supported()])
    assert talaqqi.recall(store, "u1", "what is the LARGEST moon of saturn", "en")
    assert talaqqi.recall(store, "u1", QUESTION, "ur") is None  # another language
    assert talaqqi.recall(store, "u1", "What is the largest moon of Jupiter?", "en") is None
    assert talaqqi.recall(store, "u1", "Why is the largest moon of Saturn?", "en") is None
    population = supported("The population of Pakistan in 2010 was about 179 million.")
    assert talaqqi.keep(store, "u1", "Population of Pakistan in 2010", "en", [population])
    assert talaqqi.recall(store, "u1", "Population of Pakistan in 2020", "en") is None


def test_a_question_that_leans_on_the_chat_is_never_kept_or_reused():
    assert talaqqi.opens_chat(None) and talaqqi.opens_chat([])
    assert talaqqi.opens_chat([{"role": "assistant", "content": "Assalamu alaikum"}])
    assert not talaqqi.opens_chat([{"role": "user", "content": "Tell me about Apple"}])


async def test_a_fresh_answer_stands_on_its_sources_without_asking_them_again(store):
    talaqqi.keep(store, "u1", QUESTION, "en", [supported()])
    (item,) = talaqqi._load(store, "u1")

    async def outside(query):
        raise AssertionError("not due: the sources are not asked again")

    status, findings = await talaqqi.recheck(item, outside)
    assert status == "held" and findings[0].passage.title == "Titan (moon)"


def _age(store, days):
    items = talaqqi._load(store, "u1")
    then = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    for item in items:
        item["strength"]["last_review"] = then
    talaqqi._save(store, "u1", items)
    return items[0]


async def test_once_due_it_is_asked_again_and_each_confirmation_spaces_the_next(store, sources):
    talaqqi.keep(store, "u1", QUESTION, "en", [supported()])
    item = _age(store, 60)
    assert talaqqi.due(item)

    async def outside(query):
        return await ahl_dhikr.wikipedia(query, "en")

    status, findings = await talaqqi.recheck(item, outside)
    assert status == "confirmed" and len(sources) == 1  # asked once, by its words
    before = item["strength"]["stability"]
    after = talaqqi.reused(store, "u1", item, findings, confirmed=True)
    assert after["strength"]["stability"] > before and after["reused"] == 1
    assert not talaqqi.due(after)


async def test_an_answer_a_source_now_contradicts_is_not_given(store, monkeypatch):
    monkeypatch.setattr(ahl_dhikr, "nli", fake_nli)
    talaqqi.keep(store, "u1", QUESTION, "en", [supported()])
    item = _age(store, 60)
    rhea = Passage("Rhea is the largest moon of Saturn.", "Rhea", "https://x.org/rhea", "web")

    async def contradicting(query):
        return [rhea]

    assert (await talaqqi.recheck(item, contradicting))[0] == "contradicted"

    async def unreachable(query):
        raise TimeoutError

    assert (await talaqqi.recheck(item, unreachable))[0] == "unsettled"


async def test_deleting_the_chat_forgets_the_answer_it_taught(store):
    talaqqi.keep(store, "u1", QUESTION, "en", [supported()], chat="c1")
    taj = supported("Shah Jahan built the Taj Mahal in Agra.")
    talaqqi.keep(store, "u1", "Who built the Taj Mahal?", "en", [taj], chat="c2")
    assert mahw._forget_learned(store, "u1", [], chat="c1") == 1
    assert [item["chat"] for item in talaqqi._load(store, "u1")] == ["c2"]


# ── the chat ──────────────────────────────────────────────────────────────


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse([ContentBlock(type="text", text=self.replies.pop(0))], model="fixture")


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    return create_agent("general", izn=IznPermission())


async def test_the_teacher_teaches_once_and_mizan_answers_alone_after(agent, sources):
    agent.ai_client = ScriptedProvider([ANSWER])
    first = await agent.execute(QUESTION)
    assert first["result"] == ANSWER and first["usage"]["lisan"]["calls"] == 1
    assert len(talaqqi._load(agent.adaptive, "")) == 1

    agent.ai_client = teacher = ScriptedProvider([])  # asking it would fail
    again = await agent.execute(QUESTION)
    assert teacher.requests == []
    assert again["result"].startswith(ANSWER)
    assert "no language-model call" in again["result"] and "Titan (moon)" in again["result"]
    usage = again["usage"]
    assert usage["lisan"]["calls"] == 0 and usage["lisan"]["zero_call"] is True
    assert usage["talaqqi"]["checked"] == "kept sources"
    assert again["isnad"]["counts"]["hasan"] >= 1
    assert talaqqi._load(agent.adaptive, "")[0]["reused"] == 1


async def test_mid_chat_an_evaluation_or_learning_off_neither_keeps_nor_reuses(agent, sources):
    earlier = {"history": [{"role": "user", "content": "Tell me about Saturn"}]}
    agent.ai_client = ScriptedProvider([ANSWER])
    await agent.execute(QUESTION, earlier)
    assert talaqqi._load(agent.adaptive, "") == []

    with stateless.no_learning("learning: off"):
        agent.ai_client = ScriptedProvider([ANSWER])
        await agent.execute(QUESTION)
    assert talaqqi._load(agent.adaptive, "") == []

    agent.ai_client = ScriptedProvider([ANSWER])
    await agent.execute(QUESTION)  # kept now
    with stateless.bind():
        agent.ai_client = teacher = ScriptedProvider([ANSWER])
        await agent.execute(QUESTION)
    assert len(teacher.requests) == 1  # an evaluation asks the teacher, never memory
    agent.ai_client = teacher = ScriptedProvider([ANSWER])
    await agent.execute(QUESTION, earlier)
    assert len(teacher.requests) == 1  # a question leaning on the chat is asked fresh


async def test_a_question_about_the_deen_is_never_kept(agent, sources, monkeypatch):
    monkeypatch.setattr(ahl_dhikr, "religious", lambda question, answer="": True)
    agent.ai_client = ScriptedProvider([ANSWER])
    await agent.execute(QUESTION)
    assert talaqqi._load(agent.adaptive, "") == []


async def test_a_long_answer_comes_back_as_its_confirmed_sentences_only(agent, sources):
    long_answer = (
        "The largest moon of Saturn is Titan. "
        "Its surface pressure is about 1.5 times that of Earth. "
        "Titan has lakes of liquid methane near its poles."
    )
    agent.ai_client = ScriptedProvider([long_answer])
    first = await agent.execute(QUESTION)
    assert first["result"] == long_answer  # the first answer is shown whole
    agent.ai_client = ScriptedProvider([])
    again = await agent.execute(QUESTION)
    assert again["result"].startswith(ANSWER)
    assert "pressure" not in again["result"] and "lakes" not in again["result"]


async def test_an_answer_whose_claim_a_page_confirms_across_sentences_is_kept(store, monkeypatch):
    """A claim that joins what a page says in two sentences is confirmed by the
    page's sentences together (``ahl_dhikr.joint_premise``), so it is kept."""
    page = Passage(
        "The Taj Mahal is a mausoleum in Agra. It was built by the Mughal emperor Shah Jahan. "
        "He built it in memory of his wife, Mumtaz Mahal.",
        "Taj Mahal",
        "https://en.wikipedia.org/wiki/Taj_Mahal",
        "wikipedia",
    )
    claim = "The Taj Mahal was built by Shah Jahan in memory of his wife Mumtaz Mahal."

    async def entails_when_whole(pairs):
        return [
            {"entailment": 0.95, "neutral": 0.04, "contradiction": 0.01}
            if "Shah Jahan" in premise and "Mumtaz Mahal" in premise
            else {"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05}
            for premise, _ in pairs
        ]

    monkeypatch.setattr(ahl_dhikr, "nli", entails_when_whole)
    findings = await ahl_dhikr.judge([claim], ahl_dhikr.sentences([page]))
    assert talaqqi.keep(store, "u1", "Who built the Taj Mahal?", "en", findings, teacher="t")
    kept = talaqqi.recall(store, "u1", "Who built the Taj Mahal?", "en")
    assert kept is not None and kept["answer"] == claim + ("" if claim.endswith(".") else ".")


def test_a_confirmed_claim_that_does_not_name_its_subject_is_not_kept(store):
    """ "It is one of her most famous novels" was read with what it refers to
    (``ahl_dhikr.contexts``); kept apart from its answer it says nothing."""
    page = Passage(
        "Pride and Prejudice is a novel by Jane Austen. It is one of the most famous novels.",
        "Pride and Prejudice",
        "https://en.wikipedia.org/wiki/Pride_and_Prejudice",
        "wikipedia",
    )
    findings = [
        Finding("Pride and Prejudice was written by Jane Austen.", "supported", 0.9, page),
        Finding("It is one of her most famous novels.", "supported", 0.9, page, "pride prejudice"),
    ]
    assert talaqqi.lesson(findings) == "Pride and Prejudice was written by Jane Austen."
    assert talaqqi.keep(store, "u1", "Who wrote Pride and Prejudice?", "en", findings)
    (kept,) = talaqqi.answers(store, "u1")
    assert [claim["claim"] for claim in kept["claims"]] == [findings[0].claim]
