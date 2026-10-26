"""Unlimited conversations: budgeted history, rolling summaries and loop recovery."""

import json
from unittest.mock import AsyncMock, MagicMock

from agents.base import bounded_tool_result
from agents.specialized import create_agent
from memory.dhikr import DhikrMemorySystem
from providers import BaseLLMProvider, ContentBlock, IncompleteToolCall, LLMResponse
from reasoning.context_engine import (
    SUMMARY_HEADER,
    ContextBudget,
    ContextEngine,
    estimate_tokens,
    message_tokens,
)


class FakeProvider(BaseLLMProvider):
    provider_name = "fake"

    def __init__(self, responses):
        self._responses = list(responses)
        self.create_calls = 0

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.create_calls += 1
        return self._responses.pop(0)


def make_test_agent():
    wali = MagicMock()
    izn = MagicMock()
    izn.check_permission.return_value = {
        "allowed": True,
        "reason": "Test",
        "requires_approval": False,
    }
    agent = create_agent("general", name="ContextAgent", wali=wali, izn=izn)
    agent.ai_model = "fake-model"
    return agent


def text_resp(text, stop="end_turn"):
    return LLMResponse(content=[ContentBlock(type="text", text=text)], stop_reason=stop, model="m")


async def collect(agen):
    return [chunk async for chunk in agen]


async def long_session(tmp_path, turns=300):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    for index in range(turns):
        role = "user" if index % 2 == 0 else "assistant"
        await memory.save_message("long", role, f"turn {index}: " + "details " * 40)
    return memory


class RecordingSummarizer:
    def __init__(self):
        self.calls = []

    async def __call__(self, system, prompt, max_tokens):
        self.calls.append(prompt)
        return f"summary after {len(self.calls)} chunk(s); last chunk {len(prompt)} chars"


async def test_long_session_fits_budget_with_persisted_summary(tmp_path):
    memory = await long_session(tmp_path)
    summarizer = RecordingSummarizer()
    window = 8_192
    history = await ContextEngine(memory).history_for("long", window, summarizer)

    budget = ContextBudget.for_window(window)
    assert sum(message_tokens(m) for m in history) <= budget.history_tokens + 64
    assert history[0]["content"].startswith(SUMMARY_HEADER)
    assert "turn 299" in history[-1]["content"]
    assert summarizer.calls, "older turns must be folded by the base model"
    record = await memory.get_session_summary("long")
    assert record["method"] == "model"
    assert record["covered_count"] > 0

    # Hysteresis: one more turn does not trigger another summary call.
    await memory.save_message("long", "user", "one more question")
    calls = len(summarizer.calls)
    again = await ContextEngine(memory).history_for("long", window, summarizer)
    assert len(summarizer.calls) == calls
    assert again[-1]["content"] == "one more question"


async def test_summary_falls_back_to_digest_without_a_model(tmp_path):
    memory = await long_session(tmp_path, turns=120)
    history = await ContextEngine(memory).history_for("long", 4_096, None)
    assert history[0]["content"].startswith(SUMMARY_HEADER)
    assert "turn 0" in history[0]["content"] or "turn" in history[0]["content"]
    assert (await memory.get_session_summary("long"))["method"] == "extractive"


async def test_failing_summarizer_never_stops_the_chat(tmp_path):
    memory = await long_session(tmp_path, turns=120)
    failing = AsyncMock(side_effect=RuntimeError("provider down"))
    history = await ContextEngine(memory).history_for("long", 4_096, failing)
    assert history and history[0]["content"].startswith(SUMMARY_HEADER)


async def test_short_session_is_sent_verbatim_without_current_request(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    await memory.save_message("short", "user", "first")
    await memory.save_message("short", "assistant", "")
    await memory.save_message("short", "assistant", "answer")
    await memory.save_message("short", "user", "current")
    history = await ContextEngine(memory).history_for("short", 1_000_000, None, current="current")
    assert history == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
    ]


async def test_compact_command_folds_whole_session(tmp_path):
    memory = await long_session(tmp_path, turns=10)
    summarizer = RecordingSummarizer()
    summary = await ContextEngine(memory).compact_now("long", summarizer, 200_000)
    assert summary.startswith("summary after")
    history = await ContextEngine(memory).history_for("long", 200_000, summarizer)
    assert len(history) == 1 and history[0]["content"].startswith(SUMMARY_HEADER)


async def test_history_pages_backwards(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    for index in range(7):
        await memory.save_message("paged", "user", f"m{index}")
    newest = await memory.get_messages("paged", limit=3)
    assert [m["content"] for m in newest] == ["m4", "m5", "m6"]
    older = await memory.get_messages("paged", limit=3, before_id=newest[0]["id"])
    assert [m["content"] for m in older] == ["m1", "m2", "m3"]
    assert len(await memory.get_messages("paged", limit=None)) == 7


def test_token_estimate_counts_non_latin_scripts_conservatively():
    assert estimate_tokens("abcd" * 10) == 10
    assert estimate_tokens("ميزان" * 10) > estimate_tokens("mizan" * 10)


def test_large_tool_results_stay_valid_json():
    payload = {"rows": ["x" * 100 for _ in range(500)]}
    clipped = json.loads(bounded_tool_result(payload, 5_000))
    assert clipped["truncated"] is True
    assert clipped["original_characters"] > 5_000
    assert json.loads(bounded_tool_result({"ok": 1}, 5_000)) == {"ok": 1}


class CutoffProvider(FakeProvider):
    """First call: a tool call cut by max_tokens; then a normal answer."""

    def __init__(self, responses):
        super().__init__(responses)
        self.max_tokens_seen = []
        self.messages_seen = []

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.max_tokens_seen.append(max_tokens)
        self.messages_seen.append(list(messages))
        response = super().create(model, max_tokens, system, messages, tools, temperature)
        if isinstance(response, Exception):
            raise response
        return response


async def test_cut_off_tool_call_is_requested_again_not_fatal():
    agent = make_test_agent()
    partial = LLMResponse(
        content=[ContentBlock(type="text", text="Writing the file now. ")],
        stop_reason="max_tokens",
    )
    provider = CutoffProvider([IncompleteToolCall(partial), text_resp("Done in two parts.")])
    agent.ai_client = provider
    chunks = await collect(
        agent._agentic_loop("sys", [{"role": "user", "content": "write it"}], [], False, "write")
    )
    assert "".join(chunks) == "Writing the file now. Done in two parts."
    # The retry gets more output room (bounded by the model's cap).
    assert provider.max_tokens_seen[1] >= provider.max_tokens_seen[0]
    retry_messages = provider.messages_seen[1]
    assert retry_messages[-1]["content"].startswith("[System: your previous tool call was cut off")


async def test_step_budget_ends_with_a_report_instead_of_an_error():
    agent = make_test_agent()
    agent.config["max_steps"] = 2
    action = LLMResponse(
        [ContentBlock(type="tool_use", id="t", name="list_dir", input={})], "tool_use", "m"
    )
    provider = CutoffProvider([action, action, text_resp("Did two steps; one remains.")])
    agent.ai_client = provider

    async def run_tool(name, params):
        return {"ok": True}

    agent._execute_tool_safe = run_tool
    chunks = await collect(
        agent._agentic_loop(
            "sys",
            [{"role": "user", "content": "go"}],
            [{"name": "list_dir", "description": "d", "input_schema": {}}],
            False,
            "go",
        )
    )
    full = "".join(chunks)
    assert "Did two steps; one remains." in full
    assert "Step budget reached" in full
    assert provider.messages_seen[-1][-1]["content"].startswith("[System: this run has reached")
