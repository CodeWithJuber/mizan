"""Silsila (سلسلة): MIZAN finds the rule of a number sequence and proves it on every term.

For "13, 26, 64, 118, 274, 376, find the next number" MIZAN tries, in order:

1. its own exact methods (rational arithmetic, no model): a polynomial in n,
   a polynomial in the n-th prime, and linear recurrences with a constant
   term. A rule is accepted only if it reproduces every given term with at
   least two terms to spare beyond its own parameters, so it is evidence and
   not an interpolation that would fit anything;
2. the OEIS (the On-Line Encyclopedia of Integer Sequences), which gives the
   sequence's name and its next term when the terms appear there;
3. Lisan's proposal, as a program MIZAN runs in its sandbox and accepts only
   if it reproduces every term.

When several proven rules disagree, MIZAN shows each; when none fits, it says
so and gives no number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import httpx

MIN_TERMS = 4
MAX_TERMS = 40
SPARE = 2  # terms a rule must reproduce beyond those that fixed its parameters
MARKER = "__SILSILA__"
_NUMBERS = re.compile(r"-?\d+")
_CUE = re.compile(
    r"\b(?:next|agla|agle|aage|aagay|sequence|series|pattern|missing|what\s+comes|"
    r"kaun\s*sa\s+number|find\s+the\s+number)\b|اگلا|अगला|التالي",
    re.IGNORECASE,
)
_FOLLOW = re.compile(
    r"\b(?:next\s+number|agla\s+number|sequence|series|pattern|number\s+theor\w*|try\s+again|"
    r"find\s+(?:it|the\s+next)|solve\s+it|oeis)\b" + "|" + r"\b(?:koshish|try\s+harder|"
    r"don'?t\s+give\s+up|give\s+up|haar|dobara\s+try|phir\s+se\s+try|keep\s+trying)\b",
    re.IGNORECASE,
)
# "Karo koshish", "jaldi haar kyun maan rahe ho": the user asks for more effort.
_HARDER = re.compile(
    r"\b(?:koshish|try\s+harder|give\s+up|haar|dobara|phir\s+se|keep\s+trying|take\s+time|"
    r"learn)\b",
    re.IGNORECASE,
)


def harder(text: str) -> bool:
    return bool(_HARDER.search(text or ""))


@dataclass
class Rule:
    method: str
    formula: str
    next: int
    parameters: int
    checked: int  # terms reproduced

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "formula": self.formula,
            "next": self.next,
            "checked": self.checked,
        }


def parse(text: str) -> list[int] | None:
    """The sequence a message asks about: at least four numbers and a cue like "next"."""
    if not _CUE.search(text or ""):
        return None
    return _run_of_numbers(text)


def _run_of_numbers(text: str) -> list[int] | None:
    # The longest run of numbers separated only by commas, spaces or semicolons.
    best: list[int] = []
    for run in re.finditer(r"-?\d+(?:\s*[,;]?\s*-?\d+)+", text or ""):
        values = [int(value) for value in _NUMBERS.findall(run.group(0))]
        if len(values) > len(best):
            best = values
    if not MIN_TERMS <= len(best) <= MAX_TERMS:
        return None
    if any(abs(value) > 10**30 for value in best):
        return None
    return best


def follow_up(text: str) -> bool:
    """A message that refers to an earlier sequence without restating it."""
    return bool(_FOLLOW.search(text or "")) and _run_of_numbers(text) is None


def from_history(history: list[dict] | None) -> list[int] | None:
    """The most recent sequence the user asked about in this chat."""
    for turn in list(reversed(history or []))[:12]:
        if turn.get("role") == "user":
            found = parse(str(turn.get("content", "")))
            if found:
                return found
    return None


# ── MIZAN's own exact methods ────────────────────────────────────────────


def _solve(matrix: list[list[Fraction]], vector: list[Fraction]) -> list[Fraction] | None:
    """Gaussian elimination over the rationals; None when singular."""
    size = len(vector)
    rows = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for col in range(size):
        pivot = next((r for r in range(col, size) if rows[r][col] != 0), None)
        if pivot is None:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(size):
            if r != col and rows[r][col] != 0:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
    return [rows[i][size] / rows[i][i] for i in range(size)]


def _primes(count: int) -> list[int]:
    found: list[int] = []
    candidate = 2
    while len(found) < count:
        if all(candidate % p for p in found if p * p <= candidate):
            found.append(candidate)
        candidate += 1
    return found


def _poly_text(coefficients: list[Fraction], variable: str) -> str:
    terms = []
    for power in range(len(coefficients) - 1, -1, -1):
        c = coefficients[power]
        if c == 0:
            continue
        magnitude = abs(c)
        number = "" if magnitude == 1 and power else str(magnitude)
        if power == 0:
            body = str(magnitude)
        elif power == 1:
            body = f"{number}{variable}"
        else:
            body = f"{number}{variable}^{power}"
        sign = "-" if c < 0 else "+"
        terms.append((sign, body))
    if not terms:
        return "0"
    text = ("-" if terms[0][0] == "-" else "") + terms[0][1]
    for sign, body in terms[1:]:
        text += f" {sign} {body}"
    return text


def _polynomial(xs: list[int], seq: list[int], name: str, variable: str, x_next: int) -> list[Rule]:
    rules = []
    n = len(seq)
    for degree in range(0, n - 1 - SPARE + 1):
        size = degree + 1
        if n < size + SPARE:
            break
        matrix = [[Fraction(x) ** k for k in range(size)] for x in xs[:size]]
        coefficients = _solve(matrix, [Fraction(v) for v in seq[:size]])
        if coefficients is None:
            continue
        values = [sum(c * Fraction(x) ** k for k, c in enumerate(coefficients)) for x in xs]
        if values != [Fraction(v) for v in seq]:
            continue
        upcoming = sum(c * Fraction(x_next) ** k for k, c in enumerate(coefficients))
        if upcoming.denominator != 1:
            continue
        rules.append(
            Rule(name, f"a(n) = {_poly_text(coefficients, variable)}", int(upcoming), size, n)
        )
        break  # the lowest degree that fits is the rule
    return rules


def _recurrence(seq: list[int]) -> list[Rule]:
    """a(n) = c1·a(n-1) + … + ck·a(n-k) + c0, for k = 1..3."""
    rules = []
    n = len(seq)
    for order in range(1, 4):
        unknowns = order + 1
        equations = n - order
        if equations < unknowns + SPARE:
            break
        rows = [
            [Fraction(seq[i - j]) for j in range(1, order + 1)] + [Fraction(1)]
            for i in range(order, n)
        ]
        targets = [Fraction(seq[i]) for i in range(order, n)]
        coefficients = _solve(rows[:unknowns], targets[:unknowns])
        if coefficients is None:
            continue
        if any(
            sum(c * v for c, v in zip(coefficients, row, strict=True)) != t
            for row, t in zip(rows, targets, strict=True)
        ):
            continue
        last = [Fraction(seq[n - j]) for j in range(1, order + 1)] + [Fraction(1)]
        upcoming = sum(c * v for c, v in zip(coefficients, last, strict=True))
        if upcoming.denominator != 1:
            continue
        parts = [
            f"{_coef(c)}a(n-{j})" for j, c in enumerate(coefficients[:order], start=1) if c != 0
        ]
        if coefficients[order] != 0:
            parts.append(str(coefficients[order]))
        formula = "a(n) = " + " + ".join(parts).replace("+ -", "- ") if parts else "a(n) = 0"
        rules.append(Rule("linear recurrence", formula, int(upcoming), unknowns + order, n))
        break
    return rules


def _coef(value: Fraction) -> str:
    if value == 1:
        return ""
    if value == -1:
        return "-"
    return f"{value}·"


def own_rules(seq: list[int]) -> list[Rule]:
    """Rules MIZAN finds itself, each reproducing every term."""
    n = len(seq)
    rules = _polynomial(list(range(1, n + 1)), seq, "polynomial in n", "n", n + 1)
    primes = _primes(n + 1)
    rules += _polynomial(primes[:n], seq, "polynomial in the n-th prime p", "p", primes[n])
    rules += _recurrence(seq)
    # Keep the simplest rule for each different next term.
    best: dict[int, Rule] = {}
    for rule in sorted(rules, key=lambda r: r.parameters):
        best.setdefault(rule.next, rule)
    return list(best.values())


# ── the OEIS ─────────────────────────────────────────────────────────────


async def oeis(seq: list[int], timeout: float = 10.0) -> list[dict]:
    """OEIS sequences that contain these terms in order, with the term that follows."""
    query = ",".join(str(v) for v in seq)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                "https://oeis.org/search", params={"q": query, "fmt": "json"}
            )
            response.raise_for_status()
            found = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    matches = []
    for entry in (found if isinstance(found, list) else [])[:10]:
        data = [int(v) for v in str(entry.get("data", "")).split(",") if v.strip("-").isdigit()]
        for start in range(len(data) - len(seq)):
            if data[start : start + len(seq)] == seq:
                matches.append(
                    {
                        "id": f"A{int(entry.get('number', 0)):06d}",
                        "name": str(entry.get("name", ""))[:200],
                        "next": data[start + len(seq)],
                    }
                )
                break
    return matches[:3]


# ── Lisan's proposal, proven in the sandbox ──────────────────────────────


def harness(program: str, seq: list[int]) -> str:
    data = json.dumps(seq)
    return f"""{program}

