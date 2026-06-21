"""
research — Mizan Quran computational-linguistics integration layer.

Public surface:
  get_registry()   → tuple[Finding, ...]   curated findings registry
  load_result()    → dict                  load one experiment JSON by name
  list_results()   → list[str]             names of all result JSONs
  PATHS            → module                re-export of research.paths

Imports in this file are lazy / cheap: no heavy deps (no pandas/numpy/scipy/
sklearn/matplotlib/networkx) — the whole app must be importable in a
stdlib-only environment.
"""

from research.findings import get_registry
from research.paths import (
    CSV_ENCODING,
    DATASETS_DIR,
    DB_PATH,
    FIGURES_DIR,
    FONT_PATH,
    OUTPUT_DIR,
    PACKAGE_DIR,
    RAW_DIR,
    RESULTS_DIR,
    figure_path,
    result_path,
)
from research.results_loader import list_results, load_result

# Expose paths module as PATHS for callers who prefer attribute access
import research.paths as PATHS  # noqa: E402  (after other imports for clarity)

__all__ = [
    # Findings
    "get_registry",
    # Results
    "load_result",
    "list_results",
    # Paths (individual constants)
    "PACKAGE_DIR",
    "DATASETS_DIR",
    "RAW_DIR",
    "RESULTS_DIR",
    "OUTPUT_DIR",
    "DB_PATH",
    "FONT_PATH",
    "FIGURES_DIR",
    "CSV_ENCODING",
    "result_path",
    "figure_path",
    # Paths module alias
    "PATHS",
]
