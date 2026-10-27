"""A stateless run: nothing it sees or does is remembered or learned from.

Bound for an evaluation (the AGI test, a debug comparison, or a chat sent with
``stateless: true``): no words from the user's other chats are recalled, no
learned state is written (Ta'allum, Qasd, Hifz, Tajriba, Majlis, Ahl al-Dhikr
all write through ``AdaptiveStateStore.put``), and no answer is captured as a
training candidate. The chat's own messages are still saved, so the run can be
read back.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_stateless: ContextVar[bool] = ContextVar("mizan_stateless", default=False)


def active() -> bool:
    return _stateless.get()


@contextmanager
def bind(on: bool = True) -> Iterator[None]:
    token = _stateless.set(bool(on) or _stateless.get())
    try:
        yield
    finally:
        _stateless.reset(token)
