"""Tadqiq (تدقيق, close checking): a blinded audit of the answers MIZAN gives without the teacher.

MIZAN answers more and more requests with no language-model call: a kept
program re-run (Hifz), an answer the teacher taught once (Talaqqi), its own
recipes. ``usage.lisan.zero_call`` marks them. Nothing checked those answers
against an independent opinion, so a slow decline in their quality would go
unseen while the teacher-call share kept falling. Tadqiq checks a random sample.

- **What is sampled.** Each zero-call answer of a run that is not an evaluation
  (stateless) and whose person has learning on, with probability
  ``MIZAN_AUDIT_RATE`` (default 0.03, held to [0.02, 0.05] unless an
  administrator saves another value). The draw is a uniform random number from
  the operating system; the probability is kept with each result, so every
  audit stands for 1/p answers (Horvitz-Thompson). A question about the deen is
  never audited: the teacher's word is no check on scripture.
- **Blinded.** After the answer is delivered, in the background, the teacher
  (the run's own provider and model, through Lisan) is asked the same request
  alone. It never sees MIZAN's answer.
- **Compared.** A program's printed output, or an answer that is a number
  rather than a sentence, is compared by its numbers (``tathabbut.agree``, the
  request's own numbers set aside). Words are compared by the NLI model of Ahl
  al-Dhikr in both directions, each pair first passing ``ahl_dhikr.about``. The
  outcome is agree, disagree or unsettled.
- **Monitored.** Per Fahm family, an e-CUSUM over the settled outcomes raises an
  alarm when the disagreement rate rises above the family's own baseline. Its
  parameters follow from the owner's target (a 10-point rise found within about
  two weeks at 200 requests a day); see ``design`` and docs/tadqiq.md.
- **Paid like any call.** The teacher's call goes through Iqtisad under the
  Lisan task ``audit``, charged to the person whose answer it checks; a spent
  budget refuses it before it is sent.

Each result is kept with no content: family, language, kind, outcome, time,
sampling probability and estimated cost (``$MIZAN_DATA_DIR/tadqiq.db``).
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import math
import os
import random
import re
import sqlite3
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.adaptive import tokenize, wilson_bounds

from . import tathabbut

logger = logging.getLogger("mizan.tadqiq")

# The owner's decision (30 Oct 2026, docs/consent.md): audit 2 to 5 % of answers.
DEFAULT_RATE = 0.03
MIN_RATE, MAX_RATE = 0.02, 0.05
# The owner's target: a 10-point drop in agreement found within about two
# weeks at 200 requests a day.
SHIFT = 0.10
DESIGN_REQUESTS_PER_DAY = 200
DESIGN_DAYS = 14
# An alarm never rests on less evidence than Tajdid needs to replace an
# instruction: an e-value of at least 1/α.
ALPHA = 0.05
OUTCOMES = ("agree", "disagree", "unsettled", "refused", "unavailable")

# An unbiased draw from the operating system's generator; tests may replace it.
_DRAW: random.Random = random.SystemRandom()
# Audits in flight, held so the event loop does not drop them unfinished.
_TASKS: set[asyncio.Task] = set()


def enabled() -> bool:
    """``MIZAN_TADQIQ``: ``on`` (default) or ``off``."""
    return os.getenv("MIZAN_TADQIQ", "on").strip().lower() not in {"off", "0", "false", "no"}


def _set_by_admin() -> bool:
    try:
        import runtime_settings

        return bool(runtime_settings.saved("MIZAN_AUDIT_RATE"))
    except Exception:  # noqa: BLE001 - without the registry the server's bounds hold
        return False


def rate() -> float:
    """The sampling probability: the server's value held to the approved
    [0.02, 0.05], or any value in [0, 1] an administrator saved."""
    text = os.getenv("MIZAN_AUDIT_RATE", "").strip()
    try:
        value = float(text) if text else DEFAULT_RATE
    except ValueError:
        value = DEFAULT_RATE
    if not math.isfinite(value):
        value = DEFAULT_RATE
    if _set_by_admin():
        return min(1.0, max(0.0, value))
    return min(MAX_RATE, max(MIN_RATE, value))


def window(probability: float | None = None) -> int:
    """Audits in the target window: the rate times 200 requests a day for 14 days."""
    share = rate() if probability is None else probability
    return max(1, round(share * DESIGN_REQUESTS_PER_DAY * DESIGN_DAYS))


# ── which answers are audited ────────────────────────────────────────────


def decide(task: Any, result: dict, *, nested: bool = False) -> float | None:
    """The sampling probability if this answer is drawn for an audit, else None."""
    if not enabled() or nested or not isinstance(task, str) or not task.strip():
        return None
    answer = result.get("result")
    if not result.get("success", True) or not isinstance(answer, str) or not answer.strip():
        return None
    lisan = (result.get("usage") or {}).get("lisan") or {}
    if lisan.get("zero_call") is not True:
        return None
    from memory import stateless

    if stateless.active() or not stateless.learns():
        return None  # an evaluation, or a person who turned learning off
    if (result.get("amanah") or {}).get("ignored"):
        return None  # pasted instructions aimed at the AI: no independent opinion
    probability = rate()
    if probability <= 0.0 or _DRAW.random() >= probability:
        return None
    return probability


def schedule(task: Any, result: dict, provider: Any, model: Any, *, nested: bool = False) -> None:
    """Draw this answer for an audit and, if drawn, audit it in the background.
    Called as a run finishes; never raises and never waits."""
    try:
        if provider is None or getattr(provider, "provider_name", "") == "mizan-owned":
            return
        probability = decide(task, result, nested=nested)
        if probability is None:
            return
        lisan = result["usage"]["lisan"]
        job = asyncio.get_running_loop().create_task(
            audit(
                task,
                str(result["result"]),
                provider,
                model,
                family=str(lisan.get("family") or "unplaced"),
                language=str(lisan.get("language") or "unknown"),
                probability=probability,
            )
        )
        _TASKS.add(job)
        job.add_done_callback(_TASKS.discard)
    except Exception:  # noqa: BLE001 - an audit must never touch the answer
        logger.warning("Tadqiq: could not schedule an audit", exc_info=True)


async def drain() -> None:
    """Wait for the audits in flight (shutdown, tests)."""
    while _TASKS:
        await asyncio.gather(*list(_TASKS), return_exceptions=True)


# ── asking the teacher ───────────────────────────────────────────────────


class _Teacher:
    """What Lisan needs of an agent for one audit: the run's provider and model,
    and a record of the call kept out of the run's own usage."""

    def __init__(self, provider: Any, model: Any):
        self.ai_client = provider
        self.ai_model = model
        self.calls: list[dict] = []

    def _record_llm_call(self, response: Any, latency_ms: float) -> None:
        self.calls.append({"response": response, "latency_ms": round(latency_ms, 1)})

    def _add_execution_time(self, key: str, started: float) -> float:
        return 0.0


