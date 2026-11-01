# Code audit (29 Oct 2026, read-only): MIZAN's remaining dependence on the hosted model

Paths are relative to `/backend/` unless stated. Produced by a read-only code exploration of the repository at commit d400589 (branch ccr-3bdd339e-ipygcl, base main 10c0953).

**Bottom line:**
- Most MIZAN recipes make no model call.
- Hosted-model use clusters in three places:
  1. The `_language_only` answer for anything Fahm does not place. This is where knowledge, reasoning and wording are still all done by the base model.
  2. Code writing, code repair and rule induction.
  3. Answers worded from search results and source text.
- Nothing measures the share of requests that needed zero model calls.
- The student-model design (D9) is not implemented.

---

## 1. Lisan tasks (`tadbir/lisan.py`)

**How every task runs:**
- Every task goes through `Lisan.ask` (`lisan.py:191`).
- It records a trace span `lisan.<task>` (`:205-207`). The name is the `task=` argument, or else the calling method's name.
- Spans are recorded only while a trace is bound: debug compare or Imtihan.
- No task gets tools, and images are attached to every prompt (`basar.content`, `:241`).
- `BudgetExhausted` becomes `LisanUnavailable` (`:248-250`).
- Lisan is unavailable when the provider is `mizan-owned` (`:186-189`).

**Who adapts what:**
- **Wazn** (model choice) applies only when `task=` is passed.
- **Tajdid** (instruction rewriting) applies only to tasks in `CONTRACTS` (`tajdid.py:49-56`).
- Outcomes are credited by `_lisan_outcome` (`engine.py:447`), and only for: write_code, fix_code, project_program, page_program, propose/revise_rule and propose/revise_sequence_rule.

Type key: (a) language/wording, (b) knowledge/facts, (c) reasoning/planning/code, (d) perception.

| Task (line) | What it does | Type | Fallback or learned bypass |
|---|---|---|---|
| `write_code` :288 | One program for `build_and_run` | c | **Hifz** re-runs a verified program with 0 calls (`engine.py:918-921`). Tajriba lessons are shown to it, plus Tajdid and Wazn. Otherwise the request is deferred to `_language_only`. |
| `cross_check` :299 | Independent second program (Tathabbut) | c | Wazn chooses a model but no outcome is ever credited. Not in Tajdid. A Hifz program already marked `checked` skips it. |
| `fix_code` :306 | Repair after a sandbox failure (≤2, `MAX_REPAIRS`) | c | Tajriba, Tajdid, Wazn |
| `project_program` :328 | Program over project files (`project_task`) | c | Tajriba, Wazn. Tajdid records nothing for it (not in `CONTRACTS`). |
| `page_program` :344 | `solve(page)` for analytic questions about a page | c | Wazn. Falls back to `answer_from_sources` or an excerpt. |
| `propose_rule` / `revise_rule` :354/:392 | ARC `transform(grid)` (Qiyas), up to 2 revisions | c | Tajdid, Wazn. No own solver. |
| `propose_sequence_rule` / `revise_sequence_rule` :362/:375 | Sequence rule (Silsila) | c | **Own first:** polynomials, prime polynomials, recurrences and OEIS give 0 calls. Lisan is used only if those fail. |
| `write_file` :406 | Each blueprint file (`build_project`) | c | No Wazn or Tajdid (no `task=`). Ta'allum learns only the mapping. |
| `fix_files` :435 | Repair files MIZAN's checks failed (≤2) | c | none |
| `edit_files` :584 | Change an existing project (`edit_project`) | c | none |
| `express` :449 | Word an answer from MIZAN's facts | a | **Own templates:** `phrase()` is used when Lisan is down or Furqan rejects the wording (`engine.py:697-710`) |
| `answer_from_sources` :459 | Cited answer from web, page or ayah-translation text | a (reading comprehension of supplied sources) | Fallback is an excerpt or a source list (`engine.py:3016-3030`). Ayah answers are dropped if Furqan fails (`:2569-2573`). |
| `browse_steps` :491 | Plan browser steps (Shahid) | c | Wazn, never credited. No own planner. |
| `plan_steps` :516 | Map unrecognised wording to MIZAN actions (1–4 steps) | d/c (intent understanding) | **Ta'allum** recall (per-user BM25) skips the call (`engine.py:403-405`). **qasd.learn** adds the verified wording to the user's Qasd overlay, so next time Fahm places it with 0 calls. |
| `fill_arguments` :569 | JSON args for a connector or skill tool (≤2 tries) | d/c (slot filling) | none (`tool_not_prepared`) |
| `form_checks` :616 | Read the countable form constraints out of the request (Nazm) | d | Wazn, never credited. The counting itself is MIZAN's own. |
| `conform` :638 | Rewrite to satisfy failed form checks (once) | a | Wazn, never credited. The original answer is kept if the rewrite is worse. |
| `tajdid.evolve` (`tajdid.py:255`, span `lisan.evolve`) | Rewrite an instruction after ≥5 failures | c (meta) | Runs in the background, outside the user's request |

