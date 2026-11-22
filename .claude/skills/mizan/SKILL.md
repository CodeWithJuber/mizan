# mizan Development Patterns

> Auto-generated skill from repository analysis; conventions corrected against the
> actual repository (snake_case sources, pytest suite, ruff linting). `CLAUDE.md` is
> the detailed map of the code; read it first.

## Overview
This skill teaches the core development patterns and conventions used in the
`mizan` codebase: a fully async Python 3.11+ backend (FastAPI, Pydantic v2,
aiosqlite, Click CLI) and a React 19 / TypeScript 7 / Vite 8 / Tailwind CSS 4
frontend. You'll learn about file naming, import styles, commit message
conventions, and how to write and run tests. This guide helps maintain
consistency and efficiency when contributing to `mizan`.

## Coding Conventions

### File Naming
- Use **snake_case** for Python files and directories.
  - Example: `backend/memory/dhikr.py`, `backend/agents/base.py`
- Modules keep their Arabic names (Dhikr = memory, Wali = guardian, Izn =
  permission, Tadbir = orchestration, Bab = gateway, …); the list is in `CLAUDE.md`.

### Import Style
- Use **absolute imports** relative to the `backend/` directory, which lives on
  `sys.path` (see `tests/conftest.py` for how tests set this up).
  - Example (inside `backend/`):
    ```python
    from memory.dhikr import DhikrMemorySystem
    ```
  - Example (entry points that import the package):
    ```python
    from backend._version import __version__
    ```
- Datetimes: `from datetime import UTC, datetime` and `datetime.now(UTC)`.

### Export Style
- Keep module internals private by leading underscore; re-export the public API
  from the package `__init__.py` where a package boundary exists.
  - Example: `backend/perception/__init__.py` re-exports `BasirahEngine`,
    `NutqEngine`, `VisionProcessor` and `VoiceProcessor`.

### Backend Patterns
- All backend I/O is `async`/`await`; every API request/response body is a
  Pydantic model.
- New routes go in `backend/api/main.py` alongside their group rather than in a
  new parallel router. Then run `python scripts/api_reference.py` to regenerate
  `docs/api-reference.md` and `docs/openapi.json`; `tests/test_api_reference.py`
  fails when a route is missing.
- MIZAN directs, the LLM speaks: requests Fahm recognises are planned, run and
  verified by Tadbir (`backend/tadbir/`, `docs/tadbir.md`); the model never
  controls a tool in the default `MIZAN_ORCHESTRATION=mizan`.
- Never pin a new tool into every request: an ordinary chat sends only
  `mizan_discover_tools` (`tests/test_dynamic_tool_catalog.py`).
- After editing Fahm's seeds (`backend/tadbir/data/{lughah,qasd}`), refit the
  cached models: `cd backend && python -m core.tamyiz_cache`.
- Never edit `.env`; `.env.example` is the template. Keep the backend at one
  uvicorn worker (approvals are in-process futures).

### Commit Messages
- Follow **conventional commit** patterns, usually with a scope: `feat:`, `fix:`,
  `docs:`, `refactor:`, `test:`, `chore:`, `build:`.
  - Example:
    ```
    feat(bab): email channel: MIZAN's own mailbox answers only proven, linked senders
    fix(tadbir): a program is verified only when an independent derivation agrees
    docs: update usage instructions in README
    ```

## Workflows

### Adding a New Feature
**Trigger:** When implementing new functionality.

1. Create a new Python file using snake_case naming (e.g. `backend/core/new_feature.py`).
2. Implement the feature using absolute imports from `backend/`, async I/O and
   Pydantic models for any API body.
3. Re-export the public entry points from the package `__init__.py` if the
   feature defines a new package boundary.
4. Write a test file named `tests/test_<feature>.py` covering the new behavior.
5. If you added a route, run `python scripts/api_reference.py`.
6. Run lint and tests: `make check` (or `ruff check backend/ tests/` plus
   `pytest tests/`). For frontend changes also run `npm run typecheck`,
   `npm run lint`, `npm test`, `npm run build`, `npm run size` and `npm run e2e`
   in `frontend/`.
7. Document it: `docs/<feature>.md`, its entry in `CLAUDE.md`, and
   `CHANGELOG.md` under `[Unreleased]`.
8. Commit your changes with a `feat:` prefix.
    - Example: `feat(auth): /api/auth/me and a logout that lasts`
9. Push your branch and open a pull request.

### Updating Documentation
**Trigger:** When updating or adding documentation.

1. Edit or create documentation files as needed (`README.md`, `docs/`,
   `CLAUDE.md`, `CONTRIBUTING.md`, `CHANGELOG.md` under `[Unreleased]`).
   `docs/api-reference.md` and `docs/openapi.json` are generated: never edit them
   by hand.
2. Commit changes with a `docs:` prefix.
    - Example: `docs: add API usage examples`
3. Push your branch and open a pull request.

## Testing Patterns

- Test files follow the pattern `tests/test_*.py` (e.g. `tests/test_memory.py`).
- The testing framework is **pytest** with **pytest-asyncio** (`asyncio_mode = "auto"`,
  configured in `pyproject.toml`).
- `tests/conftest.py` inserts `backend/` into `sys.path` and provides shared
  fixtures (`temp_db`, `mock_wali`, `mock_izn`, `unplaced_wording`).
- An autouse fixture sets `MIZAN_ORCHESTRATION=llm` for every test (the legacy
  suites test the model-driven loop; `tests/test_tadbir.py` covers Tadbir, the
  production default) and turns off downloads (`MIZAN_LOCKED_EVAL=off`,
  `MIZAN_HADITH_INDEX=off`).
- The Ruh model has its own tests in `ruh_model/tests/`.
- Example test file:
    ```python
    # tests/test_my_module.py
    import pytest

    from memory.my_module import main_function

    def test_main_function():
        assert main_function(2, 2) == 4
    ```

## Commands
| Command                       | Purpose                                                  |
|-------------------------------|----------------------------------------------------------|
| `make setup`                  | First-time setup: `.[dev]`, pre-commit, frontend, `.env` |
| `pip install -e ".[dev]"`     | Install dev dependencies (pytest, ruff, mypy, pre-commit)|
| `make dev`                    | Start backend + frontend dev servers                     |
| `make serve`                  | Start the backend API server (port 8000, `--reload`)     |
| `make test`                   | Run the full test suite (`pytest tests/`)                |
| `make lint`                   | Lint sources and tests (`ruff check backend/ tests/`)    |
| `make format`                 | `ruff format` + `ruff check --fix`                       |
| `make typecheck`              | `mypy backend/ --ignore-missing-imports`                 |
| `make check`                  | Run the billing guard + lint + typecheck + test          |
| `ruff format --check backend/ nlp/ tests/` | Verify formatting as CI does (line-length 100) |
| `npm run typecheck` / `lint` / `test` / `build` / `size` / `e2e` | Frontend checks (in `frontend/`) |
| `python scripts/api_reference.py` | Regenerate the API reference after adding a route    |
| `mizan doctor [--check\|--fix]` | Environment diagnostics                                |
