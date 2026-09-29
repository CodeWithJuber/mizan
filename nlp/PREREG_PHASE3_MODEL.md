# PREREGISTRATION — Phase 3 Track 3: model-side ablations

**FROZEN:** 2026-09-29 ~17:55 +04 (Asia/Dubai), BEFORE any ablation training
or candidate evaluation. Track 1's diagnosis (`nlp/DIAGNOSIS.md`) and
the Track-4 eval harness (`nlp/eval_phase3.py` + `PREREGISTRATION_PHASE3.md`)
are read and frozen; no candidate artifact has been trained or evaluated.

**Scope:** model-side interventions only, on the CURRENT (pre-merge) sense
inventory. Track 2 is concurrently doing inventory merges + mining + retraining
— Track 3 does NOT touch Track 2's files and does NOT relabel anything.

## 1. Diagnosis input (from Track 1, read-only)

9/12 zero-recall senses are label noise (data-side fix, Track 2); 2 are data
starvation (أَيّ:so which — 1 unique train item; نَذِير:warning — plural only in
test surah); 1 is feature blindness (نِساء:wives — possessive-suffix signal seen
in train as -هم, unseen as -كم in test; 20 train vs 130 majority sibling).
Baseline: accuracy 0.7592, macro-F1 0.5471 (115 senses) / 0.6554 (88 evaluated).

## 2. Interventions to ablate (exactly 3, no kitchen-sink)

All per-lemma, sklearn LogisticRegression (lbfgs, C=1.0), variant-'a' char
2–4-gram features — same recipe as Track 1 unless stated:

- **A. `balanced`**: `class_weight="balanced"` per lemma classifier. Hypothesis:
  reweighting the logreg loss toward minority senses recovers some of the
  12 zeros (esp. أَيّ, نَذِير) without starving majority senses.
- **B. `focal`**: focal-loss-style sample weighting on logreg. Iterative
  deterministic reweighting: fit → per-sample true-class probability p →
  `w = α_class · (1−p)^2`, refit (3 rounds, α from class frequencies, γ=2
  fixed). Hypothesis: focuses learning on the hard minority items that the
  sibling-majority crushes.
- **C. `poss-sfx`**: one morphological feature at TRAIN time,
  `poss_sfx=<person>` (person ∈ {1s,2m,2f,2mp,2fp,3m,3f,3mp,3fp,3dual,2dual,1p})
  from the surface form's trailing possessive suffix (diacritics stripped).
  Targets نِساء:wives blindness directly: gives the classifier a weightable
  suffix-person abstraction instead of relying on suffix n-grams alone.
  NOTE (honest): the Track-4 harness is frozen and evaluates candidates with
  the frozen variant-'a' extractor, so at TEST time this column is 0 for all
  items. The measured effect of C is therefore train-time weight
  redistribution only — disclosed here, not discovered post-hoc. Expectation:
  likely ≈null; the true test of the feature needs Track 2's mined suffix
  data. If C shows ≈no effect, that is a null result, reported as such.

Plus a **control**: Track-1 recipe reconstruction on train split. Must
reproduce the shipped artifact's test predictions before any ablation is
trusted. If control ≠ shipped predictions, investigate (train+dev?); do not
proceed on an unfaithful pipeline.

**Data (frozen):** Q-CSMP v2, md5 `35c1a6bf0cbaa58aa7d52d3683d68b5d`,
per-lemma whole-surah holdout, base items only, train 4691 / dev 451 / test 627
(same identity as the Track-4 prereg). Train on train split; dev unused
(hyperparameters fixed — γ=2, 3 rounds, C=1.0 — no tuning on dev).

## 3. Evaluation & decision rule (frozen)

Each variant is packaged as a bundle-contract artifact and scored with the
FROZEN Track-4 harness (`eval_phase3.py`) against the locked Phase-3 baseline.
One eval run per variant (deterministic seeds; no test-peeking loops).

**Candidate-PASS rule = the Track-4 rule (PREREGISTRATION_PHASE3.md §4):**
WIN (mean target-recall lift ≥ +0.10 over the 12 senses) + GUARD-A (accuracy
drop ≤ 0.02) + GUARD-F (macro-F1 drop ≤ 0.02) + NO-REGRESSION (no supported
n_test ≥ 5 sense → 0.0). Verdict per variant: PASS/FAIL with each leg named.

**Non-negotiable guardrails (task-level, stricter than Track-4 GUARD-F):**
accuracy must stay within 0.02 of 0.7592 AND macro-F1 must NOT drop below
0.5471 at all. A variant breaching these is dead even if it passes the
Track-4 rule — JEV confirms the tolerances (logged §5).

**Winner rule:** among variants that PASS the Track-4 rule AND satisfy the
task guardrails, winner = highest mean target-recall lift; tie-break = smaller
accuracy drop. If none passes: NO SHIPPABLE WINNER — the best-lift variant is
reported as informational only, with the failing legs named, and no
"improvement" claim is made. The null hypothesis is real: 9/12 zeros are label
noise unfixable model-side, so an all-FAIL ablation table is an expected
outcome, not a surprise.

