"""Measure Amanah on the held-out sets: rules alone against rules + evidence.

A held-out text counts as caught when ``amanah.scan`` reports anything for it
(the same code MIZAN runs on outside text). Rates come with 95% Wilson
intervals. The held-out files are never trained on (build_amanah_corpus.py).

    cd backend && python ../scripts/amanah_eval.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

DATA = Path(__file__).resolve().parents[1] / "backend" / "tadbir" / "data" / "amanah"


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    rate = hits / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return (round(centre - half, 3), round(centre + half, 3))


def texts(name: str) -> dict[str, str]:
    """Held-out windows joined back into their source texts."""
    groups: dict[str, list[str]] = defaultdict(list)
    for line in (DATA / name).read_text(encoding="utf-8").splitlines():
        source, _, text = line.partition("\t")
        groups[source].append(text)
    return {source: " ".join(parts) for source, parts in groups.items()}


def measure() -> dict:
    from tadbir import amanah

    sets = {"attack": texts("heldout_attack.tsv"), "data": texts("heldout_data.tsv")}
    result: dict = {}
    for mode in ("rules", "evidence"):
        os.environ["MIZAN_AMANAH"] = mode
        for label, found in sets.items():
            by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for source, text in found.items():
                key = source.split(":")[0]
                by_source[key][0] += 1
                by_source[key][1] += bool(amanah.scan(text))
            total = sum(n for n, _ in by_source.values())
            hits = sum(h for _, h in by_source.values())
            result[f"{mode}/{label}"] = {
                "texts": total,
                "flagged": hits,
                "rate": round(hits / total, 3) if total else None,
                "interval": wilson(hits, total),
                "by_source": {key: {"texts": n, "flagged": h} for key, (n, h) in by_source.items()},
            }
    os.environ.pop("MIZAN_AMANAH", None)
    model = amanah.model()
    result["model"] = {
        "loo_accuracy": model.loo_accuracy,
        "alpha": model.alpha,
        "weights": list(model.weights),
        "examples": sum(model.docs.values()),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(measure(), indent=1))
