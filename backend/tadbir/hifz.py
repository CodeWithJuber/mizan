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

import ast
import hashlib
import re
import time
from copy import deepcopy
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
    return bool(item["tokens"] == words and item["language"] == language)


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


def keep(
    store: Any,
    user_id: str,
    message: str,
    language: str,
    code: str,
    output: str,
    *,
    checked: bool = False,
) -> None:
    """Keep a program MIZAN verified for this request. ``checked``: an
    independent program agreed with its result (Tathabbut)."""
    words = content_words(message)
    if not 2 <= len(words) <= 60 or not code.strip():
        return
    items = [item for item in _load(store, user_id) if not _same(item, words, language)]
    items.append(
        {
            "tokens": words,
            "numbers": _numbers(message),
            # The request itself, so its numbers' order is known (templates).
            "request": message[:2000],
            "asking": sorted(_ASKING & set(words)),
            "language": language,
            "code": code[:20000],
            "output": output[:MAX_OUTPUT],
            "posterior": BetaEstimator(**_PRIOR).update(True).to_dict(),
            "kept": time.time(),
            "used": time.time(),
            "runs": 1,
            "checked": checked,
        }
    )
    _save(store, user_id, items)


def mark_checked(store: Any, user_id: str, kept: dict) -> None:
    """An independent program has since agreed with this kept program."""
    items = _load(store, user_id)
    for item in items:
        if _same(item, kept["tokens"], kept["language"]):
            item["checked"] = True
    _save(store, user_id, items)


def drop(store: Any, user_id: str, kept: dict) -> None:
    """Forget one kept program: an independent program disagreed with it."""
    items = [i for i in _load(store, user_id) if not _same(i, kept["tokens"], kept["language"])]
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


# ── templates: one verified program for every request of its form ────────
#
# Two verified programs for "the first 10 Fibonacci numbers" and "the first 20
# Fibonacci numbers" differ only where the request's numbers differ. Their
# least general generalisation (Plotkin's anti-unification, unique up to
# renaming for first-order terms) keeps everything they share and turns each
# difference into a slot bound to the j-th number of the request. The template
# is kept only if putting each instance's numbers back reproduces that
# instance's program exactly, and it is general only where it was seen to
# vary: a number every instance had the same, and which the new request
# changes, may sit in the program as a literal, so the template is not used.
# The kept programs stay the authority; the template is computed from them.

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
MAX_INSTANCES = 8


def _ordered(text: str) -> list[str]:
    """The request's numbers in the order it gives them."""
    return _NUMBER.findall(text)


def _shape(text: str) -> list[str]:
    """The request's content words without its numbers."""
    return [word for word in content_words(text) if not any(ch.isdigit() for ch in word)]


def _value(number: str) -> int | float:
    return float(number) if "." in number else int(number)


def _slot(values: list[Any], numbers: list[list[str]]) -> int | None:
    """The one position j of the requests' numbers that every value equals."""
    fits = _fits(values, numbers)
    exact = [j for j, offset in fits if offset == 0]
    return exact[0] if len(exact) == 1 else None


def _fits(values: list[Any], numbers: list[list[str]]) -> list[tuple[int, int]]:
    """Every (j, b) with each value equal to its request's j-th number plus b,
    the same b for all. An offset (``range(1, 11)`` for "1 to 10") is one
    parameter that the instances measure more than once, so their agreement on
    it is itself a test; it is allowed between whole numbers only."""
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        return []
    if len({type(value) for value in values}) != 1:
        return []
    fits = []
    for j in range(len(numbers[0])):
        given = [_value(found[j]) for found in numbers]
        if any(
            type(number) is not type(value) for number, value in zip(given, values, strict=True)
        ):
            continue
        offsets = {value - number for number, value in zip(given, values, strict=True)}
        if len(offsets) == 1:
            offset = offsets.pop()
            if offset == 0 or isinstance(values[0], int):
                fits.append((j, int(offset) if isinstance(values[0], int) else 0))
    return fits


