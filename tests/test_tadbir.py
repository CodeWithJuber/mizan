"""Tadbir: MIZAN's own architecture does the work; the LLM is only its language faculty."""

import json
from copy import deepcopy

import httpx
import pytest

from agents.events import bind_event_sink
from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import amal, calc, fahm, hadith, majlis, project, qasd, quran, taallum, waqt
from tadbir import lisan as lisan_module
from tadbir.express import furqan, phrase


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
        # (A bare "What can you do?" sits at P ≈ ½ in the seeds: not decisive, so
        # it is answered in words; no tool runs either way.)
        ("What are you able to do?", "capabilities", "en"),
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
        # A salam and nothing else is returned by MIZAN (4:86); with a request,
        # or returned to it, it stays conversation.
        ("Assalamualaikum bhai jaan", "salam", "hi-latn"),
        ("السلام علیکم ورحمۃ اللہ وبرکاتہ", "salam", "ur"),
        ("Walaikum assalam bhai", "converse", "hi-latn"),
        ("Assalamualaikum, Surah Ikhlas sunao", "quran", "hi-latn"),
        # Addressed to MIZAN, but not about its tools (none of these is a seed)
        ("Kya tum pagal ho gaye?", "converse", "hi-latn"),
        ("Can you tell the future of Pakistan?", "converse", "en"),
        ("Are you better than ChatGPT?", "converse", "en"),
    ],
)
def test_fahm_understands_without_a_model(text, intent, language):
    understanding = fahm.understand(text)
    assert (understanding.intent, understanding.language) == (intent, language)


def test_material_in_the_message_is_not_a_request_of_its_own():
    # A long list repeats its template on every line: each letter pattern counts
    # log(1 + n) and the text term shrinks with length, so a list is never read
    # as a near-certain action. None of these is a seed; before, each went to
    # an action with P = 1.0 (use_tool, web_read, project_task, recall).
    shops = ["soap", "rice", "tea", "oil", "salt"]
    prices = "\n".join(
        f"Item {i}: {shops[i % 5]} costs Rs {50 + 7 * i} at shop {i % 12 + 1}." for i in range(100)
    )
    assert fahm.understand(prices + "\nWhich shop sells item 63?").intent == "converse"
    names = ["Aisha", "Bilal", "Hamza", "Zainab", "Usman"]
    rolls = "\n".join(f"Roll {i}: {names[i % 5]} scored {30 + i % 70} in maths." for i in range(80))
    assert fahm.understand(rolls + "\nWhat did roll 42 score?").intent == "converse"
    assert fahm.understand("چائے میں چینی زیادہ ہو جائے تو کیا کریں؟").intent == "converse"
    # Still misread (travel words), but no longer with certainty.
    tickets = "\n".join(
        f"Ticket T-{i:03d}: seat {i % 40 + 1} in coach {i % 9 + 1}." for i in range(120)
    )
    assert qasd.ranked(tickets + "\nWhich coach is ticket T-077 in?")[0][1] < 0.9


def test_a_fixed_answer_needs_a_majority(monkeypatch):
    # The capabilities answer reads nothing in the message: as the likeliest
    # single reading but not more probable than the rest together, the
    # message goes on as conversation.
    ranked = [("capabilities", 0.4), ("converse", 0.35), ("recall", 0.25)]
    monkeypatch.setattr(qasd, "ranked", lambda *args, **kwargs: ranked)
    assert fahm.understand("Tum pagal ho?").intent == "converse"
    ranked[:] = [("capabilities", 0.6), ("converse", 0.4)]
    assert fahm.understand("Tum kya kar sakte ho?").intent == "capabilities"


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


@pytest.mark.parametrize(
    "text,value",
    [
        ("2 ki power 10 kitni hoti hai?", 1024),
        ("3 to the power of 4", 81),
        ("12 x 13 kitna hai", 156),
        ("What is 987654321 × 123456789?", 121932631112635269),
    ],
)
def test_operators_said_in_words_are_read(text, value):
    assert calc.evaluate(calc.find_expression(text)) == value


def test_a_hex_literal_is_not_a_product():
    assert calc.find_expression("0x1f") is None


def test_one_question_is_not_split_into_prayer_time_lookups():
    # "combine Zuhr and Asr" is one fiqh question, not "Zuhr" and "Asr prayers".
    assert fahm.understand_parts("Can a traveller combine Zuhr and Asr prayers?") is None
    assert fahm.understand("Can a traveller combine Zuhr and Asr prayers?").intent == "converse"


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


@pytest.mark.parametrize(
    "text,expected",
    [
        # A count of ayahs is a range from the start, or from the end when asked.
        ("Surah Yasin ki pehli 5 ayaat Arabic mein", (36, 1, 5)),
        ("surah 36 ki pehli 5 ayaat", (36, 1, 5)),
        ("first 3 verses of surah mulk", (67, 1, 3)),
        ("Surah Baqarah ki last 3 ayat", (2, 284, 286)),
        ("Surah Mulk ki aakhri 2 ayat Hindi mein", (67, 29, 30)),
        # A number after an ayah word, or alone, is that ayah.
        ("Surah Yasin 5", (36, 5, 5)),
        ("Surah Yasin ayat 5", (36, 5, 5)),
        ("Surah Yasin ki 5vi ayat", (36, 5, 5)),
    ],
)
def test_counts_of_ayahs_are_ranges(text, expected):
    reference = quran.parse_reference(text)
    assert (reference.surah, reference.start, reference.end) == expected


@pytest.mark.parametrize(
    "text,edition",
    [
        ("Surah Fatiha Urdu tarjuma ke saath", "ur"),
        ("Surah Mulk Hindi mein", "hi"),
        ("Give the Arabic text of Quran 2:285", "ar"),
        ("Surah Ikhlas ka Arabic aur Urdu tarjuma", "ur"),
        ("Surah Ikhlas", None),
    ],
)
def test_the_translation_the_person_names_is_used(text, edition):
    assert quran.requested_translation(text) == edition


async def test_a_named_translation_is_fetched(agent, monkeypatch):
    seen = {}

    async def fetch(reference, language):
        seen["language"] = language
        return {
            "reference": reference.label,
            "surah_arabic": "الفاتحة",
            "ayahs": [{"number": 1, "arabic": "ayah-1", "translation": "urdu-1"}],
            "translation": "Fateh Muhammad Jalandhry",
            "source": "api.alquran.cloud (Tanzil Uthmani text)",
            "shown": (1, 1),
            "requested": 1,
            "total": 7,
        }

    monkeypatch.setattr(quran, "fetch", fetch)
    await agent.execute("Surah Fatiha 1 Urdu tarjuma ke saath")
    assert seen["language"] == "ur"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("How many ayat are in the whole Quran?", "**6236 ayahs**"),
        ("Surah Al-Baqarah mein kitni ayat hain?", "**286 ayaat**"),
    ],
)
async def test_counts_come_from_the_surah_index(agent, monkeypatch, text, expected):
    async def fetch(reference, language):
        raise AssertionError("a count is read from the surah index, not fetched")

    monkeypatch.setattr(quran, "fetch", fetch)
    result = await agent.execute(text)
    assert expected in result["result"]
    assert result["orchestration"]["intent"] == "quran_count"


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
    # The goal's measure: answered with no hosted-model call (usage.lisan).
    assert result["usage"]["lisan"] == {
        "calls": 0,
        "zero_call": True,
        "tasks": {},
        "family": "compute",
        "language": "en",
        "source": "mizan",
        "verified": True,
    }


