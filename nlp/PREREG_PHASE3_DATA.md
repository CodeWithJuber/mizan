# PREREGISTRATION — Phase 3 Track 2: data-side fixes (merges + targeted mining + retrain)

**FROZEN:** 2026-09-29 ~14:00 +04 (Asia/Dubai), BEFORE any merge, mining, or
retraining. This document freezes the merge list, the mining strategy, the
retraining recipe, and the candidate-artifact contract. Nothing here may be
edited after execution begins; amendments require a new dated section.

**Path note:** repo path is `backend/nlp/` (verified at branch
`feature/mizan-nlp-phase3`).

**Input evidence:** `backend/nlp/DIAGNOSIS.md` (Track-1 diagnosis, committed
2026-09-29). Headline: 9 of 12 zero-recall senses are LABEL NOISE — Q-CSMP v2
"senses" are English-gloss clusters; two cases are provably unlearnable
(feature-identical items with contradictory labels). Tally: (c)×9, (a)×2,
(b)×1.

## 1. Merge list (frozen)

Nine inventory merges. For EACH merge: JEV is consulted with the diagnosis
evidence; a JEV "no" keeps the sense (reported honestly). Merges apply to
**train + dev base records only** — the test split is never relabeled, never
re-split, never touched in any way.

| # | Lemma | Merge (from → to) | Diagnosis cause | Evidence (DIAGNOSIS.md §3) |
|---|---|---|---|---|
| 1 | أَجْر | `payment` → `reward` | (c) label noise | 10/10 test items feature-identical to `reward` train items (26:109:5 ↔ 12:104:5). Provably unlearnable. |
| 2 | بَعْض | `some` → `other` | (c) label noise | miner-flagged `suspect`; test gloss "some **(others)**" (2:76:11) vs sibling "others" (3:34:4). Translation-variant split. |
| 3 | ذُو | `owner` → `possessor` | (c) primary + (a) | English synonyms for one lexeme; plurals labeled both ways. JEV in diagnosis: chose (a) conf 0.44 (weak — recorded, not followed). Collecting plural "owner" examples would teach translator habit, not Arabic sense — don't. |
| 4 | صالِحَة | `good deeds` → `righteous deeds` | (c) label noise | test 4:57:4 feature-identical to `righteous deeds` train items (29:58:4, 42:23:9, 103:3:5). Miner-flagged `suspect` (shared token "deeds"). Provably unlearnable. |
| 5 | عِلْم | `any knowledge` → `knowledge` | (c) label noise | miner-flagged `suspect` (substring); "any" is an English indefinite-article artifact on identical Arabic عِلْمٍ (6:148:27). Not a sense. |
| 6 | قَرْيَة | `cities` → `town` | (c) + (a) | `cities` is the translator's rendering of the Arabic PLURAL ٱلْقُرَىٰ (test 7:96–101) vs singular ٱلْقَرْيَةَ in `town` train. Inventory conflates number with sense. |
| 7 | قَوْل | `saying` → `word` | (c) label noise | JEV conf 0.95 in diagnosis. Same possessive construction (test وَقَوْلِهِمْ 4:155–157 vs sibling قَوْلَهُمْ 3:147); translator word-choice. |
| 8 | كِتاب | `scripture` → `book` | (c) label noise | identical surface ٱلْكِتَٰبِ, same "portion of the Book" construction (test 3:23:8 "the Scripture" vs sibling 4:44:8 "the Book"). Capitalization split. `record` kept — the one plausibly real distinction. |
| 9 | مُبِين | `manifest` → `clear` | (c) label noise | English synonyms for one lexeme; split tracks English collocation ("manifest error/loss/sin" 4:50, 4:112, 4:119) vs predicative "clear" (2:168), not Arabic sense. |

Post-merge inventory: 115 − 9 = 106 senses (before vocative handling, §2).

## 2. Targeted mining (frozen strategy)

**Quran lens (standing constraint):** real Quranic occurrences ONLY. Every
mined item cites its real location (`surah:ayah:word` from the word-level
Quran source — the same `#162 quran_words-3` CSV + Tanzil Uthmani XML the
dataset was built from). If a target cannot be found, the shortfall is
reported honestly — **never fabricate examples, never present synthetic ones
as real.** Mined items are base records only (no synthetic perturbations);
they enter the **train split only**. Test and dev splits are never touched.

