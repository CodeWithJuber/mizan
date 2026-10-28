# Contributing to MIZAN

Thank you for your interest in contributing to MIZAN! This document provides guidelines and information for contributors. [`CLAUDE.md`](CLAUDE.md) is the detailed, up-to-date map of the code: which module does what and which doc describes it.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Architecture Overview](#architecture-overview)
- [Adding Features](#adding-features)
- [Testing](#testing)
- [Reporting Issues](#reporting-issues)

## Getting Started

### Prerequisites

- Python 3.11+ (CI tests 3.11, 3.12, 3.13 and 3.14)
- Node.js 24 LTS and npm 11+ (for the frontend)
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/CodeWithJuber/mizan.git
cd mizan

# Install with development dependencies, pre-commit, the frontend and a .env
make setup

# Or manually:
pip install -e ".[dev]"
pre-commit install
cp .env.example .env
cd frontend && npm install
```

Set at least one provider (for example `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`) and a `SECRET_KEY` in `.env`; never commit `.env` (`.env.example` is the template). Optional extras: `pip install -e ".[<extra>]"` with `all`, `channels`, `vector`, `voice`, `voice-local` (on-server speech to text), `knowledge`, `nlp` or `ml` (PyTorch, for the Ruh model).

### Running Locally

```bash
# Start everything (backend + frontend)
make dev

# Or start individually:
make serve                      # Backend only (http://localhost:8000, --reload)
cd frontend && npm run dev      # Frontend only (http://localhost:3000)
make cli                        # Interactive CLI chat (mizan chat)
```

### Quick Diagnostic

If something isn't working, run the built-in doctor:

```bash
mizan doctor            # or: python3 -m backend.cli doctor
mizan doctor --check    # diagnose only
mizan doctor --fix      # auto-fix the issues it finds
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Follow existing code style and patterns
- Add tests for new functionality
- Update documentation if needed: the feature's page under `docs/`, its entry in `CLAUDE.md`, and `CHANGELOG.md` under `[Unreleased]`

### 3. Run Checks

```bash
make check  # Runs lint + typecheck + tests
```

Or individually:

```bash
make lint       # ruff check backend/ tests/
make format     # ruff format + ruff check --fix
make test       # pytest tests/ (2,721 tests collected at 5cc11dc)
make test-cov   # Run tests with coverage (term + html)
make typecheck  # mypy backend/ --ignore-missing-imports
```

CI also lints and format-checks `nlp/` (`ruff check backend/ nlp/ tests/`, `ruff format --check backend/ nlp/ tests/`) and checks the frontend:

```bash
cd frontend
npx tsc --noEmit                                         # npm run typecheck
for test in src/utils/*.test.ts; do node "$test" || exit; done
npm run build
```

### 4. Submit a Pull Request

- Write a clear PR title and description
- Reference any related issues
- Ensure CI passes
- Commit messages follow conventional commits, usually with a scope: `feat(bab): …`, `fix(tadbir): …`, `docs: …`

## Code Style

- **Python**: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting (configured in `pyproject.toml`; rules E, W, F, I, B, UP, S)
- **Line length**: 100 characters
- **Type hints**: Encouraged for all public functions; `make typecheck` runs mypy
- **Docstrings**: Required for modules, classes, and public functions
- **Async**: all backend I/O is `async`/`await`
- **API schemas**: a Pydantic model for every request and response body
- **Datetimes**: `from datetime import UTC, datetime` and `datetime.now(UTC)`, never the deprecated `datetime.utcnow()`
- **Naming**: modules keep their Arabic names (Dhikr = memory, Wali = guardian, Izn = permission, Tadbir = orchestration, …); see `CLAUDE.md` for the full list

## Architecture Overview

MIZAN follows a seven-layer Quranic cognitive architecture (`backend/core/architecture.py`):

```
Layer 1: SAMA' (Perception)  → Input processing, emotional detection
Layer 2: FIKR (Cognition)    → AI reasoning with agentic tool loop
Layer 3: DHIKR (Memory)      → Three-tier persistent memory + neural pathways
Layer 4: AQL (Reasoning)     → Logic, relationship binding, certainty tracking
Layer 5: HIKMAH (Wisdom)     → Meta-learning and pattern extraction
Layer 6: AMAL (Action)       → Tool execution and output
Layer 7: TAFAKKUR (Reflect)  → Self-improvement after every task
```

**MIZAN directs, the LLM speaks.** Requests Fahm recognises (compute, run code, build a project, Quran, hadith, dates, web search and read, recall, …) are planned, executed and verified by Tadbir (`backend/tadbir/`, [`docs/tadbir.md`](docs/tadbir.md)); the model only writes words and code. `MIZAN_ORCHESTRATION` = `mizan` (default) | `hybrid` | `llm`.

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `backend/api/` | FastAPI app (`main.py`: REST routes + WebSocket), chat commands, and the separate routers for connectors, agent skills and workspaces |
| `backend/tadbir/` | MIZAN's own orchestration: understanding (Fahm), recipes, verification, Truth Gate (Sidq), Amanah, Shahid and more |
| `backend/agents/` | `BaseAgent` ReAct loop, tool dispatch, specialized agents, federation |
| `backend/core/` | Principles and cognition (Qalb, Hikmah, …), adaptive estimators, events, hooks, plugins, middleware |
| `backend/qca/` | Quranic Cognitive Architecture: certainty engine (Yaqin), cognitive methods |
| `backend/memory/` | Dhikr memory, Masalik pathways, Daftar ledger, Mahw erasure, Tadhkir |
| `backend/reasoning/` | Planner, causal engine, context engine |
| `backend/perception/` | Sama' (voice input), Basar (images in chat), vision, Nutq |
| `backend/security/` | Auth (JWT), Wali (rate limits, guardian), Izn (permissions), approvals, vault, Sakk receipts |
| `backend/connectors/` | MCP connectors (official `mcp` SDK) |
| `backend/agent_skills/` | Agent Skills (SKILL.md) loader, installer, bundled library |
| `backend/skills/` | Built-in skill registry and tools |
| `backend/gateway/` | Bab: Telegram, email, WhatsApp, Web Push |
| `backend/workspace/` | Coding projects, the private runner, sandbox sessions, the Shahid browser |
| `backend/imtihan/` | The AGI test |
| `backend/automation/` | Scheduler (Qadr), triggers, webhooks, Muraqabah watchers |
| `backend/providers.py` | Unified LLM provider interface |
| `backend/doctor.py` | Self-healing diagnostic system |
| `frontend/src/` | React 19 + TypeScript 7 + Vite 8 + Tailwind CSS 4 frontend |
| `ruh_model/` | The Ruh root-space language model (PyTorch, `ml` extra) |
| `tests/` | Test suite (pytest) |
| `plugins/` | User plugins directory |
| `docs/` | One page per subsystem |

### Extension Points

Besides direct imports, modules can be extended through:

- **Events** (Nida') — Fire-and-forget notifications (`core/events.py`)
- **Hooks** (Ta'liq) — Data transformation pipelines (`core/hooks.py`)
- **Middleware** (Silsilah) — Request/response processing (`core/middleware.py`)

## Adding Features

### Adding a New Agent Type

```python
# backend/agents/specialized.py
from agents.base import BaseAgent

class YourAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(role="your_role", **kwargs)
        self.tools["your_tool"] = self._tool_your_tool

    async def _tool_your_tool(self, param: str) -> dict:
        return {"result": "..."}
```

Then register it in the `create_agent()` factory in the same file.

### Adding a New Skill

Create a new file in `backend/skills/builtin/`; the registry loads every `SkillBase` subclass it finds there:

```python
from ..base import SkillBase, SkillManifest

class YourSkill(SkillBase):
    manifest = SkillManifest(
        name="your_skill",
        description="What your skill does",
        permissions=["network:https://*"],
    )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._tools = {"your_tool": self.your_tool}

    async def execute(self, params: dict, context: dict | None = None) -> dict:
        return await self.your_tool(**params)

    async def your_tool(self, query: str = "") -> dict:
        return {"result": "..."}

    def get_tool_schemas(self) -> list[dict]:
        return [{"name": "your_tool", "description": "...", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}]
```

Never pin a new tool into every request: an ordinary chat sends only `mizan_discover_tools`, and the tool catalog offers other tools when a request matches them (`tests/test_dynamic_tool_catalog.py`).

### Adding a New Plugin

Create `plugins/your_plugin/plugin.json` and `plugins/your_plugin/main.py`. See the [README](README.md#build-a-plugin) for a complete example.

### Adding an API Route

Add it to `backend/api/main.py` alongside the existing group rather than creating a parallel router, with a Pydantic model for its body. Then regenerate the reference: `python scripts/api_reference.py` rewrites `docs/api-reference.md` and `docs/openapi.json`, and `tests/test_api_reference.py` fails when a route is missing from them.

### Adding a New LLM Provider

Implement `BaseLLMProvider` in `backend/providers.py`:

```python
from providers import BaseLLMProvider, ContentBlock, LLMResponse

class YourProvider(BaseLLMProvider):
    provider_name = "your_provider"

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        # Call your provider's API, return normalized LLMResponse
        return LLMResponse(
            content=[ContentBlock(type="text", text="response")],
            stop_reason="end_turn",
            model=model,
        )
```

Then add it to the `create_provider()` factory function. A paid call must be admitted by Iqtisad before it is sent (`_admit` in `providers.py`, [`docs/iqtisad.md`](docs/iqtisad.md)).

### Editing Fahm's Seeds

After editing the seeds in `backend/tadbir/data/{lughah,qasd}`, refit the cached models: `cd backend && python -m core.tamyiz_cache` (updates `backend/core/data/tamyiz.json`).

## Testing

Tests are in the `tests/` directory and use `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`). `tests/conftest.py` puts `backend/` on `sys.path` and, for every test, sets `MIZAN_ORCHESTRATION=llm` (the legacy suites test the model-driven loop; `tests/test_tadbir.py` covers MIZAN's own orchestration) and turns off downloads (`MIZAN_LOCKED_EVAL=off`, `MIZAN_HADITH_INDEX=off`). The Ruh model has its own tests in `ruh_model/tests/`.

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run a specific test file
python3 -m pytest tests/test_agents.py -v

# Run a specific test
python3 -m pytest tests/test_agents.py::TestBaseAgent::test_agent_creation -v
```

### Test Structure

There are about 135 test files; a few of them:

| File | What It Tests |
|------|---------------|
| `test_agents.py` | Agent creation, tools, security |
| `test_agent_comprehensive.py` | Agent factory, nafs evolution, federation |
| `test_api.py` | API endpoints basic tests |
| `test_api_comprehensive.py` | API endpoints detailed (doctor, errors, rate limiting) |
| `test_api_reference.py` | `docs/api-reference.md` lists every route |
| `test_tadbir.py` | Tadbir: Fahm, recipes and verification (the production orchestration) |
| `test_dynamic_tool_catalog.py` | An ordinary chat sends only `mizan_discover_tools` |
| `test_architecture.py` | Balancer, Nafs profiles, QCA integration |
| `test_core_systems.py` | Ruh, Qalb, Tawbah, Ihsan, Sabr, Shukr |
| `test_memory.py` | Memory system persistence |
| `test_memory_comprehensive.py` | Memory types, consolidation, audit logs |
| `test_masalik.py` | Neural pathway network |
| `test_qca_engine.py` | QCA layers and cognitive pipeline |
| `test_qca_comprehensive.py` | Yaqin, Mizan, Furqan, Lawh |
| `test_security_comprehensive.py` | Auth, validation, sandboxing, SSRF |
| `test_doctor.py` | Diagnostic system |
| `test_e2e_scenarios.py` | End-to-end integration scenarios |

### Writing Tests

```python
import pytest
from agents.specialized import create_agent

class TestYourFeature:
    def test_basic_functionality(self):
        agent = create_agent("general", name="Test")
        assert agent.name == "Test"

    async def test_async_operation(self):
        # pytest-asyncio handles async tests automatically
        result = await some_async_function()
        assert result["success"] is True
```

Shared fixtures in `tests/conftest.py`: `temp_db`, `mock_wali`, `mock_izn`, and `unplaced_wording` (Qasd reads every message as an action it cannot build, so Lisan maps the wording).

## Reporting Issues

- Use [GitHub Issues](https://github.com/CodeWithJuber/mizan/issues)
- Include reproduction steps
- Include relevant logs or error messages
- Specify your environment (OS, Python version)
- Run `mizan doctor` and include the output

## Code of Conduct

Be respectful, constructive, and inclusive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/).

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