async def test_the_working_is_shown_when_asked_and_comes_from_mizan(agent):
    # The live benchmark (27 Oct): "17*23 and explain step by step" got the
    # result alone. The steps are MIZAN's own evaluation, with no model call.
    result = await agent.execute("What is 17*23 and explain step by step?")
    text = result["result"]
    assert "**391**" in text and "17 × 23 = 17 × 20 + 17 × 3" in text
    assert "340 + 51 = 391" in text and agent.ai_client.requests == []
    plain = await agent.execute("What is 17*23?")
    assert "17 × 20" not in plain["result"]


async def test_a_root_question_is_answered_from_the_corpus_not_the_model(agent, monkeypatch):
    # The live benchmark (27 Oct): the chat's roots came from the model while the
    # API gave wrong ones. Both now read the same corpus (Sarf).
    from tadbir import fahm, sarf

    corpus = sarf.build(
        "1:1:1:1\tكَاتِبٌ\tN\tACT_PCPL|VF:1|ROOT:كتب|LEM:كاتِب|M|NOM\n"
        "1:1:2:1\tكَتَبَ\tV\tPERF|VF:1|ROOT:كتب|LEM:كَتَبَ|3MS\n",
        ["a scribe", "(he) wrote"],
    )

    async def ready():
        return corpus

    monkeypatch.setattr(sarf, "corpus", ready)
    understood = fahm.understand("كاتب ka root kya hai?")
    assert understood.intent == "sarf" and understood.entities["words"] == ["كاتب"]
    assert fahm.understand("ما جذر كلمة كاتب؟").entities["words"] == ["كاتب"]
    assert fahm.understand("قل هو الله أحد").intent != "sarf"
    result = await agent.execute("كاتب ka root kya hai?")
    assert "ك-ت-ب" in result["result"] and "فَاعِل" in result["result"]
    assert result["task_verified"] and agent.ai_client.requests == []


def test_steps_follow_the_order_of_evaluation_exactly():
    from tadbir import calc

    assert calc.steps("2+3*4") == ["3 × 4 = 12", "2 + 12 = 14"]
    assert calc.steps("(1/3+1/6)*12") == [
        "1 ÷ 3 = 1/3",
        "1 ÷ 6 = 1/6",
        "1/3 + 1/6 = 1/2",
        "1/2 × 12 = 6",
    ]
    assert calc.steps("125*204")[0] == "125 × 204 = 125 × 200 + 125 × 4"


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


async def test_run_this_code_runs_the_program_shown_earlier_in_the_chat(agent, monkeypatch):
    # Production: "Run this code" after an answer with a program was answered
    # "I have no tool access"; MIZAN now runs that program itself.
    fake = tools(
        agent, monkeypatch, workspace_run={"stdout": "False\n", "stderr": "", "exit_code": 0}
    )
    earlier = (
        "Here is the sketch:\n```python\nnew_code = compile(src)\n```\n"
        "And the program:\n```python\ndef evaluate_me(p):\n    return not p\n\n"
        "print(evaluate_me(True))\n```"
    )
    history = [
        {"role": "user", "content": "Write evaluate_me"},
        {"role": "assistant", "content": earlier},
    ]
    result = await agent.execute("Run this code", {"history": history})
    assert [name for name, _ in fake.calls] == ["workspace_run"]
    # The whole program, not the fragment before it.
    assert fake.calls[0][1]["command"].startswith("def evaluate_me(p):")
    assert "False" in result["result"]
    assert agent.ai_client.requests == []


async def test_run_this_code_with_no_program_in_the_chat_runs_nothing(agent, monkeypatch):
    fake = tools(agent, monkeypatch, workspace_run={"stdout": "", "stderr": "", "exit_code": 0})
    await agent.execute(
        "Execute the above program", {"history": [{"role": "assistant", "content": "Hello"}]}
    )
    assert fake.calls == []


@pytest.mark.parametrize("text", ["Execute the above program", "Ab isko run karo", "Run it please"])
def test_run_requests_without_code_are_follow_ups(text):
    assert fahm.understand(text).intent == "run_follow"


async def test_a_wrong_sandbox_result_is_not_marked_verified(agent, monkeypatch):
    tools(agent, monkeypatch, workspace_run={"stdout": "42\n", "stderr": "", "exit_code": 0})
    result = await agent.execute("Python me 2**10 run karo")
    assert result["task_verified"] is False


async def test_lisan_writes_code_and_mizan_repairs_failures(agent, monkeypatch):
    agent.ai_client = ScriptedProvider(
        [
            "```python\nprint(fib(10)\n```",
            "```python\nprint([0, 1, 1, 2, 3])\n```",
            "```python\nf = [0, 1]\nwhile len(f) < 5: f.append(f[-1] + f[-2])\nprint(f)\n```",
        ]
    )
    fake = tools(
        agent,
        monkeypatch,
        workspace_run=[
            {"stdout": "", "stderr": "SyntaxError: '(' was never closed", "exit_code": 1},
            {"stdout": "[0, 1, 1, 2, 3]\n", "stderr": "", "exit_code": 0, "duration_ms": 30},
            {"stdout": "[0, 1, 1, 2, 3]\n", "stderr": "", "exit_code": 0, "duration_ms": 20},
        ],
    )
    result = await agent.execute(
        "Ek python program likho jo 5 fibonacci numbers print kare aur run karo"
    )
    assert [name for name, _ in fake.calls] == ["workspace_run"] * 3
    assert fake.calls[1][1]["command"] == "print([0, 1, 1, 2, 3])"
    # Code, its repair, and an independent program written without seeing it.
    assert len(agent.ai_client.requests) == 3
    assert "Program:" not in agent.ai_client.requests[2]["messages"][0]["content"]
    assert "tools" not in agent.ai_client.requests[0] or not agent.ai_client.requests[0].get(
        "tools"
    )
    assert "SyntaxError" in agent.ai_client.requests[1]["messages"][0]["content"]
    assert result["task_verified"] and "2 " in result["result"]


async def test_capabilities_come_from_the_registry_not_the_model(agent):
    result = await agent.execute("Hai tumhare paas tools?")
    assert agent.ai_client.requests == []
    assert "sandbox" in result["result"] and "web search" in result["result"]
    # It lists what MIZAN can do; it never answers "yes" to a question it did not read.
    assert not result["result"].startswith(("Yes", "Haan"))


