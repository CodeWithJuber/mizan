# Evidence-bounded claims

| Claim | Evidence now | Permissible scope |
|---|---|---|
| Approval can resume in the reference app | Persistent approve/execute test, CLI smoke transcript | Local trusted-operator workflow; not main Mizan chat/API |
| Single finalized request does not execute twice | Replay and two-worker race tests | SQLite synthetic action transaction only |
| Policy blocks tested disallowed proposals | 0 executions in 15 constructed cases under policy/full configurations | Tested cases; not a universal safety theorem or field rate |
| Outcome observation detects silent failure | Full detects 3/3 injected failures vs. 2/3 without separate observation | Synthetic state and fault flags; not real provider timeouts |
| Normal tasks remain resolvable | 4/4 deliberately simple clean cases across configurations | Three-bit planner domain; not broad incident-resolution quality |
| Semantic results repeat | 96/96 matching outcomes across two runs | Identical deterministic fixtures; no stochastic-model reproducibility claim |
| Proposed deployment path exists | Owner selected Hostlelo isolated staging; deployment plan names gates/resources | Proposed; actual host/access/pilot results unverified |
| Arabic/English safety parity | None | Do not claim |
| Live LLM behavior or prompt-injection robustness | None | Do not claim |
| Production utility, uptime or commercial return | None | Do not claim |
| Forgekit/Hikmah runtime integration | None in this application | Design lineage only; Mizan policy classifier is actual code reuse |
| Human-written manuscript | Recovered writing offers style/direction but insufficient verified technical prose | Generated draft must remain labeled; author-written substance still required |

The small acceptance suite intentionally includes faults matched to the controls.
It is useful engineering evidence and weak evidence of generalization. Reviewer
objections about realism, novelty and deployment distance remain valid. The paper
must discuss those limitations rather than imply that synthetic acceptability
guarantees acceptance.
