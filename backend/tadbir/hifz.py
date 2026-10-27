"""Hifz (حفظ): MIZAN keeps the programs it verified and re-checks them every time it uses them.

When MIZAN verifies a program Lisan wrote (it ran in the sandbox and exited
cleanly), it keeps the program, its language and its output, for that user
only. A later request with the same wording and the same numbers re-runs the
kept program instead of asking Lisan again. Every reuse is a regression check:
the output must match what was verified, or the program is distrusted (its
Beta posterior falls) and Lisan writes a new one. A program whose posterior
falls below one half is forgotten.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from core.adaptive import BetaEstimator, bm25_scores

from .taallum import _ASKING, content_words

MAX_PROGRAMS = 100
MIN_OVERLAP = 0.8  # stricter than wording: a program must fit the request exactly
MAX_OUTPUT = 4000
_PRIOR = {"alpha": 2.0, "beta": 1.0, "prior_alpha": 2.0, "prior_beta": 1.0, "forgetting": 0.98}


def _key(user_id: str) -> str:
    return "hifz:" + hashlib.sha256((user_id or "anonymous").encode()).hexdigest()[:24]


def _numbers(text: str) -> list[str]:
    import re

    return sorted(set(re.findall(r"\d+(?:\.\d+)?", text)))


def _load(store: Any, user_id: str) -> list[dict]:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001 - no store: nothing kept
        return []
    return [item for item in data.get("programs", []) if isinstance(item, dict)]


def _save(store: Any, user_id: str, items: list[dict]) -> None:
    kept = [
        item
        for item in items
        if BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean >= 0.5
    ]
    kept = sorted(kept, key=lambda item: item.get("used", 0), reverse=True)[:MAX_PROGRAMS]
    try:
        store.put(_key(user_id), {"programs": kept})
    except Exception:  # noqa: BLE001 - keeping is best effort
        pass


def _same(item: dict, words: list[str], language: str) -> bool:
    return item["tokens"] == words and item["language"] == language


def recall(store: Any, user_id: str, message: str, language: str) -> dict | None:
    """The kept program for this request, if one fits it exactly enough to reuse."""
    words = content_words(message)
    items = [item for item in _load(store, user_id) if item.get("language") == language]
    if not words or not items:
        return None
    scores = bm25_scores(words, [item["tokens"] for item in items])
    best = max(range(len(items)), key=lambda index: scores[index])
    item = items[best]
    tokens = set(item["tokens"])
    overlap = len(tokens & set(words)) / max(1, len(tokens | set(words)))
    if scores[best] <= 0 or overlap < MIN_OVERLAP:
        return None
    if item.get("numbers", []) != _numbers(message):
        return None  # "10 fibonacci" is not "20 fibonacci"
    if (_ASKING & set(words)) - set(item.get("asking", [])):
        return None
    if BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean < 0.5:
        return None
    return item


def keep(store: Any, user_id: str, message: str, language: str, code: str, output: str) -> None:
    """Keep a program MIZAN verified for this request."""
    words = content_words(message)
    if not 2 <= len(words) <= 60 or not code.strip():
        return
    items = [item for item in _load(store, user_id) if not _same(item, words, language)]
    items.append(
        {
            "tokens": words,
            "numbers": _numbers(message),
            "asking": sorted(_ASKING & set(words)),
            "language": language,
            "code": code[:20000],
            "output": output[:MAX_OUTPUT],
            "posterior": BetaEstimator(**_PRIOR).update(True).to_dict(),
            "kept": time.time(),
            "used": time.time(),
            "runs": 1,
        }
    )
    _save(store, user_id, items)


def matches(item: dict, output: str) -> bool:
    return output.strip()[:MAX_OUTPUT] == str(item.get("output", "")).strip()


def record(store: Any, user_id: str, kept: dict, worked: bool) -> float:
    """One reuse of a kept program; returns its new reliability."""
    items = _load(store, user_id)
    mean = 0.0
    for item in items:
        if _same(item, kept["tokens"], kept["language"]):
            posterior = BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).update(worked)
            item["posterior"] = posterior.to_dict()
            item["used"] = time.time()
            item["runs"] = int(item.get("runs", 0)) + 1
            mean = float(posterior.mean)
    _save(store, user_id, items)
    return mean


def summary(store: Any, user_id: str) -> dict:
    items = _load(store, user_id)
    return {
        "programs": len(items),
        "reuses": sum(max(0, int(item.get("runs", 1)) - 1) for item in items),
        "items": [
            {
                "request": " ".join(item["tokens"])[:120],
                "language": item["language"],
                "runs": item.get("runs", 1),
                "reliability": round(
                    float(BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean), 3
                ),
            }
            for item in items[:50]
        ],
    }


def forget(store: Any, user_id: str) -> None:
    try:
        store.put(_key(user_id), {"programs": []})
    except Exception:  # noqa: BLE001
        pass
