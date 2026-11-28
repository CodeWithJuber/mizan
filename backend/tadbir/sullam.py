"""Sullam (سلّم): does sharing the work among agents earn its place? Report only.

He et al. 2026 (arXiv 2611.32606, §4.1) found that a multi-agent system's gains
often vanish once single agents are given the same token budget: a plain vote
of independent single answers does as well. MIZAN grades Majlis the way
ForgeKit's ``ladder.js`` grades a team, per kind of work (Fahm's intent),
against INDEPENDENT single answers given the same budget, at three rising bars:

- level 1  Y > V(1)     beats one agent
- level 2  Y > V(n_B)   beats a compute-matched majority vote
- level 3  Y > T(n_B)   beats compute-matched pass@n (solved if ANY is right)

n_B = the team's completion tokens / c₁, and c₁ = the mean completion tokens of
one independent single answer. A level counts only when a one-sided paired
t-test at α = 0.025, clustered by question (one difference per question),
confirms it AND every level below it.

- **Evidence.** The AGI test (``imtihan/runner.py``) sends every task to the
  base model alone and to MIZAN, ``repeats`` times. Each base answer is an
  independent single answer to that question (the pool); each MIZAN answer
  that used more than one agent is a team run (the group). V(n) and T(n) are
  exact, from the pool's m answers of which k were right (hypergeometric:
  ``majority_at_n``, ``pass_at_n``), interpolated at a non-integer n_B, so no
  extra model call is made. A question with fewer than ⌈n_B⌉ pool answers
  cannot judge levels 2 and 3 (capping n would understate the baseline): run
  the AGI test with more repeats. A row without a token count is not priced
  and is left out.
- **The verdict.** Majlis stays the reported default for an intent only while
  it clears level 2 (it beats the vote at the same budget); otherwise the
  report says the vote does as well, or that there is not enough evidence. It
  is reported in ``GET /api/tadbir/learning`` (Agents → Majlis → Learning) and
  never blocks or changes a run by itself.
- **The forward shape.** Workers get disjoint evidence slices, dealt by role
  with the most-constrained role first (ForgeKit's ``evidence_team.js``), and
  the lead aggregates one deduplicated facts packet (``deal``,
  ``facts_packet``). These are the building blocks; Majlis does not run the
  shape yet, so the ladder does not grade it.

Counts only, no request text: the runs come from evaluation runs, so they are
kept in one shared ``ladder.db``.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

LADDER_ALPHA = 0.025
ARMS = ("group", "pool")
_LOCK = threading.Lock()


def _path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "ladder.db"


def _connect() -> sqlite3.Connection | None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ladder_runs (arm TEXT NOT NULL, question TEXT NOT NULL, "
            "intent TEXT NOT NULL DEFAULT '', correct INTEGER NOT NULL, tokens INTEGER NOT NULL, "
            "at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        return conn
    except (OSError, sqlite3.Error):
        return None


def record_run(
    arm: str, question: str, *, correct: bool, tokens: int | None, intent: str = ""
) -> bool:
    """One team run (``group``, with its intent) or one independent single answer
    (``pool``); False when it cannot be priced or kept."""
    if arm not in ARMS or not question or not isinstance(tokens, int) or tokens < 0:
        return False
    if arm == "group" and not intent:
        return False
    conn = _connect()
    if conn is None:
        return False
    try:
        with _LOCK, conn:
            conn.execute(
                "INSERT INTO ladder_runs (arm, question, intent, correct, tokens) "
                "VALUES (?, ?, ?, ?, ?)",
                (arm, question[:200], intent if arm == "group" else "", int(correct), tokens),
            )
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return True


def _rows() -> list[tuple[str, str, str, int, int]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        return conn.execute(
            "SELECT arm, question, intent, correct, tokens FROM ladder_runs"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


# ── the references, exact (ForgeKit ladder.js) ───────────────────────────


def _log_choose(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def pass_at_n(m: int, k: int, n: int) -> float:
    """P(at least one of n distinct draws from m answers, k of them right, is right)."""
    if n <= 0 or k <= 0:
        return 0.0
    q = 1.0
    for j in range(n):
        if m - k - j <= 0:
            return 1.0
        q *= (m - k - j) / (m - j)
    return 1.0 - q


def majority_at_n(m: int, k: int, n: int) -> float:
    """A majority vote of n distinct draws from m answers, k right, when only
    right/wrong is known: P(more than half right) + ½·P(exactly half)."""
    if n <= 0:
        return 0.0
    total = _log_choose(m, n)
    p = 0.0
    for x in range(max(0, n - (m - k)), min(k, n) + 1):
        w = math.exp(_log_choose(k, x) + _log_choose(m - k, n - x) - total)
        if 2 * x > n:
            p += w
        elif 2 * x == n:
            p += w / 2
    return min(1.0, p)


def _at(f: Callable[[int], float], n: float) -> float:
    """f at a non-integer n: linear between ⌊n⌋ and ⌈n⌉, never below n = 1."""
    x = max(1.0, n)
    lo, hi = math.floor(x), math.ceil(x)
    return f(lo) if lo == hi else f(lo) + (x - lo) * (f(hi) - f(lo))


def paired_one_sided(d: list[float]) -> dict:
    """One-sided paired t-test of mean(d) > 0, one difference per question."""
    from core.adaptive import regularized_beta

    n = len(d)
    if n < 2:
        return {"n": n, "mean": d[0] if n else 0.0, "se": None, "t": None, "p": None}
    mean = sum(d) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
    se = sd / math.sqrt(n)
    if se <= 1e-12 * max(1.0, abs(mean)):  # no spread: the sign of the mean decides
        return {"n": n, "mean": mean, "se": 0.0, "t": None, "p": 0.0 if mean > 0 else 1.0}
    t = mean / se
    df = n - 1
    tail = 0.5 * regularized_beta(df / (df + t * t), df / 2, 0.5)  # P(T > |t|)
    return {"n": n, "mean": mean, "se": se, "t": t, "p": tail if t > 0 else 1 - tail}


def _round(x: float | None, k: int = 4) -> float | None:
    return round(x, k) if isinstance(x, float | int) and math.isfinite(x) else None


def grade(group: list[dict], pool: list[dict], alpha: float = LADDER_ALPHA) -> dict:
    """Grade a team on the equal-budget ladder. ``group``: {id, correct, tokens}
    per team run; ``pool``: the same per INDEPENDENT single answer."""
    warnings: list[str] = []
    if not group or not pool:
        return {"questions": 0, "level": 0, "measured": False, "warnings": warnings}
    c1 = sum(r["tokens"] for r in pool) / len(pool)
    if c1 <= 0:
        warnings.append("the single answers report no tokens: the unit cost c₁ is undefined")
        return {"questions": 0, "level": 0, "measured": False, "warnings": warnings}
    pool_by: dict[str, list[dict]] = {}
    for r in pool:
        pool_by.setdefault(r["id"], []).append(r)
    group_by: dict[str, list[dict]] = {}
    for r in group:
        group_by.setdefault(r["id"], []).append(r)
    ids = sorted(q for q in group_by if q in pool_by)
    if len(ids) < len(group_by):
        warnings.append(f"{len(group_by) - len(ids)} question(s) have no single answers")
    if not ids:
        return {"questions": 0, "level": 0, "measured": False, "warnings": warnings}
    kept = [r for q in ids for r in group_by[q]]
    n_b = sum(r["tokens"] for r in kept) / len(kept) / c1
    if n_b < 1:
        warnings.append(f"the team spent less than one agent (n_B = {n_b:.2f}); n = 1 is used")
    need = math.ceil(max(1.0, n_b))
    per = []
    for q in ids:
        members = pool_by[q]
        m, k = len(members), sum(1 for r in members if r["correct"])
        y = sum(1 for r in group_by[q] if r["correct"]) / len(group_by[q])

        def vote(n: int, m: int = m, k: int = k) -> float:
            return majority_at_n(m, k, n) if n <= m else math.nan

        def any_right(n: int, m: int = m, k: int = k) -> float:
            return pass_at_n(m, k, n)

        fits = m >= need
        per.append(
            {
                "y": y,
                "v1": vote(1),
                "vn": _at(vote, n_b) if fits else math.nan,
                "tn": _at(any_right, n_b) if fits else math.nan,
                "fits": fits,
            }
        )
    short = sum(1 for q in per if not q["fits"])
    if short:
        warnings.append(
            f"{short} question(s) have fewer than {need} single answers, so levels 2 and 3 "
            "cannot be judged: run the AGI test with more repeats"
        )

    def judge(ref: str, indeterminate: bool) -> dict:
        if indeterminate:
            return {"reference": None, "cleared": False, "indeterminate": True}
        test = paired_one_sided([q["y"] - q[ref] for q in per])
        return {
            "reference": _round(sum(q[ref] for q in per) / len(per)),
            "mean_diff": _round(test["mean"]),
            "p": _round(test["p"], 5),
            "cleared": test["p"] is not None and test["p"] < alpha,
            "indeterminate": test["p"] is None,
        }

    tests = {1: judge("v1", False), 2: judge("vn", short > 0), 3: judge("tn", short > 0)}
    level = 0
    for step in (1, 2, 3):
        if not tests[step]["cleared"]:
            break
        level = step
    return {
        "questions": len(ids),
        "measured": True,
        "alpha": alpha,
        "c1": _round(c1, 1),
        "n_b": _round(n_b, 3),
        "y": _round(sum(q["y"] for q in per) / len(per)),
        "level": level,
        "vote": "majority-of-correct",
        "tests": {str(step): test for step, test in tests.items()},
        "warnings": warnings,
    }


def level(intent: str, rows: list[tuple[str, str, str, int, int]] | None = None) -> dict:
    """The ladder for one intent and the shape the evidence keeps as default."""
    rows = _rows() if rows is None else rows
    group = [
        {"id": q, "correct": bool(ok), "tokens": t}
        for arm, q, i, ok, t in rows
        if arm == "group" and i == intent
    ]
    asked = {r["id"] for r in group}
    pool = [
        {"id": q, "correct": bool(ok), "tokens": t}
        for arm, q, _i, ok, t in rows
        if arm == "pool" and q in asked
    ]
    graded = grade(group, pool)
    vote_test = (graded.get("tests") or {}).get("2") or {}
    if graded["level"] >= 2:
        default, verdict = "majlis", "Majlis beats a vote of single answers at the same budget"
    elif graded.get("measured") and not vote_test.get("indeterminate", True):
        default, verdict = "vote", "a vote of single answers at the same budget does as well"
    else:
        default, verdict = "majlis", "not enough evidence yet"
    return {"intent": intent, "default": default, "verdict": verdict, **graded, "report_only": True}


def report(intents: list[str]) -> list[dict]:
    rows = _rows()
    seen = sorted({*intents, *(i for arm, _q, i, _ok, _t in rows if arm == "group")})
    return [level(intent, rows) for intent in seen]


def multi_agent(orchestration: dict | None) -> bool:
    """MIZAN's answer used the multi-agent shape: Majlis gave its parts to more
    than one agent."""
    if not isinstance(orchestration, dict):
        return False
    agents = orchestration.get("agents") or []
    return len({str(item.get("agent")) for item in agents if isinstance(item, dict)}) > 1


def observe_compare(compared: dict, rows: list[dict]) -> bool:
    """An AGI-test task's arms: the base answer joins the pool of independent
    single answers to that question, and MIZAN's answer is a team run when it
    was multi-agent (``imtihan/runner.run_task``). True when a team run was kept."""
    by_arm = {row.get("arm"): row for row in rows}
    ours, alone = by_arm.get("mizan"), by_arm.get("base")
    if not ours or not alone:
        return False
    question = str(alone.get("task_id") or "")
    record_run("pool", question, correct=bool(alone.get("pass")), tokens=alone.get("output_tokens"))
    orchestration = (compared.get("mizan") or {}).get("orchestration") or {}
    if not multi_agent(orchestration):
        return False
    return record_run(
        "group",
        question,
        correct=bool(ours.get("pass")),
        tokens=ours.get("output_tokens"),
        intent=str(orchestration.get("intent") or "compound"),
    )


# ── the forward shape ────────────────────────────────────────────────────

# What evidence each role can work from (by the evidence's kind).
ROLE_KINDS = {
    "katib": {"code", "file", "run"},
    "mundhir": {"web", "source", "search"},
    "mubashir": {"page", "web"},
    "khalifah": {"quran", "hadith", "date", "memory", "code", "file", "web", "source", "page"},
}


def deal(evidence: list[dict], roles: list[str]) -> dict[str, list[dict]]:
    """Disjoint evidence slices: the most-constrained role (fewest items it can
    use) chooses first, taking its share of what is still unclaimed; each item
    goes to exactly one worker. Items no role can use stay with the lead."""
    slices: dict[str, list[dict]] = {role: [] for role in roles}
    slices["lead"] = []
    unclaimed = list(range(len(evidence)))

    def usable(role: str) -> list[int]:
        kinds = ROLE_KINDS.get(role, set())
        return [i for i in unclaimed if str(evidence[i].get("kind")) in kinds]

    order = sorted(roles, key=lambda role: (len(usable(role)), roles.index(role)))
    for position, role in enumerate(order):
        mine = usable(role)
        if not mine:
            continue
        left = len(order) - position
        # Its share: what it alone can use, plus an even share of the rest.
        only = [i for i in mine if all(i not in usable(o) for o in order[position + 1 :])]
        shared = [i for i in mine if i not in only]
        take = only + shared[: max(0, -(-len(shared) // left))]
        for i in take:
            slices[role].append(evidence[i])
            unclaimed.remove(i)
    slices["lead"] = [evidence[i] for i in unclaimed]
    return slices


def facts_packet(reports: list[dict]) -> list[dict]:
    """The lead's one packet: each fact once (by its normalised words), with every
    worker that reported it."""
    packet: dict[str, dict] = {}
    for report in reports:
        worker = str(report.get("role") or "")
        for fact in report.get("facts") or []:
            text = " ".join(str(fact.get("text") if isinstance(fact, dict) else fact).split())
            if not text:
                continue
            key = hashlib.sha256(text.casefold().encode()).hexdigest()[:16]
            entry = packet.setdefault(key, {"text": text, "by": [], "sources": []})
            if worker and worker not in entry["by"]:
                entry["by"].append(worker)
            source = fact.get("source") if isinstance(fact, dict) else None
            if source and source not in entry["sources"]:
                entry["sources"].append(source)
    return sorted(packet.values(), key=lambda item: (-len(item["by"]), item["text"]))
