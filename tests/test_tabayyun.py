"""Tabayyun (49:6): MIZAN asks one question before an action it would otherwise guess.

The rule: ask exactly when Fahm read no decisive request for the action, the action
changes something, and a reference it needs (an address, a link, a handle, an id, a
number, a date) is not in the person's words in this chat or in what MIZAN saw in
this run. Interactive chats get one question card; unattended runs hold the action;
a read never asks.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents import events
from agents.base import _model_directed
from agents.specialized import create_agent
from connectors import elicitation
from security import approvals
from security.approvals import bind_approvals, collecting_held
from security.auth import TokenPayload, bind_principal, reset_principal
from tadbir import tabayyun

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
SEND = {
    "name": "send_email",
    "description": "Send an email for the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "format": "email"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
}
CLOSE = {
    "name": "close_issue",
    "description": "Close an issue.",
    "input_schema": {
        "type": "object",
        "properties": {"number": {"type": "integer"}},
        "required": ["number"],
    },
}
CONVERSE = {"intent": "converse", "language": "en", "confidence": 0.0, "by": "fahm"}


@pytest.fixture(autouse=True)
def asking(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_TABAYYUN", "ask")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    approvals._HELD_STORES.clear()


@pytest.fixture
def agent(monkeypatch):
    ran: list = []
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    made = create_agent("general", name="Tabayyun", wali=MagicMock(), izn=izn)
    made._chat_tool_allowed = lambda name: True
    for name in ("send_email", "close_issue"):

        async def handler(_name=name, **params):
            ran.append((_name, params))
            return {"ok": True}

        made.tools[name] = handler
    monkeypatch.setattr(made, "get_tool_schemas", lambda: [SEND, CLOSE])
    made._understood = dict(CONVERSE)
    made.ran = ran
    return made


class Answering:
    """The person, answering MIZAN's question card (or declining it)."""

    def __init__(self, answer: str | None):
        self.answer = answer
        self.questions: list[dict] = []

    async def __call__(self, kind, payload):
        if kind != "elicitation":
            return
        self.questions.append(payload)
        if self.answer is None:
            elicitation.broker.resolve("alice", payload["id"], "decline")
        else:
            elicitation.broker.resolve("alice", payload["id"], "accept", {"answer": self.answer})


async def model_calls(agent, tool, params):
    token = _model_directed.set(True)
    try:
        return await agent._execute_tool_safe(tool, params)
    finally:
        _model_directed.reset(token)


def interactive():
    return approvals.chat_context("alice", "chat-1", "auto")


MAIL = {"to": "bob@example.com", "subject": "Lunch", "body": "Are we still on for lunch?"}


# ── the rule, piece by piece ─────────────────────────────────────────────


def test_references_are_what_an_action_could_guess():
    assert tabayyun.particulars("bob@example.com") == ["bob@example.com"]
    assert tabayyun.particulars("See https://example.com/a, ok?") == ["https://example.com/a"]
    assert tabayyun.particulars(42) == ["42"]
    assert tabayyun.particulars("Ping @amina in #general") == ["@amina", "#general"]
    assert tabayyun.particulars("2026-12-04 at 15:30") == ["2026-12-04", "15:30"]
    assert tabayyun.particulars("acme/site") == ["acme/site"]
    # Words the action writes are not references: prose, a command, a program.
    assert tabayyun.particulars("Are we still on for lunch?") == []
    assert tabayyun.particulars("npm test") == []
    assert tabayyun.particulars("line one\nfetch('https://cdn.example.com/x.js')") == []
    assert tabayyun.particulars(True) == []


def test_a_reference_is_grounded_in_the_persons_words_or_what_the_run_saw():
    with tabayyun.bind("Email bob@example.com about lunch", []) as inquiry:
        assert tabayyun.ungrounded(MAIL, SEND, inquiry) == []
        other = {**MAIL, "to": "robert@example.org"}
        missing = tabayyun.ungrounded(other, SEND, inquiry)
        assert missing == [("to", "robert@example.org")]
        tabayyun.observe("list_contacts", {}, {"contacts": ["robert@example.org"]}, "read")
        assert tabayyun.ungrounded(other, SEND, inquiry) == []
    with tabayyun.bind(
        "close it", [{"role": "assistant", "content": "Issue #42 is open."}]
    ) as found:
        assert tabayyun.ungrounded({"number": 42}, CLOSE, found) == []
        assert tabayyun.ungrounded({"number": 41}, CLOSE, found) == [("number", 41)]