async def test_a_salam_is_returned_by_mizan_with_no_model_call(agent):
    result = await agent.execute("السلام علیکم")
    assert agent.ai_client.requests == []
    assert result["result"] == phrase("salam", "ur")
    assert result["result"].startswith("وعلیکم السلام ورحمۃ اللہ وبرکاتہ")
    assert result["orchestration"]["intent"] == "salam"
    assert result["usage"]["lisan"]["zero_call"] and result["usage"]["lisan"]["family"] == "salam"


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
    # mizan (default): the model answers in words and is given no tools at all.
    agent.ai_client = ScriptedProvider(["Recursion is a function calling itself."])
    result = await agent.execute("Explain recursion simply")
    assert result["result"] == "Recursion is a function calling itself."
    assert not agent.ai_client.requests[0].get("tools")
    assert "no tools" in agent.ai_client.requests[0]["system"]
    # MIZAN read it as conversation and the model answered: one teacher call.
    lisan = result["usage"]["lisan"]
    assert (lisan["family"], lisan["language"], lisan["source"]) == (
        "converse",
        "en",
        "language_model",
    )
    assert lisan["tasks"] == {"answer": 1} and lisan["zero_call"] is False
    # Tadbir still runs tools itself afterwards: the flag ends with the run.
    assert agent.get_tool_schemas()
    # hybrid: what MIZAN does not recognise goes to the model-driven loop.
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "hybrid")
    agent.ai_client = ScriptedProvider(["It calls itself on a smaller input."])
    await agent.execute("Explain recursion simply")
    assert agent.ai_client.requests[0].get("tools")
    # strict is the former name of mizan.
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "strict")
    agent.ai_client = ScriptedProvider(["Words only."])
    await agent.execute("Explain recursion simply")
    assert not agent.ai_client.requests[0].get("tools")
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    agent.ai_client = ScriptedProvider(["4"])
    legacy = await agent.execute("2+2?")
    assert (
        len(agent.ai_client.requests) == 1 and legacy["usage"]["orchestrator"] == "language_model"
    )
    # MIZAN did not read it (llm mode): the model answered, the family is unplaced.
    assert legacy["usage"]["lisan"]["family"] == "unplaced"
    assert legacy["usage"]["lisan"]["tasks"] == {"answer": 1}
    assert legacy["usage"]["lisan"]["zero_call"] is False


async def test_tools_mizan_may_not_use_are_left_to_the_agent_loop(agent, monkeypatch):
    monkeypatch.setattr(agent, "_chat_tool_allowed", lambda name: name != "workspace_run")
    agent.ai_client = ScriptedProvider(["I can't run code here."])
    result = await agent.execute("```python\nprint(1)\n```\nrun karo")
    assert result["usage"]["orchestrator"] == "language_model"


async def test_a_window_program_is_compiled_not_run(agent, monkeypatch):
    # The sandbox has no screen: MIZAN checks the program compiles and says so,
    # shows the code, and never claims it ran (no repair calls are wasted).
    ui = "```python\nimport tkinter as tk\nroot = tk.Tk()\nroot.mainloop()\n```"
    agent.ai_client = ScriptedProvider([ui])
    fake = tools(agent, monkeypatch, workspace_run={"stdout": "main.py compiles\n", "exit_code": 0})
    result = await agent.execute("Help me write a Python script with a window")
    assert result["orchestration"]["intent"] == "build_and_run"
    assert (
        "compile(" in fake.calls[0][1]["command"] and "mainloop" not in fake.calls[0][1]["command"]
    )
    assert "tkinter" in result["result"] and "import tkinter" in result["result"]
    assert result["completion_status"] != "verified_by_mizan"
    assert len(agent.ai_client.requests) == 1


async def test_mizan_understands_a_program_request_without_lisan(agent, monkeypatch):
    fib = "```python\na, b = 0, 1\nfor _ in range(50):\n    a, b = b, a + b\nprint(a)\n```"
    agent.ai_client = ScriptedProvider([fib, fib])
    fake = tools(
        agent, monkeypatch, workspace_run={"stdout": "12586269025\n", "stderr": "", "exit_code": 0}
    )
    result = await agent.execute("Fibonacci series ka 50th number kya hai?")
    assert result["orchestration"]["intent"] == "build_and_run"
    assert result["orchestration"]["entities"].get("understood_by") is None  # Fahm, alone
    # Lisan writes the code and an independent check; nothing was mapped.
    assert len(agent.ai_client.requests) == 2
    assert fake.calls[0][0] == "workspace_run" and "12586269025" in result["result"]


async def test_lisan_only_maps_wording_and_mizan_validates_it(agent, monkeypatch, unplaced_wording):
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


async def test_rejected_mapping_falls_back_to_the_agent_loop(agent, unplaced_wording):
    agent.ai_client = ScriptedProvider(['{"intent":"converse"}', "Python is a language."])
    result = await agent.execute("Explain what Python code is used for")
    assert result["usage"]["orchestrator"] == "language_model"
    assert result["result"] == "Python is a language."


async def test_a_question_is_answered_in_words_without_a_mapping_call(agent):
    agent.ai_client = ScriptedProvider(["Python is a language."])
    result = await agent.execute("Explain what Python code is used for")
    assert len(agent.ai_client.requests) == 1 and not agent.ai_client.requests[0].get("tools")
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
    lisan = result["usage"]["lisan"]
    assert lisan["calls"] == 4 and sum(lisan["tasks"].values()) == 4
    assert "answer" not in lisan["tasks"]  # every call was one of MIZAN's Lisan tasks
    assert lisan["family"] == "build_project" and lisan["source"] == "mizan"
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
    assert result["usage"]["orchestrator"] == "language_model"


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


def test_lisan_may_map_project_wording_and_other_stacks_go_to_the_model():
    parsed = {"intent": "build_project", "kind": "web"}
    understood = fahm.validate_parsed(
        parsed, "mujhe ek todo list chahiye jo browser mein chale", "en"
    )
    assert understood is not None and understood.entities["kind"] == "web"
    # React is beyond MIZAN's blueprints: the coding handoff builds it (kind "stack").
    react = fahm.validate_parsed(parsed, "mujhe React mein dashboard chahiye", "en")
    assert react is not None and react.entities["kind"] == "stack"
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
    # Who did it is metadata, never a footer in the answer.
    assert "Katib" not in result["result"] and result["completion_status"] == "verified_by_mizan"
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


