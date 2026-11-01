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


def summing(n: int) -> str:
    return f"```python\nn = {n}\nprint(sum(range(1, n + 1)))\n```"


def checking(n: int) -> str:
    return f"```python\nprint({n} * ({n} + 1) // 2)\n```"


async def test_programs_verified_for_two_numbers_answer_a_third_without_the_model(
    agent, monkeypatch, alice
):
    """Hifz templates: the programs for "1 se 10" and "1 se 20" differ only where
    the requests' numbers differ, so "1 se 30" is answered by putting 30 in."""
    outputs = ["55\n", "55\n", "210\n", "210\n", "465\n"]
    calls = []

    async def run(name, params):
        calls.append(params["command"])
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([summing(10), checking(10), summing(20), checking(20)])
    for n in (10, 20):
        assert (await agent.execute(REQUEST.replace("10", str(n))))["task_verified"]
    assert len(agent.ai_client.requests) == 4
    third = await agent.execute(REQUEST.replace("10", "30"))
    assert len(agent.ai_client.requests) == 4  # no model call
    assert "n = 30" in calls[-1] and "465" in third["result"]
    # Observed, not independently checked, and the answer says so.
    assert not third["task_verified"] and "kisi alag program ne check nahi kiya" in third["result"]


def keep(store, request, code, output, checked=True):
    hifz.keep(store, "u", request, "python", code, output, checked=checked)


def test_a_template_reproduces_every_program_it_comes_from(tmp_path):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))

    def fibonacci(n):
        return f"a, b = 0, 1\nfor _ in range({n}):\n    a, b = b, a + b\nprint(f'F{n} =', a)\n"

    keep(store, "Print the 10th Fibonacci number", fibonacci(10), "F10 = 55\n")
    assert hifz.template(store, "u", "Print the 7th Fibonacci number", "python") is None  # one
    keep(store, "Print the 20th Fibonacci number", fibonacci(20), "F20 = 6765\n")
    made = hifz.template(store, "u", "Print the 7th Fibonacci number", "python")
    assert made["instances"] == 2 and "range(7)" in made["code"] and "F7 =" in made["code"]
    # Other words, another kind of number, another language: no template.
    assert hifz.template(store, "u", "Print the 7th prime number", "python") is None
    assert hifz.template(store, "u", "Print the 7.5th Fibonacci number", "python") is None
    assert hifz.template(store, "u", "Print the 7th Fibonacci number", "javascript") is None
    assert hifz.template(store, "bob", "Print the 7th Fibonacci number", "python") is None


def test_a_template_is_general_only_where_it_was_seen_to_vary(tmp_path):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))
    for exponent in (10, 20):
        keep(store, f"What is 2 to the power {exponent}", f"print(2 ** {exponent})", "1\n")
    assert "2 ** 5" in hifz.template(store, "u", "What is 2 to the power 5", "python")["code"]
    # The base was 2 in every program: a new base may be a literal there.
    assert hifz.template(store, "u", "What is 3 to the power 5", "python") is None


def test_a_template_needs_programs_an_independent_program_agreed_with(tmp_path):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))
    for n in (10, 20):
        keep(store, f"Sum 1 to {n}", f"n = {n}\nprint(sum(range(1, n + 1)))", "55\n", checked=False)
    assert hifz.template(store, "u", "Sum 1 to 30", "python") is None
    # Programs that differ where the requests' numbers do not explain it: none.
    store = AdaptiveStateStore(str(tmp_path / "b.db"))
    keep(store, "Sum 1 to 10", "print(55)", "55\n")
    keep(store, "Sum 1 to 20", "print(210)", "210\n")
    assert hifz.template(store, "u", "Sum 1 to 30", "python") is None


def test_a_template_slot_may_be_a_number_plus_an_offset_the_instances_agree_on(tmp_path):
    """Live, 30 Oct: the teacher wrote ``sum(range(1, 11))`` for "1 se 10".
    The offset is one parameter both instances measure, so they test it."""
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / "a.db"))
    keep(store, "Sum 1 to 10", "print(sum(range(1, 11)))", "55\n")
    keep(store, "Sum 1 to 20", "print(sum(range(1, 21)))", "210\n")
    assert "range(1, 31)" in hifz.template(store, "u", "Sum 1 to 30", "python")["code"]
    # Offsets that disagree (11 for 10, 22 for 20) are no slot.
    store = AdaptiveStateStore(str(tmp_path / "b.db"))
    keep(store, "Sum 1 to 10", "print(sum(range(1, 11)))", "55\n")
    keep(store, "Sum 1 to 20", "print(sum(range(1, 22)))", "231\n")
    assert hifz.template(store, "u", "Sum 1 to 30", "python") is None


