"""Tadbir: MIZAN's own architecture does the work; the LLM is only its language faculty."""

import json
from copy import deepcopy

import httpx
import pytest

from agents.events import bind_event_sink
from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import calc, fahm, hadith, majlis, project, quran, taallum, waqt
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
    names = [
        "workspace_run",
        "web_search",
        "web_browse",
        "recall_memory",
        "workspace_write",
        "workspace_create",
        "workspace_glob",
        "workspace_checkpoint",
    ]
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


# ── Hadith: authentic collections, quoted verbatim ───────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Bukhari 1", "Sahih al-Bukhari 1"),
        ("Sahih Bukhari hadith no. 6018", "Sahih al-Bukhari 6018"),
        ("Muslim 2564", "Sahih Muslim 2564"),
        ("Sahih Muslim 2564b", "Sahih Muslim 2564b"),
        ("رواه مسلم 2564", "Sahih Muslim 2564"),
        ("Jami at-Tirmidhi hadith 2516", "Jami` at-Tirmidhi 2516"),
        ("Abu Daud 4031", "Sunan Abi Dawud 4031"),
        ("sunan an-nasa'i 5758", "Sunan an-Nasa'i 5758"),
        ("ibne majah 224", "Sunan Ibn Majah 224"),
        ("Muwatta Imam Malik 1", "Muwatta Malik 1"),
        ("40 hadith nawawi 13", "Forty Hadith of an-Nawawi 13"),
        ("nawawi hadith 40", "Forty Hadith of an-Nawawi 40"),
        ("Bukhari ki pehli hadees", "Sahih al-Bukhari 1"),
        ("hadith 1 of bukhari", "Sahih al-Bukhari 1"),
        ("صحيح البخاري ١", "Sahih al-Bukhari 1"),
        ("بخاری شریف کی حدیث نمبر 1", "Sahih al-Bukhari 1"),
        ("बुखारी की हदीस नंबर 1", "Sahih al-Bukhari 1"),
    ],
)
def test_hadith_reference_parsing(text, expected):
    found = hadith.parse_reference(text)
    assert found is not None and found.label == expected
    assert fahm.understand(text).intent == "hadith"


@pytest.mark.parametrize(
    "text",
    [
        "muslim 5 waqt namaz kyun padhte hain",
        "I am a Muslim",
        "Imam Bukhari 194 hijri mein paida hue",
        "Bukhari 99999",
        "Muslim 3",  # Sahih Muslim's 'Abd al-Baqi numbering starts at 8
    ],
)
def test_ordinary_words_and_invalid_numbers_are_not_hadith_references(text):
    assert hadith.parse_reference(text) is None


def test_sahih_muslim_uses_abd_al_baqi_numbering():
    reference = hadith.validated("muslim", 2564, 2)
    assert reference is not None and reference.label == "Sahih Muslim 2564b"
    assert hadith.link(reference) == "https://sunnah.com/muslim:2564b"
    assert hadith.validated("muslim", 2564, 26) is None
    assert hadith.link(hadith.HadithRef("bukhari", 1)) == "https://sunnah.com/bukhari:1"


