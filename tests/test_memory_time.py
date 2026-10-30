"""What is said later about the same thing stands above what was said before,
which stays written (13:39): recall dates statements of one thing, latest first."""

import time

import pytest

from memory.dhikr import DhikrMemorySystem, same_frame
from reasoning.context_manager import ContextManager


@pytest.mark.parametrize(
    ("first", "second", "one_thing"),
    [
        ("My city is Delhi.", "My city is Mumbai.", True),
        ("Mera sheher Delhi hai", "Mera sheher ab Mumbai hai", True),
        ("Meri umar 30 saal hai", "Meri umar 31 saal hai", True),
        ("I like tea.", "I like coffee.", False),  # "like" names nothing
        ("My city is Delhi.", "My city is Delhi.", False),  # the same words: a repetition
        ("Titan has a thick atmosphere.", "Rome is the capital of Italy.", False),
    ],
)
def test_statements_of_one_thing_are_told_by_their_shared_frame(first, second, one_thing):
    assert same_frame(first, second) is one_thing


async def test_the_later_statement_is_recalled_first_and_the_earlier_stays(tmp_path):
    memory = DhikrMemorySystem(db_path=str(tmp_path / "dhikr.db"))
    await memory.remember("My city is Delhi.", importance=0.9)
    time.sleep(1.05)  # a later second
    await memory.remember("My city is Mumbai.", importance=0.3)
    await memory.remember("I like tea.", importance=0.5)
    found = await memory.recall("city Delhi", limit=1)
    assert [item.content for item in found] == ["My city is Mumbai.", "My city is Delhi."]
    assert all(item.dated for item in found) and found[0].said > found[1].said
    alone = await memory.recall("tea", limit=3)
    assert [(item.content, item.dated) for item in alone] == [("I like tea.", False)]


def test_dated_memories_reach_the_prompt_with_their_dates():
    messages = ContextManager().inject_memory(
        [{"role": "user", "content": "Where do I live?"}],
        [
            {"type": "episodic", "content": "My city is Mumbai.", "said": "2026-10-30"},
            {"type": "episodic", "content": "My city is Delhi.", "said": "2026-01-03"},
        ],
    )
    shown = messages[0]["content"]
    assert "(said 2026-10-30) My city is Mumbai." in shown
    assert shown.index("Mumbai") < shown.index("Delhi")
