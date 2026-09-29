# Diagnosis Preregistration — mizan.nlp Phase 3, Track 1

**Artifact under diagnosis:** `backend/nlp/artifacts/default/` v1.0.0 (mizan-sense-wsd),
per-lemma sklearn LogisticRegression, variant 'a' (surface+context features),
trained 2026-09-29. **Read-only**: no retraining, no artifact modification, no
relabeling.

**Baseline to reproduce** (from manifest.json, Track-1 EVAL_REPORT.md):
- Test accuracy 0.7592 (95% CI 0.7241–0.7927), macro-F1 0.5471,
  evaluated senses 88, of which **12 with zero recall**.

## 1. What I will measure

1. **Reproduction**: load `model.joblib` (sha256-verified against manifest) and
   run inference on the Phase-1 test split (`split=="test"`, `perturbation=="base"`
   → 627 items, matching manifest `eval_n`), using the frozen feature extractor
   in `backend/nlp/wsd.py` (copied verbatim from training; any divergence is a
   finding, not a fix I will make).
2. **Repro criteria**: accuracy within ±0.005 of 0.7592 AND the same 12
   zero-recall senses (set equality). If either fails, I report ❌ honestly with
   the observed numbers instead of forcing a match.
3. **Per-sense table** (evaluated = senses present in the 627-item test set):
   lemma, sense_id, n_train (all train-split records for that sense), n_test,
   recall, precision, top-2 predicted-sense confusions for misclassified items.
4. **Per zero-recall sense**: train/test counts, confusion targets, plus a cause
   classification from §2 and a fix recommendation from §3.

## 2. Cause classification (with decision rules)

- **(a) data starvation** — n_train ≤ 5 total train records for the sense, OR
  the sense's share of its lemma's train mass < 2%. Mechanism: the classifier
  never had signal to learn. Flag is *data quantity*.
- **(b) feature blindness** — n_train ≥ 20 AND train examples exist with
  similar surface/context to test items, yet the model predicts a *different*
  sense of the same lemma with high confidence. Evidence I will show:
  char-n-gram feature overlap between the misclassified test item and the
  winning (wrong) sense's train items — i.e. the features don't separate the
  senses. Flag is *feature expressiveness*.
- **(c) label noise (suspect, never relabeled)** — keyword-rule labels
  (`label_source=="keyword-rule"`, 28,726/28,841 records; only 115 audited
  across the full set) where the keyword rule plausibly mismatches the item:
  e.g. train and test items of the same sense share identical surface forms
  but split across senses (rule fired inconsistently), or the sense's items
  carry `sense_quality` / evidence notes contradicting the assigned sense.
  I will flag suspicion with the concrete evidence; I will **not** relabel.

Borderlines and tie-breaks go to JEV (`~/workspace/skills/typesafe-jev/bin/jev-ask`);
the classification for each sense is recorded with its evidence.

## 3. Fix recommendations (per sense, one of)

- **data-side fix** — collect/generate more labeled examples for the sense
  (human audit, targeted keyword-rule expansion, or perturbation variants that
  preserve sense), or merge an unlearnable micro-sense into a coarser one.
- **model-side fix** — extend the frozen feature set (e.g. variant 'b' morph
  features, root/POS context, wider context window), class-balanced training,
  or a threshold/calibration rule for the sense.
- **leave-alone** — sense is vanishingly rare in the corpus (n_test tiny and
  n_train tiny, no cheap data source); cost of fixing exceeds value.

## 4. Outputs

- `backend/nlp/DIAGNOSIS_PREREG.md` (this file).
- `backend/nlp/DIAGNOSIS.md`: full per-sense table + cause classification +
  recommendations.
- Claim tagging: ✅ verified by my run / 📋 from earlier (Track-1 reports,
  manifest) / ❌ could not verify.

## 5. Pre-committed checks

- [ ] Artifact sha256 matches manifest before unpickling.
- [ ] Feature extractor used is the frozen one in `wsd.py` (no edits).
- [ ] No writes to `artifacts/`, no retraining, no relabeling — verified by
      diffing the branch against main for those paths.