async def test_lisan_sees_the_nearest_verified_programs_and_the_check_does_not(
    agent, monkeypatch, alice
):
    """Memento's case memory: a known form is written in its known shape; the
    independent program (Tathabbut) is written without seeing any of it."""
    outputs = ["55\n", "55\n", "210\n", "210\n"]

    async def run(name, params):
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider([summing(10), checking(10), summing(20), checking(20)])
    await agent.execute(REQUEST)
    await agent.execute(REQUEST.replace("10", "20"))
    write, check = agent.ai_client.requests[2], agent.ai_client.requests[3]
    assert "n = 10" in str(write["messages"]) and "Programs MIZAN verified" in str(
        write["messages"]
    )
    assert "n = 10" not in str(check["messages"])
    # Another user sees none of them.
    assert hifz.cases(agent.adaptive, "bob", REQUEST, "python") == []


# ── templates with the user's own words ──────────────────────────────────

W = "Write and run a Python program that "


def greet(name: str) -> str:
    return f'print("Assalamu alaikum, {name}")'


def vowels(word: str) -> str:
    return f's = "{word}"\nprint(sum(ch in "aeiou" for ch in s))'


def store_of(tmp_path, kept, name="a.db"):
    from core.adaptive import AdaptiveStateStore

    store = AdaptiveStateStore(str(tmp_path / name))
    for request, code, output, checked in kept:
        keep(store, request, code, output, checked=checked)
    return store


def printed(code: str) -> str:
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "<template>", "exec"), {})  # noqa: S102 - the test's own programs
    return out.getvalue()


GREETINGS = [
    (W + "prints a greeting for Ali", greet("Ali"), "Assalamu alaikum, Ali\n", False),
    (W + "prints a greeting for Bilal", greet("Bilal"), "Assalamu alaikum, Bilal\n", False),
]
VOWELS = [
    (W + "counts the vowels in banana", vowels("banana"), "3\n", True),
    (W + "counts the vowels in mango", vowels("mango"), "2\n", True),
]


def test_requests_of_one_form_are_anti_unified_over_their_words():
    message = "Count the letter a in Banana Split, please"
    mine = hifz._tokens(message)
    theirs = hifz._tokens("count the letter o in coconut, please")
    where = hifz._shared([key for key, *_ in mine], [key for key, *_ in theirs])
    gaps = hifz._gaps(len(mine), frozenset(where))
    own = hifz._spans(message, mine, gaps, {p: p for p in range(len(mine))}, len(mine))
    # The user's own words, in their own case, from the first to the last word.
    assert own == [("a", 1), ("Banana Split", 2)]
    other = hifz._spans("count the letter o in coconut, please", theirs, gaps, where, len(mine))
    assert [text for text, _ in other] == ["o", "coconut"]

    def shared(first, second):
        return hifz._shared(
            [key for key, *_ in hifz._tokens(first)], [key for key, *_ in hifz._tokens(second)]
        )

    # A word only added or only left out is not a span, and a number is never one.
    assert shared("greet Ali twice", "greet Ali") is None
    assert shared("greet Ali 3 times", "greet 3 Ali times") is None
    assert shared("greet Ali 3 times", "greet Bilal 5 times") is not None


def test_a_template_takes_a_span_of_the_users_own_words(tmp_path):
    store = store_of(tmp_path, GREETINGS[:1])
    assert hifz.template(store, "u", W + "prints a greeting for Omar", "python") is None  # one
    store = store_of(tmp_path, GREETINGS, "b.db")
    made = hifz.template(store, "u", W + "prints a greeting for Omar", "python")
    assert made["code"] == "print('Assalamu alaikum, Omar')"
    assert made["instances"] == 2 and made["words"] == 1
    # The user's words as they wrote them.
    lower = hifz.template(store, "u", W + "prints a greeting for omar", "python")
    assert lower["code"] == "print('Assalamu alaikum, omar')"
    # Another verb, more words than any instance's span, or this very request: none.
    assert hifz.template(store, "u", W + "prints a farewell for Omar", "python") is None
    assert hifz.template(store, "u", W + "prints a greeting for Omar twice", "python") is None
    assert hifz.template(store, "u", W + "prints a greeting for Ali", "python") is None
    assert hifz.template(store, "bob", W + "prints a greeting for Omar", "python") is None


