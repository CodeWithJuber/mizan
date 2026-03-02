"""
Thinking Stream (تفكير مرئي - Visible Thinking)
================================================

Generates structured thinking events from the QCA pipeline,
enabling transparent AI reasoning visible to the user.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ThinkingPhase(StrEnum):
    """Phases of cognitive processing."""

    PERCEPTION = "perception"  # Input analysis
    COMPREHENSION = "comprehension"  # Understanding context
    REASONING = "reasoning"  # Logical processing
    MEMORY = "memory"  # Memory retrieval
    EVALUATION = "evaluation"  # Quality assessment
    GENERATION = "generation"  # Response formation
    REFLECTION = "reflection"  # Self-check / metacognition


@dataclass(frozen=True)
class ThinkingStep:
    """A single step in the thinking trace."""

    id: str
    phase: ThinkingPhase
    content: str
    confidence: float  # 0.0-1.0
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThinkingTrace:
    """Complete thinking trace for a request."""

    request_id: str
    steps: list[ThinkingStep] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def duration_ms(self) -> float:
        """Elapsed time in milliseconds."""
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    @property
    def avg_confidence(self) -> float:
        """Mean confidence across all steps."""
        if not self.steps:
            return 0.0
        return sum(step.confidence for step in self.steps) / len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialize trace to a plain dictionary."""
        return {
            "request_id": self.request_id,
            "steps": [
                {
                    "id": step.id,
                    "phase": step.phase.value,
                    "content": step.content,
                    "confidence": step.confidence,
                    "timestamp": step.timestamp,
                    "metadata": step.metadata,
                }
                for step in self.steps
            ],
            "duration_ms": self.duration_ms,
            "avg_confidence": self.avg_confidence,
        }


# Type alias for step callbacks
StepCallback = Any  # Callable[[str, ThinkingStep], None]


class ThinkingStream:
    """Generates and manages thinking traces for visible AI reasoning.

    Usage:
        stream = ThinkingStream()
        trace = stream.create_trace()
        stream.add_step(trace.request_id, ThinkingPhase.PERCEPTION, "Analyzing input...")
        stream.add_step(trace.request_id, ThinkingPhase.REASONING, "Applying logic...")
        stream.complete(trace.request_id)
    """

    def __init__(self, max_traces: int = 100) -> None:
        self._traces: dict[str, ThinkingTrace] = {}
        self._max_traces = max_traces
        self._callbacks: list[StepCallback] = []

    def create_trace(self, request_id: str | None = None) -> ThinkingTrace:
        """Start a new thinking trace."""
        rid = request_id or str(uuid.uuid4())
        trace = ThinkingTrace(request_id=rid)
        self._traces[rid] = trace
        self._enforce_limit()
        return trace

    def add_step(
        self,
        request_id: str,
        phase: ThinkingPhase,
        content: str,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> ThinkingStep | None:
        """Add a thinking step to a trace. Returns None if trace not found."""
        trace = self._traces.get(request_id)
        if not trace:
            return None

        # Clamp confidence to valid range
        clamped_confidence = max(0.0, min(1.0, confidence))

        step = ThinkingStep(
            id=str(uuid.uuid4()),
            phase=phase,
            content=content,
            confidence=clamped_confidence,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        trace.steps.append(step)

        for callback in self._callbacks:
            try:
                callback(request_id, step)
            except Exception:
                # Don't let callback failures break the pipeline
                pass

        return step

    def complete(self, request_id: str) -> ThinkingTrace | None:
        """Mark a trace as complete."""
        trace = self._traces.get(request_id)
        if trace:
            trace.completed_at = time.time()
        return trace

    def get_trace(self, request_id: str) -> ThinkingTrace | None:
        """Retrieve a thinking trace by request ID."""
        return self._traces.get(request_id)

    def on_step(self, callback: StepCallback) -> None:
        """Register a callback invoked on each new thinking step."""
        self._callbacks.append(callback)

    def _enforce_limit(self) -> None:
        """Evict oldest traces when the buffer exceeds max_traces."""
        if len(self._traces) <= self._max_traces:
            return
        sorted_ids = sorted(
            self._traces.keys(),
            key=lambda rid: self._traces[rid].started_at,
        )
        overflow = len(self._traces) - self._max_traces
        for rid in sorted_ids[:overflow]:
            del self._traces[rid]


def generate_thinking_events(
    query: str,
    context: dict[str, Any] | None = None,
) -> ThinkingTrace:
    """Generate a standard thinking trace for a query.

    Creates a trace with common cognitive phases for
    demonstration and testing purposes.
    """
    stream = ThinkingStream()
    trace = stream.create_trace()
    rid = trace.request_id

    stream.add_step(
        rid, ThinkingPhase.PERCEPTION, f"Received: '{query[:80]}...'", 0.9
    )

    if context:
        stream.add_step(
            rid,
            ThinkingPhase.MEMORY,
            f"Retrieved {len(context)} context items",
            0.7,
        )

    stream.add_step(
        rid, ThinkingPhase.COMPREHENSION, "Understanding intent and context", 0.8
    )
    stream.add_step(
        rid, ThinkingPhase.REASONING, "Processing through cognitive layers", 0.75
    )
    stream.add_step(
        rid, ThinkingPhase.EVALUATION, "Assessing response quality", 0.85
    )
    stream.add_step(rid, ThinkingPhase.GENERATION, "Forming response", 0.8)
    stream.complete(rid)

    return trace
