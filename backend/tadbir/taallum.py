"""Ta'allum (تعلّم): MIZAN learns new wording from its own verified work.

When Fahm does not recognise a request, Lisan may map its wording to one of
MIZAN's recipes. If MIZAN then verifies the result, it keeps that wording as
an example, for that user only. Later, a message that BM25 finds close to
a kept example is mapped by MIZAN itself, with no Lisan call. Each example
keeps a Beta posterior of how often reusing it verified, and one that
stops working is dropped. The mapping still passes MIZAN's own validation
every time.

Only recipes whose details MIZAN can rebuild from the new message are
learned: write-and-run, web search and building a project. This learns
MIZAN's understanding, not model weights; nothing here becomes training
data for any model.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from core.adaptive import BetaEstimator, bm25_scores, tokenize

LEARNABLE = {"build_and_run", "web_search", "build_project", "use_tool", "edit_project"}
MAX_EXAMPLES = 200
MIN_OVERLAP = 0.6  # share of the example's content words the new message must contain
# Function words carry no intent; they are left out when comparing wording.
_STOP = {
    "a", "an", "the", "of", "to", "is", "are", "in", "on", "and", "or", "for", "me", "my", "i",
    "it", "this", "that", "with", "please", "ka", "ki", "ke", "ko", "se", "mein", "main", "hai",
    "hain", "kya", "aur", "bhi", "toh", "ek", "yeh", "ye", "woh", "do", "karo", "kar", "mujhe",
}  # fmt: skip
# Words that turn a request into a question about it: never reuse across them.
_ASKING = {
    "why", "how", "explain", "meaning", "kyun", "kyon", "kaise", "matlab", "samjhao", "kya",
}  # fmt: skip


def content_words(text: str) -> list[str]:
    return [word for word in tokenize(text) if word not in _STOP and len(word) > 1]


_PRIOR = {"alpha": 2.0, "beta": 1.0, "prior_alpha": 2.0, "prior_beta": 1.0, "forgetting": 0.98}


def _key(user_id: str) -> str:
    digest = hashlib.sha256((user_id or "anonymous").encode()).hexdigest()[:24]
    return f"taallum:{digest}"


def _load(store: Any, user_id: str) -> list[dict]:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001 - no store: nothing learned yet
        return []
    items = data.get("examples", [])
    return [item for item in items if isinstance(item, dict)]


def _save(store: Any, user_id: str, items: list[dict]) -> None:
    items = sorted(items, key=lambda item: item.get("used", 0), reverse=True)[:MAX_EXAMPLES]
    try:
        store.put(_key(user_id), {"examples": items})
    except Exception:  # noqa: BLE001 - learning is best effort
        pass


def template(understanding: Any) -> dict | None:
    """The part of a mapping that does not depend on the exact message."""
    intent = understanding.intent
    entities = understanding.entities
    if intent == "build_and_run":
        return {"intent": intent, "language": entities.get("code_language", "python")}
    if intent in ("web_search", "quran_search"):
        return {"intent": intent}
    if intent == "build_project":
        return {"intent": intent, "kind": entities.get("kind", "web")}
    if intent == "use_tool":
        return {"intent": intent, "need": entities.get("need", "")}
    if intent == "edit_project":
        return {"intent": intent}
    return None


def recall(store: Any, user_id: str, message: str) -> tuple[dict, dict] | None:
    """(parsed mapping for this message, the example used), or None."""
    words = content_words(message)
    items = _load(store, user_id)
    if not words or not items:
        return None
    scores = bm25_scores(words, [item["tokens"] for item in items])
    best = max(range(len(items)), key=lambda index: scores[index])
    item = items[best]
    tokens = set(item["tokens"])
    overlap = len(tokens & set(words)) / max(1, len(tokens))
    if scores[best] <= 0 or overlap < MIN_OVERLAP:
        return None
    if (_ASKING & set(tokenize(message))) - set(item.get("asking", [])):
        return None  # "...ka matlab samjhao" is not the request that was learned
    if BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean < 0.5:
        return None
    parsed = dict(item["template"])
    if parsed["intent"] == "build_and_run":
        parsed["request"] = message
    elif parsed["intent"] == "web_search":
        parsed["query"] = message[:300]
    elif parsed["intent"] == "edit_project":
        parsed["request"] = message[:1500]
    return parsed, item


def learn(store: Any, user_id: str, message: str, understanding: Any, verified: bool) -> None:
    """Keep or reweigh an example after MIZAN checked the result."""
    shape = template(understanding)
    if shape is None:
        return
    words = content_words(message)
    if not 2 <= len(words) <= 60:
        return
    items = _load(store, user_id)
    match = next(
        (item for item in items if item["tokens"] == words and item["template"] == shape), None
    )
    if match is None:
        if not verified:
            return  # only verified work teaches a new example
        asking = sorted(_ASKING & set(tokenize(message)))
        match = {"tokens": words, "template": shape, "asking": asking, "posterior": None}
        items.append(match)
    posterior = BetaEstimator.from_dict(match.get("posterior"), **_PRIOR).update(verified)
    match["posterior"] = posterior.to_dict()
    match["used"] = time.time()
    items = [
        item
        for item in items
        if BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean >= 0.5
    ]
    _save(store, user_id, items)


def reweigh(store: Any, user_id: str, example: dict, verified: bool) -> None:
    """Evidence on an example that was reused for a later message."""
    items = _load(store, user_id)
    for item in items:
        if item["tokens"] == example["tokens"] and item["template"] == example["template"]:
            posterior = BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).update(verified)
            item["posterior"] = posterior.to_dict()
            item["used"] = time.time()
    _save(
        store,
        user_id,
        [
            item
            for item in items
            if BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean >= 0.5
        ],
    )


def summary(store: Any, user_id: str) -> dict:
    items = _load(store, user_id)
    by_intent: dict[str, int] = {}
    for item in items:
        intent = item["template"]["intent"]
        by_intent[intent] = by_intent.get(intent, 0) + 1
    return {"examples": len(items), "by_intent": by_intent}


def forget(store: Any, user_id: str) -> None:
    try:
        store.put(_key(user_id), {"examples": []})
    except Exception:  # noqa: BLE001
        pass
