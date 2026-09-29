# PREREGISTRATION — Phase 3: candidate-model eval for `mizan.nlp` WSD

**FROZEN:** 2026-09-29 ~14:05 +04 (Asia/Dubai), BEFORE any Phase-3 candidate
model exists. No candidate artifact has been built, loaded, or evaluated.
The baseline lock (`BASELINE_PHASE3.json`) is produced AFTER this freeze,
by the frozen harness, against the current main artifact only.

**Scope:** Phase 3 will produce candidate artifacts — data-augmented and
model-tweaked variants of `mizan-sense-wsd` v1.0.0. This document freezes,
in advance, the eval split, the metrics, the decision rule for picking a
winner, and what counts as a fail. Nothing here may be edited after the
first candidate evaluation begins; any change requires a new dated
amendment with its own freeze attestation.

**Path note:** the task brief named `backend/mizan/nlp/`; no such directory
exists in the repo. The package lives at `nlp/` (verified at main
`63dfb521`). All Phase-3 files go under `nlp/`.

## 1. Eval split (identity — verified pre-freeze, all ✅)

- **Dataset:** Q-CSMP v2, local `~/workspace/research/stage2/qcsmp_v2.jsonl`,
  md5 `35c1a6bf0cbaa58aa7d52d3683d68b5d` ✅ (matches the stage-2 freeze hash).
- **Protocol:** per-lemma whole-surah holdout, `split` field as shipped,
  **base items only** (`perturbation == "base"`). For each lemma, exactly one
  surah is held out as test and one as dev; the rest is train.
- **Sizes (base items):** train **4,691** / dev **451** / test **627** ✅.
- **Per-lemma disjointness:** 0 of 48 lemmas have a test surah that appears
  in its train or dev surahs ✅ (verified 2026-09-29). Note: at the *global*
  level the 15 test surahs do appear in other lemmas' train data — the
  holdout is per-lemma, not per-surah. This is the Phase-1 protocol and is
  kept unchanged.
- **Label universe:** 115 `(lemma, sense)` pairs from train+dev+test.
  88 are test-attested; 27 have zero test items.
