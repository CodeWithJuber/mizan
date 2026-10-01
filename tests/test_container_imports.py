"""Container-layout import regression tests.

Production container (docker/Dockerfile.backend.prod) does ``COPY backend/ ./``
with ``WORKDIR /app`` and runs ``uvicorn api.main:app`` — there is NO ``backend``
top-level package in the container. A ``from backend....`` import therefore
crashes the container at boot while still passing pytest, because
tests/conftest.py puts ``backend/`` on ``sys.path`` AND the repo root makes
``backend.*`` importable as a namespace package.

2026-10-01 incident: ``backend/api/usage.py:21`` held
``from backend.api.prices import estimate_cost`` at module top level. Pytest was
green; the container crashed on boot with
``ModuleNotFoundError: No module named 'backend'``.
"""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# Repo-root CLI entry points: invoked as `python -m backend.cli` from the repo
# root (or installed), never imported by the container server path. Exempt.
EXEMPT_FILES = {"backend/cli.py", "backend/doctor.py"}

# Modules importable in the container simulation. These must import cleanly with
# ONLY backend/'s contents on sys.path (no repo root, no `backend` package).
CONTAINER_IMPORT_TARGETS = [
    "api.prices",
    "api.usage",
    "api.commands",
    "api.sandbox",
    "api.modes",
    "api.artifacts",
    "memory.mem0_store",
]

# Ruh routers loaded dynamically by backend/api/main.py::_include_ruh_router
# (2026-10-01: these were "backend.api.*" strings → 404s in the container).
CONTAINER_ROUTER_TARGETS = [
    "api.ruh_morphology",
    "api.ruh_disambiguate",
    "api.ruh_reader",
    "api.ruh_dialect",
    "api.ruh_screening",
    "api.ruh_embeddings",
    "api.ruh_tajwid",
]

# Sanctioned "backend.*" module-name strings: (relative_path, string).
# artifacts.py looks up BOTH names in sys.modules (whichever way main was
# imported) — it never imports by these names. Anything else is a container
# bug: the string only resolves in the repo-root layout.
SANCTIONED_BACKEND_STRINGS = frozenset(
    {
        ("backend/api/artifacts.py", "backend.api.main"),
    }
)


def _iter_py_files():
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in EXEMPT_FILES:
            continue
        yield path, rel


def _backend_imports_outside_try(tree):
    """Yield (lineno, import_text) for `backend.*` imports not under a Try."""
    bad = []

    def visit(node, in_try):
        nonlocal_bad = bad
        for child in ast.iter_child_nodes(node):
            child_in_try = in_try or isinstance(child, ast.Try)
            if isinstance(child, ast.ImportFrom):
                mod = child.module or ""
                if mod == "backend" or mod.startswith("backend."):
                    if not child_in_try:
                        names = ", ".join(a.asname or a.name for a in child.names)
                        nonlocal_bad.append((child.lineno, f"from {mod} import {names}"))
            elif isinstance(child, ast.Import):
                for a in child.names:
                    if a.name == "backend" or a.name.startswith("backend."):
                        if not child_in_try:
                            nonlocal_bad.append((child.lineno, f"import {a.name}"))
            visit(child, child_in_try)

    visit(tree, False)
    return bad


def test_no_bare_backend_imports_in_served_tree():
    """No `backend.*` import outside a sanctioned try/except fallback.

    The sanctioned dual-layout pattern (see backend/qca/morphology_api.py) is:
    try the container-canonical import first (``from api...`` / ``from qca...``),
    fall back to ``from backend...`` only inside ``except ImportError``.
    Anything else crashes the container while passing pytest.
    """
    violations = []
    for path, rel in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for lineno, text in _backend_imports_outside_try(tree):
            violations.append(f"{rel}:{lineno}: {text}")
    assert not violations, (
        "backend.* imports outside try/except will crash the container "
        "(no `backend` package there). Use the container-canonical form "
        "(`from api....`) instead:\n" + "\n".join(violations)
    )


def test_no_backend_module_name_strings():
    """No "backend.*" module-name strings outside the sanctioned lookup.

    2026-10-01: backend/api/main.py loaded 7 Ruh routers via the STRING
    "backend.api.ruh_morphology" etc. through __import__ — invisible to the
    import-AST check above, silently skipped in the container (try/except),
    every /v1/* Ruh endpoint 404. Module names must be container-canonical
    ("api.*"); the only sanctioned exception is the sys.modules dual lookup.
    """
    violations = []
    for path, rel in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        doc_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    doc_lines.add(first.lineno)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if node.lineno in doc_lines:
                continue
            s = node.value
            # A dotted "backend.*" string is (virtually) always a module
            # reference. A bare "backend" word (dict keys, log text, "HTTP
            # backend") is only a problem as an import argument.
            if not s.startswith("backend."):
                continue
            if (rel, s) not in SANCTIONED_BACKEND_STRINGS:
                violations.append(f"{rel}:{node.lineno}: {s!r}")
    # Bare "backend" passed as a module name to a dynamic import.
    for path, rel in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_dynamic_import = (isinstance(func, ast.Name) and func.id == "__import__") or (
                isinstance(func, ast.Attribute) and func.attr == "import_module"
            )
            if not is_dynamic_import or not node.args:
                continue
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and first.value == "backend"
                and (rel, "backend") not in SANCTIONED_BACKEND_STRINGS
            ):
                violations.append(f"{rel}:{first.lineno}: 'backend' (dynamic import)")
    assert not violations, (
        '"backend.*" module-name strings only resolve in the repo-root layout, '
        "not in the container. Use the container-canonical name:\n" + "\n".join(violations)
    )


def test_container_layout_imports(tmp_path):
    """Simulate the container: backend/ contents on sys.path, no repo root."""
    app_dir = tmp_path / "app"
    shutil.copytree(BACKEND_DIR, app_dir, ignore=shutil.ignore_patterns("__pycache__"))
    # The Dockerfile also ships ruh_model/ next to the backend tree
    # (COPY ruh_model/ ./ruh_model/) — the layout-aware repo_root() needs it.
    shutil.copytree(
        REPO_ROOT / "ruh_model",
        app_dir / "ruh_model",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    code = (
        "import "
        + ", ".join(CONTAINER_IMPORT_TARGETS)
        + "; "
        # Same dynamic load main.py performs at boot for the Ruh routers.
        + "; ".join(
            f'm = __import__({t!r}, fromlist=["router"]); '
            f"assert getattr(m, 'router', None) is not None, {t!r}"
            for t in CONTAINER_ROUTER_TARGETS
        )
        + "; print('container-imports-ok')"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(app_dir),
        # Keep the venv's site-packages visible without leaking repo paths.
        "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"container-layout import failed (rc={proc.returncode}):\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr[-2000:]}"
    )
    assert "container-imports-ok" in proc.stdout
