"""
Tawakkul Protocol (توكل) — Graceful Delegation & Degradation
==============================================================

"And whoever relies upon Allah (Tawakkul) — then He is sufficient for him." — Quran 65:3
"Tie your camel, then put your trust in Allah." — Hadith

When an agent cannot handle a task, Tawakkul provides:
- Graceful delegation to a more capable agent
- Escalation to human when no agent can handle it
- Fallback strategies for degraded operation
- No silent failures — always communicate transparently
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.tawakkul")


class DelegationReason(Enum):
    """Why delegation is needed."""

    CAPABILITY_MISSING = "capability_missing"  # Agent lacks the skill
    ENERGY_LOW = "energy_low"  # Ruh depleted
    NAFS_INSUFFICIENT = "nafs_insufficient"  # Permission level too low
    CONFIDENCE_LOW = "confidence_low"  # Not sure enough to proceed
    OVERLOADED = "overloaded"  # Too many concurrent tasks
    ERROR_RECURRING = "error_recurring"  # Same error keeps happening
    HUMAN_REQUIRED = "human_required"  # Needs human judgment


@dataclass
class DelegationRecord:
    """Record of a task delegation."""

    id: str
    from_agent: str
    to_agent: str | None  # None = escalated to human
    task: str
    reason: DelegationReason
    success: bool | None = None
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent or "human",
            "task": self.task[:200],
            "reason": self.reason.value,
            "success": self.success,
            "duration_s": (self.resolved_at or time.time()) - self.created_at,
        }


class TawakkulProtocol:
    """
    Graceful delegation and degradation protocol.

    Usage:
        tawakkul = TawakkulProtocol()

        # Check if delegation is needed
        if tawakkul.should_delegate(agent_id, task, energy=15, nafs_level=1):
            target = tawakkul.find_delegate(task, available_agents, ruh_engine, shukr)
            record = tawakkul.delegate(agent_id, target, task, DelegationReason.ENERGY_LOW)

        # Escalate to human
        record = tawakkul.escalate_to_human(agent_id, task, "Requires business decision")
    """

    def __init__(self):
        self._records: dict[str, DelegationRecord] = {}
        self._delegation_count: int = 0

    def should_delegate(
        self,
        agent_id: str,
        task: str,
        energy: float = 100,
        nafs_level: int = 1,
        error_count: int = 0,
        confidence: float = 1.0,
    ) -> DelegationReason | None:
        """
        Determine if an agent should delegate a task.
        Returns the reason for delegation, or None if the agent should proceed.
        """
        if energy < 10:
            return DelegationReason.ENERGY_LOW

        if error_count >= 3:
            return DelegationReason.ERROR_RECURRING

        if confidence < 0.3:
            return DelegationReason.CONFIDENCE_LOW

        # Check task complexity vs nafs level
        task_lower = task.lower()
        requires_high_nafs = any(
            w in task_lower
            for w in [
                "system config",
                "delete",
                "deploy",
                "production",
                "sensitive",
                "credential",
                "admin",
            ]
        )
        if requires_high_nafs and nafs_level < 4:
            return DelegationReason.NAFS_INSUFFICIENT

        return None

    def find_delegate(
        self, task: str, available_agents: dict, ruh_engine=None, shukr_system=None
    ) -> str | None:
        """
        Find the best agent to delegate to.
        Uses Ruh (energy) and Shukr (strength tracking) if available.
        """
        if not available_agents:
            return None

        candidates = []
        task_category = self._classify_task_category(task)

        for agent_id, agent in available_agents.items():
            score = 0.0

            # Prefer agents with higher Nafs level
            nafs = getattr(agent, "nafs_level", 1)
            score += nafs * 10

            # Prefer agents with energy
            if ruh_engine:
                state = ruh_engine.get_state(agent_id)
                score += state.energy * 0.5

            # Prefer agents strong in this category
            if shukr_system:
                boost = shukr_system.get_confidence_boost(agent_id, task_category)
                score += boost * 100

            # Prefer agents with high success rate
            success_rate = getattr(agent, "success_rate", 0.0)
            score += success_rate * 20

            candidates.append((agent_id, score))

        if candidates:
            candidates.sort(key=lambda x: -x[1])
            return candidates[0][0]

        return None

    def delegate(
        self, from_agent: str, to_agent: str, task: str, reason: DelegationReason
    ) -> DelegationRecord:
        """Record a delegation from one agent to another."""
        self._delegation_count += 1
        record_id = f"tawakkul_{self._delegation_count}"
        record = DelegationRecord(
            id=record_id,
            from_agent=from_agent,
            to_agent=to_agent,
            task=task,
            reason=reason,
        )
        self._records[record_id] = record
        logger.info(
            "[TAWAKKUL] Delegated from %s to %s: %s (%s)",
            from_agent,
            to_agent,
            task[:50],
            reason.value,
        )
        return record

    def escalate_to_human(self, from_agent: str, task: str, reason: str = "") -> DelegationRecord:
        """Escalate to human when no agent can handle the task."""
        self._delegation_count += 1
        record_id = f"tawakkul_{self._delegation_count}"
        record = DelegationRecord(
            id=record_id,
            from_agent=from_agent,
            to_agent=None,
            task=task,
            reason=DelegationReason.HUMAN_REQUIRED,
        )
        self._records[record_id] = record
        logger.warning(
            "[TAWAKKUL] Escalated to human from %s: %s — %s", from_agent, task[:50], reason
        )
        return record

    def resolve(self, record_id: str, success: bool):
        """Mark a delegation as resolved."""
        if record_id in self._records:
            self._records[record_id].success = success
            self._records[record_id].resolved_at = time.time()

    def get_pending_escalations(self) -> list[DelegationRecord]:
        """Get tasks escalated to human that are still pending."""
        return [r for r in self._records.values() if r.to_agent is None and r.success is None]

    def _classify_task_category(self, task: str) -> str:
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "implement", "fix", "debug"]):
            return "coding"
        if any(w in task_lower for w in ["research", "analyze", "study"]):
            return "research"
        if any(w in task_lower for w in ["write", "draft", "compose"]):
            return "writing"
        if any(w in task_lower for w in ["email", "message", "send"]):
            return "communication"
        return "general"

    def stats(self) -> dict:
        total = len(self._records)
        resolved = [r for r in self._records.values() if r.success is not None]
        successful = sum(1 for r in resolved if r.success)
        human_escalations = sum(1 for r in self._records.values() if r.to_agent is None)
        return {
            "total_delegations": total,
            "resolved": len(resolved),
            "successful": successful,
            "delegation_success_rate": successful / max(len(resolved), 1),
            "human_escalations": human_escalations,
            "pending_escalations": len(self.get_pending_escalations()),
        }
