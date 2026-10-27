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
# Why a run's words may not become training data, when they may not.
_no_training: ContextVar[str] = ContextVar("mizan_no_training", default="")


def active() -> bool:
    return _stateless.get()


def trains() -> bool:
    """Whether what this run sees may be kept as a training candidate."""
    return not _stateless.get() and not _no_training.get()


@contextmanager
def no_training(reason: str) -> Iterator[None]:
    """A run that is remembered and learned from as usual, but whose words are
    never captured for training (WhatsApp: Meta's terms s.4.7 forbid using
    platform data to train or improve models)."""
    token = _no_training.set(_no_training.get() or reason)
    try:
        yield
    finally:
        _no_training.reset(token)


@contextmanager
def bind(on: bool = True) -> Iterator[None]:
    token = _stateless.set(bool(on) or _stateless.get())
    try:
        yield
    finally:
        _stateless.reset(token)