def _today() -> str:
    from . import waqt

    now, zone = waqt.now()
    return f"{now:%A %d %B %Y}" + (f" ({zone})" if zone else " (UTC)")


async def audit(
    task: str,
    answer: str,
    provider: Any,
    model: Any,
    *,
    family: str,
    language: str,
    probability: float,
) -> str | None:
    """Ask the teacher the request alone, compare, keep the outcome. Returns the
    outcome, or None when the request was not audited (a question about the deen)."""
    await asyncio.sleep(0)  # the answer goes out first
    from api.iqtisad import BudgetExhausted
    from api.usage import build_usage_block

    from . import ahl_dhikr
    from .lisan import Lisan, LisanUnavailable

    if await asyncio.to_thread(ahl_dhikr.religious, task, answer):
        return None
    teacher = _Teacher(provider, model)
    kind, outcome = "none", "unavailable"
    try:
        said = await Lisan(teacher).audit(task, _today())
    except LisanUnavailable as exc:
        if isinstance(exc.__cause__, BudgetExhausted):
            outcome = "refused"
    except Exception:  # noqa: BLE001 - a failed audit is recorded, never raised
        logger.warning("Tadqiq: the teacher could not be asked", exc_info=True)
    else:
        kind, outcome = await compare(task, answer, said)
    costs = [build_usage_block(call).get("cost_usd") for call in teacher.calls]
    cost = sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None
    try:
        await asyncio.to_thread(
            record, family, language, kind, outcome, probability, cost, len(teacher.calls)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Tadqiq: could not keep an audit result", exc_info=True)
    return outcome


# ── comparing two answers ────────────────────────────────────────────────

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
# MIZAN's own notes under an answer ("_Computed by MIZAN_") are lines in italics.
_NOTE = re.compile(r"^\s*_[^_\n].*_\s*$", re.MULTILINE)


def _outputs(text: str) -> list[str]:
    """What programs printed, shown in plain-text fences."""
    return [body for info, body in _FENCE.findall(text) if info.strip().lower() == "text"]


def _prose(text: str) -> str:
    """The words of an answer: code and MIZAN's notes set aside, printed output kept."""
    kept = _FENCE.sub(
        lambda match: match.group(2) if match.group(1).strip().lower() in {"", "text"} else " ",
        text or "",
    )
    return _NOTE.sub(" ", kept)


def _beyond(found: list[str], request: str) -> list[str]:
    """The numbers an answer gives that the request did not already hold."""
    left = Counter(tathabbut.numbers(request))
    kept = []
    for number in found:
        if left[number] > 0:
            left[number] -= 1
            continue
        kept.append(number)
    return kept


def _words(sentence: str) -> int:
    return sum(1 for token in tokenize(sentence) if not token.isdigit())


def _claims(text: str) -> list[str]:
    """Sentences that can carry a claim: at least three words besides numbers
    (the unit Ahl al-Dhikr holds a claim to)."""
    from . import ahl_dhikr

    found = ahl_dhikr.sentences([ahl_dhikr.Passage(text, "", "", "answer")])
    return [passage.text for passage in found if _words(passage.text) >= 3]


def _numbers_outcome(mine: list[str], theirs: list[str]) -> str:
    if not theirs:
        return "unsettled"
    printed, said = " ".join(mine), " ".join(theirs)
    # Either derivation may print more (a working, a restated operand): they agree
    # when one's numbers appear, in order, among the other's.
    agreed = tathabbut.agree(said, printed) or tathabbut.agree(printed, said)
    return "agree" if agreed else "disagree"


async def compare(request: str, answer: str, teacher: str) -> tuple[str, str]:
    """(kind, outcome): how MIZAN's answer and the teacher's compare.

    ``numbers``: MIZAN's answer printed a program's output, or gives numbers and
    no sentence; the numbers beyond the request's are compared in order. ``text``:
    each answer's sentences are read against the other's by the NLI model, both
    ways, each pair first passing ``ahl_dhikr.about``. A contradiction either way
    is a disagreement; otherwise a supported claim is agreement; otherwise
    nothing was settled."""
    from . import ahl_dhikr

    theirs_text = _prose(teacher)
    outputs = _outputs(answer)
    printed = _beyond(tathabbut.numbers("\n".join(outputs)), request) if outputs else []
    if printed:
        return "numbers", _numbers_outcome(
            printed, _beyond(tathabbut.numbers(theirs_text), request)
        )
    prose = _prose(answer)
    mine = _claims(prose)
    if not mine:
        given = _beyond(tathabbut.numbers(prose), request)
        if given:
            return "numbers", _numbers_outcome(
                given, _beyond(tathabbut.numbers(theirs_text), request)
            )
        return "text", "unsettled"
    theirs = _claims(theirs_text)
    if not theirs:
        return "text", "unsettled"

    def pool(claims: list[str], source: str) -> list[Any]:
        return [ahl_dhikr.Passage(claim, source, "", source) for claim in claims]

    forward = await ahl_dhikr.judge(mine, pool(theirs, "teacher"))
    backward = await ahl_dhikr.judge(theirs, pool(mine, "mizan"))
    verdicts = {finding.verdict for finding in forward + backward}
    if "contradicted" in verdicts:
        return "text", "disagree"
    if "supported" in verdicts:
        return "text", "agree"
    return "text", "unsettled"


# ── the disagreement monitor (an e-CUSUM per family) ─────────────────────


def _kl(p: float, q: float) -> float:
    """Kullback-Leibler divergence of Bernoulli(p) from Bernoulli(q), in nats."""
    return p * math.log(p / q) + (1 - p) * math.log((1 - p) / (1 - q))


def _siegmund(information: float) -> float:
    """H with H - 1 + e^-H = information (Newton's method from above: the
    function is convex and increasing for H > 0)."""
    if information <= 0:
        return 0.0
    level = information + 1.0
    for _ in range(60):
        step = (level - 1.0 + math.exp(-level) - information) / (1.0 - math.exp(-level))
        level -= step
        if abs(step) < 1e-12:
            break
    return level


def design(baseline: float, audits: int) -> tuple[float, float, float, float]:
    """(p1, up, down, h) of the monitor for a family whose disagreement rate is
    ``baseline``, so that a rise of ``SHIFT`` is found within ``audits`` audits
    on average.

    Each settled audit adds its log-likelihood ratio: ``up`` = ln(p1/p0) for a
    disagreement, ``down`` = ln((1-p1)/(1-p0)) for an agreement. After the rise
    every audit adds I = KL(p1 || p0) on average, and Siegmund's approximation
    puts the CUSUM's expected delay from its floor at (H - 1 + e^-H)/I, where H
    is the threshold plus the expected overshoot (half a disagreement's step).
    Setting the delay to ``audits`` gives H; h = H - up/2, and never below
    ln(1/α)."""
    p0 = min(max(baseline, 1e-6), 1 - 1e-6)
    p1 = p0 + SHIFT if p0 + SHIFT < (1 + p0) / 2 else (1 + p0) / 2
    up = math.log(p1 / p0)
    down = math.log((1 - p1) / (1 - p0))
    level = _siegmund(audits * _kl(p1, p0))
    return p1, up, down, max(level - up / 2, math.log(1 / ALPHA))


def fresh() -> dict:
    return {
        "recent": [],  # the last ``window`` settled outcomes (1 = disagree), the guard
        "baseline_n": 0,  # settled audits older than the guard: the baseline
        "baseline_d": 0,
        "log_e": None,  # the e-CUSUM's log statistic; None until the baseline is learned
        "alarm": False,
        "alarms": 0,
        "alarmed_at": None,
    }


def baseline(state: dict) -> float:
    """The family's disagreement rate over its audits older than the guard
    (Jeffreys' estimate)."""
    return (float(state["baseline_d"]) + 0.5) / (float(state["baseline_n"]) + 1.0)


def observe(state: dict, disagreed: bool, audits: int) -> bool:
    """Add one settled outcome to a family's monitor; True when it raises an alarm.

    The statistic is the e-CUSUM log M_n = max(log M_{n-1}, 0) + ℓ_n against the
    baseline. If the true rate is at most the baseline, every e^ℓ has mean at
    most 1, so the expected number of audits before a false alarm is at least
    e^h (Lorden 1971; the e-detectors of Shin, Ramdas and Rinaldo). The baseline
    is learned from audits older than the last ``audits`` (the guard): a rise is
    found within about that many audits, before it can enter its own baseline.
    Monitoring starts once the baseline holds ``audits`` audits."""
    raised = False
    if state["log_e"] is not None:
        _p1, up, down, threshold = design(baseline(state), audits)
        state["log_e"] = max(state["log_e"], 0.0) + (up if disagreed else down)
        above = state["log_e"] >= threshold
        raised = above and not state["alarm"]
        state["alarm"] = above
        if raised:
            state["alarms"] = int(state["alarms"]) + 1
            state["alarmed_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    state["recent"].append(1 if disagreed else 0)
    while len(state["recent"]) > audits:
        state["baseline_d"] += state["recent"].pop(0)
        state["baseline_n"] += 1
    if state["log_e"] is None and state["baseline_n"] >= audits:
        state["log_e"] = 0.0
    return raised


def monitor_view(state: dict, audits: int) -> dict:
    view: dict[str, Any] = {
        "status": "learning the baseline",
        "baseline_audits": int(state["baseline_n"]),
        "needed": audits,
        "guard": len(state["recent"]),
        "alarms": int(state["alarms"]),
        "alarmed_at": state["alarmed_at"],
        "alarm": False,
    }
    if state["log_e"] is None:
        return view
    p0 = baseline(state)
    p1, _up, _down, threshold = design(p0, audits)
    view.update(
        status="watching",
        baseline=round(p0, 4),
        alternative=round(p1, 4),
        statistic=round(math.exp(min(state["log_e"], 700.0)), 4),
        threshold=round(math.exp(threshold), 2),
        alarm=state["log_e"] >= threshold,
        expected_delay_audits=audits,
    )
    return view


# ── storage ──────────────────────────────────────────────────────────────


class Store:
    """Audit results (no content) and each family's monitor, in one SQLite file."""

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                    family TEXT NOT NULL, language TEXT NOT NULL, kind TEXT NOT NULL,
                    outcome TEXT NOT NULL, probability REAL NOT NULL, cost_usd REAL,
                    calls INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS audits_at ON audits(at);
                CREATE TABLE IF NOT EXISTS monitors (
                    family TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT NOT NULL);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def add(self, row: tuple) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audits (at, family, language, kind, outcome, probability, "
                "cost_usd, calls) VALUES (?,?,?,?,?,?,?,?)",
                row,
            )

    def monitor(self, family: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT state FROM monitors WHERE family=?", (family,)).fetchone()
        return {**fresh(), **json.loads(row[0])} if row else fresh()

    def save_monitor(self, family: str, state: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO monitors VALUES (?,?,?) ON CONFLICT(family) DO UPDATE "
                "SET state=excluded.state, updated=excluded.updated",
                (family, json.dumps(state), datetime.now(UTC).isoformat()),
            )

    def monitors(self) -> dict[str, dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT family, state FROM monitors").fetchall()
        return {family: {**fresh(), **json.loads(state)} for family, state in rows}

    def rows(self, since: str) -> list[tuple]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT family, language, kind, outcome, probability, cost_usd FROM audits "
                "WHERE at >= ? ORDER BY at",
                (since,),
            ).fetchall()


_STORES: dict[str, Store] = {}
_STORES_LOCK = threading.Lock()


def store() -> Store:
    path = str(Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "tadqiq.db")
    with _STORES_LOCK:
        if path not in _STORES:
            _STORES[path] = Store(path)
        return _STORES[path]


def record(
    family: str,
    language: str,
    kind: str,
    outcome: str,
    probability: float,
    cost: float | None = None,
    calls: int = 0,
) -> bool:
    """Keep one audit result and, when it settled, feed the family's monitor.
    Returns True when this result raised an alarm."""
    target = store()
    at = datetime.now(UTC).isoformat(timespec="seconds")
    raised = False
    with target.lock:
        target.add((at, family, language, kind, outcome, float(probability), cost, int(calls)))
        if outcome not in ("agree", "disagree"):
            return False
        state = target.monitor(family)
        audits = window()
        raised = observe(state, outcome == "disagree", audits)
        target.save_monitor(family, state)
    if raised:
        _alarm(family, monitor_view(state, audits))
    return raised


def _alarm(family: str, view: dict) -> None:
    detail = (
        f"Audit alarm: MIZAN's own answers in '{family}' now disagree with the teacher more "
        f"often than their baseline of {view.get('baseline', 0):.0%} "
        f"(evidence {view.get('statistic', 0):.0f} ≥ {view.get('threshold', 0):.0f})"
    )
    logger.warning("[TADQIQ] %s", detail)
    from . import sijill

    # A fresh context: the note belongs to no person's chat, so erasing a chat
    # never erases it.
    contextvars.Context().run(
        sijill.note,
        "tadqiq",
        {"detail": detail, "family": family, "alarm": True},
        sijill.ADMINS,
    )


# ── the report ───────────────────────────────────────────────────────────


def report(days: int = 90) -> dict:
    """Per family: audits, outcomes, the disagreement rate with its Wilson 95 %
    interval, spend, and the monitor. Counts only; no content."""
    target = store()
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = target.rows(since)
    monitors = target.monitors()
    audits = window()

    def cell() -> dict:
        return {
            "audited": 0,
            **{outcome: 0 for outcome in OUTCOMES},
            "answers_represented": 0.0,
            "spend_usd": 0.0,
            "unpriced": 0,
            "languages": {},
        }

    families: dict[str, dict] = {}
    total = cell()
    for family, language, _kind, outcome, probability, cost in rows:
        for bucket in (families.setdefault(family, cell()), total):
            bucket["audited"] += 1
            bucket[outcome] = bucket.get(outcome, 0) + 1
            bucket["answers_represented"] += 1.0 / probability if probability > 0 else 0.0
            if cost is None:
                bucket["unpriced"] += outcome not in ("refused", "unavailable")
            else:
                bucket["spend_usd"] += float(cost)
            bucket["languages"][language] = bucket["languages"].get(language, 0) + 1

    def finish(bucket: dict) -> dict:
        settled = bucket["agree"] + bucket["disagree"]
        low, high = wilson_bounds(bucket["disagree"], settled)
        return {
            **bucket,
            "settled": settled,
            "disagreements": bucket["disagree"],
            "disagreement_rate": round(bucket["disagree"] / settled, 4) if settled else None,
            "interval": [round(low, 4), round(high, 4)] if settled else None,
            "answers_represented": round(bucket["answers_represented"], 1),
            "spend_usd": round(bucket["spend_usd"], 6),
        }

    names = sorted(
        set(families) | set(monitors),
        key=lambda name: (-families.get(name, cell())["audited"], name),
    )
    return {
        "enabled": enabled(),
        "rate": rate(),
        "rate_set_by_admin": _set_by_admin(),
        "approved_rate": [MIN_RATE, MAX_RATE],
        "days": days,
        "design": {
            "shift": SHIFT,
            "requests_per_day": DESIGN_REQUESTS_PER_DAY,
            "days": DESIGN_DAYS,
            "window_audits": audits,
            "alpha": ALPHA,
        },
        "total": finish(total),
        "families": [
            {
                "family": name,
                **finish(families.get(name, cell())),
                "monitor": monitor_view(monitors.get(name, fresh()), audits),
            }
            for name in names
        ],
    }