async def test_hadith_text_and_grades_come_verbatim_from_the_source(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        text = "حَدَّثَنِي أَبُو الطَّاهِرِ" if "/ara-" in str(request.url) else "Allah does not look"
        return httpx.Response(
            200,
            json={
                "metadata": {"section": {"45": "The Book of Virtue"}},
                "hadiths": [
                    {
                        "hadithnumber": 6542,
                        "text": text,
                        "grades": [],
                        "reference": {"book": 45, "hadith": 41},
                    }
                ],
            },
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(
        hadith.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    data = await hadith.fetch(hadith.HadithRef("muslim", 2564, 2), "en")
    assert sorted(seen) == [
        f"{hadith.API}/editions/ara-muslim/6542.min.json",
        f"{hadith.API}/editions/eng-muslim/6542.min.json",
    ]
    assert data["arabic"] == "حَدَّثَنِي أَبُو الطَّاهِرِ" and data["translation"] == "Allah does not look"
    assert data["reference"] == "Sahih Muslim 2564b" and "2564a" in data["narrations"]
    assert data["sahih_collection"] and data["section"] == "The Book of Virtue"


async def test_hadith_never_passes_through_the_model(agent, monkeypatch):
    async def fetch(reference, language):
        return {
            "reference": reference.label,
            "collection": "Jami` at-Tirmidhi",
            "collection_arabic": "جامع الترمذي",
            "sahih_collection": False,
            "section": "Chapters on Ar-Riqaq",
            "book": 37,
            "in_book": 102,
            "arabic": "احْفَظِ اللَّهَ يَحْفَظْكَ",
            "translation": "Be mindful of Allah and He will protect you.",
            "translation_language": "English",
            "clipped": False,
            "grades": [{"name": "Al-Albani", "grade": "Sahih"}],
            "narrations": [],
            "link": "https://sunnah.com/tirmidhi:2516",
            "source": hadith.SOURCE,
        }

    monkeypatch.setattr(hadith, "fetch", fetch)
    result = await agent.execute("Tirmidhi 2516 dikhao")
    assert "> احْفَظِ اللَّهَ يَحْفَظْكَ" in result["result"]
    assert (
        "- Al-Albani: Sahih" in result["result"] and "sunnah.com/tirmidhi:2516" in result["result"]
    )
    assert result["completion_status"] == "verified_by_mizan"
    assert agent.ai_client.requests == []

    async def weak(reference, language):
        found = await fetch(reference, language)
        return {**found, "grades": [{"name": "Al-Albani", "grade": "Da'if"}]}

    monkeypatch.setattr(hadith, "fetch", weak)
    graded = await agent.execute("Tirmidhi 2516")
    assert "weak or lower" in graded["result"]
    explained = await agent.execute("Explain Tirmidhi 2516")
    assert "Tuhfat al-Ahwadhi" in explained["result"] and agent.ai_client.requests == []

    async def unavailable(reference, language):
        raise hadith.HadithUnavailable("offline")

    monkeypatch.setattr(hadith, "fetch", unavailable)
    failed = await agent.execute("Bukhari 1")
    assert "does not write hadith from memory" in failed["result"]
    assert failed["task_verified"] is False and agent.ai_client.requests == []


def test_lisan_may_not_supply_a_hadith_number_the_user_did_not_write():
    parsed = {"intent": "hadith", "collection": "bukhari", "number": 1}
    assert fahm.validate_parsed(parsed, "the hadith about intentions", "en") is None
    understood = fahm.validate_parsed(parsed, "intentions wali hadith, bukhari mein number 1", "en")
    assert understood is not None and understood.entities["reference"].label == "Sahih al-Bukhari 1"


# ── Projects: MIZAN plans, saves and checks; Lisan writes the files ──────


@pytest.mark.parametrize(
    "text,kind,name",
    [
        ("Ek simple calculator app banao", "web", "Calculator app"),
        ("Create a quiz game about planets", "web", "Quiz game"),
        ("Python CLI todo app banao", "python", "CLI todo app"),
        ("ایک کیلکولیٹر ایپ بنا دو", "web", "Calculator app"),
        ("एक कैलकुलेटर ऐप बनाओ", "web", "Calculator app"),
    ],
)
def test_project_requests_are_understood(text, kind, name):
    understood = fahm.understand(text)
    assert understood.intent == "build_project"
    assert understood.entities == {"kind": kind, "name": name}


@pytest.mark.parametrize(
    "text", ["website kaise banate hain?", "React app banao", "Make it shorter", "Explain this app"]
)
def test_questions_and_other_stacks_are_not_project_builds(text):
    assert fahm.understand(text).intent != "build_project"


def test_mizan_checks_projects_itself():
    html, linked = project.link_assets("<html><head></head><body><p id='out'></p></body></html>")
    scan = project.scan_html(html)
    assert linked and "style.css" in scan.styles and "app.js" in scan.scripts
    js = "document.getElementById('out'); document.querySelector('#total'); el.id = 'made';"
    js += " document.getElementById('made')"
    assert project.missing_ids(html, js) == ["total"]
    assert project.css_balanced("a { color: red; } /* } */ b { content: '}'; }")
    assert not project.css_balanced("a { color: red; ")
    reply = "```app.js\nok();\n```\n```javascript evil.sh\nrm -rf /\n```"
    assert project.extract_files(reply, {"app.js", "index.html"}) == {"app.js": "ok();\n"}


async def test_web_project_is_planned_saved_checked_and_repaired_by_mizan(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        [
            "```html\n<html><head><title>Calc</title></head><body>"
            "<input id='a'><button id='go'>=</button></body></html>\n```",
            "```css\nbody { font: 16px sans-serif; }\n```",
            "```js\ndocument.getElementById('go').onclick = () => "
            "document.getElementById('result').textContent = 1;\n```",
            "```index.html\n<html><head><title>Calc</title></head><body><input id='a'>"
            "<button id='go'>=</button><output id='result'></output></body></html>\n```",
        ]
    )
    fake = tools(
        agent,
        monkeypatch,
        workspace_create={"id": "w1", "name": "Calculator app"},
        workspace_write={"path": "x", "sha256": "0", "bytes": 1},
        workspace_run={"stdout": "", "stderr": "", "exit_code": 0},
        workspace_checkpoint={"id": "c1"},
    )
    result = await agent.execute("Ek simple calculator app banao")
    names = [name for name, _params in fake.calls]
    assert names[0] == "workspace_create" and names[-1] == "workspace_checkpoint"
    saved = [params for name, params in fake.calls if name == "workspace_write"]
    assert [p["path"] for p in saved] == ["index.html", "style.css", "app.js", "index.html"]
    assert all(p["workspace_id"] == "w1" for p in saved)
    # MIZAN linked the assets itself, then Lisan added the missing element.
    assert '<script src="app.js"></script>' in saved[0]["content"]
    assert "id='result'" in saved[-1]["content"] and "app.js" in saved[-1]["content"]
    assert ("workspace_run", {"workspace_id": "w1", "command": "node --check app.js",
            "language": "shell", "timeout_s": 60}) in fake.calls  # fmt: skip
    assert result["completion_status"] == "verified_by_mizan"
    assert "✓" in result["result"] and "✗" not in result["result"]
    assert result["orchestration"]["language_model_calls"] == 4
    assert "Hinglish" in agent.ai_client.requests[0]["system"]
    assert not any(request.get("tools") for request in agent.ai_client.requests)


async def test_python_project_failing_tests_are_repaired_then_verified(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        [
            "```python\ndef add(a, b):\n    return a - b\n\nif __name__ == '__main__':\n"
            "    print(add(2, 3))\n```",
            "```python\nimport unittest\nfrom main import add\n\nclass T(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n```",
            "```main.py\ndef add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n"
            "    print(add(2, 3))\n```",
        ]
    )
    failed = {"stdout": "", "stderr": "AssertionError: -1 != 5", "exit_code": 1}
    passed = {"stdout": "", "stderr": "OK", "exit_code": 0}
    fake = tools(
        agent,
        monkeypatch,
        workspace_create={"id": "w2"},
        workspace_write={"path": "x"},
        workspace_run=[failed, passed, passed, passed],
        workspace_checkpoint={},
    )
    result = await agent.execute("Python CLI calculator project banao")
    commands = [params["command"] for name, params in fake.calls if name == "workspace_run"]
    assert commands[0] == "python -m unittest -q" and len(commands) == 4
    repair_request = agent.ai_client.requests[2]["messages"][0]["content"]
    assert "AssertionError: -1 != 5" in repair_request and "return a - b" in repair_request
    assert result["completion_status"] == "verified_by_mizan"
    assert "(1 baar)" in result["result"]  # answered in the user's Hinglish


async def test_a_project_that_still_fails_is_not_marked_verified(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        ["```html\n<p></p>\n```", "```css\na {\n```", "```js\nlet x = ;\n```", "no files"]
    )
    tools(
        agent,
        monkeypatch,
        workspace_create={"id": "w3"},
        workspace_write={"path": "x"},
        workspace_run={"stdout": "", "stderr": "SyntaxError", "exit_code": 1},
        workspace_checkpoint={},
    )
    result = await agent.execute("Build a todo app")
    assert result["task_verified"] is False and "✗" in result["result"]
    assert "SyntaxError" in result["result"]


async def test_an_existing_project_is_left_to_the_agent_loop(agent, monkeypatch):
    monkeypatch.setattr("workspace.context.bound_workspace_id", lambda: "w9")
    tools(agent, monkeypatch, workspace_glob={"files": [{"path": "index.html"}], "total": 1})
    agent.ai_client = ScriptedProvider(["I will edit your project."])
    result = await agent.execute("Build a todo app")
    assert "orchestrator" not in result["usage"]


# ── Waqt: dates and the Hijri calendar ───────────────────────────────────


@pytest.mark.parametrize(
    "text,kind",
    [
        ("aaj ki date kya hai", "today"),
        ("aaj ki hijri date batao", "today"),
        ("What is the date today?", "today"),
        ("abhi kitne baje hain", "today"),
        ("آج کی تاریخ کیا ہے", "today"),
        ("ما التاريخ اليوم؟", "today"),
        ("आज की तारीख क्या है", "today"),
        ("15 March 2026 hijri mein kya hogi", "to_hijri"),
        ("1 Ramadan 1448 kab hai", "to_gregorian"),
        ("Ramadan kab hai", "event"),
        ("Bakrid 1448 kab hai", "event"),
        ("Eid kab hai", "event"),
    ],
)
def test_date_questions_are_understood(text, kind):
    understood = fahm.understand(text)
    assert understood.intent == "waqt" and understood.entities["request"].kind == kind


@pytest.mark.parametrize(
    "text",
    ["Ramadan me roza kyun rakhte hain", "mera safar 2 din ka hai", "latest news search karo"],
)
def test_ordinary_sentences_are_not_date_questions(text):
    assert fahm.understand(text).intent != "waqt"


def test_umm_al_qura_conversions_and_range():
    from datetime import date

    hijri = waqt.to_hijri(date(2026, 10, 26))
    assert waqt.hijri_text(hijri) == "15 Jumada al-Ula 1448 AH"
    assert waqt.hijri_arabic(hijri) == "15 جمادى الأولى 1448 هـ"
    assert waqt.to_gregorian(1448, 9, 1) == date(2027, 2, 8)
    assert waqt.next_occurrence(9, 1, date(2026, 10, 26)) == (1448, date(2027, 2, 8))
    with pytest.raises(waqt.OutOfRange):
        waqt.to_hijri(date(2090, 1, 1))


def test_a_time_word_with_a_date_question_adds_the_time():
    assert waqt.parse("aaj ki hijri date aur time batao").with_time
    assert not waqt.parse("aaj ki date kya hai").with_time


def test_only_a_real_timezone_is_used():
    with waqt.bind_timezone("Asia/Karachi"):
        assert waqt.now()[1] == "Asia/Karachi"
        with waqt.bind_timezone("../../etc/passwd"):
            assert waqt.now()[1] is None
    assert waqt.now()[1] is None


async def test_dates_are_stated_by_mizan_without_a_model(agent, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    moment = datetime(2026, 10, 26, 21, 5, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(waqt, "now", lambda: (moment, None))
    today = await agent.execute("aaj ki date kya hai")
    assert "Monday, 26 October 2026" in today["result"]
    assert "15 Jumada al-Ula 1448 AH" in today["result"] and "UTC" in today["result"]
    assert today["completion_status"] == "verified_by_mizan"
    eid = await agent.execute("Eid kab hai")
    assert "Eid al-Fitr" in eid["result"] and "Eid al-Adha" in eid["result"]
    assert "Sahih al-Bukhari 1909" in eid["result"]  # sighting of the crescent decides
    monkeypatch.setattr(
        waqt, "now", lambda: (moment.astimezone(ZoneInfo("Asia/Kolkata")), "Asia/Kolkata")
    )
    clock = await agent.execute("What time is it?")
    assert "02:35" in clock["result"] and "Asia/Kolkata" in clock["result"]
    assert "Tuesday, 27 October 2026" in clock["result"]
    assert agent.ai_client.requests == []


# ── Compound requests: one plan, each part by its own recipe ─────────────


@pytest.mark.parametrize(
    "text,intents",
    [
        ("Bukhari 1 aur Surah Ikhlas dikhao", ["hadith", "quran"]),
        ("2+2 kitna hai aur aaj ki date kya hai", ["compute", "waqt"]),
        ("What is 2+2 and 3*3?", ["compute", "compute"]),
    ],
)
def test_independent_requests_are_split(text, intents):
    parts = fahm.understand_parts(text)
    assert parts is not None and [u.intent for _part, u in parts] == intents


@pytest.mark.parametrize(
    "text",
    [
        "Ek calculator app banao jisme do number jod sakein aur result dikhaye",
        "Surah Fatiha aur uska tarjuma",
        "web search karo latest AI news aur summarize karo",
        "Bukhari 1 and explain",
    ],
)
def test_one_request_with_a_conjunction_stays_whole(text):
    assert fahm.understand_parts(text) is None


async def test_compound_request_runs_every_part_under_one_plan(agent, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(
        waqt, "now", lambda: (datetime(2026, 10, 26, 9, 0, tzinfo=ZoneInfo("UTC")), None)
    )
    plans = []

    async def sink(kind, payload):
        if kind == "todo":
            plans.append([item["status"] for item in payload["todos"]])

    with bind_event_sink(sink):
        result = await agent.execute("2+2 kitna hai aur aaj ki date kya hai")
    assert result["orchestration"]["intent"] == "compound"
    assert "**4**" in result["result"] and "15 Jumada al-Ula 1448 AH" in result["result"]
    assert result["completion_status"] == "verified_by_mizan"
    assert plans[0] == ["in_progress", "pending"] and plans[-1] == ["completed", "completed"]
    assert agent.ai_client.requests == []


def test_lisan_may_map_project_wording_but_not_other_stacks():
    parsed = {"intent": "build_project", "kind": "web"}
    understood = fahm.validate_parsed(
        parsed, "mujhe ek todo list chahiye jo browser mein chale", "en"
    )
    assert understood is not None and understood.entities["kind"] == "web"
    assert fahm.validate_parsed(parsed, "mujhe React mein dashboard chahiye", "en") is None
    assert fahm.validate_parsed({"intent": "build_project", "kind": "rust"}, "a tool", "en") is None


# ── Majlis: MIZAN's agents share the work ────────────────────────────────


def council(monkeypatch, tmp_path, **results):
    """Khalifah coordinating Katib and Mundhir, each with its own tool gate."""
    import random

    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    # Exploit only, so tests are deterministic; exploration is tested on its own.
    monkeypatch.setattr(
        majlis,
        "thompson_choice",
        lambda options, posteriors, rng=None: max(options, key=lambda k: posteriors[k].mean),
    )
    names = ["workspace_run", "web_search", "web_browse", "recall_memory", "workspace_write"]
    agents = {}
    for kind, name in (("super", "Khalifah"), ("code", "Katib"), ("research", "Mundhir")):
        created = create_agent(kind, name=name, izn=IznPermission())
        created.ai_client = ScriptedProvider()
        monkeypatch.setattr(
            created,
            "get_tool_schemas",
            lambda: [
                {"name": n, "description": "", "input_schema": {"type": "object"}} for n in names
            ],
        )
        monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
        fake = FakeTools({key: deepcopy(value) for key, value in results.items()})
        monkeypatch.setattr(created, "_execute_tool_safe", fake)
        created.fake = fake
        agents[created.id] = created
    for created in agents.values():
        created._agent_registry = agents
    by_name = {a.name: a for a in agents.values()}
    random.seed(0)
    return by_name


async def test_mizan_gives_code_work_to_katib(monkeypatch, tmp_path):
    team = council(
        monkeypatch, tmp_path, workspace_run={"stdout": "1267650600228229401496703205376\n",
                                              "stderr": "", "exit_code": 0}
    )  # fmt: skip
    khalifah, katib = team["Khalifah"], team["Katib"]
    result = await khalifah.execute("Python me 2**100 calculate karke run karo")
    assert [name for name, _ in katib.fake.calls] == ["workspace_run"]
    assert khalifah.fake.calls == []
    assert result["orchestration"]["agents"][0]["agent"] == "Katib"
    assert "Katib" in result["result"] and result["completion_status"] == "verified_by_mizan"
    assert result["orchestration"]["plan"][0]["content"].startswith("MIZAN gives this to Katib")
    assert katib.total_tasks == 1 and katib.success_count == 1


async def test_hadith_stays_with_khalifah_and_research_goes_to_mundhir(monkeypatch, tmp_path):
    team = council(monkeypatch, tmp_path)
    assert majlis.choose(team["Khalifah"], "hadith") is team["Khalifah"]
    assert majlis.choose(team["Khalifah"], "web_search") is team["Mundhir"]
    assert majlis.choose(team["Khalifah"], "build_project") is team["Katib"]


async def test_routing_learns_from_evidence(monkeypatch, tmp_path):
    team = council(monkeypatch, tmp_path)
    khalifah, katib = team["Khalifah"], team["Katib"]
    for _ in range(40):
        majlis.record(khalifah, katib, "run_code", False)
    # Katib's code work kept failing MIZAN's checks: the work moves on.
    assert majlis.choose(khalifah, "run_code") is not katib
    rows = {(r["agent"], r["intent"]): r for r in majlis.report(khalifah)}
    assert rows[("Katib", "run_code")]["evidence"] > 0


def test_exploration_is_rare_but_real():
    import random

    class Member:
        def __init__(self, name, role):
            self.id, self.name, self.role = name, name, role
            self._agent_registry = None

        def get_tool_schemas(self):
            return [{"name": "workspace_run"}]

        def _chat_tool_allowed(self, name):
            return True

    katib, khalifah = Member("katib", "katib"), Member("khalifah", "khalifah")
    khalifah._agent_registry = {"katib": katib, "khalifah": khalifah}
    rng = random.Random(7)
    picks = [majlis.choose(khalifah, "run_code", rng).name for _ in range(400)]
    assert 0.8 < picks.count("katib") / 400 < 1.0


async def test_compound_parts_run_on_different_agents_in_parallel(monkeypatch, tmp_path):
    import asyncio

    team = council(monkeypatch, tmp_path)
    khalifah, mundhir = team["Khalifah"], team["Mundhir"]
    hadith_started = asyncio.Event()

    async def search(name, params):
        # Finishes only once Khalifah's part has started: needs real parallelism.
        await asyncio.wait_for(hadith_started.wait(), 2)
        return {"results": [{"title": "AI", "url": "https://a.example/", "snippet": "News."}]}

    async def fetch(reference, language):
        hadith_started.set()
        return {
            "reference": reference.label, "collection": "Sahih al-Bukhari",
            "collection_arabic": "صحيح البخاري", "sahih_collection": True, "section": "",
            "book": 1, "in_book": 1, "arabic": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
            "translation": "Actions are by intentions.", "translation_language": "English",
            "clipped": False, "grades": [], "narrations": [], "link": "", "source": hadith.SOURCE,
        }  # fmt: skip

    monkeypatch.setattr(mundhir, "_execute_tool_safe", search)
    monkeypatch.setattr(hadith, "fetch", fetch)
    result = await khalifah.execute("latest AI news search karo aur Bukhari 1 dikhao")
    assert result["orchestration"]["intent"] == "compound"
    workers = {w["intent"]: w["agent"] for w in result["orchestration"]["agents"]}
    assert workers == {"web_search": "Mundhir", "hadith": "Khalifah"}
    assert "بِالنِّيَّاتِ" in result["result"] and "https://a.example/" in result["result"]
    labels = [item["content"] for item in result["orchestration"]["plan"]]
    assert labels[0].startswith("Mundhir:") and labels[1].startswith("Khalifah:")


# ── Ta'allum: learning wording from verified work ────────────────────────


async def test_verified_wording_is_learned_and_reused_without_asking_lisan(agent, monkeypatch):
    fib = "```python\na, b = 0, 1\nfor _ in range(50):\n    a, b = b, a + b\nprint(a)\n```"
    agent.ai_client = ScriptedProvider(
        [
            '{"intent":"build_and_run","request":"print the 50th Fibonacci number",'
            '"language":"python"}',
            fib,
            fib,
        ]
    )
    tools(
        agent, monkeypatch, workspace_run={"stdout": "12586269025\n", "stderr": "", "exit_code": 0}
    )
    first = await agent.execute("Fibonacci series ka 50th number kya hai?")
    assert first["orchestration"]["entities"]["understood_by"] == "lisan"
    second = await agent.execute("Fibonacci series ka 60th number kya hai?")
    assert second["orchestration"]["entities"]["understood_by"] == "mizan_learned"
    assert second["orchestration"]["language_model_calls"] == 1  # code only, no mapping call
    assert len(agent.ai_client.requests) == 3
    assert taallum.summary(agent.adaptive, "")["by_intent"] == {"build_and_run": 1}


async def test_unverified_or_reworded_questions_are_not_learned(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        [
            '{"intent":"build_and_run","request":"print primes","language":"python"}',
            "```python\nprint(1/0)\n```",
            "```python\nprint(1/0)\n```",
            "```python\nprint(1/0)\n```",
        ]
    )
    failed = {"stdout": "", "stderr": "ZeroDivisionError", "exit_code": 1}
    tools(agent, monkeypatch, workspace_run=[failed, failed, failed])
    result = await agent.execute("Pehle 10 prime numbers nikalo program se")
    assert result["task_verified"] is False
    assert taallum.summary(agent.adaptive, "")["examples"] == 0


def test_learned_wording_never_crosses_into_a_question():
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(None)
    learned = fahm.Understanding(
        "build_and_run", "hi-latn", 0.6, {"code_language": "python", "understood_by": "lisan"}
    )
    taallum.learn(store, "u1", "Fibonacci series ka 50th number nikalo", learned, True)
    assert taallum.recall(store, "u1", "Fibonacci series ka 70th number nikalo") is not None
    assert taallum.recall(store, "u1", "Fibonacci series ka matlab samjhao") is None
    assert taallum.recall(store, "u2", "Fibonacci series ka 70th number nikalo") is None
    for _ in range(10):
        kept = taallum._load(store, "u1")
        if not kept:
            break
        taallum.reweigh(store, "u1", kept[0], False)
    assert taallum.summary(store, "u1")["examples"] == 0  # stopped working: dropped


async def test_learning_api_shows_routing_and_forgets_wording(monkeypatch, tmp_path):
    from fastapi import HTTPException

    from security.auth import TokenPayload

    team = council(monkeypatch, tmp_path)
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main

    alice = TokenPayload("alice", "alice", ["user"], 9999999999, 0, "t")
    monkeypatch.setattr(main, "active_agents", {})
    with pytest.raises(HTTPException):
        await main.tadbir_learning(alice)
    monkeypatch.setattr(main, "active_agents", {a.id: a for a in team.values()})
    khalifah = team["Khalifah"]
    learned = fahm.Understanding("web_search", "en", 0.6, {"understood_by": "lisan"})
    taallum.learn(khalifah.adaptive, "alice", "cricket score batao abhi", learned, True)
    view = await main.tadbir_learning(alice)
    assert view["wording"]["examples"] == 1
    assert any(r["agent"] == "Katib" and r["specialist"] for r in view["routing"])
    assert (await main.forget_tadbir_wording(alice))["forgotten"]
    assert (await main.tadbir_learning(alice))["wording"]["examples"] == 0
