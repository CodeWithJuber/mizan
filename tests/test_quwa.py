"""Quwa: the Imtihan as a profile of Google DeepMind's ten cognitive faculties."""

import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from imtihan import quwa, report, runner, scorers
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from tadbir import nazm

ROOT = Path(__file__).resolve().parents[1]
DEEPMIND = [
    "perception", "generation", "attention", "learning", "memory", "reasoning",
    "metacognition", "executive", "problem_solving", "social",
]  # fmt: skip


@pytest.fixture(autouse=True)
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))


# ── the faculties and their items ───────────────────────────────────────


def test_ten_faculties_each_with_its_ayah_and_definition():
    found = quwa.faculties()
    assert [entry["key"] for entry in found] == DEEPMIND
    assert {entry["key"] for entry in found if entry["composite"]} == {"problem_solving", "social"}
    for entry in found:
        surah, ayah = entry["ayah"].split(":")
        assert 1 <= int(surah) <= 114 and int(ayah) >= 1
        assert entry["words"] and entry["arabic"] and entry["script"] and entry["definition"]


def test_every_task_measures_one_faculty_or_a_propensity():
    tasks = runner.load_tasks()
    blocks = {task["block"] for task in tasks}
    assert set(quwa.data()["blocks"]) <= blocks | {"locked_eval"}
    for task in tasks:
        named = quwa.faculty_of(task)
        if task["block"] in quwa.data()["propensity"]:
            assert named is None
        else:
            assert named in DEEPMIND, task["id"]
    counts = {key: sum(quwa.faculty_of(task) == key for task in tasks) for key in DEEPMIND}
    # Learning comes from the multi-turn and game blocks; every other axis has ten items or more.
    assert all(count >= 10 for key, count in counts.items() if key != "learning"), counts
    assert counts["learning"] >= 6


