"""Torch-free import bootstrap for the Ruh eval/review packages.

Problem: ``ruh_model/__init__.py`` unconditionally does
``from ruh_model.model import RuhModel`` which imports torch. In torch-less
environments (CI ``dev``/``nlp`` extras, this sandbox) even
``import ruh_model.eval.anything`` fails, because the top-level ``__init__``
executes first.

``ensure_torchfree()`` registers lightweight stub packages for ``ruh_model``
and its subpackages in :data:`sys.modules`, with ``__path__`` pointed at the
real source tree. Submodule imports then load the real ``.py`` files directly,
bypassing the torch-importing ``__init__`` files. It is a no-op when the real
``ruh_model`` package is already importable (torch installed) — the real
package always wins.

Usage from a torch-less interpreter (load this file by path first)::

    import importlib.util
    from pathlib import Path

    repo_root = Path("/path/to/mizan")
    spec = importlib.util.spec_from_file_location(
        "ruh_eval__bootstrap", repo_root / "ruh_model" / "eval" / "_bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    bootstrap.ensure_torchfree(repo_root)

    from ruh_model.eval import morphology_eval  # now works without torch

Stdlib only. Never import torch here.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

# Subpackages that get stub entries so their real modules load by path.
_STUB_PACKAGES = (
    "ruh_model",
    "ruh_model.tokenizer",
    "ruh_model.eval",
    "ruh_model.review",
    "ruh_model.tests",
)


def ensure_torchfree(repo_root: str | Path | None = None) -> bool:
    """Register stub packages so ``ruh_model.*`` imports work without torch.

    Returns True if stubs were installed, False if the real ``ruh_model``
    package is already present in :data:`sys.modules` (nothing to do).
    """
    if "ruh_model" in sys.modules:
        # Real package (torch env) or stubs (already bootstrapped) present.
        return False

    root = Path(repo_root).resolve() if repo_root is not None else _find_repo_root()
    ruh_dir = root / "ruh_model"

    stubs: dict[str, types.ModuleType] = {}
    for dotted in _STUB_PACKAGES:
        stub = types.ModuleType(dotted)
        subpath = dotted.split(".", 1)[1] if "." in dotted else ""
        stub.__path__ = [str(ruh_dir / subpath)] if subpath else [str(ruh_dir)]
        stubs[dotted] = stub
        sys.modules[dotted] = stub

    # Wire parent attributes like a normal package would.
    sys.modules["ruh_model"].tokenizer = stubs["ruh_model.tokenizer"]
    sys.modules["ruh_model"].eval = stubs["ruh_model.eval"]
    sys.modules["ruh_model"].review = stubs["ruh_model.review"]
    sys.modules["ruh_model"].tests = stubs["ruh_model.tests"]
    return True


def _find_repo_root() -> Path:
    """Locate the mizan repo root from this file's location."""
    # _bootstrap.py lives at <root>/ruh_model/eval/_bootstrap.py
    return Path(__file__).resolve().parents[2]