**What ships:** the winning intervention is applied to Track 2's MERGED
inventory once its retrained data lands on the branch; the resulting model is
re-evaluated with the frozen harness and, if the Track-4 rule passes on the
merged inventory, written to `nlp/artifacts/candidate_model_v1/`
(joblib + manifest.json with sha256; manifest `eval_verdict` names the rule
outcome honestly). If Track 2 has not landed when ablations finish, the
standalone (pre-merge) winner artifact is written to `candidate_model_v1/`
marked `pending-track2-merge` in the manifest, and the merge application is
reported as an explicit pending step — no blocking forever. Never overwrite
`artifacts/default/` or Track 2's `candidate_data_v1/`.

## 4. What counts as FAIL for a variant

1. WIN leg missed (mean target lift < +0.10). 2. Task guardrail breached
   (acc drop > 0.02 or macro-F1 < 0.5471). 3. NO-REGRESSION violated.
4. Control does not reproduce shipped predictions → the pipeline is
   unfaithful; stop and report (not an ablation result).

## 5. JEV decision log

| # | question | decision | conf |
|---|---|---|---|
| 1 | noul: "the task's guardrails (accuracy within 0.02 of 0.7592; macro-F1 must not drop below 0.5471 — stricter than the Track-4 GUARD-F allowance) are appropriate for model-side ablations" | (pending — called before any training) | |
| 2 | choice: intervention shortlist {A balanced, B focal-style, C poss-sfx feature} vs alternatives (oversampling, C=grid, neural) | (pending — called before any training) | |
| 3 | choice: winner selection among variant results, given the preregistered rule | (pending — called after all variants evaluated) | |

All calls cached by `jev-ask` (`sha256(state, questions)`). Weak confidences
are disclosed, not rounded up.

## 6. Quran lens (standing constraint)

- *tabayyun*: rule frozen before any candidate exists; checksums + split
  identity verified by the harness before scoring.
- *lā taqfu*: test-absent senses → `null` recall, never 0.0; the C-variant
  test-time limitation is declared pre-hoc.
- *amāna*: fail-closed manifest validation before unpickling; no Track-2
  file touched; no claim without the harness's numbers.

## 7. Honesty bar

Every ablation number tagged ✅ verified (frozen harness, this run) /
📋 from-earlier / ❌ could-not-verify. Null results are results.

---
*End of preregistration. Ablation measurements below this line are post-freeze.*

## Addendum A — Amendment A1 adopted (2026-09-29 ~18:15 +04, pre-first-candidate-eval)

After this preregistration froze, Track 4 committed Amendment A1
(`PREREGISTRATION_PHASE3.md` §10), a merge-aware `eval_phase3.py`, the frozen
`SENSE_MERGES_PHASE3.json` (9 merges, 115 → 106 senses), and a locked
`BASELINE_PHASE3.json` in post-merge space — all BEFORE Track 3's first
candidate evaluation. Per the parent orchestrator's update, Track 3 adopts A1
as the scoring authority:

- **Scoring space:** post-merge 106-sense space; baseline = Track 4's locked
  `BASELINE_PHASE3.json` (effective acc **0.802233**, macro-F1 **0.615794**;
  original-space reference 0.759171 / 0.547097). No Track-3 re-lock.
- **Candidate-PASS rule** = Track-4 rule §4 + A1 §10: WIN (mean target recall
  lift ≥ +0.10 over the 12 targets in post-merge space; the 9 merged targets
  contribute ~0 by construction — baseline resolves 26/26 former items — so
  the bar must be cleared by the 3 unmerged senses أَيّ/نَذِير/نِساء, max
  achievable +0.25) + GUARD-A (acc drop ≤ 0.02 vs 0.802233) + GUARD-F
  (macro-F1 drop ≤ 0.02 vs 0.615794) + NO-REGRESSION (post-merge space).
- **Interventions unchanged** (frozen §2): balanced, focal, poss-sfx — all
  three already target the 3 unmerged senses (minority reweighting for the
  starved أَيّ/نَذِير; suffix-person feature for نِساء). نِساء has n_test=1:
  any gain there is a single-item swing, reported as such, never oversold.
- **Winner rule unchanged** (§3): among variants passing the A1 rule, max
  mean target lift; tie-break = smaller accuracy drop. None pass → null
  result, best-lift reported informationally, no "improvement" claimed.
- **Harness bug found + disclosed (not fixed on branch):** the branch's
  ruff-cleaned pre-A1 harness crashed in `per_sense_table`
  (`for r, p in zip(pred, rows)` — unpacking swapped; every other loop uses
  `p, r`). Fixed only in my `/tmp` working copy used for a superseded
  original-space run; Track 4's A1 harness does not have the bug. Reported
  for Track 4 to fix; Track 3 does not touch Track 4's files.
- **Superseded:** an early WIP-harness baseline lock and a killed
  original-space ablation run — decision-irrelevant under A1.

## Addendum B — packaging move (2026-09-29 ~18:20 +04)

User merged PR #39 and moved `backend/nlp/` → top-level `nlp/` on main
(commit `13504471`); the branch was rebased onto the new main (now
`a7d24f97`). This rebase dropped the first Addendum-A commit; it is
re-applied here. New paths: prereg at `nlp/PREREG_PHASE3_MODEL.md`,
candidate at `nlp/artifacts/candidate_model_v1/`, harness invoked as
`python3 nlp/eval_phase3.py` with top-level `import nlp`. The rebased A1
harness is logic-identical to the one used for the ablations below
(verified: whitespace-insensitive diff shows formatting + path strings only).
