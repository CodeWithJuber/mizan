# MIZAN - Agentic Personal AI

## Quick Reference

- **Backend**: Python 3.11+, FastAPI, Pydantic, aiosqlite
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS
- **AI Providers**: Anthropic, OpenAI, OpenRouter, Ollama
- **Database**: SQLite (via aiosqlite)
- **Infra**: Docker Compose, Nginx

## Commands

```bash
make setup          # First-time: install deps, setup frontend, create .env
make dev            # Start backend + frontend dev servers
make test           # Run pytest
make check          # Lint + typecheck + test (all checks)
make format         # Auto-format with ruff
make docker         # Docker Compose up (build + detach)
make docker-down    # Stop Docker
make clean          # Remove build artifacts
```

## Key Files

- `backend/api/main.py` - FastAPI app, all REST + WebSocket routes
- `backend/agents/base.py` - Base agent with agentic ReAct loop
- `backend/providers.py` - LLM provider abstraction (Anthropic/OpenRouter/OpenAI/Ollama)
- `backend/settings.py` - Pydantic settings from .env
- `backend/cli.py` - CLI entry point (mizan serve, mizan doctor)
- `frontend/src/App.tsx` - React router + theme provider
- `docker-compose.yml` - Dev deployment
- `Makefile` - All project commands

## Architecture

7-layer Quranic Cognitive Architecture (QCA):

| Layer | Module | Purpose |
|-------|--------|---------|
| 1-2 | `backend/perception/` | Sensory input (vision, voice, text) |
| 3 | `backend/qca/engine.py` | Cognitive integration |
| 4 | `backend/memory/` | Hierarchical memory (Dhikr, Masalik) |
| 5 | `backend/reasoning/` | ReAct reasoning with self-correction |
| 6 | `backend/agents/` | Autonomous agents with Nafs levels |
| 7 | `backend/core/` | Principles (Qalb, Ihsan, Tawbah, Sabr) |

Cross-cutting: `backend/security/` (Wali + Izn), `backend/gateway/` (channels), `backend/skills/` (capabilities)

## Key Patterns

- All backend I/O is async (async/await)
- Pydantic models for all API request/response schemas
- JWT auth on all endpoints; Wali rate-limiting; Izn permission system
- WebSocket at /ws/{client_id} for real-time streaming
- Arabic-inspired naming: Dhikr=memory, Wali=guardian, Izn=permission, Nafs=self, Qalb=heart

## Environment Setup

1. `cp .env.example .env` and set at least one API key
2. `make install-dev` (or `make setup` for full setup including frontend)
3. Required: `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`
4. Required: `SECRET_KEY` (any random string)

## Testing

- pytest with asyncio auto mode
- Tests in tests/ (comprehensive: agents, API, memory, QCA, security, e2e)
- Run `make check` for full lint + typecheck + test pipeline
- Pre-commit hook runs ruff on commit

## Security Notes

- Never edit .env directly (hook blocks this) - use .env.example as template
- API keys managed via backend/security/vault.py
- Input validation in backend/security/validation.py
- All user input sanitized before processing

## Gotchas

- Docker reads .env for compose variable substitution - inline comments like `KEY=value # comment` get parsed as part of the value
- Claude models use Anthropic only if `ANTHROPIC_API_KEY` starts with `sk-ant-`; otherwise auto-route through OpenRouter
- DEFAULT_MODEL env var controls agent model (fallback: `claude-sonnet-4-20250514`) — set it in .env
- Backend uses --reload in Docker, so local file changes in backend/ take effect automatically
- .env values are NOT auto-loaded into os.environ - pydantic-settings reads them but providers.py uses load_dotenv()
- `.claude/` and `.claude.local.md` are gitignored — local Claude Code config won't be committed
