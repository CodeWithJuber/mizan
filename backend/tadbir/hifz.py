"""Hifz (حفظ): MIZAN keeps the programs it verified and re-checks them every time it uses them.

When MIZAN verifies a program Lisan wrote (it ran in the sandbox and exited
cleanly), it keeps the program, its language and its output, for that user
only. A later request with the same wording and the same numbers re-runs the
kept program instead of asking Lisan again. Every reuse is a regression check:
the output must match what was verified, or the program is distrusted (its
Beta posterior falls) and Lisan writes a new one. A program whose posterior
falls below one half is forgotten. A request of a verified form with other
numbers or other words of the user's is answered by a template made from the
kept programs of that form (``template``).
"""

from __future__ import annotations

import ast
import difflib
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
    said = item.get("request") or " ".join(item["tokens"])
    if _unsaid(item["code"], language, [said], message):
        return None  # "the vowels in banana" holds "banana": not for "mango"
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
#
# A slot may also be a span of the user's own words: "a greeting for Ali" and
# "a greeting for Bilal" share every word but one span, and their programs
# differ only in a string that holds that span. The requests' words are
# anti-unified first (the words they share, in order, are the form; each run
# of other words is a span), then the programs, where a string, or a part of
# one, that holds the request's g-th span in every instance becomes a slot
# bound to that span. A span's value only ever becomes a string constant.

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_TOKEN = re.compile(r"(?P<number>\d+(?:\.\d+)?)|(?P<word>[^\W\d]+)")
MAX_INSTANCES = 8


def _ordered(text: str) -> list[str]:
    """The request's numbers in the order it gives them."""
    return _NUMBER.findall(text)


def _shape(text: str) -> list[str]:
    """The request's content words without its numbers."""
    return [word for word in content_words(text) if not any(ch.isdigit() for ch in word)]


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """The text's words and numbers in order, with where each stands. A word is
    compared without its case; a number is only ``#`` (its value is a number
    slot's)."""
    return [
        (
            "#" if match.lastgroup == "number" else match.group().casefold(),
            match.start(),
            match.end(),
        )
        for match in _TOKEN.finditer(text)
    ]


def _said(text: str) -> set[str]:
    return {key for key, _start, _end in _tokens(text) if key != "#"}


def _held(code: str, language: str) -> set[str]:
    """The words a program holds as data: its strings (Python, read from its
    syntax tree), or any word of it (another language, which is not parsed)."""
    if language.lower() not in {"python", "py"}:
        return _said(code)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _said(code)
    return {
        word
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        for word in _said(node.value)
    }


def _unsaid(code: str, language: str, requests: list[str], message: str) -> bool:
    """The program holds a word that every request it was verified for says
    and this request does not: it was written for their word, not this one's
    ("the vowels in banana" holds "banana"; "the vowels in mango" does not)."""
    if not requests:
        return False
    said = set.intersection(*(_said(request) for request in requests))
    return bool((_held(code, language) & said) - _said(message))


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


def _text_slot(values: list[str], numbers: list[list[str]]) -> tuple | None:
    """A string that differs only in the requests' numbers in it ("F10 =")."""
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
    return ("text", pieces[0], inner)


def _alone(value: str, start: int, end: int) -> bool:
    """value[start:end] is not part of a longer word."""
    return (start == 0 or not value[start - 1].isalnum()) and (
        end == len(value) or not value[end].isalnum()
    )


def _parts(value: str, spans: dict[int, str], alone: bool) -> list[tuple[str, Any]]:
    """The string as literal text, numbers (``digits``) and the request's word
    spans (``word``, the g-th span), the longest span first where two start at
    one place; with ``alone``, a span inside a longer word is text."""
    order = sorted(spans.items(), key=lambda item: (-len(item[1]), item[0]))
    parts: list[tuple[str, Any]] = []
    text, k = "", 0

    def flush() -> None:
        pieces = _NUMBER.split(text)
        for index, number in enumerate(_NUMBER.findall(text)):
            parts.extend([("text", pieces[index]), ("digits", number)])
        parts.append(("text", pieces[-1]))

    while k < len(value):
        for g, span in order:
            end = k + len(span)
            if value.startswith(span, k) and (not alone or _alone(value, k, end)):
                flush()
                parts.append(("word", g))
                text, k = "", end
                break
        else:
            text += value[k]
            k += 1
    flush()
    return [part for part in parts if part != ("text", "")]


