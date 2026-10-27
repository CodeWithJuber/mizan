"""Silsila: sequences answered by a rule MIZAN proves on every term, and the fixes from a live chat."""

import subprocess
import sys
from copy import deepcopy

import pytest
from fastapi import HTTPException

from agents.specialized import create_agent
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.izn import IznPermission
from tadbir import amal, silsila


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
    created = create_agent("general", izn=IznPermission())
    created.ai_client = ScriptedProvider()
    monkeypatch.setattr(
        created,
        "get_tool_schemas",
        lambda: [{"name": "workspace_run", "description": "", "input_schema": {"type": "object"}}],
    )
    monkeypatch.setattr(created, "_chat_tool_allowed", lambda name: True)

    async def no_oeis(seq, timeout=10.0):
        return []

    monkeypatch.setattr(silsila, "oeis", no_oeis)
    return created


def sandbox(agent, monkeypatch):
    async def run(name, params):
        done = subprocess.run(
            [sys.executable, "-I", "-c", params["command"]], capture_output=True, text=True
        )
        return {"stdout": done.stdout, "stderr": done.stderr, "exit_code": done.returncode}

    monkeypatch.setattr(agent, "_execute_tool_safe", run)


FIRST = "13, 26, 64, 118, 274, 376, find next number"
SECOND = "7, 35,3385,74099,10671,753,593 find next number"


@pytest.mark.parametrize(
    "terms,formula,upcoming",
    [
        ([13, 26, 64, 118, 274, 376], "a(n) = 2p^2 + 3p - 1", 628),
        ([1, 1, 2, 3, 5, 8, 13], "a(n) = a(n-1) + a(n-2)", 21),
        ([1, 4, 9, 16, 25], "a(n) = n^2", 36),
        ([3, 5, 7, 9], "a(n) = 2n + 1", 11),
    ],
)
def test_mizans_own_methods_prove_the_rule_on_every_term(terms, formula, upcoming):
    (rule,) = silsila.own_rules(terms)
    assert (rule.formula, rule.next, rule.checked) == (formula, upcoming, len(terms))


def test_a_rule_needs_terms_to_spare_and_no_rule_is_forced():
    assert silsila.own_rules([7, 35, 3385, 74099, 10671, 753, 593]) == []
    # Four points fit a cubic exactly; with no term to spare it proves nothing.
    assert all(rule.method != "polynomial in n" for rule in silsila.own_rules([1, 7, 2, 9]))


def test_sequences_and_follow_ups_are_recognised():
    assert silsila.parse(FIRST) == [13, 26, 64, 118, 274, 376]
    assert silsila.parse(SECOND) == [7, 35, 3385, 74099, 10671, 753, 593]
    assert silsila.parse("I have 3, 4, 5, 6 apples") is None
    assert silsila.follow_up("Can you learn and take time to find the next number")
    assert silsila.follow_up("You should take help of all number theories search internet")
    history = [{"role": "user", "content": FIRST}, {"role": "assistant", "content": "…"}]
    assert silsila.from_history(history) == [13, 26, 64, 118, 274, 376]


async def test_the_first_sequence_is_solved_without_the_model(agent):
    result = await agent.execute(FIRST)
    assert result["task_verified"] and "**628**" in result["result"]
    assert "2p^2 + 3p - 1" in result["result"]
    assert agent.ai_client.requests == []
    assert result["isnad"]["supported"] == 1.0


async def test_an_unknown_sequence_gets_no_guess(agent, monkeypatch):
    sandbox(agent, monkeypatch)
    wrong = "```python\ndef a(n):\n    # squares\n    return n * n\n```"
    agent.ai_client = ScriptedProvider([wrong, wrong, wrong])
    result = await agent.execute(SECOND)
    assert result["task_verified"] is False
    assert "gives no next number" in result["result"]
    assert "Term 1: expected 7, got 1" in agent.ai_client.requests[1]["messages"][0]["content"]


async def test_a_rule_lisan_proposes_is_accepted_only_after_the_sandbox_proves_it(
    agent, monkeypatch
):
    sandbox(agent, monkeypatch)
    terms = "2, 6, 24, 120, 720 next number?"  # factorials: none of MIZAN's own methods
    right = "```python\ndef a(n):\n    # (n+1)! \n    import math\n    return math.factorial(n + 1)\n```"
    agent.ai_client = ScriptedProvider([right])
    result = await agent.execute(terms)
    assert result["task_verified"] and "**5040**" in result["result"]


async def test_a_follow_up_uses_the_sequence_asked_earlier(agent):
    history = [{"role": "user", "content": FIRST}, {"role": "assistant", "content": "628"}]
    result = await agent.execute(
        "Can you learn and take time to find the next number", {"history": history}
    )
    assert "**628**" in result["result"]
    assert result["orchestration"]["entities"]["understood_by"] == "conversation"


