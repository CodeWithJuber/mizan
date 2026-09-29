"""Torch-free loader for ruh_model reader/dialect submodules.

``ruh_model/__init__.py`` unconditionally imports torch (via
``ruh_model.model``), so a plain ``from ruh_model.reader... import``
fails in torch-less environments (CI installs only ``[dev,nlp]``).
This helper loads the pure-stdlib submodules directly by file path,
bypassing the package ``__init__`` -- the same pattern the repo's
plugin system uses (``importlib.util.spec_from_file_location``).

Only modules with no torch dependency may be loaded this way:
``ruh_model/reader/annotator.py``, ``ruh_model/reader/store.py``,
``ruh_model/dialect/normalize.py`` (all stdlib-only).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def repo_root() -> Path:
    """Absolute path of the repository root (this file lives in backend/api)."""
    return Path(__file__).resolve().parents[2]


def load_ruh_module(relative_path: str, module_name: str) -> ModuleType:
    """Load a torch-free ruh_model submodule by repo-relative path.

    The loaded module is registered in ``sys.modules`` under
    ``module_name`` so repeated loads are cheap and identity-stable.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    full_path = repo_root() / relative_path
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load ruh module from {full_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
