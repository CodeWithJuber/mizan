# MIZAN (ميزان) - Agentic Personal AI

> Quranic Cognitive Architecture (QCA) for human-like reasoning. Version 3.0.0.

## Quick Reference

- **Backend**: Python 3.11+ (FastAPI, Pydantic v2, aiosqlite, Click CLI) — fully async
- **Frontend**: React 19, TypeScript 7, Vite 8, Tailwind CSS 4 (`@tailwindcss/vite`, theme in `src/index.css`), react-router-dom 7, recharts 3
- **AI Providers**: Anthropic (SDK 2.x, API `2026-10-21`, default `claude-opus-5-5`), OpenAI, OpenRouter, Ollama, + in-house **Ruh** model
- **Database**: SQLite via aiosqlite (default `data/mizan.db`)
- **Infra**: Docker Compose, Nginx; optional Ollama + ChromaDB profiles
- **ML**: PyTorch (optional `ml` extra) for the Ruh language model

## Commands

```bash
make setup          # First-time: install deps (.[dev]), pre-commit, frontend, .env
make dev            # Start backend + frontend dev servers (runs ./start.sh start)
make serve          # Backend only (uvicorn, --reload, port 8000)
make cli            # Interactive CLI chat (mizan chat)
make test           # pytest tests/ -v
make test-cov       # pytest with coverage (term + html)
make check          # lint + typecheck + test (full pipeline)
make lint           # ruff check backend/ tests/
make format         # ruff format + ruff check --fix
make typecheck      # mypy backend/ --ignore-missing-imports
make docker         # docker compose up -d --build
make docker-full    # + ollama and vector (ChromaDB) profiles
make docker-down    # Stop Docker
make clean          # Remove build/cache artifacts
make version        # Print VERSION
make release-patch  # Bump + changelog + tag + push (also -minor/-major/-beta/-rc)
```

**CLI** (`mizan <cmd>`, entry point `backend.cli:main`): `serve`, `chat`, `status`, `setup`, `doctor [--check|--fix]`, `version`.

## Key Files

