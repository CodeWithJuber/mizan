"""Isnad (إسناد): the chain of support behind every claim in an answer, and its grade.

Each claim (a sentence or a quoted passage) is graded by what supports it,
with the terms of hadith science:

- **sahih**: MIZAN established it itself (an exact calculation, a text read
  from its authentic source, a program it ran and checked) or verified it;
- **hasan**: supported by evidence MIZAN gathered (a tool result or a cited
  source) but not verified;
- **da'if**: nothing MIZAN holds supports it, only the language model's words;
- **mawdu'**: fabricated: an action that never happened, a citation to a
  source that does not exist, or a link MIZAN never found.

Grading is by rule (numbers, citations, links, word overlap with the
evidence); it shows support, not truth.
"""

from __future__ import annotations

import re
from typing import Any

from .express import _ACTION_CLAIM, _CITATION, _NUMBER, _URL

GRADES = ("sahih", "hasan", "daif", "mawdu")
# What a verified recipe's answer rests on, by kind of work.
BASIS = {
    "compute": "MIZAN calculated it exactly",
    "quran": "read verbatim from MIZAN's Quran source",
    "hadith": "read verbatim from MIZAN's hadith source",
    "waqt": "MIZAN's calendar (Umm al-Qura) and clock",
    "salah": "computed by MIZAN for your place (Adhan astronomical method)",
    "watch": "MIZAN saved the watcher and computed when it runs",
    "capabilities": "MIZAN's live tool registry",
    "run_code": "MIZAN ran it in its sandbox and checked the result",
    "build_and_run": "MIZAN ran it in its sandbox and checked the result",
    "qiyas": "the rule reproduced every example in MIZAN's sandbox",
    "silsila": "MIZAN checked the rule on every term",
    "build_project": "MIZAN's checks of the project passed",
    "edit_project": "MIZAN's checks of the change passed",
}
MAX_CLAIMS = 40
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE = re.compile(r"(?<=[.!?۔؟])\s+")
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have",
    "not", "but", "you", "your", "its", "his", "her", "they", "their", "which", "what", "when",
    "hai", "hain", "aur", "mein", "yeh", "woh", "kya", "kar", "liye",
}  # fmt: skip


def claims(text: str) -> list[dict]:
    """The answer's claims: quoted passages and sentences, without code or MIZAN's notes."""
    units: list[dict] = []
    quote: list[str] = []

    def close_quote() -> None:
        if quote:
            units.append({"text": " ".join(quote)[:600], "kind": "quote"})
            quote.clear()

    for raw in _FENCE.sub("\n", text or "").splitlines():
        line = raw.strip()
        if line.startswith(">"):
            quote.append(line.lstrip("> ").strip())
            continue
        close_quote()
        if not line or re.fullmatch(r"_.*_", line) or line.startswith("---"):
            continue  # MIZAN's own notes and separators state no claim
        line = re.sub(r"^(?:[#>*\-]+|\d+[.)])\s*", "", line).replace("**", "").strip()
        if re.fullmatch(r"\[[^\]]+\]\([^)]+\)", line):
            continue  # a source-list entry
        for sentence in _SENTENCE.split(line):
            sentence = sentence.strip()
            if len(sentence) >= 12 or _NUMBER.search(sentence):
                units.append({"text": sentence[:600], "kind": "sentence"})
    close_quote()
    return units[:MAX_CLAIMS]


def _words(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text)} - _STOP


def _grade(unit: dict, evidence: str, verified: bool, max_citation: int) -> dict:
    text = unit["text"]
    reasons: list[str] = []
    if _ACTION_CLAIM.search(text):
        reasons.append("claims an action that has no receipt")
    for citation in _CITATION.findall(text):
        if not 1 <= int(citation) <= max_citation:
            reasons.append(f"cites source [{citation}], which does not exist")
    for url in _URL.findall(text):
        if url.rstrip(").,") not in evidence:
            reasons.append("links to a page MIZAN did not find")
    if reasons:
        return {**unit, "grade": "mawdu", "support": reasons}
    support = []
    numbers = [n.replace(",", "") for n in _NUMBER.findall(text)]
    plain_evidence = evidence.replace(",", "")
    unsupported = [n for n in numbers if n not in plain_evidence]
    if numbers and not unsupported:
        support.append("every number is in MIZAN's evidence")
    cited = [c for c in _CITATION.findall(text) if 1 <= int(c) <= max_citation]
    if cited:
        support.append(f"cites source {', '.join(f'[{c}]' for c in cited)}")
    words = _words(text)
    overlap = len(words & _words(evidence)) / len(words) if words else 0.0
    if overlap >= 0.5:
        support.append(f"{round(overlap * 100)}% of its words are in the evidence")
    if unsupported:
        return {**unit, "grade": "daif", "support": [f"number {unsupported[0]} has no evidence"]}
    if not support:
        return {**unit, "grade": "daif", "support": ["nothing MIZAN holds supports it"]}
    return {**unit, "grade": "sahih" if verified else "hasan", "support": support}


def ledger(
    text: str,
    *,
    established: bool = False,
    basis: str = "",
    evidence: str = "",
    verified: bool = False,
    max_citation: int = 0,
) -> list[dict]:
    """Grade every claim of one answer (or one part of it)."""
    units = claims(text)
    if established:
        return [{**unit, "grade": "sahih", "support": [basis]} for unit in units]
    if not evidence:
        graded = [_grade(unit, "", False, 0) for unit in units]
        return [
            unit
            if unit["grade"] == "mawdu"
            else {**unit, "grade": "daif", "support": ["the language model's words only"]}
            for unit in graded
        ]
    return [_grade(unit, evidence, verified, max_citation) for unit in units]


def summary(graded: list[dict]) -> dict[str, Any]:
    counts = {grade: sum(1 for unit in graded if unit["grade"] == grade) for grade in GRADES}
    total = len(graded)
    return {
        "counts": counts,
        "claims": total,
        # The Mizan (balance): the share of the answer MIZAN stands behind.
        "supported": round((counts["sahih"] + counts["hasan"]) / total, 3) if total else None,
        "ledger": graded,
    }
