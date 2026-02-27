# Contributing to MIZAN

Thank you for your interest in contributing to MIZAN! This document provides guidelines and information for contributors.

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

- Python 3.11+
- Node.js 20+ (for frontend)
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/CodeWithJuber/mizan.git
cd mizan

# Install with development dependencies
make setup

# Or manually:
pip install -e ".[dev]"
pre-commit install
cd frontend && npm install
```

### Running Locally

```bash
# Start everything (backend + frontend)
make dev

# Or start individually:
make serve                      # Backend only (http://localhost:8000)
cd frontend && npm run dev      # Frontend only (http://localhost:3000)
```

### Quick Diagnostic

If something isn't working, run the built-in doctor:

```bash
python3 -m backend.cli doctor
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Follow existing code style and patterns
- Add tests for new functionality
- Update documentation if needed

### 3. Run Checks

```bash
make check  # Runs lint + typecheck + tests
```

Or individually:

```bash
make lint       # Ruff linting
make format     # Auto-format code
make test       # Run all 484+ tests
make test-cov   # Run tests with coverage
make typecheck  # MyPy type checking
```

### 4. Submit a Pull Request

- Write a clear PR title and description
- Reference any related issues
- Ensure CI passes

## Code Style

- **Python**: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting (configured in `pyproject.toml`)
- **Line length**: 100 characters
- **Type hints**: Encouraged for all public functions
- **Docstrings**: Required for modules, classes, and public functions
- **Imports**: Use `from datetime import datetime, timezone` (not `datetime.datetime`)
- **Async**: Use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`

## Architecture Overview

MIZAN follows a seven-layer Quranic cognitive architecture with a fully decoupled design:

```
Layer 1: SAMA' (Perception)  → Input processing, emotional detection
Layer 2: FIKR (Cognition)    → AI reasoning with agentic tool loop
Layer 3: DHIKR (Memory)      → Three-tier persistent memory + neural pathways
Layer 4: AQL (Reasoning)     → Logic, relationship binding, certainty tracking
Layer 5: HIKMAH (Wisdom)     → Meta-learning and pattern extraction
Layer 6: AMAL (Action)       → Tool execution and output
Layer 7: TAFAKKUR (Reflect)  → Self-improvement after every task
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `backend/api/` | FastAPI routes, WebSocket, and request handling |
| `backend/agents/` | Agent system (base + specialized + federation) |
| `backend/core/` | Core systems: events, hooks, plugins, middleware, emotional intelligence |
| `backend/qca/` | Quranic Cognitive Architecture: certainty engine, cognitive methods |
| `backend/memory/` | Three-tier memory (Dhikr) + neural pathways (Masalik) |
| `backend/security/` | Auth (JWT), permissions (Izn), validation, sandboxing (Wali) |
| `backend/skills/` | Extensible skill registry + built-in skills |
| `backend/providers.py` | Unified LLM provider interface |
| `backend/doctor.py` | Self-healing diagnostic system |
| `frontend/src/` | React + Vite + Tailwind frontend |
| `tests/` | Test suite (484+ tests) |
| `plugins/` | User plugins directory |

### Communication Patterns

Modules never import each other directly. They communicate through:

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

Create a new file in `backend/skills/builtin/`:

```python
from skills.base import BaseSkill

class YourSkill(BaseSkill):
    name = "your_skill"
    description = "What your skill does"

    async def execute(self, params: dict) -> dict:
        return {"result": "..."}
```

### Adding a New Plugin

Create `plugins/your_plugin/plugin.json` and `plugins/your_plugin/main.py`. See the [README](README.md#build-a-plugin-in-5-minutes) for a complete example.

### Adding a New LLM Provider

Implement `BaseLLMProvider` in `backend/providers.py`:

```python
from providers import BaseLLMProvider, ContentBlock, LLMResponse

class YourProvider(BaseLLMProvider):
    provider_name = "your_provider"

    def create(self, model, max_tokens, system, messages, tools=None):
        # Call your provider's API, return normalized LLMResponse
        return LLMResponse(
            content=[ContentBlock(type="text", text="response")],
            stop_reason="end_turn",
            model=model,
        )
```

Then add it to the `create_provider()` factory function.

## Testing

Tests are in the `tests/` directory and use `pytest` with `pytest-asyncio`.

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

| File | What It Tests |
|------|---------------|
| `test_agents.py` | Agent creation, tools, security |
| `test_agent_comprehensive.py` | Agent factory, nafs evolution, federation |
| `test_api.py` | API endpoints basic tests |
| `test_api_comprehensive.py` | API endpoints detailed (doctor, errors, rate limiting) |
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
from backend.agents.specialized import create_agent

class TestYourFeature:
    def test_basic_functionality(self):
        agent = create_agent("general", name="Test")
        assert agent.name == "Test"

    async def test_async_operation(self):
        # pytest-asyncio handles async tests automatically
        result = await some_async_function()
        assert result["success"] is True
```

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