async def test_verified_wording_is_learned_and_reused_without_asking_lisan(
    agent, monkeypatch, unplaced_wording
):
    fib = "```python\na, b = 0, 1\nfor _ in range(50):\n    a, b = b, a + b\nprint(a)\n```"
    agent.ai_client = ScriptedProvider(
        [
            '{"intent":"build_and_run","request":"print the 50th Fibonacci number",'
            '"language":"python"}',
            fib,
            fib,
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
    # The code and its independent check only, no mapping call.
    assert second["orchestration"]["language_model_calls"] == 2
    assert len(agent.ai_client.requests) == 5
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
    # A user's learning lives with that user's own agents, not the shared ones.
    mine = await main.chat_agent_for(alice, khalifah)
    assert mine is not khalifah and len(mine._agent_registry) == len(team)
    learned = fahm.Understanding("web_search", "en", 0.6, {"understood_by": "lisan"})
    taallum.learn(mine.adaptive, "alice", "cricket score batao abhi", learned, True)
    assert taallum.summary(khalifah.adaptive, "alice")["examples"] == 0
    view = await main.tadbir_learning(alice)
    assert view["wording"]["examples"] == 1
    assert any(r["agent"] == "Katib" and r["specialist"] for r in view["routing"])
    assert (await main.forget_tadbir_wording(alice))["forgotten"]
    assert (await main.tadbir_learning(alice))["wording"]["examples"] == 0


# ── Amal: any other action, with MIZAN choosing the tool ─────────────────

ISSUES_TOOL = {
    "name": "mcp__github__list_issues",
    "description": "List the open issues of a GitHub repository",
    "input_schema": {
        "type": "object",
        "properties": {"repo": {"type": "string", "minLength": 1}},
        "required": ["repo"],
        "additionalProperties": False,
    },
}


async def test_mizan_picks_the_tool_and_validates_lisans_arguments(agent, monkeypatch):
    shell = {"name": "bash", "description": "list issues of a github repository via shell"}
    monkeypatch.setattr(agent, "get_tool_schemas", lambda: [shell, ISSUES_TOOL])
    agent.ai_client = ScriptedProvider(
        [
            '{"steps":[{"intent":"use_tool","need":"list GitHub issues","text":"..."}]}',
            "{}",  # misses the required repo: MIZAN rejects it
            '{"repo": "mizan"}',
            "There are two open issues: Login bug and Slow chat.",
        ]
    )
    fake = tools(
        agent,
        monkeypatch,
        mcp__github__list_issues={"issues": [{"title": "Login bug"}, {"title": "Slow chat"}]},
    )
    result = await agent.execute("Mere mizan repo ke open issues kaun se hain?")
    assert fake.calls == [("mcp__github__list_issues", {"repo": "mizan"})]  # never the shell
    assert "rejected" in agent.ai_client.requests[2]["system"]
    assert result["result"].startswith("There are two open issues")
    assert result["completion_status"] == "evidence_observed"  # ran, not verified
    assert not any(r.get("tools") for r in agent.ai_client.requests)


def test_tool_arguments_are_checked_against_the_schema():
    schema = ISSUES_TOOL["input_schema"]
    assert amal.problems({"repo": "mizan"}, schema) == []
    assert amal.problems({}, schema) and amal.problems({"repo": 5, "x": 1}, schema)
    assert amal.problems("repo", schema) == ["the arguments must be a JSON object"]
    assert amal.problems({"anything": 1}, {"type": "nonsense-type"}) == []  # malformed schema
    assert amal.restrict({"repo": "m", "name": "x"}, schema) == {"repo": "m"}
    assert amal.restrict({"name": "x"}, {"type": "object", "properties": {}}) == {}


async def test_lisan_plans_several_steps_and_mizan_runs_each(agent, monkeypatch):
    async def fetch(reference, language):
        return {
            "reference": reference.label, "collection": "Sahih al-Bukhari",
            "collection_arabic": "صحيح البخاري", "sahih_collection": True, "section": "",
            "book": 1, "in_book": 1, "arabic": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
            "translation": "Actions are by intentions.", "translation_language": "English",
            "clipped": False, "grades": [], "narrations": [], "link": "", "source": hadith.SOURCE,
        }  # fmt: skip

    monkeypatch.setattr(hadith, "fetch", fetch)
    agent.ai_client = ScriptedProvider(
        [
            '{"steps":[{"intent":"compute","expression":"12*12","text":"twelve squared"},'
            '{"intent":"hadith","collection":"bukhari","number":1,"text":"the first hadith"},'
            '{"intent":"delete_everything"}]}'
        ]
    )
    result = await agent.execute("Twelve squared kitna, phir Bukhari ki hadith 1 bhi dikhana")
    assert result["orchestration"]["intent"] == "compound"
    assert result["orchestration"]["entities"]["understood_by"] == "lisan_plan"
    assert "**144**" in result["result"] and "بِالنِّيَّاتِ" in result["result"]
    assert len(agent.ai_client.requests) == 1  # one mapping call; MIZAN did the rest


# ── Editing the selected project ─────────────────────────────────────────

PAGE = "<html><head><link rel='stylesheet' href='style.css'></head><body><button id='go'>Go</button><script src='app.js'></script></body></html>\n"


def project_tools(agent, monkeypatch, runs):
    files = {"index.html": PAGE, "app.js": "document.getElementById('go').onclick = () => 1;\n", "style.css": "button { color: blue; }\n"}  # fmt: skip
    calls = []

    async def fake(name, params):
        calls.append((name, deepcopy(params)))
        if name == "workspace_glob":
            return {"files": [{"path": p, "size": len(c)} for p, c in files.items()], "total": 3}
        if name == "workspace_read":
            return {
                "path": params["path"],
                "content": files[params["path"]],
                "sha256": "sha-" + params["path"],
            }
        if name == "workspace_write":
            files[params["path"]] = params["content"]
            return {"path": params["path"], "sha256": "new-" + params["path"]}
        if name == "workspace_run":
            return runs.pop(0)
        return {"id": "c1"}

    monkeypatch.setattr(agent, "_execute_tool_safe", fake)
    monkeypatch.setattr("workspace.context.bound_workspace_id", lambda: "w9")
    names = [
        "workspace_glob",
        "workspace_read",
        "workspace_write",
        "workspace_run",
        "workspace_checkpoint",
    ]
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {}} for n in names],
    )
    return files, calls


async def test_mizan_edits_the_selected_project_checks_and_repairs(agent, monkeypatch):
    ok = {"stdout": "", "stderr": "", "exit_code": 0}
    broken = {"stdout": "", "stderr": "SyntaxError: Unexpected token", "exit_code": 1}
    files, calls = project_tools(agent, monkeypatch, [broken, ok])
    agent.ai_client = ScriptedProvider(
        [
            "```style.css\nbutton { color: red; }\n```\n```app.js\ndocument.getElementById('go').onclick = () => {;\n```",
            "```app.js\ndocument.getElementById('go').onclick = () => 2;\n```",
        ]
    )
    understood = fahm.understand("Button ka color red karo")
    assert understood.intent == "edit_project"
    result = await agent.execute("Button ka color red karo")
    assert files["style.css"] == "button { color: red; }\n" and "=> 2" in files["app.js"]
    writes = [params for name, params in calls if name == "workspace_write"]
    assert writes[0]["expected_sha256"] == "sha-style.css"  # never overwrites a newer file
    assert writes[-1]["expected_sha256"] == "new-app.js"  # the repair follows the first write
    assert (
        "workspace_run",
        {"command": "node --check app.js", "language": "shell", "timeout_s": 60},
    ) in calls
    assert result["completion_status"] == "verified_by_mizan"
    assert (
        "-button { color: blue; }" in result["result"]
        and "+button { color: red; }" in result["result"]
    )
    assert "SyntaxError" in agent.ai_client.requests[1]["messages"][0]["content"]


