"""Tadrib (تدريب): MIZAN's own models learn while it works (docs/tadrib.md).

A verified piece of work becomes a lesson that the model learns from within
seconds (fast weights); the night consolidates the day's lessons into the
gated version (slow weights); every lesson is listed and can be taken back.

Phase 1: the Ruh reader learns the language of each consented message. A
lesson is the person's own words (pasted text and invisible characters set
aside) from a run that may train (``training: on``, not barred, not
stateless), with no instruction aimed at an AI and no scripture in it. The
trainer, one background thread, scores it with the fast and the slow copy
before anything is learned (prequential: predict, then learn), keeps it only
where Lughah and the serving reader read the same language (MIZAN's check, the
owner's decision of 31 Oct 2026 in place of a person's review), holds one in
``HELD_OUT`` out as test, learns the rest (``online.Online``) and swaps the
fast weights into the reader that serves (``ruh_reader.swap``). On the held-out
lessons a paired sign test watches the fast copy; when its e-value reaches
1/α the fast copy starts again from the slow weights.

``MIZAN_TADRIB``: ``on`` | ``off`` (default until the pre-registered
measurement in docs/tadrib.md passes: nothing is kept, and the reader learns
at night from reviewed messages only, as before).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("mizan.tadrib")

MODES = ("off", "on")
HELD_OUT = 5  # one lesson in five is never learned and is kept as test
SALT = "tadrib-1"
KIND = "reader"
ALPHA = 0.05
SAVE_EVERY = 8  # lessons between writes of the fast copy to disk
TIMINGS = 200  # the last lessons' seconds kept for the status


def mode() -> str:
    found = os.getenv("MIZAN_TADRIB", "off").strip().lower()
    return found if found in MODES else "off"


def held_out(digest: str) -> bool:
    """Whether this lesson is one of the one in ``HELD_OUT`` never learned (fixed by SHA-256)."""
    mixed = hashlib.sha256(f"{SALT}:held:{digest}".encode()).hexdigest()
    return int(mixed[:16], 16) % HELD_OUT == 0


def setting() -> Any:
    """The online learner's setting, chosen on the dev stream (docs/tadrib.md)."""
    from .online import Setting

    return Setting()


def lesson_text(message: str) -> str:
    """The person's own words of a message: pasted regions removed, then
    Amanah's clean (tag and zero-width characters gone)."""
    from .. import amanah

    text = message or ""
    for region in amanah.pasted(text):
        text = text.replace(region, " ")
    return " ".join(amanah.clean_message(text).split())


def gate(message: str) -> tuple[str, str]:
    """(verdict, lesson text): ``ok`` when the message may become a reader
    lesson under this run's choices, else why not."""
    from memory import stateless

    from .. import amanah, lughah, ruh_reader

    if mode() == "off":
        return "off", ""
    if stateless.active() or not stateless.learns() or not stateless.trains():
        return "no consent", ""
    if stateless.barred_from_training():
        return "barred", ""
    if ruh_reader.mode() == "off" or not ruh_reader.has_torch():
        return "no reader", ""
    if ruh_reader.manifest("current") is None:
        return "no reader", ""
    if amanah.scan_message(message or ""):
        return "injection", ""
    text = lesson_text(message)
    if not ruh_reader.reading(lughah.own_words(text)):
        return "no words", ""
    if ruh_reader.scripture(text):
        return "scripture", ""
    return "ok", text


async def offer(owner: str, chat_id: str, message: str) -> str:
    """Keep a message as a pending lesson and hand it to the trainer; never
    delays the answer (the trainer learns it in the background). Returns the
    verdict (``offered``, ``seen`` or why not)."""
    if not owner:
        return "no owner"
    verdict, text = await asyncio.to_thread(gate, message)
    if verdict != "ok":
        return verdict
    from ..ruh_reader import text_digest
    from . import store

    digest = text_digest(text)
    added = await asyncio.to_thread(store.add, owner, digest, chat_id, KIND, text, "agreement")
    if not added:
        return "seen"
    _trainer.submit(owner, digest)
    return "offered"


