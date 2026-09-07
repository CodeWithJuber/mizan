# Mizan-AgentOps: synthetic assurance reference application

This research addition implements a persistent local incident-control workflow:
observe, plan, inspect, approve/reject, execute, verify, and preserve an audit trail.
It supports an IAAI-27 Emerging Applications investigation. **It is not a submitted
paper, production deployment, or live LLM benchmark.**

The planner performs uniform-cost symbolic search over three Boolean observations
(worker, route, cache). Remediation operates on a local SQLite synthetic service.
The verifier separately reads realized target state rather than trusting a tool's
success response. This is an intentionally small, completely inspectable model.

## Existing research reused

- **Mizan**: imports `IznPermission` and `PermissionLevel` from the existing
  permission module for tool policy classification. Its old `approve_pending`
  method deletes a request without creating an executable approval grant. The
  new application replaces that lifecycle with durable, plan-bound requests;
  it does **not** claim that the main Mizan chat/API approval flow is repaired.
- **Hikmah Stack**: informs separation of proposals from trusted controls, explicit
  unknown outcomes, and hash-linked history. Its Rust runtime is not integrated
  or benchmarked in this artifact.
- **Forgekit**: informs evidence-producing verification, reproducible evaluation,
  and conservative claims. Its MCP and model runtimes are not integrated or
  benchmarked here.

No unrelated mathematical theorem, new cognitive capability, novel planning
algorithm, human oversight benefit, or general prompt-injection defense is claimed.

## Run the local application

From the Mizan repository root, with Python 3.11 or newer:

```bash
python3 -m pip install -e '.[dev]'
python3 -m research.iaai27_agentops --db /tmp/agentops-demo.sqlite init
python3 -m research.iaai27_agentops --db /tmp/agentops-demo.sqlite propose
```

Inspect the returned plan, evidence, environment, and policy binding. Copy its
request ID into these commands. Each command is a separate process; approval
survives process restart.

```bash
python3 -m research.iaai27_agentops --db /tmp/agentops-demo.sqlite request REQUEST_ID
python3 -m research.iaai27_agentops --db /tmp/agentops-demo.sqlite approve REQUEST_ID
python3 -m research.iaai27_agentops --db /tmp/agentops-demo.sqlite execute REQUEST_ID
python3 -m research.iaai27_agentops --db /tmp/agentops-demo.sqlite inspect
```

Use `reject REQUEST_ID` instead of `approve` to veto. Evidence expires after 60
seconds; a delayed execution needs a fresh proposal and approval. Reusing the
same finalized request does not execute it twice. `init` requires a fresh database;
it deliberately does not reset existing history.

## Trust and isolation boundaries

- CLI-only, trusted local operator; no web interface or network listener.
- Local file access is the authority boundary. The operator label is descriptive,
  not a remote identity assertion. Do not expose these calls to an untrusted LLM,
  user, or network without an authenticated separation of operator and executor.
- All action variants, including ungated research baselines, mutate only the
  synthetic `targets` table. No arbitrary shell command or cloud API exists.
- Approval is bound to stored action/evidence/environment/policy payloads, expires,
  and is finalized transactionally. Current policy and target state are rechecked.
- An entire synthetic execution and its audit update use one SQLite transaction.
  This atomicity does not transfer to external cloud actions. A real adapter
  requires durable outbox/idempotency, uncertain-outcome reconciliation, and
  separately authorized compensation.
- Audit chaining detects some changes under a trusted database boundary. It does
  not prevent an administrator from replacing or recomputing the whole history,
  detect all truncation without an external anchor, encrypt records, or implement
  regulatory immutability.
- Rollback restores simulated state and may restore the original fault. It does
  not necessarily restore service availability.

## Verification and reproduction

```bash
python3 -m pytest research/iaai27_agentops/test_agentops.py -q
python3 -m ruff check research/iaai27_agentops
python3 -m research.iaai27_agentops.evaluate --out /tmp/agentops-evaluation
```

The recorded run has 24 designed scenarios x 4 configurations = 96 episodes.
Results, complete per-episode audit traces, fixture definitions, source hashes,
dependency versions and repeatability findings are in `results/`.

| Configuration | Prohibited executions / 15 cases | False completions / 24 episodes | Clean resolutions / 4 | Failed remediations detected / 3 |
|---|---:|---:|---:|---:|
| Ungated sandbox baseline | 14 | 3 | 4 | 2 |
| Approval only | 11 | 3 | 4 | 2 |
| Approval + policy | 0 | 1 | 4 | 2 |
| Full + independent outcome observation | 0 | 0 | 4 | 3 |

All variants share a restricted synthetic executor, request-payload integrity and
finalization behavior. Ablations isolate approval, policy and outcome observation;
“ungated” does not mean unconstrained operating-system access. Approval decisions
are simulated. A second run matched 96/96 semantic outcomes, excluding timings
and audit UUID/hash differences. This is deterministic replay, not 96 independent
statistical samples. These are finite-suite counts with no population confidence
interval, significance test, or production failure-rate interpretation.

Some scenarios force malformed/prohibited proposals directly into the control
boundary. They measure downstream enforcement, not a model's tendency to produce
those proposals. The planner does not ingest natural-language logs. Consequently
there is no measured natural-language prompt-injection resistance, no Arabic vs.
English comparison, no live LLM call, and no general incident-resolution result.

The initial test run passed 23 application tests. The existing repository suite
passed 557 tests with 8 skips. `make check` passes lint but stops on the existing
mypy duplicate-module error for `_version` / `backend._version`; this research-only
addition does not modify the existing backend. See `results/validation.md`.

## Research limitations and deployment

See [the proposed pilot](DEPLOYMENT.md) and [the claim ledger](CLAIMS.md). Future
external adapters, live models, operator trials and held-out incident evaluation
remain separate work. The current simulator is not a miniature production cloud
and must not be advertised as one.

New reference code and evaluation assembly were generated with AI assistance in
this task. Existing repository authorship and licenses remain intact. Manuscript
authorship must be disclosed independently; a style-matched draft does not become
human-written text merely because it is reviewed or approved.
