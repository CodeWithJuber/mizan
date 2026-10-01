#!/usr/bin/env python3
"""Re-vendor the Bayan tokenizer sources into the standalone ``bayan`` package.

Copies the torch-free tokenizer modules from ``ruh_model/tokenizer/`` plus the
roots lexicon from ``backend/qca/roots.py`` into
``packages/bayan/src/bayan/_tok/``, rewriting ``ruh_model.tokenizer.`` imports
to ``bayan._tok.`` and applying the small anchored patches needed for a
self-contained install:

1. ``bayan.py``: guard the numpy-dependent Q28 import so the package stays
   zero-dependency (the public facade never instantiates Q28).
2. ``root_vocab.py``: look for the bundled ``_data/roots.py`` first, so the
   installed wheel never depends on the repo checkout layout.
3. ``public_api.py``: point the module loader at ``bayan._tok.*``, drop the
   ``sys.modules`` stub machinery (unneeded inside a real package) and the
   now-unused ``sys`` / ``importlib.util`` imports.

Every patch is anchored on exact source text. If an anchor is not found the
script exits non-zero — upstream drift can never silently ship a broken
package. Re-run after any change to the sources, then rebuild the wheel.

Usage (from the repo root):
    python packages/bayan/scripts/sync_vendor.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PKG = REPO_ROOT / "packages" / "bayan"
TOK_SRC = REPO_ROOT / "ruh_model" / "tokenizer"
TOK_DST = PKG / "src" / "bayan" / "_tok"

# (source filename, destination filename)
VENDOR_FILES = [
    ("bayan.py", "bayan.py"),
    ("morphology.py", "morphology.py"),
    ("root_vocab.py", "root_vocab.py"),
    ("english_bridge.py", "english_bridge.py"),
    ("q28_articulatory.py", "q28_articulatory.py"),
    ("public_api.py", "public_api.py"),
]

_Q28_IMPORT_ANCHOR = (
    "from ruh_model.tokenizer.q28_articulatory import Q28ArticulatoryBasis"
)
_Q28_GUARDED = '''\
try:
    from bayan._tok.q28_articulatory import Q28ArticulatoryBasis
except ImportError:  # numpy is optional; the public facade never uses Q28
    class Q28ArticulatoryBasis:  # type: ignore[no-redef]
        """Placeholder that fails loudly only if actually instantiated."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError(
                "Q28ArticulatoryBasis needs numpy, which is not installed. "
                "Install numpy, or use the torch-free BayanTokenizer facade."
            )
'''

_ROOTS_LOADER_ANCHOR = """\
    project_root = _Path(__file__).resolve().parents[2]
    candidate_paths = [
        project_root / "backend" / "qca" / "roots.py",
        project_root / "qca" / "roots.py",
    ]
"""
_ROOTS_LOADER_PATCHED = """\
    # Standalone ``bayan`` package: prefer the lexicon bundled in the wheel.
    candidate_paths = [
        _Path(__file__).resolve().parent / "_data" / "roots.py",
    ]
    project_root = _Path(__file__).resolve().parents[2]
    candidate_paths += [
        project_root / "backend" / "qca" / "roots.py",
        project_root / "qca" / "roots.py",
    ]
"""

_STUBS_ANCHOR_START = "def _ensure_package_stubs() -> None:"
_STUBS_REPLACEMENT = '''\
def _ensure_package_stubs() -> None:
    """No-op in the standalone ``bayan`` package.

    The vendored copy imports ``bayan._tok.*`` directly, so no
    ``sys.modules`` stubs are needed. The numpy/Q28 guard lives in the
    vendored ``bayan.py`` instead.
    """
'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"SYNC FAILED [{label}]: anchor found {count} times (expected 1). "
            "Upstream source changed — update the patch."
        )
    return text.replace(old, new)


def _replace_stubs_fn(text: str) -> str:
    """Replace the whole _ensure_package_stubs function with a no-op."""
    lines = text.splitlines(keepends=True)
    start = next(
        (i for i, ln in enumerate(lines) if ln.startswith(_STUBS_ANCHOR_START)), None
    )
    if start is None:
        raise SystemExit("SYNC FAILED [stubs]: _ensure_package_stubs not found.")
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.match(r"^(def |class |[A-Za-z_])", lines[i])
        ),
        len(lines),
    )
    return "".join(lines[:start]) + _STUBS_REPLACEMENT + "".join(lines[end:])


def main() -> None:
    if not (REPO_ROOT / "pyproject.toml").exists():
        raise SystemExit(f"Repo root not found at {REPO_ROOT}")
    TOK_DST.mkdir(parents=True, exist_ok=True)
    (TOK_DST / "_data").mkdir(exist_ok=True)
    (TOK_DST / "__init__.py").write_text(
        '"""Vendored Bayan tokenizer internals (see scripts/sync_vendor.py)."""\n'
    )
    (TOK_DST / "_data" / "__init__.py").write_text("")

    for src_name, dst_name in VENDOR_FILES:
        src = TOK_SRC / src_name
        if not src.exists():
            raise SystemExit(f"SYNC FAILED: source missing: {src}")
        text = src.read_text(encoding="utf-8")

        # 1. Rewrite absolute repo imports to the vendored namespace.
        text, n = re.subn(r"from ruh_model\.tokenizer\.", "from bayan._tok.", text)
        text, m = re.subn(r"import ruh_model\.tokenizer\.", "import bayan._tok.", text)
        if src_name == "bayan.py" and n + m == 0:
            raise SystemExit("SYNC FAILED [bayan.py]: no ruh_model imports rewritten.")

        # 2. File-specific patches.
        if src_name == "bayan.py":
            text = _replace_once(
                text,
                "from bayan._tok.q28_articulatory import Q28ArticulatoryBasis",
                _Q28_GUARDED.rstrip("\n"),
                "bayan.py q28 guard",
            )
        elif src_name == "root_vocab.py":
            text = _replace_once(
                text, _ROOTS_LOADER_ANCHOR, _ROOTS_LOADER_PATCHED, "root_vocab loader"
            )
        elif src_name == "public_api.py":
            for dotted in ("bayan", "morphology", "root_vocab", "english_bridge"):
                text = _replace_once(
                    text,
                    f'importlib.import_module("ruh_model.tokenizer.{dotted}")',
                    f'importlib.import_module("bayan._tok.{dotted}")',
                    f"public_api loader {dotted}",
                )
            text = _replace_stubs_fn(text)
            text = _replace_once(
                text,
                "import importlib\nimport importlib.util\nimport sys\nimport types\n",
                "import importlib\nimport types\n",
                "public_api unused imports",
            )

        (TOK_DST / dst_name).write_text(text, encoding="utf-8")
        print(f"vendored: {src_name} -> _tok/{dst_name}")

    # 3. The roots lexicon ships as package data.
    roots_src = REPO_ROOT / "backend" / "qca" / "roots.py"
    if not roots_src.exists():
        raise SystemExit(f"SYNC FAILED: roots lexicon missing: {roots_src}")
    (TOK_DST / "_data" / "roots.py").write_text(
        roots_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print("vendored: backend/qca/roots.py -> _tok/_data/roots.py")
    print("OK — vendoring complete.")


if __name__ == "__main__":
    sys.exit(main())