async def test_a_build_request_in_a_used_project_becomes_an_edit(agent, monkeypatch):
    files, calls = project_tools(agent, monkeypatch, [])
    agent.ai_client = ScriptedProvider(["```about.html\n<p>About</p>\n```"])
    result = await agent.execute("Ek about page banao")
    assert files["about.html"] == "<p>About</p>\n"
    assert not any(name == "workspace_create" for name, _ in calls)
    assert "about.html" in result["result"]


def long_project(agent, monkeypatch):
    """A project whose app.js (about 30 KB) is longer than Lisan may rewrite whole."""
    body = "".join(f"function step{i}() {{ return {i}; }}\n" for i in range(1000))
    files = {"index.html": PAGE, "app.js": body + "// the end of app.js\n"}
    calls = []

    async def fake(name, params):
        calls.append((name, deepcopy(params)))
        if name == "workspace_glob":
            return {"files": [{"path": p, "size": len(c)} for p, c in files.items()], "total": 2}
        if name == "workspace_read":
            return {"path": params["path"], "content": files[params["path"]], "sha256": "sha"}
        if name == "workspace_write":
            files[params["path"]] = params["content"]
            return {"path": params["path"], "sha256": "new"}
        if name == "workspace_run":
            return {"stdout": "", "stderr": "", "exit_code": 0}
        return {"id": "c1"}

    monkeypatch.setattr(agent, "_execute_tool_safe", fake)
    monkeypatch.setattr("workspace.context.bound_workspace_id", lambda: "w9")
    names = ["workspace_glob", "workspace_read", "workspace_write", "workspace_run"]
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {}} for n in names],
    )
    assert len(files["app.js"]) > lisan_module.WHOLE_FILE_CHARS
    return files, calls


async def test_a_long_file_changes_only_by_edit_blocks_and_keeps_its_tail(agent, monkeypatch):
    files, calls = long_project(agent, monkeypatch)
    before = files["app.js"]
    agent.ai_client = ScriptedProvider(
        [
            "```app.js edit\n<<<<<<< SEARCH\nfunction step7() { return 7; }\n=======\n"
            "function step7() { return 'seven'; }\n>>>>>>> REPLACE\n```"
        ]
    )
    result = await agent.execute("Update the step7 function in app.js")
    assert files["app.js"] == before.replace("return 7;", "return 'seven';", 1)
    assert files["app.js"].endswith("// the end of app.js\n")
    shown = agent.ai_client.requests[0]["messages"][0]["content"]
    assert "long file: change it only with edit blocks" in shown
    assert "+function step7() { return 'seven'; }" in result["result"]


async def test_a_whole_file_reply_for_a_long_file_is_never_saved(agent, monkeypatch):
    files, calls = long_project(agent, monkeypatch)
    before = files["app.js"]
    cut = before[:12000] + "function added() {}\n"  # the model repeated only part of it
    agent.ai_client = ScriptedProvider([f"```app.js\n{cut}```", f"```app.js\n{cut}```"])
    await agent.execute("app.js mein ek added function jodo")
    assert files["app.js"] == before
    assert not any(name == "workspace_write" for name, _ in calls)


async def test_an_edit_that_does_not_match_exactly_once_is_refused(agent, monkeypatch):
    files, calls = long_project(agent, monkeypatch)
    before = files["app.js"]
    agent.ai_client = ScriptedProvider(
        [
            "```app.js edit\n<<<<<<< SEARCH\nreturn\n=======\nyield\n>>>>>>> REPLACE\n```",
            "```app.js edit\n<<<<<<< SEARCH\nno such line\n=======\nx\n>>>>>>> REPLACE\n```",
        ]
    )
    result = await agent.execute("app.js mein step7 function badlo")
    assert files["app.js"] == before
    # Hinglish request, Hinglish note: which file's edits did not apply, and why.
    assert (
        "laagu nahi hue" in result["result"]
        and "app.js: old_string was not found" in result["result"]
    )


async def test_a_reply_cut_at_the_output_limit_saves_nothing(agent, monkeypatch):
    files, calls = project_tools(agent, monkeypatch, [])
    before = dict(files)
    cut = LLMResponse(
        [ContentBlock(type="text", text="```style.css\nbutton { color: re")],
        model="fixture",
        stop_reason="max_tokens",
    )
    agent.ai_client = ScriptedProvider([cut])
    result = await agent.execute("Button ka color red karo")
    assert files == before
    assert not any(name == "workspace_write" for name, _ in calls)
    assert "output limit" in result["result"]


async def test_typescript_files_are_parsed_by_esbuild_or_reported_not_run(agent, monkeypatch):
    from tadbir.engine import Tadbir

    runs = [{"stdout": "", "stderr": "esbuild is not in the sandbox", "exit_code": 127}]
    fake = tools(agent, monkeypatch, workspace_run=runs)
    agent._last_tool_results = []  # set by execute(); this calls the check directly
    changes = {"src/App.tsx": "export const App = () => <p/>;\n", "src/util.ts": "export {};\n"}
    checks, problem = await Tadbir(agent)._check_edit(changes, changes, sorted(changes))
    assert checks == [
        ("`src/App.tsx, src/util.ts` parses (esbuild)", None, "esbuild is not in the sandbox")
    ]
    assert problem == ""
    command = fake.calls[0][1]["command"]
    assert "node_modules/.bin/esbuild" in command and "src/App.tsx src/util.ts" in command
    fake.results["workspace_run"] = [{"stdout": "", "stderr": "x.ts:1:5: ERROR", "exit_code": 1}]
    checks, problem = await Tadbir(agent)._check_edit(
        {"x.ts": "let = ;"}, {"x.ts": "let = ;"}, ["x.ts"]
    )
    assert checks[0][1] is False and "x.ts:1:5: ERROR" in problem


def test_edit_blocks_are_read_and_applied_exactly():
    reply = (
        "```a.py edit\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
        "<<<<<<< SEARCH\ny = 1\n=======\n>>>>>>> REPLACE\n```\n"
        "```b.py\nprint('whole')\n```"
    )
    edits = project.extract_edits(reply, {"a.py", "b.py"})
    assert edits == {"a.py": [("x = 1", "x = 2"), ("y = 1", "")]}
    # An edit block is never taken for a whole file.
    assert project.extract_files(reply, {"a.py", "b.py"}) == {"b.py": "print('whole')\n"}
    changed, refused = project.apply_edits(edits, {"a.py": "x = 1\ny = 1\nz = 1\n"})
    assert changed == {"a.py": "x = 2\n\nz = 1\n"} and refused == []
    twice = {"a.py": [("1", "2")]}
    changed, refused = project.apply_edits(twice, {"a.py": "1 1"})
    assert changed == {} and "matches 2 places" in refused[0]
    assert lisan_module.long_files({"s": "x" * 12000, "l": "x" * 12001}) == {"l"}