# From the owner's chat export of 27 Oct 2026, 16:13.
GAPPED = "13, 26, 64, 118, 274, ?, 628, 778, 1126 find missing ? Number"
LIMIT = (
    r"A sequence is defined by x₀ = 1 and \(x_{n+1} = x_n + \frac{1}{x_n}\) for n ≥ 0. "
    r"Prove or disprove whether the sequence converges, and find the exact limit of "
    r"\(\frac{x_{n}}{\sqrt{n}}\) as n → ∞."
)


def test_a_missing_term_is_read_with_the_terms_after_it():
    assert silsila.with_gap(GAPPED) == (
        [13, 26, 64, 118, 274, 628, 778, 1126],
        [1, 2, 3, 4, 5, 7, 8, 9],
        6,
    )
    # A "?" at the end asks for the next term; a sequence never has two gaps.
    assert silsila.with_gap("1, 2, 4, 8, 16, ?") is None
    assert silsila.with_gap("1, ?, 4, ?, 16, 32, 64") is None
    (rule,) = silsila.missing_rules(*silsila.with_gap(GAPPED))
    assert (rule.formula, rule.next, rule.checked) == ("a(n) = 2p^2 + 3p - 1", 376, 8)
    # Terms after the gap rule out what the terms before it alone would allow.
    assert silsila.missing_rules([1, 4, 9, 16, 99, 50], [1, 2, 3, 4, 6, 7], 5) == []


async def test_the_missing_term_is_proven_on_every_known_term(agent):
    result = await agent.execute(GAPPED)
    assert result["task_verified"] and "missing number" in result["result"]
    assert "**376**" in result["result"] and "all 8 terms" in result["result"]
    assert "274, ?, 628" in result["result"]
    assert agent.ai_client.requests == []


async def test_a_problem_with_its_own_definition_is_not_a_follow_up(agent):
    # It was answered with the sequence from an earlier message, from memory.
    history = [{"role": "user", "content": FIRST}, {"role": "assistant", "content": "**628**"}]
    agent.ai_client = ScriptedProvider(["It diverges, and x(n)/sqrt(n) tends to sqrt(2)."])
    result = await agent.execute(LIMIT, {"history": history})
    assert "628" not in result["result"] and "sqrt(2)" in result["result"]
    assert len(agent.ai_client.requests) == 1


async def test_a_question_mark_takes_up_the_request_left_unanswered(agent):
    # The reply to GAPPED failed (an empty reply is not kept), then the user sent "?".
    result = await agent.execute("?", {"history": [{"role": "user", "content": GAPPED}]})
    assert "**376**" in result["result"]
    assert result["orchestration"]["intent"] == "silsila"


async def test_a_question_mark_after_an_answer_is_conversation_not_a_search(agent):
    history = [
        {"role": "user", "content": "Salaam"},
        {"role": "assistant", "content": "Wa alaikum salaam"},
    ]
    agent.ai_client = ScriptedProvider(["What would you like to know?"])
    result = await agent.execute("?", {"history": history})
    assert "no ayah" not in result["result"] and "Quran" not in result["result"]
    assert len(agent.ai_client.requests) == 1


def test_a_vague_need_is_never_matched_to_an_unrelated_tool():
    tools = [
        {"name": "workspace_list", "description": "List the user's coding projects"},
        {
            "name": "mcp__github__list_issues",
            "description": "List the open issues of a GitHub repository",
        },
    ]

    class Agent:
        adaptive = None

    assert amal.choose(Agent(), tools, "learn and take time to find the next number", "") is None
    chosen = amal.choose(Agent(), tools, "list my GitHub issues", "")
    assert chosen["name"] == "mcp__github__list_issues"


async def test_web_search_command_formats_results(monkeypatch):
    from api.commands import cmd_web_search
    from skills.builtin.web_browse import WebBrowseSkill

    async def search(self, query):
        return {"results": [{"title": "OEIS", "url": "https://oeis.org", "snippet": "Sequences"}]}

    monkeypatch.setattr(WebBrowseSkill, "search", search)
    text = await cmd_web_search("integer sequences")
    assert "1. [OEIS](https://oeis.org)" in text and "Sequences" in text


def test_scratch_never_counts_against_the_project_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIZAN_WORKSPACE_ROOT", raising=False)
    from skills.builtin.coding_workspace import scratch_project
    from workspace.store import MAX_WORKSPACES, WorkspaceStore

    store = WorkspaceStore("quota-user")
    for index in range(MAX_WORKSPACES):
        store.create(f"project {index}")
    assert scratch_project(store)  # code from a chat still runs
    with pytest.raises(HTTPException) as caught:
        store.create("one more")
    assert caught.value.status_code == 413 and "Delete one" in caught.value.detail