- **Audited items:** the 4 audited test items ride inside the test split
  as-is (per Track-1's frozen role); reported as a sanity note only, no
  decision weight.
- **Harness enforcement:** `eval_phase3.py` re-verifies dataset md5, the
  4691/451/627 counts, and per-lemma surah disjointness before scoring.
  Any mismatch → FAIL (fail-closed), never a silent re-split.

Per-lemma test/dev surahs (frozen):

| lemma | test surah (n) | dev surah (n) | lemma | test surah (n) | dev surah (n) |
|---|---|---|---|---|---|
| آباء | 7 (5) | 2 (4) | عَبْد | 37 (10) | 17 (8) |
| آخَر | 6 (4) | 12 (4) | عَدُوّ | 2 (6) | 20 (5) |
| آخِر | 2 (17) | 3 (10) | عَلِيم | 2 (20) | 4 (17) |
| آيَة | 6 (32) | 7 (29) | عَيْن | 7 (4) | 18 (3) |
| أَجْر | 26 (11) | 4 (10) | عِلْم | 6 (8) | 3 (6) |
| أَرْض | 2 (24) | 7 (21) | فَضْل | 4 (10) | 3 (8) |
| أَكْثَر | 26 (9) | 12 (6) | قَرْيَة | 7 (6) | 11 (3) |
| أَمْر | 11 (13) | 18 (8) | قَوْل | 4 (9) | 2 (6) |
| أَهْل | 3 (12) | 4 (10) | كَثِير | 5 (11) | 4 (6) |
| أَوَّل | 6 (5) | 9 (4) | كِتاب | 3 (32) | 2 (27) |
| أَيّ | 55 (31) | 33 (6) | مَثَل | 2 (6) | 16 (6) |
| أُمَّة | 16 (4) | 10 (2) | مُؤْمِن | 4 (18) | 3 (16) |
| بَعْض | 2 (14) | 6 (14) | مُبِين | 4 (7) | 36 (7) |
| بَيِّنَة | 2 (8) | 40 (6) | مِثْل | 2 (5) | 4 (3) |
| بُنَىّ | 2 (9) | 7 (9) | ناس | 2 (38) | 3 (19) |
| حَقّ | 2 (19) | 10 (18) | نَذِير | 54 (11) | 35 (6) |
| خالِد | 2 (8) | 3 (6) | نَفْس | 2 (33) | 3 (21) |
| خَيْر | 2 (26) | 3 (13) | نِساء | 4 (19) | 2 (9) |
| دِين | 9 (7) | 5 (6) | وَلِيّ | 4 (9) | 42 (8) |
| ذُو | 3 (7) | 41 (3) | يَد | 5 (15) | 2 (7) |
| ذِكْر | 21 (7) | 20 (5) | يَمِين | 5 (7) | 16 (6) |
| زَوْج | 33 (9) | 2 (7) | يَوْم | 2 (25) | 3 (17) |
| سَيِّئَة | 4 (4) | 40 (4) | شَهِيد | 2 (7) | 4 (7) |
| شَىْء | 6 (22) | 2 (21) | صالِحَة | 4 (4) | 18 (4) |

## 2. Metrics (frozen)

Computed on the 627 test base items, per-lemma top-1 prediction vs gold
`sense`, features from the frozen extractor (char 2–4 grams of
surface/prev/next + length bucket — byte-identical to the shipped
`nlp/wsd.py`, verified by the harness self-test).

1. **Per-sense recall, all 115 senses** (primary). Test-attested senses:
   correct / n. Senses absent from test (27): reported as `null`
   (undefined — NOT 0.0; honesty: no claim without knowledge).
2. **Overall accuracy** = correct / 627 (top-1).
3. **Macro-F1 over the 115 senses** with the frozen Track-1 rule:
   senses absent from test contribute 0.0; predictions for senses outside
   the universe map to a dummy class; `zero_division=0`. Replicated exactly
   from `train_track1.py`.
4. **Mean sense recall** (test-attested senses) — informational.
5. **Per-lemma accuracy** (48) — informational.
6. **ECE** (10 bins) — informational note, no decision weight.
7. **Bootstrap 95% CIs** (seed 137, 10,000 resamples) for accuracy and
   macro-F1 — reported, NOT decision inputs. Known quirk (documented in
   Track-1 EVAL_REPORT): the macro-F1 point estimate can sit slightly above
   its percentile CI because resamples drop rare senses; the skew is real,
   not a bug.

## 3. The 12 target senses (frozen)

Baseline per-sense recall = 0.0 on all 12 (Phase-1, n=627). Sense IDs follow
the `qcsmp2:<lemma>:<sense-slug>` scheme from `sense_inventory.json`.

| # | sense_id | n_test | n_train |
|---|---|---|---|
| 1 | `qcsmp2:أَجْر:payment` | 10 | 7 |
| 2 | `qcsmp2:أَيّ:so which` | 31 | 1 |
| 3 | `qcsmp2:بَعْض:some` | 1 | 16 |
| 4 | `qcsmp2:ذُو:owner` | 2 | 11 |
| 5 | `qcsmp2:صالِحَة:good deeds` | 1 | 9 |
| 6 | `qcsmp2:عِلْم:any knowledge` | 1 | 8 |
| 7 | `qcsmp2:قَرْيَة:cities` | 4 | 2 |
| 8 | `qcsmp2:قَوْل:saying` | 3 | 8 |
| 9 | `qcsmp2:كِتاب:scripture` | 1 | 19 |
| 10 | `qcsmp2:مُبِين:manifest` | 3 | 10 |
| 11 | `qcsmp2:نَذِير:warning` | 11 | 2 |
| 12 | `qcsmp2:نِساء:wives` | 1 | 4 |

69 test items total across the 12. Five have n_test ≤ 2 — per-sense recall
is noisy there; the rule uses the unweighted mean (frozen), and the noise
is disclosed here rather than hidden.

## 4. Decision rule (frozen — tolerances set by JEV, §7)

Let B = locked baseline (`BASELINE_PHASE3.json`), C = candidate. All
deltas are point estimates, candidate − baseline.

- **WIN — target recall lift:** mean over the 12 target senses of
  (recall_C − recall_B) **≥ +0.10**.
- **GUARD-A — accuracy:** accuracy_C − accuracy_B **≥ −0.02**
  (drop of at most 0.02).
- **GUARD-F — macro-F1:** macroF1_C − macroF1_B **≥ −0.02**.
- **NO-REGRESSION:** no test-attested sense with baseline recall > 0 **and**
  n_test ≥ 5 may drop to exactly 0.0 recall in C. Flips on senses with
  n_test < 5 are reported as **warnings**, not fails (21 of the 76
  previously-nonzero senses have n_test ≤ 2 — a single-item noise flip must
  not fail a good candidate).

**Verdict: PASS** iff WIN + GUARD-A + GUARD-F + NO-REGRESSION all hold.
Otherwise **FAIL**, with each failed leg named in the report. A candidate
may also be reported with warnings and still PASS.

**Determinism & discipline:** one eval run per candidate (fixed seeds;
lbfgs/DictVectorizer are deterministic). No test-set peeking loops, no
post-hoc rule changes. The harness writes a JSON report per run.

## 5. What counts as FAIL (explicit)

1. WIN leg missed (mean target lift < +0.10).
2. GUARD-A missed (accuracy drop > 0.02).
3. GUARD-F missed (macro-F1 drop > 0.02).
4. NO-REGRESSION violated (a supported previously-nonzero sense → 0.0).
5. **Fail-closed harness triggers** (each is a FAIL with the reason
   recorded, not a crash): manifest schema/license invalid; sha256 mismatch
   on `model.joblib` or `sense_inventory.json` (checked BEFORE unpickling);
   missing required files; model over the 250 MB size budget; bundle
   missing the primary `model_a_surface_ctx` contract
   (per-lemma `vec`/`clf`/`labels`); dataset md5 mismatch; split counts ≠
   4691/451/627; per-lemma surah-overlap detected; feature-extractor
   self-test mismatch.
6. A candidate that cannot be loaded under the bundle contract at all.

## 6. Baseline lock

- Baseline = the main-branch artifact `mizan-sense-wsd` v1.0.0
  (`model.joblib` sha256
  `019f0795a51d371ca91714c37b1bd8a861dff2ea2bf3f36433c99a777dcf9c26` ✅),
  evaluated once by the frozen harness → `BASELINE_PHASE3.json`.
- Expected from Track-1 (📋 from-earlier): accuracy **0.7592**
  [0.7241, 0.7927], macro-F1 **0.5471**. Lock rule: the harness must
  reproduce both within **±0.0005** (rounding noise). If not, investigate
  and report honestly — numbers are never fudged to match.
- Runtimes: sklearn 1.9.1 / joblib 1.6.0 / numpy 2.5.3 (manifest-pinned;
  the harness records actual versions and warns on mismatch).

## 7. JEV decision log (all calls logged)

| # | time (+04) | type | question | decision | conf |
|---|---|---|---|---|---|
| 1 | 2026-09-29 ~14:00 | choice | mean-recall-lift bar on the 12 target senses (+0.05 / +0.10 / +0.15) | **+0.10** (`lift_010`) | 0.33 — weak; adopting the proposed value, disclosed as reviewable |
| 2 | 2026-09-29 ~14:00 | choice | max allowed accuracy/macro-F1 drop (0.01 / 0.02 / 0.05) | **≤ 0.02** (`drop_002`) | 0.73 |
| 3 | 2026-09-29 ~14:00 | noul (thr 0.7) | "zero-regression hard-fail on ALL 76 previously-nonzero senses is appropriately strict" | **NO** — p=0.67 < 0.7, not confirmed | 0.67 |
| 4 | 2026-09-29 ~14:01 | choice | zero-regression policy (hard-all / hard-supported-n≥5 / flag-only) | **hard on n_test ≥ 5; warnings below** (`hard_supported`) | 0.69 |

Call 3's weak NO + the measured fact (21/76 nonzero senses have n_test ≤ 2)
motivated call 4's refinement. All four calls cached by `jev-ask`
(`sha256(state, questions)`).

## 8. Quran lens (standing constraint)

- *tabayyun* (verify before acting): the rule is frozen before any candidate
  exists; the harness verifies checksums and split identity before scoring.
- *lā taqfu* (no claim without knowledge): senses absent from test get
  `null` recall, not 0.0; weak JEV confidences are disclosed, not rounded
  up; one eval run, no peeking loops.
- *amāna* (stewardship): fail-closed loading; the artifact is first-party
  and sha-pinned, but unpickling still happens only after verification.

## 9. Honesty bar

Every number in Phase-3 reports is tagged ✅ verified (computed by the
frozen harness in the run being reported), 📋 from-earlier (Track-1 /
stage-2, not recomputed), or ❌ could-not-verify (stated plainly).
`BASELINE_PHASE3.json` carries the claim tags with the run that produced it.

---
*End of preregistration. Candidate measurements below this line are post-freeze.*