def test_a_span_is_a_slot_only_where_the_instances_varied(tmp_path):
    def count(letter, word):
        return f's = "{word}"\nprint(s.count("{letter}"))'

    store = store_of(
        tmp_path,
        [
            (W + "counts the letter a in banana", count("a", "banana"), "3\n", True),
            (W + "counts the letter a in mango", count("a", "mango"), "1\n", True),
        ],
    )
    made = hifz.template(store, "u", W + "counts the letter a in papaya", "python")
    assert printed(made["code"]) == "3\n"
    # The letter was "a" in every instance: a new letter may be a literal there.
    assert hifz.template(store, "u", W + "counts the letter e in cheese", "python") is None
    # Two spans that both varied are two slots.
    store = store_of(
        tmp_path,
        [
            (W + "counts the letter a in banana", count("a", "banana"), "3\n", True),
            (W + "counts the letter o in coconut", count("o", "coconut"), "3\n", True),
        ],
        "b.db",
    )
    made = hifz.template(store, "u", W + "counts the letter e in cheese", "python")
    assert made["words"] == 2 and printed(made["code"]) == "3\n"


def test_numbers_and_a_span_of_words_together(tmp_path):
    store = store_of(
        tmp_path,
        [
            (
                W + "prints the first 3 letters of the word banana",
                'print("banana"[:3])',
                "ban\n",
                False,
            ),
            (
                W + "prints the first 4 letters of the word mango",
                'print("mango"[:4])',
                "mang\n",
                False,
            ),
        ],
    )
    made = hifz.template(store, "u", W + "prints the first 5 letters of the word coconut", "python")
    assert made["code"] == "print('coconut'[:5])"
    assert (
        hifz.template(store, "u", W + "prints the last 5 letters of the word coconut", "python")
        is None
    )


def test_a_users_words_stay_data_and_never_become_code(tmp_path):
    import ast

    names = ["Muhammad Ali Raza Khan", "Bilal Ahmed Shah Qureshi"]
    store = store_of(
        tmp_path,
        [(W + f"prints a greeting for {name}", greet(name), name + "\n", False) for name in names],
    )
    hostile = 'Zaid"); import os; ("Omar'
    made = hifz.template(store, "u", W + f"prints a greeting for {hostile}", "python")
    tree = ast.parse(made["code"])
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    assert [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)] == [
        f"Assalamu alaikum, {hostile}"
    ]
    assert printed(made["code"]) == f"Assalamu alaikum, {hostile}\n"
    # Braces in the user's words never open an f-string expression.
    store = store_of(
        tmp_path,
        [
            (
                W + f"prints a greeting and a message count for {name}",
                f'print(f"Assalamu alaikum, {name}! You have {{2 + 3}} messages")',
                f"Assalamu alaikum, {name}! You have 5 messages\n",
                True,
            )
            for name in names
        ],
        "b.db",
    )
    braces = "Zaid{os}Omar Khan"
    made = hifz.template(
        store, "u", W + f"prints a greeting and a message count for {braces}", "python"
    )
    tree = ast.parse(made["code"])
    assert len([node for node in ast.walk(tree) if isinstance(node, ast.FormattedValue)]) == 1
    assert printed(made["code"]) == f"Assalamu alaikum, {braces}! You have 5 messages\n"
    # A span the programs used as a name is never a slot: names are code.
    store = store_of(
        tmp_path,
        [
            (W + "stores 5 in a variable named total", "total = 5\nprint(total)", "5\n", True),
            (W + "stores 5 in a variable named count", "count = 5\nprint(count)", "5\n", True),
        ],
        "c.db",
    )
    assert hifz.template(store, "u", W + "stores 5 in a variable named result", "python") is None


def test_a_kept_program_holding_another_requests_word_is_not_reused(tmp_path):
    """Recall tolerates a differing word (80% overlap); a program that holds the
    old word as data is not for the new request."""
    banana = W + "counts the vowels in the word banana and prints the count"
    store = store_of(tmp_path, [(banana, vowels("banana"), "3\n", True)])
    assert hifz.recall(store, "u", banana, "python")["code"] == vowels("banana")
    assert hifz.recall(store, "u", banana.replace("banana", "mango"), "python") is None


def test_a_numbers_template_does_not_carry_a_word_the_new_request_lacks(tmp_path):
    def first(n, word):
        return f'print("{word}"[:{n}])'

    store = store_of(
        tmp_path,
        [
            (
                W + f"prints the first {n} letters of the word pomegranate",
                first(n, "pomegranate"),
                "pomegranat\n",
                False,
            )
            for n in (10, 11)
        ],
    )
    same = W + "prints the first 12 letters of the word pomegranate"
    assert hifz.template(store, "u", same, "python")["code"] == "print('pomegranate'[:12])"
    other = W + "prints the first 12 letters of the word watermelon"
    assert hifz.template(store, "u", other, "python") is None


