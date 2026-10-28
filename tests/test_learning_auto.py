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
