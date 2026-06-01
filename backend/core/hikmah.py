"""
Hikmah Engine (حكمة) — Wisdom Distillation
============================================

"He gives wisdom (hikmah) to whom He wills, and whoever is given wisdom has been
 given much good. And none remembers except those of understanding (ulu al-albab)."
— Quran 2:269

Wisdom, in the Qur'an, is *applied* understanding — knowing the right course for
a situation, distilled from experience (the ulu al-albab are precisely those who
*remember* and *reflect*). It is not raw information; it is the principle drawn
from many experiences.

MIZAN already *accumulates* experience — Shukr records what worked, Tawbah records
lessons from errors, Lubb evaluates reasoning quality — but it had no engine to
*distil* those into reusable counsel. Hikmah is that engine.

It ingests three kinds of experience:
  - success    (from Shukr)  → "this approach works for situations like X"
  - correction (from Tawbah) → "for error type Y, the fix/lesson is Z"
  - reflection (from Lubb)   → "reasoning of kind X tends to have flaw Y"

…and promotes a recurring observation to an *applicable principle* once it has
enough support. `advise(task)` then returns the principles relevant to a new task.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.hikmah")


class CounselSource(Enum):
    SUCCESS = "success"        # reinforced by what worked (Shukr)
    CORRECTION = "correction"  # learned from an error (Tawbah)
    REFLECTION = "reflection"  # noticed in metacognition (Lubb)


@dataclass
class Principle:
    """A distilled, applicable piece of wisdom for a class of situations."""

    situation_type: str
    counsel: str
    source: CounselSource
    support_count: int = 1
    confidence: float = 0.3
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    examples: list[str] = field(default_factory=list)

    @property
    def is_applicable(self) -> bool:
        """A principle is trusted counsel once it has repeated support."""
        return self.support_count >= HikmahEngine.MIN_SUPPORT

    def to_dict(self) -> dict:
        return {
            "situation_type": self.situation_type,
            "counsel": self.counsel,
            "source": self.source.value,
            "support_count": self.support_count,
            "confidence": round(self.confidence, 3),
            "applicable": self.is_applicable,
        }


@dataclass
class Counsel:
    """Wisdom offered for a specific task."""

    task: str
    principles: list[Principle] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task": self.task[:120],
            "summary": self.summary,
            "confidence": round(self.confidence, 3),
            "principles": [p.to_dict() for p in self.principles],
        }


def _classify_situation(text: str) -> str:
    """Coarse situation type from task/observation text (keyword heuristic)."""
    t = text.lower()
    buckets = {
        "coding": ["code", "function", "bug", "implement", "refactor", "compile", "class", "import"],
        "debugging": ["error", "fix", "broken", "fail", "exception", "traceback", "debug"],
        "research": ["research", "find", "search", "investigate", "look up", "explore"],
        "filesystem": ["file", "read", "write", "directory", "path", "delete", "folder"],
        "data": ["data", "csv", "json", "parse", "dataframe", "analyze", "dataset"],
        "deployment": ["deploy", "release", "docker", "build", "ci", "publish", "server"],
        "writing": ["write", "draft", "document", "explain", "summarize", "report"],
        "security": ["auth", "token", "password", "secret", "permission", "vault", "security"],
    }
    for situation, keywords in buckets.items():
        if any(k in t for k in keywords):
            return situation
    return "general"


class HikmahEngine:
    """
    Wisdom distillation from accumulated experience.

    Usage:
        hikmah = HikmahEngine()
        hikmah.observe_success("coding", "wrote tests before refactoring")
        hikmah.observe_correction("ModuleNotFoundError", "install dep before import")
        ...
        counsel = hikmah.advise("refactor the auth module")
        for p in counsel.principles:
            print(p.counsel)
    """

    # Observations needed before a principle becomes trusted counsel
    MIN_SUPPORT = 3

    def __init__(self):
        # key: f"{situation_type}::{source}" → Principle
        self._principles: dict[str, Principle] = {}

    # ── ingestion ──────────────────────────────────────────────

    def observe_success(self, situation: str, detail: str) -> Principle:
        """Reinforce wisdom from something that worked (Shukr signal)."""
        situation_type = _classify_situation(situation + " " + detail)
        counsel = f"For {situation_type} tasks, this approach has worked: {detail[:120]}"
        return self._reinforce(situation_type, counsel, CounselSource.SUCCESS, detail)

    def observe_correction(self, error_type: str, lesson: str) -> Principle:
        """Distil wisdom from an error's lesson (Tawbah signal)."""
        situation_type = _classify_situation(error_type + " " + lesson)
        counsel = f"When facing '{error_type[:50]}': {lesson[:120]}"
        return self._reinforce(situation_type, counsel, CounselSource.CORRECTION, lesson)

    def observe_reflection(self, situation: str, note: str) -> Principle:
        """Record a metacognitive observation (Lubb signal)."""
        situation_type = _classify_situation(situation + " " + note)
        counsel = f"In {situation_type} reasoning, watch for: {note[:120]}"
        return self._reinforce(situation_type, counsel, CounselSource.REFLECTION, note)

    def _reinforce(
        self, situation_type: str, counsel: str, source: CounselSource, example: str
    ) -> Principle:
        key = f"{situation_type}::{source.value}"
        now = time.time()
        if key in self._principles:
            p = self._principles[key]
            p.support_count += 1
            p.last_seen = now
            # Confidence grows logarithmically with support (cf. Shukr)
            p.confidence = min(0.95, 0.3 + math.log(p.support_count + 1) * 0.18)
            # Keep the most recent counsel phrasing + a few examples
            p.counsel = counsel
            if example and example not in p.examples:
                p.examples.append(example[:120])
                p.examples = p.examples[-5:]
        else:
            p = Principle(
                situation_type=situation_type,
                counsel=counsel,
                source=source,
                support_count=1,
                confidence=0.3,
                examples=[example[:120]] if example else [],
            )
            self._principles[key] = p
        logger.debug(
            "[HIKMAH] %s support=%d conf=%.2f", key, p.support_count, p.confidence
        )
        return p

    # ── retrieval ──────────────────────────────────────────────

    def distill(self, min_support: int | None = None) -> list[Principle]:
        """Return applicable principles, strongest first."""
        threshold = self.MIN_SUPPORT if min_support is None else min_support
        applicable = [p for p in self._principles.values() if p.support_count >= threshold]
        applicable.sort(key=lambda p: (p.confidence, p.support_count), reverse=True)
        return applicable

    def advise(self, task: str, top_k: int = 3) -> Counsel:
        """
        Offer wisdom relevant to a new task: matches by situation type first,
        then by keyword overlap, ranked by confidence.
        """
        situation_type = _classify_situation(task)
        task_words = {w for w in task.lower().split() if len(w) > 3}

        scored: list[tuple[float, Principle]] = []
        for p in self._principles.values():
            if not p.is_applicable:
                continue
            score = p.confidence
            if p.situation_type == situation_type:
                score += 0.5  # same-domain principles are most relevant
            overlap = len(task_words & {w for w in p.counsel.lower().split() if len(w) > 3})
            score += 0.05 * overlap
            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        principles = [p for _s, p in scored[:top_k]]

        if principles:
            confidence = sum(p.confidence for p in principles) / len(principles)
            summary = (
                f"{len(principles)} relevant principle(s) for {situation_type} tasks. "
                f"Foremost: {principles[0].counsel}"
            )
        else:
            confidence = 0.0
            summary = (
                f"No distilled wisdom yet for {situation_type} tasks — proceed from "
                f"first principles and this will become a learning example."
            )

        return Counsel(
            task=task,
            principles=principles,
            summary=summary,
            confidence=round(confidence, 3),
        )

    def stats(self) -> dict:
        applicable = self.distill()
        by_source = {s.value: 0 for s in CounselSource}
        for p in self._principles.values():
            by_source[p.source.value] += 1
        return {
            "total_principles": len(self._principles),
            "applicable_principles": len(applicable),
            "by_source": by_source,
        }
