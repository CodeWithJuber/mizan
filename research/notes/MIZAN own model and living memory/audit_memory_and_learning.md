# Code audit (29 Oct 2026, read-only): MIZAN memory and learning — what exists, what is wired into chat, what is dead

Produced by a read-only code exploration of the repository at commit d400589 (branch ccr-3bdd339e-ipygcl, base main 10c0953). Paths are relative to `/backend/`.

**Bottom line:** MIZAN has one real, persistent, self-updating memory loop. It covers explicit notes (Dhikr with Tadhkir/FSRS), the Masalik pathway graph, and per-user learning from verified work (Ta'allum, Qasd, Hifz, Tajriba, Majlis, Ilm). Around that loop sit four "neuroscience" modules (LivingMemory, the Manam dream engine, LawhMahfuz with quaternary, mem0) that are write-only, RAM-only, empty or switched off.

Nothing captures episodic memories from ordinary chat. There is no consolidation, supersession or differential privacy. The hourly maintenance never touches non-admin users' memory.

## 1. Inventory of memory stores

**Paths.** Non-admin users get `$MIZAN_DATA_DIR/private/<sha(user)>/memory.db` (`api/main.py:1568-1581`), and their private agents use it (`main.py:1584-1603`). Admins share the global `memory` and the template agents (`main.py:3308-3313`, `1613-1615`). Chat messages and running summaries always live in the **global** DB, filtered by owner (`main.py:1670`, `dhikr.py:475-483`). Learned state goes to the agent's `AdaptiveStateStore`, which is the same SQLite file as that agent's memory (`agents/base.py:1247-1255`).

| Store | Written when | Scope | Read back into the turn? | Status |
|---|---|---|---|---|
| Dhikr `memories` table + Tadhkir columns (`dhikr.py:372-496`) | Only explicit writes: the "remember" intent (`tadbir/engine.py:3042-3069`), `POST /api/memory/store` (`main.py:3352`), Daftar import (`daftar.py:346`), knowledge ingest into the **global** DB (`main.py:4430`, `4486`). Nothing from ordinary chat. | per-user (global for admin/ingest) | Yes. MemoryPyramid in the system prompt (`base.py:2630-2645`), plus `context_manager.inject_memory` (`base.py:1217-1229`). The second path is admin only: private agents are built without `context_manager` (`main.py:1589-1599` vs `168`). | **LIVE** |
| Masalik graph, persisted to `masalik_network.json` (`dhikr.py:286-294`) | Every `remember` (`dhikr.py:558`), every model answer's task telemetry (`base.py:3923-3928`), knowledge ingest | per-user | Yes. Pyramid layer 1 adds "Associated concept: X" (`memory_pyramid.py:114-131`). Recall also strengthens pathways (`dhikr.py:654`, `masalik.py:612-617`). | **LIVE** |
| Running summary `session_summaries` (`context_engine.py:285-306`) | Inline, before the answer, once a session exceeds its budget | global DB, per session | Yes, as the first history message (`context_engine.py:312-315`) | **LIVE** |
| Cross-chat recall over `agent_messages` (`dhikr.py:1240-1286`) | n/a: reads saved messages | per-owner | Yes, `conversation_memory` (`main.py:1692-1705`, `base.py:2829-2836`). Last 200 user messages, at most 5, `about()` rule. | **LIVE** |
| `hikmah` table (`base.py:3969-3977`) | After every model answer (`_tafakkur`) | per-user | Yes, "Learned Patterns" in the prompt (`base.py:2587-2600`) | **DECORATIVE**: the content is only "Response delivered for 'coding' in N ms; outcome not verified" (`base.py:3953-3956`) |
| `task_history` (`base.py:3911-3918`) | After every model answer | per-user | Only through the Mahw Masalik rebuild | write-mostly |
| KnowledgeGraph `kg_entities` (`knowledge_graph.py:37-60`) | `add_entity(task[:100])` after a successful model answer (`base.py:3559`) | per-user | Yes: `query_entity` in the prompt (`base.py:2649-2670`) and pyramid layer 4 | **Half-broken.** The relationship loop reads `self.qca.lawh._tiers` (`base.py:3565`), but `LawhMemory` defines `tiers` (`qca/engine.py:651`). The AttributeError is swallowed (`base.py:3574`), so no relationships are ever written. |
| QCA `LawhMemory` tier 3 (RAM, `qca/engine.py:630-740`) | `TOOL:` and `RESULT:` entries after each tool call and each answer (`base.py:1679-1685`, `1796-1802`) | per agent instance, RAM, unbounded | Yes, `[Lawh Memory: …]` (`base.py:1206-1211`) | **LIVE but ungated:** the only automatic episodic memory, lost on restart (details in §5) |
| Ta'allum / Qasd / Hifz / Tajriba / Majlis / Ilm keys in `adaptive_state` | Tadbir after a verified outcome (`engine.py:242`, `517-538`, `918-1092`, `935-982`); Ahl al-Dhikr after an answer (`ahl_dhikr.py:431-478`) | per-user (keys hashed by user) | Yes: wording maps to an intent (`engine.py:507`), program reuse (`918`), repair lessons go to Lisan (`935-937`), corroborated (sahih) facts go to the prompt (`base.py:3488-3490`, `2837-2844`) | **LIVE** |
| `harness.db`: Tajdid + Wazn (`tajdid.py:76-86`, `wazn.py:22`) | After each Lisan code task (`engine.py:447-461`) | **global** | Yes: instruction variant, model choice | **LIVE** |
| VectorStore (`vector_store.py`) | On `remember`, only if `MIZAN_VECTOR_URL` is set (`dhikr.py:320-333`, `566-569`) | per-user collection | pyramid layer 3 | off by default |
| `memory_pyramid.py` | n/a | n/a | It *is* the live read path (`dhikr.py:763-770`) | **LIVE** |
| LawhMahfuz + `quaternary.py` | `store_immutable` (`lawh_mahfuz.py:150`) has **no caller**; quaternary is only used from there | n/a | pyramid layer 5 always returns nothing | **DEAD** |
| LivingMemory (`living_memory.py`) | `process_input` after each answer (`base.py:3659`). Built with no backing stores (`base.py:556`), so RAM only. | per agent | `recall()` is never called. `run_maintenance` runs only on template agents (`main.py:348-357`). | **DEAD / decorative** |
| Manam dream engine (`core/dream_engine.py`) | `add_memory` after each answer (`base.py:3643`) | RAM | `run_consolidation` runs hourly on template agents only; its `DreamSession` result is discarded (`dream_engine.py:277-285`) | **DECORATIVE** |
| mem0 (`mem0_store.py`) | `add_turn_async` (`:295`) has **no caller** | n/a | `recall_block_sync` (`base.py:2809-2819`) is a no-op unless `MEM0_ENABLED` (default false, `:42-47`) | **DEAD** |
| `DhikrMemorySystem.working_memory` (cap 7, `dhikr.py:350-351`, `619-627`) | `remember` with importance above 0.6 | RAM | never read (only cleared by Daftar, `daftar.py:258`) | **DEAD** |
| Sijill (`sijill.py:22-24`) | every `trace.event("learn")` (`trace.py:105-107`) | RAM, 200 per user | UI only | display only |

## 2. Real-time learning per turn, and the offline jobs

**Before the answer, inline:**
- running-summary fold, a model call bounded by `provider_limits().total` (`context_engine.py:364`);
- cross-chat recall;
- Qasd posterior with the chat as a Dirichlet prior (`qasd.py:151-200`);
- Ta'allum and Hifz recall;
- Ilm `evidence_for`;
- pyramid recall.

Recall writes as it reads. Every recalled note gets an FSRS **Good** review and `access_count+1` (`dhikr.py:720-749`), and Masalik pathways strengthen by 0.02 per hop. This happens once via the pyramid and again via `context_manager` for admins.

**Tadbir path (recipe intents), no model call:**
- `taallum.learn`/`reweigh` and `qasd.learn` (`engine.py:517-538`);
- `majlis.record` (`:435`);
- `hifz.keep`/`record`/`drop`/`mark_checked` (`:1000-1092`);
- `tajriba.learn`/`credit` (`:947-982`);
- `tajdid.record` + `wazn.record` (`:452-453`).

These run synchronously at `engine.py:242`, before the last chunk streams (`:253`). The only background task is `tajdid.evolve`, a Lisan call via `create_task` (`:458-461`). Plain conversation (`converse`) returns at `engine.py:235-237` **before `_learn`**, so ordinary chat teaches Tadbir nothing.

**Model path, after the answer, all inline in `execute()`:**
- tool reliability Beta (`base.py:1257-1265`);
- hikmah, `task_history` and Masalik encode;
- the KG entity;
- dream and LivingMemory (RAM only);
- then Nazm, the Truth Gate and Ahl al-Dhikr (`base.py:3105-3125`). Ahl al-Dhikr may hold the "done" frame for up to `BUDGET_SECONDS=20` (`ahl_dhikr.py:66`) and writes ilm facts, host trust and source order.

**Latency budget.** There is none for learning writes. Each `AdaptiveStateStore.get/put` opens a blocking SQLite connection on the event loop (`adaptive.py:371-402`). `qasd.learn` re-vectorises up to 400 examples on every learn (`qasd.py:254-257`). The only overall bound is `chat_run_seconds()` (`main.py:2473`).

**Offline jobs:**
- **Hourly `maintain_memory`** (`main.py:334-363`) runs `memory.consolidate()` on the **global DB only**: Masalik tafakkur (co-activation links), nisyan (decay and pruning), and a hard DELETE of memories older than 7 days whose ACT-R weight × importance is below 0.05 (`dhikr.py:855-913`). It then runs dream and LivingMemory upkeep on template agents only. Private memories are consolidated only by a manual `POST /api/memory/consolidate` (`main.py:3363`).
- **Daily Muhasaba** (`main.py:377-395`, `muhasaba.py:190-244`) re-checks arithmetic and Quran/hadith quotes in model answers and posts a correction. It feeds no estimator back: nothing in FSRS, Tajdid or Majlis changes.
- There is **no Nawm job**.

## 3. The mathematics in use

- **FSRS-6** (`tadhkir.py`).
  - Retrievability: `R(t) = (1 + f·t/S)^(−w20)`, with `f = 0.9^(−1/w20) − 1` (`:45-46`, `:97-106`).
  - Parameters are the package's `DEFAULT_PARAMETERS`: global, fitted on others' review data, never on MIZAN's. w20 = 0.1542; initial S (Again/Hard/Good/Easy) = 0.212 / 1.293 / 2.307 / 8.296 days. No optimizer is called.
  - The first grade is a hand rule: thirds of importance map to Hard/Good/Easy (`:60-63`).
  - Every later review is graded **Good**: on recall (`dhikr.py:727`) and when the user repeats a note (`dhikr.py:598-600`).
  - **Again is never used** in live code. That contradicts the module docstring (`tadhkir.py:19`, `:29-30`); `docs/quranic-algorithms.md:39` admits it.
  - `interval_days` is unused.
  - Ranking is `(0.25 + 0.75·BM25norm)·R·(0.5 + 0.5·importance)`, hand weights (`dhikr.py:238-245`).
- **ACT-R.** The optimized-learning form `B = ln(n/(1−d)) − d·ln L`, d = 0.5, with weight `1/(1 + e^{−(B−τ)/s})`, τ = −6, s = 0.5 (`dhikr.py:251-260`, `adaptive.py:276-280`). It is used for legacy rows, pyramid recency and **pruning**, so ranking (FSRS) and forgetting (ACT-R) use different models. The full `actr_activation` sum and `approximate_ages` are unused. By my arithmetic, a never-recalled note at importance 0.5 is deleted after about 2 months, and at 0.8 after about 4 months (global DB only).
- **Beta posteriors** (`adaptive.py:67-129`), all with hand-set priors and forgetting factors:

  | Where | Prior (α, β) | Forgetting | Rule |
  |---|---|---|---|
  | Ta'allum, Hifz, Tajriba | (2, 1) | 0.98 | drop when mean < 0.5 |
  | Majlis | (20, 2) / (10, 4) / (2, 4) by role | 0.98 | Thompson choice |
  | Wazn | (2, 1) | 0.99 | readiness 0.7 (env) |
  | Tajdid | (2, 1) | 1.0 | e-value gate |
  | Ahl al-Dhikr source order | (1, 1) | 0.99 | Thompson order |
  | Ahl al-Dhikr host trust | (2, 1) | 1.0 | log-odds `Σ s_h·p_h·logit(t̄_h)` (`ahl_dhikr.py:545-557`) |
  | tool reliability | (1, 1) | 0.98 | posterior mean |
  | pyramid "certainty" | n/a | n/a | `(2·imp + n)/(2 + n)` capped at 0.95 (`memory_pyramid.py:144-146`) |
- **BM25**: k1 = 1.5, b = 0.75, fixed (`adaptive.py:296-321`). Used in ranking, the pyramid blend (0.5/0.5, `memory_pyramid.py:228-230`), Ta'allum, Hifz, Tajriba and Ilm.
- **Paired e-value (Tajdid).** `E = 2^n·2·B(w+1, l+1)/B(1,1)·P(q > ½)` (`adaptive.py:177-204`). Threshold `1/(0.05·2^−(k+1))`, so 40 for the first challenger (`tajdid.py:105-107`). Disagreement budget 80, challenger proposed after 5 failures (`:58-63`). These are declared, not fitted.
- **Dirichlet / naive Bayes (Qasd via Tamyiz).** `P(f|c) = (n_cf + α)/(n_c + αV)`. α, the three weights and the length exponent γ are **fitted** by leave-one-out (`core/tamyiz.py:7-33`). The chat prior is one pseudo-count per class plus the posteriors of the last 12 earlier messages (`qasd.py:185-200`). This is the most principled component.
- **Hardcoded thresholds that contradict "no hardcoded rules":**
  - Masalik: LTP 0.02, spread factors 0.6/0.3, half-life `24 + 700·w²` hours, hikmah at 10 co-activations and weight ≥ 0.5, 30 s working-memory decay (`masalik.py:135-195`, `597`, `612-617`);
  - forget-below 0.05 and the 7-day cutoff (`dhikr.py:879-883`);
  - importance constants 0.8 / 0.7 / 0.3 at call sites;
  - pyramid certainty constants 0.7 / 0.6 / 0.9;
  - overlap gates 0.6 (Ta'allum) and 0.8 (Hifz);
  - the `about()` "more than half the information" rule (`dhikr.py:168`);
  - recall window 200 / top 5;
  - QCA tier cut-offs 0.85 / 0.45 (`qca/engine.py:730`);
  - all of LivingMemory's weights (`living_memory.py:37-62`).

## 4. Status of designs D4–D7

The report predates PR #143, which merged at 07:01 UTC on 2026-10-28 (the report file is from 06:10 that day).

**D4 (Dhikr recall and per-item strength).**
- Done: the FSRS-6 strength update and R-weighted ranking (#143).
- Not done:
  - the logistic recall gate;
  - a learned injection threshold (it is still a fixed top-5);
  - ACT-R fan or spreading terms;
  - temporal context (TCM);
  - surprise-based episode boundaries;
  - Again/Hard grades from restatement or correction;
  - **supersession**: no `t_valid_from`/`superseded_by` anywhere in the code;
  - escalation to an archive search.
- Imtihan has only 10 in-context memory items (`imtihan/tasks/memory.jsonl`). It has no cross-session or LongMemEval-style belief tracking.

**D5 (Nawm).** Nothing is implemented: no segmentation, fact extraction, deduplication, supersession, semantic promotion, re-verification queue, soft archive or EWC-style margin. The closest pieces are hourly Masalik tafakkur/nisyan and daily Muhasaba.

**D6 (cross-user learning with DP).** Nothing: no noise mechanism, no privacy accounting, no partition selection. Grep finds no DP code.

**D7 (archive and anytime-valid promotion gate).**
- Done: the paired e-value with α-spending for Tajdid instructions only (#143).
- Not done:
  - a variant archive with parent IDs and checker hashes (Tajdid keeps only the last 20 decisions, `tajdid.py:218-221`);
  - parent selection;
  - the novelty pre-filter;
  - the confidential audit;
  - the Goodhart freeze;
  - an e-process for Hifz, Tajriba or Wazn, which still use mean-based rules;
  - e-process demotion.
- Ta'lim uses a one-shot paired bootstrap that refuses a batch at P(worse) ≥ 0.95 (`talim.py:206-260`).

## 5. Cross-user and global learning, and privacy controls

**Shared across all users:**
- the Qasd/Lughah seed corpora, plus admin Ta'lim batches in `talim.db`, behind the bootstrap gate;
- Tajdid instruction versions and Wazn model posteriors in `harness.db` (counts plus error signatures with quoted names and numbers stripped, `tajriba.py:36-45`);
- Shukr-based agent choice for queued tasks (`main.py:1644-1657`);
- the global KnowledgeGraph and knowledge ingest. Any authenticated user can write ingested knowledge into the global DB (`main.py:4389-4440`), but only admin template agents read it.

**Not shared:** the Qasd overlay, Majlis counts, Ilm facts, host trust and source order. All sit in each user's private adaptive store, so a new user starts cold on all of them.

**Privacy controls:**
- **`stateless.bind`** gates `AdaptiveStateStore.put` (`adaptive.py:386-390`), `_tafakkur` (`base.py:3944`), cross-chat recall (`main.py:1692`), `_remember` (`engine.py:3054`) and training capture (`base.py:3165-3170`). **It does not gate:**
  - FSRS and access updates on recall (`dhikr.py:720-749`);
  - Masalik strengthening and encoding (`base.py:3923`);
  - `task_history` (`base.py:3911`);
  - the KG entity write (`base.py:3559`);
  - QCA Lawh, dream and LivingMemory RAM.
- **`cross_chat_recall: off`** is bypassed by:
  - KG hits (earlier task text from other chats, `memory_pyramid.py:182-203`);
  - QCA `RESULT:` entries (`base.py:1206`);
  - Masalik concepts.
- **Mahw** (`mahw.py:126-149`, `500-579`) erases messages, summary, notes, `task_history`, hikmah, KG task entities, Ta'allum, Hifz, Ilm and Qasd overlay entries learned from the chat, learner rows and vectors, then rebuilds Masalik. **It misses:**
  - Tajriba lessons, which keep request tokens (`tajriba.py:98`);
  - QCA Lawh, dream and LivingMemory RAM, which hold task and response text;
  - Sijill;
  - harness failure signatures.
- **Daftar** lists notes, preferences, summaries and Hifz/Ta'allum/Tajriba (`daftar.py:157-187`). It does not list the Qasd overlay, Ilm facts, Masalik, KG, hikmah or `task_history`.

## 6. Gaps against a neuroscience-grounded design

| Mechanism | Present? | Evidence |
|---|---|---|
| Episodic to semantic consolidation | **No.** `memory_type` labels exist but nothing moves memories between them. The per-session running summary is the only automatic gist, and it is per chat and written by the model. LivingMemory's level promotion (`living_memory.py:59-61`) and the dream engine's NREM gist (`dream_engine.py:335-337`) exist but are dead. | §1 |
| Automatic episodic encoding | **Almost none persistent.** The only automatic episodic store is QCA Lawh (RAM, unbounded). The `memories` table needs an explicit "remember". | `base.py:1796` |
| Reconsolidation on retrieval | **Strength only.** Retrieval updates FSRS S/D and Masalik weights, never content. No rewrite on contradiction. Ilm witness re-grading (`ahl_dhikr.py:532-560`) is the closest analogue, and only for sourced facts. | `dhikr.py:727` |
| Interference / competition | **No.** No fan effect, no lateral inhibition, no supersession. Retrieval is **non-selective**: the SQL prefilter ORs `LIKE` over every query word and orders by importance (`dhikr.py:669-683`), and the top 5 are reinforced whether or not they are relevant (no relevance floor, `:717-727`). That is a rich-get-richer loop. Competition exists only at intent level (Qasd softmax, Majlis Thompson sampling). | §2 |
| Working-memory limit | **Token budget only** (`ContextBudget.for_window`, `context_engine.py:127-143`), plus fixed top-k caps (5 pyramid hits, 5 recalled messages, mem0's 800 tokens). The Miller-7 store is dead. Nothing models the roughly 4-chunk limit. | `dhikr.py:351` |
| Sleep-like replay | **Weak.** Hourly Masalik tafakkur links co-activated pairs from up to 100 recent in-RAM activation sets (`masalik.py:720-771`), global DB only. The dream engine's replay output is discarded. No prioritised replay (need × gain) and no re-verification queue. | `main.py:344-357` |
| Synaptic-tagging-like importance gating | **Partly.** Real outcome-gated plasticity: only *verified* work teaches Ta'allum, Hifz, Tajriba and Qasd (`taallum.py:126-127`, `engine.py:533-536`), and facts need two witnesses before entering the prompt (`ahl_dhikr.py:563-585`). Otherwise importance is a caller constant, mapped to the first FSRS grade. LivingMemory's salience and novelty gate (`living_memory.py:43-49`) is dead. | §3 |
| Forgetting | **Hard delete**, not a searchable archive. Pruning uses ACT-R rather than FSRS. It runs only on the global DB, so user notes are never auto-forgotten and vectors are not dropped on prune. | `dhikr.py:903` |
| Error-driven updating | **Yes, for skills and routing** (Beta updates on verification, the Tajdid e-value). **No, for memories**: restatement and correction signals, and the Again grade, are never captured. | §3 |
