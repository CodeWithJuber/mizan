"""
Agent Federation — Risalah (رسالة) Protocol
=============================================

"O you who have believed, obey Allah and obey the Messenger
 and those in authority among you." — Quran 4:59

Agent-to-agent communication protocol for MIZAN's multi-agent system.
No central bottleneck — agents discover, negotiate, and collaborate directly.

Protocol:
  1. Discovery — agents register capabilities in the Majlis
  2. Negotiation — requester proposes task, responder accepts/declines
  3. Delegation — task handed off with context via Risalah message
  4. Reporting — results returned with Yaqin certainty tag
  5. Learning — both agents learn from the interaction (Tafakkur)
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("mizan.federation")


class MessageType(Enum):
    DISCOVER = "discover"         # Who can handle X?
    OFFER = "offer"               # I can handle X
    DELEGATE = "delegate"         # Please handle this task
    ACCEPT = "accept"             # I accept the task
    DECLINE = "decline"           # I cannot handle this
    RESULT = "result"             # Task result
    STATUS = "status"             # Progress update
    LEARN = "learn"               # Share learned pattern


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class RisalahMessage:
    """
    Risalah (رسالة) — Inter-agent message.
    Every message carries its own certainty and context.
    """
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: MessageType = MessageType.DISCOVER
    sender_id: str = ""
    recipient_id: str = ""  # Empty = broadcast
    task: str = ""
    context: Dict = field(default_factory=dict)
    payload: Any = None
    priority: TaskPriority = TaskPriority.NORMAL
    yaqin_level: str = "ilm"  # ilm / ayn / haqq
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)
    reply_to: str = ""  # ID of message being replied to
    ttl: int = 30  # Time to live in seconds

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "type": self.msg_type.value,
            "sender": self.sender_id,
            "recipient": self.recipient_id,
            "task": self.task,
            "priority": self.priority.value,
            "yaqin_level": self.yaqin_level,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentCapability:
    """Registered capability of an agent."""
    agent_id: str = ""
    agent_name: str = ""
    role: str = ""
    capabilities: List[str] = field(default_factory=list)
    nafs_level: int = 1
    success_rate: float = 0.0
    current_load: int = 0
    max_capacity: int = 10
    specializations: List[str] = field(default_factory=list)
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def available(self) -> bool:
        return self.current_load < self.max_capacity

    def match_score(self, required_capabilities: List[str]) -> float:
        """Score how well this agent matches required capabilities."""
        if not required_capabilities:
            return 0.5
        matched = sum(1 for c in required_capabilities if c in self.capabilities)
        base = matched / max(len(required_capabilities), 1)
        # Bonus for nafs level and success rate
        return base * 0.6 + self.success_rate * 0.25 + (self.nafs_level / 7) * 0.15


class AgentFederation:
    """
    Federation — the agent-to-agent coordination layer.

    Enables:
      - Service discovery (who can do what)
      - Task delegation (hand off work)
      - Result aggregation (combine multi-agent outputs)
      - Collaborative learning (share patterns)
    """

    def __init__(self):
        self.registry: Dict[str, AgentCapability] = {}
        self.message_bus: List[RisalahMessage] = []
        self.pending_delegations: Dict[str, RisalahMessage] = {}
        self.completed_delegations: List[Dict] = []
        self._handlers: Dict[str, Callable] = {}
        self._message_handlers: Dict[MessageType, List[Callable]] = {
            mt: [] for mt in MessageType
        }

    # ─── Registration ───

    def register_agent(self, agent_id: str, agent_name: str, role: str,
                       capabilities: List[str], nafs_level: int = 1,
                       success_rate: float = 0.0,
                       specializations: List[str] = None) -> AgentCapability:
        """Register an agent's capabilities in the federation."""
        cap = AgentCapability(
            agent_id=agent_id,
            agent_name=agent_name,
            role=role,
            capabilities=capabilities,
            nafs_level=nafs_level,
            success_rate=success_rate,
            specializations=specializations or [],
        )
        self.registry[agent_id] = cap
        logger.info(f"[FEDERATION] Registered: {agent_name} ({role}) with {len(capabilities)} capabilities")
        return cap

    def unregister_agent(self, agent_id: str):
        """Remove an agent from the federation."""
        self.registry.pop(agent_id, None)

    def update_agent(self, agent_id: str, **kwargs):
        """Update an agent's registration."""
        if agent_id in self.registry:
            for key, value in kwargs.items():
                if hasattr(self.registry[agent_id], key):
                    setattr(self.registry[agent_id], key, value)
            self.registry[agent_id].last_heartbeat = time.time()

    # ─── Discovery ───

    def discover(self, required_capabilities: List[str] = None,
                 min_nafs: int = 1,
                 exclude: Set[str] = None) -> List[AgentCapability]:
        """
        Discover agents matching criteria.
        Returns sorted by match score (best first).
        """
        exclude = exclude or set()
        candidates = []

        for agent_id, cap in self.registry.items():
            if agent_id in exclude:
                continue
            if cap.nafs_level < min_nafs:
                continue
            if not cap.available:
                continue

            score = cap.match_score(required_capabilities or [])
            if score > 0:
                candidates.append((score, cap))

        candidates.sort(key=lambda x: -x[0])
        return [cap for _, cap in candidates]

    def find_best_agent(self, task_type: str,
                        required_capabilities: List[str] = None,
                        min_nafs: int = 1) -> Optional[AgentCapability]:
        """Find the single best agent for a task."""
        # Map task types to capability hints
        type_hints = {
            "coding": ["generate_code", "run_tests", "lint_code", "bash"],
            "research": ["search_web", "analyze_text", "arxiv_search"],
            "browsing": ["browse_url", "search_web", "extract_content"],
            "communication": ["send_webhook", "send_notification"],
            "analysis": ["analyze_text", "fact_check", "synthesize_sources"],
            "file_management": ["read_file", "write_file", "list_files"],
        }

        caps = required_capabilities or type_hints.get(task_type, [])
        candidates = self.discover(caps, min_nafs)
        return candidates[0] if candidates else None

    # ─── Messaging ───

    async def send_message(self, message: RisalahMessage) -> str:
        """Send a message through the federation bus."""
        self.message_bus.append(message)

        # Notify handlers
        handlers = self._message_handlers.get(message.msg_type, [])
        for handler in handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"[FEDERATION] Handler error: {e}")

        return message.message_id

    def on_message(self, msg_type: MessageType, handler: Callable):
        """Register a handler for a message type."""
        self._message_handlers[msg_type].append(handler)

    # ─── Delegation ───

    async def delegate_task(self, from_agent: str, task: str,
                            required_capabilities: List[str] = None,
                            priority: TaskPriority = TaskPriority.NORMAL,
                            context: Dict = None) -> Optional[Dict]:
        """
        Delegate a task to the best available agent.

        Process:
          1. Discover capable agents
          2. Send DELEGATE message to best match
          3. Wait for ACCEPT/DECLINE
          4. Track pending delegation
        """
        best = self.find_best_agent(
            task_type=self._classify_task(task),
            required_capabilities=required_capabilities,
            min_nafs=1,
        )

        if not best:
            logger.warning(f"[FEDERATION] No agent found for task: {task[:50]}")
            return None

        msg = RisalahMessage(
            msg_type=MessageType.DELEGATE,
            sender_id=from_agent,
            recipient_id=best.agent_id,
            task=task,
            context=context or {},
            priority=priority,
        )

        await self.send_message(msg)
        self.pending_delegations[msg.message_id] = msg

        # Update load
        best.current_load += 1

        logger.info(
            f"[FEDERATION] Delegated to {best.agent_name}: {task[:50]}"
        )

        return {
            "delegation_id": msg.message_id,
            "delegated_to": best.agent_id,
            "agent_name": best.agent_name,
            "match_score": best.match_score(required_capabilities or []),
        }

    async def report_result(self, delegation_id: str, agent_id: str,
                            result: Any, success: bool,
                            confidence: float = 0.5,
                            yaqin_level: str = "ilm") -> Dict:
        """Report task result back to the delegating agent."""
        delegation = self.pending_delegations.pop(delegation_id, None)

        if not delegation:
            return {"error": "Delegation not found"}

        # Update agent load
        if agent_id in self.registry:
            self.registry[agent_id].current_load = max(
                0, self.registry[agent_id].current_load - 1
            )

        result_msg = RisalahMessage(
            msg_type=MessageType.RESULT,
            sender_id=agent_id,
            recipient_id=delegation.sender_id,
            task=delegation.task,
            payload=result,
            confidence=confidence,
            yaqin_level=yaqin_level,
            reply_to=delegation_id,
        )

        await self.send_message(result_msg)

        record = {
            "delegation_id": delegation_id,
            "task": delegation.task[:100],
            "from": delegation.sender_id,
            "to": agent_id,
            "success": success,
            "confidence": confidence,
            "yaqin_level": yaqin_level,
            "timestamp": time.time(),
        }
        self.completed_delegations.append(record)

        # Keep history bounded
        if len(self.completed_delegations) > 500:
            self.completed_delegations = self.completed_delegations[-500:]

        return record

    # ─── Direct Delegation (Agent-to-Agent) ───

    async def delegate(self, from_agent_id: str, target_agent_id: str,
                       task: str, context: Dict = None,
                       priority: TaskPriority = TaskPriority.NORMAL,
                       timeout: float = 120.0,
                       execute_fn: Callable = None) -> Dict:
        """
        Delegate a task directly from one agent to a specific target agent.

        Unlike delegate_task() which auto-discovers the best agent, this method
        sends work to a *known* target agent by ID. It:
          1. Validates the target agent is registered and available
          2. Sends a DELEGATE message on the federation bus
          3. Invokes the target agent's execute function (supplied via execute_fn)
          4. Returns the result to the calling agent

        Parameters
        ----------
        from_agent_id : str
            ID of the requesting (calling) agent.
        target_agent_id : str
            ID of the agent that should handle the task.
        task : str
            Natural-language description of the work to do.
        context : dict, optional
            Extra context dict forwarded to the target agent.
        priority : TaskPriority
            Priority level for the delegation.
        timeout : float
            Maximum seconds to wait for the target to finish.
        execute_fn : callable, optional
            An async function ``(agent_id, task, context) -> dict`` that actually
            runs the task on the target agent. When *None*, the method records the
            delegation but cannot run the task (useful in decoupled setups where a
            separate runner picks up pending delegations).

        Returns
        -------
        dict
            Contains delegation_id, target info, success flag, and result payload.
        """
        # --- Validate target ---
        target = self.registry.get(target_agent_id)
        if not target:
            return {
                "success": False,
                "error": f"Target agent '{target_agent_id}' is not registered in the federation.",
            }

        if not target.available:
            return {
                "success": False,
                "error": f"Target agent '{target.agent_name}' is at capacity ({target.current_load}/{target.max_capacity}).",
            }

        # --- Create and send DELEGATE message ---
        msg = RisalahMessage(
            msg_type=MessageType.DELEGATE,
            sender_id=from_agent_id,
            recipient_id=target_agent_id,
            task=task,
            context=context or {},
            priority=priority,
        )

        await self.send_message(msg)
        self.pending_delegations[msg.message_id] = msg
        target.current_load += 1

        logger.info(
            f"[FEDERATION] Direct delegation {msg.message_id}: "
            f"{from_agent_id} -> {target.agent_name} | task={task[:60]}"
        )

        # --- Execute on target if we have an executor ---
        result_payload: Any = None
        success = False
        confidence = 0.5
        yaqin_level = "ilm"

        if execute_fn is not None:
            try:
                result_payload = await asyncio.wait_for(
                    execute_fn(target_agent_id, task, context or {}),
                    timeout=timeout,
                )
                success = result_payload.get("success", False) if isinstance(result_payload, dict) else True
                confidence = result_payload.get("confidence", 0.7) if isinstance(result_payload, dict) else 0.7
                if success:
                    yaqin_level = "ayn"
            except asyncio.TimeoutError:
                result_payload = {"error": f"Delegation timed out after {timeout}s"}
                success = False
            except Exception as exc:
                result_payload = {"error": str(exc)}
                success = False
                logger.error(f"[FEDERATION] Delegation execution error: {exc}")

            # Report result back through the federation
            await self.report_result(
                delegation_id=msg.message_id,
                agent_id=target_agent_id,
                result=result_payload,
                success=success,
                confidence=confidence,
                yaqin_level=yaqin_level,
            )
        else:
            # No executor — delegation is recorded but not executed here
            result_payload = {
                "status": "pending",
                "message": "Delegation recorded. Awaiting external execution.",
            }

        return {
            "delegation_id": msg.message_id,
            "success": success,
            "target_agent_id": target_agent_id,
            "target_agent_name": target.agent_name,
            "task": task,
            "result": result_payload,
            "yaqin_level": yaqin_level,
            "confidence": confidence,
        }

    # ─── Learning ───

    async def share_learning(self, agent_id: str, pattern: str,
                             outcome: str, confidence: float = 0.7):
        """Share a learned pattern with all federation members."""
        msg = RisalahMessage(
            msg_type=MessageType.LEARN,
            sender_id=agent_id,
            task=pattern,
            payload={"pattern": pattern, "outcome": outcome},
            confidence=confidence,
        )
        await self.send_message(msg)

    # ─── Status ───

    def get_status(self) -> Dict:
        """Get federation status."""
        return {
            "registered_agents": len(self.registry),
            "available_agents": sum(1 for c in self.registry.values() if c.available),
            "pending_delegations": len(self.pending_delegations),
            "completed_delegations": len(self.completed_delegations),
            "message_bus_size": len(self.message_bus),
            "agents": [
                {
                    "id": cap.agent_id,
                    "name": cap.agent_name,
                    "role": cap.role,
                    "nafs_level": cap.nafs_level,
                    "success_rate": round(cap.success_rate, 3),
                    "load": f"{cap.current_load}/{cap.max_capacity}",
                    "available": cap.available,
                    "capabilities": cap.capabilities[:5],
                }
                for cap in self.registry.values()
            ],
        }

    def _classify_task(self, task: str) -> str:
        """Classify task type from text."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "script", "python", "function", "bug"]):
            return "coding"
        if any(w in task_lower for w in ["search", "research", "find", "paper"]):
            return "research"
        if any(w in task_lower for w in ["browse", "web", "url", "page"]):
            return "browsing"
        if any(w in task_lower for w in ["email", "message", "send", "notify"]):
            return "communication"
        if any(w in task_lower for w in ["analyze", "review", "check", "audit"]):
            return "analysis"
        return "general"