# The measured set: two verified programs for requests of one form, a fresh
# request, and what the template must print (None: there must be no template).
# Ids say what is measured: "template" (a correct template), "refuse" (it must
# not template: another verb, another form, too little evidence) and "missed"
# (refused although a template would have been right: a known limit).
def _first(n, word):
    return f'print("{word}"[:{n}])'


def _count(letter, word):
    return f's = "{word}"\nprint(s.count("{letter}"))'


def _upper(word):
    return f'word = "{word}"\nprint(word.upper())'


def _letters(name):
    return f"print(f\"{name} has {{len('{name}')}} letters\")"


FIRST = [
    (W + "prints the first 3 letters of the word banana", _first(3, "banana"), "ban\n", False),
    (W + "prints the first 4 letters of the word mango", _first(4, "mango"), "mang\n", False),
]
REVERSED = [
    (W + "prints the word banana reversed", 'print("banana"[::-1])', "ananab\n", False),
    (W + "prints the word mango reversed", 'print("mango"[::-1])', "ognam\n", False),
]
MEASURED = [
    ("template-greeting", GREETINGS, W + "prints a greeting for Omar", "Assalamu alaikum, Omar\n"),
    (
        "template-users-case",
        GREETINGS,
        W + "prints a greeting for omar",
        "Assalamu alaikum, omar\n",
    ),
    ("template-vowels", VOWELS, W + "counts the vowels in coconut", "3\n"),
    ("template-reversed", REVERSED, W + "prints the word coconut reversed", "tunococ\n"),
    (
        "template-capitals",
        [
            (W + "prints the word banana in capital letters", _upper("banana"), "BANANA\n", False),
            (W + "prints the word mango in capital letters", _upper("mango"), "MANGO\n", False),
        ],
        W + "prints the word Lahore in capital letters",
        "LAHORE\n",
    ),
    (
        "template-repr",
        [
            (
                W + "prints the repr of the word banana",
                'print(repr("banana"))',
                "'banana'\n",
                False,
            ),
            (W + "prints the repr of the word mango", 'print(repr("mango"))', "'mango'\n", False),
        ],
        W + "prints the repr of the word coconut",
        "'coconut'\n",
    ),
    (
        "template-fstring",
        [
            (
                W + "prints how many letters the name Ali has",
                _letters("Ali"),
                "Ali has 3 letters\n",
                True,
            ),
            (
                W + "prints how many letters the name Zainab has",
                _letters("Zainab"),
                "Zainab has 6 letters\n",
                True,
            ),
        ],
        W + "prints how many letters the name Omar has",
        "Omar has 4 letters\n",
    ),
    (
        "template-numbers-and-words",
        FIRST,
        W + "prints the first 5 letters of the word coconut",
        "cocon\n",
    ),
    (
        "template-two-spans",
        [
            (W + "counts the letter a in banana", _count("a", "banana"), "3\n", True),
            (W + "counts the letter o in coconut", _count("o", "coconut"), "3\n", True),
        ],
        W + "counts the letter e in cheese",
        "3\n",
    ),
    (
        "template-hinglish",
        [
            (
                "Ek python program likho jo Ali ke liye salaam print kare aur run karo",
                greet("Ali"),
                "Assalamu alaikum, Ali\n",
                False,
            ),
            (
                "Ek python program likho jo Bilal ke liye salaam print kare aur run karo",
                greet("Bilal"),
                "Assalamu alaikum, Bilal\n",
                False,
            ),
        ],
        "Ek python program likho jo Omar ke liye salaam print kare aur run karo",
        "Assalamu alaikum, Omar\n",
    ),
    (
        "template-arabic-script",
        [
            (W + "prints a greeting for علی", greet("علی"), "Assalamu alaikum, علی\n", False),
            (W + "prints a greeting for بلال", greet("بلال"), "Assalamu alaikum, بلال\n", False),
        ],
        W + "prints a greeting for عمر",
        "Assalamu alaikum, عمر\n",
    ),
    (
        "template-two-word-names",
        [
            (
                W + "prints a greeting for Ali Raza",
                greet("Ali Raza"),
                "Assalamu alaikum, Ali Raza\n",
                False,
            ),
            (
                W + "prints a greeting for Bilal Ahmed",
                greet("Bilal Ahmed"),
                "Assalamu alaikum, Bilal Ahmed\n",
                False,
            ),
        ],
        W + "prints a greeting for Abdul Rahman",
        "Assalamu alaikum, Abdul Rahman\n",
    ),
    (
        "template-numbers-only",
        [
            ("Sum 1 to 10", "print(sum(range(1, 11)))", "55\n", True),
            ("Sum 1 to 20", "print(sum(range(1, 21)))", "210\n", True),
        ],
        "Sum 1 to 30",
        "465\n",
    ),
    ("refuse-another-verb-farewell", GREETINGS, W + "prints a farewell for Omar", None),
    ("refuse-another-verb-emails", GREETINGS, W + "emails a greeting for Omar", None),
    ("refuse-another-preposition", GREETINGS, W + "prints a greeting to Omar", None),
    ("refuse-another-verb-consonants", VOWELS, W + "counts the consonants in coconut", None),
    ("refuse-another-verb-sorted", REVERSED, W + "prints the word coconut sorted", None),
    ("refuse-first-not-last", FIRST, W + "prints the last 5 letters of the word coconut", None),
    ("refuse-extra-words-twice", GREETINGS, W + "prints a greeting for Omar twice", None),
    ("refuse-extra-words-and", VOWELS, W + "counts the vowels in banana and mango", None),
    ("refuse-one-instance", GREETINGS[:1], W + "prints a greeting for Omar", None),
    (
        "refuse-word-never-varied",
        [
            (
                W + f"prints the first {n} letters of the word pomegranate",
                _first(n, "pomegranate"),
                "pomegranat\n",
                False,
            )
            for n in (10, 11)
        ],
        W + "prints the first 12 letters of the word watermelon",
        None,
    ),
    (
        "refuse-word-used-as-a-name",
        [
            (W + "stores 5 in a variable named total", "total = 5\nprint(total)", "5\n", True),
            (W + "stores 5 in a variable named count", "count = 5\nprint(count)", "5\n", True),
        ],
        W + "stores 5 in a variable named result",
        None,
    ),
    (
        "refuse-programs-differ-beyond-the-span",
        [
            GREETINGS[0],
            (W + "prints a greeting for Bilal", 'print("Hello, Bilal")', "Hello, Bilal\n", False),
        ],
        W + "prints a greeting for Omar",
        None,
    ),
    (
        "refuse-unchecked-numbers",
        [(request, code, output, False) for request, code, output, _ in VOWELS],
        W + "counts the vowels in coconut",
        None,
    ),
    ("refuse-this-very-request", GREETINGS, W + "prints a greeting for Ali", None),
    (
        "missed-program-changed-the-case",
        [
            (W + "prints a greeting for ali", greet("Ali"), "Assalamu alaikum, Ali\n", False),
            (W + "prints a greeting for bilal", greet("Bilal"), "Assalamu alaikum, Bilal\n", False),
        ],
        W + "prints a greeting for omar",
        None,
    ),
    ("missed-longer-span-than-seen", GREETINGS, W + "prints a greeting for Abdul Rahman", None),
]


