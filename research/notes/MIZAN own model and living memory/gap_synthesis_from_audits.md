# Coordinator's gap synthesis (29 Oct 2026) — where MIZAN falls short of the owner's goal today

Derived only from the three code audits and the two experiments in this folder. Each gap cites its evidence file. The owner's goal: MIZAN's own NLP and own small model carry real-time learning; the hosted model is a teacher that teaches once; a Quranic root-space meaning space across Hinglish/Urdu/Hindi/English/Arabic; a full real-time, human-like, neuroscience-grounded memory — all on 2 vCPU / 2 GB with no GPU.

## A. The hosted model still does the thinking where it matters most

| # | Gap | Evidence |
|---|---|---|
| A1 | Every request Fahm does not place goes to the `_language_only` path: knowledge, reasoning and wording all by the base model in one call; and plain conversation returns **before `_learn`**, so ordinary chat teaches MIZAN nothing (no Qasd, Ta'allum, memory or wording is learned from it). | audit_base_model_dependence §2; audit_memory_and_learning §2 |
| A2 | Lisan tasks that still need the model on every occurrence: `express`, `answer_from_sources`, `plan_steps` (when no Ta'allum hit), `fill_arguments`, `write_file`/`fix_files`/`edit_files`, `browse_steps`, `form_checks`/`conform`, `cross_check`. Only Hifz, Ta'allum and `qasd.learn` convert past model work into zero-call futures; `cross_check`, `browse_steps`, `form_checks`, `conform` are never even credited, so nothing learns from them. | audit_base_model_dependence §1, §4 |
| A3 | The "teacher that teaches once" loop does not exist: a base-model answer is checked (Sidq/Isnad/Ahl al-Dhikr) and shown, but what it taught (a fact, a wording, a mapping) is kept only in narrow cases (Ahl al-Dhikr `ilm` sentences with two witnesses, per user). There is no store of teacher-given facts with provenance that MIZAN answers from next time, and no decision rule for "I know this well enough to answer alone". | audit_base_model_dependence §4 |
| A4 | Nothing measures progress toward the goal: no "share of answers with zero hosted-model calls", `orchestration.language_model_calls` is not persisted, Iqtisad rows carry no request or task id, Imtihan does not keep `lisan_calls`. The production baseline could not even be measured (E3). | audit_base_model_dependence §3; experiments E3 |
| A5 | Training-data capture is unusable for the goal: Tadbir-verified work is never captured (`capture_eligible` false), captures carry no verification outcome, there is no consent or licence filter, nothing consumes the data, and the repository's CI policy forbids machine-authored training targets outright. | audit_base_model_dependence §5; audit_ruh_model_state §5 |

## B. Ruh is not yet a language model MIZAN can use

| # | Gap | Evidence |
|---|---|---|
| B1 | Bayan v1 has **58 roots**; English, Urdu, Hinglish and most Arabic decode to UNK; negation words are erased as stopwords; the Q28 fallback is dead code. | audit_ruh_model_state §1 |
| B2 | Bayan v2 is a **byte-level** tokenizer: the (root, pattern) factorisation is unused, so "root-space" exists in name only; Arabic/Urdu cost 2 bytes per character. | audit_ruh_model_state §1, §5 |
| B3 | No checkpoint can hold a conversation (v2 full-size run: incoherent, 0/3 negation probes); data is ~0.5% of a compute-optimal budget; **no Urdu, Hindi or Hinglish data anywhere**; `full_real.yaml` and `/api/ruh/data-stats` list non-existent datasets. | audit_ruh_model_state §2 |
| B4 | The 46M default is too slow for the production CPU (≈82 ms per generated token at a 64-token context without a KV cache; ~90 s for a 300-byte reply); there is no KV cache; the provider clips prompts to the last 64 bytes in a common configuration. | audit_ruh_model_state §4–5; experiments E1 |
| B5 | What the CPU can afford: a 5–15M-parameter model reaches 20 tokens/parameter in days to two weeks of 25%-duty training; incremental updates cost 0.3–1 s per 1k tokens. Anything ≥100M is out of reach without a GPU. | experiments E1 |
| B6 | Ruh's useful, tested pieces are the morphology/root analyzer (47% root accuracy), the confidence head, the tajwid rules engine, pinned Quran provenance and the review/abstention gates — not the language model. | audit_ruh_model_state §3, §6 |

## C. The root-space "universal meaning space" is unproven and, as an inventory, too small

| # | Gap | Evidence |
|---|---|---|
| C1 | The Quranic corpus has 1,651 roots and 14,835 surface forms. In everyday **Arabic** only 43% of tokens are Quran-attested forms; in **Urdu** 36.6% of tokens contain letters Arabic lacks and only 10.5% are exact Quranic forms. A Quranic root inventory cannot be the vocabulary of a universal model; roots can be one feature channel. | experiments E2 |
| C2 | No cross-lingual lexicon, no concept layer, no alignment between Urdu/Hindi/English words and roots or concepts exists in code; the English "concept map" has 117 entries. | audit_ruh_model_state §1 |
| C3 | No evaluation exists for understanding in Urdu/Hinglish/Hindi at any model size (MASSIVE intents, XNLI, LinCE are not wired). | audit_ruh_model_state §3 |

## D. Memory is one explicit-note loop, not a living memory

| # | Gap | Evidence |
|---|---|---|
| D1 | No automatic episodic encoding: `memories` rows need an explicit "remember"; the only automatic episodic store (QCA Lawh) is RAM, unbounded, lost on restart. | audit_memory_and_learning §1, §6 |
| D2 | No consolidation: no Nawm, no episodic→semantic promotion, no supersession (`t_valid_from`/`superseded_by` absent), no content reconsolidation on retrieval, no re-verification queue. The hourly job touches only the global DB (admins); private users' memory is never consolidated or pruned. | audit_memory_and_learning §2, §4, §6 |
| D3 | Recall is non-selective and self-reinforcing: SQL `LIKE` prefilter ordered by importance, top-5 always reinforced with a Good grade (rich-get-richer); the Again/Hard grades (restatement, correction) are never produced; FSRS-6 runs on default parameters never fitted to MIZAN; forgetting uses a different model (ACT-R) than ranking and is a hard delete. | audit_memory_and_learning §3, §6 |
| D4 | No working-memory model (token budget and fixed top-k only), no interference/fan effect, no surprise-based episode boundaries, no temporal context, no prioritised replay (need × gain). | audit_memory_and_learning §6 |
| D5 | Four "neuroscience" modules are dead or decorative (LivingMemory, Manam dream engine, LawhMahfuz+quaternary, mem0, the Miller-7 working memory) and the KnowledgeGraph relationship loop is broken by an attribute typo; the architecture docs and `/api/ruh/architecture` overstate what runs. | audit_memory_and_learning §1; audit_ruh_model_state §4 |
| D6 | Privacy gaps against the owner's own principles: `stateless.bind` does not gate FSRS/Masalik/KG/task_history writes; `cross_chat_recall: off` is bypassed by KG, Lawh and Masalik; Mahw misses Tajriba lessons, Lawh/dream/LivingMemory RAM, Sijill and harness signatures; Daftar does not list the Qasd overlay, Ilm facts, Masalik, KG, hikmah or task_history. | audit_memory_and_learning §5 |
| D7 | Many fixed constants where the project's principle is "no hardcoded rules" (Masalik LTP 0.02 and half-life, forget-below 0.05, 7-day cutoff, overlap gates 0.6/0.8, top-5, pyramid certainty constants, Beta priors and forgetting factors). | audit_memory_and_learning §3 |
| D8 | New users start cold on everything learned (Qasd overlay, Majlis, Ilm, host trust): nothing is shared across users with privacy accounting (D6 of the earlier report unbuilt). | audit_memory_and_learning §5 |

## E. What already works and must be kept (the base to build on)

- Verified-outcome-gated learning (Ta'allum, Hifz, Tajriba, qasd.learn, Majlis) — real synaptic-tagging-like gating, per user, no model.
- Tamyiz/Lughah/Qasd: fitted, principled, fast on CPU.
- Ahl al-Dhikr with local NLI and two-witness facts; Sidq/Isnad truth gates; Tathabbut cross-checks; Tajdid's anytime-valid e-value gate.
- FSRS-6 strength per memory (needs grades and fitting), Masalik pathways, Mahw and Daftar.
- Ruh's morphology analyzer, confidence head, tajwid engine, provenance-pinned Quran data.
