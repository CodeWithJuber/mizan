"""Isnad: every claim of an answer graded by what supports it."""

from copy import deepcopy

import pytest

from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import isnad, muqabala


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
    created = create_agent("general", izn=IznPermission())
    created.ai_client = ScriptedProvider()
    names = ["web_search", "workspace_run"]
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {"type": "object"}} for n in names],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
    return created


EVIDENCE = (
    "Report A https://a.example/1 Rain fell 125 mm in the city. Roads reopened after the storm."
)


@pytest.mark.parametrize(
    "claim,grade",
    [
        ("Rain fell 125 mm in the city [1].", "hasan"),
        ("Rain fell 300 mm in the city.", "daif"),
        ("The mayor thanked the volunteers warmly.", "daif"),
        ("I checked the river gauge myself.", "mawdu"),
        ("See [4] for details on the flood.", "mawdu"),
        ("More at https://evil.example/flood today.", "mawdu"),
    ],
)
def test_each_claim_is_graded_by_its_support(claim, grade):
    (graded,) = isnad.ledger(claim, evidence=EVIDENCE, max_citation=2)
    assert graded["grade"] == grade, graded


def test_verified_support_is_sahih_and_claims_skip_code_and_notes():
    text = "Rain fell 125 mm in the city.\n\n```python\nprint(1)\n```\n\n_MIZAN ran it._\n- [Report A](https://a.example/1)"
    graded = isnad.ledger(text, evidence=EVIDENCE, verified=True)
    assert [unit["grade"] for unit in graded] == ["sahih"]
    quoted = isnad.ledger("> قُلْ هُوَ ٱللَّهُ أَحَدٌ\n> ٱللَّهُ ٱلصَّمَدُ", established=True, basis="source")
    assert len(quoted) == 1 and quoted[0]["kind"] == "quote" and quoted[0]["grade"] == "sahih"
    summary = isnad.summary(isnad.ledger("Words alone are said here. Nothing backs them up."))
    assert summary["counts"]["daif"] == 2 and summary["supported"] == 0.0
    # A lead-in introduces a list and states nothing itself.
    units = isnad.claims("Thodi detail:\n- Titan ka diameter lagbhag 5,150 km hai.")
    assert [unit["text"] for unit in units] == ["Titan ka diameter lagbhag 5,150 km hai."]


async def test_mizans_own_work_is_sahih_and_reaches_the_usage_block(agent):
    result = await agent.execute("2**100 kitna hai?")
    assert result["isnad"]["counts"]["sahih"] >= 1 and result["isnad"]["supported"] == 1.0
    assert result["usage"]["isnad"] == result["isnad"]
    assert result["isnad"]["ledger"][0]["support"] == ["MIZAN calculated it exactly"]


async def test_a_search_answer_is_graded_against_the_results(agent, monkeypatch):
    results = {
        "results": [
            {"title": "Report A", "url": "https://a.example/1", "snippet": "Rain fell 125 mm."},
            {"title": "Report B", "url": "https://b.example/2", "snippet": "Roads reopened."},
        ]
    }

    async def run(name, params):
        return results

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider(["Rain fell 125 mm [1] and roads reopened [2]."])
    result = await agent.execute("Latest weather news search karo")
    grades = [claim["grade"] for claim in result["isnad"]["ledger"]]
    assert grades and set(grades) <= {"sahih", "hasan"}


async def test_the_models_own_words_are_daif(agent):
    agent.ai_client = ScriptedProvider(["Recursion is a function that calls itself again."])
    result = await agent.execute("Explain recursion simply")
    assert result["isnad"]["counts"]["daif"] == 1 and result["isnad"]["supported"] == 0.0


async def test_debug_mode_grades_both_answers(agent):
    agent.ai_client = ScriptedProvider(["It is 1267650600228229401496703205377, I checked it."])
    run = await muqabala.compare(agent, "2**100 kitna hai?", {}, [])
    assert run["checks"]["isnad"]["mizan"]["supported"] == 1.0
    base = run["checks"]["isnad"]["base"]
    assert base["counts"]["mawdu"] == 1  # "I checked it": an action with no receipt


def test_headings_and_questions_are_not_claims():
    """Live check of 30 Oct 2026: the heading "**Who actually built it**" was
    judged as a claim and "supported" by a page's "Discover who built the Taj
    Mahal". A heading names what follows and a question asks: neither claims."""
    text = (
        "**Who actually built it**\n## Summary\n# Why does it matter?\n"
        "- **Patron:** Shah Jahan commissioned it.\n**Titan is the largest moon.**\n"
        "Why does it matter? Because it is old."
    )
    assert [unit["text"] for unit in isnad.claims(text)] == [
        "Patron: Shah Jahan commissioned it.",
        "Titan is the largest moon.",
        "Because it is old.",
    ]


def test_a_hindi_answer_is_split_at_the_danda():
    """Measured 30 Oct 2026: a teacher's Hindi answer of three sentences was one
    claim, so no source could hold most of it and nothing was ever checked."""
    text = "अमेज़न नदी दक्षिण अमेरिका में है। यह पेरू के एंडीज़ पर्वतों से निकलती है। यह अटलांटिक महासागर में गिरती है।"
    assert [unit["text"] for unit in isnad.claims(text)] == [
        "अमेज़न नदी दक्षिण अमेरिका में है।",
        "यह पेरू के एंडीज़ पर्वतों से निकलती है।",
        "यह अटलांटिक महासागर में गिरती है।",
    ]
