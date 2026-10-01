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

import logging
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
