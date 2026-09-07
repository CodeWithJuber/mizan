# Proposed Hostlelo pilot

Status: **proposed**, confirmed as the intended deployment path by Juber Shaikh
in this conversation. No Hostlelo server was contacted or changed in this task.
No pilot has started, no customer/user outcome was measured, and no production
environment access is implied.

## Scope and owner

- Proposed owner/operator: Juber Shaikh.
- Intended setting: isolated Hostlelo staging environment with generated data.
- First users: the owner and subsequently an explicitly authorized staging
  operator. No claim that additional operators are recruited or committed.
- Initial artifact: this repository's local symbolic controller and SQLite
  simulator. Real infrastructure actions and model proposals require new adapters.
- Data: generated service states, diagnostic observations and audit events.
  Exclude customer, employer, airline, ticket, billing and production data.

## Entry requirements

Before calling the pilot “installed,” record the staging host's ownership and
authorization, capacity, OS/runtime versions, isolation controls, artifact commit,
operator access, and recovery procedure. A specific staging host and its resources
were not verified in this task. The initial installation needs Python 3.11+, the
Mizan dependencies and a writable private data directory; no GPU/model key is
required for the symbolic reference application.

Use a dedicated unprivileged OS account and private directory. Do not share its
database credentials or local account with an untrusted proposal engine. The
reference application has no remote identity boundary. Do not expose the CLI
through an unauthenticated web terminal or model tool.

## Proposed milestones (relative to confirmed staging access)

| Milestone | Target window | Deliverable | Acceptance gate |
|---|---|---|---|
| Reproduce local artifact | Day 0-1 | Exact commit, manifest, tests and raw results | Application tests pass; finite-suite results reproduced; known repository gate failure recorded |
| Install isolated staging simulator | Day 1-2 | Installation log and permissions evidence | No production credentials/data; only synthetic targets reachable; restart preserves pending/approved requests |
| Operator walkthrough | Day 2-4 | Recorded propose/reject/approve/replay/expiry cases | Operator can inspect exact scope, reject and observe outcome; approval UI/CLI misunderstandings logged |
| Read-only real-service adapter in staging | Day 4-7 | Separate probe adapter and seeded faults on disposable test services | Independent probe agreement, fault restoration and explicit environment scoping; no state-changing tools |
| Bounded staging action adapter | After prior gate | Allowlisted action + idempotency + recovery handling | Fresh authorization, denial/replay/concurrency/crash tests; known-outcome verification and stop mechanism |
| Live model comparison | After adapter gate and approved credentials | Versioned prompts, model outputs and held-out evaluation | Model never receives operator credentials/ground truth; control and task-quality metrics reported separately |

These are proposed planning targets, not promised calendar commitments or
completed activities. Failures move the schedule; they are not waived to fit it.

## Stop and recovery rules

Stop on any action outside the target allowlist, unauthorized execution, approval
parameter mismatch, uncertain side effect, corrupted audit replay, or accidental
production/customer-data access. Disable the executor before diagnosis. Preserve
logs. Reconcile real external state before retrying an uncertain action. The
simulator's SQLite transaction does not solve distributed action atomicity.

For the current simulator, archive the private database and initialize a new
file for a new trial. Never overwrite history while claiming uninterrupted audit
integrity. For later real-service trials, snapshots and compensating actions must
be specified and authorized before inducing faults.

## Pilot evaluation to collect later

Record operator task success, approval comprehension, veto effectiveness, time to
verified recovery, unnecessary interventions, escalation workload, every failure,
and system overhead. Compare against an operator-run documented runbook and an
approval-only condition. Define representative scenarios and independent labels
before collection. Do not reuse the deliberately adversarial control-suite mix
as an estimate of actual incident prevalence.

Juber intends to present at IAAI-27 in Montréal if accepted, subject to visa
arrangements. Registration, visa issuance, travel booking and funding have not
been completed or guaranteed by this task.
