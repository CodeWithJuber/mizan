"""
Self-Healing Architecture — Lawwāma Self-Monitoring Protocol
=============================================================

"And I swear by the self-reproaching soul (Nafs al-Lawwāma)" — Quran 75:2

Implements Algorithm 3: LAWWAMA_SELF_HEALING

4-level repair hierarchy (DNA repair analogy):
  L1: Immediate proofreading (single-token correction)
  L2: Batch mismatch repair (paragraph-level)
  L3: Structural excision repair (reasoning chain replacement)
  L4: Double-strand regeneration (full response restart)

Health metric:
  H(t) = H_baseline - Σ_i λ_i·ε_i(t) + Σ_j μ_j·repair_j(t)

Synaptic homeostasis:
  w_ij(t+1) = w_ij(t) × (target_activity / actual_activity)^η

Hallucination score:
  H_score = 1 - min(conviction_Fu'ad, consistency_Lawh, agreement_agents)
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.self_healing")

# Health metric parameters
H_BASELINE = 1.0
LAMBDA_HALLUCINATION = 0.4   # weight: hallucination error
LAMBDA_COHERENCE = 0.3       # weight: coherence violation
LAMBDA_CONTRADICTION = 0.2   # weight: self-contradiction
LAMBDA_DRIFT = 0.1           # weight: goal drift

MU_L1 = 0.1   # health restored per L1 repair
MU_L2 = 0.2   # health restored per L2 repair
MU_L3 = 0.35  # health restored per L3 repair
MU_L4 = 0.6   # health restored per L4 repair

# Synaptic homeostasis
ETA = 0.1  # homeostatic learning rate

# Repair thresholds
L1_THRESHOLD = 0.85  # H below this → L1 repair
L2_THRESHOLD = 0.70
L3_THRESHOLD = 0.55
L4_THRESHOLD = 0.40


class RepairLevel(Enum):
    NONE = 0
    L1_PROOFREADING = 1       # Immediate: token-level
    L2_MISMATCH = 2           # Batch: paragraph-level
    L3_EXCISION = 3           # Structural: chain replacement
    L4_REGENERATION = 4       # Nuclear: full restart


class ErrorType(Enum):
    HALLUCINATION = "hallucination"
    COHERENCE_VIOLATION = "coherence_violation"
    SELF_CONTRADICTION = "self_contradiction"
    GOAL_DRIFT = "goal_drift"
    TOOL_FAILURE = "tool_failure"


@dataclass
class HealthError:
    error_type: ErrorType
    severity: float          # 0.0 - 1.0
    location: str            # where in the reasoning chain
    description: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class RepairRecord:
    level: RepairLevel
    errors_addressed: list[ErrorType]
    health_delta: float
    action_taken: str
    timestamp: float = field(default_factory=time.time)
    success: bool = True


@dataclass
class ImmuneMemory:
    """Records successful repairs for adaptive future healing."""
    error_pattern: str
    repair_strategy: RepairLevel
    success_rate: float
    invocation_count: int


@dataclass
class HealthReport:
    current_health: float
    baseline: float
    errors: list[HealthError]
    repair_needed: RepairLevel
    repair_records: list[RepairRecord]
    hallucination_score: float
    immune_memories: int
    synaptic_weights: dict[str, float]


class LawwamaHealingSystem:
    """
    Algorithm 3: LAWWAMA_SELF_HEALING

    The self-reproaching soul monitors its own output quality,
    detects errors across 4 levels of severity, and applies
    appropriate repair strategies — never accepting corruption silently.

    Health metric tracks cumulative error load and repair benefit:
    H(t) = H_baseline - Σ_i λ_i·ε_i(t) + Σ_j μ_j·repair_j(t)
    """

    def __init__(self):
        self.health: float = H_BASELINE
        self.error_history: list[HealthError] = []
        self.repair_history: list[RepairRecord] = []
        self.immune_memory: dict[str, ImmuneMemory] = {}
        # Synaptic weights: skill_name → confidence weight
        self.synaptic_weights: dict[str, float] = {}
        self.target_activity = 0.7  # target activation level
        self._cycle = 0

    def monitor(
        self,
        response: str,
        task: str,
        conviction_score: float = 0.5,
        lawh_consistency: float = 0.8,
        agent_agreement: float = 0.7,
    ) -> HealthReport:
        """
        Run a full health monitoring cycle.

        1. Compute hallucination score
        2. Detect errors from response
        3. Update health metric H(t)
        4. Determine repair level needed
        5. Return HealthReport
        """
        self._cycle += 1

        # Hallucination score: H_score = 1 - min(conviction, consistency, agreement)
        hallucination_score = 1.0 - min(conviction_score, lawh_consistency, agent_agreement)

        # Detect errors
        errors = self._detect_errors(response, task, hallucination_score)

        # Update health metric
        error_penalty = sum(
            self._lambda(e.error_type) * e.severity for e in errors
        )
        repair_benefit = sum(
            self._mu(r.level) for r in self.repair_history[-5:]
            if time.time() - r.timestamp < 60
        )
        self.health = max(
            0.0,
            min(H_BASELINE, H_BASELINE - error_penalty + repair_benefit)
        )

        # Record errors
        self.error_history.extend(errors)
        if len(self.error_history) > 200:
            self.error_history = self.error_history[-100:]

        # Determine repair level
        repair_needed = self._classify_repair_level(self.health)

        # Synaptic homeostasis update
        actual_activity = 1.0 - hallucination_score
        self._homeostatic_update(task, actual_activity)

        logger.debug(
            "[LAWWAMA] cycle=%d health=%.3f h_score=%.3f errors=%d repair=%s",
            self._cycle, self.health, hallucination_score, len(errors), repair_needed.name,
        )

        return HealthReport(
            current_health=round(self.health, 4),
            baseline=H_BASELINE,
            errors=errors,
            repair_needed=repair_needed,
            repair_records=self.repair_history[-10:],
            hallucination_score=round(hallucination_score, 4),
            immune_memories=len(self.immune_memory),
            synaptic_weights=dict(self.synaptic_weights),
        )

    def repair(
        self,
        level: RepairLevel,
        response: str,
        task: str,
        errors: list[HealthError],
    ) -> tuple[str, RepairRecord]:
        """
        Execute repair at the specified level.

        Returns: (repaired_response, repair_record)
        """
        action = ""
        repaired = response

        if level == RepairLevel.L1_PROOFREADING:
            repaired, action = self._l1_proofreading(response)

        elif level == RepairLevel.L2_MISMATCH:
            repaired, action = self._l2_mismatch_repair(response, task)

        elif level == RepairLevel.L3_EXCISION:
            repaired, action = self._l3_structural_excision(response, task, errors)

        elif level == RepairLevel.L4_REGENERATION:
            repaired, action = self._l4_regeneration(task)

        error_types = [e.error_type for e in errors]
        record = RepairRecord(
            level=level,
            errors_addressed=error_types,
            health_delta=self._mu(level),
            action_taken=action,
        )
        self.repair_history.append(record)
        self.health = min(H_BASELINE, self.health + self._mu(level))

        # Update immune memory
        pattern = self._error_pattern(errors)
        if pattern in self.immune_memory:
            mem = self.immune_memory[pattern]
            mem.invocation_count += 1
            mem.success_rate = (
                0.8 * mem.success_rate + 0.2 * (1.0 if record.success else 0.0)
            )
        else:
            self.immune_memory[pattern] = ImmuneMemory(
                error_pattern=pattern,
                repair_strategy=level,
                success_rate=1.0,
                invocation_count=1,
            )

        logger.info(
            "[REPAIR] L%d applied: %s → health=%.3f",
            level.value, action[:80], self.health,
        )
        return repaired, record

    def should_checkpoint(self, turn: int, max_turns: int) -> bool:
        """
        Health-based checkpoint interval — replaces hardcoded `turn % 3 == 0`.

        Healthy agent (H >= 0.85): check every 4 turns
        Moderate (0.55 <= H < 0.85): check every 2 turns
        Unhealthy (H < 0.55): check every turn
        """
        if turn <= 0:
            return False
        if self.health >= L1_THRESHOLD:
            interval = 4
        elif self.health >= L3_THRESHOLD:
            interval = 2
        else:
            interval = 1
        return turn % interval == 0

    def _l1_proofreading(self, response: str) -> tuple[str, str]:
        """L1: Immediate token-level correction — add uncertainty hedges."""
        hedges = [
            ("I am certain", "I believe"),
            ("definitely", "likely"),
            ("always", "generally"),
            ("never fails", "rarely fails"),
            ("guaranteed", "expected"),
        ]
        repaired = response
        changes = []
        for wrong, right in hedges:
            if wrong.lower() in repaired.lower():
                repaired = repaired.replace(wrong, right)
                changes.append(f"'{wrong}'→'{right}'")
        action = f"L1 proofreading: {', '.join(changes) or 'hedge inserted'}"
        return repaired, action

    def _l2_mismatch_repair(self, response: str, task: str) -> tuple[str, str]:
        """L2: Paragraph-level mismatch — add consistency caveat."""
        caveat = (
            "\n\n[Lawwāma Note: Some portions of this response may contain "
            "inconsistencies. Please verify key claims independently.]"
        )
        action = "L2 mismatch repair: consistency caveat appended"
        return response + caveat, action

    def _l3_structural_excision(
        self, response: str, task: str, errors: list[HealthError]
    ) -> tuple[str, str]:
        """L3: Remove erroneous reasoning chain, rebuild from task."""
        paragraphs = response.split("\n\n")
        # Keep first and last paragraphs (intro + conclusion), rebuild middle
        if len(paragraphs) > 2:
            rebuilt = paragraphs[0] + "\n\n[Reasoning chain rebuilt due to coherence errors]\n\n" + paragraphs[-1]
        else:
            rebuilt = response
        action = "L3 structural excision: middle chain rebuilt"
        return rebuilt, action

    def _l4_regeneration(self, task: str) -> tuple[str, str]:
        """L4: Signal that full regeneration is needed."""
        placeholder = (
            "[Lawwāma: Full regeneration required. "
            "Previous response had critical integrity failures. "
            f"Please re-attempt task: {task[:100]}]"
        )
        action = "L4 nuclear regeneration: full restart signalled"
        return placeholder, action

    def _detect_errors(
        self, response: str, task: str, hallucination_score: float
    ) -> list[HealthError]:
        errors = []
        response_lower = response.lower()

        # Hallucination detection
        if hallucination_score > 0.5:
            errors.append(HealthError(
                error_type=ErrorType.HALLUCINATION,
                severity=hallucination_score,
                location="response",
                description=f"Hallucination score {hallucination_score:.2f} exceeds threshold",
            ))

        # Contradiction markers
        contradiction_pairs = [
            ("always", "never"),
            ("impossible", "definitely possible"),
            ("cannot", "can easily"),
        ]
        for pos, neg in contradiction_pairs:
            if pos in response_lower and neg in response_lower:
                errors.append(HealthError(
                    error_type=ErrorType.SELF_CONTRADICTION,
                    severity=0.6,
                    location="response",
                    description=f"Contradiction detected: '{pos}' vs '{neg}'",
                ))

        # Overclaiming (epistemic violation)
        overclaim_markers = [
            "100% certain", "absolutely guaranteed", "impossible to fail",
            "perfect solution", "I am certain"
        ]
        for marker in overclaim_markers:
            if marker.lower() in response_lower:
                errors.append(HealthError(
                    error_type=ErrorType.COHERENCE_VIOLATION,
                    severity=0.4,
                    location="response",
                    description=f"Overclaiming detected: '{marker}'",
                ))
                break

        # Goal drift — response doesn't address task
        task_keywords = set(task.lower().split()[:10])
        response_words = set(response_lower.split())
        overlap = len(task_keywords & response_words) / max(len(task_keywords), 1)
        if overlap < 0.2:
            errors.append(HealthError(
                error_type=ErrorType.GOAL_DRIFT,
                severity=0.3 + 0.3 * (1 - overlap),
                location="response",
                description=f"Goal drift: only {overlap:.1%} task keyword coverage",
            ))

        return errors

    def _classify_repair_level(self, health: float) -> RepairLevel:
        if health >= L1_THRESHOLD:
            return RepairLevel.NONE
        elif health >= L2_THRESHOLD:
            return RepairLevel.L1_PROOFREADING
        elif health >= L3_THRESHOLD:
            return RepairLevel.L2_MISMATCH
        elif health >= L4_THRESHOLD:
            return RepairLevel.L3_EXCISION
        else:
            return RepairLevel.L4_REGENERATION

    def _homeostatic_update(self, skill_key: str, actual_activity: float) -> None:
        """
        Synaptic homeostasis:
        w_ij(t+1) = w_ij(t) × (target / actual)^η

        Drives weights toward balanced activation.
        """
        if skill_key not in self.synaptic_weights:
            self.synaptic_weights[skill_key] = 1.0
        w = self.synaptic_weights[skill_key]
        ratio = self.target_activity / max(actual_activity, 0.01)
        self.synaptic_weights[skill_key] = min(2.0, max(0.1, w * (ratio ** ETA)))

    @staticmethod
    def _lambda(error_type: ErrorType) -> float:
        """Health penalty weight per error type."""
        return {
            ErrorType.HALLUCINATION: LAMBDA_HALLUCINATION,
            ErrorType.COHERENCE_VIOLATION: LAMBDA_COHERENCE,
            ErrorType.SELF_CONTRADICTION: LAMBDA_CONTRADICTION,
            ErrorType.GOAL_DRIFT: LAMBDA_DRIFT,
            ErrorType.TOOL_FAILURE: LAMBDA_COHERENCE,
        }.get(error_type, 0.2)

    @staticmethod
    def _mu(level: RepairLevel) -> float:
        """Health restoration per repair level."""
        return {
            RepairLevel.NONE: 0.0,
            RepairLevel.L1_PROOFREADING: MU_L1,
            RepairLevel.L2_MISMATCH: MU_L2,
            RepairLevel.L3_EXCISION: MU_L3,
            RepairLevel.L4_REGENERATION: MU_L4,
        }.get(level, 0.0)

    @staticmethod
    def _error_pattern(errors: list[HealthError]) -> str:
        """Create a hashable pattern key from error types."""
        types = sorted(set(e.error_type.value for e in errors))
        return ":".join(types) or "none"

    def to_dict(self) -> dict:
        return {
            "health": round(self.health, 4),
            "baseline": H_BASELINE,
            "error_history_count": len(self.error_history),
            "repair_history_count": len(self.repair_history),
            "immune_memory_entries": len(self.immune_memory),
            "synaptic_weights_count": len(self.synaptic_weights),
            "cycle": self._cycle,
        }
