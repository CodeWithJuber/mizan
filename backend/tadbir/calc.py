"""MIZAN's own arithmetic: exact, bounded, no eval and no language model.

Integers stay exact (Python big integers); fractions use exact rationals when
both operands are integers, so ``1/3 + 1/6`` is ``1/2``. Exponents, factorials
and result sizes are bounded so a request cannot exhaust the server.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable
from fractions import Fraction
from typing import Any, cast

MAX_DIGITS = 20000
MAX_EXPONENT = 100000
MAX_FACTORIAL = 3000
MAX_NODES = 200

_BINARY: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type, Callable[[Any], Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "factorial": math.factorial,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
    "gcd": math.gcd,
    "lcm": math.lcm,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}

Number = int | float | Fraction


class CalcError(ValueError):
    pass


def _check(value: Number) -> Number:
    if isinstance(value, bool):
        raise CalcError("Booleans are not numbers here")
    if isinstance(value, int) and value.bit_length() > MAX_DIGITS * 3.33:
        raise CalcError("The result is too large")
    if isinstance(value, float) and not math.isfinite(value):
        raise CalcError("The result is not a finite number")
    return value


def _evaluate(node: ast.AST) -> Number:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        constant: int | float = node.value  # type: ignore[assignment]
        return _check(constant)
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _check(_UNARY[type(node.op)](_evaluate(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, Fraction)) and abs(Fraction(right)) > MAX_EXPONENT:
                raise CalcError("The exponent is too large")
            if isinstance(left, int) and isinstance(right, int) and right > 0:
                if left not in (0, 1, -1) and right * math.log2(abs(left) or 1) > MAX_DIGITS * 3.33:
                    raise CalcError("The result is too large")
        if (
            isinstance(node.op, ast.Div)
            and isinstance(left, (int, Fraction))
            and isinstance(right, (int, Fraction))
        ):
            if right == 0:
                raise CalcError("Division by zero")
            return _check(Fraction(left) / Fraction(right))
        try:
            return _check(_BINARY[type(node.op)](left, right))
        except ZeroDivisionError:
            raise CalcError("Division by zero") from None
        except OverflowError:
            raise CalcError("The result is too large") from None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and not node.keywords
        and len(node.args) <= 2
    ):
        args = [_evaluate(arg) for arg in node.args]
        if node.func.id == "factorial":
            if len(args) != 1 or not isinstance(args[0], int) or not 0 <= args[0] <= MAX_FACTORIAL:
                raise CalcError(f"factorial needs a whole number from 0 to {MAX_FACTORIAL}")
        try:
            plain = [float(a) if isinstance(a, Fraction) else a for a in args]
            return _check(_FUNCTIONS[node.func.id](*plain))
        except (ValueError, TypeError, OverflowError) as exc:
            raise CalcError(str(exc) or "Invalid function argument") from None
    raise CalcError("Only numbers, + - * / // % ** and basic math functions are supported")


def normalize(expression: str) -> str:
    text = expression.strip().rstrip("=?").strip()
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:of|ka|ki|ke|का|की|के)\s*(\d+(?:\.\d+)?)", r"(\1*\2/100)", text
    )
    # Operators said in words: "2 ki power 10", "3 to the power of 4", "12 x 13".
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:(?:ki|ka|ke|की|का|के|to\s+the|raised\s+to(?:\s+the)?)\s+)?"
        r"(?:power|पावर)\s+(?:of\s+)?(\d+(?:\.\d+)?)",
        r"\1**\2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?<=\d)(?<!\b0)\s*[xX]\s*(?=\d)", "*", text)  # never 0x1f (hex)
    text = re.sub(r"(\d+)\s*!", r"factorial(\1)", text)
    text = re.sub(r"√\s*(\d+(?:\.\d+)?)", r"sqrt(\1)", text)
    return text


def evaluate(expression: str) -> Number:
    text = normalize(expression)
    if not text or len(text) > 500:
        raise CalcError("Expression is empty or too long")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise CalcError("Not a valid arithmetic expression") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise CalcError("Expression is too complex")
    return _evaluate(tree)


_SIGNS = {
    ast.Add: "+",
    ast.Sub: "−",
    ast.Mult: "×",
    ast.Div: "÷",
    ast.FloorDiv: "//",
    ast.Mod: "mod",
    ast.Pow: "^",
}


def steps(expression: str) -> list[str]:
    """The working: every operation in the order it is evaluated, each with its
    exact value. A product of two whole numbers is also shown by place value
    (17 × 23 = 17 × 20 + 17 × 3), the distributive law written out."""
    tree = ast.parse(normalize(expression), mode="eval")
    lines: list[str] = []

    def walk(node: ast.AST) -> Number:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.BinOp) and type(node.op) in _SIGNS:
            left, right = walk(node.left), walk(node.right)
            value = _evaluate(
                ast.Expression(
                    body=ast.BinOp(left=_literal(left), op=node.op, right=_literal(right))
                )
            )
            sign = _SIGNS[type(node.op)]
            if isinstance(node.op, ast.Mult) and _place_value(left, right):
                parts = _parts(int(right))
                lines.append(
                    f"{_short(left)} × {_short(right)} = "
                    + " + ".join(f"{_short(left)} × {part}" for part in parts)
                )
                products = [int(left) * part for part in parts]
                lines.extend(
                    f"{_short(left)} × {part} = {product}"
                    for part, product in zip(parts, products, strict=True)
                )
                lines.append(" + ".join(str(p) for p in products) + f" = {_short(value)}")
            else:
                lines.append(f"{_short(left)} {sign} {_short(right)} = {_short(value)}")
            return value
        value = _evaluate(ast.Expression(body=cast(ast.expr, node)))
        if isinstance(node, (ast.Call, ast.UnaryOp)) and ast.unparse(node) != _short(value):
            lines.append(f"{ast.unparse(node)} = {_short(value)}")
        return value

    walk(tree)
    return lines


def _short(value: Number) -> str:
    """A step's number: an exact fraction stays a/b (the answer line gives its decimal)."""
    if isinstance(value, Fraction) and value.denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    return render(value)


