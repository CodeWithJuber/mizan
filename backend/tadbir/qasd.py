"""Qasd (قصد): what a request is for, as a posterior over MIZAN's recipes.

A naive Bayes model (``core.tamyiz``) reads three kinds of evidence:

- the request's own words, as character n-grams and words, so spelling
  variants and code-mixed Hinglish share evidence;
- what MIZAN's parsers find in it (``e:qref`` a valid Quran reference,
  ``e:expr`` an exact calculation, ``e:url`` a link the user wrote, …): the
  parsers are grammars, and the model learns how much each finding counts;
- the context (``c:project`` when a coding project is selected).

It is fitted on the seed examples in ``data/qasd`` (the smoothing and the
weight of each kind of evidence by leave-one-out), and every request MIZAN carries out and verifies after
Lisan had to map it is added to that user's own counts, so the next one like
it is understood without a model call. ``converse`` (answer in words) is a
class with its own examples: MIZAN acts only when an action is more probable
than conversation, and no threshold is set by hand.

Two yes/no facets are separate models: ``current`` (the answer depends on
something current or outside MIZAN) and ``harder`` (the user asks for more
effort on what came before).
"""

from __future__ import annotations

import hashlib
import threading
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

from core.tamyiz import Overlay, Tamyiz, char_ngrams, letters

SEEDS = Path(__file__).parent / "data" / "qasd"
PROJECT = "\x1eproject\x1e"
_LOCK = threading.Lock()
MAX_LEARNED = 400  # learned examples kept per user (storage bound, oldest first out)


def compose(message: str, project: bool) -> str:
    return (PROJECT if project else "") + message


def _features(text: str) -> Counter[str]:
    from . import fahm

    project = text.startswith(PROJECT)
    message = text[len(PROJECT) :] if project else text
    found: Counter[str] = Counter()
    for token in fahm.evidence(message):
        found["e:" + token] += 1
    if project:
        found["c:project"] += 1
    words = letters(fahm.plain_words(message)).lower()
    found.update(char_ngrams(words, (2, 3, 4)))
    found.update("w:" + word for word in words.split())
    return found


def _rows(name: str) -> list[list[str]]:
    rows = []
    for line in (SEEDS / name).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(line.split("\t"))
    return rows


def _text(raw: str) -> str:
    text = raw.replace("\\n", "\n")
    return compose(text[len("[project] ") :], True) if text.startswith("[project] ") else text


# Intents that work on the selected project; for every other intent, whether a
# project is selected says nothing about the intent (P(c:project | intent) is the
# same), so each of their examples is counted in both contexts.
PROJECT_INTENTS = {"run_file", "project_task", "edit_project"}


def examples() -> list[tuple[str, ...]]:
    found: list[tuple[str, ...]] = []
    for number, (label, text) in enumerate(_rows("intents.tsv")):
        if label not in PROJECT_INTENTS and not text.startswith("[project] "):
            group = f"seed:{number}"  # both contexts are held out together
            found += [(_text(text), label, group), (compose(_text(text), True), label, group)]
        else:
            found.append((_text(text), label))
    return found


def facet_examples(facet: str) -> list[tuple[str, str]]:
    return [(_text(text), label) for name, label, text in _rows("facets.tsv") if name == facet]


@cache
def model() -> Tamyiz:
    with _LOCK:
        from core.tamyiz_cache import fitted

        return fitted("qasd", _features, examples)


@cache
def facet_model(facet: str) -> Tamyiz:
    with _LOCK:
        from core.tamyiz_cache import fitted

        return fitted(f"qasd.{facet}", _features, lambda: facet_examples(facet))


def posterior(message: str, project: bool = False, overlay: Overlay | None = None) -> dict:
    found: dict[str, float] = model().posterior(compose(message, project), overlay)
    return found


def ranked(
    message: str, project: bool = False, overlay: Overlay | None = None
) -> list[tuple[str, float]]:
    found = posterior(message, project, overlay)
    return sorted(found.items(), key=lambda item: -item[1])


def prefers(message: str, first: str, second: str, project: bool = False) -> bool:
    """The model finds ``first`` more probable than ``second`` for this message."""
    found = posterior(message, project)
    return bool(found.get(first, 0.0) > found.get(second, 0.0))


def facet(name: str, message: str) -> bool:
    found: dict[str, float] = facet_model(name).posterior(message)
    return found.get("yes", 0.0) > found.get("no", 0.0)


# ── learning from verified work, per user ───────────────────────────────


def _key(user_id: str) -> str:
    return "qasd:" + hashlib.sha256((user_id or "anonymous").encode()).hexdigest()[:24]


def overlay(store: Any, user_id: str) -> Overlay | None:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001 - no store: nothing learned yet
        return None
    return Overlay.from_dict(data.get("overlay")) if data.get("overlay") else None


def learn(store: Any, user_id: str, message: str, intent: str, project: bool) -> bool:
    """Add one verified request to this user's counts (once per wording)."""
    if intent not in model().labels or not message.strip():
        return False
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001
        return False
    text = compose(message.strip(), project)
    digest = hashlib.sha256(f"{intent}\t{text}".encode()).hexdigest()[:16]
    seen = list(data.get("seen") or [])
    if digest in seen:
        return False
    learned = list(data.get("examples") or [])
    learned.append({"intent": intent, "text": text[:2000]})
    learned = learned[-MAX_LEARNED:]
    rebuilt = Overlay()
    vectorize = model().vector
    for item in learned:
        rebuilt.add(item["intent"], vectorize(item["text"]))
    try:
        store.put(
            _key(user_id),
            {
                "overlay": rebuilt.to_dict(),
                "examples": learned,
                "seen": [*seen, digest][-MAX_LEARNED:],
            },
        )
    except Exception:  # noqa: BLE001
        return False
    return True


def summary(store: Any, user_id: str) -> dict:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001
        data = {}
    learned = data.get("examples") or []
    return {
        "learned": len(learned),
        "by_intent": dict(Counter(item.get("intent") for item in learned)),
        "model": model().state(),
    }
