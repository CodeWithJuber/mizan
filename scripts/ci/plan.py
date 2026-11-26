#!/usr/bin/env python3
"""What one CI run checks: the first job of ci.yml runs it (docs/ci-artifacts.md).

    python3 scripts/ci/plan.py

Standard library only. It reads GITHUB_EVENT_NAME; BASE, the commit a pull request's change is
compared with (its merge commit's first parent, main as it is); and SHOULD_SKIP and SKIPPED_BY,
skip-duplicate-actions' answer for this run's files. It prints key=value lines and appends them to
$GITHUB_OUTPUT.

- A pull request gets typecheck and the unit tests its change reaches: agents push a pull request
  many times.
- A push to main gets typecheck and every unit test, the provenance preflight, then the production
  images Deploy Production sends.
- The weekly run and a run by hand get typecheck and every unit test.
- A push to main goes straight to the production images only when an earlier full run (a push,
  the weekly run or a run by hand) passed with the same files. A pull request's run checks only
  part, so its pass never counts.
- The runner is a small server, so no run lints, starts a browser, runs the model and training
  tests (NOT_IN_CI) or builds anything a deploy does not ship. Those run by hand
  (docs/ci-artifacts.md, Not in CI).

The unit tests a pull request runs: the test files it changes, the test files whose imports reach
a changed module (transitively, read from the source), and the test files that name a changed
file. Every unit test runs when the change touches shared code (conftest.py and what it imports,
backend/core/, the settings, the providers, api/main.py, agents/base.py), data under backend/,
configuration, dependencies or a workflow, deletes a module, or changes a module no test reaches:
then the mapping cannot decide. An import by a computed name escapes it; main runs every test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The runs that check everything their files need. A pull request's run checks only part.
FULL_RUNS = ("push", "schedule", "workflow_dispatch")

# --- Unit tests -------------------------------------------------------------------------------
TEST_ROOTS = ("tests/", "ruh_model/tests/", "packages/bayan/tests/", "research/own_model/tests/")
# Where a dotted module name starts: the tests put backend/ on sys.path, bayan is installed.
IMPORT_ROOTS = ("backend/", "", "packages/bayan/src/")
NOT_SOURCE = {".git", "node_modules", "frontend", "venv", ".venv", "__pycache__"}
# A change here runs every unit test: the mapping cannot see what depends on it.
EVERY_TEST = (
    ".github/",
    "scripts/ci/",
    "backend/core/",
    "*conftest.py",
    "tests/__init__.py",
    "pyproject.toml",
    "*requirements*.txt",
    "backend/settings.py",
    "backend/runtime_settings*.py",
    "backend/providers*.py",
    "backend/api/main.py",
    "backend/agents/base.py",
)
# A test that reads every backend module (test_container_imports.py, test_runtime_settings.py).
TREE_SCAN = 'rglob("*.py")'
# Model and training tests CI never runs: they install torch or run the owned model's training
# stages (docs/ci-artifacts.md, Not in CI). They still count as tests, so a change that reaches
# only them runs none of them rather than every test. ci.yml's test job ignores the same files.
NOT_IN_CI = (
    "ruh_model/tests/",
    "research/own_model/tests/",
    "tests/test_owned_learning_cycle.py",
    "tests/test_owned_checkpoint_activation.py",
    "tests/test_owned_learning_service.py",
)
# packages/bayan/scripts/sync_vendor.py --check compares the vendored copy with these.
BAYAN_SOURCES = ("packages/bayan/", "ruh_model/tokenizer/", "backend/qca/roots.py")
# A change here runs every Vitest spec; another frontend change runs the specs it reaches.
FRONTEND_CONFIG = (
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/vite.config.*",
    "frontend/vitest.config.*",
    "frontend/tsconfig*.json",
    ".github/workflows/ci.yml",
    "scripts/ci/",
)

IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w. \t,]+)", re.M)
FROM = re.compile(r"^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]*)", re.M)
DYNAMIC = re.compile(r"""(?:import_module|__import__)\(\s*["']([\w.]+)["']""")


def matches(path: str, patterns) -> bool:
    return any(path.startswith(p) if p.endswith("/") else fnmatch(path, p) for p in patterns)


def changed_files(base: str, root: Path = ROOT) -> list[str] | None:
    """The files changed since `base`, or None when there is no commit to compare with."""
    if not base or set(base) == {"0"}:
        return None
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--no-renames", base, "HEAD"],
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        print(f"No diff against {base}: {diff.stderr.strip()}", file=sys.stderr)
        return None
    return [line for line in diff.stdout.splitlines() if line]


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return matches(path, TEST_ROOTS) and name.startswith("test_") and name.endswith(".py")


def module_names(path: str) -> list[str]:
    """The dotted names `path` is imported by."""
    names = []
    for start in IMPORT_ROOTS:
        if path.startswith(start):
            parts = path[len(start) : -len(".py")].split("/")
            if parts[-1] == "__init__":
                parts.pop()
            if parts:
                names.append(".".join(parts))
    return names


def imported(text: str, names: list[str], package: bool) -> set[str]:
    """The dotted names a source imports, with each package on the way. Read as text, so an
    import in a docstring counts too: that runs more tests, never fewer."""
    found = set(DYNAMIC.findall(text))
    for line in IMPORT.findall(text):
        found.update(part.split()[0] for part in line.split(",") if part.split())
    for dots, module, listed in FROM.findall(text):
        listed = re.sub(r"#[^\n]*", "", listed).strip("()")
        members = [part.split()[0] for part in listed.split(",") if part.split()]
        bases = [module]
        if dots:
            bases = []
            for name in names:
                parent = name.split(".") if package else name.split(".")[:-1]
                parent = parent[: len(parent) - len(dots) + 1]
                bases.append(".".join(parent + ([module] if module else [])))
        for base in filter(None, bases):
            found.add(base)
            found.update(f"{base}.{member}" for member in members if member.isidentifier())
    whole = set()
    for name in found:
        parts = name.split(".")
        whole.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return whole


class Source:
    """The repository's Python files: their text, and which file imports which."""

    def __init__(self, root: Path):
        self.files = []
        for folder, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in NOT_SOURCE)
            here = Path(folder).relative_to(root).as_posix()
            prefix = "" if here == "." else f"{here}/"
            self.files += [prefix + f for f in sorted(files) if f.endswith(".py")]
        self.text = {
            f: (root / f).read_text(encoding="utf-8", errors="replace") for f in self.files
        }
        by_name = defaultdict(set)
        for f in self.files:
            for name in module_names(f):
                by_name[name].add(f)
        self.importers = defaultdict(set)
        for f in self.files:
            for name in imported(self.text[f], module_names(f), f.endswith("/__init__.py")):
                for target in by_name.get(name, ()):
                    if target != f:
                        self.importers[target].add(f)

    def users(self, path: str) -> set[str]:
        """The files that import `path`, directly or through others."""
        seen, todo = set(), [path]
        while todo:
            for user in self.importers[todo.pop()] - seen:
                seen.add(user)
                todo.append(user)
        return seen

    def naming(self, path: str, tests_only: bool, whole_path: bool = False) -> set[str]:
        """The files whose text names `path`: its path, or else its file name."""
        names = (path,) if whole_path else (path, path.rsplit("/", 1)[-1])
        return {
            f
            for f, text in self.text.items()
            if f != path and (is_test(f) or not tests_only) and any(n in text for n in names)
        }


def unit_tests(changed: list[str] | None, root: Path = ROOT) -> str | list[str]:
    """'all', or the test files (in every TEST_ROOTS) that the change reaches."""
    if changed is None:
        return "all"
    source = None
    selected = set()
    for path in changed:
        if matches(path, EVERY_TEST):
            return "all"
        if path.startswith("backend/") and not path.endswith(".py"):
            return "all"  # data a module reads: seeds, fits, bundled skills
        exists = (root / path).is_file()
        if is_test(path):
            if exists:
                selected.add(path)
            continue
        if path.endswith(".py") and not exists:
            return "all"  # a deleted module: what imported it?
        source = source or Source(root)
        if path.endswith(".py"):
            users = source.users(path) | source.naming(path, tests_only=True)
            if "tests/conftest.py" in users or not any(map(is_test, users)):
                return "all"
            if path.startswith("backend/"):
                users |= {f for f in source.files if is_test(f) and TREE_SCAN in source.text[f]}
        else:
            # Comments name docs and frontend files everywhere; only a test that names one reads
            # it. No Python test reads the frontend, so only its whole path counts there.
            frontend = path.startswith("frontend/")
            tests_only = frontend or path.endswith(".md")
            users = set()
            for user in source.naming(path, tests_only, whole_path=frontend):
                users |= {user} | source.users(user)
            if "tests/conftest.py" in users:
                return "all"
        selected |= {f for f in users if is_test(f)}
    return sorted(selected)


def plan(event: str, changed: list[str] | None, root: Path = ROOT, passed_by: str | None = None):
    """What this run checks, as the strings ci.yml's conditions read."""
    flag = {True: "true", False: "false"}
    result = {"verified": "false", "pytest": "none", "vitest": "none"}
    result |= {name: "false" for name in ("bayan", "utils", "provenance")}

    if event == "pull_request":
        tests = unit_tests(changed, root)
        every = tests == "all"
        if changed is None or any(matches(p, FRONTEND_CONFIG) for p in changed):
            vitest = "all"
        elif any(p.startswith("frontend/") for p in changed):
            vitest = "changed"  # vitest run --changed: the specs whose imports reach the change
        else:
            vitest = "none"
        run = [t for t in tests if t.startswith("tests/") and not matches(t, NOT_IN_CI)]
        python = "all" if every else " ".join(run)
        result |= {
            "pytest": python or "none",
            "bayan": flag[
                every
                or any(t.startswith("packages/bayan/tests/") for t in tests)
                or any(matches(p, BAYAN_SOURCES) for p in changed)
            ],
            "vitest": vitest,
            "utils": flag[vitest != "none"],
        }
        return result

    if event == "push" and passed_by in FULL_RUNS:
        return result | {"verified": "true"}

    result |= {"pytest": "all", "vitest": "all", "provenance": "true"}
    return result | {name: "true" for name in ("bayan", "utils")}


def main() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    base = os.environ.get("BASE", "")
    passed_by = None
    if os.environ.get("SHOULD_SKIP") == "true":
        try:
            passed_by = json.loads(os.environ.get("SKIPPED_BY") or "{}").get("event")
        except (ValueError, AttributeError) as error:
            print(f"Unreadable skip-duplicate-actions answer, checking: {error}", file=sys.stderr)
    changed = changed_files(base) if event == "pull_request" else None
    if changed is not None:
        print(f"{len(changed)} file(s) changed since {base}")
    lines = [f"{key}={value}" for key, value in plan(event, changed, ROOT, passed_by).items()]
    print("\n".join(lines))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