def test_only_a_decisive_reading_that_covers_the_action_lets_it_go_unasked():
    built = {"intent": "build_project", "confidence": 0.8, "by": "fahm"}
    assert tabayyun.decisive(built, "workspace_write")
    assert not tabayyun.decisive(built, "send_email")  # not the action that was read
    assert not tabayyun.decisive({**built, "confidence": 0.4}, "workspace_write")
    assert not tabayyun.decisive({**built, "by": "lisan"}, "workspace_write")  # the model's
    assert not tabayyun.decisive(CONVERSE, "workspace_write")
    assert not tabayyun.decisive(None, "workspace_write")


def test_the_setting_is_registered_and_on_by_default(monkeypatch):
    import runtime_settings

    setting = runtime_settings.BY_KEY["MIZAN_TABAYYUN"]
    assert setting.default == "ask" and setting.choices == ("ask", "off")
    monkeypatch.delenv("MIZAN_TABAYYUN")
    assert tabayyun.mode() == "ask"
    monkeypatch.setenv("MIZAN_TABAYYUN", "nonsense")
    assert tabayyun.mode() == "ask"


# ── in the gate ──────────────────────────────────────────────────────────


async def test_an_unsaid_recipient_is_asked_once_and_the_answer_is_used(agent):
    person = Answering("bob@example.com")
    principal = bind_principal(USER)
    try:
        with (
            tabayyun.bind("Tell my friend lunch is still on", []) as inquiry,
            events.bind_event_sink(person),
            bind_approvals(interactive()),
        ):
            first = await model_calls(agent, "send_email", MAIL)
            assert agent.ran == []  # not run on a guess
            assert first["clarified"]["answer"] == "bob@example.com"
            assert "bob@example.com" in first["error"]
            again = await model_calls(agent, "send_email", MAIL)
    finally:
        reset_principal(principal)
    assert again == {"ok": True} and agent.ran == [("send_email", MAIL)]
    (question,) = person.questions
    assert question["kind"] == "question" and question["server"] == "MIZAN"
    assert question["argument"] == "to" and question["tool"] == "send_email"
    assert question["schema"]["properties"]["answer"]["default"] == "bob@example.com"
    assert tabayyun.summary(inquiry) == {
        "asked": 1,
        "tool": "send_email",
        "argument": "to",
        "outcome": "answered",
    }


async def test_one_question_per_request(agent):
    person = Answering("bob@example.com")
    principal = bind_principal(USER)
    try:
        with (
            tabayyun.bind("Tell my friend lunch is still on", []),
            events.bind_event_sink(person),
            bind_approvals(interactive()),
        ):
            await model_calls(agent, "send_email", MAIL)
            later = await model_calls(agent, "close_issue", {"number": 7})
    finally:
        reset_principal(principal)
    assert len(person.questions) == 1
    assert later.get("tabayyun") and agent.ran == []


async def test_a_declined_question_runs_nothing(agent):
    person = Answering(None)
    principal = bind_principal(USER)
    try:
        with (
            tabayyun.bind("Tell my friend lunch is still on", []) as inquiry,
            events.bind_event_sink(person),
            bind_approvals(interactive()),
        ):
            result = await model_calls(agent, "send_email", MAIL)
    finally:
        reset_principal(principal)
    assert result["declined"] and agent.ran == []
    assert tabayyun.summary(inquiry)["outcome"] == "declined"


async def test_an_unattended_run_holds_the_action_for_its_owner(agent):
    principal = bind_principal(USER)
    try:
        with (
            tabayyun.bind("Tell my friend lunch is still on", []),
            approvals.unattended("alice", "watch-1", "watcher"),
            collecting_held() as held,
        ):
            result = await model_calls(agent, "send_email", MAIL)
    finally:
        reset_principal(principal)
    assert result["held_for_approval"] and agent.ran == []
    assert held[0]["tool"] == "send_email" and "to" in held[0]["reason"]


