"""The Imtihan report: pass rates with Wilson intervals, pass^k, calibration and cost."""

from __future__ import annotations

import math
from typing import Any

ARMS = ("base", "mizan")
# Categories and weights after the Artificial Analysis Intelligence Index v4
# (Agents 30%, Coding 20%, Scientific Reasoning 20%, General 30%).
CATEGORIES = {
    "agents": (0.30, ("agent_tools", "agent_web", "agent_recovery", "agent_guardrail",
                      "honesty", "injection")),
    "coding": (0.20, ("agent_coding", "code")),
    "reasoning": (0.20, ("arc", "exactness", "consistency")),
    "general": (0.30, ("knowledge", "abstention", "scripture", "multilingual", "learning",
                       "safety")),
}  # fmt: skip


def weighted(blocks: dict) -> dict:
    """Each category's mean block pass rate, and their weighted mean (weights renormalised
    over the categories that ran)."""
    categories: dict[str, dict] = {}
    for name, (weight, members) in CATEGORIES.items():
        present = [blocks[b] for b in members if b in blocks]
        if not present:
            continue
        entry: dict[str, Any] = {"weight": weight, "blocks": [b for b in members if b in blocks]}
        for arm in ARMS:
            rates = [b[arm]["rate"] for b in present if b[arm]["rate"] is not None]
            entry[arm] = round(sum(rates) / len(rates), 3) if rates else None
        categories[name] = entry
    index: dict[str, Any] = {"categories": categories}
    for arm in ARMS:
        scored = [(c["weight"], c[arm]) for c in categories.values() if c[arm] is not None]
        total = sum(w for w, _ in scored)
        index[arm] = round(sum(w * v for w, v in scored) / total, 3) if total else None
    return index