def _number_slot(values: list[Any], numbers: list[list[str]]) -> tuple[int, int] | None:
    """The slot a differing number fills: the request's j-th number exactly when
    exactly one position gives it, else the one position that gives it with an
    offset."""
    fits = _fits(values, numbers)
    exact = [fit for fit in fits if fit[1] == 0]
    if exact:
        return exact[0] if len(exact) == 1 else None
    return fits[0] if len(fits) == 1 else None


def _generalise(trees: list[ast.AST], numbers: list[list[str]]) -> list[tuple[int, Any]] | None:
    """Slots of the trees' least general generalisation, as (position in
    ``ast.walk`` of the first tree, slot), or None when the trees differ in
    anything the requests' numbers do not explain."""
    walks = [list(ast.walk(tree)) for tree in trees]
    if len({len(walk) for walk in walks}) != 1:
        return None
    slots: list[tuple[int, Any]] = []
    for position, nodes in enumerate(zip(*walks, strict=True)):
        if len({type(node) for node in nodes}) != 1:
            return None
        first = nodes[0]
        if isinstance(first, ast.Constant):
            values = [node.value for node in nodes]
            if all(value == values[0] and type(value) is type(values[0]) for value in values):
                continue
            if all(isinstance(value, str) for value in values):
                pieces = [_NUMBER.split(value) for value in values]
                found = [_NUMBER.findall(value) for value in values]
                if len({tuple(piece) for piece in pieces}) != 1:
                    return None
                if len({len(numbers_in) for numbers_in in found}) != 1:
                    return None
                inner: list[int | str] = []
                for k in range(len(found[0])):
                    column = [numbers_in[k] for numbers_in in found]
                    if len(set(column)) == 1:
                        inner.append(column[0])
                        continue
                    j = _slot([_value(value) for value in column], numbers)
                    if j is None:
                        return None
                    inner.append(j)
                slots.append((position, ("text", pieces[0], inner)))
                continue
            fit = _number_slot(values, numbers)
            if fit is None:
                return None
            slots.append((position, ("number", *fit)))
            continue
        for name in first._fields:
            fields = [getattr(node, name, None) for node in nodes]
            if isinstance(fields[0], ast.AST):
                continue  # compared at its own position in the walk
            if isinstance(fields[0], list):
                lists = [field for field in fields if isinstance(field, list)]
                if len(lists) != len(fields) or len({len(field) for field in lists}) != 1:
                    return None
                if any(not isinstance(element, ast.AST) for field in lists for element in field):
                    if len({repr(field) for field in lists}) != 1:
                        return None
                continue
            if len({repr(field) for field in fields}) != 1:
                return None
    return slots


def _instantiate(tree: ast.AST, slots: list[tuple[int, Any]], numbers: list[str]) -> ast.AST:
    copy = deepcopy(tree)
    nodes = list(ast.walk(copy))
    for position, slot in slots:
        node = nodes[position]
        assert isinstance(node, ast.Constant)
        if slot[0] == "number":
            node.value = _value(numbers[slot[1]]) + slot[2]
        else:
            _, pieces, inner = slot
            text = pieces[0]
            for index, part in enumerate(inner):
                text += (numbers[part] if isinstance(part, int) else part) + pieces[index + 1]
            node.value = text
    return copy


def _trusted(item: dict) -> bool:
    from . import tathabbut

    reliable = BetaEstimator.from_dict(item.get("posterior"), **_PRIOR).mean >= 0.5
    # A program that printed numbers counts only once an independent program
    # agreed with it (Tathabbut).
    return reliable and (bool(item.get("checked")) or not tathabbut.applies(item["output"]))