def _literal(value: Number) -> ast.expr:
    """A computed value back as an expression, exact fractions kept exact."""
    if isinstance(value, Fraction):
        return ast.BinOp(
            left=ast.Constant(value.numerator), op=ast.Div(), right=ast.Constant(value.denominator)
        )
    return ast.Constant(value)


def _place_value(left: Number, right: Number) -> bool:
    whole = isinstance(left, int) and isinstance(right, int)
    return whole and 10 <= abs(int(right)) < 10**6 and len(_parts(int(right))) > 1


def _parts(number: int) -> list[int]:
    """A whole number by place value: 2305 → [2000, 300, 5]."""
    digits = str(abs(number))
    sign = -1 if number < 0 else 1
    return [
        sign * int(digit) * 10 ** (len(digits) - index - 1)
        for index, digit in enumerate(digits)
        if digit != "0"
    ]


def render(value: Number) -> str:
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return str(value.numerator)
        decimal = value.numerator / value.denominator
        return f"{value.numerator}/{value.denominator} ≈ {decimal:.12g}"
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e16:
            return str(int(value))
        return f"{value:.12g}"
    return str(value)


_EXPRESSION = re.compile(
    r"(?:(?:sqrt|factorial|log10|log2|log|exp|sin|cos|tan|abs|round|floor|ceil|gcd|lcm)\s*\(|[\d(√-])"
    r"[\d\s+\-*/%^().,×÷−!√a-z]*[\d)!]"
)


def find_expression(text: str) -> str | None:
    """The longest arithmetic-looking span in free text, if it evaluates."""
    candidates = sorted(
        (m.group(0).strip() for m in _EXPRESSION.finditer(text.lower())), key=len, reverse=True
    )
    for candidate in candidates:
        # An operation between operands, a factorial, a root or a function: a
        # bare (signed) number such as "-2290" is not a calculation.
        if not re.search(
            r"[\d).]\s*(?:\*\*|[+\-*/%^×÷])\s*[\d(.√a-z]|\d\s*!|√|[a-z]+\(|%\s*of",
            normalize(candidate),
        ):
            continue
        if re.fullmatch(r"\d{1,3}\s*:\s*\d{1,3}", candidate):
            continue
        try:
            evaluate(candidate)
        except CalcError:
            continue
        return candidate
    return None