- `backend/api/main.py` — FastAPI app, ~80 REST routes + WebSocket (single large module, ~3.5k lines)
- `backend/api/commands.py` — Slash/command handlers used by chat
- `backend/agents/base.py` — `BaseAgent`: agentic **ReAct loop**, tool dispatch, Nafs evolution, self-healing
- `backend/tadbir/` — **Tadbir**: MIZAN's own orchestration (Fahm understanding → plan → tools via `_execute_tool_safe` → verify → express); the LLM is only **Lisan**, the language faculty (`docs/tadbir.md`). Runs first in `_execute_impl`; `MIZAN_ORCHESTRATION` = mizan (default: the model never controls a tool; unrecognised requests are answered in words with zero tools via the `_language_only` flag in `agents/base.py`) | hybrid (old default) | llm; `strict` = mizan. `majlis.py` gives each part to the best agent (Thompson sampling over Beta posteriors per agent+intent, parallel across agents); `taallum.py` learns verified wording per user so Lisan is not asked again (`/api/tadbir/learning`, Majlis → Learning)
- `backend/core/tamyiz.py` + `tadbir/lughah.py` + `tadbir/qasd.py` — **Fahm by evidence**: language and intent are posteriors of a weighted naive Bayes model (hashed char n-grams + words + parser findings `e:`/context `c:`), smoothing and weights fitted by grouped leave-one-out, MAP decision with `converse` as a class (no word lists, cue regexes or thresholds). `fahm.understand` takes the most probable buildable recipe by family, only when that family is decisive (P > ½); the chat's earlier user messages are the prior (Dirichlet, as Lughah does: `qasd.prior(earlier=…)`); Lisan maps wording (with the last 3 messages as context) only when action families that outranked conversation could not be built and outweigh it (`fahm.actionable`). `use_tool` = a request for a connected tool (Lisan picks it, MIZAN checks the schema). Seeds in `tadbir/data/{lughah,qasd}` (licences in `data/lughah/LICENSES.md`); verified requests are learned per user (`qasd.learn`, Overlay). Fits are cached by corpus SHA-256 in `core/data/tamyiz.json`: after editing seeds run `cd backend && python -m core.tamyiz_cache` (`docs/fahm.md`)
- `backend/tadbir/trace.py` + `muqabala.py` — **debug mode**: `POST /api/debug/compare` sends one message to the base model alone and to MIZAN; spans (understand, invoke_agent, execute_tool, `lisan.<task>` prompts, model usage, Furqan, learning) are recorded only while a trace is bound, and both answers are checked (unsupported numbers, unbacked actions, Quran/hadith quote fidelity). Access: `MIZAN_DEBUG_MODE` = admins | users | off (`docs/debug-mode.md`)
- `backend/imtihan/` — **AGI test**: 96 tasks: 83 questions in 13 blocks (incl. **Ibrah**, `tasks/ibrah.jsonl`: each failure the owner reports from production becomes a task) (`tasks/*.jsonl`; ARC-AGI-2, TruthfulQA, XSTest subsets with `tasks/LICENSES.md`) sent to the base model alone and to MIZAN through Muqabala, scored by rule (`scorers.py`), reported with Wilson intervals, pass^k, ECE/Brier and consistency (`report.py`); background runs + history (`runner.py`), `/api/imtihan/*` (admin), Developer → AGI Test, `python -m imtihan` (`docs/imtihan.md`). ARC puzzles use the **Qiyas** recipe (`tadbir/qiyas.py`): Lisan proposes `transform(grid)`, MIZAN accepts it only if it reproduces every example in the sandbox. Plus 10 **agentic** tasks (`agentic.py`, `agentic/tasks.jsonl`: fresh sandboxed project per arm, judged on the final state, guardrails score 0, injected faults, page fixtures; tool accuracy/groundedness/recovery/latency) and 3 **ARC-AGI-3-style games** (`games/arena.py`; MIZAN plays with **Mustakshif**, `games/mustakshif.py`: learns motion/toggle rules, plans, explores, remembers won levels, no model; `games/arc3.py` plays the official API when `ARC_API_KEY` is set, `/api/imtihan/arc3`). The report adds an index weighted like Artificial Analysis (agents 30 / coding 20 / reasoning 20 / general 30)
- `backend/tadbir/hifz.py` + `muhasaba.py` — **automatic learning**: Hifz keeps programs MIZAN verified per user and re-runs them (same words + numbers) with no model call, each reuse a regression check; Muhasaba re-checks unverified answers daily (arithmetic, Quran/hadith quotes) and posts corrections (`MIZAN_MUHASABA`, user opt-out `muhasaba: off`). Each non-admin user gets a private team of every agent sharing one registry (`_private_agent` in `api/main.py`) so Majlis works per user (`docs/automatic-learning.md`). Also learned from verified outcomes, no weights: **Tajriba** (`tajriba.py`, per-user repair lessons shown to Lisan), **Tajdid** (`tajdid.py`, Lisan's code instructions evolve; a challenger replaces the incumbent only at P(better) ≥ 0.95, `harness.db`, `MIZAN_HARNESS_EVOLUTION`), **Wazn** (`wazn.py`, cheapest ready model from `MIZAN_LISAN_MODELS`, one step stronger per failed attempt); Furqan rejects wording that drops a tool result's warning (`express.cautions`)
- `backend/tadbir/fihris.py` — **Fihris**: finds ayahs by their words when no reference is given (Qasd intent `quran_search`): its own index of 5 views (Arabic + transliteration as letter trigrams, Saheeh/Jalandhry/Hindi translations as words) downloaded once into `$MIZAN_DATA_DIR/quran`; each query word weighted by which view reads it and by P(topic | word) against MIZAN's request seeds; BM25 per view, standardised and mixed; the best ayah is quoted verbatim from the source (`docs/fihris.md`). Follow-up `run_follow` ("run this code") runs the latest program shown in the chat
- `backend/tadbir/isnad.py` — **Isnad**: every answer's claims graded sahih (MIZAN established/verified) · hasan (evidence supports) · da'if (model's words only) · mawdu' (fabricated action/citation/link); attached as `result["isnad"]` → `usage.isnad`, shown under each chat answer, in debug mode for both arms and in the AGI report (`docs/isnad.md`)
- `backend/tadbir/sidq.py` — **Sidq (Truth Gate)**: before an unverified answer is shown, wrong `a op b = c` arithmetic is corrected, altered Quran/hadith quotes are replaced by the source, mawdu' action claims and nonexistent citations are removed, links that do not exist (404/410, no such host) are dropped; `MIZAN_TRUTH_GATE` strict (default) | flag | off; `result["sidq"]` → `usage.sidq`, shown under the answer (`docs/sidq.md`)
- `backend/tadbir/ahl_dhikr.py` — **Ahl al-Dhikr** ("ask the people of knowledge", 16:43): when the question asks about the world (Qasd facet `fact`) and the answer is the model's own words, each da'if claim is asked of MIZAN's sources before it is shown: the user's own `ilm` (settled before), then Wikipedia and a web search in a Thompson-sampled learned order; BM25 picks sentences and a multilingual NLI model (`MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`, MIT, ONNX on CPU, pinned, `$MIZAN_DATA_DIR/models/nli`) gives entailment/contradiction/neither by MAP; supported → hasan with source, contradicted → the source's sentence shown next to the claim, none → "Allahu a'lam" note; settled sentences are kept per user (Mahw erases them with the chat) and given to Lisan before it answers. Ruling questions (facet `ruling`) end with a referral to a qualified scholar. `MIZAN_AHL_DHIKR`, `MIZAN_CONTACT` (User-Agent contact); `usage.ahl`, "Sources asked" under the answer (`docs/ahl-dhikr.md`)
- `backend/tadbir/hudud.py` — **Hudud**: an audit-hook guard in front of every program MIZAN runs on a project (`project_task` recipe) or a page: it may write only the files the request names, never delete/rename/spawn (`docs/hudud.md`). Fahm routes `project_task` (data files + compute verbs), `run_file` (run `x.py`), and reads the next user-given link when a page is gone
- `backend/tadbir/sijill.py` — **Sijill**: live per-user record of every learning step (`trace.event("learn", …)`, Sidq corrections, game levels); `/api/tadbir/learning/live?after=`, shown as **Learning now** on the Learning page
- `backend/knowledge/hf_hub.py` + `skills/builtin/huggingface_hub.py` — **Hugging Face, read by MIZAN on the server** (the code sandbox has no network): `hf_repos` / `hf_files` / `hf_preview` / `hf_import` (into the project; large text files become their first rows); only huggingface.co and `*.hf.co`, redirects checked; `HF_TOKEN` (sealed secret setting) used for admins only; Fahm intent `hf_hub` for HF links and phrasing. `imtihan/locked_eval.py` runs the owner's hash-locked `mizan-eval-v1` as an AGI Test block (`docs/huggingface.md`)
- `backend/tadbir/amanah.py` — **Amanah**: outside text is data. Scans for instructions aimed at the AI (NFKC fold, Unicode tag smuggling, zero-width, exfiltration image links, concealment) and, by evidence (`MIZAN_AMANAH=evidence`, default), a Tamyiz model trained on licensed injection datasets (`tadbir/data/amanah`, held-out recall 20% vs 9.6% for rules, 0.9% false positives; `scripts/amanah_eval.py`), neutralizes them, fences the rest (`<<untrusted id>>`), and taints the run so a model-chosen action that changes something needs approval (`_model_directed` in `agents/base.py`); pasted text never maps to an action (`clean_message`); connector tools are pinned (a changed or poisoned description is held until trusted) and poisoned user skills are held (`docs/amanah.md`)
- `backend/memory/daftar.py` — **Daftar**: one ledger per user of notes (own private memory DB), preferences, chat summaries and learned items, each with provenance (source, created, last used, expiry); edit, forget one or by topic (preview first), export Markdown/JSON, import `mizan-daftar/1` (Amanah skips injected entries). `/api/daftar*` for every user; `/api/memory/*` stays admin-only (`docs/daftar.md`)
- `backend/memory/mahw.py` — **Mahw (true forget)**: `DELETE /api/chat/{id}` (409 while running) erases a chat everywhere (messages, summary, request receipts, Muhasaba reviews, artifacts, plan file, held actions; notes with source `chat:<id>` + vectors; task_history/hikmah/KG rows of its requests; Qasd/Ta'allum/Hifz learned from them (`qasd.unlearn`); learner rows; debug runs) and rebuilds Masalik from what is kept; Daftar note forgets go through `erase_notes`. Then 20-char pieces of the erased text are searched in every store (a piece in the user's other chats explains itself, any other copy is a trace); receipt (removed per store, checks, traces, kept, outside) without content in `mahw.db`, `GET /api/daftar/receipts` (`docs/mahw.md`)
- `backend/automation/muraqabah.py` — **Muraqabah**: per-user watchers (daily · around a prayer · Hijri days · page change) running a task through the user's own agent, a reminder, or the built-in ayah of the day; prayer times computed locally with `adhanpy` (MIT) from the user's place; notices held during salah (5 min before to 20 after each adhan; Jumu'ah 30/60), Thompson-gated by a per-kind Beta posterior of "useful"/"not now" within a daily budget, the rest in an evening digest; posts to the user's Muraqabah chat. Chat creates watchers (Fahm `watch`) and answers prayer times (`salah`); a watcher's task never creates watchers. Times stored as UTC ISO (`_utc`). `/api/muraqabah*`, Watchers page, `MIZAN_MURAQABAH` (`docs/muraqabah.md`)
- `backend/security/sakk.py` — **Sakk (signed action receipts)**: every tool call (`_execute_tool_safe` wraps `_execute_tool_checked` and writes the receipt in `finally`), held decision, approval and Mahw erase is a receipt in the owner's chain: SHA-256 over RFC 8785 JSON (`rfc8785`), `prev` link, HMAC digests of params/results under a per-owner sealed key (no content). Daily Ed25519-signed Merkle root (RFC 6962 hashing) of every chain's head; `/api/sakk`, `/verify`, `/export`, `scripts/verify_sakk.py` checks an export offline. `imtihan/scorecard.py` publishes a run's aggregate report (no prompts) with its hash in a `system` receipt; public `/api/public/reliability`, `/api/public/sakk` (`_OPEN_API_PREFIXES`, no login, Wali-limited) and the `/reliability` page (rendered by `main.tsx` outside the app) (`docs/sakk.md`)
- `backend/perception/sama.py` — **Sama' (voice input)**: speech to text on MIZAN's own server with `faster-whisper` (MIT; Whisper weights pinned per size, downloaded once into `$MIZAN_DATA_DIR/models/whisper`, int8 CPU, VAD); spoken language = argmax P(lang|audio)·chat prior from Lughah; the user's recent words as Whisper context. ≤2 MB/≤90 s (decode stops early), `MIZAN_STT_DAILY_SECONDS` per non-admin. `GET /api/voice`, `POST /api/voice/transcribe` (words go into the composer, never auto-sent), Telegram voice notes (`hear=` on `TelegramBot`). Read aloud uses the browser's `speechSynthesis` and never reads Quranic text (`utils/voice.ts speakable`) (`docs/sama.md`)
- `backend/perception/basar.py` — **Basar (images in chat)**: `images` on `POST /api/chat/stream` (≤4, ≤10 MB, PNG/JPEG/WebP/GIF via Pillow, ≤40 MP); re-encoded without EXIF (no GPS), ≤1568 px, kept per owner by SHA-256 in `$MIZAN_DATA_DIR/media/<owner>` (message metadata holds only the ids; `GET /api/media/{sha}` owner-only; Mahw erases); bound for the turn and the next (`basar.bind`/`content`) so the agent's last user message and Lisan's prompts carry Anthropic image blocks (converted to `image_url` for OpenAI-compatible providers); Iqtisad bounds 1600 tokens per image; a model-chosen change in a turn with an image needs approval (Amanah); a model OpenRouter lists as text-only gets a "not seen" note instead and Wazn picks image-reading Lisan models (`providers.accepts_images`); "make a page from this image" is a `build_project` seed. The old WebSocket "multimodal" path is audio-only now (`docs/basar.md`)
- `backend/api/iqtisad.py` — **Iqtisad (hard spending limits)**: every paid call (Anthropic/OpenAI/OpenRouter `create`/`stream` in `providers.py`) is admitted before it is sent: input bounded by UTF-8 bytes (learned tokens/byte mean+2σ away from the limit), `max_tokens` capped to the money left, in-flight reservations, refused when the learned p10 answer no longer fits; settled with provider cost or `api.prices` (live OpenRouter prices in `prices_live.json`), cut-off calls charged at their bound. `MIZAN_BUDGET_DAILY_USD`/`_MONTHLY_USD` (non-admins), admin per-user and own lower limits, user's local day; `BudgetExhausted` → `error_code: budget_exhausted`; `/api/iqtisad*`, Settings → Spending (`docs/iqtisad.md`)
- `docs/api-testing.md` + `scripts/mizan_client.py` — testing MIZAN without the web app: auth (Bearer token or `X-API-Key`), `/api/chat/stream` SSE events, `/api/debug/compare`, `/api/imtihan/*`, receipts, public routes; the client is standard-library only
- `backend/providers.py` — LLM provider abstraction (Anthropic/OpenRouter/OpenAI/Ollama auto-routing)
- `backend/providers_ruh.py` — `RuhModelProvider` adapter for the local Ruh model
- `backend/reasoning/context_engine.py` — unlimited conversations: model-sized history + persisted running summary (`session_summaries`)
- `backend/core/adaptive.py` — evidence-weighing estimators (Beta posteriors, EW stats, ACT-R, BM25) that replace fixed thresholds (`docs/adaptive-mathematics.md`)
- `backend/settings.py` — Pydantic settings (reads `.env`)
- `backend/runtime_settings.py` — admin-managed settings registry (Settings → System settings, `/api/settings/runtime`); saved values in `$MIZAN_DATA_DIR/runtime_settings.json` override `.env` (`docs/admin-settings.md`)
- `backend/cli.py` — Click CLI entry point
- `backend/doctor.py` — Environment diagnostics (`mizan doctor`)
- `frontend/src/App.tsx` — React router + theme provider; pages under `frontend/src/pages/`
- `ruh_model/` — Standalone Arabic root-morphology transformer (see `ruh_model/README.md`)
- `Makefile`, `pyproject.toml`, `docker-compose.yml`, `docker-compose.prod.yml`

## Architecture

7-layer **Quranic Cognitive Architecture (QCA)**:

| Layer | Module | Purpose |
|-------|--------|---------|
| 1-2 | `backend/perception/` | Sensory input: `vision`, `voice`, `nutq` (speech), `basirah` (insight) |
| 3 | `backend/qca/` | Cognitive integration: `engine`, `answer_engine`, `yaqin_engine` (certainty), `roots`, `cognitive_methods` |
| 4 | `backend/memory/` | Hierarchical memory: `dhikr`, `masalik`, `memory_pyramid`, `lawh_mahfuz`, `living_memory`, `knowledge_graph`, `vector_store` |
| 5 | `backend/reasoning/` | ReAct reasoning: `aql_engine`, `causal_engine`, `planner`, `context_manager` |
| 6 | `backend/agents/` | Autonomous agents with **Nafs** levels: `base`, `specialized`, `khalifah`, `shura_council`, `federation`, `perpetual_rotation` |
| 7 | `backend/core/` | Principles & cognition: `qalb`, `ihsan`, `tawbah`, `sabr`, `shukr`, `tawakkul`, `fitrah`, `fuad`, `lubb`, `basira`, `hawa`, `hikmah`, `hidayah`, `nafs_triad`, `ruh_engine`, `dream_engine`, `creativity`, `imagination`, `self_healing`, plus `plugins`, `hooks`, `middleware`, `events` |

**Cross-cutting subsystems:**

- `backend/security/` — `auth` (JWT), `wali` (rate limiting / guardian), `izn` (permissions), `approvals` (per-chat permission modes + Allow/Deny broker; unattended runs — watchers, schedules, triggers, queue — bind a deferred context via `approvals.unattended`, so actions needing a person are held in `held_actions.db` and decided once via `/api/chat/held/{id}`), `vault` (API key storage), `validation` (input sanitization)
- `backend/connectors/` — MCP connectors (official `mcp` SDK): per-user store, encrypted secrets, OAuth, SSRF `net_guard`, registry browse; tools exposed as `mcp__<server>__<tool>` (`docs/connectors.md`)
- `backend/agent_skills/` — Agent Skills (SKILL.md): loader (project > user > bundled), `activate_skill`/`read_skill_file`, GitHub/zip installer, bundled `library/` (`docs/agent-skills.md`)
- `backend/agents/events.py` — live activity events (`tool_start`, `tool_result`, `todo`, `approval_*`, `skill`) bound per chat stream; `session_state.py` keeps the per-chat plan
- `backend/gateway/` — **Bab**: Telegram (`telegram.py`, Bot API long polling via httpx, no webhook; `TELEGRAM_BOT_TOKEN`, `MIZAN_TELEGRAM`) and links (`store.py`, `bab.db`: one-time 128-bit codes stored as SHA-256, 10 min, single use). Private chats from linked accounts only; each message is the web chat's turn (`_bab_turn` in `api/main.py`) under deferred approvals, held actions come back as inline buttons (`_decide_held`); forwarded text is fenced as data; watcher notices also go to Telegram. **Web Push** (`push.py`, `pywebpush`, VAPID key sealed in `bab.db`): known push services only (FCM/Mozilla/Apple/WNS, https), 404/410 removes the device, lock screen hidden unless `push_preview: on`; the PWA's `public/sw.js` only shows notifications (no caching) (`docs/bab.md`)
- `backend/skills/` — Capability system: `base`, `registry`, `builtin/`
- `backend/router/` — `intelligent_router`: provider/model selection
- `backend/task_queue/` — Async background work: `task_queue`, `worker`, `priorities`
- `backend/automation/` — Scheduled/triggered jobs: `qadr` (scheduler), `triggers`, `webhooks`
- `backend/learner/` — `ruh_learner`, `data_export`: training-data capture from interactions
- `backend/knowledge/` — `ingest`: document/source ingestion (RAG)
- `backend/network/` — `ummah`: agent federation / peer discovery
- `backend/cognitive/` — `thinking_stream`: real-time reasoning trace streaming
- `plugins/` — Drop-in plugins (`plugin.json` + `main.py`); see `request_logger`, `hello_world`

### API surface (groups in `backend/api/main.py`)
`/api/auth/*`, `/api/agents/*`, `/api/tasks`, `/api/chat`, `/api/plan/*`, `/api/memory/*`, `/api/perception/*`, `/api/knowledge/*`, `/api/providers/*`, `/api/security/*`, `/api/channels/*`, `/api/automation/*`, `/api/skills/*`, `/api/gateway/*`, `/api/nafs/*`, `/api/yaqin/*`, `/api/qalb/*`, `/api/federation/*`, `/api/ruh/*`, `/api/queue/*`, `/api/learner/*`, `/api/training/*`, `/api/plugins/*`, `/api/events`, `/api/doctor`, `/api/settings`, `/api/chat/approvals`, `/api/tadbir/learning`, `/api/debug/*`, `/api/imtihan/*`, `/api/iqtisad*`, `/api/bab/*`, `/api/voice*`, `/api/sakk*`, public `/api/public/*`. Separate routers: `/api/connectors/*` (`api/connectors.py`), `/api/agent-skills/*` (`api/agent_skills.py`), `/api/workspaces/*` (`api/coding_workspace.py`). Public versioned API under `/api/v1/*` (root-analyze, tokenize, q28-features). WebSocket at `/ws/{client_id}`.

### Ruh model (`ruh_model/`)
Pure-PyTorch transformer operating in **root-space** (`(root_id, pattern_id)` pairs) instead of BPE tokens. Subpackages: `tokenizer` (Bayan), `embedding` (ISM), `attention` (Qalb), `layers`, `loss` (Mizan), `training`, `benchmarks`, `configs`. Entry scripts `train.py` / `train_full.py`, config in `config.py`. Wired into the backend via `backend/providers_ruh.py` and `/api/ruh/*` + `/api/training/*` endpoints. Requires the `ml` optional dependency group.

## Key Patterns

- **All backend I/O is async** (`async`/`await`).
- Pydantic models for every API request/response schema.
- JWT auth on endpoints; **Wali** rate-limiting; **Izn** permission gating before tool execution.
- **MIZAN directs, the LLM speaks**: requests Fahm recognises (compute, run code, write+run, build a web/Python project, Quran, hadith, Gregorian/Hijri dates, web search/read, recall, remember (the user's own words kept as a `chat:<id>` note), capabilities) are planned, executed and verified by Tadbir; Quran and hadith text and computed results never come from the model. Tests default to `MIZAN_ORCHESTRATION=llm` (conftest) except `tests/test_tadbir.py`.
- Agents run a real ReAct loop (`BaseAgent.think` → `_agentic_loop`), not single-shot calls; max iterations scale with **Nafs** level. Tools execute through `_execute_tool_safe` with input validation and self-healing (auto-install missing packages).
- **Nafs** levels (7-stage) evolve via `evolve_nafs()` / `DevelopmentalGate` based on success rate, task count, and hikmah.
- Real-time streaming via WebSocket and the `cognitive/thinking_stream` module.
- **Agentic coding** (`docs/agentic-coding.md`): chats send `permission_mode` (`auto_edits` | `ask` | `plan` | `auto`); mutating tools wait for `POST /api/chat/approvals/{id}`. Coding tools: `workspace_read/edit/write/glob/grep/run`, `todo_write`. The frontend IDE (`components/CodingWorkspace.tsx`) previews web projects with Sandpack and Python with Pyodide.
- **Server sandbox sessions** (`workspace/sessions.py` on the runner, `workspace/session_client.py` + `api/workspace_sessions.py` in the backend): per-project hardened containers with an egress allowlist proxy, three-way file sync, dev-server previews at public capability URLs `/api/workspaces/preview/<cap>/<port>/` (always CSP-sandboxed), a PTY terminal at `/ws/workspaces/{id}/terminal`, and stdio MCP servers for non-admins. The container-side helper is stdlib-only `workspace/session_agent.py`.
- **Arabic-inspired naming** (consistency matters): Dhikr=memory, Masalik=memory paths, Wali=guardian, Izn=permission, Nafs=self/ego, Qalb=heart, Fuad=conviction, Lubb=metacognition, Basira=insight/discernment, Hawa=lower-pull/safety gate, Hikmah=wisdom, Ihsan=excellence, Tawbah=self-correction, Sabr=patience, Shura=council, Khalifah=steward agent, Yaqin=certainty, Ruh=spirit/model, Qadr=scheduling, Ummah=network, Bab=gateway.
- **al-Insān human-model** (`docs/quranic_human_model.md`): the Qur'anic anthropology MIZAN implements. Faculties (`basira`, `hawa`, `hikmah`, …) run inside `BaseAgent.execute()` and inject guidance into the system prompt via `self._faculty_guidance`. Set `DEEP_FACULTY_LOOP=true` to let them actively gate/redirect (default: advisory only).

## Environment Setup

1. `cp .env.example .env` and set at least one API key.
2. `make install-dev` (or `make setup` for full setup including frontend).
3. Required: `ANTHROPIC_API_KEY` **or** `OPENROUTER_API_KEY`.
4. Required: `SECRET_KEY` (any random string).
5. Optional: channel tokens (`TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_APP_TOKEN`, `WHATSAPP_TOKEN`), `OLLAMA_URL`, `RUH_ENABLED`, email settings.

**Install extras** (`pip install -e ".[<extra>]"`): `dev`, `all`, `channels`, `vector` (ChromaDB), `voice` (ElevenLabs), `ml` (PyTorch + Ruh deps).

## Testing

- pytest with asyncio auto mode; tests in `tests/` (agents, API, memory, QCA, security, router, task_queue, learner, e2e — many `*_comprehensive.py`).
- Ruh model has its own tests in `ruh_model/tests/`.
- Run `make check` for the full lint + typecheck + test pipeline before pushing.
- Pre-commit hook runs ruff (`.pre-commit-config.yaml`).
- CI: `.github/workflows/` — `ci.yml`, `pr-check.yml`, `release.yml`, `auto-release.yml`, `docs.yml`.

## Security Notes

- Never edit `.env` directly (a hook may block this) — use `.env.example` as the template.
- API keys managed via `backend/security/vault.py`.
- Input validation/sanitization in `backend/security/validation.py`; all user input sanitized before processing.
- Tool calls pass through `izn` permission checks; rate limits enforced by `wali`.

## Gotchas

- Docker reads `.env` for compose variable substitution — inline comments like `KEY=value # comment` get parsed as part of the value.
- Claude models use Anthropic only if `ANTHROPIC_API_KEY` starts with `sk-ant-`; otherwise they auto-route through OpenRouter.
- Claude requests never send `temperature`/`top_p`/`top_k` (API `2026-10-21` rejects them); `MIZAN_CHAT_TEMPERATURE` applies to other providers only. Effort comes from `MIZAN_CHAT_EFFORT`.
- Chat limits (steps, continuations, history budget, waits) are documented in `docs/chat-limits-and-metrics.md`; the step budget is no longer tied to the Nafs level.
- `DEFAULT_MODEL` controls the agent model (empty → provider default, `claude-opus-5-5` on Anthropic) — set it in `.env`. `LLM_PROVIDER=auto` (default) detects the provider from keys.
- Backend runs with `--reload`, so local edits in `backend/` take effect automatically.
- Admin-saved runtime settings (`runtime_settings.json`) override `.env` at startup; when a value seems ignored, check Settings → System settings for a "Set here" badge.
- `.env` values are NOT auto-loaded into `os.environ` — pydantic-settings reads them, but `providers.py` calls `load_dotenv()`.
- `.claude/` and `.claude.local.md` are gitignored — local Claude Code config won't be committed.
- The Ruh model and `ml` extra require PyTorch; `/api/ruh/*` and training endpoints are inert unless `RUH_ENABLED=true` and the model path is configured.
- Approvals are in-process futures: keep the backend at **one uvicorn worker** (the prod image does).
- Back up `$MIZAN_DATA_DIR/connectors.key` with the data volume; without it saved connector secrets cannot be decrypted.
- An ordinary chat must still send only `mizan_discover_tools` (`tests/test_dynamic_tool_catalog.py`); never pin new tools into every request.
- `backend/api/main.py` is a single large module — add routes there alongside existing groups rather than creating parallel routers.
