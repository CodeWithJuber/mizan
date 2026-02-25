"""
Tawbah Protocol (توبة) — Structured Error Recovery
====================================================

"Indeed, Allah loves those who are constantly repentant (Tawwabeen)
 and loves those who purify themselves." — Quran 2:222

Error recovery protocol that transforms failures into learning:
  1. Acknowledge (اعتراف) — detect and acknowledge the error
  2. Analyze (تحليل) — identify root cause
  3. Plan (خطة) — create a correction plan
  4. Apply (تطبيق) — execute the fix
  5. Verify (تحقق) — confirm the fix works

Errors are not failures — they are opportunities for Tazkiyah (purification).
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mizan.tawbah")


class TawbahStage(Enum):
    """Stages of the error recovery process."""
    ACKNOWLEDGE = "acknowledge"   # Detect and admit the error
    ANALYZE = "analyze"           # Find root cause
    PLAN = "plan"                 # Create correction plan
    APPLY = "apply"               # Execute the fix
    VERIFY = "verify"             # Confirm success
    COMPLETE = "complete"         # Recovery finished


@dataclass
class TawbahRecord:
    """Record of an error recovery process."""
    id: str
    agent_id: str
    error_type: str
    error_message: str
    task: str
    stage: TawbahStage = TawbahStage.ACKNOWLEDGE
    root_cause: str = ""
    correction_plan: str = ""
    fix_applied: str = ""
    verified: bool = False
    success: bool = False
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    attempts: int = 1
    lessons_learned: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "error_type": self.error_type,
            "error_message": self.error_message[:500],
            "task": self.task[:200],
            "stage": self.stage.value,
            "root_cause": self.root_cause,
            "correction_plan": self.correction_plan,
            "verified": self.verified,
            "success": self.success,
            "attempts": self.attempts,
            "lessons_learned": self.lessons_learned,
            "duration_s": (self.completed_at or time.time()) - self.started_at,
        }


class TawbahProtocol:
    """
    Structured error recovery system.

    Usage:
        tawbah = TawbahProtocol()

        # When an error occurs:
        record = tawbah.acknowledge(agent_id, error, task)
        tawbah.analyze(record, "Null pointer in line 42")
        tawbah.plan(record, "Add null check before access")
        tawbah.apply(record, "Added null check")
        tawbah.verify(record, success=True)

        # Get lessons from past errors:
        lessons = tawbah.get_lessons("coding")
    """

    MAX_ATTEMPTS = 3

    def __init__(self):
        self._records: Dict[str, TawbahRecord] = {}
        self._lessons: List[Dict] = []
        self._error_patterns: Dict[str, int] = {}

    def acknowledge(self, agent_id: str, error: Exception | str,
                    task: str) -> TawbahRecord:
        """
        Stage 1: Acknowledge the error.
        "The first step of repentance is recognition."
        """
        error_msg = str(error)
        error_type = type(error).__name__ if isinstance(error, Exception) else "TaskError"

        record_id = f"tawbah_{agent_id}_{int(time.time())}"
        record = TawbahRecord(
            id=record_id,
            agent_id=agent_id,
            error_type=error_type,
            error_message=error_msg,
            task=task,
            stage=TawbahStage.ACKNOWLEDGE,
        )

        self._records[record_id] = record
        self._error_patterns[error_type] = self._error_patterns.get(error_type, 0) + 1

        logger.info("[TAWBAH] Acknowledged: %s — %s", error_type, error_msg[:100])
        return record

    def analyze(self, record: TawbahRecord, root_cause: str) -> TawbahRecord:
        """
        Stage 2: Analyze root cause.
        "Understanding why you erred is the path to correction."
        """
        record.root_cause = root_cause
        record.stage = TawbahStage.ANALYZE
        logger.info("[TAWBAH] Root cause: %s", root_cause[:100])
        return record

    def plan(self, record: TawbahRecord, correction_plan: str) -> TawbahRecord:
        """
        Stage 3: Create correction plan.
        "Plan the correction before acting."
        """
        record.correction_plan = correction_plan
        record.stage = TawbahStage.PLAN
        logger.info("[TAWBAH] Plan: %s", correction_plan[:100])
        return record

    def apply(self, record: TawbahRecord, fix_description: str) -> TawbahRecord:
        """
        Stage 4: Apply the fix.
        "Act upon the correction with sincerity."
        """
        record.fix_applied = fix_description
        record.stage = TawbahStage.APPLY
        logger.info("[TAWBAH] Fix applied: %s", fix_description[:100])
        return record

    def verify(self, record: TawbahRecord, success: bool,
               lesson: str = "") -> TawbahRecord:
        """
        Stage 5: Verify the fix.
        "Confirm the correction has taken hold."
        """
        record.verified = True
        record.success = success
        record.stage = TawbahStage.VERIFY if not success else TawbahStage.COMPLETE
        record.completed_at = time.time()

        if success:
            record.lessons_learned = lesson or f"Fixed {record.error_type}: {record.root_cause}"
            self._lessons.append({
                "error_type": record.error_type,
                "root_cause": record.root_cause,
                "fix": record.fix_applied,
                "lesson": record.lessons_learned,
                "timestamp": time.time(),
            })
            logger.info("[TAWBAH] Verified SUCCESS: %s", record.lessons_learned[:100])
        else:
            record.attempts += 1
            if record.attempts < self.MAX_ATTEMPTS:
                record.stage = TawbahStage.ANALYZE  # Re-analyze
                logger.warning("[TAWBAH] Verification failed, attempt %d/%d",
                               record.attempts, self.MAX_ATTEMPTS)
            else:
                record.stage = TawbahStage.COMPLETE
                record.lessons_learned = f"UNRESOLVED after {self.MAX_ATTEMPTS} attempts: {record.error_type}"
                logger.error("[TAWBAH] Max attempts reached for %s", record.id)

        return record

    def get_lessons(self, error_type: str = None) -> List[Dict]:
        """Get lessons learned from past error recoveries."""
        if error_type:
            return [l for l in self._lessons if l["error_type"] == error_type]
        return list(self._lessons)

    def get_pattern_frequency(self) -> Dict[str, int]:
        """Get frequency of error patterns (for systemic issue detection)."""
        return dict(self._error_patterns)

    def has_prior_fix(self, error_type: str) -> Optional[Dict]:
        """Check if we have a prior fix for this error type."""
        for lesson in reversed(self._lessons):
            if lesson["error_type"] == error_type:
                return lesson
        return None

    def get_active_recoveries(self, agent_id: str = None) -> List[TawbahRecord]:
        """Get active (uncompleted) recovery records."""
        records = self._records.values()
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        return [r for r in records if r.stage != TawbahStage.COMPLETE]

    def stats(self) -> Dict:
        total = len(self._records)
        successful = sum(1 for r in self._records.values() if r.success)
        return {
            "total_recoveries": total,
            "successful": successful,
            "recovery_rate": successful / max(total, 1),
            "lessons_learned": len(self._lessons),
            "error_patterns": len(self._error_patterns),
            "active_recoveries": len(self.get_active_recoveries()),
        }
