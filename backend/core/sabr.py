"""
Sabr Engine (صبر) — Patience & Long-Running Task Management
=============================================================

"O you who believe, seek help through patience (Sabr) and prayer." — Quran 2:153
"Indeed, the patient will be given their reward without account." — 39:10

Manages long-running tasks with:
- Task decomposition into manageable steps
- Progress tracking with milestones
- Graceful interruption and resumption
- Timeout handling with dignity (no panic)
- Persistent state for resumable workflows
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.sabr")


class SabrTaskState(Enum):
    """States of a long-running task."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"  # Waiting for external input/resource
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SabrStep:
    """A single step in a decomposed long-running task."""

    index: int
    description: str
    state: SabrTaskState = SabrTaskState.PENDING
    result: Any = None
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "description": self.description,
            "state": self.state.value,
            "has_result": self.result is not None,
            "error": self.error,
        }


@dataclass
class SabrWorkflow:
    """A long-running workflow managed by the Sabr engine."""

    id: str
    agent_id: str
    task: str
    steps: list[SabrStep] = field(default_factory=list)
    state: SabrTaskState = SabrTaskState.PENDING
    current_step: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    progress: float = 0.0  # 0.0 to 1.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "task": self.task[:200],
            "state": self.state.value,
            "current_step": self.current_step,
            "total_steps": len(self.steps),
            "progress": round(self.progress, 3),
            "steps": [s.to_dict() for s in self.steps],
        }


class SabrEngine:
    """
    Long-running task management with patience and persistence.

    Usage:
        sabr = SabrEngine()

        # Create a workflow with steps
        workflow = sabr.create_workflow(agent_id, task, [
            "Research the topic",
            "Analyze findings",
            "Draft the report",
            "Review and polish",
        ])

        # Execute steps one at a time
        sabr.start_step(workflow.id)
        sabr.complete_step(workflow.id, result="Research complete")
        sabr.start_step(workflow.id)
        ...

        # Pause and resume
        sabr.pause(workflow.id)
        sabr.resume(workflow.id)
    """

    def __init__(self):
        self._workflows: dict[str, SabrWorkflow] = {}

    def create_workflow(
        self, agent_id: str, task: str, step_descriptions: list[str]
    ) -> SabrWorkflow:
        """Create a new long-running workflow with defined steps."""
        workflow_id = f"sabr_{agent_id}_{int(time.time())}"
        steps = [SabrStep(index=i, description=desc) for i, desc in enumerate(step_descriptions)]
        workflow = SabrWorkflow(
            id=workflow_id,
            agent_id=agent_id,
            task=task,
            steps=steps,
        )
        self._workflows[workflow_id] = workflow
        logger.info("[SABR] Created workflow %s with %d steps", workflow_id, len(steps))
        return workflow

    def decompose_task(self, task: str) -> list[str]:
        """
        Decompose a complex task into manageable steps.
        Uses heuristics — can be enhanced with LLM decomposition.
        """
        task_lower = task.lower()

        # Coding task decomposition
        if any(w in task_lower for w in ["implement", "build", "create", "develop"]):
            return [
                "Understand requirements and plan approach",
                "Set up necessary files and structure",
                "Implement core functionality",
                "Add error handling and edge cases",
                "Test the implementation",
                "Review and refine",
            ]

        # Research task decomposition
        if any(w in task_lower for w in ["research", "investigate", "study", "analyze"]):
            return [
                "Define research scope and questions",
                "Gather sources and data",
                "Analyze and synthesize findings",
                "Draw conclusions",
                "Compile final report",
            ]

        # Writing task decomposition
        if any(w in task_lower for w in ["write", "draft", "compose", "document"]):
            return [
                "Outline structure and key points",
                "Research supporting material",
                "Write first draft",
                "Review and revise",
                "Final polish and formatting",
            ]

        # Default decomposition
        return [
            "Analyze the task requirements",
            "Execute the main work",
            "Verify results",
        ]

    def start_step(self, workflow_id: str) -> SabrStep | None:
        """Start the current step of a workflow."""
        wf = self._workflows.get(workflow_id)
        if not wf or wf.current_step >= len(wf.steps):
            return None

        wf.state = SabrTaskState.RUNNING
        if wf.started_at is None:
            wf.started_at = time.time()

        step = wf.steps[wf.current_step]
        step.state = SabrTaskState.RUNNING
        step.started_at = time.time()

        logger.info(
            "[SABR] Step %d/%d: %s", wf.current_step + 1, len(wf.steps), step.description[:50]
        )
        return step

    def complete_step(
        self, workflow_id: str, result: Any = None, error: str = None
    ) -> SabrWorkflow | None:
        """Complete the current step and advance."""
        wf = self._workflows.get(workflow_id)
        if not wf or wf.current_step >= len(wf.steps):
            return None

        step = wf.steps[wf.current_step]
        step.completed_at = time.time()

        if error:
            step.state = SabrTaskState.FAILED
            step.error = error
            # Don't advance — let the agent retry or handle
        else:
            step.state = SabrTaskState.COMPLETED
            step.result = result
            wf.current_step += 1

        # Update progress
        completed = sum(1 for s in wf.steps if s.state == SabrTaskState.COMPLETED)
        wf.progress = completed / len(wf.steps)

        # Check if all steps are done
        if wf.current_step >= len(wf.steps):
            wf.state = SabrTaskState.COMPLETED
            wf.completed_at = time.time()
            logger.info("[SABR] Workflow %s completed (%.0f%%)", workflow_id, wf.progress * 100)

        return wf

    def pause(self, workflow_id: str) -> bool:
        """Pause a running workflow (can be resumed later)."""
        wf = self._workflows.get(workflow_id)
        if wf and wf.state == SabrTaskState.RUNNING:
            wf.state = SabrTaskState.PAUSED
            if wf.current_step < len(wf.steps):
                wf.steps[wf.current_step].state = SabrTaskState.PAUSED
            logger.info("[SABR] Paused workflow %s at step %d", workflow_id, wf.current_step)
            return True
        return False

    def resume(self, workflow_id: str) -> SabrWorkflow | None:
        """Resume a paused workflow."""
        wf = self._workflows.get(workflow_id)
        if wf and wf.state == SabrTaskState.PAUSED:
            wf.state = SabrTaskState.RUNNING
            logger.info("[SABR] Resumed workflow %s at step %d", workflow_id, wf.current_step)
            return wf
        return None

    def cancel(self, workflow_id: str) -> bool:
        """Cancel a workflow."""
        wf = self._workflows.get(workflow_id)
        if wf and wf.state not in (SabrTaskState.COMPLETED, SabrTaskState.CANCELLED):
            wf.state = SabrTaskState.CANCELLED
            wf.completed_at = time.time()
            return True
        return False

    def get_workflow(self, workflow_id: str) -> SabrWorkflow | None:
        return self._workflows.get(workflow_id)

    def get_active_workflows(self, agent_id: str = None) -> list[SabrWorkflow]:
        """Get all active (non-completed) workflows."""
        active = [
            wf
            for wf in self._workflows.values()
            if wf.state in (SabrTaskState.RUNNING, SabrTaskState.PAUSED, SabrTaskState.WAITING)
        ]
        if agent_id:
            active = [wf for wf in active if wf.agent_id == agent_id]
        return active

    def stats(self) -> dict:
        total = len(self._workflows)
        completed = sum(1 for wf in self._workflows.values() if wf.state == SabrTaskState.COMPLETED)
        return {
            "total_workflows": total,
            "completed": completed,
            "active": len(self.get_active_workflows()),
            "completion_rate": completed / max(total, 1),
        }
