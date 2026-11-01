"""Tajriba (تجربة): lessons MIZAN draws from its own repaired failures.

Terminal-RSI (arXiv:2610.22192) turns verifier outcomes into policy updates by
rewriting failed or partial trajectories into verified ones; HERD
(arXiv:2610.31401) keeps the cases its skills miss in a bounded memory. MIZAN
does both without touching model weights. When a program failed in its
sandbox and a repair then verified, MIZAN keeps the lesson: the error (as a
signature without the user's names and values), the change that fixed it,
and the kind of work. The next time Lisan writes or repairs code for similar
work, MIZAN gives it the most relevant verified lessons. Each lesson keeps a
Beta posterior of how often the work it was shown for then verified; lessons
that stop helping are dropped, and the memory is bounded. Lessons are kept
per user.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import time
from typing import Any

from core.adaptive import BetaEstimator, bm25_scores, tokenize

MAX_LESSONS = 60
SHOWN = 3
_PRIOR = {"alpha": 2.0, "beta": 1.0, "prior_alpha": 2.0, "prior_beta": 1.0, "forgetting": 0.98}
_EXCEPTION = re.compile(r"\b([A-Z]\w*(?:Error|Exception|Warning))\b:?\s*(.*)")


def _key(user_id: str) -> str:
    return "tajriba:" + hashlib.sha256((user_id or "anonymous").encode()).hexdigest()[:24]


def signature(error: str) -> str:
    """The error's kind and message with names, paths and numbers replaced."""
    lines = [line for line in (error or "").splitlines() if line.strip()]
    for line in reversed(lines):
        match = _EXCEPTION.search(line)
        if match:
            message = re.sub(r"'[^']*'|\"[^\"]*\"", "<name>", match.group(2))
            message = re.sub(r"\d+", "<n>", message)
            return f"{match.group(1)}: {message.strip()}"[:160]
    return (lines[-1] if lines else "")[:160]


def change(failing: str, fixed: str, limit: int = 30) -> str:
    """The lines the verified repair changed."""
    diff = difflib.unified_diff(
        failing.splitlines(), fixed.splitlines(), "failed", "verified", lineterm="", n=0
    )
    lines = [line for line in diff if not line.startswith(("---", "+++", "@@"))]
    return "\n".join(lines[:limit])


def _load(store: Any, user_id: str) -> list[dict]:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001 - no store: no lessons yet
        return []
    return [item for item in data.get("lessons", []) if isinstance(item, dict)]


def _mean(item: dict) -> float:
    return float(BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean)


def _save(store: Any, user_id: str, items: list[dict]) -> None:
    kept = [item for item in items if _mean(item) >= 0.5]
    kept = sorted(kept, key=lambda item: item.get("used", 0), reverse=True)[:MAX_LESSONS]
    try:
        store.put(_key(user_id), {"lessons": kept})
    except Exception:  # noqa: BLE001 - learning is best effort
        pass


def _chat() -> str:
    """The chat this lesson is learned in, so erasing the chat erases it (Mahw)."""
    try:
        from workspace.context import current_chat_session

        return str(current_chat_session() or "")
    except Exception:  # noqa: BLE001 - outside a chat there is none
        return ""


def _tokens(sig: str, request: str) -> list[str]:
    return list(tokenize(f"{sig} {request}"))[:80]


def learn(
    store: Any, user_id: str, kind: str, request: str, failing: str, error: str, fixed: str
) -> dict | None:
    """Keep the lesson of one failure that a verified repair resolved."""
    sig = signature(error)
    diff = change(failing, fixed)
    if not sig or not diff:
        return None
    chat = _chat()
    items = _load(store, user_id)
    for item in items:
        if item["kind"] == kind and item["signature"] == sig:
            item["change"] = diff  # the latest verified way of fixing it
            item["used"] = time.time()
            chats = item.setdefault("chats", [])
            if chat and chat not in chats:
                chats.append(chat)
            _save(store, user_id, items)
            return item
    lesson = {
        "id": hashlib.sha256(f"{kind}|{sig}|{diff}".encode()).hexdigest()[:12],
        "kind": kind,
        "signature": sig,
        "change": diff,
        "tokens": _tokens(sig, request),
        "posterior": BetaEstimator(**_PRIOR).to_dict(),
        "used": time.time(),
        "chats": [chat] if chat else [],
    }
    items.append(lesson)
    _save(store, user_id, items)
    return lesson


def relevant(store: Any, user_id: str, kind: str, text: str, k: int = SHOWN) -> list[dict]:
    """The verified lessons most related to this work (BM25), most useful first."""
    items = [item for item in _load(store, user_id) if item["kind"] == kind]
    if not items:
        return []
    scores = bm25_scores(tokenize(text), [item["tokens"] for item in items])
    ranked = sorted(
        (pair for pair in zip(scores, items, strict=True) if pair[0] > 0),
        key=lambda pair: pair[0] * (0.5 + _mean(pair[1])),
        reverse=True,
    )
    return [item for _score, item in ranked[:k]]


def render(lessons: list[dict]) -> str:
    if not lessons:
        return ""
    parts = ["Lessons MIZAN verified in earlier work (a failure and the change that fixed it):"]
    for lesson in lessons:
        parts.append(f"- {lesson['signature']}\n{lesson['change']}")
    return "\n".join(parts)


def credit(store: Any, user_id: str, lessons: list[dict], worked: bool) -> None:
    """The work these lessons were shown for verified, or did not."""
    if not lessons:
        return
    shown = {lesson["id"] for lesson in lessons}
    items = _load(store, user_id)
    for item in items:
        if item["id"] in shown:
            posterior = BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).update(worked)
            item["posterior"] = posterior.to_dict()
            item["used"] = time.time()
    _save(store, user_id, items)


def summary(store: Any, user_id: str) -> dict:
    items = _load(store, user_id)
    return {
        "lessons": len(items),
        "items": [
            {
                "kind": item["kind"],
                "signature": item["signature"],
                "usefulness": round(_mean(item), 3),
            }
            for item in items[:30]
        ],
    }


def unlearn(store: Any, user_id: str, chat: str, requests: list[str]) -> int:
    """Drop the lessons learned in an erased chat (Mahw): those that name it, and
    older ones whose words are exactly one of its requests'. A lesson also used in
    another chat goes too: its words or its repair came from the erased one."""

    def came_from(item: dict) -> bool:
        if chat and chat in (item.get("chats") or []):
            return True
        return any(
            item.get("tokens") == _tokens(str(item.get("signature", "")), request)
            for request in requests
        )

    items = _load(store, user_id)
    kept = [item for item in items if not came_from(item)]
    if len(kept) != len(items):
        try:
            store.put(_key(user_id), {"lessons": kept})
        except Exception:  # noqa: BLE001
            return 0
    return len(items) - len(kept)


def forget(store: Any, user_id: str) -> None:
    try:
        store.put(_key(user_id), {"lessons": []})
    except Exception:  # noqa: BLE001
        pass
