"""Execution receipts describe delivery and observations, never proof of correctness."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def prepare_tool_call(
    fn: Callable, params: dict, invoke_style: str = "kwargs"
) -> tuple[tuple, dict]:
    """Bind arguments before invoking a tool; a body exception must never replay it."""
    if invoke_style not in {"kwargs", "dict"}:
        raise ValueError("Unknown tool invocation style")
    if not isinstance(params, dict):
        raise TypeError("Tool parameters must be a dictionary")
    candidates = {"kwargs": ((), params), "dict": ((params,), {})}
    preferred = candidates[invoke_style]
    try:
        signature = inspect.signature(fn)
    except (ValueError, TypeError):
        # Opaque callables get one invocation with their registered convention.
        return preferred
    try:
        signature.bind(*preferred[0], **preferred[1])
        return preferred
    except TypeError as preferred_error:
        alternate = candidates["dict" if invoke_style == "kwargs" else "kwargs"]
        try:
            signature.bind(*alternate[0], **alternate[1])
        except TypeError:
            raise preferred_error from None
        return alternate


def tool_result_failed(result: Any) -> bool:
    """Recognize explicit failure fields without interpreting arbitrary tool text."""
    if not isinstance(result, dict):
        return False
    if result.get("error") or result.get("success") is False or result.get("timed_out"):
        return True
    for key in ("returncode", "exit_code"):
        value = result.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value != 0:
            return True
    status = result.get("status")
    return isinstance(status, int) and status >= 400


def completion_metadata(response: Any) -> dict[str, Any]:
    """Classify the final provider receipt, keeping abstention separate from an answer.

    Capture eligibility means an unreviewed example may be saved. It is not
    training eligibility, task verification, or a claim that the answer is true.
    """
    if response is None:
        return {
            "completion_status": "missing_receipt",
            "answer_delivered": False,
            "task_verified": False,
            "capture_eligible": False,
        }
    has_text = any(
        getattr(block, "type", "") == "text" and bool(getattr(block, "text", "").strip())
        for block in (getattr(response, "content", None) or [])
    )
    usage = getattr(response, "usage", None) or {}
    usage = usage if isinstance(usage, dict) else {}
    owned_status = usage.get("owned_status")
    mizan = usage.get("mizan")
    gate = mizan.get("gate", {}) if isinstance(mizan, dict) else {}
    gate = gate if isinstance(gate, dict) else {}
    gate_outcome = gate.get("outcome")
    stop = getattr(response, "stop_reason", "")
    if owned_status == "abstained" or gate_outcome == "ABSTAIN":
        status = "abstained"
    elif gate_outcome == "HUMAN_REVIEW":
        status = "human_review_required"
    elif gate_outcome == "RETRY" or stop in {"max_tokens", "incomplete"}:
        status = "incomplete"
    elif stop == "tool_use":
        status = "tool_request"
    elif not has_text:
        status = "empty_response"
    elif owned_status == "reviewed_memory":
        status = "reviewed_memory"
    else:
        status = "unverified_answer"
    metadata = {
        "completion_status": status,
        "answer_delivered": has_text,
        "task_verified": False,
        "capture_eligible": has_text and status in {"unverified_answer", "reviewed_memory"},
    }
    if owned_status in {"abstained", "reviewed_memory", "own_model_unverified"}:
        metadata["owned_status"] = owned_status
    return metadata