**Calls outside Lisan:**
- The `_language_only` / agent-loop answer (`agents/base.py:_agentic_loop` :1429). This is all of (a)+(b)+(c) together, and the only place general knowledge enters.
- The running-summary call for long chats (`reasoning/context_engine.py:351-378`, via `api/main.py:1660-1672`). It is not passed to `_record_llm_call`, so it is not in `usage.calls`, but Iqtisad still charges it.
- Peripheral: `reasoning/planner.py:145` (the `/api/plan*` endpoints) and `api/modes.py:105`.

**Perception (d) that is already MIZAN's own:**
- Speech: Sama', faster-whisper running locally.
- Ahl al-Dhikr's NLI: local MiniLM.
- Intent and language: Tamyiz/Qasd/Lughah naive Bayes.
- Quran search: Fihris BM25.
- Arabic morphology: Sarf.

Images are not own: they go to the hosted model through Lisan prompts and the agent loop.

---

## 2. The `_language_only` path and the orchestration modes

**Modes** (`tadbir/engine.py:94-102`, `MIZAN_ORCHESTRATION`):
- `mizan` (default; `strict` is an alias).
- `hybrid`.
- `llm`: `Tadbir.handle` returns None immediately (`:202`).

**When Fahm does not recognise a request (mizan mode):**
1. `Tadbir.handle` returns None. This happens for `converse`, for an intent with no handler (`:235-237`), for `Defer`, and when Tadbir raises (`base.py:3467-3469`).
2. Before that, `_understand` may already have spent **one `plan_steps` call**. That happens when `fahm.actionable()` is true: action families that outranked conversation could not be built and outweigh it (`engine.py:397-422`, `fahm.py:778-789`), and there was no Ta'allum hit. It also happens when `fahm.partly_understood()` is true (`engine.py:378-396`). If the plan is rejected or maps to converse, that call is spent and the request still falls through.
3. `base.py:3478-3487` sets `_language_only=True` and emits the trace event `plan/language_model_answers tools_for_model=none`. Ahl al-Dhikr's settled `verified_evidence` is added to the context (`:3488-3490`).
4. **Tools:** `get_tool_schemas()` returns `[]` (`:617`). The tool catalog is set to None, so even `mizan_discover_tools` is not offered (`:1157-1159`). Any stray tool call is refused (`:2326-2327`). The only exception is MIZAN's own `web_search` for Ahl al-Dhikr, which lifts the flag briefly (`:1994-1998`).
5. **System prompt** (`:2711-2750`):
   - A ~3.2k-character template, plus `RESPONSE_POLICY` (379 characters).
   - `_LANGUAGE_ONLY_NOTE` (543 characters, `:383-390`), plus the "Answer in words." line.
   - The agent's role and configured instructions.
   - In total about 4.1k characters, roughly 1k tokens, before role text.
