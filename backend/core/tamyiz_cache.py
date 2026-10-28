"""Fitted Tamyiz models, with their leave-one-out calibration kept between runs.

Fitting α and the evidence weights by leave-one-out takes seconds; counting the
corpus takes a fraction of one. The fitted values are stored with the SHA-256 of the corpus
they were fitted on: ``core/data/tamyiz.json`` ships with the code, and
``$MIZAN_DATA_DIR/tamyiz.json`` holds any refit made at run time. A corpus that
changed is simply refitted; a stale value is never used.

    python -m core.tamyiz_cache    # refit every model and update core/data/tamyiz.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from .tamyiz import Tamyiz

logger = logging.getLogger("mizan.tamyiz")
PACKAGED = Path(__file__).parent / "data" / "tamyiz.json"
_REGISTRY: dict[str, tuple[Callable, Callable]] = {}


def _runtime() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "tamyiz.json"


def digest(examples: list[tuple[str, ...]]) -> str:
    hasher = hashlib.sha256()
    for row in examples:
        hasher.update(("\t".join(str(field) for field in reversed(row)) + "\n").encode())
    return hasher.hexdigest()


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def fitted(name: str, featurize: Callable, examples: Callable[[], list[tuple[str, ...]]]) -> Tamyiz:
    _REGISTRY[name] = (featurize, examples)
    rows = examples()
    key = digest(rows)
    model = Tamyiz(featurize)
    for source in (PACKAGED, _runtime()):
        saved = _read(source).get(name) or {}
        # A fit made before the length exponent γ existed is fitted again.
        if saved.get("sha256") == key and len(saved.get("weights") or []) == 3 and "gamma" in saved:
            model.fit(rows, calibrate=False)
            model.alpha = float(saved["alpha"])
            w_prior, w_text, w_evidence = (float(value) for value in saved["weights"])
            model.weights = (w_prior, w_text, w_evidence)
            model.gamma = float(saved["gamma"])
            model.loo_loss, model.loo_accuracy = saved.get("loo_loss"), saved.get("loo_accuracy")
            return model
    model.fit(rows)
    logger.info("Tamyiz %s refitted: %s", name, model.state())
    try:
        path = _runtime()
        stored = _read(path)
        stored[name] = {"sha256": key, **model.state()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    except OSError:
        pass  # a read-only data directory: the fit is kept in memory
    return model


def refit_all() -> dict:
    """Refit every registered model from scratch and store the result with the code."""
    # The shipped fit is of the shipped seeds only, never what one server was taught.
    os.environ["MIZAN_TALIM"] = "off"
    from tadbir import amanah, lughah, qasd

    lughah.model()
    qasd.model()
    amanah.model()
    for facet in sorted({row[0] for row in qasd._rows("facets.tsv")}):
        qasd.facet_model(facet)
    stored: dict = {}
    for name, (featurize, examples) in sorted(_REGISTRY.items()):
        rows = examples()
        model = Tamyiz(featurize).fit(rows)
        stored[name] = {"sha256": digest(rows), **model.state()}
        print(name, stored[name])
    PACKAGED.parent.mkdir(parents=True, exist_ok=True)
    PACKAGED.write_text(json.dumps(stored, indent=1) + "\n", encoding="utf-8")
    return stored


if __name__ == "__main__":
    # Run with -m this file is __main__, while the models register with the
    # imported module ``core.tamyiz_cache``: refit through that one.
    from core import tamyiz_cache

    tamyiz_cache.refit_all()
