"""Tadbir: MIZAN's own architecture does the work; the LLM is only its language faculty."""

import json
from copy import deepcopy

import httpx
import pytest

from agents.events import bind_event_sink
from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import calc, fahm, quran
from tadbir.express import furqan


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, LLMResponse):
            return reply
        return LLMResponse([ContentBlock(type="text", text=reply)], model="fixture")


class FakeTools:
    """Stands in for _execute_tool_safe and records every call MIZAN makes."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def __call__(self, name, params):
        self.calls.append((name, deepcopy(params)))
        result = self.results[name]
        return result.pop(0) if isinstance(result, list) else result


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    created = create_agent("general", izn=IznPermission())
    created.ai_client = ScriptedProvider()
    names = ["workspace_run", "web_search", "web_browse", "recall_memory", "workspace_write"]
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {"type": "object"}} for n in names],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
    return created


def tools(agent, monkeypatch, **results):
    fake = FakeTools(results)
    monkeypatch.setattr(agent, "_execute_tool_safe", fake)
    return fake


# ── Fahm: understanding without a model ──────────────────────────────────


@pytest.mark.parametrize(
    "text,intent,language",
    [
        ("Hai tumhare paas tools?", "capabilities", "hi-latn"),
        ("What can you do?", "capabilities", "en"),
        ("2+2?", "compute", "en"),
        ("2+2 kitna hota hai?", "compute", "hi-latn"),
        ("What is 15% of 200?", "compute", "en"),
        ("Python me 2**100 calculate karke run karo", "run_code", "hi-latn"),
        ("```python\nprint(1)\n```\nrun karo", "run_code", "hi-latn"),
        (
            "Ek python program likho jo 10 fibonacci print kare aur run karo",
            "build_and_run",
            "hi-latn",
        ),
        ("Ayatul Kursi sunao", "quran", "hi-latn"),
        ("سورة الإخلاص", "quran", "ar"),
        ("سورہ یٰسین", "quran", "ur"),
        ("मुझे सूरह इखलास सुनाओ", "quran", "hi"),
        ("https://example.com/a padho aur summary do", "web_read", "hi-latn"),
        ("Latest news about Gaza search karo", "web_search", "hi-latn"),
        ("Search the latest news about Gaza", "web_search", "en"),
        ("Yaad hai maine kya bataya tha?", "recall", "hi-latn"),
        ("Explain recursion simply", "converse", "en"),
        ("Assalamu alaikum bhai kaise ho", "converse", "hi-latn"),
    ],
)
def test_fahm_understands_without_a_model(text, intent, language):
    understanding = fahm.understand(text)
    assert (understanding.intent, understanding.language) == (intent, language)


def test_mizan_writes_the_program_for_a_run_request():
    understanding = fahm.understand("Python me 2**100 calculate karke run karo")
    assert understanding.entities["code"] == "print(2**100)"
    assert understanding.entities["generated_by"] == "mizan"


# ── Own calculation and Quran index ──────────────────────────────────────


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2**100", "1267650600228229401496703205376"),
        ("2^10", "1024"),
        ("1/3 + 1/6", "1/2 ≈ 0.5"),
        ("20!", "2432902008176640000"),
        ("15% of 200", "30"),
        ("(3+4)*5", "35"),
    ],
)
def test_exact_calculation(expression, expected):
    assert calc.render(calc.evaluate(expression)) == expected


@pytest.mark.parametrize(
    "expression", ["2**10**10", "1/0", "__import__('os')", "factorial(10**6)", "a+1"]
)
def test_calculator_refuses_unsafe_or_unbounded_input(expression):
    with pytest.raises(calc.CalcError):
        calc.evaluate(expression)


def test_surah_index_matches_the_hafs_count():
    assert len(quran.SURAHS) == 114
    assert sum(count for _, _, count in quran.SURAHS) == quran.TOTAL_AYAHS == 6236


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2:255", (2, 255, 255)),
        ("Surah Al-Baqarah 255", (2, 255, 255)),
        ("surah al kahf ayat 10-12", (18, 10, 12)),
        ("Surah Yasin ayat 1", (36, 1, 1)),
        ("سورة البقرة 255", (2, 255, 255)),
        ("surah ikhlas", (112, None, None)),
        ("Quran 3:190-191", (3, 190, 191)),
    ],
)
def test_reference_parsing(text, expected):
    reference = quran.parse_reference(text)
    assert (reference.surah, reference.start, reference.end) == expected


@pytest.mark.parametrize(
    "text,ayah",
    [
        ("Surah Rahman ki terahvi ayat dikhao", 13),
        ("Surah Rahman ki 13vi ayat", 13),
        ("Surah Yasin ki pehli ayat", 1),
        ("surah mulk 1st ayah", 1),
    ],
)
def test_ordinal_ayahs(text, ayah):
    reference = quran.parse_reference(text)
    assert reference.start == reference.end == ayah


async def test_long_surahs_are_shown_in_parts(agent, monkeypatch):
    async def fetch(reference, language):
        return {
            "reference": reference.label,
            "surah_arabic": "الرحمن",
            "ayahs": [
                {"number": n, "arabic": f"ayah-{n}", "translation": ""} for n in range(1, 11)
            ],
            "translation": "",
            "source": "api.alquran.cloud (Tanzil Uthmani text)",
            "shown": (1, 10),
            "requested": 78,
            "total": 78,
        }

    monkeypatch.setattr(quran, "fetch", fetch)
    result = await agent.execute("Surah Rahman")
    assert "1–10 of 78" in result["result"] and "Surah Ar-Rahman 11-20" in result["result"]


@pytest.mark.parametrize("text", ["2:300", "surah 115", "what is 2:3", "Surah 1:8"])
def test_invalid_or_ambiguous_references_are_rejected(text):
    assert quran.parse_reference(text) is None


async def test_quran_text_is_verbatim_with_the_source_basmala_removed(monkeypatch):
    payload = {
        "data": [
            {"numberInSurah": 1, "text": quran.BASMALA + " قُلْ هُوَ ٱللَّهُ أَحَدٌ"},
            {"numberInSurah": 1, "text": "Say, He is Allah, [who is] One,"},
        ]
    }
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=payload)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        quran.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    data = await quran.fetch(quran.Reference(112, 1, 1), "en")
    assert data["ayahs"][0]["arabic"] == "قُلْ هُوَ ٱللَّهُ أَحَدٌ"
    assert seen == ["https://api.alquran.cloud/v1/ayah/112:1/editions/quran-uthmani,en.sahih"]
    fatiha = await quran.fetch(quran.Reference(1, 1, 1), "en")
    assert fatiha["ayahs"][0]["arabic"].startswith(quran.BASMALA)


def test_basmala_is_removed_whatever_the_mark_order():
    reordered = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ قُلْ هُوَ"
    reordered = reordered.replace("\u064e\u0651", "\u0651\u064e")
    assert quran.strip_basmala(reordered) == "قُلْ هُوَ"
    assert quran.strip_basmala("قُلْ هُوَ") == "قُلْ هُوَ"


def test_furqan_rejects_unsupported_wording():
    facts = json.dumps({"value": "1024", "sources": ["https://a.example/x"]})
    assert furqan("The answer is 1024 [1].", facts, max_citation=1) == []
    assert furqan("The answer is 2048.", facts)
    assert furqan("See [3].", facts, max_citation=2)
    assert furqan("More at https://evil.example/", facts)
    assert furqan("I ran the code and it worked.", facts)


# ── The engine through agent.execute ────────────────────────────────────


async def test_arithmetic_is_answered_by_mizan_with_no_model_call(agent):
    result = await agent.execute("2+2?")
    assert "**4**" in result["result"]
    assert agent.ai_client.requests == []
    assert result["completion_status"] == "verified_by_mizan" and result["task_verified"]
    assert result["usage"]["orchestrator"] == "mizan"
    assert result["orchestration"]["intent"] == "compute"


async def test_run_request_is_planned_run_and_cross_checked_by_mizan(agent, monkeypatch):
    fake = tools(
        agent,
        monkeypatch,
        workspace_run={
            "stdout": "1267650600228229401496703205376\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 40,
        },
    )
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    with bind_event_sink(sink):
        result = await agent.execute("Python me 2**100 calculate karke run karo aur result batao")
    assert fake.calls == [
        ("workspace_run", {"command": "print(2**100)", "language": "python", "timeout_s": 60})
    ]
    assert agent.ai_client.requests == []
    assert result["task_verified"]
    assert "1267650600228229401496703205376" in result["result"]
    kinds = [kind for kind, _ in events]
    assert "todo" in kinds and "tool_start" in kinds and "tool_result" in kinds
    final_plan = [payload for kind, payload in events if kind == "todo"][-1]["todos"]
    assert all(item["status"] == "completed" for item in final_plan)


async def test_a_wrong_sandbox_result_is_not_marked_verified(agent, monkeypatch):
    tools(agent, monkeypatch, workspace_run={"stdout": "42\n", "stderr": "", "exit_code": 0})
    result = await agent.execute("Python me 2**10 run karo")
    assert result["task_verified"] is False


async def test_lisan_writes_code_and_mizan_repairs_failures(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        ["```python\nprint(fib(10)\n```", "```python\nprint([0, 1, 1, 2, 3])\n```"]
    )
    fake = tools(
        agent,
        monkeypatch,
        workspace_run=[
            {"stdout": "", "stderr": "SyntaxError: '(' was never closed", "exit_code": 1},
            {"stdout": "[0, 1, 1, 2, 3]\n", "stderr": "", "exit_code": 0, "duration_ms": 30},
        ],
    )
    result = await agent.execute(
        "Ek python program likho jo 5 fibonacci numbers print kare aur run karo"
    )
    assert [name for name, _ in fake.calls] == ["workspace_run", "workspace_run"]
    assert fake.calls[1][1]["command"] == "print([0, 1, 1, 2, 3])"
    assert len(agent.ai_client.requests) == 2
    assert "tools" not in agent.ai_client.requests[0] or not agent.ai_client.requests[0].get(
        "tools"
    )
    assert "SyntaxError" in agent.ai_client.requests[1]["messages"][0]["content"]
    assert result["task_verified"] and "2 " in result["result"]


async def test_capabilities_come_from_the_registry_not_the_model(agent):
    result = await agent.execute("Hai tumhare paas tools?")
    assert agent.ai_client.requests == []
    assert "sandbox" in result["result"] and "web search" in result["result"]


async def test_quran_text_never_passes_through_the_model(agent, monkeypatch):
    async def fetch(reference, language):
        return {
            "reference": reference.label,
            "surah_arabic": "الإخلاص",
            "ayahs": [
                {"number": 1, "arabic": "قُلْ هُوَ ٱللَّهُ أَحَدٌ", "translation": "Say, He is Allah, One"}
            ],
            "translation": "Saheeh International",
            "source": "api.alquran.cloud (Tanzil Uthmani text)",
        }

    monkeypatch.setattr(quran, "fetch", fetch)
    result = await agent.execute("Surah Ikhlas ayah 1")
    assert "قُلْ هُوَ ٱللَّهُ أَحَدٌ ﴿1﴾" in result["result"]
    assert agent.ai_client.requests == []

    async def unavailable(reference, language):
        raise quran.QuranUnavailable("offline")

    monkeypatch.setattr(quran, "fetch", unavailable)
    failed = await agent.execute("Surah Ikhlas ayah 1")
    assert "does not write ayahs from memory" in failed["result"]
    assert failed["task_verified"] is False and agent.ai_client.requests == []


async def test_search_answer_keeps_only_supported_citations(agent, monkeypatch):
    results = {
        "results": [
            {"title": "Report A", "url": "https://a.example/1", "snippet": "Rain fell 12 mm."},
            {"title": "Report B", "url": "https://b.example/2", "snippet": "Roads reopened."},
        ]
    }
    tools(agent, monkeypatch, web_search=[results, results])
    agent.ai_client = ScriptedProvider(["Rain fell 12 mm [1] and roads reopened [2]."])
    good = await agent.execute("Latest weather news search karo")
    assert good["result"].startswith("Rain fell 12 mm [1]")
    assert "https://a.example/1" in good["result"] and good["task_verified"]
    agent.ai_client = ScriptedProvider(["Rain fell 99 mm [7]."])
    bad = await agent.execute("Latest weather news search karo")
    assert "99 mm" not in bad["result"] and "Report A" in bad["result"]
    assert bad["task_verified"] is False


async def test_modes_route_unknown_requests(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(["Recursion is a function calling itself."])
    result = await agent.execute("Explain recursion simply")
    assert "orchestrator" not in result.get("usage", {})
    assert agent.ai_client.requests[0].get("tools")  # the general agent loop
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "strict")
    agent.ai_client = ScriptedProvider(["It calls itself on a smaller input."])
    strict = await agent.execute("Explain recursion simply")
    assert strict["usage"]["orchestrator"] == "mizan"
    assert not agent.ai_client.requests[0].get("tools")  # language only, no tool control
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    agent.ai_client = ScriptedProvider(["4"])
    legacy = await agent.execute("2+2?")
    assert len(agent.ai_client.requests) == 1 and "orchestrator" not in legacy["usage"]


async def test_tools_mizan_may_not_use_are_left_to_the_agent_loop(agent, monkeypatch):
    monkeypatch.setattr(agent, "_chat_tool_allowed", lambda name: name != "workspace_run")
    agent.ai_client = ScriptedProvider(["I can't run code here."])
    result = await agent.execute("```python\nprint(1)\n```\nrun karo")
    assert "orchestrator" not in result["usage"]


async def test_lisan_only_maps_wording_and_mizan_validates_it(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        [
            '{"intent":"build_and_run","request":"print the 50th Fibonacci number","language":"python"}',
            "```python\na, b = 0, 1\nfor _ in range(50):\n    a, b = b, a + b\nprint(a)\n```",
        ]
    )
    fake = tools(
        agent, monkeypatch, workspace_run={"stdout": "12586269025\n", "stderr": "", "exit_code": 0}
    )
    result = await agent.execute("Fibonacci series ka 50th number kya hai?")
    assert result["orchestration"]["intent"] == "build_and_run"
    assert result["orchestration"]["entities"]["understood_by"] == "lisan"
    assert fake.calls[0][0] == "workspace_run" and "12586269025" in result["result"]
    assert not any(r.get("tools") for r in agent.ai_client.requests)


@pytest.mark.parametrize(
    "parsed",
    [
        {"intent": "web_read", "url": "https://invented.example/"},
        {"intent": "quran", "surah": 2, "ayah_start": 300},
        {"intent": "compute", "expression": "__import__('os')"},
        {"intent": "delete_everything"},
    ],
)
def test_doubtful_lisan_mappings_are_rejected(parsed):
    assert fahm.validate_parsed(parsed, "summarize the latest Quran news 2", "en") is None


async def test_rejected_mapping_falls_back_to_the_agent_loop(agent):
    agent.ai_client = ScriptedProvider(['{"intent":"converse"}', "Python is a language."])
    result = await agent.execute("Explain what Python code is used for")
    assert "orchestrator" not in result["usage"]
    assert result["result"] == "Python is a language."
