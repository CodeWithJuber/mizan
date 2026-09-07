"""Meaningful lifecycle and failure tests against the actual local controller."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from .core import Action, Evidence, Policy, Store, execute, symbolic_plan

NOW = 1_000_000.0


@pytest.fixture
def app(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    store.initialize((False, True, True))
    policy = Policy()
    yield store, policy
    store.close()


def request(app, evidence=None, actions=None):
    store, policy = app
    evidence = store.observe(NOW) if evidence is None else evidence
    actions = symbolic_plan(evidence, policy.target) if actions is None else actions
    return store.propose(actions, evidence, policy, NOW)


def test_approval_resume_survives_restart(app):
    store, policy = app
    identifier = request(app)
    assert store.decide(identifier, True, "test-operator", NOW)
    reopened = Store(store.path)
    try:
        result = execute(reopened, identifier, policy, NOW)
        assert result["recovered"] is True
        assert reopened.state()["worker"] is True
        assert reopened.audit_valid()
    finally:
        reopened.close()


@pytest.mark.parametrize("approval", ["missing", "rejected", "expired"])
def test_no_execution_without_valid_approval(app, approval):
    store, policy = app
    identifier = request(app)
    if approval != "missing":
        store.decide(identifier, approval == "expired", "test-operator", NOW)
    result = execute(store, identifier, policy, NOW + (301 if approval == "expired" else 0))
    assert result["executed"] is False
    assert store.state()["worker"] is False


def test_replay_is_not_second_execution(app):
    store, policy = app
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)
    assert execute(store, identifier, policy, NOW)["executed"]
    assert execute(store, identifier, policy, NOW)["status"] == "already_final"


def test_two_workers_only_one_executes(app):
    store, policy = app
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)

    def run(_):
        local = Store(store.path)
        try:
            return execute(local, identifier, Policy(), NOW)
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(result["executed"] for result in results) == 1


def test_parameter_substitution_invalidates_binding(app):
    store, policy = app
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)
    value = store.request(identifier)["payload"]
    value["actions"][0]["target"] = "other"
    with store.db:
        store.db.execute(
            "UPDATE requests SET payload=? WHERE id=?", (json.dumps(value), identifier)
        )
    assert execute(store, identifier, policy, NOW)["reason"] == "binding_mismatch"


def test_policy_change_requires_fresh_approval(app):
    store, policy = app
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)
    assert execute(store, identifier, Policy(version="changed"), NOW)["reason"] == "policy_changed"


@pytest.mark.parametrize(
    "mode", ["stale", "missing", "conflict", "untrusted", "future", "duplicate"]
)
def test_invalid_evidence_blocks_a_preexisting_proposal(app, mode):
    store, policy = app
    evidence = store.observe(NOW)
    if mode == "stale":
        evidence[0] = replace(evidence[0], observed_at=NOW - 61)
    elif mode == "missing":
        evidence.pop()
    elif mode == "conflict":
        evidence.append(Evidence("contradiction", "worker", True, NOW))
    elif mode == "untrusted":
        evidence[0] = replace(evidence[0], source="untrusted_log")
    elif mode == "future":
        evidence[0] = replace(evidence[0], observed_at=NOW + 1)
    else:
        evidence.append(evidence[0])
    identifier = request(app, evidence=evidence, actions=[Action("restart_worker", policy.target)])
    store.decide(identifier, True, "operator", NOW)
    assert execute(store, identifier, policy, NOW)["executed"] is False


def test_state_drift_is_rechecked(app):
    store, policy = app
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)
    with store.db:
        store.db.execute("UPDATE targets SET worker=1")
    assert execute(store, identifier, policy, NOW)["reason"] == "target_changed_since_observation"


@pytest.mark.parametrize("fault", ["no_effect", "timeout", "partial_failure"])
def test_failed_remediation_is_detected_and_rolled_back(app, fault):
    store, policy = app
    with store.db:
        store.db.execute("UPDATE targets SET route=0")
    original = store.state()
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)
    result = execute(store, identifier, policy, NOW, fault=fault)
    assert result["recovered"] is False
    assert result["rollback"]
    assert store.state() == original


def test_missing_verifier_reports_unknown(app):
    store, policy = app
    identifier = request(app)
    store.decide(identifier, True, "operator", NOW)
    result = execute(store, identifier, policy, NOW, verifier=False)
    assert result["recovered"] is None
    assert result["rollback"]


def test_symbolic_planner_handles_compound_faults_and_healthy_state(app):
    store, policy = app
    evidence = [Evidence(k, k, False, NOW) for k in ("worker", "route", "cache")]
    plan = symbolic_plan(evidence, policy.target)
    assert len(plan) == 3
    assert plan[0].tool == "refresh_cache"
    assert symbolic_plan([replace(e, value=True) for e in evidence], policy.target) == []
    assert symbolic_plan(evidence[:-1], policy.target) is None


def test_audit_detects_changed_history(app):
    store, _ = app
    assert store.audit_valid()
    with store.db:
        store.db.execute("UPDATE audit SET payload='changed' WHERE seq=1")
    assert not store.audit_valid()


def test_policy_denies_unnecessary_mutation_and_outside_target(app):
    store, policy = app
    evidence = store.observe(NOW)
    assert not policy.check([Action("restart_worker", "another")], evidence, NOW)[0]
    assert not policy.check([Action("repair_route", policy.target)], evidence, NOW)[0]
    assert not policy.check([Action("disable_monitor", policy.target)], evidence, NOW)[0]


def test_existing_izn_resume_defect_remains_a_separate_baseline():
    from backend.security.izn import IznPermission

    izn = IznPermission()
    assert izn.check_permission("test", "katib", "install_package", {"name": "demo"})[
        "requires_approval"
    ]
    assert izn.approve_pending("test:install_package")
    assert izn.check_permission("test", "katib", "install_package", {"name": "demo"})[
        "requires_approval"
    ]
