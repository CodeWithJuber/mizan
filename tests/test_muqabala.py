"""Muqabala debug mode: the base model alone vs MIZAN, with MIZAN's trace and checks."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import muqabala, quran, trace


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse(
            [ContentBlock(type="text", text=self.replies.pop(0))],
            model="fixture-model",
            usage={"input": 12, "output": 7},
        )


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    created = create_agent("general", izn=IznPermission())
    created.ai_client = ScriptedProvider()
    created.ai_model = "fixture-model"
    names = ["workspace_run", "web_search"]
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {"type": "object"}} for n in names],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)
    return created


IKHLAS = "قُلْ هُوَ ٱللَّهُ أَحَدٌ"


def ikhlas(monkeypatch):
    async def fetch(reference, language):
        return {
            "reference": reference.label,
            "surah_arabic": "الإخلاص",
            "ayahs": [{"number": 1, "arabic": IKHLAS, "translation": "Say, He is Allah, One"}],
            "translation": "Saheeh International",
            "source": "api.alquran.cloud (Tanzil Uthmani text)",
        }

    monkeypatch.setattr(quran, "fetch", fetch)


def test_nothing_is_recorded_without_a_bound_trace():
    assert not trace.active()
    trace.event("plan", "x", a=1)
    with trace.span("execute_tool", "y") as record:
        record["attributes"]["ok"] = True
    with trace.bind() as recorded:
        with trace.span("invoke_agent", "Khalifah"):
            trace.event("verify", "furqan", accepted=True)
    parent, child = recorded.to_list()
    assert child["parent"] == parent["id"] and parent["parent"] is None
    assert not trace.active()


async def test_a_wrong_base_answer_is_caught_by_mizans_exact_value(agent):
    agent.ai_client = ScriptedProvider(["2**100 is about 1267650600228229401496703205377."])
    run = await muqabala.compare(agent, "2**100 kitna hai?", {}, [])
    base, mizan, checks = run["base"], run["mizan"], run["checks"]
    # The base arm: one plain call, no tools, no MIZAN system prompt.
    (request,) = agent.ai_client.requests
    # The plain prompt and the same clock MIZAN's arm reads, nothing else.
    assert request["system"].startswith(muqabala.BASE_SYSTEM) and not request.get("tools")
    assert "The current date and time is" in request["system"]
    assert base["usage"]["input_tokens"] == 12 and base["tool_calls"] == 0
    # MIZAN computed the value itself, with no model call.
    assert "1267650600228229401496703205376" in mizan["text"] and mizan["verified"]
    assert mizan["model_calls"] == 0
    assert [span["op"] for span in mizan["spans"]][:2] == ["understand", "invoke_agent"]
    assert checks["intent"] == "compute"
    assert checks["base"]["unsupported_numbers"] == ["1267650600228229401496703205377"]
    assert checks["mizan"]["unsupported_numbers"] == []
    assert checks["agreement"]["share"] == 0.0
    assert any(line.startswith("+") for line in checks["diff"])


async def test_quran_quotes_are_checked_against_mizans_source(agent, monkeypatch):
    ikhlas(monkeypatch)
    # Different marks and letter forms, the same words: a match.
    agent.ai_client = ScriptedProvider(["قل هو الله احد — Say, He is Allah, One."])
    same = await muqabala.compare(agent, "Surah Ikhlas ayah 1", {}, [])
    assert same["checks"]["intent"] == "quran"
    source = next(span for span in same["mizan"]["spans"] if span["op"] == "execute_tool")
    assert source["attributes"]["source"] is True and source["attributes"]["ok"] is True
    assert same["checks"]["quote"]["status"] == "matches"
    # Words the ayah does not contain: flagged.
    agent.ai_client = ScriptedProvider(["قل هو رب العالمين الكريم"])
    wrong = await muqabala.compare(agent, "Surah Ikhlas ayah 1", {}, [])
    assert wrong["checks"]["quote"]["status"] == "differs"
    agent.ai_client = ScriptedProvider(["Say, He is Allah, One."])
    missing = await muqabala.compare(agent, "Surah Ikhlas ayah 1", {}, [])
    assert missing["checks"]["quote"]["status"] == "missing"


def test_quote_check_tells_an_excerpt_from_a_misquote():
    source = "> ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌۭ وَلَا نَوْمٌۭ"
    # The common script for the Uthmani text, with a heading around it.
    common = "آية الكرسي: اللَّهُ لَا إِلَهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ"
    assert muqabala.quote_check(common, source)["status"] == "matches"
    assert muqabala.quote_check("اللَّهُ لَا إِلَهَ إِلَّا هُوَ", source)["status"] == "excerpt"
    misquote = muqabala.quote_check("الله لا اله الا هو الرحيم الكريم", source)
    assert misquote["status"] == "differs" and misquote["changed"]


def test_arabic_digits_are_numbers_too():
    run_base = {"text": "آية الكرسي (البقرة: ٢٥٥)"}
    mizan = {
        "text": "**Surah Al-Baqarah 2:255**",
        "verified": True,
        "spans": [
            {"op": "plan", "name": "result", "attributes": {"facts": {"reference": "2:255"}}}
        ],
    }
    report = muqabala.checks("Ayatul Kursi", run_base, mizan)
    assert report["base"]["unsupported_numbers"] == []
    assert report["agreement"]["share"] == 1.0


async def test_the_trace_shows_every_tool_and_lisan_prompt(agent, monkeypatch):
    calls = []

    async def run_tool(name, params):
        calls.append(name)
        return {"stdout": "[0, 1, 1, 2, 3]\n", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run_tool)

    class ByRequest(ScriptedProvider):
        # The two arms run at once, so replies go by what is asked, not by order:
        # MIZAN's Lisan is asked for a program, the base model for an answer.
        def create(self, **kwargs):
            asked = str(kwargs.get("system", "")) + str(kwargs.get("messages", ""))
            self.replies = (
                ["```python\nprint([0, 1, 1, 2, 3])\n```"]
                if "```" in asked or "program" in str(kwargs.get("system", "")).lower()
                else ["I ran it: 0 1 1 2 3"]
            )
            return super().create(**kwargs)

    agent.ai_client = ByRequest()
    run = await muqabala.compare(
        agent, "Ek python program likho jo 5 fibonacci numbers print kare aur run karo", {}, []
    )
    spans = run["mizan"]["spans"]
    lisan = [span for span in spans if span["name"].startswith("lisan.")]
    assert lisan and lisan[0]["name"] == "lisan.write_code"
    assert "fibonacci" in lisan[0]["attributes"]["user"]
    assert "print(" in lisan[0]["attributes"]["reply"]
    tool = next(span for span in spans if span["op"] == "execute_tool")
    assert tool["name"] == "workspace_run" and tool["attributes"]["ok"] is True
    # The program and the independent check written without seeing it (Tathabbut).
    assert run["mizan"]["tool_calls"] == 2 and calls == ["workspace_run", "workspace_run"]
    assert [span["name"] for span in lisan] == ["lisan.write_code", "lisan.cross_check"]
    # The base model claimed it ran code; it has no tools, so no receipt backs it.
    assert run["checks"]["base"]["unbacked_action_claims"]


async def test_abstention_is_detected_for_either_arm(agent):
    agent.ai_client = ScriptedProvider(["I don't know the answer.", "Words only."])
    run = await muqabala.compare(agent, "Explain recursion simply", {}, [])
    assert run["checks"]["base"]["abstained"] or run["checks"]["mizan"]["abstained"]
    assert any(span["name"] == "language_model_answers" for span in run["mizan"]["spans"])


async def test_runs_are_kept_per_user_and_capped(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(muqabala, "KEEP_RUNS", 3)
    for index in range(5):
        await muqabala.save(
            "alice",
            {
                "id": f"{index:032x}",
                "created_at": float(index),
                "prompt": f"p{index}",
                "checks": {"intent": "compute"},
                "mizan": {"verified": True, "text": "x" * 9000},
            },
        )
    listed = await muqabala.runs("alice")
    assert [run["prompt"] for run in listed] == ["p4", "p3", "p2"]
    stored = await muqabala.get("alice", f"{4:032x}")
    assert stored["mizan"]["text"].endswith("(trimmed)")
    assert await muqabala.runs("bob") == []
    await muqabala.clear("alice")
    assert await muqabala.runs("alice") == []


@pytest.mark.parametrize(
    "value,admin,user", [("admins", True, False), ("users", True, True), ("off", False, False)]
)
def test_access_follows_the_setting(monkeypatch, value, admin, user):
    monkeypatch.setenv("MIZAN_DEBUG_MODE", value)
    assert muqabala.allowed(True) is admin and muqabala.allowed(False) is user


def test_compare_endpoint(agent, monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    from api import main

    async def no_preferences(user_id):
        return {}

    monkeypatch.setattr(main.memory, "get_chat_preferences", no_preferences)
    monkeypatch.setitem(main.active_agents, "fixture", agent)
    client = TestClient(main.app, raise_server_exceptions=False)
    admin = main.auth.create_token(main.auth.create_user("debugadmin", "pw", roles=["admin"]))
    member = main.auth.create_token(main.auth.create_user("debuguser", "pw", roles=["user"]))
    agent.ai_client = ScriptedProvider(["4"])
    response = client.post(
        "/api/debug/compare",
        json={"prompt": "2+2?", "agent_id": "fixture"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base"]["text"] == "4" and "**4**" in body["mizan"]["text"]
    listed = client.get("/api/debug/runs", headers={"Authorization": f"Bearer {admin}"}).json()
    assert listed["runs"][0]["id"] == body["id"]
    denied = client.post(
        "/api/debug/compare",
        json={"prompt": "2+2?"},
        headers={"Authorization": f"Bearer {member}"},
    )
    assert denied.status_code == 403


def test_arabic_terms_in_an_explanation_are_not_read_as_a_quote():
    source = "> إِنَّ رَبَّكُمُ ٱللَّهُ ٱلَّذِى خَلَقَ ٱلسَّمَٰوَٰتِ وَٱلْأَرْضَ فِى سِتَّةِ أَيَّامٍۢ"
    answer = "Here يوم means a stage, not 24 hours; in يوم القيامة it is the Day of Judgement."
    assert muqabala.quote_check(answer, source)["status"] == "missing"
    # A passage given as the ayah is still read, however different.
    wrong = muqabala.quote_check("إن ربكم الله الذي خلق الأرض في يومين", source)
    assert wrong["status"] == "differs"


# Ayat al-Kursi (2:255) as MIZAN's source gives it (Tanzil Uthmani) and as an
# answer writes it in the common script (Tanzil simple), both from the
# editions MIZAN reads.
KURSI_SOURCE = (
    "> ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌۭ وَلَا نَوْمٌۭ ۚ "
    "لَّهُۥ مَا فِى ٱلسَّمَٰوَٰتِ وَمَا فِى ٱلْأَرْضِ ۗ مَن ذَا ٱلَّذِى يَشْفَعُ عِندَهُۥٓ إِلَّا "
    "بِإِذْنِهِۦ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَىْءٍۢ "
    "مِّنْ عِلْمِهِۦٓ إِلَّا بِمَا شَآءَ ۚ وَسِعَ كُرْسِيُّهُ ٱلسَّمَٰوَٰتِ وَٱلْأَرْضَ ۖ وَلَا "
    "يَـُٔودُهُۥ حِفْظُهُمَا ۚ وَهُوَ ٱلْعَلِىُّ ٱلْعَظِيمُ"
)
KURSI = (
    "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَهُ مَا "
    "فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَنْ ذَا الَّذِي يَشْفَعُ عِنْدَهُ إِلَّا بِإِذْنِهِ ۚ "
    "يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِنْ عِلْمِهِ إِلَّا "
    "بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ "
    "الْعَلِيُّ الْعَظِيمُ"
)
DAMMA, FATHA, KASRA = chr(0x64F), chr(0x64E), chr(0x650)


def test_an_exact_quote_in_either_script_matches_and_a_part_is_an_excerpt():
    assert muqabala.quote_check(KURSI, KURSI_SOURCE)["status"] == "matches"
    # Written without vowels, as most answers write it: not penalised for them.
    bare = "".join(c for c in KURSI if not 0x64B <= ord(c) <= 0x652)
    assert muqabala.quote_check(bare, KURSI_SOURCE)["status"] == "matches"
    # The Uthmani text itself, and its first half word for word.
    assert muqabala.quote_check(KURSI_SOURCE[2:], KURSI_SOURCE)["status"] == "matches"
    half = " ".join(KURSI.split()[:20])
    assert muqabala.quote_check(half, KURSI_SOURCE)["status"] == "excerpt"


def test_one_changed_word_in_a_long_ayah_is_not_a_match():
    # The audit: one of 50 words changed read as "matches" (0.98 ≥ 0.97).
    words = KURSI.split()
    words[3] = "الْعَلِيمُ"  # in place of إِلَّا
    check = muqabala.quote_check(" ".join(words), KURSI_SOURCE)
    assert check["status"] == "close" and check["coverage"] < 1
    assert check["changed"] == [{"kind": "changed", "source": "إِلَّا", "given": "الْعَلِيمُ"}]
    # A word dropped from inside the passage, or added to it, is no excerpt either.
    dropped = " ".join(words[:3] + words[4:])
    assert muqabala.quote_check(dropped, KURSI_SOURCE)["status"] == "close"
    added = " ".join(KURSI.split()[:5] + ["حَقًّا"] + KURSI.split()[5:])
    added_check = muqabala.quote_check(added, KURSI_SOURCE)
    assert added_check["status"] == "close" and added_check["changed"][0]["kind"] == "added"


def test_changed_vowels_are_not_a_match():
    # The audit: three vowel marks changed still read as "matches".
    words = KURSI.split()
    words[0] = words[0][:-1] + KASRA  # اللَّهُ → اللَّهِ
    words[5] = words[5].replace(DAMMA, FATHA)  # الْحَيُّ → الْحَيَّ
    words[9] = words[9][:-1] + FATHA  # تَأْخُذُهُ → تَأْخُذُهَ
    check = muqabala.quote_check(" ".join(words), KURSI_SOURCE)
    assert check["status"] == "close" and check["coverage"] == 1.0
    assert [change["kind"] for change in check["changed"]] == ["vowels"] * 3


def test_half_an_ayah_with_another_continuation_is_not_an_excerpt():
    # The audit: the first half word for word, then other words given as its
    # continuation, read as an "excerpt".
    half = " ".join(KURSI.split()[:20])
    continued = muqabala.quote_check(
        f"{half} and to Him belongs whatever is in the heavens", KURSI_SOURCE
    )
    assert continued["status"] == "close"
    assert continued["changed"][0]["kind"] == "continued"
    # A translation after a dash, or a phrase cited inside a sentence, is not.
    translated = f"{half} — Allah, there is no deity except Him"
    assert muqabala.quote_check(translated, KURSI_SOURCE)["status"] == "excerpt"
    inline = "The phrase لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ says He never tires."
    assert muqabala.quote_check(inline, KURSI_SOURCE)["status"] == "excerpt"
