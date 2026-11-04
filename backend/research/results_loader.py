"""
Loader for experiment result JSON files.

Imports ONLY stdlib + pydantic — no pandas/numpy/scipy/sklearn/matplotlib/networkx.
Path-traversal is prevented by whitelisting names against list_results().
"""

import json
from functools import cache
from pathlib import Path

from research.paths import RESULTS_DIR
from research.schemas import ResultEnvelope


@cache
def list_results() -> list[str]:
    """Return the stems of all *.json files under RESULTS_DIR, sorted."""
    return sorted(p.stem for p in RESULTS_DIR.glob("*.json"))


def _validate_name(name: str) -> None:
    """
    Reject names that could escape the results directory.

    Raises ValueError for names containing path separators or dots, and
    KeyError for names not in the known result set.
    """
    # Reject traversal characters before checking the whitelist
    if "/" in name or "\\" in name or "." in name or ".." == name:
        raise ValueError(f"Invalid result name (traversal rejected): {name!r}")

    known = list_results()
    if name not in known:
        raise KeyError(f"Unknown result name: {name!r}. Available: {known}")


def load_result(name: str) -> dict:
    """
    Load and parse the named experiment result JSON.

    Results are LRU-cached so repeated calls are free.
    Raises ValueError for path-traversal names; KeyError for unknown names.
    """
    _validate_name(name)
    return _cached_load(name)


@cache
def _cached_load(name: str) -> dict:
    """Internal cached reader — only called after name has been validated."""
    path: Path = RESULTS_DIR / f"{name}.json"
    with path.open(encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Result {name!r} is not a JSON object")
    return data


def load_result_typed(name: str) -> ResultEnvelope:
    """
    Load a result and wrap it in the permissive ResultEnvelope model.

    Falls back gracefully: on any Pydantic validation error the raw dict is
    returned wrapped in a minimal envelope so the catalog never crashes.
    """
    try:
        raw = load_result(name)
        return ResultEnvelope.model_validate(raw)
    except Exception:
        # Never crash the catalog — return an empty envelope
        return ResultEnvelope()