def _agree(rows: list[list[tuple[str, Any]]], numbers: list[list[str]]) -> tuple | None:
    """One form of a string for every instance: the same text and the same
    spans in the same places, and each number that differs the j-th number."""
    if len({len(row) for row in rows}) != 1:
        return None
    parts: list[tuple[str, Any]] = []
    for column in zip(*rows, strict=True):
        if len({kind for kind, _ in column}) != 1:
            return None
        kind, values = column[0][0], [value for _, value in column]
        if kind == "digits" and len(set(values)) > 1:
            j = _slot([_value(value) for value in values], numbers)
            if j is None:
                return None
            parts.append(("number", j))
        elif len(set(values)) == 1:
            parts.append(("text" if kind == "digits" else kind, values[0]))
        else:
            return None
    if not any(kind == "word" for kind, _ in parts):
        return None
    return ("words", parts)


def _words_slot(
    values: list[str], numbers: list[list[str]], spans: list[dict[int, str]]
) -> tuple | None:
    """A string that holds the requests' word spans, in every instance at the
    same place: spans read as whole words first, else wherever they stand."""
    for alone in (True, False):
        rows = [_parts(value, own, alone) for value, own in zip(values, spans, strict=True)]
        slot = _agree(rows, numbers)
        if slot is not None:
            return slot
    return None


def _generalise(
    trees: list[ast.AST],
    numbers: list[list[str]],
    spans: list[dict[int, str]] | None = None,
) -> list[tuple[int, Any]] | None:
    """Slots of the trees' least general generalisation, as (position in
    ``ast.walk`` of the first tree, slot), or None when the trees differ in
    anything the requests' numbers (and word ``spans``, the g-th span of each
    instance that varied) do not explain."""
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
                slot = _text_slot(values, numbers)
                if slot is None and spans:
                    slot = _words_slot(values, numbers, spans)
                if slot is None:
                    return None
                slots.append((position, slot))
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


def _instantiate(
    tree: ast.AST,
    slots: list[tuple[int, Any]],
    numbers: list[str],
    spans: list[str] | None = None,
) -> ast.AST:
    """The tree with each slot filled. A slot is always a constant: a number,
    or a string whose parts are text, numbers and the request's word spans, so
    the user's words are data and never code."""
    copy = deepcopy(tree)
    nodes = list(ast.walk(copy))
    for position, slot in slots:
        node = nodes[position]
        assert isinstance(node, ast.Constant)
        if slot[0] == "number":
            node.value = _value(numbers[slot[1]]) + slot[2]
        elif slot[0] == "words":
            node.value = "".join(
                numbers[value]
                if kind == "number"
                else (spans or [])[value]
                if kind == "word"
                else value
                for kind, value in slot[1]
            )
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


def _bound(slots: list[tuple[int, Any]], kind: str) -> set[int]:
    """The request's numbers (``number``) or word spans (``word``) the slots use."""
    used: set[int] = set()
    for _position, slot in slots:
        if slot[0] == "number" and kind == "number":
            used.add(slot[1])
        elif slot[0] == "text" and kind == "number":
            used |= {part for part in slot[2] if isinstance(part, int)}
        elif slot[0] == "words":
            used |= {value for part, value in slot[1] if part == kind}
    return used