def test_the_faculty_files_are_what_the_builder_makes():
    done = subprocess.run(
        [sys.executable, "scripts/build_quwa_tasks.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr


def test_a_person_can_answer_the_text_items_only():
    tasks = {task["id"]: task for task in quwa.panel_tasks()}
    assert "exec-hanoi-3" in tasks and "mem-update" in tasks
    assert tasks["mem-update"]["history"]  # earlier turns are shown with the item
    assert not any(task_id.startswith(("agent-", "game-")) for task_id in tasks)
    assert not any(task["block"] in quwa.data()["propensity"] for task in tasks.values())


# ── the scorers the faculties added ─────────────────────────────────────


def _hanoi(n, a="A", b="B", c="C"):
    return [] if n == 0 else _hanoi(n - 1, a, c, b) + [f"{a}->{c}"] + _hanoi(n - 1, b, a, c)


def test_hanoi_plays_the_moves():
    spec = {"kind": "hanoi", "disks": 3, "optimal": True}
    assert scorers.score(spec, "\n".join(_hanoi(3)))["pass"]
    worded = "\n".join(
        f"{n}. Move disk from {m.replace('->', ' to ')}" for n, m in enumerate(_hanoi(3), 1)
    )
    assert scorers.score(spec, "Here are the moves:\n" + worded)["pass"]
    illegal = scorers.score(spec, "A->B\nA->B")
    assert not illegal["pass"] and "smaller disk" in illegal["detail"]
    longer = ["A->B", "B->A"] + _hanoi(3)
    assert not scorers.score(spec, "\n".join(longer))["pass"]  # solved, but not in fewest moves
    assert scorers.score({**spec, "optimal": False}, "\n".join(longer))["pass"]


def test_metacognition_passes_on_knowing_whether_it_is_right():
    spec = {"kind": "metacog", "answer": {"kind": "number", "expected": "97"}}
    right = scorers.score(spec, "The 25th prime is 97.\nConfidence: 90%")
    assert right["pass"] and right["correct"] and right["confidence"] == 0.9
    assert not scorers.score(spec, "It is 89.\nConfidence: 97%")["pass"]  # confidently wrong
    assert scorers.score(spec, "It is 89, I think. Confidence: 30%")[
        "pass"
    ]  # knows it may be wrong
    # The confidence line is not the answer.
    assert not scorers.score(spec, "Not sure.\nConfidence: 97%")["correct"]
    assert not scorers.score(spec, "It is 97.")["pass"]  # no confidence stated


def test_choice_reads_any_letter_of_the_item():
    spec = {"kind": "choice", "expected": "C", "options": {"A": "x", "B": "y", "C": "z"}}
    assert scorers.score(spec, "C) It cannot be determined")["pass"]
    assert scorers.score(spec, "The answer is C.")["pass"]
    assert not scorers.score({**spec, "expected": "B"}, "C")["pass"]


def test_auroc2_is_discrimination_between_right_and_wrong():
    assert report.auroc2([(0.9, True), (0.8, True), (0.2, False)]) == 1.0
    assert report.auroc2([(0.9, False), (0.2, True)]) == 0.0
    assert report.auroc2([(0.5, True), (0.5, False)]) == 0.5
    assert report.auroc2([(0.9, True)]) is None


# ── Nazm: checks of form ─────────────────────────────────────────────────


def test_nazm_counts_what_was_asked():
    text = "Sabr is light. It steadies the heart. Allah loves the patient."
    assert nazm.check_one(text, {"kind": "sentences", "exact": 3})["ok"]
    assert not nazm.check_one(text, {"kind": "sentences", "max": 2})["ok"]
    assert nazm.check_one(text, {"kind": "no_char", "chars": ","})["ok"]
    assert nazm.check_one("- a\n- b\n* c", {"kind": "bullets", "exact": 3})["ok"]
    assert nazm.check_one("1. a\n2) b", {"kind": "numbered", "exact": 2})["ok"]
    assert nazm.check_one('```json\n{"a": 1, "b": 2}\n```', {"kind": "json", "keys": ["a"]})["ok"]
    assert not nazm.check_one("{'a': 1}", {"kind": "json", "keys": ["a"]})["ok"]
    assert nazm.check_one("صبح کی سیر اچھی ہے۔", {"kind": "script", "name": "arabic"})["ok"]
    assert len(nazm.sentences("صبح کی سیر اچھی ہے۔ اس سے سکون ملتا ہے۔")) == 2
    assert not nazm.check_one("Sunlight helps.", {"kind": "exclude", "words": ["sunlight"]})["ok"]
    assert nazm.check_one("Sunlight helps.", {"kind": "exclude", "words": ["sun"]})["ok"]
    assert nazm.check_one("ok. That is all.", {"kind": "ends_with", "text": "That is all."})["ok"]


def test_nazm_keeps_only_checks_resting_on_the_request():
    request = "Explain sabr in exactly three sentences, without commas."
    read = [
        {"kind": "sentences", "exact": 3, "basis": "exactly three sentences"},
        {"kind": "no_char", "chars": ",", "basis": "without commas"},
        {"kind": "words", "max": 10, "basis": "under ten words"},  # not in the request
        {"kind": "rhyme", "basis": "sabr"},  # not a kind MIZAN can count
    ]
    kept = nazm.grounded(request, read)
    assert kept == [{"kind": "sentences", "exact": 3}, {"kind": "no_char", "chars": ","}]


# ── the profile ─────────────────────────────────────────────────────────


def _results(passes: dict[str, tuple[bool, bool]]):
    rows = []
    for task_id, (base, mizan) in passes.items():
        for arm, passed in (("base", base), ("mizan", mizan)):
            rows.append(
                {"task_id": task_id, "block": "x", "arm": arm, "attempt": 1, "pass": passed}
            )
    return rows


def test_profile_rates_each_faculty_and_keeps_propensity_apart():
    tasks = [
        {"id": "r1", "block": "reasoning"},
        {"id": "r2", "block": "reasoning"},
        {"id": "s1", "block": "social"},
        {"id": "i1", "block": "injection"},
        {"id": "o1", "block": "ibrah", "faculty": "memory"},
    ]
    results = _results(
        {
            "r1": (False, True),
            "r2": (True, True),
            "s1": (True, False),
            "i1": (False, True),
            "o1": (False, True),
        }  # fmt: skip
    )
    profile = quwa.profile(results, tasks)
    faculties = {entry["key"]: entry for entry in profile["faculties"]}
    assert faculties["reasoning"]["items"] == 2
    assert faculties["reasoning"]["base"]["rate"] == 0.5
    assert faculties["reasoning"]["mizan"]["rate"] == 1.0
    assert faculties["reasoning"]["delta"] == 0.5
    assert faculties["memory"]["items"] == 1  # a task's own faculty wins over its block's
    assert faculties["attention"]["items"] == 0 and faculties["attention"]["mizan"]["rate"] is None
    assert "injection" in profile["propensity"]
    assert sum(entry["items"] for entry in profile["faculties"]) == 4


def test_the_percentile_is_against_the_panel_on_the_same_items():
    tasks = [{"id": f"r{n}", "block": "reasoning"} for n in range(4)]
    results = _results({"r0": (True, True), "r1": (True, True), "r2": (False, True),
                        "r3": (False, False)})  # fmt: skip
    panel = {
        "p1": {"r0": True, "r1": False},  # 50% on r0, r1: MIZAN 100% there
        "p2": {"r0": True, "r1": True, "r2": True, "r3": True},  # beats MIZAN (75%)
        "p3": {"r2": True},  # ties MIZAN on r2: counts half
    }
    human = quwa.profile(results, tasks, panel)["faculties"][5]["mizan"]["human"]
    assert human["people"] == 3
    assert human["percentile"] == 0.5  # 1 + 0 + 0.5 out of 3
    assert human["level"] is None  # the interval's lower end is below the 50th percentile


def test_a_level_is_claimed_only_from_the_lower_end_of_the_interval():
    assert quwa.level(0.95) == "expert"
    assert quwa.level(0.5) == "competent"
    assert quwa.level(0.49) is None
    assert quwa.level(None) is None
    # 30 of 30 people beaten: the lower end (0.886) supports Competent, not Expert.
    assert report.wilson(30, 30)[0] < 0.9


async def test_panel_answers_are_scored_by_the_items_rules_and_can_be_erased():
    scored = await quwa.record(
        "p01",
        {"exec-hanoi-3": "\n".join(_hanoi(3)), "reas-modular": "It is 4", "no-such": "x"},
        by="admin",
    )
    verdicts = {entry["task_id"]: entry["pass"] for entry in scored}
    assert verdicts == {"exec-hanoi-3": True, "reas-modular": False}
    assert quwa.panel() == {"p01": {"exec-hanoi-3": True, "reas-modular": False}}
    listed = quwa.people()
    assert listed[0]["person"] == "p01" and listed[0]["faculties"]["executive"] == 1.0
    assert quwa.forget("p01") == 2 and quwa.panel() == {}


def test_a_stored_run_is_read_against_the_panel_as_it_is_now():
    tasks = [{"id": "exec-hanoi-3", "block": "executive"}]
    results = _results({"exec-hanoi-3": (False, True)})
    run = {"status": "complete", "result": {"tasks": tasks, "results": results, "report": {}}}
    assert quwa.with_panel(run) is run  # no panel yet
    with quwa._db() as connection:
        connection.execute(
            "INSERT INTO answers VALUES ('p1', 'exec-hanoi-3', '', 0, '', 'admin', 0)"
        )
    profile = quwa.with_panel(run)["result"]["report"]["faculties"]
    executive = next(entry for entry in profile["faculties"] if entry["key"] == "executive")
    assert executive["mizan"]["human"]["percentile"] == 1.0
    assert executive["base"]["human"]["percentile"] == 0.5


async def test_panel_api_is_admin_only(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    from api import main

    admin = main.auth.create_token(main.auth.create_user("quwaadmin", "pw", roles=["admin"]))
    member = main.auth.create_token(main.auth.create_user("quwauser", "pw", roles=["user"]))
    headers = {"Authorization": f"Bearer {admin}"}
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(
            "/api/imtihan/panel", headers={"Authorization": f"Bearer {member}"}
        )
        assert denied.status_code == 403
        listed = (await client.get("/api/imtihan/panel", headers=headers)).json()
        assert len(listed["faculties"]) == 10 and listed["tasks"] and listed["people"] == []
        bad = await client.post(
            "/api/imtihan/panel",
            json={"person": "no spaces", "answers": {"x": "y"}},
            headers=headers,
        )
        assert bad.status_code == 422
        sent = await client.post(
            "/api/imtihan/panel",
            json={"person": "p02", "answers": {"ps-tiles": "60 cm"}},
            headers=headers,
        )
        assert sent.json()["scored"] == [
            {"task_id": "ps-tiles", "pass": True, "detail": "expects 60"}
        ]
        removed = await client.delete("/api/imtihan/panel/p02", headers=headers)
        assert removed.json() == {"removed": 1}


# ── Nazm in MIZAN's own answers ──────────────────────────────────────────


class FormProvider(BaseLLMProvider):
    """Answers each kind of request MIZAN makes: the checks Lisan reads, the first
    answer (two commas, four sentences) and the rewrite."""

    provider_name = "fixture"

    def __init__(self, rewrite: str):
        self.rewrite = rewrite
        self.asked: list[str] = []

    def create(self, **kwargs):
        system = str(kwargs.get("system") or "")
        if "checks of form" in system:
            self.asked.append("form_checks")
            text = (
                '{"checks": [{"kind": "sentences", "exact": 3, "basis": "exactly three '
                'sentences"}, {"kind": "no_char", "chars": ",", "basis": "without commas"}, '
                '{"kind": "words", "max": 5, "basis": "in five words"}]}'
            )
        elif "MIZAN counted this answer" in system:
            self.asked.append("conform")
            text = self.rewrite
        elif '"steps"' in system:
            self.asked.append("map")
            text = '{"steps":[{"intent":"converse"}]}'
        else:
            self.asked.append("answer")
            text = "Sabr is patience, steady and calm. It holds the heart. It is rewarded. Truly."
        return LLMResponse([ContentBlock(type="text", text=text)], model="fixture")


@pytest.fixture
def form_agent(monkeypatch, tmp_path):
    from agents.specialized import create_agent
    from security.izn import IznPermission

    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    created = create_agent("general", izn=IznPermission())
    created.ai_model = "fixture-model"
    monkeypatch.setattr(created, "get_tool_schemas", lambda: [])
    return created


REQUEST = "Describe sabr in exactly three sentences, without commas."


async def test_mizan_counts_the_form_and_streams_the_rewrite(form_agent):
    form_agent.ai_client = FormProvider("Sabr is patience. It holds the heart. It is rewarded.")
    chunks: list[str] = []

    async def stream(chunk="", **kwargs):
        if not kwargs:
            chunks.append(chunk)

    result = await form_agent.execute(REQUEST, stream_callback=stream)
    assert result["result"] == "Sabr is patience. It holds the heart. It is rewarded."
    # Only the checks resting on the request's own words were kept ("in five words" is not).
    assert result["nazm"] == {"checks": 2, "failed": 0, "rewritten": True, "held": 2}
    assert result["usage"]["nazm"]["rewritten"] is True
    assert "".join(chunks) == result["result"]  # what streamed is what was kept
    # The checks are read after the answer, only for an answer in words.
    assert form_agent.ai_client.asked[-2:] == ["form_checks", "conform"]


async def test_a_rewrite_that_brings_new_numbers_is_not_kept(form_agent):
    form_agent.ai_client = FormProvider("Sabr is patience. It holds 70 hearts. It is rewarded.")
    result = await form_agent.execute(REQUEST)
    assert result["result"].startswith("Sabr is patience, steady and calm.")
    assert result["nazm"]["rewritten"] is False and result["nazm"]["failed"] == 2


async def test_a_request_with_no_form_asks_lisan_nothing_more(form_agent):
    form_agent.ai_client = FormProvider("unused")
    result = await form_agent.execute("What is patience in Islam?")
    assert "nazm" not in result
    assert "form_checks" not in form_agent.ai_client.asked
