"""
Ruh Engine (روح) — Agent Vitality/Energy System
=================================================

"And they ask you about the Ruh (spirit).
 Say: The Ruh is of the affair of my Lord." — Quran 17:85

The Ruh engine manages agent cognitive energy:
- Complex tasks deplete energy
- Rest periods regenerate energy
- Low energy triggers task redistribution
- Prevents agent burnout and encourages balanced workloads

Energy model inspired by the soul's need for spiritual refreshment.
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.ruh")


@dataclass
class RuhState:
    """Current vitality state of an agent's Ruh."""

    energy: float = 100.0  # Current energy (0-100)
    max_energy: float = 100.0  # Maximum energy capacity
    regen_rate: float = 2.0  # Energy regenerated per minute of rest
    last_activity: float = field(default_factory=time.time)
    last_rest_start: float | None = None
    total_tasks_since_rest: int = 0
    fatigue_level: float = 0.0  # 0=fresh, 1=exhausted

    # Energy costs by task complexity
    ENERGY_COSTS = {
        "trivial": 2.0,
        "simple": 5.0,
        "moderate": 15.0,
        "complex": 30.0,
        "extreme": 50.0,
    }

    # Fatigue thresholds
    FATIGUE_THRESHOLDS = {
        "fresh": (0.0, 0.2),
        "alert": (0.2, 0.4),
        "working": (0.4, 0.6),
        "tired": (0.6, 0.8),
        "exhausted": (0.8, 1.0),
    }


class RuhEngine:
    """
    Manages agent energy levels and prevents cognitive burnout.

    Usage:
        ruh = RuhEngine()
        state = ruh.get_state(agent_id)
        can_proceed = ruh.can_handle_task(agent_id, "complex")
        ruh.consume_energy(agent_id, "complex")
        ruh.rest(agent_id)
    """

    def __init__(self):
        self._states: dict[str, RuhState] = {}

    def initialize_agent(
        self, agent_id: str, max_energy: float = 100.0, regen_rate: float = 2.0
    ) -> RuhState:
        """Initialize Ruh state for a new agent."""
        state = RuhState(
            energy=max_energy,
            max_energy=max_energy,
            regen_rate=regen_rate,
        )
        self._states[agent_id] = state
        return state

    def get_state(self, agent_id: str) -> RuhState:
        """Get current Ruh state, creating default if needed."""
        if agent_id not in self._states:
            self.initialize_agent(agent_id)
        state = self._states[agent_id]
        self._apply_regeneration(agent_id)
        return state

    def can_handle_task(self, agent_id: str, complexity: str = "moderate") -> bool:
        """Check if agent has enough energy for a task."""
        state = self.get_state(agent_id)
        cost = state.ENERGY_COSTS.get(complexity, 15.0)
        return state.energy >= cost

    def consume_energy(
        self, agent_id: str, complexity: str = "moderate", duration_ms: float = 0
    ) -> float:
        """
        Consume energy for task execution.
        Returns remaining energy.
        """
        state = self.get_state(agent_id)
        cost = state.ENERGY_COSTS.get(complexity, 15.0)

        # Duration adds fatigue
        if duration_ms > 5000:
            cost *= 1.0 + (duration_ms / 60000.0)  # +1x per minute

        state.energy = max(0.0, state.energy - cost)
        state.last_activity = time.time()
        state.last_rest_start = None
        state.total_tasks_since_rest += 1

        # Update fatigue
        state.fatigue_level = 1.0 - (state.energy / state.max_energy)

        if state.energy < 20:
            logger.warning("Agent %s energy low: %.1f%%", agent_id, state.energy)
        if state.energy <= 0:
            logger.warning("Agent %s exhausted (Ruh depleted)", agent_id)

        return state.energy

    def rest(self, agent_id: str) -> float:
        """Start resting — agent enters idle state for regeneration."""
        state = self.get_state(agent_id)
        state.last_rest_start = time.time()
        state.total_tasks_since_rest = 0
        return state.energy

    def _apply_regeneration(self, agent_id: str):
        """Apply passive energy regeneration based on idle time."""
        state = self._states[agent_id]
        now = time.time()

        if state.last_rest_start:
            rest_minutes = (now - state.last_rest_start) / 60.0
            regen = rest_minutes * state.regen_rate
            state.energy = min(state.max_energy, state.energy + regen)
            state.fatigue_level = 1.0 - (state.energy / state.max_energy)
        else:
            # Passive regen even when not explicitly resting (but slower)
            idle_minutes = (now - state.last_activity) / 60.0
            if idle_minutes > 1.0:
                passive_regen = idle_minutes * (state.regen_rate * 0.3)
                state.energy = min(state.max_energy, state.energy + passive_regen)
                state.fatigue_level = 1.0 - (state.energy / state.max_energy)

    def classify_task_complexity(self, task: str) -> str:
        """Estimate task complexity from description."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["hello", "hi", "status", "list", "show"]):
            return "trivial"
        if any(w in task_lower for w in ["read", "check", "find", "get"]):
            return "simple"
        if any(w in task_lower for w in ["analyze", "review", "compare", "summarize"]):
            return "moderate"
        if any(w in task_lower for w in ["research", "implement", "refactor", "design"]):
            return "complex"
        if any(w in task_lower for w in ["architect", "migrate", "overhaul", "rewrite"]):
            return "extreme"
        return "moderate"

    def get_fatigue_label(self, agent_id: str) -> str:
        """Get human-readable fatigue status."""
        state = self.get_state(agent_id)
        for label, (low, high) in state.FATIGUE_THRESHOLDS.items():
            if low <= state.fatigue_level < high:
                return label
        return "exhausted"

    def get_vitality_report(self, agent_id: str) -> dict:
        """Get full vitality report for an agent."""
        state = self.get_state(agent_id)
        return {
            "energy": round(state.energy, 1),
            "max_energy": state.max_energy,
            "energy_percent": round(state.energy / state.max_energy * 100, 1),
            "fatigue_level": round(state.fatigue_level, 3),
            "fatigue_label": self.get_fatigue_label(agent_id),
            "tasks_since_rest": state.total_tasks_since_rest,
            "regen_rate": state.regen_rate,
            "is_resting": state.last_rest_start is not None,
        }

    def find_most_rested(self, agent_ids: list) -> str | None:
        """Find the most rested agent from a list (for task delegation)."""
        if not agent_ids:
            return None
        best = None
        best_energy = -1
        for aid in agent_ids:
            state = self.get_state(aid)
            if state.energy > best_energy:
                best_energy = state.energy
                best = aid
        return best