def _numbers_hold(numbers: list[str], found: list[list[str]], bound: set[int]) -> bool:
    """General only where it was seen to vary: a number every instance had the
    same, which this request changes, may sit in the program as a literal; and
    a number slot keeps its kind."""
    for j, number in enumerate(numbers):
        column = {numbers_of[j] for numbers_of in found}
        if j not in bound and (len(column) == 1 and number not in column):
            return False  # never seen to vary, and the program may hold it as a literal
        if j in bound:
            types = {type(_value(numbers_of[j])) for numbers_of in found}
            if types != {type(_value(number))}:
                return False  # "10" was an integer in every instance; "2.5" is not
    return True


def template(store: Any, user_id: str, message: str, language: str) -> dict | None:
    """A program for this request made from the verified programs of its form,
    or None. Python programs only (their syntax tree is read). The form's slots
    are the request's numbers, and spans of its words where the requests of
    the form differ in words."""
    if language.lower() not in {"python", "py"}:
        return None
    return _by_numbers(store, user_id, message, language) or _by_words(
        store, user_id, message, language
    )


def _by_numbers(store: Any, user_id: str, message: str, language: str) -> dict | None:
    """A template from requests with the same words apart from their numbers."""
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
    if not _numbers_hold(numbers, found, _bound(slots, "number")):
        return None
    code = ast.unparse(_instantiate(trees[0], slots, numbers))
    if _unsaid(code, language, [item["request"] for item in distinct], message):
        return None  # a word the instances shared, held as data, is not this request's
    return {
        "code": code,
        "language": language,
        "instances": len(distinct),
        "slots": len(slots),
        "requests": [item["request"][:200] for item in distinct],
    }


def _shared(mine: list[str], theirs: list[str]) -> dict[int, int] | None:
    """Where another request has each word of this one that the two share,
    when they differ only in spans that each fills with other words: no word
    is only added or only left out, and every number stands where it stood."""
    shared: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, mine, theirs, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            shared.update((i, j1 + i - i1) for i in range(i1, i2))
        elif tag != "replace" or "#" in mine[i1:i2] or "#" in theirs[j1:j2]:
            return None
    return shared


def _gaps(size: int, frame: frozenset[int]) -> list[tuple[int, int]]:
    """The runs of positions outside the frame, as [start, end)."""
    gaps: list[tuple[int, int]] = []
    start: int | None = None
    for position in range(size + 1):
        inside = position < size and position not in frame
        if inside and start is None:
            start = position
        elif not inside and start is not None:
            gaps.append((start, position))
            start = None
    return gaps


def _spans(
    text: str,
    tokens: list[tuple[str, int, int]],
    gaps: list[tuple[int, int]],
    where: dict[int, int],
    size: int,
) -> list[tuple[str, int]]:
    """Each gap's span in a request, as the user wrote it (from its first word
    to its last, with what stands between them), and its length in words.
    ``where`` maps the new request's frame positions to this request's;
    ``size`` is the new request's length in tokens."""
    spans = []
    for start, end in gaps:
        first = where[start - 1] + 1 if start > 0 else 0
        last = where[end] - 1 if end < size else len(tokens) - 1
        spans.append((text[tokens[first][1] : tokens[last][2]], last - first + 1))
    return spans


def _by_words(store: Any, user_id: str, message: str, language: str) -> dict | None:
    """A template from requests with the same words apart from their numbers
    and spans of other words: the most specific form this request shares with
    two or more kept requests that differ in those spans."""
    mine = _tokens(message)
    keys = [key for key, _start, _end in mine]
    asking = _ASKING & set(content_words(message))
    count = len(_ordered(message))
    candidates = []
    for item in sorted(_load(store, user_id), key=lambda item: -item.get("used", 0)):
        if item.get("language") != language or not _trusted(item):
            continue
        request = item.get("request") or ""
        if not request or set(item.get("asking", [])) != asking:
            continue
        if len(_ordered(request)) != count:
            continue
        theirs = _tokens(request)
        where = _shared(keys, [key for key, _start, _end in theirs])
        if where is not None:
            candidates.append((item, theirs, where))
        if len(candidates) == MAX_INSTANCES:
            break
    # The forms this request shares with the kept requests: each one's shared
    # words, and every intersection of them (a form of more requests).
    frames: set[frozenset[int]] = set()
    for _item, _theirs, where in candidates:
        own = frozenset(where)
        frames |= {own} | {own & frame for frame in frames}
    for frame in sorted(frames, key=lambda frame: (-len(frame), sorted(frame))):
        chosen = [entry for entry in candidates if frame <= entry[2].keys()]
        made = _form(message, mine, frame, chosen, language)
        if made is not None:
            return made
    return None