def template(store: Any, user_id: str, message: str, language: str) -> dict | None:
    """A program for this request made from the verified programs of its form,
    or None. Python programs only (their syntax tree is read)."""
    if language.lower() not in {"python", "py"}:
        return None
    shape, numbers = _shape(message), _ordered(message)
    if not shape or not numbers:
        return None
    asking = _ASKING & set(content_words(message))
    instances = []
    for item in _load(store, user_id):
        if item.get("language") != language or not _trusted(item):
            continue
        request = item.get("request") or ""
        if not request:
            continue  # kept before templates: its request's numbers are not in order
        theirs = _shape(request)
        overlap = len(set(theirs) & set(shape)) / max(1, len(set(theirs) | set(shape)))
        if overlap < MIN_OVERLAP or set(item.get("asking", [])) != asking:
            continue
        if len(_ordered(request)) != len(numbers):
            continue
        instances.append(item)
    instances = sorted(instances, key=lambda item: item.get("used", 0), reverse=True)
    seen: set[tuple[str, ...]] = set()
    distinct = []
    for item in instances:
        key = tuple(_ordered(item["request"]))
        if key not in seen:
            seen.add(key)
            distinct.append(item)
    distinct = distinct[:MAX_INSTANCES]
    if len(distinct) < 2 or tuple(numbers) in seen:
        return None
    try:
        trees = [ast.parse(item["code"]) for item in distinct]
    except SyntaxError:
        return None
    found = [_ordered(item["request"]) for item in distinct]
    slots = _generalise(trees, found)
    if not slots:
        return None
    # Test-guided acceptance: every instance comes back exactly.
    for tree, numbers_of in zip(trees, found, strict=True):
        if ast.dump(_instantiate(trees[0], slots, numbers_of)) != ast.dump(tree):
            return None
    bound = {slot[1] for _, slot in slots if slot[0] == "number"} | {
        part for _, slot in slots if slot[0] == "text" for part in slot[2] if isinstance(part, int)
    }
    for j, number in enumerate(numbers):
        column = {numbers_of[j] for numbers_of in found}
        if j not in bound and (len(column) == 1 and number not in column):
            return None  # never seen to vary, and the program may hold it as a literal
        if j in bound:
            types = {type(_value(numbers_of[j])) for numbers_of in found}
            if types != {type(_value(number))}:
                return None  # "10" was an integer in every instance; "2.5" is not
    code = ast.unparse(_instantiate(trees[0], slots, numbers))
    return {
        "code": code,
        "language": language,
        "instances": len(distinct),
        "slots": len(slots),
        "requests": [item["request"][:200] for item in distinct],
    }


# ── cases: what Lisan sees when it must still write ──────────────────────
#
# When no kept program or template answers a request, Lisan writes one. It is
# shown this user's verified programs nearest the request (Memento's case
# memory: gains plateau at four cases), so a request of a known form is
# written in the known shape, and the next one of that form can be answered
# by a template. Tathabbut's independent program never sees them.

CASES = 4
CASE_CODE = 2000


def cases(store: Any, user_id: str, message: str, language: str, k: int = CASES) -> list[dict]:
    """This user's verified programs nearest the request, the nearest first."""
    shape = _shape(message)
    items = [
        item
        for item in _load(store, user_id)
        if item.get("language") == language and _trusted(item) and item.get("request")
    ]
    if not shape or not items:
        return []
    scores = bm25_scores(shape, [_shape(item["request"]) for item in items])
    ranked = sorted(range(len(items)), key=lambda index: -scores[index])
    return [items[index] for index in ranked if scores[index] > 0][:k]


def render(found: list[dict]) -> str:
    if not found:
        return ""
    parts = [
        "Programs MIZAN verified for this user's earlier requests of a similar kind. When "
        "this request has the same form, write it the same way, changing only what the "
        "request changes:"
    ]
    for item in found:
        parts.append(
            f"Request: {item['request'][:300]}\n```{item['language']}\n"
            f"{item['code'][:CASE_CODE]}\n```"
        )
    return "\n\n".join(parts)
