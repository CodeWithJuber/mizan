"""Nazm (نظم, ordered arrangement): checks of the form an answer was asked to take.

"Exactly three sentences", "under 50 words", "no commas", "a bulleted list of
four", "as JSON with the keys name and age": constraints a reader can check by
counting, so MIZAN checks them by counting rather than trusting the wording.
Each check is typed (``KINDS``) and returns whether it holds and what was found.

Used twice, with one implementation:

- the Imtihan ``constraints`` scorer (generation faculty), whose items carry
  their checks
- MIZAN's own answers (``agents/base.py``): Lisan reads the checks out of the
  request (``Lisan.constraints``), each with the words of the request it rests
  on; MIZAN keeps only checks whose words are in the request, counts the
  answer against them and has the answer rewritten once with what failed
"""

from __future__ import annotations

import json
import re
from typing import Any

_SENTENCE_END = re.compile(r"(?<=[.!?؟।۔])[\"'”’)\]]*\s+|(?<=[.!?؟।۔])[\"'”’)\]]*$")
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_BULLET = re.compile(r"^\s*(?:[-*•‣▪]|•)\s+\S")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+\S")
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
_SCRIPTS = {
    "arabic": re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]"),
    "devanagari": re.compile(r"[ऀ-ॿ]"),
    "latin": re.compile(r"[A-Za-zÀ-ɏ]"),
    "tamil": re.compile(r"[஀-௿]"),
}
KINDS = (
    "sentences", "words", "lines", "paragraphs", "bullets", "numbered", "include", "exclude",
    "no_char", "lowercase", "uppercase", "starts_with", "ends_with", "json", "script",
)  # fmt: skip


def sentences(text: str) -> list[str]:
    body = " ".join(line.strip() for line in (text or "").strip().splitlines() if line.strip())
    return [part.strip() for part in _SENTENCE_END.split(body) if part and part.strip()]


def words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def _lines(text: str) -> list[str]:
    return [line for line in (text or "").splitlines() if line.strip()]


def _count(found: int, check: dict) -> tuple[bool, str]:
    ok = True
    if "exact" in check:
        ok = found == int(check["exact"])
    if "min" in check:
        ok = ok and found >= int(check["min"])
    if "max" in check:
        ok = ok and found <= int(check["max"])
    bounds = ", ".join(f"{key} {check[key]}" for key in ("exact", "min", "max") if key in check)
    return ok, f"{found} ({bounds})"


def _has(text: str, word: str) -> bool:
    pattern = re.escape(word.lower())
    # A word is matched whole where it begins/ends with a letter or digit.
    if word[:1].isalnum():
        pattern = r"(?<![^\W_])" + pattern
    if word[-1:].isalnum():
        pattern += r"(?![^\W_])"
    return re.search(pattern, text.lower()) is not None


def _json(text: str) -> Any:
    fenced = _FENCE.search(text or "")
    candidate = (fenced.group(1) if fenced else text or "").strip()
    try:
        return json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(candidate[start : end + 1])
            except ValueError:
                return None
    return None


def check_one(text: str, check: dict) -> dict:
    """{"kind", "ok", "found"} for one typed check."""
    kind = check.get("kind")
    text = (text or "").strip()
    ok: bool
    found: str
    if kind == "sentences":
        ok, found = _count(len(sentences(text)), check)
    elif kind == "words":
        ok, found = _count(len(words(text)), check)
    elif kind == "lines":
        ok, found = _count(len(_lines(text)), check)
    elif kind == "paragraphs":
        parts = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
        ok, found = _count(len(parts), check)
    elif kind == "bullets":
        ok, found = _count(sum(bool(_BULLET.match(line)) for line in _lines(text)), check)
    elif kind == "numbered":
        ok, found = _count(sum(bool(_NUMBERED.match(line)) for line in _lines(text)), check)
    elif kind == "include":
        missing = [word for word in check.get("words", []) if not _has(text, str(word))]
        ok, found = not missing, f"missing {missing}" if missing else "all present"
    elif kind == "exclude":
        present = [word for word in check.get("words", []) if _has(text, str(word))]
        ok, found = not present, f"present {present}" if present else "none present"
    elif kind == "no_char":
        present = [char for char in str(check.get("chars", "")) if char in text]
        ok, found = not present, f"has {present}" if present else "none"
    elif kind == "lowercase":
        ok, found = text == text.lower(), "lower case" if text == text.lower() else "has capitals"
    elif kind == "uppercase":
        ok, found = text == text.upper(), "upper case" if text == text.upper() else "has small"
    elif kind == "starts_with":
        expected = str(check.get("text", ""))
        ok = text.lower().startswith(expected.lower())
        found = repr(text[: len(expected) + 10])
    elif kind == "ends_with":
        expected = str(check.get("text", "")).rstrip()
        ok = text.rstrip().lower().endswith(expected.lower())
        found = repr(text[-(len(expected) + 10) :])
    elif kind == "json":
        value = _json(text)
        keys = [str(key) for key in check.get("keys", [])]
        missing = [key for key in keys if not isinstance(value, dict) or key not in value]
        ok = value is not None and not missing
        found = "not JSON" if value is None else f"missing keys {missing}" if missing else "JSON"
    elif kind == "script":
        pattern = _SCRIPTS.get(str(check.get("name", "")).lower())
        letters = [char for char in text if char.isalpha()]
        share = (
            sum(bool(pattern.match(char)) for char in letters) / len(letters)
            if pattern and letters
            else 0.0
        )
        # Most letters in the script: a borrowed word or a name may be in another.
        ok, found = share > 0.5, f"{round(share * 100)}% of letters"
    else:
        return {"kind": kind, "ok": False, "found": "unknown check"}
    return {"kind": kind, "ok": bool(ok), "found": found}


def check(text: str, checks: list[dict]) -> list[dict]:
    return [check_one(text, item) for item in checks if isinstance(item, dict)]


def failed(results: list[dict]) -> list[dict]:
    return [result for result in results if not result["ok"]]


def grounded(request: str, checks: list[dict]) -> list[dict]:
    """The checks Lisan read out of ``request`` whose cited words are the request's
    own (``basis``), of a known kind: a check never rests on words nobody wrote."""
    lowered = " ".join((request or "").lower().split())
    kept = []
    for item in checks:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            continue
        basis = " ".join(str(item.get("basis") or "").lower().split())
        if len(basis) < 3 or basis not in lowered:
            continue
        kept.append({key: value for key, value in item.items() if key != "basis"})
    return kept


def describe(results: list[dict]) -> str:
    """The failed checks in words, for the rewrite."""
    return "; ".join(f"{result['kind']}: found {result['found']}" for result in failed(results))
