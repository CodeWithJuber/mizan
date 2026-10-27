"""Fahm reads a message with the chat it belongs to, and acts only on a decisive reading.

From the owner's chat of 27 October 2026: while they taught MIZAN words of their
dialect, "Garbage area 👇 कुलडी 😁" was built as a website, and other lines ran
a Quran search or a reminder.
"""

import os
import sys
from copy import deepcopy

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agents.specialized import create_agent  # noqa: E402
from providers import BaseLLMProvider, ContentBlock, LLMResponse  # noqa: E402
from security.izn import IznPermission  # noqa: E402
from tadbir import fahm, qasd  # noqa: E402

# The owner teaching MIZAN their dialect, line by line (their own words).
TEACHING = [
    "Kidhar ko kaine ,  so gaya ko soogaa kya",
    "Abhi kar dunga ko bisyayte me Aabar kar dunga",
    "Nanu ka matlab taabar yaani bache",
    "Baan matlab bahan gaali",
    "Crores rupees\nकिरोड़ू रप्पे",
    "Bed Sheet\n👇\nपिलंग पोस\n😁",
    "Toilet \nसंडास\n😁",
    "आधार कार्ड\n👇\n हज़ारी कार्ड\nटायर \n👇\nटेर",
    "Mudguard\nमरघाट",
    "Garbage area\n👇\nकुलडी\n😁",
]


def chat(messages):
    history = []
    for text in messages:
        history += [{"role": "user", "content": text}, {"role": "assistant", "content": "Achha."}]
    return history


def test_the_chat_so_far_is_the_prior():
    earlier = TEACHING[:6]
    alone = qasd.prior()
    in_chat = qasd.prior(earlier=earlier)
    assert in_chat["converse"] > alone["converse"]
    assert abs(sum(in_chat.values()) - 1.0) < 1e-9
    # Without earlier messages the posterior is the model's own.
    assert qasd.posterior("Bukhari 1") == qasd.posterior("Bukhari 1", earlier=())


def test_a_dialect_lesson_never_runs_an_action():
    for index, line in enumerate(TEACHING):
        understood = fahm.understand(line, chat(TEACHING[:index]))
        assert understood.intent == "converse", line


@pytest.mark.parametrize(
    "request_text, intent",
    [("Surah Ikhlas sunao", "quran"), ("2**100 kitna hai", "compute"), ("Bukhari 1", "hadith")],
)
def test_a_clear_request_in_a_conversation_is_still_carried_out(request_text, intent):
    assert fahm.understand(request_text, chat(TEACHING)).intent == intent


def test_only_a_decisive_reading_is_acted_on(monkeypatch):
    # The likeliest single reading is a website, but not more likely than every
    # other reading together: MIZAN does not build it; Lisan may read the words.
    monkeypatch.setattr(
        qasd,
        "posterior",
        lambda message, project=False, overlay=None, earlier=(): {
            "build_project": 0.3,
            "converse": 0.25,
            "remember": 0.15,
            "recall": 0.15,
            "compute": 0.15,
        },
    )
    understood = fahm.understand("Garbage area")
    assert understood.intent == "converse"
    assert fahm.actionable(understood)


def test_many_small_readings_are_uncertainty_not_a_request(monkeypatch):
    monkeypatch.setattr(
        qasd,
        "posterior",
        lambda message, project=False, overlay=None, earlier=(): {
            "converse": 0.3,
            "hadith": 0.15,
            "compute": 0.15,
            "remember": 0.15,
            "recall": 0.15,
            "watch": 0.1,
        },
    )
    understood = fahm.understand("Mudguard मरघाट")
    assert understood.intent == "converse" and not fahm.actionable(understood)


class Scripted(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse([ContentBlock(type="text", text=self.replies.pop(0))], model="fixture")


async def test_lisan_reads_the_wording_with_the_chat_it_belongs_to(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    monkeypatch.setattr(
        qasd,
        "posterior",
        lambda message, project=False, overlay=None, earlier=(): {
            "build_project": 0.3,
            "converse": 0.25,
            "remember": 0.15,
            "recall": 0.15,
            "compute": 0.15,
        },
    )
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = Scripted(['{"steps":[{"intent":"converse"}]}', "कुलडी — yaad rakha."])
    result = await agent.execute(
        "Garbage area\n👇\nकुलडी\n😁", context={"history": chat(TEACHING[4:7])}
    )
    mapping = agent.ai_client.requests[0]["messages"][-1]["content"]
    assert "previous messages in this chat" in mapping and "पिलंग पोस" in mapping
    assert "orchestrator" not in result.get("usage", {})  # answered in words, nothing built