class _Trainer:
    """One background thread that learns lessons one at a time."""

    def __init__(self) -> None:
        # (the person's lesson file, the lesson's digest, the person when known)
        self.queue: queue.Queue[tuple[Any, str, str] | None] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.started = threading.Lock()
        self.idle: Callable[[], bool] = lambda: True
        self.online: Any = None
        self.slow: str | None = None
        self.fit: Any = None
        self.languages: list[str] = []
        self.generation = 0
        self.rebuild = False
        self.since_save = 0
        self.timings: deque[float] = deque(maxlen=TIMINGS)
        self.stats = self._fresh_stats()
        self.signs = [0, 0]  # held-out lessons the slow / the fast copy read better

    @staticmethod
    def _fresh_stats() -> dict:
        return {
            "offered": 0,
            "learned": 0,
            "held_out": 0,
            "disagreed": 0,
            "contradicted": 0,
            "resets": 0,
            "rebuilds": 0,
            "prequential": {
                "learned": {"n": 0, "fast": 0.0, "slow": 0.0},
                "held_out": {"n": 0, "fast": 0.0, "slow": 0.0},
            },
            "last": None,
        }

    # ── the thread ──────────────────────────────────────────────────────

    def start(self) -> None:
        with self.started:
            if self.thread is not None and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._run, name="tadrib", daemon=True)
            self.thread.start()
            self._enqueue_pending()

    def submit(self, owner: str, digest: str) -> None:
        from . import store

        self.stats["offered"] += 1
        self.queue.put((store.path_of(owner), digest, owner))
        self.start()

    def invalidate(self) -> None:
        """The slow weights or the lessons changed: rebuild the fast copy."""
        self.generation += 1
        self.rebuild = True
        self.queue.put(None)
        self.start()

    def _enqueue_pending(self) -> None:
        """Lessons kept but not yet learned (a restart came between)."""
        from . import store

        try:
            for path in store.owners_with_lessons():
                for lesson in store.pending_at(path):
                    self.queue.put((path, lesson.digest, ""))
        except Exception as exc:  # noqa: BLE001 - pending lessons wait for the night
            logger.warning("Tadrib: pending lessons not read: %s", exc)

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            while not self.idle():  # a request runs: learning waits for it
                time.sleep(0.5)
            try:
                self.step(item)
            except Exception:  # noqa: BLE001 - a failed lesson never stops MIZAN
                logger.exception("Tadrib: a lesson failed")

    def step(self, item: tuple[Any, str, str] | None) -> None:
        """One queue item under the reader's lock: a lesson, or (None) a rebuild."""
        from ..ruh_reader import disk_lock

        with disk_lock():
            if not self._ensure():
                return
            if self.rebuild:
                self._rebuild()
            if item is not None:
                self._lesson(*item)

    # ── the models (called under ruh_reader.disk_lock) ──────────────────

    def _ensure(self) -> bool:
        """The online learner on the current slow version; False when there is none."""
        from .. import ruh_reader

        current = ruh_reader.manifest("current")
        if current is None or ruh_reader.mode() == "off" or not ruh_reader.has_torch():
            self.online = None
            return False
        if self.online is not None and self.slow == current.get("created"):
            return True
        from ..ruh_reader import net
        from .online import Online

        slow = net.load(ruh_reader._files("current")[0])
        languages = list(current["languages"])
        rows = ruh_reader.seeds()
        lines, _ = ruh_reader.training_lines(
            ruh_reader.trainable(
                row for row in rows if ruh_reader.part(ruh_reader.group_of(row[0])) == "train"
            ),
            languages,
        )
        self.online = Online(slow, setting(), lines)
        self.slow = current.get("created")
        self.fit = ruh_reader.Fit(**current["fit"])
        self.languages = languages
        self.signs = [0, 0]
        fast = ruh_reader.fast_manifest()
        if fast is not None and fast.get("setting") == setting().to_dict():
            loaded = net.load(ruh_reader.fast_files()[0])
            self.online.fast.load_state_dict(loaded.state_dict())
            self.online.learned = list(fast.get("learned") or [])
        self.rebuild = self._unlearned()
        return True

    def _lessons(self) -> list[tuple[str, int, str]]:
        """Every learned lesson not yet consolidated, all owners, in the order given."""
        from .. import lughah, ruh_reader
        from . import store

        found = []
        for path in store.owners_with_lessons():
            found += store.unconsolidated_at(path, KIND)
        found.sort(key=lambda lesson: (lesson.created, lesson.digest))
        return [
            (
                ruh_reader.reading(lughah.own_words(lesson.text)),
                self.languages.index(lesson.language),
                lesson.digest,
            )
            for lesson in found
            if lesson.language in self.languages
        ]

    def _unlearned(self) -> bool:
        """Whether lessons are kept that the fast copy has not learned (or the other way)."""
        try:
            return {d for _o, _s, d in self._lessons()} != set(self.online.learned)
        except Exception:  # noqa: BLE001 - unreadable stores: rebuild to be safe
            return True

    def _rebuild(self) -> None:
        """Start again from the slow weights and learn the kept lessons in order."""
        lessons = self._lessons()
        self.online.replay(lessons)
        self.rebuild = False
        self.stats["rebuilds"] += 1
        self._publish(save=True)

    def _publish(self, save: bool) -> None:
        from .. import ruh_reader

        if self.slow is not None:
            ruh_reader.swap(self.online.serving_copy(), self.slow)
        if save:
            self._save()

    def _save(self) -> None:
        from .. import ruh_reader
        from .online import save_fast

        weights, described = ruh_reader.fast_files()
        if not self.online.learned:
            ruh_reader.drop_fast()
        else:
            save_fast(
                self.online,
                weights,
                described,
                {
                    "slow": self.slow,
                    "learned": list(self.online.learned),
                    "setting": setting().to_dict(),
                    "saved": datetime.now(UTC).isoformat(),
                },
            )
        self.since_save = 0

    def _posterior(self, model: Any, own: str) -> list[float]:
        from .. import ruh_reader
        from ..ruh_reader import net

        scored, counts = net.score(model, [own], list(range(len(self.languages))))
        return ruh_reader.reader_log_posterior(
            scored[0], counts[0], self.fit.kappa, self.fit.gamma, self.fit.ref
        )

    def _lesson(self, path: Any, digest: str, owner: str) -> None:
        from core.adaptive import paired_e_value

        from .. import lughah, ruh_reader, sijill
        from . import store

        lesson = store.get_at(path, digest)
        if lesson is None or lesson.status != "pending":
            return
        began = time.perf_counter()
        own = ruh_reader.reading(lughah.own_words(lesson.text))
        found = lughah.naive_posterior(lesson.text)
        if not own or set(found) != set(self.languages):
            store.drop_at(path, digest)
            return
        fast = self._posterior(self.online.fast, own)
        slow = self._posterior(self.online.slow, own)
        alone = ruh_reader._argmax([found[code] for code in self.languages])
        if ruh_reader._argmax(fast) != alone:  # MIZAN's check: both read one language
            store.drop_at(path, digest)
            self.stats["disagreed"] += 1
            return
        code = self.languages[alone]
        if ruh_reader.contradicted(lesson.text, code):  # and no third witness says otherwise
            store.drop_at(path, digest)
            self.stats["contradicted"] += 1
            return
        held = held_out(digest)
        part = self.stats["prequential"]["held_out" if held else "learned"]
        part["n"] += 1
        part["fast"] += -fast[alone]
        part["slow"] += -slow[alone]
        if held:
            store.settle_at(path, digest, "held_out", code)
            self.stats["held_out"] += 1
            if -slow[alone] < -fast[alone]:
                self.signs[0] += 1
            elif -fast[alone] < -slow[alone]:
                self.signs[1] += 1
            if paired_e_value(*self.signs) >= 1 / ALPHA:  # the fast copy reads worse
                logger.warning("Tadrib: the fast reader read held-out lessons worse; reset")
                self.online.reset()
                self.signs = [0, 0]
                self.stats["resets"] += 1
                self._publish(save=True)
            return
        self.online.learn(own, alone, digest)
        if not store.settle_at(path, digest, "learned", code):
            # Erased while it was learned: start again without it.
            self._rebuild()
            return
        self._publish(save=False)
        self.since_save += 1
        if self.since_save >= SAVE_EVERY:
            self._save()
        self.stats["learned"] += 1
        took = time.perf_counter() - began
        self.timings.append(took)
        self.stats["last"] = datetime.now(UTC).isoformat()
        if owner:
            sijill.note(
                "tadrib",
                {
                    "detail": f"MIZAN's reader learned the language of your message ({code}) in {took:.1f}s"
                },
                owner=owner,
            )

    # ── forgetting ──────────────────────────────────────────────────────

    def forget(self, digests: set[str], texts: Iterable[str] = ()) -> int:
        """Drop every model that learned these lessons; the fast copy is
        rebuilt from the slow weights with the lessons that remain."""
        from .. import ruh_reader

        texts = list(texts)
        erased = set(digests) | {ruh_reader.text_digest(t) for t in texts if t and t.strip()}
        with ruh_reader.disk_lock():
            learned = set(self.online.learned) if self.online is not None else set()
            hit = bool(erased & learned)
            if hit:
                ruh_reader.drop_fast()
            dropped = ruh_reader.forget(texts, digests)
            if hit:
                self.online.reset()
                ruh_reader.reset()  # serve the slow weights until the rebuild
        if hit or dropped:
            self.invalidate()
        return dropped + int(hit)

    def status(self) -> dict:
        ordered = sorted(self.timings)

        def mean(part: dict) -> dict:
            n = part["n"]
            return {
                "n": n,
                "fast": round(part["fast"] / n, 6) if n else None,
                "slow": round(part["slow"] / n, 6) if n else None,
            }

        from core.adaptive import paired_e_value

        return {
            **{k: v for k, v in self.stats.items() if k != "prequential"},
            "prequential": {name: mean(part) for name, part in self.stats["prequential"].items()},
            "safety": {
                "slow_better": self.signs[0],
                "fast_better": self.signs[1],
                "e_value": round(paired_e_value(*self.signs), 4),
                "reset_at": 1 / ALPHA,
            },
            "fast_lessons": len(self.online.learned) if self.online is not None else 0,
            "slow": self.slow,
            "queue": self.queue.qsize(),
            "seconds_per_lesson": {
                "n": len(ordered),
                "median": round(ordered[len(ordered) // 2], 3) if ordered else None,
                "p95": round(ordered[int(len(ordered) * 0.95)], 3) if ordered else None,
            },
            "running": self.thread is not None and self.thread.is_alive(),
        }


_trainer = _Trainer()


def configure(idle: Callable[[], bool]) -> None:
    """Learn only while ``idle()`` (no request runs); set by the app at startup."""
    _trainer.idle = idle


def slow_changed() -> None:
    """A night replaced the slow weights: the fast copy starts again from them."""
    _trainer.invalidate()


def forget_chat(owner: str, chat_id: str, texts: Iterable[str] = ()) -> dict:
    """Mahw: a chat's lessons are deleted and every model that learned them
    (or the chat's words, ``texts``) is dropped. Synchronous."""
    from . import store

    digests = store.drop_chat(owner, chat_id) if owner and chat_id else []
    dropped = _trainer.forget(set(digests), texts)
    return {"lessons": len(digests), "versions": dropped}


def reject(owner: str, digest: str) -> bool:
    """The person takes a lesson back: deleted, and forgotten by every model."""
    from . import store

    if not store.drop(owner, digest):
        return False
    _trainer.forget({digest})
    return True


def status() -> dict:
    from .. import ruh_reader

    return {
        "mode": mode(),
        # The serving reader: mode, gate, fit, and what shadow saw since the
        # last restart (counts only), read before the reader is ever turned on.
        "reader": ruh_reader.status(),
        "setting": setting().to_dict() if ruh_reader.has_torch() else None,
        "held_out": f"1/{HELD_OUT}",
        "trainer": _trainer.status(),
    }
