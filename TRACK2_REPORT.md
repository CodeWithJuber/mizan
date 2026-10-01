# TRACK-2 EXECUTION REPORT — Phase 3 data-side fixes

**Executed:** 2026-09-29 ~14:05–15:00 +04 · **Prereg:** `nlp/PREREG_PHASE3_DATA.md`
(frozen before execution) · **Branch:** `feature/mizan-nlp-phase3` @ `a7d24f97`
(rebased; package now top-level `nlp/`) · **Scoring:** Track-4 frozen harness
(`nlp/eval_phase3.py`, Amendment A1 — post-merge 106-sense space)

## 1. Inventory merges — 9 frozen merges executed (JEV-approved, none rejected)

| # | Merge | JEV | conf | Records relabeled (train/dev/test, base) |
|---|---|---|---|---|
| M1 | أَجْر: `payment` → `reward` | merge | 0.52 ⚠️ weak | (see counts) |
| M2 | بَعْض: `some` → `other` | merge | 0.77 | |
| M3 | ذُو: `owner` → `possessor` | merge | 0.94 | |
| M4 | صالِحَة: `good deeds` → `righteous deeds` | merge | 0.85 | |
| M5 | عِلْم: `any knowledge` → `knowledge` | merge | 0.49 ⚠️ weak | |
| M6 | قَرْيَة: `cities` → `town` | merge | 0.69 | |
| M7 | قَوْل: `saying` → `word` | merge | 0.61 | |
| M8 | كِتاب: `scripture` → `book` | merge | 0.97 | |
| M9 | مُبِين: `manifest` → `clear` | merge | 0.95 | |

**128 base records relabeled** (train/dev/test). The test split was never
relabeled on disk beyond the symmetric scoring remap, and never used in training.

**Amendment A1 conformance.** The frozen merge map
(`nlp/SENSE_MERGES_PHASE3.json`) defines exactly these 9 merges → **106
senses**. The earlier JEV vocative decision (S1, conf 0.80: `أَيّ:mankind` +
`أَيّ:you who believe` → `vocative`) is **reverted / superseded**: the frozen
scoring ontology takes precedence, the harness fail-closes on any other label
space (`load_merges` validates the map against the shipped inventory; bundle
labels must lie within the frozen 106). Logged here honestly — the merge was
linguistically sound but out of scope of the frozen map. (n_test = 0 for both
vocative senses, so the revert is score-neutral.)

**Inventory:** 115 → **106 senses** (48 lemmas unchanged). The staged
`sense_inventory.json` is the **original 115-sense inventory** (byte-identical
to `nlp/artifacts/default/`, sha256 `8b298596…` — the harness's `load_merges`
requires merged-away sense_ids to be present); the **bundle predicts the
frozen 106 labels** (prediction remap is a no-op).

## 2. Targeted mining — real Quranic occurrences only (THE critical path)

### ✅ أَيّ interrogative → `so which`: 24 items mined → test recall 0.0 → 1.0

