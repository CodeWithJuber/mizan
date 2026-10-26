---
name: python-project
description: Create, debug or test Python code in the user's coding project with an isolated run loop (pytest, scripts, data processing). Use for Python scripts, packages, bug fixes, tests or data analysis tasks.
license: MIT
metadata:
  author: mizan
  version: "1.0"
---

# Python project

## Loop
1. Understand the request; for multi-step work keep a `todo_write` plan.
2. Explore with `workspace_glob("**/*.py")`, `workspace_grep`, `workspace_read`.
3. Change code with `workspace_edit` (exact, unique matches). Create new modules with
   `workspace_write`.
4. Verify in the sandbox with `workspace_run` (language `python` or `shell`):
   - `python -m pytest -q` when tests exist (add focused tests for new behaviour);
   - otherwise run the script with a small sample input.
   The sandbox has no network: do not depend on downloads at run time.
5. If a run fails, read the traceback, fix the root cause, run again. Stop after a
   few unsuccessful attempts and explain what is blocking.
6. Report the real output, the files changed and any limitation.

## Conventions
- Python 3.11+, type hints on public functions, `pathlib` for paths.
- Small functions; no global state; raise clear exceptions.
- Keep dependencies to the standard library plus what the project already uses
  (numpy, matplotlib and Pillow are available in the sandbox).
- Save generated charts or files into the project so the user can open them.
