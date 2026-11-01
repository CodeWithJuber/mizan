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


def harder(text: str) -> bool:
    """The user asks for more effort ("Karo koshish"), as Qasd's ``harder`` facet reads it."""
    from . import qasd

    return qasd.facet("harder", text or "")


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
    """The sequence a message asks about: a run of at least four numbers, in a
    message MIZAN's intent model reads as a sequence question."""
    found = _run_of_numbers(text)
    if found is None:
        return None
    from . import qasd

    return found if qasd.prefers(text, "silsila", "converse") else None


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


_TERM = r"(?:-?\d+|\?|_)"
_GAP = {"?", "_"}


def with_gap(text: str) -> tuple[list[int], list[int], int] | None:
    """A sequence with one term missing inside it, written ``?`` or ``_``
    ("13, 26, 64, 118, 274, ?, 628"): its known terms, their positions (from 1)
    and the position of the missing term. A ``?`` at the end asks for the next
    term, which :func:`_run_of_numbers` reads."""
    best: tuple[list[int], list[int], int] | None = None
    size = 0
    for run in re.finditer(rf"{_TERM}(?:\s*[,;]?\s*{_TERM})+", text or ""):
        tokens = re.findall(r"-?\d+|\?|_", run.group(0))
        gaps = [index for index, token in enumerate(tokens) if token in _GAP]
        if len(gaps) != 1 or not 0 < gaps[0] < len(tokens) - 1 or len(tokens) > MAX_TERMS:
            continue
        known = [(index + 1, int(token)) for index, token in enumerate(tokens) if token not in _GAP]
        if len(known) < MIN_TERMS or any(abs(value) > 10**30 for _n, value in known):
            continue
        if len(tokens) > size:
            size = len(tokens)
            best = ([value for _n, value in known], [n for n, _v in known], gaps[0] + 1)
    return best


def shown(seq: list[int], positions: list[int] | None = None, gap: int | None = None) -> str:
    """The terms as the user wrote them, with ``?`` where one is missing."""
    if not gap or not positions:
        return ", ".join(str(value) for value in seq)
    by_position = dict(zip(positions, seq, strict=True))
    return ", ".join("?" if n == gap else str(by_position[n]) for n in range(1, max(positions) + 1))


def follow_up(text: str) -> bool:
    """A message about an earlier sequence that does not restate it."""
    from . import qasd

    ranked = qasd.ranked(text or "")
    return _run_of_numbers(text) is None and bool(ranked) and ranked[0][0] == "silsila_follow"


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


def missing_rules(seq: list[int], positions: list[int], gap: int) -> list[Rule]:
    """Rules for a sequence with a term missing inside it: fitted on the known
    terms at their own positions and checked on every one of them, terms after
    the gap included; ``Rule.next`` is the missing term."""
    rules = _polynomial(positions, seq, "polynomial in n", "n", gap)
    primes = _primes(max([*positions, gap]))
    rules += _polynomial(
        [primes[n - 1] for n in positions],
        seq,
        "polynomial in the n-th prime p",
        "p",
        primes[gap - 1],
    )
    best: dict[int, Rule] = {}
    for rule in sorted(rules, key=lambda r: r.parameters):
        best.setdefault(rule.next, rule)
    return list(best.values())


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


async def oeis_missing(
    seq: list[int], positions: list[int], gap: int, timeout: float = 10.0
) -> list[dict]:
    """OEIS sequences that hold every known term at its position, with the missing one."""
    before = [value for value, n in zip(seq, positions, strict=True) if n < gap]
    after = [value for value, n in zip(seq, positions, strict=True) if n > gap]
    query = ",".join(str(v) for v in (before if len(before) >= len(after) else after))
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
    width = max([*positions, gap])
    for entry in (found if isinstance(found, list) else [])[:10]:
        data = [int(v) for v in str(entry.get("data", "")).split(",") if v.strip("-").isdigit()]
        for start in range(len(data) - width + 1):
            if all(data[start + n - 1] == value for value, n in zip(seq, positions, strict=True)):
                matches.append(
                    {
                        "id": f"A{int(entry.get('number', 0)):06d}",
                        "name": str(entry.get("name", ""))[:200],
                        "next": data[start + gap - 1],
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
