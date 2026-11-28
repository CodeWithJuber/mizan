"""Sullam (سلّم): does sharing the work among agents earn its place? Report only.

He et al. 2026 (arXiv 2611.32606) found that a multi-agent system's gains often
vanish once a single agent is given the same token budget: a plain vote of
independent single answers does as well. MIZAN keeps the check ForgeKit's
ladder keeps: per kind of work (Fahm's intent), the multi-agent answer shape
(Majlis: the parts of a request given to the agents that fit, side by side)
stays the default only while it beats a plain vote of
single answers **at the same token budget**.

- **Evidence** is a pair of outcomes on the same request: the multi-agent
  answer and a single-answer arm, each verified or not by rule. The AGI test
  (``imtihan/runner.py``) already sends every task to the base model alone
  and to MIZAN; when MIZAN's answer used more than one agent, the pair is
  recorded, counting the lone answer as a vote of one and only when it spent
  no more tokens than the multi-agent shape (a vote of k answers within the
  same budget does at least as well as one). A pair where both arms agree
  carries no evidence.
- **Decision**: ``core.adaptive.paired_e_value`` over the pairs where they
  disagree, safe to read after every pair. The default changes only when the
  e-value that the challenger is better reaches 1/α (α = 0.05: 20). Until
  then, today's behaviour stands: no change without evidence.
- **The forward shape**: workers get disjoint evidence slices, dealt by role
  with the most-constrained role first (ForgeKit's evidence_team.js), and the
  lead aggregates one deduplicated facts packet (``deal``, ``facts_packet``).
  It is a challenger arm like the vote.

The ladder level per intent is reported in ``GET /api/tadbir/learning``
(Agents → Majlis → Learning). It never blocks or changes a run by itself.
Counts only, no request text: the pairs come from evaluation runs, so they
are kept in one shared ``ladder.db``.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from pathlib import Path

SHAPES = ("majlis", "vote", "forward")
CHALLENGERS = ("vote", "forward")
ALPHA = 0.05
_LOCK = threading.Lock()


def _path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "ladder.db"


def _connect() -> sqlite3.Connection | None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pairs (intent TEXT NOT NULL, challenger TEXT NOT NULL, "
            "multi_ok INTEGER NOT NULL, other_ok INTEGER NOT NULL, multi_tokens INTEGER, "
            "other_tokens INTEGER, at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        return conn
    except (OSError, sqlite3.Error):
        return None


def record_pair(
    intent: str,
    challenger: str,
    *,
    multi_ok: bool,
    other_ok: bool,
    multi_tokens: int | None,
    other_tokens: int | None,
) -> bool:
    """One equal-budget pair; False when it is not one (the challenger spent more)."""
    if challenger not in CHALLENGERS or not intent:
        return False
    if multi_tokens is not None and other_tokens is not None and other_tokens > multi_tokens:
        return False  # not at the same budget: the challenger had more
    conn = _connect()
    if conn is None:
        return False
    try:
        with _LOCK, conn:
            conn.execute(
                "INSERT INTO pairs (intent, challenger, multi_ok, other_ok, multi_tokens, "
                "other_tokens) VALUES (?, ?, ?, ?, ?, ?)",
                (intent, challenger, int(multi_ok), int(other_ok), multi_tokens, other_tokens),
            )
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return True


def _counts() -> dict[tuple[str, str], dict[str, int]]:
    conn = _connect()
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            "SELECT intent, challenger, SUM(other_ok > multi_ok), SUM(multi_ok > other_ok), "
            "COUNT(*) FROM pairs GROUP BY intent, challenger"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return {
        (intent, challenger): {"wins": int(wins or 0), "losses": int(losses or 0), "pairs": n}
        for intent, challenger, wins, losses, n in rows
    }


def level(intent: str, counts: dict | None = None) -> dict:
    """The default shape for this intent and the evidence for each challenger."""
    from core.adaptive import paired_e_value

    counts = _counts() if counts is None else counts
    evidence = {}
    default = "majlis"
    best = 0.0
    for challenger in CHALLENGERS:
        found = counts.get((intent, challenger), {"wins": 0, "losses": 0, "pairs": 0})
        better = paired_e_value(found["wins"], found["losses"])
        worse = paired_e_value(found["losses"], found["wins"])
        evidence[challenger] = {
            **found,
            "challenger_better": round(better, 3),
            "majlis_better": round(worse, 3),
        }
        if better >= 1 / ALPHA and better > best:
            default, best = challenger, better
    settled = default != "majlis" or any(
        item["majlis_better"] >= 1 / ALPHA for item in evidence.values()
    )
    return {
        "intent": intent,
        "default": default,
        "level": default if settled else "majlis (not enough evidence)",
        "threshold": round(1 / ALPHA, 1),
        "evidence": evidence,
        "report_only": True,
    }


def report(intents: list[str]) -> list[dict]:
    counts = _counts()
    seen = sorted({*intents, *(intent for intent, _c in counts)})
    return [level(intent, counts) for intent in seen]


def multi_agent(orchestration: dict | None) -> bool:
    """MIZAN's answer used the multi-agent shape: Majlis gave its parts to more
    than one agent."""
    if not isinstance(orchestration, dict):
        return False
    agents = orchestration.get("agents") or []
    return len({str(item.get("agent")) for item in agents if isinstance(item, dict)}) > 1


def observe_compare(compared: dict, rows: list[dict]) -> bool:
    """An AGI-test task's two arms as an equal-budget pair, when MIZAN's arm
    was multi-agent (``imtihan/runner.run_task``)."""
    mizan = compared.get("mizan") or {}
    orchestration = mizan.get("orchestration") or {}
    if not multi_agent(orchestration):
        return False
    by_arm = {row.get("arm"): row for row in rows}
    ours, alone = by_arm.get("mizan"), by_arm.get("base")
    if not ours or not alone:
        return False

    def tokens(row: dict) -> int | None:
        parts = [row.get("input_tokens"), row.get("output_tokens")]
        return sum(int(p) for p in parts if isinstance(p, int)) if any(parts) else None

    return record_pair(
        str(orchestration.get("intent") or "compound"),
        "vote",
        multi_ok=bool(ours.get("pass")),
        other_ok=bool(alone.get("pass")),
        multi_tokens=tokens(ours),
        other_tokens=tokens(alone),
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