import json as _json

_SEQ = _json.loads({data!r})
_report = {{"checked": 0, "total": len(_SEQ), "next": None, "error": None}}
try:
    _wrong = []
    if "a" in globals() and callable(globals()["a"]):
        _got = [int(a(n)) for n in range(1, len(_SEQ) + 2)]
        for _n, (_x, _y) in enumerate(zip(_got, _SEQ), 1):
            if _x == _y:
                _report["checked"] += 1
            else:
                _wrong.append([_n, _y, _x])
        _report["next"] = _got[len(_SEQ)]
    else:
        _report["checked"] = 2
        for _i in range(2, len(_SEQ)):
            _x = int(next_term(list(_SEQ[:_i])))
            if _x == _SEQ[_i]:
                _report["checked"] += 1
            else:
                _wrong.append([_i + 1, _SEQ[_i], _x])
        _report["next"] = int(next_term(list(_SEQ)))
    _report["wrong"] = _wrong[:4]
except Exception as _exc:
    _report["error"] = (type(_exc).__name__ + ": " + str(_exc))[:300]
print("{MARKER}" + _json.dumps(_report))
"""


def read(stdout: str) -> dict | None:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(MARKER):
            try:
                value = json.loads(line[len(MARKER) :])
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


def proven(report: dict | None, seq: list[int]) -> bool:
    if not report:
        return False
    return report.get("checked") == len(seq) and isinstance(report.get("next"), int)


def feedback(report: dict | None, stderr: str = "") -> str:
    """What the proposed rule got wrong, for Lisan's revision."""
    if not report:
        return f"The program did not run: {stderr[-1500:]}"
    if report.get("error"):
        return f"The program failed: {report['error']}"
    lines = [f"It reproduces {report.get('checked', 0)} of {report.get('total', 0)} terms."]
    for n, expected, got in report.get("wrong", []):
        lines.append(f"Term {n}: expected {expected}, got {got}")
    return "\n".join(lines)


def rule_comment(program: str) -> str:
    match = re.search(r"#\s*(.+)", program)
    return match.group(1).strip()[:200] if match else ""


def summary(seq: list[int]) -> dict[str, Any]:
    return {"terms": seq, "count": len(seq)}
