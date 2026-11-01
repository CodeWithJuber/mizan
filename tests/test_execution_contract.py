"""Provider delivery and callable binding do not certify task completion."""

import pytest

from agents.execution_contract import completion_metadata, prepare_tool_call, tool_result_failed
from providers import ContentBlock, LLMResponse


def test_binding_chooses_arguments_without_invoking_side_effects():
    calls = []

    def tool(params):
        calls.append(params)

    args, kwargs = prepare_tool_call(tool, {"path": "one.txt"}, "kwargs")
    assert calls == []
    tool(*args, **kwargs)
    assert calls == [{"path": "one.txt"}]


def test_invalid_arguments_do_not_invoke_the_callable():
    calls = []

    def tool(first, second):
        calls.append((first, second))

    with pytest.raises(TypeError):
        prepare_tool_call(tool, {"unknown": 1})
    assert calls == []


@pytest.mark.parametrize(
    ("usage", "expected", "capture"),
    [
        ({"owned_status": "abstained"}, "abstained", False),
        ({"owned_status": "reviewed_memory"}, "reviewed_memory", True),
        ({"owned_status": "own_model_unverified"}, "unverified_answer", True),
        ({"mizan": {"gate": {"outcome": "ABSTAIN"}}}, "abstained", False),
        ({"mizan": {"gate": {"outcome": "HUMAN_REVIEW"}}}, "human_review_required", False),
        ({"mizan": {"gate": {"outcome": "RETRY"}}}, "incomplete", False),
        ({}, "unverified_answer", True),
    ],
)
def test_receipts_preserve_abstention_and_never_claim_verification(usage, expected, capture):
    result = completion_metadata(
        LLMResponse([ContentBlock(type="text", text="A delivered message")], usage=usage)
    )
    assert result["completion_status"] == expected
    assert result["answer_delivered"]
    assert result["task_verified"] is False
    assert result["capture_eligible"] is capture


@pytest.mark.parametrize(
    "result",
    [
        {"error": "denied"},
        {"exit_code": 1},
        {"returncode": -1},
        {"timed_out": True},
        {"success": False},
        {"status": 403},
    ],
)
def test_explicit_failed_receipts_are_not_success_observations(result):
    assert tool_result_failed(result)


def test_error_word_in_successful_data_is_not_failure():
    assert not tool_result_failed({"content": 'Documentation for the "error" key', "exit_code": 0})
    assert completion_metadata(None)["capture_eligible"] is False
