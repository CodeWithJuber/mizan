"""
Shukr System (شكر) — Positive Reinforcement & Strength Tracking
=================================================================

"If you are grateful, I will surely increase you." — Quran 14:7

Tracks and reinforces what works:
- Identifies agent strengths and successful patterns
- Reinforces effective strategies through increased confidence
- Focuses agents on what they do well
- Provides gratitude-based feedback loops
"""

import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.shukr")


@dataclass
class StrengthRecord:
    """A recorded strength/success pattern."""

    pattern: str
    category: str
    success_count: int = 0
    total_count: int = 0
    avg_duration_ms: float = 0.0
    last_success: float = field(default_factory=time.time)
    confidence_boost: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_count, 1)


class ShukrSystem:
    """
    Positive reinforcement system that tracks and amplifies strengths.

    Usage:
        shukr = ShukrSystem()
        shukr.record_success(agent_id, "coding", "python_debugging", 1500)
        shukr.record_success(agent_id, "coding", "python_debugging", 1200)
        strengths = shukr.get_strengths(agent_id)
        boost = shukr.get_confidence_boost(agent_id, "coding")
    """

    def __init__(self):
        self._strengths: dict[str, dict[str, StrengthRecord]] = defaultdict(dict)
        self._gratitude_log: list[dict] = []

    def record_success(self, agent_id: str, category: str, pattern: str, duration_ms: float = 0):
        """Record a successful task completion."""
        key = f"{category}:{pattern}"
        if key not in self._strengths[agent_id]:
            self._strengths[agent_id][key] = StrengthRecord(
                pattern=pattern,
                category=category,
            )

        record = self._strengths[agent_id][key]
        record.success_count += 1
        record.total_count += 1
        record.last_success = time.time()

        # Update average duration
        if duration_ms > 0:
            n = record.success_count
            record.avg_duration_ms = (record.avg_duration_ms * (n - 1) + duration_ms) / n

        # Calculate confidence boost (logarithmic growth)
        import math

        record.confidence_boost = min(0.2, math.log(record.success_count + 1) * 0.05)

        if record.success_count % 10 == 0:
            self._gratitude_log.append(
                {
                    "agent_id": agent_id,
                    "pattern": pattern,
                    "milestone": record.success_count,
                    "timestamp": time.time(),
                }
            )
            logger.info(
                "[SHUKR] Agent %s reached %d successes in %s",
                agent_id,
                record.success_count,
                pattern,
            )

    def record_failure(self, agent_id: str, category: str, pattern: str):
        """Record a task failure (updates total without adding success)."""
        key = f"{category}:{pattern}"
        if key not in self._strengths[agent_id]:
            self._strengths[agent_id][key] = StrengthRecord(
                pattern=pattern,
                category=category,
            )
        self._strengths[agent_id][key].total_count += 1

    def get_strengths(self, agent_id: str, min_success: int = 3) -> list[dict]:
        """Get agent's identified strengths, sorted by success rate."""
        records = self._strengths.get(agent_id, {})
        strengths = [
            {
                "pattern": r.pattern,
                "category": r.category,
                "success_rate": round(r.success_rate, 3),
                "success_count": r.success_count,
                "avg_duration_ms": round(r.avg_duration_ms, 1),
                "confidence_boost": round(r.confidence_boost, 3),
            }
            for r in records.values()
            if r.success_count >= min_success
        ]
        strengths.sort(key=lambda x: (-x["success_rate"], -x["success_count"]))
        return strengths

    def get_confidence_boost(self, agent_id: str, category: str) -> float:
        """Get confidence boost for a task category based on past successes."""
        records = self._strengths.get(agent_id, {})
        boosts = [
            r.confidence_boost
            for key, r in records.items()
            if r.category == category and r.success_rate > 0.7
        ]
        return sum(boosts) / max(len(boosts), 1) if boosts else 0.0

    def get_best_agent_for(self, agent_ids: list[str], category: str) -> str | None:
        """Find the agent with highest success rate in a category."""
        best_agent = None
        best_rate = -1

        for aid in agent_ids:
            records = self._strengths.get(aid, {})
            category_records = [
                r for r in records.values() if r.category == category and r.total_count >= 3
            ]
            if category_records:
                avg_rate = sum(r.success_rate for r in category_records) / len(category_records)
                if avg_rate > best_rate:
                    best_rate = avg_rate
                    best_agent = aid

        return best_agent

    def get_gratitude_milestones(self, agent_id: str = None) -> list[dict]:
        """Get gratitude milestones (celebration moments)."""
        if agent_id:
            return [g for g in self._gratitude_log if g["agent_id"] == agent_id]
        return list(self._gratitude_log)

    def stats(self, agent_id: str = None) -> dict:
        if agent_id:
            records = self._strengths.get(agent_id, {})
            return {
                "total_patterns": len(records),
                "total_successes": sum(r.success_count for r in records.values()),
                "top_category": Counter(r.category for r in records.values()).most_common(1)[0][0]
                if records
                else None,
            }
        return {
            "agents_tracked": len(self._strengths),
            "total_milestones": len(self._gratitude_log),
        }