6. **Context** (`_build_messages` :2790ff, `think` :1187-1229):
   - Model-sized history: the running summary plus recent turns fitted to (window − (16k output + window/4)).
   - Recalled `conversation_memory` from other chats.
   - The SETTLED-by-sources block, mem0 recall, and the AGENT STATE block: Nafs/Ruh telemetry, unified recall top 5, knowledge-graph facts ≤10, Hikmah ≤10.
   - Todos, active skills and saved reply defaults.
   - QCA root line, NLP senses, Lawh hits (3) and Dhikr memories (3).
7. **Model call:** normally **one** streamed call. Output budget is 16k tokens per call by default (`_DEFAULT_OUTPUT_TOKENS` :133). It continues up to 20 times on `max_tokens` (`_MAX_AUTO_CONTINUATIONS` :131). An empty reasoning reply is retried once at low effort.
8. **After the answer:**
   - Isnad, Sidq and Ahl al-Dhikr run, all model-free (NLI plus `web_search` tool calls) (`:3115-3125`).
   - Nazm runs only if Qasd's `form` facet fires (`:3099-3105`). It adds 1–2 Lisan calls (`form_checks`, then `conform`).
   - A RuhLearner candidate is captured (§5).

**`_workspace_only`** (`base.py:393-409`, `engine.py:1730-1800`):
- Used for coding beyond the recipes: stack/React builds, projects that are too big or have a `package.json` (`:1385-1389`, `:1575-1578`), and plan-mode proposals.
- Only when `_handoff_ready()` holds: mizan mode, an interactive approver is present, an event sink exists, and `MIZAN_WORKSPACE_AGENT` is on.
- The model then runs the full ReAct loop with only the 12 `WORKSPACE_AGENT_TOOLS` on one project. MIZAN checks the changed files and allows one repair turn.
- This is the one place in mizan mode where the model controls tools.

**`hybrid`:** the same Tadbir front end, but anything unhandled goes to the full ReAct loop with every permitted tool:
- Up to 100 tool steps (`_DEFAULT_MAX_STEPS` :138).
- The tool catalog offers 8 schemas / 12 KB plus discovery (:1145-1156).

**Model calls per request type** (from the recipe code and `docs/tadbir.md:45-72`):

*0 calls:*
- capabilities, compute, run_code, run_follow, run_file
- quran (text only), quran_count, hadith (including `_explain`, which only adds a commentary note)
- waqt, salah, watch, hf_hub, remember, sarf
- silsila when own methods fit
- Hifz reuse of an already-checked program
- Mustakshif games

*1 call:*
- quran_question and quran_search: always `answer_from_sources` on the translation (`engine.py:2500-2507` passes `question=True`)
- web_search and web_read (`_answer_from`)
- recall (`express`)

*2–5 calls:*
- build_and_run: write_code (1) + fix (≤2) + cross_check (1) + one disagreement fix (1)
- project_task: program + ≤2 fixes + express
- use_tool: fill_arguments (1–2) + express
- qiyas: 1 + ≤2 revisions
- browse: steps (≤2) + answer

*N calls:*
- build_project: one `write_file` per blueprint file (3 for web, 2 for python) + ≤2 `fix_files`

*Unrecognised request:* 1 call (language-only), or **2 calls** when it looked actionable (plan_steps + answer). Add +1–2 for Nazm form checks, and summary calls in long chats.

---

## 3. What is measured today

**Per request** (`base.py:3114-3209`, persisted on each assistant message, `api/main.py:2537-2546`):
- `usage` = `build_usage_summary(_llm_calls)` (`api/usage.py:125-150`). This sums tokens, cost and latency, and keeps `usage.calls[]`, one entry per provider call, Lisan calls included because Lisan calls `agent._record_llm_call`.
- `usage.orchestrator` is `"mizan"` or `"language_model"`.
- Also present: `usage.isnad/amanah/sidq/ahl/nazm`, `usage.memory{stateless, recalled, learning, training}` and `usage.timings`, which includes `provider_ms`, `tool_ms` and `provider_attempt_count`.
- **There is no `usage.lisan` field.**
- `orchestration.language_model_calls = self.lisan.calls` (`engine.py:288`), along with the intent and `understood_by`, is in the live result but **not persisted** (`chat_completion_receipt`, `api/main.py:1869-1875`).

