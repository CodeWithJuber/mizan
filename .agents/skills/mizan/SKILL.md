# mizan Development Patterns

> Auto-generated skill from repository analysis; conventions corrected against the
> actual repository (snake_case sources, pytest suite, ruff linting).

## Overview
This skill teaches the core development patterns and conventions used in the
`mizan` Python codebase. You'll learn about file naming, import styles, commit
message conventions, and how to write and run tests. This guide helps maintain
consistency and efficiency when contributing to `mizan`.

## Coding Conventions

### File Naming
- Use **snake_case** for Python files and directories.
  - Example: `backend/memory/dhikr.py`, `backend/agents/base.py`

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

### Export Style
- Keep module internals private by leading underscore; re-export the public API
  from the package `__init__.py` where a package boundary exists.
  - Example: `backend/perception/__init__.py` re-exports `BasirahEngine` and
    `NutqEngine`.

### Commit Messages
- Follow **conventional commit** patterns: `feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`.
  - Example:
    ```
    feat: add data normalization to processor
    docs: update usage instructions in README
    ```

## Workflows

### Adding a New Feature
**Trigger:** When implementing new functionality.
**Command:** `/add-feature`

1. Create a new Python file using snake_case naming (e.g. `backend/core/new_feature.py`).
2. Implement the feature using absolute imports from `backend/`.
3. Re-export the public entry points from the package `__init__.py` if the
   feature defines a new package boundary.
4. Write a test file named `tests/test_<feature>.py` covering the new behavior.
5. Run lint and tests: `make check` (or `ruff check backend/ tests/` plus
   `pytest tests/`).
6. Commit your changes with a `feat:` prefix.
    - Example: `feat: implement user authentication`
7. Push your branch and open a pull request.

### Updating Documentation
**Trigger:** When updating or adding documentation.
**Command:** `/update-docs`

1. Edit or create documentation files as needed (`README.md`, `docs/`,
   `CONTRIBUTING.md`, `CHANGELOG.md` under `[Unreleased]`).
2. Commit changes with a `docs:` prefix.
    - Example: `docs: add API usage examples`
3. Push your branch and open a pull request.

## Testing Patterns

- Test files follow the pattern `tests/test_*.py` (e.g. `tests/test_memory.py`).
- The testing framework is **pytest** with **pytest-asyncio** (`asyncio_mode = "auto"`,
  configured in `pyproject.toml`).
- `tests/conftest.py` inserts `backend/` into `sys.path` and provides shared
  fixtures (`temp_db`, `mock_wali`, `mock_izn`).
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
| `pip install -e ".[dev]"`     | Install dev dependencies (pytest, ruff, mypy, pre-commit)|
| `pytest tests/`               | Run the full test suite                                  |
| `ruff check backend/ tests/`  | Lint sources and tests                                   |
| `ruff format --check backend/ tests/` | Verify formatting (line-length 100)              |
| `make check`                  | Run lint + typecheck + test                              |
| `make serve`                  | Start the backend API server                             |
