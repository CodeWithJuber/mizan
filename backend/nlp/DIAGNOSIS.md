# Diagnosis — mizan.nlp Phase 3, Track 1: the 12 zero-recall senses

**Artifact:** `backend/nlp/artifacts/default/` v1.0.0 (mizan-sense-wsd), per-lemma
sklearn LogisticRegression, variant 'a'. **Read-only diagnosis**: no retraining,
no artifact modification, no relabeling (verified: branch diff vs main touches
only the two new docs).

**Preregistration:** `backend/nlp/DIAGNOSIS_PREREG.md` (committed before any
test-set analysis). Claim tags: ✅ verified by this run / 📋 from earlier
(Track-1 reports, manifest, build scripts) / ❌ could not verify.

## 1. Reproduction ✅

Loaded `model.joblib` (sha256 `019f0795…d8c26` matches manifest ✅) with the
frozen `_features` extractor verbatim from `backend/nlp/wsd.py`, ran inference
on the Phase-1 eval set (`split=="test"`, `perturbation=="base"`, n=627 —
matches manifest `eval_n` ✅):

| Metric | Track-1 (manifest) | Reproduced here | Match |
|---|---|---|---|
| Accuracy | 0.7592 | **0.7592** (n=627) | ✅ exact |
| Evaluated senses (n_test>0) | 88 | **88** | ✅ exact |
| Zero-recall senses | 12 | **12** (same set — see §3) | ✅ exact |
| Macro-F1 | 0.5471 | 0.5471 | ✅ exact, **with a caveat** |

**Macro-F1 caveat** ✅: Track 1 computed macro-F1 over **all 115 inventory
senses** (`f1_score(labels=<all 115>, average='macro', zero_division=0)` —
verified by recomputation). 19 senses have no test items and were never
predicted (F1=0 each), and 8 more were predicted but never true in test.
Over the 88 truly evaluated senses the macro-F1 is 0.6554. The 0.5471 is not
wrong, but it conflates "unevaluated" with "failed".

**Split honesty note** ✅: the holdout is *per-lemma whole-surah* (build script
`build_qcsmp_v2.py`: each lemma's largest surah → test, 2nd → dev, rest →
train). Train records do exist from the 15 test surahs, but they belong to
*other* lemmas — for every lemma, its test surah is disjoint from its train
surahs. No leakage for the per-lemma classifiers. Side effect: a sense
concentrated in a lemma's test surah is starved in train by construction
(this bit نَذِير:warning and أَيّ:so which).

## 2. Headline pattern

**All 12 zero-recall senses were confused into exactly ONE sibling sense,
100% of their test items** (e.g. 31/31, 11/11, 10/10). The classifier never
"spread" errors — it assigned the whole sense to the majority sibling. 10 of
the 12 have n_test ≤ 4 (fragile zeros); the three that move macro-F1 are
أَيّ:so which (31), نَذِير:warning (11), أَجْر:payment (10).

**Root pattern across 9 of 12:** the "senses" are **English-gloss clusters**,
not Arabic lexical senses. Q-CSMP v2's new-lemma senses were auto-mined by
grouping normalized English translations (`mine_new_lemmas` in
`build_qcsmp_v2.py`); the miner's own `flag_quality` heuristic marks groups
"suspect" when they share content tokens / are substrings / share crude stems
— i.e. translation variants. 28,726/28,841 records are `keyword-rule` labeled;
only 115 are audited (23 of 5,769 base items). The classifier is being asked
to reproduce *translator word choice* from Arabic char n-grams — where the
Arabic side is identical, no feature set can separate the labels.

## 3. Per-sense table

Columns: n_train = all train records (base = base-perturbation only);
n_test = base test items (the eval set); confusions = predicted sense (count).