def test_only_safe_project_paths_are_written():
    assert project.editable("src/app.js") and not project.editable("../etc/passwd")
    assert not project.editable("node_modules/x.js") and not project.editable(".env")
    reply = "```app.js\nok\n```\n```src/new.css\na{}\n```\n```../evil.js\nx\n```"
    assert set(project.extract_files(reply, {"app.js"}, new_files=True)) == {
        "app.js",
        "src/new.css",
    }
    assert set(project.extract_files(reply, {"app.js"})) == {"app.js"}


# ── Remember: the user's own words, kept as a note tied to the chat ─────


def _notes(agent, source):
    import sqlite3

    with sqlite3.connect(agent.memory.db_path) as conn:
        return conn.execute("SELECT content FROM memories WHERE source = ?", (source,)).fetchall()


@pytest.fixture
def with_memory(agent, tmp_path):
    from memory.dhikr import DhikrMemorySystem

    agent.memory = DhikrMemorySystem(str(tmp_path / "notes.db"))
    return agent


async def test_remember_keeps_the_users_own_words_tied_to_the_chat(with_memory, monkeypatch):
    agent = with_memory
    fake = tools(agent, monkeypatch)
    text = "Yaad rakhna meri beti ka naam Maryam hai"
    result = await agent.execute(text, context={"session_id": "chat-7"})
    assert result["success"] and result.get("orchestrator") == "mizan"
    assert _notes(agent, "chat:chat-7") == [(text,)]
    assert fake.calls == []  # MIZAN keeps it itself: no tool, no model
    assert "Daftar" in result["result"]


async def test_what_the_user_said_in_this_chat_is_recalled_from_the_chat(agent, monkeypatch):
    # Working memory before long-term memory: the chat itself holds the answer,
    # so no memory search runs, and every earlier statement is given in order.
    fake = tools(agent, monkeypatch)
    history = [
        {"role": "user", "content": "My son's name is Ibrahim."},
        {"role": "assistant", "content": "MashaAllah, a beautiful name."},
        {"role": "user", "content": "How long should I walk each day?"},
        {"role": "assistant", "content": "About 30 to 45 minutes."},
    ]
    result = await agent.execute(
        "What did I say my son's name is?", context={"session_id": "c1", "history": history}
    )
    assert result.get("orchestrator") == "mizan"
    assert "Ibrahim" in result["result"]
    assert fake.calls == []


def test_chat_statements_are_given_only_when_one_speaks_of_the_request():
    from tadbir.engine import _said_in_chat

    history = [
        {"role": "user", "content": "The Wi-Fi password is sabr2025."},
        {"role": "user", "content": "Sorry, I changed it: it is now shukr2026."},
    ]
    said = _said_in_chat("What's the Wi-Fi password?", history)
    assert said == [turn["content"] for turn in history]  # the correction comes with it
    assert _said_in_chat("What is the capital of Japan?", history) == []


async def test_a_stateless_chat_saves_no_note_and_says_so(with_memory, monkeypatch):
    from memory import stateless

    agent = with_memory
    tools(agent, monkeypatch)
    with stateless.bind():
        result = await agent.execute(
            "Yaad rakhna meri beti ka naam Maryam hai", context={"session_id": "chat-8"}
        )
    assert _notes(agent, "chat:chat-8") == []
    assert "stateless" in result["result"] and "Daftar" not in result["result"]


async def test_a_watcher_task_never_saves_a_note(with_memory, monkeypatch):
    from security import approvals

    agent = with_memory
    tools(agent, monkeypatch)
    with approvals.unattended("owner", "watch-1", "watcher"):
        await agent.execute("Remember that my son is allergic to milk", context={})
    assert _notes(agent, "chat") == []


async def test_an_answer_says_which_words_from_other_chats_it_used(agent, monkeypatch):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    agent.ai_client = ScriptedProvider(["Maryam's first day — may Allah make it easy."])
    recalled = [
        {
            "message_id": "m1",
            "session_id": "chat-old",
            "created_at": "2026-10-20T08:00:00Z",
            "content": "My daughter Maryam starts school next week",
            "source": "prior_user_statement",
        }
    ]
    result = await agent.execute(
        "How should I prepare her for it?",
        context={"session_id": "chat-new", "conversation_memory": recalled},
    )
    assert result["usage"]["recalled"] == [
        {
            "session_id": "chat-old",
            "created_at": "2026-10-20T08:00:00Z",
            "content": "My daughter Maryam starts school next week",
        }
    ]
    without = await _plain_answer(agent)
    assert "recalled" not in without["usage"]


async def _plain_answer(agent):
    agent.ai_client = ScriptedProvider(["Wa alaikum assalam."])
    return await agent.execute("Assalamu alaikum", context={"session_id": "chat-new"})