def _form(
    message: str,
    mine: list[tuple[str, int, int]],
    frame: frozenset[int],
    chosen: list[tuple[dict, list[tuple[str, int, int]], dict[int, int]]],
    language: str,
) -> dict | None:
    """The template of one form (the new request's words at ``frame``), from
    the kept requests that share it, or None."""
    gaps = _gaps(len(mine), frame)
    if not gaps or len(chosen) < 2:
        return None
    own = _spans(message, mine, gaps, {p: p for p in range(len(mine))}, len(mine))
    numbers = _ordered(message)
    rows: list[tuple[dict, list[tuple[str, int]]]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for item, theirs, where in chosen:
        spans = _spans(item["request"], theirs, gaps, where, len(mine))
        key = (tuple(_ordered(item["request"])), tuple(text for text, _ in spans))
        if key not in seen:
            seen.add(key)
            rows.append((item, spans))
    if (tuple(numbers), tuple(text for text, _ in own)) in seen:
        return None  # this very request was kept: recall's, not a template's
    texts = [[text for text, _ in spans] for _item, spans in rows]
    if len({tuple(row) for row in texts}) < 2:
        return None  # at least two instances with different spans
    # The form is what the requests are about, like memory.dhikr.same_frame:
    # two words or more, one of them above the information of an average word
    # of general language, and no request's spans longer than the form.
    words = [mine[position][0] for position in sorted(frame) if mine[position][0] != "#"]
    if len(words) < 2:
        return None
    if any(
        sum(length for _, length in spans) > len(words)
        for spans in [own, *(spans for _item, spans in rows)]
    ):
        return None
    from .ahl_dhikr import average_information, information

    if not any(information(word) > average_information() for word in words):
        return None
    try:
        trees = [ast.parse(item["code"]) for item, _spans in rows]
    except SyntaxError:
        return None
    found = [_ordered(item["request"]) for item, _spans in rows]
    # A span that never varied gets no slot: only the varied ones are looked for.
    varied = [g for g in range(len(gaps)) if len({row[g] for row in texts}) > 1]
    slots = _generalise(trees, found, [{g: row[g] for g in varied} for row in texts])
    if not slots:
        return None
    # Test-guided acceptance: every instance comes back exactly.
    for tree, numbers_of, row in zip(trees, found, texts, strict=True):
        if ast.dump(_instantiate(trees[0], slots, numbers_of, row)) != ast.dump(tree):
            return None
    if not _numbers_hold(numbers, found, _bound(slots, "number")):
        return None
    bound = _bound(slots, "word")
    for g, (text, length) in enumerate(own):
        column = {row[g] for row in texts}
        if g not in bound and len(column) == 1 and text not in column:
            return None  # never seen to vary, and the program may hold it
        if g in bound and length not in {spans[g][1] for _item, spans in rows}:
            return None  # one word in every instance; two words is another form
    tree = _instantiate(trees[0], slots, numbers, [text for text, _ in own])
    code = ast.unparse(tree)
    try:
        # What runs is exactly the tree made: the user's words stay a constant.
        if ast.dump(ast.parse(code)) != ast.dump(tree):
            return None
    except SyntaxError:
        return None
    if _unsaid(code, language, [item["request"] for item, _spans in rows], message):
        return None
    return {
        "code": code,
        "language": language,
        "instances": len(rows),
        "slots": len(slots),
        "words": len(bound),
        "requests": [item["request"][:200] for item, _spans in rows],
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
