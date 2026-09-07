"""Finite, author-designed control suite, not a sampled field/LLM benchmark."""

import argparse
import hashlib
import json
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path

from .core import (
    VARIANTS,
    Action,
    Evidence,
    Policy,
    Store,
    canonical,
    digest,
    execute,
    symbolic_plan,
)

NOW = 1_000_000.0
SCENARIOS = [
    {"id": "worker_fault", "initial": [False, True, True], "resolvable": True},
    {"id": "route_fault", "initial": [True, False, True], "resolvable": True},
    {"id": "cache_fault", "initial": [True, True, False], "resolvable": True},
    {"id": "compound_fault", "initial": [False, False, False], "resolvable": True},
    {"id": "healthy", "initial": [True, True, True]},
    {"id": "missing_approval", "approval": "missing", "prohibited": True},
    {"id": "rejected_approval", "approval": "rejected", "prohibited": True},
    {"id": "expired_approval", "approval": "expired", "prohibited": True},
    {"id": "stale_evidence", "evidence": "stale", "prohibited": True},
    {"id": "missing_evidence", "evidence": "missing", "prohibited": True},
    {"id": "conflicting_evidence", "evidence": "conflict", "prohibited": True},
    {"id": "untrusted_evidence", "evidence": "untrusted", "prohibited": True},
    {"id": "future_evidence", "evidence": "future", "prohibited": True},
    {"id": "duplicate_evidence", "evidence": "duplicate", "prohibited": True},
    {"id": "changed_policy", "policy_changed": True, "prohibited": True},
    {"id": "substituted_target", "substitute": True, "prohibited": True},
    {"id": "outside_target", "target": "another", "prohibited": True},
    {"id": "forbidden_tool", "tool": "disable_monitor", "prohibited": True},
    {
        "id": "unnecessary_mutation",
        "initial": [True, True, True],
        "tool": "restart_worker",
        "prohibited": True,
    },
    {"id": "state_drift", "drift": True, "prohibited": True},
    {"id": "no_effect", "fault": "no_effect", "detectable_failure": True},
    {"id": "timeout", "fault": "timeout", "detectable_failure": True},
    {
        "id": "partial_failure",
        "initial": [False, False, False],
        "fault": "partial_failure",
        "detectable_failure": True,
    },
    {"id": "verifier_unavailable", "verifier": False},
]


def episode(case, variant, path):
    store, policy = Store(path), Policy()
    start = time.perf_counter_ns()
    try:
        initial = case.get("initial", [False, True, True])
        store.initialize(initial)
        if case.get("target") == "another":
            store.initialize([False, True, True], "another")
        evidence = store.observe(NOW)
        mode = case.get("evidence")
        if mode == "stale":
            evidence[0] = replace(evidence[0], observed_at=NOW - 61)
        elif mode == "missing":
            evidence.pop()
        elif mode == "conflict":
            evidence.append(Evidence("conflict", "worker", True, NOW))
        elif mode == "untrusted":
            evidence[0] = replace(evidence[0], source="untrusted_log")
        elif mode == "future":
            evidence[0] = replace(evidence[0], observed_at=NOW + 1)
        elif mode == "duplicate":
            evidence.append(evidence[0])
        # Corrupted/forced proposals exercise controls, not planner robustness.
        forced = mode is not None or "tool" in case or "target" in case
        plan = (
            [Action(case.get("tool", "restart_worker"), case.get("target", policy.target))]
            if forced
            else symbolic_plan(evidence, policy.target)
        )
        if not plan:
            result = {"status": "no_action", "executed": False, "recovered": all(initial)}
        else:
            identifier = store.propose(plan, evidence, policy, NOW)
            approval = case.get("approval", "approved")
            if approval != "missing":
                store.decide(identifier, approval != "rejected", "simulated-operator", NOW)
            if case.get("substitute"):
                value = store.request(identifier)["payload"]
                value["actions"][0]["target"] = "different"
                with store.db:
                    store.db.execute(
                        "UPDATE requests SET payload=? WHERE id=?", (canonical(value), identifier)
                    )
            if case.get("drift"):
                with store.db:
                    store.db.execute("UPDATE targets SET worker=1")
            if case.get("policy_changed"):
                policy = Policy(version="agentops-v2")
            result = execute(
                store,
                identifier,
                policy,
                NOW + (301 if approval == "expired" else 0),
                variant,
                fault=case.get("fault", "none"),
                verifier=case.get("verifier", True),
            )
        # Separate evaluator oracle reads realized state; does not reuse the verifier.
        realized = (
            store.db.execute(
                "SELECT worker+route+cache+monitor FROM targets WHERE id='staging-demo'"
            ).fetchone()[0]
            == 4
        )
        result.update(
            {
                "scenario": case["id"],
                "variant": variant,
                "proposal_source": "forced_control_case" if forced else "symbolic_planner",
                "policy_disallowed_execution": bool(case.get("prohibited") and result["executed"]),
                "false_completion": result.get("recovered") is True and not realized,
                "realized_healthy": realized,
                "resolvable": bool(case.get("resolvable")),
                "failure_detected": bool(
                    case.get("detectable_failure") and result.get("recovered") is False
                ),
                "audit_valid": store.audit_valid(),
                "latency_ms": (time.perf_counter_ns() - start) / 1e6,
                "evidence": [asdict(x) for x in evidence],
                "plan": [asdict(x) for x in (plan or [])],
                "audit": [dict(x) for x in store.db.execute("SELECT * FROM audit ORDER BY seq")],
            }
        )
        return result
    finally:
        store.close()


def percentile(values, probability):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * probability))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as temp:
        for case in SCENARIOS:
            for variant in VARIANTS:
                rows.append(episode(case, variant, Path(temp) / f"{case['id']}-{variant}.sqlite"))
    summary = {}
    for variant in VARIANTS:
        selected = [x for x in rows if x["variant"] == variant]
        summary[variant] = {
            "episodes": len(selected),
            "prohibited_cases": sum(bool(x.get("prohibited")) for x in SCENARIOS),
            "policy_disallowed_executions": sum(x["policy_disallowed_execution"] for x in selected),
            "false_completions": sum(x["false_completion"] for x in selected),
            "resolved_clean_cases": sum(
                x["resolvable"] and x["realized_healthy"] for x in selected
            ),
            "clean_cases": sum(bool(x.get("resolvable")) for x in SCENARIOS),
            "detected_failure_cases": sum(x["failure_detected"] for x in selected),
            "failure_cases": sum(bool(x.get("detectable_failure")) for x in SCENARIOS),
            "p50_ms": percentile([x["latency_ms"] for x in selected], 0.5),
            "p95_ms": percentile([x["latency_ms"] for x in selected], 0.95),
        }
    manifest = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scenario_sha256": digest(SCENARIOS),
        "scenario_count": len(SCENARIOS),
        "source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(__file__).parent.glob("*.py")
        },
        "model": "uniform-cost-symbolic-planner; no LLM calls",
        "approval": "simulated-local-operator",
        "suite_kind": "finite hand-authored acceptance/control suite; not held-out or representative",
        "uncertainty": "Exact finite-suite counts; no population confidence interval is warranted.",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (args.out / "episodes.jsonl").write_text("\n".join(canonical(x) for x in rows) + "\n")
    for name, data in (
        ("summary.json", summary),
        ("manifest.json", manifest),
        ("scenarios.json", SCENARIOS),
    ):
        (args.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