async def test_cross_chat_recall_can_be_turned_off(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from memory.dhikr import DhikrMemorySystem

    chat = DhikrMemorySystem(str(tmp_path / "chat.db"))
    monkeypatch.setattr(main, "memory", chat)
    monkeypatch.setattr(main, "chat_history", AsyncMock(return_value=[]))
    user = SimpleNamespace(user_id="u-1")
    await chat.authorize_session("old", "u-1", create=True)
    await chat.save_message("old", "user", "My daughter Maryam starts school next week")

    on = await main.chat_context(user, "new", {}, None, "Maryam school")
    assert on["conversation_memory"]
    await chat.set_chat_preference("u-1", "cross_chat_recall", "off")
    off = await main.chat_context(user, "new", {}, None, "Maryam school")
    assert off["conversation_memory"] == []


def test_the_agi_tests_paraphrases_reach_the_same_recipe():
    # The 27 October API benchmark: surah counts in English and Arabic went to
    # a verse search, and an Urdu question about boiling water to morphology.
    surahs = [
        "How many surahs are in the Quran?",
        "Quran me kitni surtein hain?",
        "قرآن مجید میں کتنی سورتیں ہیں؟",
        "كم عدد سور القرآن الكريم؟",
    ]
    assert {fahm.understand(text).intent for text in surahs} == {"quran_count"}
    assert fahm.understand("سطح سمندر پر پانی کتنے ڈگری سیلسیس پر ابلتا ہے؟").intent != "sarf"
    assert fahm.understand("كاتب کا مادہ کیا ہے؟").intent == "sarf"


# ── Coding beyond MIZAN's recipes: the model with the project's tools only ──

HANDOFF_TOOLS = [
    "workspace_glob", "workspace_read", "workspace_write", "workspace_edit", "workspace_run",
    "workspace_create", "workspace_checkpoint", "workspace_sandbox", "web_search",
]  # fmt: skip


def tool_use(name, call_id="t1", **arguments):
    return LLMResponse(
        [ContentBlock(type="tool_use", id=call_id, name=name, input=arguments)],
        model="fixture",
        stop_reason="tool_use",
    )


@pytest.fixture
def handoff(agent, monkeypatch, tmp_path):
    """A real project store for one signed-in person, an interactive chat that answers
    approval prompts, and project tools that act on that store."""
    from agents.base import BaseAgent
    from security.approvals import ApprovalContext, bind_approvals
    from security.auth import TokenPayload, bind_principal, reset_principal
    from workspace import context as workspace_context
    from workspace.store import WorkspaceStore

    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    user = TokenPayload("amina", "Amina", ["user"], 9999999999, 0, "t")
    store = WorkspaceStore(user.user_id)
    calls, events = [], []

    async def act(name, params):
        calls.append((name, deepcopy(params)))
        bound = workspace_context.bound_workspace_id()
        if name == "workspace_create":
            return store.create(params["name"])
        if name == "workspace_write":
            return store.write(bound, params["path"], params["content"])
        if name == "workspace_glob":
            return store.glob(bound, params.get("pattern", "**/*"))
        if name == "workspace_read":
            return store.read(bound, params["path"])
        if name == "workspace_run":
            return runs.pop(0) if runs else {"stdout": "", "stderr": "", "exit_code": 0}
        if name == "workspace_checkpoint":
            return store.checkpoint(bound, params.get("message", "x"), kind="agent")
        # Anything else goes through the real gate, which refuses it in a handoff.
        return await BaseAgent._execute_tool_checked(agent, name, params)

    runs: list[dict] = []
    monkeypatch.setattr(agent, "_execute_tool_safe", act)
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {}} for n in HANDOFF_TOOLS],
    )

    async def sink(kind, payload):
        events.append((kind, payload))

    principal = bind_principal(user)
    context = ApprovalContext(user.user_id, "chat-1", "auto_edits", interactive=True)

    class Handoff:
        pass

    state = Handoff()
    state.store, state.calls, state.events, state.runs, state.context = (
        store, calls, events, runs, context,
    )  # fmt: skip
    with bind_event_sink(sink), bind_approvals(context):
        yield state
    reset_principal(principal)


def offered_tools(request):
    return sorted(tool["name"] for tool in request.get("tools") or [])


async def test_a_react_app_is_built_by_the_model_with_project_tools_only(agent, handoff):
    message = "Build me a todo app in React"
    understood = fahm.understand(message)
    assert understood.intent == "converse" and fahm.actionable(understood)
    page = '<div id="root"></div><script type="module" src="src/App.jsx"></script>\n'
    agent.ai_client = ScriptedProvider(
        [
            '{"steps":[{"intent":"build_project","kind":"stack","text":"' + message + '"}]}',
            tool_use("workspace_write", path="index.html", content=page),
            tool_use("web_search", "t2", query="react todo example"),
            tool_use("workspace_write", "t3", path="src/App.jsx", content="export default 1;\n"),
            "I made a React todo app: index.html and src/App.jsx.",
        ]
    )
    result = await agent.execute(message)
    # MIZAN made the project, bound the chat to it, and the files are in it.
    made = next(payload for kind, payload in handoff.events if kind == "workspace")
    assert made["created"] is True and result["workspace_id"] == made["workspace_id"]
    files = handoff.store.files(made["workspace_id"])
    assert files["src/App.jsx"] == b"export default 1;\n" and "index.html" in files
    # The model saw the project's tools and nothing else; web_search was refused.
    model_turns = [r for r in agent.ai_client.requests if r.get("tools")]
    assert model_turns and all("web_search" not in offered_tools(r) for r in model_turns)
    assert "workspace_write" in offered_tools(model_turns[0])
    refused = next(p for n, p in handoff.calls if n == "web_search")
    assert refused == {"query": "react todo example"}
    assert "only the project's workspace tools" in json.dumps(model_turns[-1]["messages"])
    # MIZAN checked what changed (esbuild on the JSX, the page's references) and says so.
    commands = [p["command"] for n, p in handoff.calls if n == "workspace_run"]
    assert any("src/App.jsx" in command and "esbuild" in command for command in commands)
    assert result["result"].startswith("I made a React todo app")
    assert "MIZAN's check of the project" in result["result"]
    assert "`index.html` loads only files that exist" in result["result"]
    assert result["completion_status"] == "verified_by_mizan"
    assert handoff.store.checkpoints(made["workspace_id"])[0]["kind"] == "agent"


async def test_without_someone_to_approve_a_react_request_is_answered_in_words(
    agent, handoff, monkeypatch
):
    from security.approvals import bind_approvals

    agent.ai_client = ScriptedProvider(
        [
            '{"steps":[{"intent":"build_project","kind":"stack"}]}',
            "Here is how you could structure it.",
        ]
    )
    with bind_approvals(None):  # an AGI test, a watcher: nobody answers prompts
        result = await agent.execute("Build me a todo app in React")
    assert result["result"] == "Here is how you could structure it."
    assert not any(name == "workspace_create" for name, _ in handoff.calls)
    assert not agent.ai_client.requests[-1].get("tools")  # words only, no tools


