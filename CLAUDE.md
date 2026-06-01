# MIZAN (ميزان) - Agentic Personal AI

> Quranic Cognitive Architecture (QCA) for human-like reasoning. Version 3.0.0.

## Quick Reference

- **Backend**: Python 3.11+ (FastAPI, Pydantic v2, aiosqlite, Click CLI) — fully async
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, react-router-dom, recharts
- **AI Providers**: Anthropic, OpenAI, OpenRouter, Ollama, + in-house **Ruh** model
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
- `backend/providers.py` — LLM provider abstraction (Anthropic/OpenRouter/OpenAI/Ollama auto-routing)
- `backend/providers_ruh.py` — `RuhModelProvider` adapter for the local Ruh model
- `backend/settings.py` — Pydantic settings (reads `.env`)
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
| 7 | `backend/core/` | Principles & cognition: `qalb`, `ihsan`, `tawbah`, `sabr`, `shukr`, `tawakkul`, `fitrah`, `fuad`, `lubb`, `hidayah`, `nafs_triad`, `ruh_engine`, `dream_engine`, `creativity`, `imagination`, `self_healing`, plus `plugins`, `hooks`, `middleware`, `events` |

**Cross-cutting subsystems:**

- `backend/security/` — `auth` (JWT), `wali` (rate limiting / guardian), `izn` (permissions), `vault` (API key storage), `validation` (input sanitization)
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
`/api/auth/*`, `/api/agents/*`, `/api/tasks`, `/api/chat`, `/api/plan/*`, `/api/memory/*`, `/api/perception/*`, `/api/knowledge/*`, `/api/providers/*`, `/api/security/*`, `/api/channels/*`, `/api/automation/*`, `/api/skills/*`, `/api/gateway/*`, `/api/nafs/*`, `/api/yaqin/*`, `/api/qalb/*`, `/api/federation/*`, `/api/ruh/*`, `/api/queue/*`, `/api/learner/*`, `/api/training/*`, `/api/plugins/*`, `/api/events`, `/api/doctor`, `/api/settings`. Public versioned API under `/api/v1/*` (root-analyze, tokenize, q28-features). WebSocket at `/ws/{client_id}`.

### Ruh model (`ruh_model/`)
Pure-PyTorch transformer operating in **root-space** (`(root_id, pattern_id)` pairs) instead of BPE tokens. Subpackages: `tokenizer` (Bayan), `embedding` (ISM), `attention` (Qalb), `layers`, `loss` (Mizan), `training`, `benchmarks`, `configs`. Entry scripts `train.py` / `train_full.py`, config in `config.py`. Wired into the backend via `backend/providers_ruh.py` and `/api/ruh/*` + `/api/training/*` endpoints. Requires the `ml` optional dependency group.

## Key Patterns

- **All backend I/O is async** (`async`/`await`).
- Pydantic models for every API request/response schema.
- JWT auth on endpoints; **Wali** rate-limiting; **Izn** permission gating before tool execution.
- Agents run a real ReAct loop (`BaseAgent.think` → `_agentic_loop`), not single-shot calls; max iterations scale with **Nafs** level. Tools execute through `_execute_tool_safe` with input validation and self-healing (auto-install missing packages).
- **Nafs** levels (7-stage) evolve via `evolve_nafs()` / `DevelopmentalGate` based on success rate, task count, and hikmah.
- Real-time streaming via WebSocket and the `cognitive/thinking_stream` module.
- **Arabic-inspired naming** (consistency matters): Dhikr=memory, Masalik=memory paths, Wali=guardian, Izn=permission, Nafs=self/ego, Qalb=heart, Ihsan=excellence, Tawbah=self-correction, Sabr=patience, Shura=council, Khalifah=steward agent, Yaqin=certainty, Ruh=spirit/model, Qadr=scheduling, Ummah=network, Bab=gateway.

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
- `DEFAULT_MODEL` controls the agent model (fallback: `claude-sonnet-4-20250514`) — set it in `.env`.
- Backend runs with `--reload`, so local edits in `backend/` take effect automatically.
- `.env` values are NOT auto-loaded into `os.environ` — pydantic-settings reads them, but `providers.py` calls `load_dotenv()`.
- `.claude/` and `.claude.local.md` are gitignored — local Claude Code config won't be committed.
- The Ruh model and `ml` extra require PyTorch; `/api/ruh/*` and training endpoints are inert unless `RUH_ENABLED=true` and the model path is configured.
- `backend/api/main.py` is a single large module — add routes there alongside existing groups rather than creating parallel routers.
