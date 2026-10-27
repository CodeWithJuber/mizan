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
- `backend/tadbir/trace.py` + `muqabala.py` — **debug mode**: `POST /api/debug/compare` sends one message to the base model alone and to MIZAN; spans (understand, invoke_agent, execute_tool, `lisan.<task>` prompts, model usage, Furqan, learning) are recorded only while a trace is bound, and both answers are checked (unsupported numbers, unbacked actions, Quran/hadith quote fidelity). Access: `MIZAN_DEBUG_MODE` = admins | users | off (`docs/debug-mode.md`)
- `backend/imtihan/` — **AGI test**: 70 tasks in 12 blocks (`tasks/*.jsonl`; ARC-AGI-2, TruthfulQA, XSTest subsets with `tasks/LICENSES.md`) sent to the base model alone and to MIZAN through Muqabala, scored by rule (`scorers.py`), reported with Wilson intervals, pass^k, ECE/Brier and consistency (`report.py`); background runs + history (`runner.py`), `/api/imtihan/*` (admin), Developer → AGI Test, `python -m imtihan` (`docs/imtihan.md`). ARC puzzles use the **Qiyas** recipe (`tadbir/qiyas.py`): Lisan proposes `transform(grid)`, MIZAN accepts it only if it reproduces every example in the sandbox
- `backend/tadbir/isnad.py` — **Isnad**: every answer's claims graded sahih (MIZAN established/verified) · hasan (evidence supports) · da'if (model's words only) · mawdu' (fabricated action/citation/link); attached as `result["isnad"]` → `usage.isnad`, shown under each chat answer, in debug mode for both arms and in the AGI report (`docs/isnad.md`)
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

- `backend/security/` — `auth` (JWT), `wali` (rate limiting / guardian), `izn` (permissions), `approvals` (per-chat permission modes + Allow/Deny broker), `vault` (API key storage), `validation` (input sanitization)
- `backend/connectors/` — MCP connectors (official `mcp` SDK): per-user store, encrypted secrets, OAuth, SSRF `net_guard`, registry browse; tools exposed as `mcp__<server>__<tool>` (`docs/connectors.md`)
- `backend/agent_skills/` — Agent Skills (SKILL.md): loader (project > user > bundled), `activate_skill`/`read_skill_file`, GitHub/zip installer, bundled `library/` (`docs/agent-skills.md`)
- `backend/agents/events.py` — live activity events (`tool_start`, `tool_result`, `todo`, `approval_*`, `skill`) bound per chat stream; `session_state.py` keeps the per-chat plan
- `backend/gateway/` — External channels: `bab` (entry), `router`, `channels/`
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
`/api/auth/*`, `/api/agents/*`, `/api/tasks`, `/api/chat`, `/api/plan/*`, `/api/memory/*`, `/api/perception/*`, `/api/knowledge/*`, `/api/providers/*`, `/api/security/*`, `/api/channels/*`, `/api/automation/*`, `/api/skills/*`, `/api/gateway/*`, `/api/nafs/*`, `/api/yaqin/*`, `/api/qalb/*`, `/api/federation/*`, `/api/ruh/*`, `/api/queue/*`, `/api/learner/*`, `/api/training/*`, `/api/plugins/*`, `/api/events`, `/api/doctor`, `/api/settings`, `/api/chat/approvals`, `/api/tadbir/learning`, `/api/debug/*`, `/api/imtihan/*`. Separate routers: `/api/connectors/*` (`api/connectors.py`), `/api/agent-skills/*` (`api/agent_skills.py`), `/api/workspaces/*` (`api/coding_workspace.py`). Public versioned API under `/api/v1/*` (root-analyze, tokenize, q28-features). WebSocket at `/ws/{client_id}`.

### Ruh model (`ruh_model/`)
Pure-PyTorch transformer operating in **root-space** (`(root_id, pattern_id)` pairs) instead of BPE tokens. Subpackages: `tokenizer` (Bayan), `embedding` (ISM), `attention` (Qalb), `layers`, `loss` (Mizan), `training`, `benchmarks`, `configs`. Entry scripts `train.py` / `train_full.py`, config in `config.py`. Wired into the backend via `backend/providers_ruh.py` and `/api/ruh/*` + `/api/training/*` endpoints. Requires the `ml` optional dependency group.

## Key Patterns

- **All backend I/O is async** (`async`/`await`).
- Pydantic models for every API request/response schema.
- JWT auth on endpoints; **Wali** rate-limiting; **Izn** permission gating before tool execution.
- **MIZAN directs, the LLM speaks**: requests Fahm recognises (compute, run code, write+run, build a web/Python project, Quran, hadith, Gregorian/Hijri dates, web search/read, recall, capabilities) are planned, executed and verified by Tadbir; Quran and hadith text and computed results never come from the model. Tests default to `MIZAN_ORCHESTRATION=llm` (conftest) except `tests/test_tadbir.py`.
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