async def test_the_setting_off_answers_in_words(agent, handoff, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_AGENT", "off")
    agent.ai_client = ScriptedProvider(
        ['{"steps":[{"intent":"build_project","kind":"stack"}]}', "In words only."]
    )
    result = await agent.execute("Build me a todo app in React")
    assert result["result"] == "In words only."
    assert not handoff.calls


def test_a_question_about_building_or_a_plain_page_is_not_a_handoff():
    assert fahm.validate_parsed({"intent": "build_project", "kind": "x"}, "app", "en") is None
    react = fahm.validate_parsed(
        {"intent": "build_project", "kind": "web"}, "Build me a todo app in React", "en"
    )
    assert react is not None and react.entities["kind"] == "stack"
    page = fahm.validate_parsed(
        {"intent": "build_project", "kind": "web"}, "Make a stopwatch web page", "en"
    )
    assert page is not None and page.entities["kind"] == "web"  # MIZAN's own blueprint
    assert project.recipe_sized([{"path": "index.html", "size": 100}])
    assert not project.recipe_sized([{"path": "package.json", "size": 10}])
    many = [{"path": f"f{i}.js", "size": 10} for i in range(9)]
    assert not project.recipe_sized(many)


async def test_a_node_project_is_edited_by_the_model_with_one_repair_turn(agent, handoff):
    from workspace.context import bind_workspace, reset_workspace

    store = handoff.store
    workspace = store.create("Shop")["id"]
    store.write(workspace, "package.json", '{"name": "shop"}\n')
    store.write(workspace, "src/total.js", "export const total = 1;\n")
    handoff.runs += [
        {"stdout": "", "stderr": "SyntaxError: Unexpected token '}'", "exit_code": 1},
        {"stdout": "", "stderr": "", "exit_code": 0},
    ]
    agent.ai_client = ScriptedProvider(
        [
            tool_use("workspace_write", path="src/total.js", content="export const total = }\n"),
            "I changed the total.",
            tool_use("workspace_write", "t2", path="src/total.js", content="export const total = 2;\n"),
            "Fixed the syntax error.",
        ]
    )  # fmt: skip
    message = "Update the total in total.js to show 2"
    selected = bind_workspace(workspace)
    try:
        assert fahm.understand(message).intent == "edit_project"
        result = await agent.execute(message)
    finally:
        reset_workspace(selected)
    assert store.read(workspace, "src/total.js")["content"] == "export const total = 2;\n"
    repair = json.dumps(agent.ai_client.requests[2]["messages"])
    assert "MIZAN checked the files you changed" in repair and "SyntaxError" in repair
    assert "<<untrusted" in repair  # the check's output reaches the model as data
    assert "one turn to repair it" in result["result"]
    assert result["completion_status"] == "verified_by_mizan"
    assert "workspace_id" not in result  # the chat already had this project


async def test_plan_mode_reads_the_project_and_changes_nothing(agent, handoff):
    from workspace.context import bind_workspace, reset_workspace

    store = handoff.store
    workspace = store.create("Shop")["id"]
    store.write(workspace, "package.json", '{"name": "shop"}\n')
    handoff.context.mode = "plan"
    agent.ai_client = ScriptedProvider(
        [
            tool_use("workspace_read", path="package.json"),
            "Plan: 1. add src/cart.js 2. show the total.",
        ]
    )
    selected = bind_workspace(workspace)
    try:
        result = await agent.execute("Update the total in total.js to show 2")
    finally:
        reset_workspace(selected)
    # The plan is the model's words alone: no checks of files that did not change.
    assert result["result"] == "Plan: 1. add src/cart.js 2. show the total."
    assert "web_search" not in offered_tools(agent.ai_client.requests[0])
    assert store.files(workspace) == {"package.json": b'{"name": "shop"}\n'}
    assert result["completion_status"] != "verified_by_mizan"


async def test_plan_mode_offers_reads_only_and_a_small_project_is_still_read(
    agent, handoff, monkeypatch
):
    from workspace.context import bind_workspace, reset_workspace

    store = handoff.store
    workspace = store.create("Page")["id"]
    store.write(workspace, "index.html", "<h1>Todo</h1>\n")
    handoff.context.mode = "plan"
    # As in a real chat: plan mode offers the project's reads and nothing that writes.
    reads = ["workspace_glob", "workspace_read", "web_search"]
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {}} for n in reads],
    )
    agent.ai_client = ScriptedProvider(
        [
            tool_use("workspace_read", path="index.html"),
            "Plan: 1. add a footer under the list 2. show the year.",
        ]
    )
    selected = bind_workspace(workspace)
    try:
        message = "Add a footer that shows the current year to the page"
        assert fahm.understand(message).intent in ("edit_project", "build_project")
        result = await agent.execute(message)
    finally:
        reset_workspace(selected)
    # The model was given the project's reads and read it (MIZAN's own recipe
    # cannot write in plan mode, so it is not words without the project).
    assert "workspace_read" in offered_tools(agent.ai_client.requests[0])
    assert ("workspace_read", {"path": "index.html"}) in [
        (n, {k: v for k, v in p.items() if k == "path"}) for n, p in handoff.calls
    ]
    assert result["result"] == "Plan: 1. add a footer under the list 2. show the year."
    assert store.files(workspace) == {"index.html": b"<h1>Todo</h1>\n"}


async def test_approve_plan_and_run_goes_to_the_model_without_reading_the_words(agent, handoff):
    from workspace.context import bind_workspace, reset_workspace

    store = handoff.store
    workspace = store.create("Shop")["id"]
    handoff.context.button = {"plan_approved": True}
    agent.ai_client = ScriptedProvider(
        [
            tool_use("workspace_write", path="notes.md", content="# Plan done\n"),
            "Done: wrote notes.md as planned.",
        ]
    )
    selected = bind_workspace(workspace)
    try:
        result = await agent.execute("Go ahead")  # Fahm alone reads this as conversation
    finally:
        reset_workspace(selected)
    assert store.read(workspace, "notes.md")["content"] == "# Plan done\n"
    assert "approved the plan" in json.dumps(agent.ai_client.requests[0]["messages"])
    assert result["orchestration"]["entities"]["understood_by"] == "button"


async def test_mizans_checks_run_in_one_sandbox_run_so_the_person_is_asked_once(
    agent, monkeypatch, tmp_path
):
    import subprocess

    from tadbir.engine import Tadbir

    changes = {"good.py": "x = 1\n", "bad.py": "def broken(:\n", "data.json": "{}"}
    for path, content in changes.items():
        (tmp_path / path).write_text(content)

    def run(command):
        done = subprocess.run(
            ["bash", "-c", command], cwd=tmp_path, capture_output=True, text=True, timeout=60
        )
        return {"stdout": done.stdout, "stderr": done.stderr, "exit_code": done.returncode}

    fake = tools(agent, monkeypatch, workspace_run=[])

    async def sandbox(name, params):
        fake.calls.append((name, deepcopy(params)))
        return run(params["command"])

    monkeypatch.setattr(agent, "_execute_tool_safe", sandbox)
    agent._last_tool_results = []
    checks, problem = await Tadbir(agent)._check_edit(changes, changes, sorted(changes))
    assert [name for name, _ in fake.calls] == ["workspace_run"]  # one run, one prompt
    assert ("`good.py` has valid syntax (sandbox)", True, "") in checks
    assert ("`bad.py` has valid syntax (sandbox)", False, "") in checks
    assert ("`data.json` is valid JSON", True, "") in checks
    assert "py_compile bad.py` failed" in problem and "SyntaxError" in problem
    # A program that prints a marker cannot pass a check: each run's marker is new.
    forged = "echo '@@mizan-check 1 exit 0'"
    assert forged not in fake.calls[0][1]["command"]


async def test_words_after_a_tool_start_a_new_paragraph(agent, monkeypatch):
    before = LLMResponse(
        [
            ContentBlock(type="text", text="Reading the project."),
            ContentBlock(type="tool_use", id="t1", name="workspace_glob", input={}),
        ],
        model="fixture",
        stop_reason="tool_use",
    )
    agent.ai_client = ScriptedProvider([before, "Done: it has no files."])
    tools(agent, monkeypatch, workspace_glob={"files": [], "total": 0})
    agent._llm_calls, agent._last_tool_results = [], []
    text = await agent._model_turn("What is in the project?", None, None)
    assert text == "Reading the project.\n\nDone: it has no files."
