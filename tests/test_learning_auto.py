"""Automatic learning: Hifz (kept programs, re-checked on reuse) and Muhasaba (self-review)."""

from copy import deepcopy

import pytest

from agents.specialized import create_agent
from memory.dhikr import DhikrMemorySystem
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from security.izn import IznPermission
from tadbir import hifz, muhasaba, quran


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
    created = create_agent(
        "general", izn=IznPermission(), memory=DhikrMemorySystem(str(tmp_path / "a.db"))
    )
    created.ai_client = ScriptedProvider()
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": "workspace_run", "description": "", "input_schema": {"type": "object"}}],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
    return created


@pytest.fixture
def alice():
    token = bind_principal(TokenPayload("alice", "alice", ["user"], 9999999999, 0, "t"))
    yield "alice"
    reset_principal(token)


PROGRAM = "```python\nprint(sum(range(1, 11)))\n```"
CHECK = "```python\nprint(10 * 11 // 2)\n```"  # the same result by another method
REQUEST = "Ek python program likho jo 1 se 10 tak ka sum print kare aur run karo"


async def test_a_verified_program_is_kept_and_reused_without_the_model(agent, monkeypatch, alice):
    outputs = ["55\n", "55\n", "55\n"]  # the program, its independent check, the reuse
    calls = []

    async def run(name, params):
        calls.append(params["command"])
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([PROGRAM, CHECK])
    first = await agent.execute(REQUEST)
    assert first["task_verified"] and len(agent.ai_client.requests) == 2
    assert hifz.summary(agent.adaptive, "alice")["programs"] == 1
    second = await agent.execute(REQUEST)
    assert second["task_verified"]
    assert len(agent.ai_client.requests) == 2  # no new model call: it was checked when kept
    assert calls[0] == calls[2] and "Hifz" not in second["result"]
    assert hifz.summary(agent.adaptive, "alice")["items"][0]["runs"] == 2
    # Different numbers are a different program.
    assert hifz.recall(agent.adaptive, "alice", REQUEST.replace("10", "20"), "python") is None
    assert hifz.recall(agent.adaptive, "bob", REQUEST, "python") is None


