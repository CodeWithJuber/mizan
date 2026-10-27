"""Iqtisad (اقتصاد): hard per-user limits on what model calls may cost.

Spending is held to a measure (al-Furqan 25:67): every paid model call is
admitted against its user's remaining daily and monthly budget *before* it is
sent, and settled with what it really cost afterwards.

Admission bounds the call's worst case, so a single call cannot overspend:

- **Input** is bounded from the request's size. A byte-level tokenizer makes at
  most one token per UTF-8 byte, so ``bytes`` is a hard upper bound. Once a
  model has been observed, MIZAN uses its learned tokens-per-byte ratio
  (exponentially weighted mean + 2σ), and falls back to the hard bound whenever
  the remaining money is within twice the learned estimate.
- **Output** is bounded by ``max_tokens``, which providers enforce. MIZAN caps
  it at what the remaining money can pay for. If even the learned 10th
  percentile of this model's answers no longer fits, the call is refused
  instead of being cut short.
- In-flight calls hold a reservation, so parallel calls cannot spend the same
  money twice.

Prices come from ``api.prices`` (provider list prices, overridable); a model
with no known price is refused while a limit applies, unless
``MIZAN_BUDGET_UNPRICED=allow``. Provider-reported cost, when sent, is what is
charged. Local models (Ollama, Ruh, the owned model) never pass through here.

Limits: ``MIZAN_BUDGET_DAILY_USD`` / ``MIZAN_BUDGET_MONTHLY_USD`` apply to every
user who is not an administrator; an administrator can set a limit for any
user, and every user can lower their own. The day is the user's local day.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from api import prices
from core.adaptive import EWStats

logger = logging.getLogger("mizan.iqtisad")

# One-sided z for the input bound (≈97.7%) and for the useful-output floor
# (the 10th percentile of a normal).
_Z_INPUT = 2.0
_Z_OUTPUT_P10 = 1.2816
# Documented per-image token ceiling for a full-size image (Anthropic vision
# guide); used only to bound images, never to charge them.
_IMAGE_TOKENS = 1600
# Anthropic prompt-cache prices relative to input (pricing page).
CACHE_WRITE = 1.25
CACHE_READ = 0.10


class BudgetExhausted(RuntimeError):
    """The current user's budget cannot pay for this call."""

    def __init__(
        self,
        period: str,
        limit: float | None,
        spent: float,
        resets_at: str,
        *,
        reason: str = "limit",
        model: str = "",
    ):
        self.period, self.limit, self.spent = period, limit, spent
        self.resets_at, self.reason, self.model = resets_at, reason, model
        if reason == "unavailable":
            text = "MIZAN cannot read its spending ledger, so no paid call may run"
        elif reason == "unpriced":
            text = (
                f"MIZAN has no price for the model {model!r}, so it cannot keep "
                "this call inside your spending limit"
            )
        else:
            word = "daily" if period == "day" else "monthly"
            text = (
                f"Your {word} model budget (${limit:.2f}) is used up "
                f"(${spent:.4f} spent); it renews at {resets_at}"
            )
        super().__init__(text)

    def public(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "limit_usd": self.limit,
            "spent_usd": round(self.spent, 6),
            "resets_at": self.resets_at,
            "reason": self.reason,
        }


# ── storage ──────────────────────────────────────────────────────────────


