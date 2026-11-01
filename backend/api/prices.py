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

import json
import logging
import math
import os
import re
from pathlib import Path

logger = logging.getLogger("mizan.prices")

# (input $/1M, output $/1M)
PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    # Anthropic — current models (Anthropic model table, checked 2026-10-26)
    "claude-fable-5-1": (10.00, 50.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    # Anthropic — previous models (checked 2026-09-24/2026-09-01 mirrors)
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI — current models (OpenRouter catalog list prices, checked 2026-10-26)
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-6-luna": (0.10, 0.50),
    # OpenAI — previous models (checked 2026-09-15/2026-09-24 mirrors)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    # Local providers — no API cost
    "llama3.2": (0.0, 0.0),
    "qwen3.8": (0.0, 0.0),
    "ruh-local": (0.0, 0.0),
}


# Live list prices from the OpenRouter catalog (USD per token there, stored
# per 1M here), refreshed with the model limits and kept on the data volume so
# a restart without network still knows them.
_LIVE: dict[str, tuple[float, float]] = {}
_LIVE_LOADED = False


def _live_path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "prices_live.json"


def _per_million(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    # OpenRouter marks variable-price routers with a negative price.
    return round(number * 1_000_000, 9) if math.isfinite(number) and number >= 0 else None


def record_live(catalog: dict[str, tuple[object, object]]) -> int:
    """Keep the catalog's list prices; returns how many models have one."""
    global _LIVE_LOADED
    live: dict[str, tuple[float, float]] = {}
    for model, (prompt, completion) in catalog.items():
        rate_in, rate_out = _per_million(prompt), _per_million(completion)
        if rate_in is not None and rate_out is not None:
            live[model.strip().lower()] = (rate_in, rate_out)
    if live:
        _LIVE.clear()
        _LIVE.update(live)
        _LIVE_LOADED = True
        try:
            path = _live_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(_LIVE))
            tmp.replace(path)
        except OSError as exc:
            logger.debug("[PRICES] live prices not saved: %s", exc)
    return len(live)


def _live(model: str) -> tuple[float, float] | None:
    global _LIVE_LOADED
    if not _LIVE_LOADED:
        _LIVE_LOADED = True
        try:
            saved = json.loads(_live_path().read_text())
            _LIVE.update({str(k): (float(v[0]), float(v[1])) for k, v in saved.items()})
        except (OSError, ValueError, TypeError, IndexError):
            pass
    return _LIVE.get((model or "").strip().lower())


def _normalize(model: str) -> str:
    """Normalize a model id for table lookup.

    OpenRouter-style ids (``anthropic/claude-sonnet-4``) and dated Anthropic
    ids (``claude-sonnet-4-6-2025xxxx``) are reduced to their base family key
    so lookups hit the table without inventing new rows.
    """
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.split("/")[-1]
    # OpenRouter writes Claude versions with a dot (claude-opus-5.5).
    m = re.sub(r"^(claude-[a-z]+-\d+)\.(\d+)", r"\1-\2", m)
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
    found = PRICES_PER_MILLION.get(_normalize(model))
    return found if found is not None else _live(model)


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
