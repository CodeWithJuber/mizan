"""Model-transparency + cost helpers for the chat workstream.

Builds the per-assistant-message ``usage`` block that is:
  1. included in the ``chat_complete`` WS payload,
  2. persisted in ``agent_messages.metadata.usage`` via ``memory.save_message``,
  3. served back through ``GET /api/chat/{session_id}`` (metadata column),
  4. rendered by the frontend (``MessageMeta`` component).

Cost rule (highest priority first):
  provider-reported ``usage.cost`` (authoritative) ->
  estimate from ``backend/api/prices.py`` (flagged ``cost_estimated: True``,
  frontend MUST render with "~" prefix) ->
  no cost (cost display off, never a fabricated number).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import Any

from api.prices import estimate_cost

logger = logging.getLogger("mizan.usage")


def extract_llm_meta(llm_response: Any) -> dict:
    """Extract observed model + usage from a provider ``LLMResponse``.

    Uses the OBSERVED model string from the provider's response metadata —
    never the requested/configured model name. Missing values are simply
    absent from the returned dict (never invented).
    """
    if llm_response is None:
        return {}
    meta: dict[str, Any] = {}
    model = getattr(llm_response, "model", None)
    if model:
        meta["model"] = str(model)
    usage = getattr(llm_response, "usage", None) or {}
    if isinstance(usage, dict):
        # Normalized keys first ("input"/"output"), then provider-native
        # variants ("prompt_tokens"/"completion_tokens",
        # "input_tokens"/"output_tokens") — never invent, just read.
        inp = usage.get("input")
        if inp is None:
            inp = usage.get("prompt_tokens", usage.get("input_tokens"))
        out = usage.get("output")
        if out is None:
            out = usage.get("completion_tokens", usage.get("output_tokens"))
        if inp is not None:
            meta["input_tokens"] = inp
        if out is not None:
            meta["output_tokens"] = out
        # Preserve Mizan's bounded gate/advisory metadata for audit and UI display.
        if isinstance(usage.get("mizan"), dict):
            meta["mizan"] = usage["mizan"]
        for key in ("owned_status", "owned_reason", "proposal_id"):
            if isinstance(usage.get(key), (str, int)):
                meta[key] = usage[key]
        if isinstance(usage.get("owned_prompt"), dict):
            meta["owned_prompt"] = usage["owned_prompt"]
        checkpoint = usage.get("owned_checkpoint")
        if isinstance(checkpoint, dict) and checkpoint.get("source") in {"registry", "environment"}:
            digest = checkpoint.get("sha256")
            if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
                meta["owned_checkpoint"] = {"source": checkpoint["source"], "sha256": digest}
                generation = checkpoint.get("generation")
                if type(generation) is int and generation >= 0:
                    meta["owned_checkpoint"]["generation"] = generation
        for key in ("reasoning_tokens", "visible_output_tokens", "cache_read", "cache_creation"):
            value = usage.get(key)
            if type(value) is int and value >= 0:
                meta[key] = value
        if usage.get("reasoning_observed") is True:
            meta["reasoning_observed"] = True
        # Authoritative provider-reported cost, if the provider sends one.
        if usage.get("cost") is not None:
            meta["provider_cost"] = usage.get("cost")
    stop_reason = getattr(llm_response, "stop_reason", None)
    if stop_reason:
        meta["finish_reason"] = str(stop_reason)
    return meta


def build_usage_block(
    llm_call: dict | None,
    *,
    provider_usage_chunk: dict | None = None,
) -> dict:
    """Build the persisted/rendered ``usage`` block for one assistant message.

    ``llm_call`` is the agent's recorded ``{"model", "usage", "latency_ms"}``
    dict (see ``BaseAgent._record_llm_call``); ``provider_usage_chunk`` is an
    optional byte-for-byte forwarded raw usage chunk from the stream.
    """
    block: dict[str, Any] = {}
    if llm_call:
        meta = extract_llm_meta(llm_call.get("response"))
        block.update(meta)
        latency = llm_call.get("latency_ms")
        if latency is not None:
            block["latency_ms"] = latency
    if provider_usage_chunk:
        block["raw"] = provider_usage_chunk

    # Cost: provider-reported first (authoritative), else estimate.
    if block.get("provider_cost") is not None:
        block["cost_usd"] = block.pop("provider_cost")
        block["cost_estimated"] = False
    elif block.get("model") and (
        block.get("input_tokens") is not None or block.get("output_tokens") is not None
    ):
        est = estimate_cost(
            block["model"],
            int(block.get("input_tokens") or 0),
            int(block.get("output_tokens") or 0),
        )
        if est is not None:
            block["cost_usd"] = est
            block["cost_estimated"] = True
    return block


def build_usage_summary(calls: list[dict]) -> dict:
    """Preserve every observed call, summing only reported values."""
    blocks = [build_usage_block(call) for call in calls]
    if not blocks:
        return {}
    summary = dict(blocks[-1])
    for field in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "latency_ms",
        "cost_usd",
    ):
        reported = [block[field] for block in blocks if field in block]
        if reported:
            summary[field] = sum(reported)
    summary["calls"] = blocks
    if any(block.get("reasoning_observed") for block in blocks):
        summary["reasoning_observed"] = True
    if any(block.get("cost_estimated") for block in blocks):
        summary["cost_estimated"] = True
    if any("cost_usd" not in block for block in blocks):
        summary.pop("cost_usd", None)
        summary.pop("cost_estimated", None)
    return summary


def teacher_calls(
    result: dict,
    calls: int,
    tasks: dict[str, int] | None,
    understood: dict | None,
) -> dict:
    """How much of one request the hosted model did, by MIZAN's own kinds of work.

    ``calls`` is every provider call the run recorded (``usage.calls``); ``tasks``
    the Lisan tasks among them, the rest being the model answering in words
    ("answer"). ``zero_call`` is the goal's measure: the answer needed no hosted
    model at all. ``family``/``language`` are what Fahm read ("unplaced" when MIZAN
    did not read the request: ``llm`` mode or an evaluation). docs/teacher-calls.md.
    """
    tally = {str(k): int(v) for k, v in (tasks or {}).items() if int(v) > 0}
    direct = calls - sum(tally.values())
    if direct > 0:
        tally["answer"] = tally.get("answer", 0) + direct
    read = understood or {}
    return {
        "calls": int(calls),
        "zero_call": calls == 0,
        "tasks": tally,
        "family": str(read.get("intent") or "unplaced"),
        "language": str(read.get("language") or "unknown"),
        "source": "mizan" if result.get("orchestrator") == "mizan" else "language_model",
        "verified": bool(result.get("task_verified")),
    }


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def teacher_share(rows: Iterable[tuple[str, str]]) -> dict:
    """The goal's measure over saved answers: the share answered with no hosted-model
    call, with a Wilson 95 % interval, overall, per day and per (family, language).

    ``rows`` are ``(created_at, metadata JSON)`` of assistant messages. Answers saved
    before ``usage.lisan`` existed count by their recorded calls under the family
    "unrecorded"; incomplete answers and evaluations (stateless) are left out.
    """
    from core.adaptive import wilson_bounds

    def cell() -> dict:
        return {"requests": 0, "zero_call": 0, "calls": 0, "verified": 0}

    total = cell()
    days: dict[str, dict] = {}
    groups: dict[tuple[str, str], dict] = {}
    tasks: dict[str, int] = {}
    for created_at, raw in rows:
        try:
            meta = json.loads(raw or "{}")
        except ValueError:
            continue
        if not isinstance(meta, dict) or meta.get("status") != "complete":
            continue
        usage: dict = _as_dict(meta.get("usage"))
        if meta.get("stateless") or _as_dict(usage.get("memory")).get("stateless"):
            continue
        lisan: dict = _as_dict(usage.get("lisan"))
        if not lisan:
            calls = len(usage.get("calls") or [])
            family, language, verified = "unrecorded", "unknown", bool(usage.get("task_verified"))
        else:
            calls = int(lisan.get("calls") or 0)
            family = str(lisan.get("family") or "unplaced")
            language = str(lisan.get("language") or "unknown")
            verified = bool(lisan.get("verified"))
            for name, count in (lisan.get("tasks") or {}).items():
                tasks[str(name)] = tasks.get(str(name), 0) + int(count or 0)
        for bucket in (
            total,
            days.setdefault(str(created_at)[:10], cell()),
            groups.setdefault((family, language), cell()),
        ):
            bucket["requests"] += 1
            bucket["zero_call"] += calls == 0
            bucket["calls"] += calls
            bucket["verified"] += verified

    def share(bucket: dict) -> dict:
        n, z = bucket["requests"], bucket["zero_call"]
        low, high = wilson_bounds(z, n)
        return {
            **bucket,
            "zero_call_share": round(z / n, 4) if n else None,
            "interval": [round(low, 4), round(high, 4)] if n else None,
        }

    return {
        **share(total),
        "by_day": [{"day": day, **share(days[day])} for day in sorted(days)],
        "by_family": [
            {"family": family, "language": language, **share(bucket)}
            for (family, language), bucket in sorted(
                groups.items(), key=lambda item: (-item[1]["requests"], item[0])
            )
        ],
        "lisan_tasks": dict(sorted(tasks.items(), key=lambda item: -item[1])),
    }
