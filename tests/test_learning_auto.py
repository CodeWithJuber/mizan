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
REQUEST = "Ek python program likho jo 1 se 10 tak ka sum print kare aur run karo"


async def test_a_verified_program_is_kept_and_reused_without_the_model(agent, monkeypatch, alice):
    outputs = ["55\n", "55\n"]
    calls = []

    async def run(name, params):
        calls.append(params["command"])
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([PROGRAM])
    first = await agent.execute(REQUEST)
    assert first["task_verified"] and len(agent.ai_client.requests) == 1
    assert hifz.summary(agent.adaptive, "alice")["programs"] == 1
    second = await agent.execute(REQUEST)
    assert second["task_verified"]
    assert len(agent.ai_client.requests) == 1  # no new model call
    assert calls[0] == calls[1] and "Hifz" not in second["result"]
    assert hifz.summary(agent.adaptive, "alice")["items"][0]["runs"] == 2
    # Different numbers are a different program.
    assert hifz.recall(agent.adaptive, "alice", REQUEST.replace("10", "20"), "python") is None
    assert hifz.recall(agent.adaptive, "bob", REQUEST, "python") is None


async def test_a_kept_program_whose_output_changes_is_not_trusted(agent, monkeypatch, alice):
    outputs = ["55\n", "56\n", "55\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([PROGRAM, PROGRAM])
    await agent.execute(REQUEST)
    again = await agent.execute(REQUEST)
    # The reused program printed something else: Lisan wrote the program again.
    assert len(agent.ai_client.requests) == 2 and again["task_verified"]


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
    assert len(await memory.get_messages("s2", limit=10)) == 1  # bob opted out
    assert await muhasaba.run(memory) == {"reviewed": 0, "corrected": 0}  # reviewed once
