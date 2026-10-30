"""A stateless run: nothing it sees or does is remembered or learned from.

Bound for an evaluation (the AGI test, a debug comparison, or a chat sent with
``stateless: true``): no words from the user's other chats are recalled, no
learned state is written (Ta'allum, Qasd, Hifz, Tajriba, Majlis, Ahl al-Dhikr
all write through ``AdaptiveStateStore.put``), and no answer is captured as a
training candidate. Outside evaluations the user's own choices apply
(docs/consent.md): ``learning: off`` stops learning (:func:`no_learning`), and
words are captured for training only with ``training: on``
(:func:`allow_training`). The chat's own messages are still saved, so the run can be
read back.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_stateless: ContextVar[bool] = ContextVar("mizan_stateless", default=False)
# Why a run's words may become training data: only the user's own yes
# (``training: on``; docs/consent.md). Unset, nothing is captured.
_training: ContextVar[str] = ContextVar("mizan_training", default="")
# Why a run's words may not become training data even with that yes.
_no_training: ContextVar[str] = ContextVar("mizan_no_training", default="")
# Why MIZAN may not learn from this run for the user, when it may not (the
# user's ``learning: off``; docs/consent.md).
_no_learning: ContextVar[str] = ContextVar("mizan_no_learning", default="")


def active() -> bool:
    return _stateless.get()


def learns() -> bool:
    """Whether MIZAN may learn from this run for its user (the ``self`` purpose):
    learned state, memory strengthening, task records, pathways, the knowledge
    graph. Off in a stateless run and when the user turned learning off; the
    chat's own messages and a note the user asks for are kept either way."""
    return not _stateless.get() and not _no_learning.get()


@contextmanager
def no_learning(reason: str) -> Iterator[None]:
    """A run whose user turned learning off: nothing is learned from it."""
    token = _no_learning.set(_no_learning.get() or reason)
    try:
        yield
    finally:
        _no_learning.reset(token)


def trains() -> bool:
    """Whether what this run sees may be kept as a training candidate: only
    when its user said yes, never in a stateless run or a run a channel's terms
    keep out of training. Training is opt-in, so a run nobody bound a choice
    for captures nothing."""
    return bool(_training.get()) and not _stateless.get() and not _no_training.get()


def barred_from_training() -> bool:
    """What no yes can lift: an evaluation run, or words a channel's terms keep
    out of training. The training store refuses these itself; the user's yes
    (:func:`trains`) is asked where a chat's words become candidates."""
    return _stateless.get() or bool(_no_training.get())


@contextmanager
def allow_training(reason: str) -> Iterator[None]:
    """A run whose user switched training on (``training: on``)."""
    token = _training.set(reason)
    try:
        yield
    finally:
        _training.reset(token)


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