**Aggregates:**
- No counter, metrics endpoint or report computes "share of requests with zero model calls", "share handled by MIZAN", or calls per request (no Prometheus/Counter use found).
- It can be derived offline: assistant messages where `usage.orchestrator=="mizan"` and `usage.calls` is absent.

**Iqtisad** (`api/iqtisad.py`):
- Table `spend(owner_id, day, month, model, input_tokens, output_tokens, cost_usd, source)` in `$MIZAN_DATA_DIR/iqtisad.db` (:118-133).
- `summary()` gives day and month spend, history and by-model breakdown (:646-669). Routes are at `/api/iqtisad*` (`main.py:3428-3465`).
- Rows carry no request id or Lisan task, so spend cannot be split by task or by recipe versus language-only. Local models bypass it.

**Sijill** (`tadbir/sijill.py`):
- An in-memory deque, last 200 notes per user, not persisted.
- Notes come from `trace.event("learn", …)` for taallum, qasd, hifz, tajriba, tajdid, majlis, daftar, sidq, ahl and nazm.
- Served at `/api/tadbir/learning/live` (`main.py:5550`).

**Learning views:**
- `/api/tadbir/learning` (`:5534`): `majlis.report` + `taallum.summary`.
- `/api/tadbir/programs`, `/lessons` and `/harness` (`:5695-5758`): Tajdid versions and Wazn per-model posteriors.

**Debug compare and Imtihan** (`tadbir/muqabala.py`):
- `base_arm` (:109): one call, no tools.
- `mizan_arm` (:158-197) counts `model_calls` (all "chat" spans, including the provider span inside each Lisan span), `lisan_calls` (spans starting `lisan.`) and `tool_calls`.
- Imtihan rows store `model_calls` and `tool_calls` per arm (`imtihan/runner.py:80-99`). `report.py:172-182` sums tokens, cost, latency, model calls and tool calls per arm. The markdown prints "Model calls: base X, MIZAN Y; tool calls by MIZAN Z" (`:251-255`).
- `lisan_calls` is not carried into Imtihan rows.
- The report covers block pass rates with Wilson intervals, a weighted index, the faculty profile, ECE calibration, paraphrase consistency and the Isnad supported share.
- **No stored run results are in the repo.** Only commit messages mention "28 Oct benchmark" findings. `docs/imtihan.md:192` says a full run is ≥380 model calls per attempt, "MIZAN's Lisan calls come on top".

---

## 4. Learning loops (no weights)

All `AdaptiveStateStore.put` writes are skipped when the run is stateless (`core/adaptive.py:386-390`).

**Where the per-user store lives:** each non-admin user has
`$MIZAN_DATA_DIR/private/<sha256(user)>/memory.db`, table `adaptive_state` (`api/main.py:1568-1580`; `base.py:1247-1255`).