async def test_with_no_one_to_ask_the_question_goes_into_the_answer(agent):
    with tabayyun.bind("Tell my friend lunch is still on", []):
        result = await model_calls(agent, "send_email", MAIL)
        # MIZAN's own refusal names the guess; that does not make it the person's.
        again = await model_calls(agent, "send_email", MAIL)
    assert result["tabayyun"]["argument"] == "to" and agent.ran == []
    assert "ask" in result["error"].lower()
    assert again.get("tabayyun") and agent.ran == []


async def test_what_the_person_said_is_never_asked(agent):
    with (
        tabayyun.bind("Email bob@example.com that lunch is still on", []),
        bind_approvals(interactive()),
    ):
        assert await model_calls(agent, "send_email", MAIL) == {"ok": True}


async def test_reads_mizans_own_choices_and_off_are_never_asked(agent, monkeypatch):
    # MIZAN's own recipe (not the model's choice) runs what it parsed.
    with tabayyun.bind("Tell my friend lunch is still on", []), bind_approvals(interactive()):
        assert await agent._execute_tool_safe("send_email", MAIL) == {"ok": True}
    # A decisive reading that covers the action.
    agent._understood = {"intent": "build_project", "confidence": 0.9, "by": "fahm"}
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{**SEND, "name": "workspace_write"}],
    )
    agent.tools["workspace_write"] = agent.tools["send_email"]
    with tabayyun.bind("Make me a page", []), bind_approvals(interactive()):
        assert await model_calls(agent, "workspace_write", MAIL) == {"ok": True}
    # A read: a connector tool that says it only reads.
    agent._understood = dict(CONVERSE)
    monkeypatch.setattr(agent, "_read_only_hint", lambda name: True)
    with tabayyun.bind("Tell my friend lunch is still on", []), bind_approvals(interactive()):
        assert await model_calls(agent, "send_email", MAIL) == {"ok": True}
    monkeypatch.setattr(agent, "_read_only_hint", lambda name: False)
    # Off.
    monkeypatch.setenv("MIZAN_TABAYYUN", "off")
    with tabayyun.bind("Tell my friend lunch is still on", []), bind_approvals(interactive()):
        assert await model_calls(agent, "send_email", MAIL) == {"ok": True}
    assert len(agent.ran) == 4


async def test_without_a_reading_of_its_own_mizan_reads_the_request(agent):
    agent._understood = None
    with tabayyun.bind("thanks, that is all", []) as inquiry:
        result = await model_calls(agent, "send_email", MAIL)
    assert result.get("tabayyun") and agent.ran == []
    assert inquiry.understood is not None and inquiry.understood["by"] == "fahm"


async def test_a_full_run_records_the_question_in_its_usage(agent, monkeypatch):
    from providers import BaseLLMProvider, ContentBlock, LLMResponse

    class Scripted(BaseLLMProvider):
        provider_name = "fixture"

        def __init__(self):
            self.replies = [
                LLMResponse(
                    content=[
                        ContentBlock(
                            type="tool_use",
                            id="c0",
                            name="mizan_discover_tools",
                            input={"names": ["send_email"]},
                        )
                    ],
                    stop_reason="tool_use",
                ),
                LLMResponse(
                    content=[ContentBlock(type="tool_use", id="c1", name="send_email", input=MAIL)],
                    stop_reason="tool_use",
                ),
                LLMResponse(
                    content=[ContentBlock(type="tool_use", id="c2", name="send_email", input=MAIL)],
                    stop_reason="tool_use",
                ),
                LLMResponse(
                    content=[ContentBlock(type="text", text="Sent.")], stop_reason="end_turn"
                ),
            ]

        def create(self, **kwargs):
            return self.replies.pop(0)

    agent.ai_client, agent.ai_model = Scripted(), "fixture"
    agent._understood = None
    person = Answering("bob@example.com")
    principal = bind_principal(USER)
    try:
        with events.bind_event_sink(person), bind_approvals(interactive()):
            result = await agent.execute("Tell my friend lunch is still on")
    finally:
        reset_principal(principal)
    assert agent.ran == [("send_email", MAIL)]
    assert result["usage"]["tabayyun"]["outcome"] == "answered"
