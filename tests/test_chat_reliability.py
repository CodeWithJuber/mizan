"""
Chat Reliability Tests — production bug-hunt fixes (2026-09-30)
================================================================

Covers the backend fixes for the user's 9 chat issues:
  - Issue 5: tool calls within a turn execute CONCURRENTLY (not sequentially)
  - Issue 9: true token streaming via provider.stream() (+ create() fallback)
  - Issue 9: max_tokens truncation → bounded auto-continue, then honest notice
  - Bonus:   empty model output → summarize tool results (no Hindi filler)
  - Providers: Anthropic/OpenAI stream wrappers accumulate tool_use blocks
"""

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from agents.specialized import create_agent
from providers import (
    ContentBlock,
    LLMResponse,
    _AnthropicStreamWrapper,
    _OpenAIStreamWrapper,
)

# ═══════════════════════════════════════════════════════════════════════════════
# FAKES
# ═══════════════════════════════════════════════════════════════════════════════


class FakeProvider:
    """Deterministic create()-only provider returning scripted responses."""

    provider_name = "fake"

    def __init__(self, responses):
        self._responses = list(responses)
        self.create_calls = 0

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.create_calls += 1
        return self._responses.pop(0)


class FakeStreamWrapper:
    """Minimal wrapper honoring the provider streaming contract."""

    def __init__(self, chunks, final):
        self._chunks = list(chunks)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def text_stream(self):
        yield from self._chunks

    def get_final_response(self):
        return self._final


class FakeStreamingProvider(FakeProvider):
    def __init__(self, responses, stream_chunks=None, final=None):
        super().__init__(responses)
        self._stream_chunks = stream_chunks or []
        self._final = final
        self.stream_calls = 0
        self.stream_tools = "unset"

    def stream(self, model, max_tokens, system, messages, tools=None, temperature=None):
        self.stream_calls += 1
        self.stream_tools = tools
        return FakeStreamWrapper(self._stream_chunks, self._final)


def make_test_agent():
    wali = MagicMock()
    wali.check_rate_limit.return_value = True
    wali.validate_command.return_value = True
    wali.validate_url.return_value = True
    wali.validate_file_path.return_value = True
    wali.audit = MagicMock()
    izn = MagicMock()
    izn.check_permission.return_value = {
        "allowed": True,
        "reason": "Test",
        "requires_approval": False,
    }
    agent = create_agent("general", name="TestAgent", wali=wali, izn=izn)
    agent.ai_model = "fake-model"
    return agent


def text_resp(text, stop="end_turn"):
    return LLMResponse(
        content=[ContentBlock(type="text", text=text)],
        stop_reason=stop,
        model="fake-model",
    )


async def collect(agen):
    return [c async for c in agen]


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE 5 — PARALLEL TOOL EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestParallelTools:
    async def test_tool_calls_in_one_turn_run_concurrently(self):
        agent = make_test_agent()
        events = []

        async def tool_a():
            events.append(("a_start", time.monotonic()))
            await asyncio.sleep(0.4)
            events.append(("a_end", time.monotonic()))
            return {"ok": "a"}

        async def tool_b():
            events.append(("b_start", time.monotonic()))
            await asyncio.sleep(0.4)
            events.append(("b_end", time.monotonic()))
            return {"ok": "b"}

        agent.tools["tool_a"] = tool_a
        agent.tools["tool_b"] = tool_b
        agent.ai_client = FakeProvider(
            [
                LLMResponse(
                    content=[
                        ContentBlock(type="tool_use", id="t1", name="tool_a", input={}),
                        ContentBlock(type="tool_use", id="t2", name="tool_b", input={}),
                    ],
                    stop_reason="tool_use",
                ),
                text_resp("done"),
            ]
        )

        chunks = await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "go"}], [], False, "go")
        )
        full = "".join(chunks)
        assert "done" in full

        starts = {name: ts for name, ts in events if name.endswith("_start")}
        ends = {name: ts for name, ts in events if name.endswith("_end")}
        # Overlap: the second tool started before the first finished.
        # Sequential execution could never satisfy this.
        assert max(starts.values()) < min(ends.values())

    async def test_tool_results_fed_back_in_order(self):
        agent = make_test_agent()

        async def tool_a():
            return {"n": 1}

        async def tool_b():
            return {"n": 2}

        agent.tools["tool_a"] = tool_a
        agent.tools["tool_b"] = tool_b
        provider = FakeProvider(
            [
                LLMResponse(
                    content=[
                        ContentBlock(type="tool_use", id="t1", name="tool_a", input={}),
                        ContentBlock(type="tool_use", id="t2", name="tool_b", input={}),
                    ],
                    stop_reason="tool_use",
                ),
                text_resp("done"),
            ]
        )
        agent.ai_client = provider
        await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "go"}], [], False, "go")
        )
        # Both tool results were recorded for the summary path, in order.
        assert [tr["name"] for tr in agent._last_tool_results] == ["tool_a", "tool_b"]


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE 9 — TRUE STREAMING + FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════