async def test_a_kept_program_whose_output_changes_is_not_trusted(agent, monkeypatch, alice):
    outputs = ["55\n", "55\n", "56\n", "55\n", "55\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([PROGRAM, CHECK, PROGRAM, CHECK])
    await agent.execute(REQUEST)
    again = await agent.execute(REQUEST)
    # The reused program printed something else: Lisan wrote the program again.
    assert len(agent.ai_client.requests) == 4 and again["task_verified"]


FIB30 = (
    "Write and run a Python program that prints the 30th Fibonacci number, where F1 = 1 and F2 = 1."
)
F29 = "```python\na, b = 0, 1\nfor _ in range(29):\n    a, b = b, a + b\nprint(a)\n```"
F30 = "```python\na, b = 0, 1\nfor _ in range(30):\n    a, b = b, a + b\nprint(a)\n```"


async def test_a_program_that_answers_another_question_is_caught_and_repaired(
    agent, monkeypatch, alice
):
    # The 27 October benchmark: F29 printed for F30, run cleanly, kept as verified.
    outputs = ["514229\n", "832040\n", "832040\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([F29, F30, F30])
    result = await agent.execute(FIB30)
    assert result["task_verified"] and "832040" in result["result"]
    assert "514229" not in result["result"]
    # The repair was told what the independent program printed.
    assert "832040" in agent.ai_client.requests[2]["messages"][0]["content"]
    kept = hifz.recall(agent.adaptive, "alice", FIB30, "python")
    assert kept and "range(30)" in kept["code"] and kept["checked"] is True


async def test_two_derivations_that_still_disagree_are_not_verified(agent, monkeypatch, alice):
    outputs = ["514229\n", "832040\n", "514229\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([F29, F30, F29])
    result = await agent.execute(FIB30)
    assert result["task_verified"] is False and "832040" in result["result"]
    assert hifz.summary(agent.adaptive, "alice")["programs"] == 0


async def test_a_result_the_second_program_could_not_check_is_not_verified(
    agent, monkeypatch, alice
):
    # Production, 28 October: the independent program failed, and F29 was shown as
    # if verified. A check that could not run proves nothing.
    outputs = [
        {"stdout": "514229\n", "stderr": "", "exit_code": 0},
        {"stdout": "", "stderr": "SyntaxError", "exit_code": 1},
    ]

    async def run(name, params):
        return outputs.pop(0)

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([F29, "```python\nprint(\n```"])
    result = await agent.execute(FIB30)
    assert result["task_verified"] is False
    assert "could not be run" in result["result"]
    assert hifz.summary(agent.adaptive, "alice")["programs"] == 0


async def test_a_program_kept_before_the_check_is_dropped_when_it_disagrees(
    agent, monkeypatch, alice
):
    hifz.keep(agent.adaptive, "alice", FIB30, "python", "print(514229)", "514229\n")
    outputs = ["514229\n", "832040\n", "832040\n", "832040\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([F30, F30, F30])
    result = await agent.execute(FIB30)
    assert result["task_verified"] and "832040" in result["result"]
    kept = hifz.recall(agent.adaptive, "alice", FIB30, "python")
    assert kept and kept["checked"] is True and "514229" not in kept["output"]


def test_muhasaba_recomputes_arithmetic():
    findings = muhasaba.arithmetic(
        "So 2**10 = 1000, and 3 + 4 = 7. Also 25! = 15511210043330985984000000."
    )
    assert findings == [
        {"kind": "arithmetic", "expression": "2**10", "claimed": "1000", "correct": "1024"}
    ]
    assert muhasaba.arithmetic("1/3 = 0.33 roughly, and 2024-03-01 = Friday") == []


async def test_muhasaba_corrects_a_misquote_once_and_respects_opt_out(tmp_path, monkeypatch):
    async def fetch(reference, language):
        return {"reference": "Surah Al-Ikhlas 112:1", "ayahs": [{"arabic": "قُلْ هُوَ ٱللَّهُ أَحَدٌ"}]}

    monkeypatch.setattr(quran, "fetch", fetch)
    memory = DhikrMemorySystem(str(tmp_path / "chat.db"))
    await memory.authorize_session("s1", "alice", create=True)
    await memory.authorize_session("s2", "bob", create=True)
    wrong = "Surah Ikhlas 112:1 is: قل هو رب العالمين الكريم"
    await memory.save_message("s1", "user", "Surah Ikhlas ki pehli ayat batao")
    await memory.save_message("s1", "assistant", wrong, metadata={"status": "complete"})
    await memory.save_message(
        "s1", "assistant", "2+2 = 5", metadata={"usage": {"orchestrator": "mizan"}}
    )
    await memory.save_message("s2", "assistant", wrong, metadata={"status": "complete"})
    await memory.set_chat_preference("bob", "muhasaba", "off")
    found = await muhasaba.run(memory)
    assert found == {"reviewed": 3, "corrected": 1}
    messages = await memory.get_messages("s1", limit=10)
    correction = messages[-1]
    assert correction["metadata"]["muhasaba"] and "قُلْ هُوَ ٱللَّهُ أَحَدٌ" in correction["content"]
    assert "MIZAN ne" in correction["content"]  # in the language the user asked in
    assert len(await memory.get_messages("s2", limit=10)) == 1  # bob opted out
    assert await muhasaba.run(memory) == {"reviewed": 0, "corrected": 0}  # reviewed once


def summing(n: int) -> str:
    return f"```python\nn = {n}\nprint(sum(range(1, n + 1)))\n```"


def checking(n: int) -> str:
    return f"```python\nprint({n} * ({n} + 1) // 2)\n```"


async def test_programs_verified_for_two_numbers_answer_a_third_without_the_model(
    agent, monkeypatch, alice
):
    """Hifz templates: the programs for "1 se 10" and "1 se 20" differ only where
    the requests' numbers differ, so "1 se 30" is answered by putting 30 in."""
    outputs = ["55\n", "55\n", "210\n", "210\n", "465\n"]
    calls = []

    async def run(name, params):
        calls.append(params["command"])
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([summing(10), checking(10), summing(20), checking(20)])
    for n in (10, 20):
        assert (await agent.execute(REQUEST.replace("10", str(n))))["task_verified"]
    assert len(agent.ai_client.requests) == 4
    third = await agent.execute(REQUEST.replace("10", "30"))
    assert len(agent.ai_client.requests) == 4  # no model call
    assert "n = 30" in calls[-1] and "465" in third["result"]
    # Observed, not independently checked, and the answer says so.
    assert not third["task_verified"] and "kisi alag program ne check nahi kiya" in third["result"]


def keep(store, request, code, output, checked=True):
    hifz.keep(store, "u", request, "python", code, output, checked=checked)


def test_a_template_reproduces_every_program_it_comes_from(tmp_path):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))

    def fibonacci(n):
        return f"a, b = 0, 1\nfor _ in range({n}):\n    a, b = b, a + b\nprint(f'F{n} =', a)\n"

    keep(store, "Print the 10th Fibonacci number", fibonacci(10), "F10 = 55\n")
    assert hifz.template(store, "u", "Print the 7th Fibonacci number", "python") is None  # one
    keep(store, "Print the 20th Fibonacci number", fibonacci(20), "F20 = 6765\n")
    made = hifz.template(store, "u", "Print the 7th Fibonacci number", "python")
    assert made["instances"] == 2 and "range(7)" in made["code"] and "F7 =" in made["code"]
    # Other words, another kind of number, another language: no template.
    assert hifz.template(store, "u", "Print the 7th prime number", "python") is None
    assert hifz.template(store, "u", "Print the 7.5th Fibonacci number", "python") is None
    assert hifz.template(store, "u", "Print the 7th Fibonacci number", "javascript") is None
    assert hifz.template(store, "bob", "Print the 7th Fibonacci number", "python") is None


def test_a_template_is_general_only_where_it_was_seen_to_vary(tmp_path):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))
    for exponent in (10, 20):
        keep(store, f"What is 2 to the power {exponent}", f"print(2 ** {exponent})", "1\n")
    assert "2 ** 5" in hifz.template(store, "u", "What is 2 to the power 5", "python")["code"]
    # The base was 2 in every program: a new base may be a literal there.
    assert hifz.template(store, "u", "What is 3 to the power 5", "python") is None


