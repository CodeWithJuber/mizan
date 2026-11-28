"""Tawbah loop detection: the same failure three times is a loop, not progress.

Within one run each failed tool call is normalised into a signature (the tool, the
error's class, its message with numbers, paths and ids taken out). The third identical
signature stops that path: the model is told it failed three times the same way and must
change approach, a diagnosis is recorded, and where Wazn routes the run's model, the
rest of the run goes one tier stronger.
"""

from unittest.mock import MagicMock

from agents.specialized import create_agent
from core.tawbah import THRASH_K, TawbahLoop, error_class, failure_signature, normalize_error
from providers import BaseLLMProvider, ContentBlock, LLMResponse


def test_volatile_parts_are_normalised():
    one = normalize_error(
        'File "/home/a/proj/src/app.py", line 12, in run\n'
        "KeyError: 'user' at 0x7f3a2b1c (id 3f2a9b1c-4d5e-4f60-8a7b-9c0d1e2f3a4b) after 1532 ms"
    )
    two = normalize_error(
        'File "/tmp/run-77/src/app.py", line 48, in run\n'
        "KeyError: 'user' at 0x55aa11 (id 0b1c2d3e-0000-4f60-8a7b-123456789abc) after 9 ms"
    )
    assert one == two
    assert "app.py" in one and "/home/a" not in one


def test_the_signature_is_tool_class_and_message():
    first = {"error": "ModuleNotFoundError: No module named 'requests'", "exit_code": 1}
    again = {"error": "ModuleNotFoundError: No module named 'requests'", "exit_code": 1}
    other = {"error": "ModuleNotFoundError: No module named 'flask'", "exit_code": 1}
    assert failure_signature("bash", first) == failure_signature("bash", again)
    assert failure_signature("bash", first) != failure_signature("workspace_run", first)
    assert failure_signature("bash", first) != failure_signature("bash", other)
    assert failure_signature("bash", {"ok": True}) is None  # not a failure
    assert error_class(first["error"]) == "ModuleNotFoundError"
    assert error_class("connection timed out") == "timeout"
    # A run's stderr says why when there is no error field.
    ran = {"stdout": "", "stderr": "Traceback ...\nValueError: bad input 42\n", "exit_code": 1}
    assert error_class(ran["stderr"]) == "ValueError"
    assert failure_signature("workspace_run", ran) is not None


def test_the_third_identical_failure_stops_that_path():
    loop = TawbahLoop()
    failed = {"error": "Permission denied: /etc/shadow"}
    assert loop.observe("bash", failed) is None
    assert loop.observe("bash", {"ok": True}) is None  # a success in between changes nothing
    assert loop.observe("bash", failed) is None
    diagnosis = loop.observe("bash", failed)
    assert diagnosis is not None and diagnosis["count"] == THRASH_K == 3
    assert diagnosis["tool"] == "bash" and diagnosis["first"] is True
    later = loop.observe("bash", failed)
    assert later is not None and later["count"] == 4 and later["first"] is False
    assert len(loop.diagnoses) == 1
    assert loop.observe("bash", {"error": "No such file: x.txt"}) is None  # another path


def test_the_stop_note_keeps_the_error_and_says_change_approach():
    loop = TawbahLoop()
    failed = {"error": "SyntaxError: invalid syntax (line 3)"}
    for _ in range(2):
        loop.observe("python_exec", failed)
    diagnosis = loop.observe("python_exec", failed)
    noted = loop.stop_note(failed, diagnosis)
    assert noted["error"] == failed["error"]
    assert "3 times" in noted["tawbah"] and "change approach" in noted["tawbah"].lower()


# ── In the agent's loop ────────────────────────────────────────────────────


class Scripted(BaseLLMProvider):
    provider_name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.models: list[str] = []
        self.seen: list[list] = []

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.models.append(model)
        self.seen.append(messages)
        return self.script.pop(0)


def call(n):
    return LLMResponse(
        content=[ContentBlock(type="tool_use", id=f"c{n}", name="bash", input={"command": "make"})],
        stop_reason="tool_use",
    )


def text(value):
    return LLMResponse(content=[ContentBlock(type="text", text=value)], stop_reason="end_turn")


def agent_with(script, model="cheap-model"):
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Tawbah", wali=MagicMock(), izn=izn)
    agent.ai_model = model
    agent.ai_client = Scripted(script)
    return agent


async def run(agent):
    failures = []

    async def failing(name, params):
        failures.append(name)
        return {
            "stdout": "",
            "stderr": "make: *** No rule to make target 'all'.  Stop.\n",
            "exit_code": 2,
        }

    agent._execute_tool_safe = failing
    schemas = [{"name": "bash", "description": "d", "input_schema": {"type": "object"}}]
    chunks = [
        chunk
        async for chunk in agent._agentic_loop(
            "sys", [{"role": "user", "content": "build it"}], schemas, False, "build it"
        )
    ]
    return chunks, failures


def tool_results(messages):
    found = []
    for message in messages:
        if message["role"] == "user" and isinstance(message["content"], list):
            found += [
                part["content"] for part in message["content"] if part.get("type") == "tool_result"
            ]
    return found


async def test_the_loop_tells_the_model_to_change_approach_and_records_why(monkeypatch):
    monkeypatch.delenv("MIZAN_LISAN_MODELS", raising=False)
    agent = agent_with([call(1), call(2), call(3), text("I could not build it: no Makefile.")])
    agent._tawbah_loops = []
    _chunks, failures = await run(agent)
    assert failures == ["bash"] * 3
    results = tool_results(agent.ai_client.seen[-1])
    assert len(results) == 3
    assert "tawbah" not in results[0] and "tawbah" not in results[1]
    assert "3 times" in results[2] and "change approach" in results[2].lower()
    (diagnosis,) = agent._tawbah_loops
    assert diagnosis["tool"] == "bash" and diagnosis["count"] == 3
    assert any(r.error_type == "repeated_failure" for r in agent.tawbah._records.values())
    assert set(agent.ai_client.models) == {"cheap-model"}  # no Wazn list: same model


async def test_wazn_moves_the_rest_of_the_run_one_tier_stronger(monkeypatch):
    monkeypatch.setenv("MIZAN_LISAN_MODELS", "cheap-model,strong-model,strongest-model")
    agent = agent_with([call(1), call(2), call(3), text("Stopped.")])
    agent._tawbah_loops = []
    await run(agent)
    assert agent.ai_client.models == ["cheap-model"] * 3 + ["strong-model"]
    assert agent._tawbah_loops[0]["escalated_to"] == "strong-model"


def test_wazn_names_the_next_stronger_model(monkeypatch):
    from tadbir import wazn

    monkeypatch.setenv("MIZAN_LISAN_MODELS", "a,b,c")
    assert wazn.stronger("a") == "b" and wazn.stronger("b") == "c"
    assert wazn.stronger("c") is None  # already the strongest
    assert wazn.stronger("not-listed") is None  # Wazn does not route this model
    monkeypatch.setenv("MIZAN_LISAN_MODELS", "")
    assert wazn.stronger("a") is None
