"""Tathabbut (تثبّت, "make sure", Quran 49:6): a program's result is verified
only when an independent derivation agrees with it.

A program that runs cleanly can still answer a different question: the 30th
Fibonacci number printed as F29 ran with exit code 0 and was kept as verified
in the 27 October API benchmark. Running cleanly says the code works; it does
not say the code read the request right. So when a program prints numbers,
Lisan writes a second program for the same request by a different method,
without seeing the first, and MIZAN runs it: the result is verified when every
number the second prints appears, in order, in the first's output (N-version
programming). Two derivations that share no code rarely share a misreading.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def numbers(text: str) -> list[str]:
    """The numbers a program printed, in order (thousands separators dropped)."""
    return [match.group(0).replace(",", "") for match in _NUMBER.finditer(text or "")]


def _same(a: str, b: str) -> bool:
    """Equal at the precision the less precise of the two was printed with."""
    try:
        x, y = Decimal(a), Decimal(b)
    except InvalidOperation:
        return a == b
    places = min(
        -int(x.as_tuple().exponent) if x.as_tuple().exponent < 0 else 0,  # type: ignore[operator]
        -int(y.as_tuple().exponent) if y.as_tuple().exponent < 0 else 0,  # type: ignore[operator]
    )
    step = Decimal(1).scaleb(-places)
    return x.quantize(step) == y.quantize(step)


def agree(primary: str, check: str) -> bool | None:
    """Whether the first program's output holds every number the independent
    one printed, in the same order; None when the check printed no number."""
    wanted = numbers(check)
    if not wanted:
        return None
    printed = iter(numbers(primary))
    return all(any(_same(number, seen) for seen in printed) for number in wanted)


def applies(output: str) -> bool:
    """A result that can be checked this way: the program printed a number."""
    return bool(numbers(output))