@pytest.mark.parametrize(
    ("kept", "fresh", "expected"),
    [case[1:] for case in MEASURED],
    ids=[case[0] for case in MEASURED],
)
def test_measured_word_templates(tmp_path, kept, fresh, expected):
    store = store_of(tmp_path, kept)
    made = hifz.template(store, "u", fresh, "python")
    if expected is None:
        assert made is None
    else:
        assert made is not None and printed(made["code"]) == expected


async def test_programs_verified_for_two_words_answer_a_third_without_the_model(
    agent, monkeypatch, alice
):
    """Hifz templates with words: the programs for "banana" and "mango" differ
    only where the requests' words differ, so "coconut" is put in."""
    outputs = ["3\n", "3\n", "2\n", "2\n", "3\n"]
    calls = []

    async def run(name, params):
        calls.append(params["command"])
        return {"stdout": outputs.pop(0), "stderr": "", "exit_code": 0}

    def check(word):
        return f'```python\nprint(len([c for c in "{word}" if c in "aeiou"]))\n```'

    monkeypatch.setattr(agent, "_execute_tool_safe", run)
    agent.ai_client = ScriptedProvider(
        [
            f"```python\n{vowels('banana')}\n```",
            check("banana"),
            f"```python\n{vowels('mango')}\n```",
            check("mango"),
        ]
    )
    for word in ("banana", "mango"):
        assert (await agent.execute(W + f"counts the vowels in {word}"))["task_verified"]
    assert len(agent.ai_client.requests) == 4
    third = await agent.execute(W + "counts the vowels in coconut")
    assert len(agent.ai_client.requests) == 4  # no model call
    assert "s = 'coconut'" in calls[-1] and "3" in third["result"]
    assert not third["task_verified"] and "your numbers or words" in third["result"]
