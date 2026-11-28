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

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.tawbah")

# ── Loop detection: the same failure, again and again, is not progress ──────
# Ported from ForgeKit's diagnose.js and doom-loop guard. Within one run each failed tool
# call is reduced to a signature (the tool, its error's class, the message with what
# varies between identical failures taken out); the THRASH_K-th identical signature
# stops that path with a diagnosis instead of a fourth try.

THRASH_K = 3

_NORMALISE: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
        "<ts>",
    ),
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\b"), "<ts>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<id>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<addr>"),
    (re.compile(r"\b[0-9a-f]{12,}\b", re.I), "<hex>"),
    # /home/x/src/a.py → a.py: the machine's prefix goes, the file's name is signal.
    (re.compile(r"(?:/[\w.~-]+)+/([\w.-]+)"), r"\1"),
    (re.compile(r"\b[A-Za-z]:\\(?:[\w.~ -]+\\)*([\w.-]+)"), r"\1"),
    (re.compile(r"\bline \d+", re.I), "line <n>"),
    (re.compile(r":\d+(?::\d+)?\b"), ":<n>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*m?s\b"), "<dur>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"[ \t]+"), " "),
)
_EXCEPTION = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Error|Exception|Exit|Interrupt))\b")
_CLASSES = (
    (
        "dependency",
        re.compile(r"module not found|cannot find module|no module named|ERESOLVE", re.I),
    ),
    ("permission", re.compile(r"EACCES|permission denied|unauthori[sz]ed|forbidden", re.I)),
    ("timeout", re.compile(r"timeout|timed out|ETIMEDOUT", re.I)),
    ("not_found", re.compile(r"not found|no such file|does not exist|404", re.I)),
    ("assertion", re.compile(r"assertion|expected .* actual", re.I)),
)


def normalize_error(text: str) -> str:
    """The error with what varies between identical failures taken out: times, ids,
    addresses, digests, machine paths, line numbers, durations and other numbers."""
    value = str(text or "").replace("\r\n", "\n")
    for pattern, replacement in _NORMALISE:
        value = pattern.sub(replacement, value)
    return value.strip()


def error_text(result: Any) -> str:
    """What a failed tool result says went wrong: its error, else the end of stderr."""
    if not isinstance(result, dict):
        return str(result)[:2000]
    if result.get("error"):
        return str(result["error"])[:2000]
    stderr = str(result.get("stderr") or "").strip()
    if stderr:
        lines = [line for line in stderr.splitlines() if line.strip()]
        return "\n".join(lines[-3:])[:2000]  # the root error is usually last
    code = result.get("exit_code", result.get("returncode", result.get("status")))
    return f"exit {code}" if code is not None else json.dumps(result, default=str)[:500]


def error_class(text: str) -> str:
    """An exception's name when the text names one, else a kind of failure."""
    found = _EXCEPTION.findall(str(text or ""))
    if found:
        return str(found[-1])
    for name, pattern in _CLASSES:
        if pattern.search(str(text or "")):
            return name
    return "error"


def failure_signature(tool_name: str, result: Any) -> str | None:
    """The signature of a failed call (None when the call did not fail)."""
    from agents.execution_contract import tool_result_failed

    if not tool_result_failed(result):
        return None
    text = error_text(result)
    key = f"{tool_name}\0{error_class(text)}\0{normalize_error(text)}"
    return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:16]


class TawbahLoop:
    """One run's failed tool calls, counted by signature."""

    def __init__(self, k: int = THRASH_K):
        self.k = k
        self.counts: dict[str, int] = {}
        self.diagnoses: list[dict] = []

    def observe(self, tool_name: str, result: Any) -> dict | None:
        """The diagnosis when this failure is the k-th (or a later) identical one."""
        signature = failure_signature(tool_name, result)
        if signature is None:
            return None
        count = self.counts[signature] = self.counts.get(signature, 0) + 1
        if count < self.k:
            return None
        text = error_text(result)
        diagnosis = {
            "tool": tool_name,
            "signature": signature,
            "error_class": error_class(text),
            "error": normalize_error(text).splitlines()[0][:200] if text.strip() else "",
            "count": count,
            "first": count == self.k,
        }
        if diagnosis["first"]:
            self.diagnoses.append(diagnosis)
        return diagnosis

    @staticmethod
    def stop_note(result: Any, diagnosis: dict) -> dict:
        """The result the model reads instead of a plain failure: the error kept, and
        why this path is closed."""
        base = result if isinstance(result, dict) else {"error": str(result)}
        note = (
            f"This path failed {diagnosis['count']} times with the same error "
            f"({diagnosis['error_class']}: {diagnosis['error']}). Trying it again will "
            "fail the same way: change approach (a different tool, different input, or "
            "a different plan), or tell the person what blocks you and what you tried."
        )
        return {**base, "tawbah": note}