def test_a_template_needs_programs_an_independent_program_agreed_with(tmp_path):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))
    for n in (10, 20):
        keep(store, f"Sum 1 to {n}", f"n = {n}\nprint(sum(range(1, n + 1)))", "55\n", checked=False)
    assert hifz.template(store, "u", "Sum 1 to 30", "python") is None
    # Programs that differ where the requests' numbers do not explain it: none.
    store = AdaptiveStateStore(str(tmp_path / "b.db"))
    keep(store, "Sum 1 to 10", "print(55)", "55\n")
    keep(store, "Sum 1 to 20", "print(210)", "210\n")
    assert hifz.template(store, "u", "Sum 1 to 30", "python") is None


def test_a_template_slot_may_be_a_number_plus_an_offset_the_instances_agree_on(tmp_path):
    """Live, 30 Oct: the teacher wrote ``sum(range(1, 11))`` for "1 se 10".
    The offset is one parameter both instances measure, so they test it."""
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))
    keep(store, "Sum 1 to 10", "print(sum(range(1, 11)))", "55\n")
    keep(store, "Sum 1 to 20", "print(sum(range(1, 21)))", "210\n")
    assert "range(1, 31)" in hifz.template(store, "u", "Sum 1 to 30", "python")["code"]
    # Offsets that disagree (11 for 10, 22 for 20) are no slot.
    store = AdaptiveStateStore(str(tmp_path / "b.db"))
    keep(store, "Sum 1 to 10", "print(sum(range(1, 11)))", "55\n")
    keep(store, "Sum 1 to 20", "print(sum(range(1, 22)))", "231\n")
    assert hifz.template(store, "u", "Sum 1 to 30", "python") is None


async def test_lisan_sees_the_nearest_verified_programs_and_the_check_does_not(
    agent, monkeypatch, alice
):
    """Memento's case memory: a known form is written in its known shape; the
    independent program (Tathabbut) is written without seeing any of it."""
    outputs = ["55\n", "55\n", "210\n", "210\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([summing(10), checking(10), summing(20), checking(20)])
    await agent.execute(REQUEST)
    await agent.execute(REQUEST.replace("10", "20"))
    write, check = agent.ai_client.requests[2], agent.ai_client.requests[3]
    assert "n = 10" in str(write["messages"]) and "Programs MIZAN verified" in str(
        write["messages"]
    )
    assert "n = 10" not in str(check["messages"])
    # Another user sees none of them.
    assert hifz.cases(agent.adaptive, "bob", REQUEST, "python") == []