| Target | Lemma | Sense label for mined items | Source constraint | Rationale |
|---|---|---|---|---|
| Interrogative أَيّ | أَيّ | `so which` | surahs ∉ {55 (test), 33 (dev)}; interrogative uses only (فَبِأَىِّ-style), NOT يَا أَيُّهَا vocatives | train has 1 unique base item; all 31 test items are surah-55's refrain, unseen in train (a) |
| Plural نُذُر | نَذِير | `warning` | surahs ∉ {54 (test), 35 (dev)} | all 11 test items are plural نُذُر in surah 54, absent from train (a); secondary (c): number conflated with sense — decision: keep `warning` as the plural-warning sense (inventory keeps both `warner`/`warning`; JEV confirms, §6) |
| Possessive نِسَاء | نِساء | `wives` | surahs ∉ {4 (test), 2 (dev)}; possessive-suffix forms across suffix persons (-كُمْ, -هِم, -هُنَّ, …) | distinguishing pattern (possessive suffix) in principle visible to char n-grams but starved: 20 train vs 130 majority (b). Mining is productive and cheap. |

**Vocative pseudo-senses** (`أَيّ:mankind`, `أَيّ:you who believe`): the
diagnosis calls them vocative-addressee artifacts (the label describes the
*next word* in يَٰٓأَيُّهَا, not the lemma). JEV decides drop-vs-replace
(§6): (i) **drop** — remove both senses from the inventory and exclude their
~34 train/dev items from training (they describe the addressee, not a sense
of أَيّ); or (ii) **replace** — merge both into one `vocative` sense
(يَا أَيُّهَا is a real grammatical function of أَيّ; the artifact is only
the addressee split). If JEV picks drop, the items are excluded, not
relabeled as interrogative (that would be fresh label noise).

**Labeling honesty:** mined items get `label_source: "targeted-mining"`
(not `keyword-rule`), with `evidence.tanzil_surface_ok` verified per item.

## 3. Retraining recipe (frozen — verified to reproduce Track-1 exactly)

The shipped `model.joblib` was reverse-engineered and the recipe verified:
retraining from scratch on the UNCHANGED data reproduces the shipped
model's test predictions **627/627** (accuracy 0.7592, matches manifest).
Recipe:

- Data: **train split, base perturbation only** (4691 base train items).
  Plus mined items (train split, base perturbation) — from the SAME
  `qcsmp_v2.jsonl` with merged labels, or appended records in identical
  schema.
- Per lemma: `DictVectorizer()` (sort=True default) fit on training feature
  dicts; `LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000,
  defaults)` on the vectorized features; labels = sorted unique senses in
  the lemma's (merged) training data.
- Feature extractor: frozen `_features` from `backend/nlp/wsd.py`
  (variant "a" only — the primary model; variant "b" retrained identically
  for contract completeness).
- Seeds: lbfgs/DictVectorizer deterministic; no randomness.

## 4. Candidate artifact (frozen contract)

- Path: `backend/nlp/artifacts/candidate_data_v1/` — `model.joblib` +
  `manifest.json` (schema v1, sha256-pinned, Apache-2.0) +
  `sense_inventory.json`. **Never overwrites `artifacts/default/`.**
- `manifest.json`: `version` "1.1.0-data", `variant` "a (surface+context;
  PRIMARY)", `num_lemmas` 48, `num_senses` = merged count, honest
  `eval_accuracy`/`eval_macro_f1` computed on the frozen 627-item test set
  (reported BOTH against frozen 115-sense labels AND against
  merge-remapped gold labels — the latter is the corrected label space;
  the former shows the stale-label cost plainly).
- Bundle contract identical to `default/`:
  `models.model_a_surface_ctx.per_lemma[lemma] = {vec, clf, labels}`
  (+ variant b). Loadable by the unchanged `nlp/wsd.py` loader.

## 5. Test updates (frozen)

- `tests/test_nlp.py`: update inventory-count assertions to the merged
  inventory (115 → post-merge count). Full test suite must be green.
- Phase-2 agent-loop wiring (IP-1..IP-4, `MIZAN_NLP_NATIVE_WSD`): run its
  tests too; the new sense space must not break the loop.

## 6. JEV decision log (filled during execution)

All calls `jev-ask` type `choice`, model `jev-1.13.0`, 2026-09-29 ~14:05–14:15 +04.
Weak confidences (< 0.5) disclosed, not rounded up.

