"""
Tafakkur Planner (تَفَكُّر) — Planning via Deep Reflection
=============================================================

"Those who remember Allah and reflect on the creation of the heavens and earth" — Quran 3:191

Decomposes complex goals into sub-tasks.
Each sub-task is delegated to the most appropriate agent.
Progress is tracked, and failures trigger re-planning.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.planner")


class SubTaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    """A single sub-task in a plan"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    agent_role: str = "wakil"  # Preferred agent role
    agent_id: Optional[str] = None  # Assigned agent
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # IDs of tasks this depends on
    priority: int = 5  # 1-10
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "description": self.description,
            "agent_role": self.agent_role,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "result": str(self.result)[:500] if self.result else None,
            "error": self.error,
            "dependencies": self.dependencies,
            "priority": self.priority,
        }


@dataclass
class Plan:
    """A complete plan with sub-tasks"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    subtasks: List[SubTask] = field(default_factory=list)
    status: str = "active"  # active | completed | failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def progress(self) -> float:
        if not self.subtasks:
            return 0.0
        completed = sum(1 for t in self.subtasks if t.status == SubTaskStatus.COMPLETED)
        return completed / len(self.subtasks)

    @property
    def next_tasks(self) -> List[SubTask]:
        """Get tasks that are ready to execute (pending with all dependencies met)"""
        completed_ids = {t.id for t in self.subtasks if t.status == SubTaskStatus.COMPLETED}
        return [
            t for t in self.subtasks
            if t.status == SubTaskStatus.PENDING
            and all(dep in completed_ids for dep in t.dependencies)
        ]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "progress": round(self.progress, 2),
            "subtasks": [t.to_dict() for t in self.subtasks],
            "created_at": self.created_at,
        }


class TafakkurPlanner:
    """
    Decomposes complex goals into executable sub-tasks.
    Uses AI to understand the goal and create a plan.
    """

    # Role mapping: task type -> best agent role
    ROLE_MAPPING = {
        "code": "katib",
        "coding": "katib",
        "write": "katib",
        "test": "katib",
        "search": "mubashir",
        "browse": "mubashir",
        "web": "mubashir",
        "research": "mundhir",
        "analyze": "mundhir",
        "report": "mundhir",
        "email": "rasul",
        "message": "rasul",
        "notify": "rasul",
        "send": "rasul",
    }

    def __init__(self):
        self._active_plans: Dict[str, Plan] = {}

    async def decompose(self, goal: str, agent, context: Dict = None) -> Plan:
        """
        Decompose a complex goal into sub-tasks using AI.
        """
        plan = Plan(goal=goal)

        if not agent.ai_client:
            # Simple fallback: single task
            plan.subtasks.append(SubTask(
                description=goal,
                agent_role=self._classify_role(goal),
            ))
            self._active_plans[plan.id] = plan
            return plan

        # Use AI to decompose
        try:
            response = agent.ai_client.create(
                model=agent.ai_model,
                max_tokens=2048,
                system="""You are a task planner. Decompose the given goal into 2-6 concrete sub-tasks.
Return a JSON array of objects with fields:
- "description": clear action to take
- "role": one of "katib" (code), "mubashir" (browse), "mundhir" (research), "rasul" (communicate), "wakil" (general)
- "priority": 1-10 (10 = highest)
- "depends_on": array of indices (0-based) of tasks this depends on

Return ONLY the JSON array, no other text.""",
                messages=[{"role": "user", "content": f"Decompose this goal into sub-tasks:\n\n{goal}"}],
            )

            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            text = text.strip()
            # Extract JSON from response
            if "[" in text:
                json_str = text[text.index("["):text.rindex("]") + 1]
                tasks_data = json.loads(json_str)

                subtask_ids = []
                for i, td in enumerate(tasks_data[:6]):
                    subtask = SubTask(
                        description=td.get("description", f"Step {i + 1}"),
                        agent_role=td.get("role", "wakil"),
                        priority=td.get("priority", 5),
                    )
                    subtask_ids.append(subtask.id)

                    # Map dependencies from indices to IDs
                    deps = td.get("depends_on", [])
                    subtask.dependencies = [
                        subtask_ids[d] for d in deps
                        if isinstance(d, int) and 0 <= d < len(subtask_ids)
                    ]

                    plan.subtasks.append(subtask)

        except Exception as e:
            logger.error(f"[TAFAKKUR] Plan decomposition failed: {e}")
            plan.subtasks.append(SubTask(
                description=goal,
                agent_role=self._classify_role(goal),
            ))

        self._active_plans[plan.id] = plan
        return plan

    def delegate(self, subtask: SubTask, agents: Dict) -> Optional[str]:
        """
        Assign a sub-task to the most appropriate agent.
        Returns the agent_id.
        """
        # Find agent matching the preferred role
        for agent_id, agent in agents.items():
            if agent.role == subtask.agent_role:
                subtask.agent_id = agent_id
                return agent_id

        # Fallback: use first available agent
        if agents:
            agent_id = list(agents.keys())[0]
            subtask.agent_id = agent_id
            return agent_id

        return None

    async def execute_plan(self, plan: Plan, agents: Dict, stream_callback=None) -> Dict:
        """Execute a plan by running sub-tasks in dependency order"""
        from .aql_engine import AqlEngine

        engine = AqlEngine(max_iterations=5)
        results = []

        while plan.next_tasks:
            # Get ready tasks (can be parallel if no dependencies between them)
            ready = plan.next_tasks

            for subtask in ready:
                subtask.status = SubTaskStatus.IN_PROGRESS

                # Delegate to agent
                agent_id = self.delegate(subtask, agents)
                if not agent_id:
                    subtask.status = SubTaskStatus.FAILED
                    subtask.error = "No agent available"
                    continue

                agent = agents[agent_id]

                if stream_callback:
                    await stream_callback(f"\n[Plan Step: {subtask.description}]\n")

                # Execute through AqlEngine
                result = await engine.reason_to_completion(
                    subtask.description, agent,
                    stream_callback=stream_callback,
                )

                if result.get("success"):
                    subtask.status = SubTaskStatus.COMPLETED
                    subtask.result = result.get("response", "")
                else:
                    subtask.status = SubTaskStatus.FAILED
                    subtask.error = result.get("error", "Unknown error")

                results.append({
                    "subtask_id": subtask.id,
                    "description": subtask.description,
                    "agent": agent.name,
                    "success": result.get("success", False),
                    "response": str(result.get("response", ""))[:500],
                })

        # Determine overall plan status
        all_done = all(
            t.status in (SubTaskStatus.COMPLETED, SubTaskStatus.SKIPPED)
            for t in plan.subtasks
        )
        plan.status = "completed" if all_done else "failed"

        return {
            "plan_id": plan.id,
            "status": plan.status,
            "progress": plan.progress,
            "results": results,
        }

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self._active_plans.get(plan_id)

    def _classify_role(self, text: str) -> str:
        text_lower = text.lower()
        for keyword, role in self.ROLE_MAPPING.items():
            if keyword in text_lower:
                return role
        return "wakil"
