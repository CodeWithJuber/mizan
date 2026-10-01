"""Per-token price table for cost estimation (chat usage workstream).

Prices are USD per 1M tokens, grounded 2026-09-30 against published pricing
references (Anthropic official pricing page via costly-oss / claudeboost /
ai-topics mirrors; OpenAI official pricing via costly-oss / tokentrack /
ai-tools-guide mirrors).

THESE ARE ESTIMATES — provider list prices move without notice. Every value
rendered from this table MUST be shown with a "~" prefix (see
``backend/api/usage.py`` ``cost_estimated`` flag). When the provider reports
``usage.cost`` directly it is authoritative and this table is not consulted.

Local models (ollama, ruh) have no API cost: priced at 0.0.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("mizan.prices")

# (input $/1M, output $/1M)
PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    # Anthropic — official list pricing (checked 2026-09-24/2026-09-01 mirrors)
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI — official list pricing (checked 2026-09-15/2026-09-24 mirrors)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    # Local providers — no API cost
    "llama3.2": (0.0, 0.0),
    "ruh-local": (0.0, 0.0),
}


def _normalize(model: str) -> str:
    """Normalize a model id for table lookup.

    OpenRouter-style ids (``anthropic/claude-sonnet-4``) and dated Anthropic
    ids (``claude-sonnet-4-6-2025xxxx``) are reduced to their base family key
    so lookups hit the table without inventing new rows.
    """
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.split("/")[-1]
    if m in PRICES_PER_MILLION:
        return m
    # Prefix-family fallback: claude-sonnet-4-*-dated -> claude-sonnet-4
    for family in ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4", "gpt-4o"):
        if m.startswith(family):
            return family
    return m


def lookup(model: str) -> tuple[float, float] | None:
    """Return (input $/1M, output $/1M) for a model, or None if unknown.

    Env override ``MIZAN_PRICE_OVERRIDES`` (``model:in/out,model:in/out``)
    takes precedence so the user can correct prices without a code change.
    """
    overrides = os.environ.get("MIZAN_PRICE_OVERRIDES", "").strip()
    if overrides:
        for entry in overrides.split(","):
            try:
                name, rates = entry.split(":", 1)
                inp, outp = rates.split("/", 1)
                if name.strip().lower() == (model or "").strip().lower():
                    return (float(inp), float(outp))
            except ValueError:
                logger.warning("[PRICES] ignoring malformed override %r", entry)
    return PRICES_PER_MILLION.get(_normalize(model))


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate USD cost from token counts. Returns None when unknown.

    Never invents a price: an unlisted model yields None (caller renders
    cost display off), not a guess.
    """
    rates = lookup(model)
    if rates is None:
        return None
    inp, outp = rates
    return round((input_tokens / 1_000_000) * inp + (output_tokens / 1_000_000) * outp, 6)