| # | question | decision | conf |
|---|---|---|---|
| M1 | merge أَجْر:payment → reward | **merge** | 0.52 — weak, disclosed |
| M2 | merge بَعْض:some → other | **merge** | 0.77 |
| M3 | merge ذُو:owner → possessor | **merge** | 0.94 |
| M4 | merge صالِحَة:good deeds → righteous deeds | **merge** | 0.85 |
| M5 | merge عِلْم:any knowledge → knowledge | **merge** | 0.49 — weak, disclosed |
| M6 | merge قَرْيَة:cities → town | **merge** | 0.69 (first call returned an unparseable decision string; re-asked with clean ASCII options → clean "yes") |
| M7 | merge قَوْل:saying → word | **merge** | 0.61 |
| M8 | merge كِتاب:scripture → book | **merge** | 0.97 |
| M9 | merge مُبِين:manifest → clear | **merge** | 0.95 |
| S1 | vocative pseudo-senses (أَيّ:mankind, you who believe): drop vs merge-to-`vocative` vs keep | **merge_vocative** | 0.80 |
| S2 | mining strategy (composite) | **reject** | 0.25 — too weak to be action-guiding; re-asked as three narrow questions |
| S2a | mine 24 gloss-verified interrogative أَيّ items → `so which` (train-only, base-only, real citations) | **reject** | 0.46 — weak; no reason given. Proceeding per the preregistered evidence-based plan (DIAGNOSIS.md explicitly prescribes interrogative-أَيّ mining for the starvation case); the weak reject is disclosed here and in TRACK2_REPORT.md |
| S2b | نَذِير plural نُذُر mining: 0 real occurrences outside test surah 54 → skip | **skip** | 0.81 |
| S2c | نِساء possessive mining: 0 new real occurrences (all 12 already in dataset) → skip, report honestly | **skip / report honestly** | 0.38 — weak, but the decision is forced by the verified zero count, not by JEV |

No merge received a "no": all 9 merges executed.

## 7. Quran lens (standing constraints)

- *tabayyun* (verify before acting): merges preregistered with evidence;
  training recipe verified 627/627 before retraining on new data; test
  split untouched.
- *lā taqfu* (no claim without knowledge): no invented occurrences; mined
  items carry real addresses; shortfalls reported, not filled; JEV weak
  confidences disclosed.
- *amāna* (stewardship): candidate never overwrites `default/`; sha-pinned
  manifest; unpickling only after manifest validation (unchanged loader).

## 8. Honesty bar

Every number tagged ✅ verified (computed in this run) / 📋 from-earlier /
❌ could-not-verify. `eval_accuracy` in the candidate manifest is computed
by the frozen harness recipe on the frozen test split — never tuned.

---
*End of preregistration. Execution (JEV log, mining counts, retrain
numbers) below this line is post-freeze.*

---

## ADDENDUM A1 — post-freeze changes (2026-09-29 ~15:00 +04, Juber's directive)

The parent orchestrator froze Track-4's **Amendment A1** after this prereg was
written. The following deviations from the preregistered plan were made to
conform to the frozen scoring protocol; each is disclosed, none is hidden.

**A1.1 — Frozen 9-merge ontology (106 senses), not 105.** The prereg planned
10 label changes (M1–M9 + the JEV vocative merge S1 → 105 senses). Amendment A1
freezes exactly the 9 merges in `nlp/SENSE_MERGES_PHASE3.json` → **106 senses**.
The vocative merge (JEV S1, conf 0.80) is **reverted**: the harness fail-closes
on any label space other than the frozen 106 (`load_merges` validates the map
against the shipped inventory; bundle labels must lie within it). The shipped
`sense_inventory.json` is therefore the **original 115-sense inventory**
(byte-identical to the baseline's), and the bundle predicts the 106 frozen
labels. Score-neutral: both vocative senses have n_test = 0.

**A1.2 — Scoring in post-merge space.** WIN = mean recall lift over the 12
targets, both sides scored in post-merge space; bar +0.10 (max achievable
+0.25, since 26/26 former test items already resolve to merge targets at
baseline). Guardrails: accuracy ≥ −0.02 vs 0.8022, macro-F1 ≥ −0.02 vs 0.6158.

**A1.3 — Mining shortfalls proven by full-Quran enumeration (not estimates).**
- نَذِير: 15 plural-pattern words in the Quran; 14 are lemma نَذِير — 3 in
  train (10:101, 46:21, 53:56, all `warner`) + 11 in test surah 54 (all
  `warning`) + 1 نُذُورَهُمْ "their vows" (22:29, different lemma). The
  `warning` sense of the plural exists **only in surah 54**. Train's 2
  `warning` examples are singular. 10:101 وَٱلنُّذُرُ adjudicated against
  classical tafsir (Ibn Kathir/Tabari: النُّذُرُ = الرسل) → label kept;
  no relabeling performed (would be metric gaming).
- نِساء: 15 possessive-suffix words in the Quran — 4 dev (surah 2), 2 test
  (surah 4), 9 train — **all already in the dataset**. 0 minable.

**A1.4 — Packaging move.** The user moved `backend/nlp/` → top-level `nlp/`
on main (commit 13504471); the branch was rebased onto new main (`a7d24f97`).
All Track-2 paths are now `nlp/...`: candidate at
`nlp/artifacts/candidate_data_v1/`, docs at `nlp/`.

**A1.5 — Honest verdict (frozen harness, authoritative):**
`FAIL (lift=0.092593 d_acc=0.051037 d_f1=0.009989 regressions=0)`.
WIN leg fails by 0.0074 (needs نِساء 1/1 or نَذِير ≥1/11; both proven
unreachable data-side — §A1.3). Guardrails and no-regression pass.
The bar is not lowered; the shortfall is reported with numbers.