| Loop | Trigger | Stored | Where / scope | Fewer future model calls? |
|---|---|---|---|---|
| **qasd.learn** (`qasd.py:238`) | A request placed by Lisan (or by the chat) that MIZAN then **verified** (`engine.py:530-538`, `_qasd_label` :3320) | Message text + intent, rebuilt naive-Bayes `Overlay`, ≤400 examples (`MAX_LEARNED` :46) | key `qasd:<hash>`, per user | **Yes**: the next similar wording is placed by Fahm itself, so no `plan_steps` |
| **Ta'allum** (`taallum.py`) | Lisan-mapped request, kept only if verified. Reuse is re-weighed (`engine.py:517-529`) | Content-word tokens, intent template, Beta posterior. ≤200, overlap ≥0.6. Learns only build_and_run, web_search, build_project, use_tool, edit_project (:25-27) | `taallum:<hash>`, per user | **Yes**: skips `plan_steps` |
| **Hifz** (`hifz.py`) | Verified (and Tathabbut-checked) `build_and_run` program | Tokens, numbers, code, output, Beta. ≤100, overlap ≥0.8 | `hifz:<hash>`, per user | **Yes**: write, fix and cross-check (2–5 calls) become 0; one cross-check for an older unchecked program |
| **Tajriba** (`tajriba.py`) | A failure later repaired and verified | Error signature + diff + request tokens, Beta. ≤60, top 3 shown | `tajriba:<hash>`, per user | Indirect: fewer repair rounds; it still adds prompt text |
| **Tajdid** (`tajdid.py`) | Each credited code/rule outcome. ≥5 failures → challenger written via Lisan | Instruction versions, Beta, paired e-value (α_k=0.05·2^−k) | `$MIZAN_DATA_DIR/harness.db`, **global** | Indirect (fewer failures). The rewrites themselves are model calls. |
| **Wazn** (`wazn.py`) | Credited outcomes (task × model) | Beta per `wazn:<task>:<model>` | `harness.db`, global. Active only if `MIZAN_LISAN_MODELS` is set (≤6 hosted models, same provider) | No: same number of calls, possibly cheaper ones |
| **Majlis** (`majlis.py:99-156`) | Every recipe outcome | Beta per agent + intent (Thompson sampling) | coordinator adaptive store, per user | No (routing only) |
| **Ahl al-Dhikr ilm / witnesses** (`ahl_dhikr.py:390-625`) | Da'if claims in model-worded factual answers, checked against ilm, Wikipedia and web with local NLI | Settled sentences + site (`ilm:<hash>`, per user); host reliability Beta (`ilm:hosts`); source-order trust (`ilm:sources`) | Hosts and sources are per store, so per user for private users | No. Two-witness facts are **given to** the model as `verified_evidence` (`evidence_for` :563, `base.py:3488`). It saves web lookups, not model calls. |
| **Ta'lim** (`talim.py`) | Admin-taught batches for Qasd, facets or Lughah, accepted only if a paired bootstrap gives P(worse) <0.95 | Batches | `$MIZAN_DATA_DIR/talim.db`, **global** | Yes (wider Fahm coverage) |
| **Muhasaba** (`muhasaba.py`) | Daily review of unverified (model-word) answers | Review marks in table `muhasaba_reviews` (:196) in the memory DB. It posts corrections for arithmetic and Quran/hadith quotes. | per user | No |
| **Tadhkir** (`memory/tadhkir.py`, `memory/dhikr.py:816-830`) | Memory write and each recall | FSRS-6 stability, difficulty, last review on `memories` rows | per user | No (ranks recall that goes into prompts) |
| Tafakkur / Hikmah / Shukr (`base.py:3511-3553`) | Successful language-only answers | Heuristic patterns injected into later prompts | agent memory | No |

---

## 5. `backend/learner/`: training-data capture

**Capture** (`agents/base.py:3163-3193`) happens only when all of these hold:
- `result.success`;
- `capture_eligible`, which **Tadbir results never are** (`engine.py:271`) — so only language-only, hybrid or llm agent-loop answers qualify;
- a `session_id` is present;
- `stateless.trains()` is true;
- an authenticated owner exists and `usage.model` is set.

**What is stored:**
- One row in `$MIZAN_DATA_DIR/private/<sha256(owner)>/learner.sqlite3`, table `interactions` (`ruh_learner.py:12-24`, `for_owner` :66-77).
- Fields: `prompt` (raw task text only, no context or system prompt), `response`, `provider`, `model`, `metadata{session_id, review_status:"unreviewed"}`, `quality_score` 0.