class TestTrueStreaming:
    async def test_tokens_arrive_incrementally(self):
        agent = make_test_agent()
        final = text_resp("hello world")
        provider = FakeStreamingProvider([], stream_chunks=["hello ", "world"], final=final)
        agent.ai_client = provider

        received = await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], True, "hi")
        )
        # Incremental chunks — not a single post-hoc blob.
        assert received == ["hello ", "world"]
        assert provider.stream_calls == 1
        assert provider.create_calls == 0

    async def test_streaming_passes_tools_to_provider(self):
        agent = make_test_agent()
        final = text_resp("ok")
        provider = FakeStreamingProvider([], stream_chunks=["ok"], final=final)
        agent.ai_client = provider
        schemas = [{"name": "tool_a"}]

        await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], schemas, True, "hi")
        )
        assert provider.stream_tools == schemas

    async def test_streaming_failure_falls_back_to_create(self):
        agent = make_test_agent()

        class BrokenStreamProvider(FakeProvider):
            def stream(self, *a, **k):
                raise RuntimeError("streaming not supported")

        provider = BrokenStreamProvider([text_resp("fallback ok")])
        agent.ai_client = provider

        chunks = await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], True, "hi")
        )
        # The create() fallback text must still be delivered (no silent drop).
        assert "".join(chunks) == "fallback ok"
        assert provider.create_calls == 1


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE 9 — MAX_TOKENS AUTO-CONTINUE
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaxTokensContinue:
    async def test_truncated_turn_auto_continues(self):
        agent = make_test_agent()
        provider = FakeProvider(
            [
                text_resp("part1 ", stop="max_tokens"),
                text_resp("part2"),
            ]
        )
        agent.ai_client = provider

        chunks = await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], False, "hi")
        )
        full = "".join(chunks)
        assert "part1" in full and "part2" in full
        assert provider.create_calls == 2

    async def test_bounded_continue_then_honest_notice(self):
        agent = make_test_agent()
        provider = FakeProvider([text_resp(f"p{i} ", stop="max_tokens") for i in range(5)])
        agent.ai_client = provider

        chunks = await collect(
            agent._agentic_loop("sys", [{"role": "user", "content": "hi"}], [], False, "hi")
        )
        full = "".join(chunks)
        # 1 initial + 2 bounded continuations, then an honest notice.
        assert provider.create_calls == 3
        assert "length limit" in full