class TawbahStage(Enum):
    """Stages of the error recovery process."""

    ACKNOWLEDGE = "acknowledge"  # Detect and admit the error
    ANALYZE = "analyze"  # Find root cause
    PLAN = "plan"  # Create correction plan
    APPLY = "apply"  # Execute the fix
    VERIFY = "verify"  # Confirm success
    COMPLETE = "complete"  # Recovery finished


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
    completed_at: float | None = None
    attempts: int = 1
    lessons_learned: str = ""

    def to_dict(self) -> dict:
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
        self._records: dict[str, TawbahRecord] = {}
        self._lessons: list[dict[str, Any]] = []
        self._error_patterns: dict[str, int] = {}

    def acknowledge(self, agent_id: str, error: Exception | str, task: str) -> TawbahRecord:
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

    def verify(self, record: TawbahRecord, success: bool, lesson: str = "") -> TawbahRecord:
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
            self._lessons.append(
                {
                    "error_type": record.error_type,
                    "root_cause": record.root_cause,
                    "fix": record.fix_applied,
                    "lesson": record.lessons_learned,
                    "timestamp": time.time(),
                }
            )
            logger.info("[TAWBAH] Verified SUCCESS: %s", record.lessons_learned[:100])
        else:
            record.attempts += 1
            if record.attempts < self.MAX_ATTEMPTS:
                record.stage = TawbahStage.ANALYZE  # Re-analyze
                logger.warning(
                    "[TAWBAH] Verification failed, attempt %d/%d",
                    record.attempts,
                    self.MAX_ATTEMPTS,
                )
            else:
                record.stage = TawbahStage.COMPLETE
                record.lessons_learned = (
                    f"UNRESOLVED after {self.MAX_ATTEMPTS} attempts: {record.error_type}"
                )
                logger.error("[TAWBAH] Max attempts reached for %s", record.id)

        return record

    def loop(self, agent_id: str, task: str, diagnosis: dict) -> TawbahRecord:
        """Record a path that failed the same way THRASH_K times in one run: the error
        acknowledged, its signature as the cause, a change of approach as the plan."""
        record = self.acknowledge(
            agent_id, f"{diagnosis.get('tool')}: {diagnosis.get('error', '')}", task
        )
        record.error_type = "repeated_failure"
        self._error_patterns["repeated_failure"] = (
            self._error_patterns.get("repeated_failure", 0) + 1
        )
        self.analyze(
            record,
            f"{diagnosis.get('tool')} failed {diagnosis.get('count')} times with the same "
            f"{diagnosis.get('error_class')} (signature {diagnosis.get('signature')})",
        )
        self.plan(record, "Stop retrying this path; change approach or report what blocks it")
        return record

    def get_lessons(self, error_type: str | None = None) -> list[dict[str, Any]]:
        """Get lessons learned from past error recoveries."""
        if error_type:
            return [lesson for lesson in self._lessons if lesson["error_type"] == error_type]
        return list(self._lessons)

    def get_pattern_frequency(self) -> dict[str, int]:
        """Get frequency of error patterns (for systemic issue detection)."""
        return dict(self._error_patterns)

    def has_prior_fix(self, error_type: str) -> dict[str, Any] | None:
        """Check if we have a prior fix for this error type."""
        for lesson in self._lessons[::-1]:
            if lesson["error_type"] == error_type:
                return lesson
        return None

    def get_active_recoveries(self, agent_id: str | None = None) -> list[TawbahRecord]:
        """Get active (uncompleted) recovery records."""
        records = list(self._records.values())
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        return [r for r in records if r.stage != TawbahStage.COMPLETE]

    def stats(self) -> dict:
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
