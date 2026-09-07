"""An executable synthetic AgentOps application with explicit trust boundaries.

The planner is symbolic, not an LLM. SQLite target state is a synthetic service,
not a container, operating-system service, or customer environment. Approval is
by a trusted local operator; this module does not authenticate remote humans.
"""

import hashlib
import heapq
import json
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.security.izn import IznPermission, PermissionLevel

FACTS = ("worker", "route", "cache")
ACTIONS = {"restart_worker": "worker", "repair_route": "route", "refresh_cache": "cache"}
UPDATE_SQL = {
    "restart_worker": "UPDATE targets SET worker=1 WHERE id=?",
    "repair_route": "UPDATE targets SET route=1 WHERE id=?",
    "refresh_cache": "UPDATE targets SET cache=1 WHERE id=?",
}
COSTS = {"restart_worker": 3, "repair_route": 2, "refresh_cache": 1}
VARIANTS = ("ungated", "approval_only", "approval_policy", "full")


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Evidence:
    id: str
    key: str
    value: bool
    observed_at: float
    source: str = "sandbox_probe"


@dataclass(frozen=True)
class Action:
    tool: str
    target: str


def symbolic_plan(evidence, target):
    """Uniform-cost search over eight Boolean states, using observations only.

    No scenario ID, fault-injection setting, or evaluator label is an input.
    Untrusted free text is deliberately not part of this planner's language.
    """
    state = {}
    for item in evidence:
        if item.key in state and state[item.key] != item.value:
            return None
        state[item.key] = item.value
    if set(state) != set(FACTS) or any(type(v) is not bool for v in state.values()):
        return None
    start = tuple(state[k] for k in FACTS)
    queue = [(0, start, ())]
    best = {start: 0}
    while queue:
        cost, current, path = heapq.heappop(queue)
        if all(current):
            return [Action(tool, target) for tool in path]
        for tool, key in ACTIONS.items():
            index = FACTS.index(key)
            if current[index]:
                continue
            following = list(current)
            following[index] = True
            following = tuple(following)
            new_cost = cost + COSTS[tool]
            if new_cost < best.get(following, float("inf")):
                best[following] = new_cost
                heapq.heappush(queue, (new_cost, following, path + (tool,)))
    return None


class Policy:
    """Use Mizan's tool classification plus application-specific invariants."""

    def __init__(self, target="staging-demo", max_age=60, version="agentops-v1"):
        self.target = target
        self.max_age = max_age
        self.version = version
        self.izn = IznPermission()
        for tool in ACTIONS:
            self.izn.grant_tool("agentops", tool, PermissionLevel.APPROVAL_REQUIRED)
        self.izn.grant_tool("agentops", "disable_monitor", PermissionLevel.DENIED)

    @property
    def fingerprint(self):
        policy = self.izn.get_policy("agentops")
        return digest(
            {
                "target": self.target,
                "max_age": self.max_age,
                "version": self.version,
                "permissions": {k: v.level.value for k, v in policy.tool_permissions.items()},
            }
        )

    def check(self, actions, evidence, now):
        if not actions or len(actions) > 3:
            return False, "empty_or_oversized_plan"
        seen = {}
        ids = set()
        for item in evidence:
            if item.id in ids or item.source != "sandbox_probe" or item.key not in FACTS:
                return False, "invalid_evidence_provenance"
            ids.add(item.id)
            if type(item.value) is not bool or not 0 <= now - item.observed_at <= self.max_age:
                return False, "invalid_or_stale_evidence"
            if item.key in seen:
                return False, "duplicate_or_conflicting_fact"
            seen[item.key] = item.value
        if set(seen) != set(FACTS):
            return False, "missing_evidence"
        used = set()
        for action in actions:
            if action.target != self.target or action.tool not in ACTIONS or action.tool in used:
                return False, "action_outside_scope"
            used.add(action.tool)
            permission = self.izn.check_permission(
                "agentops", "agentops", action.tool, {"target": action.target}
            )
            if not permission["allowed"] and not permission["requires_approval"]:
                return False, "tool_policy_denied"
            if seen[ACTIONS[action.tool]]:
                return False, "unnecessary_mutation"
        return True, "permitted_pending_bound_approval"


