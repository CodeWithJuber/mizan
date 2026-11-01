"""Qiyas (قياس): MIZAN infers a rule from worked examples and proves it on every one.

A puzzle gives input→output pairs (grids of colours 0–9, as in ARC) and test
inputs. Lisan proposes the rule as a Python function ``transform(grid)``.
MIZAN runs it in the sandbox on every example and accepts the rule only when
it reproduces all of them exactly; otherwise Lisan revises it from the
examples it got wrong. Only a proven rule's answer is marked verified.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_SIDE = 30
MARKER = "__QIYAS__"
_FENCED_JSON = re.compile(r"```(?:json)?[ \t]*\n(.*?)```", re.DOTALL)


def _grid(value: Any) -> bool:
    return (
        isinstance(value, list)
        and 1 <= len(value) <= MAX_SIDE
        and all(isinstance(row, list) and 1 <= len(row) <= MAX_SIDE for row in value)
        and len({len(row) for row in value}) == 1
        and all(type(cell) is int and 0 <= cell <= 9 for row in value for cell in row)
    )


def _puzzle(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    train, test = value.get("train"), value.get("test")
    if not isinstance(train, list) or not isinstance(test, list) or not train or not test:
        return None
    if len(train) > 10 or len(test) > 4:
        return None
    pairs = [
        {"input": pair["input"], "output": pair["output"]}
        for pair in train
        if isinstance(pair, dict) and _grid(pair.get("input")) and _grid(pair.get("output"))
    ]
    cases = [
        {"input": case["input"]}
        for case in test
        if isinstance(case, dict) and _grid(case.get("input"))
    ]
    if len(pairs) != len(train) or len(cases) != len(test):
        return None
    return {"train": pairs, "test": cases}


def parse(text: str) -> dict | None:
    """The puzzle in a message: a JSON object with ``train`` pairs and ``test`` inputs."""
    if '"train"' not in text or '"test"' not in text:
        return None
    candidates = _FENCED_JSON.findall(text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            found = _puzzle(json.loads(candidate))
        except ValueError:
            continue
        if found is not None:
            return found
    return None


def harness(program: str, puzzle: dict) -> str:
    """A script that runs ``transform`` on every example and test input and reports."""
    data = json.dumps(puzzle, separators=(",", ":"))
    return f"""{program}

import json as _json

_PUZZLE = _json.loads({data!r})


def _norm(grid):
    return [[int(cell) for cell in row] for row in grid]


def _apply(grid):
    try:
        return {{"output": _norm(transform([list(row) for row in grid]))}}
    except Exception as exc:  # the rule failed on this grid
        return {{"error": (type(exc).__name__ + ": " + str(exc))[:300]}}


_train = []
for _pair in _PUZZLE["train"]:
    _got = _apply(_pair["input"])
    _got["ok"] = _got.get("output") == _pair["output"]
    _train.append(_got)
_test = [_apply(_case["input"]) for _case in _PUZZLE["test"]]
print("{MARKER}" + _json.dumps({{"train": _train, "test": _test}}))
"""


def read(stdout: str) -> dict | None:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(MARKER):
            try:
                report = json.loads(line[len(MARKER) :])
            except ValueError:
                return None
            return report if isinstance(report, dict) else None
    return None


def passed(report: dict | None, puzzle: dict) -> int:
    if not report:
        return 0
    return sum(1 for item in report.get("train", [])[: len(puzzle["train"])] if item.get("ok"))


def test_outputs(report: dict | None) -> list[list[list[int]]] | None:
    if not report:
        return None
    outputs = [item.get("output") for item in report.get("test", [])]
    return outputs if outputs and all(_grid(grid) for grid in outputs) else None


def failures(report: dict | None, puzzle: dict, stderr: str = "") -> str:
    """What the rule got wrong, for Lisan's revision."""
    if not report:
        return f"The program did not run: {stderr[-1500:]}"
    lines = []
    for index, (item, pair) in enumerate(
        zip(report.get("train", []), puzzle["train"], strict=False), 1
    ):
        if item.get("ok"):
            continue
        if "error" in item:
            lines.append(f"Example {index}: error {item['error']}")
        else:
            lines.append(
                f"Example {index}: expected {json.dumps(pair['output'])}\n"
                f"got {json.dumps(item.get('output'))}"
            )
    return "\n".join(lines)[:4000]


def render(grid: list[list[int]]) -> str:
    return "[\n" + ",\n".join("  " + json.dumps(row) for row in grid) + "\n]"


def describe(puzzle: dict) -> str:
    """The examples, written compactly for Lisan."""
    parts = []
    for index, pair in enumerate(puzzle["train"], 1):
        parts.append(
            f"Example {index} input:\n{render(pair['input'])}\noutput:\n{render(pair['output'])}"
        )
    for index, case in enumerate(puzzle["test"], 1):
        parts.append(f"Test input {index}:\n{render(case['input'])}")
    return "\n\n".join(parts)