class Ledger:
    """Spend rows, limits and calibration for every user (one SQLite file)."""

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS spend (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, day TEXT NOT NULL,
                    month TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER,
                    output_tokens INTEGER, cost_usd REAL NOT NULL, source TEXT NOT NULL,
                    created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS spend_owner_day ON spend(owner_id, day);
                CREATE INDEX IF NOT EXISTS spend_owner_month ON spend(owner_id, month);
                CREATE TABLE IF NOT EXISTS limits (
                    owner_id TEXT NOT NULL, scope TEXT NOT NULL, daily_usd REAL,
                    monthly_usd REAL, updated TEXT NOT NULL,
                    PRIMARY KEY (owner_id, scope));
                CREATE TABLE IF NOT EXISTS zones (
                    owner_id TEXT PRIMARY KEY, zone TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calibration (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    _SPENT = {
        "day": "SELECT COALESCE(SUM(cost_usd), 0) FROM spend WHERE owner_id=? AND day=?",
        "month": "SELECT COALESCE(SUM(cost_usd), 0) FROM spend WHERE owner_id=? AND month=?",
    }

    def spent(self, owner: str, column: str, value: str) -> float:
        with self._connect() as conn:
            row = conn.execute(self._SPENT[column], (owner, value)).fetchone()
        return float(row[0] or 0.0)

    def record(
        self,
        owner: str,
        day: str,
        month: str,
        model: str,
        tokens: tuple[int, int],
        cost: float,
        source: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO spend VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    owner,
                    day,
                    month,
                    model,
                    tokens[0],
                    tokens[1],
                    float(cost),
                    source,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def limits(self, owner: str) -> dict[str, dict[str, float | None]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT scope, daily_usd, monthly_usd FROM limits WHERE owner_id=?", (owner,)
            ).fetchall()
        return {
            row["scope"]: {"day": row["daily_usd"], "month": row["monthly_usd"]} for row in rows
        }

    def set_limits(self, owner: str, scope: str, day: float | None, month: float | None) -> None:
        with self._lock, self._connect() as conn:
            if day is None and month is None:
                conn.execute("DELETE FROM limits WHERE owner_id=? AND scope=?", (owner, scope))
                return
            conn.execute(
                "INSERT INTO limits VALUES (?,?,?,?,?) ON CONFLICT(owner_id, scope) DO UPDATE "
                "SET daily_usd=excluded.daily_usd, monthly_usd=excluded.monthly_usd, "
                "updated=excluded.updated",
                (owner, scope, day, month, datetime.now(UTC).isoformat()),
            )

    def zone(self, owner: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT zone FROM zones WHERE owner_id=?", (owner,)).fetchone()
        return str(row[0]) if row else None

    def remember_zone(self, owner: str, zone: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO zones VALUES (?,?) ON CONFLICT(owner_id) DO UPDATE "
                "SET zone=excluded.zone",
                (owner, zone),
            )

    def stats(self, key: str) -> EWStats:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM calibration WHERE key=?", (key,)).fetchone()
        return EWStats.from_dict(json.loads(row[0])) if row else EWStats()

    def observe(self, key: str, value: float) -> None:
        with self._lock:
            stats = self.stats(key)
            stats.update(value)
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO calibration VALUES (?,?) ON CONFLICT(key) DO UPDATE "
                    "SET value=excluded.value",
                    (key, json.dumps(stats.to_dict())),
                )

    def history(self, owner: str, days: int) -> list[dict]:
        since = (datetime.now(UTC) - timedelta(days=days + 1)).date().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT day, SUM(cost_usd) AS cost, COUNT(*) AS calls FROM spend "
                "WHERE owner_id=? AND day>=? GROUP BY day ORDER BY day",
                (owner, since),
            ).fetchall()
        return [
            {"day": r["day"], "cost_usd": round(r["cost"], 6), "calls": r["calls"]} for r in rows
        ]

    def by_model(self, owner: str, month: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT model, SUM(cost_usd) AS cost, COUNT(*) AS calls, "
                "SUM(source != 'provider') AS estimated FROM spend "
                "WHERE owner_id=? AND month=? GROUP BY model ORDER BY cost DESC",
                (owner, month),
            ).fetchall()
        return [
            {
                "model": r["model"],
                "cost_usd": round(r["cost"], 6),
                "calls": r["calls"],
                "estimated_calls": int(r["estimated"] or 0),
            }
            for r in rows
        ]

    def owners(self, month: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT owner_id, SUM(cost_usd) AS cost, COUNT(*) AS calls FROM spend "
                "WHERE month=? GROUP BY owner_id ORDER BY cost DESC",
                (month,),
            ).fetchall()
        return [
            {"owner_id": r["owner_id"], "cost_usd": round(r["cost"], 6), "calls": r["calls"]}
            for r in rows
        ]


_LEDGERS: dict[str, Ledger] = {}
_LEDGER_LOCK = threading.Lock()


def ledger() -> Ledger | None:
    """The spending ledger, or None where the data directory cannot be written."""
    path = str(Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "iqtisad.db")
    with _LEDGER_LOCK:
        if path not in _LEDGERS:
            try:
                _LEDGERS[path] = Ledger(path)
            except (OSError, sqlite3.Error) as exc:
                logger.debug("[IQTISAD] no ledger at %s: %s", path, exc)
                return None
        return _LEDGERS[path]


# ── who, when, how much ─────────────────────────────────────────────────


def _owner() -> str:
    from security.auth import current_user_id

    return current_user_id() or ""


def _is_admin() -> bool:
    from security.auth import request_has_role

    return bool(request_has_role("admin"))


def _money(name: str) -> float | None:
    text = os.getenv(name, "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        logger.warning("[IQTISAD] ignoring non-numeric %s", name)
        return None
    return value if math.isfinite(value) and value >= 0 else None


def effective_limits(owner: str, *, admin: bool) -> dict[str, float | None]:
    """The tightest of: the server default (non-admins) or the admin's limit
    for this user, and the user's own lower limit."""
    store = ledger()
    saved = store.limits(owner) if owner and store else {}
    result: dict[str, float | None] = {}
    for period, setting in (
        ("day", "MIZAN_BUDGET_DAILY_USD"),
        ("month", "MIZAN_BUDGET_MONTHLY_USD"),
    ):
        if "admin" in saved:
            base = saved["admin"][period]
        else:
            base = None if admin or not owner else _money(setting)
        own = saved.get("self", {}).get(period)
        present = [value for value in (base, own) if value is not None]
        result[period] = min(present) if present else None
    return result


def _zone_named(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - unknown or malformed zone names
        return None


def _zone(owner: str) -> ZoneInfo:
    """The user's zone: the chat's own if bound (and remembered), else the
    last one remembered, else UTC."""
    from tadbir import waqt

    _, bound = waqt.now()
    zone = _zone_named(bound)
    store = ledger()
    if zone is not None:
        if store is not None and owner and store.zone(owner) != bound:
            store.remember_zone(owner, str(bound))
        return zone
    saved = store.zone(owner) if store is not None and owner else None
    return _zone_named(saved) or ZoneInfo("UTC")


def periods(owner: str) -> tuple[str, str, dict[str, str]]:
    """(day, month, period → when it renews, ISO with offset)."""
    zone = _zone(owner)
    now = datetime.now(zone)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return (
        now.date().isoformat(),
        now.strftime("%Y-%m"),
        {"day": tomorrow.isoformat(), "month": next_month.isoformat()},
    )


# ── sizing a request ─────────────────────────────────────────────────────


def _size(value: Any) -> tuple[int, int]:
    """(UTF-8 bytes of the text it carries, images) for a request part."""
    if isinstance(value, str):
        return len(value.encode("utf-8")), 0
    if isinstance(value, dict):
        if value.get("type") == "image" or value.get("type") == "image_url":
            return 0, 1
        size, images = 0, 0
        for key, item in value.items():
            part, found = _size(item)
            size += part + len(str(key))
            images += found
        return size, images
    if isinstance(value, (list, tuple)):
        size, images = 0, 0
        for item in value:
            part, found = _size(item)
            size, images = size + part, images + found
        return size, images
    if value is None:
        return 0, 0
    return len(str(value).encode("utf-8")), 0


def _family(model: str) -> str:
    return (model or "").strip().lower()


# ── admission and settlement ─────────────────────────────────────────────

_INFLIGHT: dict[str, float] = {}
_INFLIGHT_LOCK = threading.Lock()


@dataclass
class Ticket:
    """One admitted call: what it may cost, and how it is settled."""

    owner: str
    model: str
    max_tokens: int
    input_bytes: int
    images: int
    rates: tuple[float, float] | None
    reserved: float = 0.0
    cache_write: float = 1.0
    settled: bool = field(default=False)

    def _release(self) -> None:
        if self.reserved:
            with _INFLIGHT_LOCK:
                left = _INFLIGHT.get(self.owner, 0.0) - self.reserved
                if left > 1e-12:
                    _INFLIGHT[self.owner] = left
                else:
                    _INFLIGHT.pop(self.owner, None)
            self.reserved = 0.0

    def release(self) -> None:
        """The call was rejected before running: nothing to charge."""
        if not self.settled:
            self.settled = True
            self._release()

    def settle(
        self, usage: dict | None, model: str | None = None, *, streamed_bytes: int = 0
    ) -> float:
        """Charge what the call cost; learn this model's token sizes."""
        if self.settled:
            return 0.0
        self.settled = True
        try:
            return self._charge(usage or {}, model or self.model, streamed_bytes)
        except Exception:  # noqa: BLE001 - accounting must never break a reply
            logger.exception("[IQTISAD] could not record spend")
            return 0.0
        finally:
            self._release()

    def _charge(self, usage: dict, model: str, streamed_bytes: int) -> float:
        store = ledger()
        if store is None:
            return 0.0
        family = _family(self.model)
        inp = _int(usage.get("input"))
        out = _int(usage.get("output"))
        cache_read = _int(usage.get("cache_read")) or 0
        cache_write = _int(usage.get("cache_creation")) or 0
        if inp is not None and self.input_bytes > 0 and not self.images:
            store.observe(f"ratio:{family}", (inp + cache_read + cache_write) / self.input_bytes)
        if out is not None:
            store.observe(f"output:{family}", float(out))
        provider_cost = usage.get("cost")
        source = "provider"
        if inp is None or out is None:
            # The call ended without a full usage record (cut off or failed
            # mid-stream): what is missing is charged at its bound, so an
            # unreported call is never free.
            ratio = store.stats(f"ratio:{family}")
            per_byte = min(1.0, ratio.mean) if ratio.count >= 3 else 1.0
            if inp is None:
                inp = math.ceil(self.input_bytes * per_byte) + self.images * _IMAGE_TOKENS
            if out is None:
                out = math.ceil(streamed_bytes * per_byte)
            source = "bound"
        if isinstance(provider_cost, (int, float)) and not isinstance(provider_cost, bool):
            cost, source = float(provider_cost), "provider"
        else:
            rates = prices.lookup(model) or self.rates
            if rates is None:
                cost, source = 0.0, "unpriced"
            else:
                source = "table" if source == "provider" else source
                rate_in, rate_out = rates
                cost = (
                    inp * rate_in
                    + cache_write * rate_in * CACHE_WRITE
                    + cache_read * rate_in * CACHE_READ
                    + out * rate_out
                ) / 1_000_000
        day, month, _ = periods(self.owner)
        store.record(self.owner, day, month, model, (inp or 0, out or 0), cost, source)
        return cost


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _rates(models: Iterable[str]) -> tuple[float, float] | None:
    """The highest input and output price among the models a request may use."""
    found = [prices.lookup(model) for model in models if model]
    if not found or any(rate is None for rate in found):
        return None
    return (max(rate[0] for rate in found if rate), max(rate[1] for rate in found if rate))


def admit(
    model: str,
    max_tokens: int,
    request: Any,
    *,
    fallbacks: Iterable[str] = (),
    cache_write: float = 1.0,
) -> Ticket:
    """Admit one paid call for the current user, or raise ``BudgetExhausted``.

    Returns a ticket whose ``max_tokens`` is what the call may produce.
    """
    owner = _owner()
    size, images = _size(request)
    rates = _rates([model, *fallbacks])
    ticket = Ticket(
        owner, model, max(1, int(max_tokens)), size, images, rates, cache_write=cache_write
    )
    limits = effective_limits(owner, admin=_is_admin())
    if all(value is None for value in limits.values()):
        return ticket
    day, month, renews = periods(owner)
    store = ledger()
    if store is None:
        # A limit applies but nothing can be counted against it: fail closed.
        period = "day" if limits["day"] is not None else "month"
        raise BudgetExhausted(
            period, limits[period], 0.0, renews[period], reason="unavailable", model=model
        )
    if rates is None:
        if os.getenv("MIZAN_BUDGET_UNPRICED", "refuse").strip().lower() == "allow":
            return ticket
        period = "day" if limits["day"] is not None else "month"
        raise BudgetExhausted(
            period, limits[period], 0.0, renews[period], reason="unpriced", model=model
        )
    with _INFLIGHT_LOCK:
        inflight = _INFLIGHT.get(owner, 0.0)
    remaining, tight_period, spent_in = math.inf, "day", 0.0
    for period, column in (("day", day), ("month", month)):
        limit = limits[period]
        if limit is None:
            continue
        spent = store.spent(owner, period, column)
        left = limit - spent - inflight
        if left < remaining:
            remaining, tight_period, spent_in = left, period, spent
    rate_in, rate_out = rates
    family = _family(model)
    ratio = store.stats(f"ratio:{family}")
    hard = size + images * _IMAGE_TOKENS
    learned = hard
    if ratio.count >= 3:
        learned = (
            math.ceil(size * min(1.0, ratio.mean + _Z_INPUT * ratio.std)) + images * _IMAGE_TOKENS
        )
    input_rate = rate_in * max(1.0, cache_write)
    learned_cost = learned * input_rate / 1_000_000
    # Close to the limit, use the hard bound instead of the learned one.
    tokens_in = hard if remaining < 2 * learned_cost else learned
    cost_in = tokens_in * input_rate / 1_000_000

    def refuse() -> BudgetExhausted:
        return BudgetExhausted(
            tight_period, limits[tight_period], spent_in, renews[tight_period], model=model
        )

    if remaining <= cost_in:
        raise refuse()
    cap = ticket.max_tokens
    if rate_out > 0:
        cap = min(cap, math.floor((remaining - cost_in) * 1_000_000 / rate_out))
    answers = store.stats(f"output:{family}")
    floor = 1
    if answers.count >= 3:
        floor = max(1, math.ceil(answers.mean - _Z_OUTPUT_P10 * answers.std))
    if cap < min(floor, ticket.max_tokens) or cap < 1:
        raise refuse()
    ticket.max_tokens = cap
    ticket.reserved = cost_in + cap * rate_out / 1_000_000
    with _INFLIGHT_LOCK:
        _INFLIGHT[owner] = _INFLIGHT.get(owner, 0.0) + ticket.reserved
    return ticket


def charge_fee(owner: str, usd: float, what: str, *, admin: bool = False) -> None:
    """Admit and record one fixed-price paid action (a WhatsApp template), or
    raise ``BudgetExhausted``: like a model call, it is paid for only when the
    owner's limits leave room for it."""
    cost = max(0.0, float(usd))
    limits = effective_limits(owner, admin=admin)
    day, month, renews = periods(owner)
    store = ledger()
    if store is None:
        if any(value is not None for value in limits.values()):
            period = "day" if limits["day"] is not None else "month"
            raise BudgetExhausted(
                period, limits[period], 0.0, renews[period], reason="unavailable", model=what
            )
        return
    with _INFLIGHT_LOCK:
        inflight = _INFLIGHT.get(owner, 0.0)
    for period, column in (("day", day), ("month", month)):
        limit = limits[period]
        if limit is None:
            continue
        spent = store.spent(owner, period, column)
        if spent + inflight + cost > limit:
            raise BudgetExhausted(period, limit, spent, renews[period], model=what)
    store.record(owner, day, month, what, (0, 0), cost, "fee")


# ── reports ──────────────────────────────────────────────────────────────


def _left(limit: float | None, spent: float) -> float | None:
    return None if limit is None else round(max(0.0, limit - spent), 6)


def summary(owner: str, *, admin: bool, days: int = 30) -> dict[str, Any]:
    store = ledger()
    if store is None:
        raise RuntimeError("The spending ledger is unavailable")
    day, month, renews = periods(owner)
    limits = effective_limits(owner, admin=admin)
    saved = store.limits(owner)
    spent = {"day": store.spent(owner, "day", day), "month": store.spent(owner, "month", month)}
    return {
        "day": day,
        "month": month,
        "spent_usd": {key: round(value, 6) for key, value in spent.items()},
        "limits_usd": limits,
        "own_limits_usd": saved.get("self", {"day": None, "month": None}),
        "remaining_usd": {key: _left(limits[key], spent[key]) for key in limits},
        "renews_at": renews,
        "history": store.history(owner, days),
        "by_model": store.by_model(owner, month),
        "unpriced": os.getenv("MIZAN_BUDGET_UNPRICED", "refuse").strip().lower(),
        "checked_at": time.time(),
    }
