"""
Ihsan Mode (إحسان) — Proactive Excellence
============================================

"Indeed, Allah commands justice (Adl) and excellence (Ihsan)." — Quran 16:90
"What is Ihsan? To worship Allah as if you see Him." — Hadith Jibril

Ihsan mode enables agents to go beyond what is asked:
- After completing a task, suggest related improvements
- Proactively identify issues before they become problems
- Offer context-aware enhancements
- Transform reactive task execution into proactive assistance
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.ihsan")


@dataclass
class IhsanSuggestion:
    """A proactive suggestion from Ihsan mode."""

    id: str
    agent_id: str
    task_context: str
    suggestion: str
    category: str  # improvement, prevention, optimization, learning
    confidence: float = 0.5
    accepted: bool | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "suggestion": self.suggestion,
            "category": self.category,
            "confidence": self.confidence,
            "accepted": self.accepted,
        }


class IhsanMode:
    """
    Proactive excellence engine.

    When enabled, agents don't just complete tasks — they look for ways
    to exceed expectations. After each task, Ihsan checks:
      1. Can this be done better? (optimization)
      2. Are there related issues? (prevention)
      3. Is there additional context the user would benefit from? (learning)
      4. Can the underlying process be improved? (improvement)

    Usage:
        ihsan = IhsanMode()
        suggestions = ihsan.analyze_completion(agent_id, task, result)
        ihsan.record_feedback(suggestion_id, accepted=True)
    """

    # Minimum Nafs level to use Ihsan mode
    MIN_NAFS_LEVEL = 3  # Mulhama (Inspired) or above

    def __init__(self):
        self._suggestions: dict[str, IhsanSuggestion] = {}
        self._acceptance_rate: float = 0.0
        self._total_suggested: int = 0
        self._total_accepted: int = 0

    def is_eligible(self, nafs_level: int) -> bool:
        """Check if agent's Nafs level is high enough for Ihsan mode."""
        return nafs_level >= self.MIN_NAFS_LEVEL

    def analyze_completion(
        self, agent_id: str, task: str, result: dict, nafs_level: int = 1
    ) -> list[IhsanSuggestion]:
        """
        Analyze a completed task and generate proactive suggestions.
        Only produces suggestions if agent is at Mulhama level or above.
        """
        if not self.is_eligible(nafs_level):
            return []

        suggestions = []
        task_lower = task.lower()
        success = result.get("success", False)

        # Pattern: coding tasks → suggest tests
        if success and any(w in task_lower for w in ["code", "implement", "write", "fix"]):
            suggestions.append(
                self._create_suggestion(
                    agent_id,
                    task,
                    "Consider adding tests for the changes made",
                    "improvement",
                    0.7,
                )
            )

        # Pattern: file operations → suggest backup
        if any(w in task_lower for w in ["delete", "modify", "overwrite", "update file"]):
            suggestions.append(
                self._create_suggestion(
                    agent_id,
                    task,
                    "Consider creating a backup before modifying",
                    "prevention",
                    0.6,
                )
            )

        # Pattern: research → suggest deeper analysis
        if success and any(w in task_lower for w in ["research", "analyze", "review"]):
            suggestions.append(
                self._create_suggestion(
                    agent_id,
                    task,
                    "Related topics identified that may provide additional context",
                    "learning",
                    0.5,
                )
            )

        # Pattern: slow execution → suggest optimization
        duration = result.get("duration_ms", 0)
        if success and duration > 10000:
            suggestions.append(
                self._create_suggestion(
                    agent_id,
                    task,
                    f"Task took {duration / 1000:.1f}s — consider caching or parallel execution",
                    "optimization",
                    0.6,
                )
            )

        # Pattern: errors occurred → suggest error handling
        if not success:
            suggestions.append(
                self._create_suggestion(
                    agent_id,
                    task,
                    "Consider adding error handling or input validation",
                    "prevention",
                    0.7,
                )
            )

        return suggestions

    def _create_suggestion(
        self, agent_id: str, task: str, suggestion: str, category: str, confidence: float
    ) -> IhsanSuggestion:
        self._total_suggested += 1
        sid = f"ihsan_{agent_id}_{self._total_suggested}"
        s = IhsanSuggestion(
            id=sid,
            agent_id=agent_id,
            task_context=task[:200],
            suggestion=suggestion,
            category=category,
            confidence=confidence,
        )
        self._suggestions[sid] = s
        return s

    def record_feedback(self, suggestion_id: str, accepted: bool):
        """Record user feedback on a suggestion."""
        if suggestion_id in self._suggestions:
            self._suggestions[suggestion_id].accepted = accepted
            if accepted:
                self._total_accepted += 1
            self._update_acceptance_rate()

    def _update_acceptance_rate(self):
        rated = [s for s in self._suggestions.values() if s.accepted is not None]
        if rated:
            self._acceptance_rate = sum(1 for s in rated if s.accepted) / len(rated)

    def get_acceptance_rate(self) -> float:
        return self._acceptance_rate

    def stats(self) -> dict:
        return {
            "total_suggestions": self._total_suggested,
            "total_accepted": self._total_accepted,
            "acceptance_rate": round(self._acceptance_rate, 3),
            "active_suggestions": len(
                [s for s in self._suggestions.values() if s.accepted is None]
            ),
        }
