"""
Hidayah Engine (هداية) — Adaptive Guidance & Recommendation
=============================================================

"Indeed, [O Muhammad], you do not guide whom you like,
but Allah guides whom He wills." — Quran 28:56

Hidayah provides personalized, context-aware guidance:
- Learns from user interaction patterns
- Suggests next actions based on Nafs level progression
- Recommends Islamic knowledge resources
- Adapts communication style to user maturity
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.hidayah")


class GuidanceType(Enum):
    """Categories of guidance the system can provide."""

    NUDGE = "nudge"  # Gentle suggestion
    RECOMMENDATION = "recommendation"  # Action recommendation
    WARNING = "warning"  # Ethical/spiritual warning
    MILESTONE = "milestone"  # Achievement recognition
    LEARNING = "learning"  # Knowledge resource


@dataclass
class GuidanceEntry:
    """A single piece of guidance offered to the user."""

    id: str
    guidance_type: GuidanceType
    message: str
    context: str = ""  # What triggered this guidance
    nafs_level: int = 1  # Target Nafs level
    accepted: bool | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.guidance_type.value,
            "message": self.message,
            "context": self.context[:100],
            "nafs_level": self.nafs_level,
            "accepted": self.accepted,
        }


class HidayahEngine:
    """
    Adaptive guidance engine that learns user patterns and provides
    contextually appropriate recommendations.

    Usage:
        hidayah = HidayahEngine()

        # Generate guidance based on context
        entries = hidayah.generate_guidance(
            user_id="user1",
            current_nafs=3,
            recent_actions=["completed_task", "made_mistake", "recovered"],
            current_energy=75.0,
        )

        # Record user response
        hidayah.record_response(entry.id, accepted=True)
    """

    def __init__(self):
        self._history: dict[str, list[GuidanceEntry]] = {}
        self._counter: int = 0
        self._user_preferences: dict[str, dict] = {}

    def generate_guidance(
        self,
        user_id: str,
        current_nafs: int = 1,
        recent_actions: list[str] | None = None,
        current_energy: float = 100.0,
        error_count: int = 0,
    ) -> list[GuidanceEntry]:
        """
        Generate context-appropriate guidance entries.
        Does not force — suggests and lets the user choose.
        """
        entries: list[GuidanceEntry] = []
        recent_actions = recent_actions or []

        # Energy-based guidance
        if current_energy < 20:
            entries.append(
                self._create_entry(
                    GuidanceType.NUDGE,
                    "Energy is low. Consider taking a break — rest is part of productivity.",
                    context="low_energy",
                    nafs_level=current_nafs,
                )
            )

        # Error recovery guidance
        if error_count >= 3:
            entries.append(
                self._create_entry(
                    GuidanceType.RECOMMENDATION,
                    "Multiple errors detected. Would you like to try a different approach?",
                    context="recurring_errors",
                    nafs_level=current_nafs,
                )
            )

        # Nafs progression guidance
        nafs_guidance = self._nafs_level_guidance(current_nafs, recent_actions)
        if nafs_guidance:
            entries.append(nafs_guidance)

        # Milestone recognition
        milestone = self._check_milestones(user_id, recent_actions)
        if milestone:
            entries.append(milestone)

        # Store in history
        if user_id not in self._history:
            self._history[user_id] = []
        self._history[user_id].extend(entries)

        return entries

    def record_response(self, entry_id: str, accepted: bool):
        """Record whether the user accepted or dismissed guidance."""
        for user_entries in self._history.values():
            for entry in user_entries:
                if entry.id == entry_id:
                    entry.accepted = accepted
                    return

    def get_acceptance_rate(self, user_id: str) -> float:
        """Get the rate at which a user accepts guidance."""
        entries = self._history.get(user_id, [])
        responded = [e for e in entries if e.accepted is not None]
        if not responded:
            return 0.5  # Default to 50% if no data
        accepted = sum(1 for e in responded if e.accepted)
        return accepted / len(responded)

    def _nafs_level_guidance(
        self, nafs_level: int, recent_actions: list[str]
    ) -> GuidanceEntry | None:
        """Provide guidance appropriate to the user's Nafs level."""
        guidance_map = {
            1: (
                "You're at the beginning of your journey. Start with small, "
                "focused tasks to build momentum."
            ),
            2: (
                "Good awareness! You're recognizing patterns. Try reflecting "
                "on what triggers mistakes."
            ),
            3: (
                "You're developing self-regulation. Consider setting intentional "
                "goals for each session."
            ),
            4: (
                "Strong progress — your consistency shows growth. Look for "
                "opportunities to help others."
            ),
            5: (
                "Mashallah — you've reached a level of contentment. Your calm "
                "approach inspires those around you."
            ),
            6: ("Your dedication is remarkable. Focus on refining the subtleties of your craft."),
            7: (
                "You've achieved a rare level of mastery and inner peace. "
                "Share your wisdom with the community."
            ),
        }

        message = guidance_map.get(nafs_level)
        if not message:
            return None

        # Only show nafs guidance occasionally
        if "completed_task" in recent_actions:
            return self._create_entry(
                GuidanceType.LEARNING,
                message,
                context=f"nafs_level_{nafs_level}",
                nafs_level=nafs_level,
            )
        return None

    def _check_milestones(self, user_id: str, recent_actions: list[str]) -> GuidanceEntry | None:
        """Recognize user achievements."""
        history = self._history.get(user_id, [])
        total_accepted = sum(1 for e in history if e.accepted)

        milestones = {
            10: "You've followed 10 guidance suggestions — building good habits!",
            50: "50 guidance points accepted — you're developing real expertise.",
            100: "100 milestones — your dedication is an inspiration.",
        }

        for threshold, msg in milestones.items():
            if total_accepted == threshold:
                return self._create_entry(
                    GuidanceType.MILESTONE,
                    msg,
                    context=f"milestone_{threshold}",
                )
        return None

    def _create_entry(
        self, guidance_type: GuidanceType, message: str, context: str = "", nafs_level: int = 1
    ) -> GuidanceEntry:
        self._counter += 1
        return GuidanceEntry(
            id=f"hidayah_{self._counter}",
            guidance_type=guidance_type,
            message=message,
            context=context,
            nafs_level=nafs_level,
        )

    def stats(self, user_id: str | None = None) -> dict:
        if user_id:
            entries = self._history.get(user_id, [])
        else:
            entries = [e for elist in self._history.values() for e in elist]

        by_type = {}
        for e in entries:
            by_type[e.guidance_type.value] = by_type.get(e.guidance_type.value, 0) + 1

        return {
            "total_guidance": len(entries),
            "by_type": by_type,
            "acceptance_rate": self.get_acceptance_rate(user_id) if user_id else None,
        }