def wilson(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    rate = passed / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return (round(max(0.0, centre - margin), 3), round(min(1.0, centre + margin), 3))


def ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float | None:
    """Expected calibration error: stated confidence against how often it was right."""
    if not pairs:
        return None
    total = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        group = [(c, ok) for c, ok in pairs if low <= c < high or (index == bins - 1 and c == 1.0)]
        if group:
            accuracy = sum(ok for _c, ok in group) / len(group)
            stated = sum(c for c, _ok in group) / len(group)
            total += len(group) / len(pairs) * abs(accuracy - stated)
    return round(total, 3)


def brier(pairs: list[tuple[float, bool]]) -> float | None:
    if not pairs:
        return None
    return round(sum((c - float(ok)) ** 2 for c, ok in pairs) / len(pairs), 3)


def summarize(results: list[dict], tasks: list[dict]) -> dict[str, Any]:
    """``results`` holds one row per task, attempt and arm."""
    blocks: dict[str, dict] = {}
    order = list(dict.fromkeys(task["block"] for task in tasks))
    for block in order:
        block_tasks = [task["id"] for task in tasks if task["block"] == block]
        entry: dict[str, Any] = {"tasks": len(block_tasks)}
        for arm in ARMS:
            rows = [r for r in results if r["block"] == block and r["arm"] == arm]
            scored = [r for r in rows if not r.get("error")]
            passed = sum(1 for r in scored if r["pass"])
            by_task: dict[str, list[bool]] = {}
            for r in scored:
                by_task.setdefault(r["task_id"], []).append(r["pass"])
            first = [r for r in scored if r["attempt"] == 1]
            entry[arm] = {
                "scored": len(scored),
                "errors": len(rows) - len(scored),
                "passed": passed,
                "rate": round(passed / len(scored), 3) if scored else None,
                "interval": wilson(passed, len(scored)),
                "pass_at_1": round(sum(r["pass"] for r in first) / len(first), 3)
                if first
                else None,
                # pass^k: the task passed on every attempt.
                "pass_all": round(sum(all(v) for v in by_task.values()) / len(by_task), 3)
                if by_task
                else None,
            }
        rates = [entry[arm]["rate"] for arm in ARMS]
        entry["delta"] = (
            round(rates[1] - rates[0], 3) if None not in rates else None  # type: ignore[operator]
        )
        blocks[block] = entry

    index: dict[str, Any] = {}
    for arm in ARMS:
        rates = [entry[arm]["rate"] for entry in blocks.values() if entry[arm]["rate"] is not None]
        scored = [r for r in results if r["arm"] == arm and not r.get("error")]
        passed = sum(1 for r in scored if r["pass"])
        index[arm] = {
            "score": round(sum(rates) / len(rates), 3) if rates else None,
            "pooled": round(passed / len(scored), 3) if scored else None,
            "interval": wilson(passed, len(scored)),
        }

    calibration = {}
    for arm in ARMS:
        pairs = [
            (r["confidence"], r["pass"])
            for r in results
            if r["arm"] == arm and r.get("confidence") is not None and not r.get("error")
        ]
        stated = [r for r in results if r["arm"] == arm and r["block"] == "knowledge"]
        calibration[arm] = {
            "ece": ece(pairs),
            "brier": brier(pairs),
            "answers_with_confidence": len(pairs),
            "answers": len(stated),
        }

    consistency = {}
    groups = sorted({task["group"] for task in tasks if task.get("group")})
    for arm in ARMS:
        held = 0
        for group in groups:
            members = {task["id"] for task in tasks if task.get("group") == group}
            rows = [
                r
                for r in results
                if r["arm"] == arm and r["task_id"] in members and r["attempt"] == 1
            ]
            held += bool(rows) and all(r["pass"] for r in rows) and len(rows) == len(members)
        consistency[arm] = {
            "groups": len(groups),
            "consistent": held,
            "rate": round(held / len(groups), 3) if groups else None,
        }

    cost = {}
    for arm in ARMS:
        rows = [r for r in results if r["arm"] == arm]
        priced = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
        cost[arm] = {
            "input_tokens": sum(r.get("input_tokens") or 0 for r in rows),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in rows),
            "cost_usd": round(sum(priced), 6) if priced else None,
            "latency_ms": round(sum(r.get("latency_ms") or 0 for r in rows), 1),
            "model_calls": sum(r.get("model_calls") or 0 for r in rows),
            "tool_calls": sum(r.get("tool_calls") or 0 for r in rows),
        }
    isnad = {}
    for arm in ARMS:
        rows = [r for r in results if r["arm"] == arm and r.get("supported") is not None]
        isnad[arm] = {
            # Share of each answer's claims MIZAN's evidence supports (Isnad).
            "supported": round(sum(r["supported"] for r in rows) / len(rows), 3) if rows else None,
            "fabricated_claims": sum(r.get("fabricated") or 0 for r in results if r["arm"] == arm),
        }
    from . import agentic

    return {
        "blocks": blocks,
        "index": index,
        "weighted": weighted(blocks),
        "agentic": agentic.summarize(results),
        "isnad": isnad,
        "calibration": calibration,
        "consistency": consistency,
        "cost": cost,
    }


def markdown(report: dict, title: str = "MIZAN Imtihan") -> str:
    lines = [f"# {title}", ""]
    index = report["index"]
    lines.append(
        f"**Score** (mean of block pass rates): base {_pct(index['base']['score'])}, "
        f"MIZAN {_pct(index['mizan']['score'])}"
    )
    lines += ["", "| Block | Tasks | Base | MIZAN | Δ |", "|---|---|---|---|---|"]
    for block, entry in report["blocks"].items():
        lines.append(
            f"| {block} | {entry['tasks']} | {_pct(entry['base']['rate'])} | "
            f"{_pct(entry['mizan']['rate'])} | {_signed(entry['delta'])} |"
        )
    calibration = report["calibration"]
    lines += [
        "",
        f"Calibration (knowledge, ECE; lower is better): base {calibration['base']['ece']}, "
        f"MIZAN {calibration['mizan']['ece']}",
        f"Paraphrase consistency: base {_pct(report['consistency']['base']['rate'])}, "
        f"MIZAN {_pct(report['consistency']['mizan']['rate'])}",
    ]
    cost = report["cost"]
    lines.append(
        f"Model calls: base {cost['base']['model_calls']}, MIZAN {cost['mizan']['model_calls']}; "
        f"tool calls by MIZAN {cost['mizan']['tool_calls']}"
    )
    return "\n".join(lines) + "\n"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{round(value * 100)}%"


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{'+' if value >= 0 else ''}{round(value * 100)} pts"