**Consent and stateless rules** (`memory/stateless.py`):
- `trains()` is false for stateless runs: Imtihan, debug compare, chats sent with `stateless:true`.
- It is also false under `no_training` (WhatsApp, `api/main.py:3770`).
- There is **no opt-in consent and no licence filter.** Default Anthropic or OpenRouter-Claude outputs are captured. The report says Anthropic's terms forbid training on them.

**Review and export:**
- Review: `/api/learner/review/{id}` (`main.py:7160`) binds reviewer, evidence and a content hash (`review_contract.py`).
- Export: `/api/learner/export` (`main.py:7111`) yields only `accepted` rows with quality ≥0.8. It excludes only the `mizan-owned` and `mizan-support` providers (`data_export.py:10-15`).
- The export schema deliberately has no `messages`/`text` field: `authorship:"model"`, `original_data_eligible: False` (:79-104).
- `get_stats` reports `automatic_weight_training: False` (`ruh_learner.py:137-146`).

**Consumers:**
- None. No training pipeline reads it.
- `mizan_owned/learning_cycle.py:1-5` states "Chat review exports are not inputs here".
- `docs/automatic-learning.md:120-136`: CI forbids machine-authored training targets.
- `KhalifahAgent` also captures (`agents/khalifah.py:92,284`) but is not instantiated anywhere.
- Mahw erases `learner.sqlite3` rows (`memory/mahw.py:549,646`).

---

## 6. Student model, distillation and local models; status of D9 "Lisan-local"

- **Ruh** (`providers_ruh.py`, `providers.py:1356-1365, 1488-1511`):
  - Requires `RUH_ENABLED` plus a checkpoint.
  - `supports_tools=False`, `max_output_tokens=1024`.
  - `ruh_model/README.md` calls it an experimental root generator; the epoch-19 checkpoint "does not establish sentence-level chat".
  - It is a whole-agent provider, not a Lisan rung.
- **IntelligentRouter** (`router/intelligent_router.py`): Ruh-first with external fallback at a confidence of 0.7. **Used only in `tests/test_router.py`**, never in production.
- **Ollama** (`providers.py:1482`), **mizan-minimind** (`providers_minimind.py`, RunPod `mizan-full-sft`, `:1431`) and **mizan-hybrid** (Qwen3-4B base + gates, `MIZAN_HYBRID_ENABLED`, `:1444`): each replaces the whole agent provider. Lisan always uses the agent's one provider (`lisan.py:226-243`).
- **mizan-owned** (`mizan_owned/`):
  - Abstains rather than calling a hosted model.
  - Its learning cycle trains fresh CPU checkpoints only from human-written, reviewer-approved bundles.
  - With it active, Lisan is unavailable, so every code/wording recipe is deferred.
- **Wazn** (`MIZAN_LISAN_MODELS`): a cascade over hosted models of one provider only. There is no local first rung.

**D9 (`research/reports/MIZAN self learning architecture.md:782-795`, plus the hygiene list at `:595-604`)** specifies:
- a licence filter (allow DeepSeek and open weights, deny Anthropic and OpenAI);
- SFT, KTO, DPO and GRPO datasets built from verified outcomes;
- a LoRA adapter retrained from a frozen base;
- McNemar promotion on about 686 items;
- a per-family local-first Beta router feeding Wazn;
- shard-based erasure.

**Status: not implemented.**
- No LoRA, KTO, DPO, GRPO, McNemar, licence filter or local-first routing code exists in `backend/`, `ruh_model/` or `scripts/`.
- Captures carry no verification outcome (Tadbir-verified work is never captured), so the inputs D9 needs (verified, corrected or failed outcomes) are not recorded.
- The repository's current data policy forbids machine-authored training targets outright (`docs/automatic-learning.md:120-136`), which conflicts with D9's SFT on teacher outputs.

**What already exists toward D9:**
- step 1 of the report's ordering ("requests that need no model": Hifz, learned wordings, computed answers);
- the Wazn cascade;
- Iqtisad;
- the review-gated capture store.
