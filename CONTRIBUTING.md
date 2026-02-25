# Contributing to MIZAN

Thank you for your interest in contributing to MIZAN! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
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
make serve        # Backend only (http://localhost:8000)
cd frontend && npm run dev  # Frontend only (http://localhost:3000)
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
make test       # Run tests
make typecheck  # MyPy type checking
```

### 4. Submit a Pull Request

- Write a clear PR title and description
- Reference any related issues
- Ensure CI passes

## Code Style

- **Python**: We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting (configured in `pyproject.toml`)
- **Line length**: 100 characters
- **Type hints**: Encouraged for all public functions
- **Docstrings**: Required for modules, classes, and public functions

## Architecture Overview

MIZAN follows a seven-layer Quranic cognitive architecture:

```
Layer 1: SAMA' (Perception)  → Input processing
Layer 2: FIKR (Cognition)    → AI reasoning with agentic tool loop
Layer 3: DHIKR (Memory)      → Three-tier persistent memory
Layer 4: AQL (Reasoning)     → Logic and relationship binding
Layer 5: HIKMAH (Wisdom)     → Meta-learning and pattern extraction
Layer 6: AMAL (Action)       → Tool execution and output
Layer 7: TAFAKKUR (Reflect)  → Self-improvement after every task
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `backend/api/` | FastAPI routes and WebSocket |
| `backend/agents/` | Agent system (base + specialized) |
| `backend/memory/` | Three-tier memory (Dhikr) |
| `backend/qca/` | Quranic Cognitive Architecture engine |
| `backend/security/` | Auth, permissions, validation |
| `backend/skills/` | Extensible skill/plugin system |
| `frontend/src/` | React frontend |
| `tests/` | Test suite |

## Adding a New Agent Type

```python
# backend/agents/specialized.py
from agents.base import BaseAgent

class YourAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(role="your_role", **kwargs)
        # Register additional tools
        self.tools["your_tool"] = self._tool_your_tool

    async def _tool_your_tool(self, param: str) -> dict:
        # Implement tool logic
        return {"result": "..."}
```

## Adding a New Skill

Create a new file in `backend/skills/builtin/`:

```python
from skills.base import BaseSkill

class YourSkill(BaseSkill):
    name = "your_skill"
    description = "What your skill does"

    async def execute(self, params: dict) -> dict:
        # Implement skill logic
        return {"result": "..."}
```

## Reporting Issues

- Use [GitHub Issues](https://github.com/CodeWithJuber/mizan/issues)
- Include reproduction steps
- Include relevant logs or error messages
- Specify your environment (OS, Python version)

## Code of Conduct

Be respectful, constructive, and inclusive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/).

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