class Store:
    """Durable local request lifecycle; permission to use the file is authority.

    The operator and agent share a trusted local account. This is not remote
    identity assurance, multi-tenant authorization, or an immutable ledger.
    """

    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS targets (
              id TEXT PRIMARY KEY, worker INTEGER, route INTEGER, cache INTEGER,
              monitor INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS requests (
              id TEXT PRIMARY KEY, payload TEXT NOT NULL, binding TEXT NOT NULL,
              state TEXT NOT NULL, expires REAL NOT NULL, approver TEXT,
              outcome TEXT);
            CREATE TABLE IF NOT EXISTS audit (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
              previous TEXT NOT NULL, hash TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def event(self, kind, value):
        row = self.db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        payload = canonical({"kind": kind, "value": value})
        hashed = hashlib.sha256((previous + payload).encode()).hexdigest()
        self.db.execute(
            "INSERT INTO audit(payload,previous,hash) VALUES(?,?,?)", (payload, previous, hashed)
        )

    def audit_valid(self):
        previous = "0" * 64
        for row in self.db.execute("SELECT * FROM audit ORDER BY seq"):
            if row["previous"] != previous:
                return False
            hashed = hashlib.sha256((previous + row["payload"]).encode()).hexdigest()
            if hashed != row["hash"]:
                return False
            previous = hashed
        return True

    def initialize(self, state, target="staging-demo"):
        with self.db:
            self.db.execute(
                "INSERT INTO targets(id,worker,route,cache,monitor) VALUES(?,?,?,?,?)",
                (target, int(state[0]), int(state[1]), int(state[2]), 1),
            )
            self.event("initialized", {"target": target, "state": state})

    def state(self, target="staging-demo"):
        row = self.db.execute("SELECT * FROM targets WHERE id=?", (target,)).fetchone()
        if row is None:
            raise ValueError("Unknown sandbox target")
        return {k: bool(row[k]) for k in (*FACTS, "monitor")}

    def observe(self, now, target="staging-demo"):
        state = self.state(target)
        return [Evidence(f"{target}:{key}", key, state[key], now) for key in FACTS]

    def propose(self, actions, evidence, policy, now, ttl=300):
        identifier = uuid.uuid4().hex
        payload = {
            "actions": [asdict(x) for x in actions],
            "evidence": [asdict(x) for x in evidence],
            "policy": policy.fingerprint,
            "environment": "synthetic-local",
        }
        with self.db:
            self.db.execute(
                "INSERT INTO requests(id,payload,binding,state,expires) VALUES(?,?,?,?,?)",
                (identifier, canonical(payload), digest(payload), "pending", now + ttl),
            )
            self.event("proposed", {"request": identifier, "payload": payload})
        return identifier

    def request(self, identifier):
        row = self.db.execute("SELECT * FROM requests WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Unknown request")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def decide(self, identifier, approve, actor, now):
        if not actor.strip():
            raise ValueError("Local operator label is required")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.request(identifier)
            if row["state"] != "pending" or row["expires"] <= now:
                return False
            state = "approved" if approve else "rejected"
            self.db.execute(
                "UPDATE requests SET state=?,approver=? WHERE id=?", (state, actor, identifier)
            )
            self.event(state, {"request": identifier, "local_operator_label": actor})
            return True


def observe_recovery(store, target, available=True):
    """Separate synthetic health probe; ignores planner and tool return values."""
    if not available:
        return None
    row = store.db.execute(
        "SELECT worker,route,cache,monitor FROM targets WHERE id=?", (target,)
    ).fetchone()
    return row is not None and tuple(row) == (1, 1, 1, 1)


def execute(store, identifier, policy, now=None, variant="full", fault="none", verifier=True):
    """Execute only synthetic state transitions in a single SQLite transaction.

    Fault injection and ablated variants are research-only. Every variant remains
    confined to the local synthetic target table; none calls shell/cloud tools.
    """
    now = time.time() if now is None else now
    if variant not in VARIANTS:
        raise ValueError("Unknown variant")
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        row = store.request(identifier)
        if row["state"] in ("completed", "failed", "blocked"):
            return {"status": "already_final", "executed": False, "recovered": None}
        payload = row["payload"]
        actions = [Action(**x) for x in payload["actions"]]
        evidence = [Evidence(**x) for x in payload["evidence"]]
        reason = None
        if row["binding"] != digest(payload):
            reason = "binding_mismatch"
        elif variant != "ungated" and (row["state"] != "approved" or row["expires"] <= now):
            reason = "approval_missing_rejected_or_expired"
        elif variant in ("approval_policy", "full"):
            if payload["policy"] != policy.fingerprint:
                reason = "policy_changed"
            else:
                allowed, message = policy.check(actions, evidence, now)
                if not allowed:
                    reason = message
                elif any(store.state(policy.target)[item.key] != item.value for item in evidence):
                    reason = "target_changed_since_observation"
        if reason:
            result = {"status": "blocked", "reason": reason, "executed": False, "recovered": None}
            store.db.execute(
                "UPDATE requests SET state='blocked',outcome=? WHERE id=?",
                (canonical(result), identifier),
            )
            store.event("blocked", {"request": identifier, "result": result})
            return result
        before = {a.target: store.state(a.target) for a in actions}
        calls = 0
        tool_ok = True
        for index, action in enumerate(actions):
            calls += 1
            if fault == "timeout":
                tool_ok = False
                break
            if fault == "no_effect":
                continue
            if action.tool == "disable_monitor":
                store.db.execute("UPDATE targets SET monitor=0 WHERE id=?", (action.target,))
            elif action.tool in ACTIONS:
                store.db.execute(UPDATE_SQL[action.tool], (action.target,))
            else:
                tool_ok = False
                break
            if fault == "partial_failure" and index == 0:
                tool_ok = False
                break
        observed = observe_recovery(store, policy.target, verifier) if variant == "full" else None
        recovered = observed if variant == "full" else tool_ok
        rollback = False
        if variant == "full" and recovered is not True:
            for target, state in before.items():
                store.db.execute(
                    "UPDATE targets SET worker=?,route=?,cache=?,monitor=? WHERE id=?",
                    (*(int(state[k]) for k in (*FACTS, "monitor")), target),
                )
            rollback = all(store.state(target) == state for target, state in before.items())
        result = {
            "status": "completed" if recovered is True else "failed",
            "executed": calls > 0,
            "calls": calls,
            "tool_ok": tool_ok,
            "recovered": recovered,
            "verified": variant == "full",
            "rollback": rollback,
        }
        store.db.execute(
            "UPDATE requests SET state=?,outcome=? WHERE id=?",
            (result["status"], canonical(result), identifier),
        )
        store.event("execution", {"request": identifier, "result": result})
        return result