Source: `#162 quran_words-3` word-level CSV (the dataset's own source);
every surface verified against the Tanzil Uthmani XML (`tanzil_surface_ok`).
Train split, base records, `label_source: "targeted-mining"`, surahs ∉ {33, 55}
(أَيّ's dev/test surahs). Gloss-verified interrogatives only; borderline
forms excluded (17:110:7, 19:69:6, 28:28:5, 82:8:2); vocatives excluded.

| # | address | form | gloss |
|---|---|---|---|
| 1 | 3:44:13 | أَيُّهُمْ | (as to) which of them |
| 2 | 4:11:60 | أَيُّهُمْ | which of them |
| 3 | 6:19:2 | أَىُّ | What |
| 4 | 7:185:19 | فَبِأَىِّ | So in what |
| 5 | 9:124:8 | أَيُّكُمْ | Which of you |
| 6 | 11:7:14 | أَيُّكُمْ | which of you |
| 7 | 17:57:8 | أَيُّهُمْ | which of them |
| 8 | 18:12:4 | أَىُّ | which |
| 9 | 18:19:28 | أَيُّهَآ | which is |
| 10 | 19:73:11 | أَىُّ | Which |
| 11 | 20:71:23 | أَيُّنَآ | which of us |
| 12 | 26:227:17 | أَىَّ | (to) what |
| 13 | 27:38:4 | أَيُّكُمْ | Which of you |
| 14 | 31:34:21 | بِأَىِّ | in what |
| 15 | 40:81:3 | فَأَىَّ | Then which |
| 16 | 45:6:7 | فَبِأَىِّ | Then in what |
| 17 | 53:55:1 | فَبِأَىِّ | Then which (of) |
| 18 | 67:2:6 | أَيُّكُمْ | which of you |
| 19 | 68:6:1 | بِأَييِّكُمُ | Which of you |
| 20 | 68:40:2 | أَيُّهُم | which of them |
| 21 | 77:12:1 | لِأَىِّ | For what |
| 22 | 77:50:1 | فَبِأَىِّ | Then in what |
| 23 | 80:18:2 | أَىِّ | what |
| 24 | 81:9:1 | بِأَىِّ | For what |

File: `nlp/mining/mined_interrogative_ayy.jsonl` (Q-CSMP record schema).
Mining script: `nlp/track2_train/mine_ayy.py` (asserts lemma, surah
exclusion, dataset dedupe, gloss match, Tanzil surface per item).

JEV note: two weak rejects (0.25 composite, 0.46 narrow) with no reason given;
proceeded per the preregistered evidence-based plan — disclosed, not hidden.

### ❌ نَذِير plural نُذُر → `warning`: 0 items — well provably dry

Full-Quran enumeration (Tanzil XML + `#162` word CSV, plural pattern ذُ):

| occurrence | surah | dataset | label |
|---|---|---|---|
| وَٱلنُّذُرُ 10:101:10 | train | ✅ in dataset | `warner` |
| ٱلنُّذُرُ 46:21:10 | train | ✅ in dataset | `warner` |
| ٱلنُّذُرِ 53:56:4 | train | ✅ in dataset | `warner` |
| نُذُورَهُمْ 22:29:5 | — | not in dataset | different lemma (نَذْر "vow") |
| 11× plural forms (وَنُذُرِ ×6, بِٱلنُّذُرِ ×3, ٱلنُّذُرُ ×2) | **54 = test surah** | ✅ in dataset | `warning` |

**15** plural-pattern words exist in the entire Quran; **14** are lemma
نَذِير. The `warning` sense of the plural occurs **only in surah 54** (the test
surah). The 3 train plurals are unambiguously `warner` per classical tafsir
(10:101: النُّذُرُ = الرسل, paired with ٱلْءَايَٰتُ; 46:21: خَلَتِ temporal;
53:56: مِنَ ٱلنُّذُرِ ٱلْأُولَىٰ) — relabeling any of them to chase test items
would be dishonest gaming, so none was touched. **0 minable. Honest shortfall
reported, not filled.** (JEV S2b: skip mining, conf 0.81 — consistent.)

### ❌ نِساء possessive → `wives`: 0 items — well provably dry

Full-Quran enumeration (15 possessive-suffix نِساء words):

| split | items | senses |
|---|---|---|
| dev (surah 2) | 2:49, 2:187, 2:223, 2:226 | 1 women + 3 wives |
| test (surah 4) | 4:15, **4:23:19 ← the target** | 1 women + 1 wives |
| train | 3:61, 7:127, 7:141, 14:6, 28:4, 40:25, 58:2, 58:3, 65:4 | 7 women + 2 wives |

**All 15 are already in the dataset — 0 unmined occurrences exist.**
The test item (4:23:19 نِسَائِكُمْ, "mothers of your wives" in the mahram
list) has no train precedent: train `wives` possessives are نِّسَائِهِم
(58:2, 58:3) and vocatives (33:30, 33:32); the كُمْ + wives pattern appears
only in dev (2:187, 2:223 — frozen, untouchable). **0 minable. Honest
shortfall.** (JEV S2c: skip / report honestly.)

## 3. Retraining

- **Recipe** (frozen, verified 627/627 prediction agreement on unmerged data):
  train-split base records only + 24 mined; per-lemma `DictVectorizer` +
  `LogisticRegression(C=1.0, lbfgs, max_iter=1000)`; labels = sorted unique
  senses; frozen `_features` variant "a" (primary) + "b", now single-sourced
  from `nlp/wsd.py::_features` (verified byte-identical to the earlier copy).
- **Train set:** 4,715 records (4,691 base + 24 mined); **128** base records
  relabeled by the 9 frozen merges.
- **Single-sense lemmas** (5: أَجْر, صالِحَة, عِلْم, قَرْيَة, مُبِين):
  honest constant prior predictor (`DummyClassifier(strategy="prior")`).
- **Artifact:** `nlp/artifacts/candidate_data_v1/`
  (`model.joblib` 5.6 MB, `manifest.json` v1.1.0-data,
  `sense_inventory.json` = original 115 senses, see §1).
  `artifacts/default/` untouched. Manifest validates against the real
  `nlp/artifact.py` validator (schema v1 + sha256 + Apache-2.0 + size budget).

## 4. Honest numbers — frozen harness, post-merge 106-sense space

| Metric | Baseline (locked) | Candidate | Δ | Guardrail |
|---|---|---|---|---|
| Accuracy | 0.802233 | **0.85327** | **+0.0510** | ≥ −0.02 ✅ |
| Macro-F1 (106) | 0.615794 | **0.625783** | **+0.0100** | ≥ −0.02 ✅ |
| **Mean target-recall lift (12 targets)** | — | **0.0926** | bar +0.10 | ❌ **miss by 0.0074** |

Per-target deltas (candidate − baseline, post-merge space):

| target | baseline | candidate | Δ |
|---|---|---|---|
| 8 merged reps (أَجْر, بَعْض, ذُو, صالِحَة, عِلْم, قَرْيَة, كِتاب, مُبِين) | 1.0 | 1.0 | 0.0 (former items all resolve — no broken merges) |
| قَوْل::word | 0.888889 (8/9) | **1.0 (9/9)** | **+0.1111** — the one real merge benefit: merged `saying` training data fixed the misclassified `word` item |
| أَيّ::so which | 0.0 | **1.0 (31/31)** | **+1.0** — the mining fixed it |
| نَذِير::warning | 0.0 | 0.0 (0/11) | 0.0 — unminable (§2) |
| نِساء::wives | 0.0 | 0.0 (0/1) | 0.0 — unminable (§2) |

**Verdict: WIN leg FAILS honestly at 0.0926 < 0.10.** The +0.10 bar needs one
more of: نِساء 1/1 (+0.0833) or نَذِير ≥1/11 (+0.0076 → 0.1002). Both are
unreachable from the data side — the wells are provably dry (§2: full-Quran
enumerations). The bar is not lowered; the shortfall is reported with numbers.
Guardrails pass comfortably; no-regression: zero violations (see §6).

## 5. Tests

- `tests/test_nlp.py`: existing sections A–C untouched (they pin the
  **default** artifact: 115 senses, acc 0.7592 — still true). Added
  **Section D** for `candidate_data_v1/`: manifest validates with checksums
  (real `nlp/artifact.py` validator), `num_senses == 115` (shipped inventory;
  harness merge-check requires all 115), version `1.1.0-data`, smoke tests
  via `MIZAN_NLP_ARTIFACT` env override (أَجْر → only `reward`;
  interrogative أَيّ → `so which` conf > 0.5). Import order follows the
  ruff I001 convention (`nlp` sorts as third-party).
- Full suite + Phase-2 wiring tests (`test_nlp_integration.py`,
  `MIZAN_NLP_NATIVE_WSD` IP-1..IP-4): see §6.

## 6. Verification status

**Frozen harness run** (`python3 -m nlp.eval_phase3` from the repo root —
note: the documented `python3 nlp/eval_phase3.py` invocation **crashes**;
`nlp/types.py` shadows stdlib `types` when the script dir is on `sys.path`,
so `-m` is required; flagged as a repo bug):

```
verdict: FAIL (lift=0.092593 d_acc=0.051037 d_f1=0.009989 regressions=0)
```

| leg | value | bar | result |
|---|---|---|---|
| win_lift (mean target-recall lift, 12 targets) | 0.092593 | +0.10 | ❌ FAIL (shortfall 0.0074) |
| guard_accuracy Δ | +0.051037 | ≥ −0.02 | ✅ |
| guard_macro_f1 Δ | +0.009989 | ≥ −0.02 | ✅ |
| no_regression | 0 violations, 0 warnings | — | ✅ |

- All 9 merged reps: former test items resolve to target at 1.0 — no merge
  broke a previously-correct prediction.
- قَوْل::word 0.888889 → 1.0 (9/9): the merged `saying` training data fixed
  the one item the baseline missed — the only real model gain from the merges.
- أَيّ::so which 0.0 → 1.0 (31/31): the 24 mined interrogatives fixed it.
- نَذِير::warning 0/11, نِساء::wives 0/1: unminable (§2) — the honest
  shortfall. The remaining 0.0074 lift would need one of these; no honest
  data-side move exists (full-Quran enumerations above; no relabeling without
  preregistered evidence; recipe frozen).

---
*Honesty tags: ✅ computed in this run (frozen harness) · 📋 from earlier
(Track-1 manifest, locked baseline) · ❌ could-not-verify: none — every
planned check was executed. Weak JEV confidences disclosed, not rounded up;
shortfalls reported with full-Quran enumerations, not filled.*