| # | Sense | n_train (base) | n_test | Predicted as | Cause | Fix |
|---|---|---|---|---|---|---|
| 1 | `qcsmp2:أَجْر:payment` | 35 (7) | 10 | reward (10/10) | **(c) label noise** ✅ — 10/10 test items are **feature-identical** to `reward` train items (e.g. test 26:109:5 ↔ train 12:104:5; 26:109:7 ↔ 10:72:8). Identical inputs, contradictory labels: unlearnable by any model on these features. | **data-side**: merge `payment`→`reward` (inventory fix) |
| 2 | `qcsmp2:أَيّ:so which` | 5 (1) | 31 | mankind (31/31) | **(a) data starvation** ✅ — the 5 train records are **one unique item** (6:81:16 × 5 perturbations). All 31 test items are surah 55's refrain فَبِأَىِّ, a construction never seen in train. Secondary (c): sibling "senses" `mankind`/`you who believe` are vocative-addressee artifacts (all train items are يَٰٓأَيُّهَا "O mankind / O you who believe") — the label describes the *next word*, not the lemma. | **data-side**: mine interrogative أَيّ uses; inventory: drop/replace the vocative pseudo-senses |
| 3 | `qcsmp2:بَعْض:some` | 80 (16) | 1 | other (1/1) | **(c) label noise** ✅ — miner-flagged `suspect`; the test item's own gloss is "some **(others)**" (2:76:11 بَعْضٍ) vs sibling "others" (3:34:4 بَعْضٍ). Translation-variant split. | **data-side**: merge `some`→`other`, or human-audit the 16 base items |
| 4 | `qcsmp2:ذُو:owner` | 55 (11) | 2 | possessor (2/2) | **(c) primary + (a) contributing** — `owner`/`possessor` are English synonyms for one Arabic lexeme (ذُو/أُولُو); plural forms appear labeled *both* ways (train `possessor` has لِّأُو۟لِى/أُو۟لُوا۟ "possessors"; test `owner` items 3:13:28, 3:18:9 are the same plurals glossed "owners"). Contributing (a): zero plural `owner` train items, so the classifier learned plural→possessor. JEV consulted: chose (a), conf **0.44** (weak — recorded, not followed; the synonymy evidence decides). | **data-side**: merge `owner`→`possessor` (inventory fix). Collecting plural "owner" examples would teach translator habit, not Arabic sense — don't. |
| 5 | `qcsmp2:صالِحَة:good deeds` | 45 (9) | 1 | righteous deeds (1/1) | **(c) label noise** ✅ — test item 4:57:4 ٱلصَّٰلِحَٰتِ is feature-identical to `righteous deeds` train items (29:58:4, 42:23:9, 103:3:5). Miner-flagged `suspect` (shared token "deeds"). | **data-side**: merge `good deeds`→`righteous deeds` |
| 6 | `qcsmp2:عِلْم:any knowledge` | 40 (8) | 1 | knowledge (1/1) | **(c) label noise** ✅ — miner-flagged `suspect` (substring); "any" is an English indefinite-article artifact on identical Arabic عِلْمٍ (6:148:27). Not a sense. | **data-side**: merge `any knowledge`→`knowledge` |
| 7 | `qcsmp2:قَرْيَة:cities` | 10 (2) | 4 | town (4/4) | **(c) + (a)** ✅ — `cities` is not a sense of قَرْيَة ("town/village"); it is the translator's rendering of the Arabic **plural** ٱلْقُرَىٰ (test 7:96–101) vs singular ٱلْقَرْيَةَ in `town` train. Inventory conflates number with sense. Also (a): n_train=10 (2 base). | **data-side**: merge `cities`→`town` (inventory fix) |
| 8 | `qcsmp2:قَوْل:saying` | 40 (8) | 3 | word (3/3) | **(c) label noise** ✅ — JEV conf **0.95**. Same lexeme + same possessive construction (test وَقَوْلِهِمْ "and their saying" 4:155–157 vs sibling قَوْلَهُمْ "their words" 3:147); the split is translator word-choice. Miner's `strong` flag is a heuristic gap (it checks token overlap, not synonymy). | **data-side**: merge `saying`→`word` (or human-audit if a discourse sense was intended) |
| 9 | `qcsmp2:كِتاب:scripture` | 95 (19) | 1 | book (1/1) | **(c) label noise** ✅ — identical surface ٱلْكِتَٰبِ in the same "portion of the Book" construction (test 3:23:8 "the Scripture" vs sibling 4:44:8 "the Book"). Capitalization/word-choice split. | **data-side**: merge `scripture`→`book` (keep `record` — the one plausibly real distinction) |
| 10 | `qcsmp2:مُبِين:manifest` | 50 (10) | 3 | clear (3/3) | **(c) label noise** ✅ — `manifest`/`clear` are English synonyms for one Arabic lexeme; the split tracks English collocation ("manifest error/loss/sin": 4:50, 4:112, 4:119 مُّبِينًا) vs predicative "clear" (2:168 مُّبِينٌ), not Arabic sense. | **data-side**: merge `manifest`→`clear` |
| 11 | `qcsmp2:نَذِير:warning` | 10 (2) | 11 | warner (11/11) | **(a) primary + (c) secondary** ✅ — 2 unique base train items (67:17:12, 74:36:1); all 11 test items are the plural نُذُر in surah 54 (the lemma's test surah), a usage absent from train. Secondary (c): inventory conflates plural morphology with sense; miner-flagged `suspect`. | **data-side**: mine plural نُذُر occurrences; inventory decision needed: is plural-usage a sense or a number feature? |
| 12 | `qcsmp2:نِساء:wives` | 20 (4) | 1 | women (1/1) | **(b) feature blindness** — JEV conf **0.40** (weak, but directionally aligned). The distinguishing pattern (possessive suffix: train has -هِم "their"/vocative; test 4:23:19 نِسَآئِكُمْ has unseen -كُم "your") is in principle visible to char n-grams, but 20 examples vs 130 majority never let the logreg weight the suffix abstraction. The one genuinely learnable distinction in the set. | **data-side** (primary): mine possessive نِسَاء across suffix persons (productive, cheap). **model-side** (alternative): class weights, or a morph `has-possessive-suffix` feature (variant 'b' family) |

**Cause tally:** (c) label noise 9 (7 pure, 2 mixed) · (a) data starvation 2 (1 pure, 1 mixed) · (b) feature blindness 1.
No sense classified leave-alone: every fix is a cheap inventory merge or targeted mining pass.

**Precision note:** all 12 senses have fp=0 (never predicted), so precision is n/a — the damage is pure recall, concentrated in macro-F1's tail.

## 4. Cross-cutting findings

1. **The sense inventory is the main defect, not the model.** 9/12 zeros trace to
   English-gloss-cluster "senses" (synonym pairs: payment/reward, good/righteous
   deeds, manifest/clear, saying/word, scripture/book, owner/possessor, some/other,
   knowledge/any-knowledge; number conflated with sense: cities, warning). The
   logistic regression is correctly refusing to hallucinate distinctions the
   Arabic side doesn't contain — two cases (أَجْر, صالِحَة) are *provably*
   unlearnable: identical feature vectors, contradictory labels.
2. **Per-lemma surah holdout amplifies starvation.** Senses concentrated in a
   lemma's test surah (أَيّ's surah-55 refrain, نَذِير's surah-54 plurals) get
   ~zero train support by construction. Future mining should stratify *senses*,
   not just lemmas, across splits — or hold out verses, not surahs, for rare senses.
3. **Perturbation multiplicity inflates n_train.** أَيّ:so-which's "5 train items"
   are one address × 5 perturbations. Effective-sample reporting (unique base
   items) should be standard in future eval reports.
4. **Miner `suspect` flags were predictive.** 4 of the 12 were miner-flagged
   `suspect` (بَعْض, صالِحَة, عِلْم, نَذِير); the heuristic missed synonym pairs
   with no token overlap (its known gap — see #8, #9). The P2 expert-adjudication
   gate the build script defers to is exactly where these 12 belong.

## 5. Recommended fix order (Phase-3 Track-1 follow-up)

1. **Inventory merges** (data-side, cheapest, fixes 8–9 senses): merge the synonym
   pairs listed above; drop the pseudo-senses (`any knowledge`, vocative أَيّ
   senses, `cities`). No model change needed — re-eval only.
2. **Targeted mining** (data-side): interrogative أَيّ, plural نُذُر, possessive
   نِسَاء across suffix persons. Fixes the 3 starvation/blindness senses.
3. **Model-side** (only if #2 under-delivers for نِساء:wives): class-balanced
   training or a possessive-suffix morph feature (variant-'b' family).
4. **Eval hygiene**: report effective (unique-base) n_train; compute macro-F1
   over evaluated senses separately from the 115-sense inventory figure.

---
*Diagnosis run 2026-09-29. JEV consulted on 3 borderline classifications
(§3 rows 4, 8, 12); confidences recorded inline. No training code, artifact, or
label was modified or created — branch diff vs main contains only
DIAGNOSIS_PREREG.md and this file.*