# ═══════════════════════════════════════════════════════════════════════════════
# BONUS — EMPTY OUTPUT → TOOL-RESULT SUMMARY (NO FILLER)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmptyOutputSummary:
    def test_no_hindi_filler_string_in_codebase(self):
        src = (Path(__file__).parent.parent / "backend" / "agents" / "base.py").read_text()
        assert "saransh" not in src

    async def test_summarize_tool_results_yields_summary(self):
        agent = make_test_agent()
        final = text_resp("Summary: all good")
        provider = FakeStreamingProvider([], stream_chunks=["Summary: ", "all good"], final=final)
        agent.ai_client = provider

        out = await collect(
            agent._summarize_tool_results("do things", [{"name": "tool_a", "result": {"ok": 1}}])
        )
        assert "".join(out) == "Summary: all good"

    async def test_summarize_falls_back_to_create(self):
        agent = make_test_agent()

        class BrokenStreamProvider(FakeProvider):
            def stream(self, *a, **k):
                raise RuntimeError("no stream")

        provider = BrokenStreamProvider([text_resp("created summary")])
        agent.ai_client = provider

        out = await collect(
            agent._summarize_tool_results("do things", [{"name": "tool_a", "result": {"ok": 1}}])
        )
        assert "".join(out) == "created summary"


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE 6 — MEMORY INJECTION (REGRESSION)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryInjection:
    """Issue 6 regression: think() must inject Dhikr memories into the prompt.

    Root cause (2026-09-30): think() called ``memory.recall(task, top_k=3)``
    but DhikrMemorySystem.recall() takes ``limit`` — TypeError on every chat
    turn, swallowed by a bare ``except: pass``, so memory injection silently
    never happened.
    """

    async def test_think_injects_recalled_memories(self, tmp_path):
        from memory.dhikr import DhikrMemorySystem
        from reasoning.context_manager import ContextManager

        mem = DhikrMemorySystem(db_path=str(tmp_path / "mem.db"))
        await mem.remember(
            "The user prefers concise answers with bullet points",
            memory_type="preference",
            importance=0.9,
            tags=["preference"],
        )

        agent = make_test_agent()
        agent.memory = mem
        agent.context_manager = ContextManager()

        captured = {}

        class CapturingProvider(FakeProvider):
            def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
                captured["messages"] = messages
                return super().create(model, max_tokens, system, messages, tools, temperature)

        agent.ai_client = CapturingProvider([text_resp("ok")])

        chunks = [c async for c in agent.think("give me concise answers")]
        assert "ok" in "".join(chunks)

        all_content = " ".join(
            m.get("content", "") for m in captured["messages"] if isinstance(m.get("content"), str)
        )
        assert "[Context from Dhikr memory]" in all_content
        assert "bullet points" in all_content


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER STREAM WRAPPERS
# ═══════════════════════════════════════════════════════════════════════════════


class TestStreamWrappers:
    def test_anthropic_wrapper_final_response(self):
        fake_msg = SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="hi"),
                SimpleNamespace(type="tool_use", id="t1", name="search", input={"q": "x"}),
            ],
            stop_reason="tool_use",
            model="claude-x",
            usage=SimpleNamespace(input_tokens=5, output_tokens=7),
        )
        fake_stream = SimpleNamespace(
            text_stream=iter(["hi"]),
            get_final_message=lambda: fake_msg,
        )
        mgr = SimpleNamespace()
        mgr.__enter__ = lambda: fake_stream
        mgr.__exit__ = lambda *a: False

        with _AnthropicStreamWrapper(mgr) as s:
            assert list(s.text_stream) == ["hi"]
            resp = s.get_final_response()

        assert resp.stop_reason == "tool_use"
        assert resp.usage == {"input": 5, "output": 7}
        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0].name == "search"
        assert tool_blocks[0].input == {"q": "x"}

    def test_openai_wrapper_accumulates_tool_calls(self):
        def delta(content=None, tool_calls=None):
            return SimpleNamespace(content=content, tool_calls=tool_calls)

        def chunk(d, finish=None):
            return SimpleNamespace(choices=[SimpleNamespace(delta=d, finish_reason=finish)])

        tc1 = SimpleNamespace(
            index=0,
            id="call_1",
            function=SimpleNamespace(name="search", arguments='{"q":'),
        )
        tc2 = SimpleNamespace(
            index=0,
            id="",
            function=SimpleNamespace(name="", arguments='"x"}'),
        )
        w = _OpenAIStreamWrapper(None, "m", 10, [])
        w._stream = [
            chunk(delta(content="hi")),
            chunk(delta(tool_calls=[tc1])),
            chunk(delta(tool_calls=[tc2]), finish="tool_calls"),
        ]

        assert list(w.text_stream) == ["hi"]
        resp = w.get_final_response()
        assert resp.stop_reason == "tool_use"
        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0].id == "call_1"
        assert tool_blocks[0].name == "search"
        assert tool_blocks[0].input == {"q": "x"}

    def test_openai_wrapper_finish_reason_mapping(self):
        def chunk(finish):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="x", tool_calls=None),
                        finish_reason=finish,
                    )
                ]
            )

        for finish, expected in [("stop", "end_turn"), ("length", "max_tokens")]:
            w = _OpenAIStreamWrapper(None, "m", 10, [])
            w._stream = [chunk(finish)]
            list(w.text_stream)
            assert w.get_final_response().stop_reason == expected
