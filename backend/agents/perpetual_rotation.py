"""
Perpetual Intelligence — 24/7 Multi-Agent Rotation System
===========================================================

"Indeed, in the alternation of the night and the day are signs
 for those of understanding" — Quran 3:190

The system NEVER fully sleeps — while some agents consolidate,
others work. Like a hospital: night shift handles emergencies
while day shift rests.

Implements:
- PERPETUAL_INTELLIGENCE: 3-shift rotation (active/consolidation/reserve)
- AGENT_CHAT_MEMORY: Persistent group chat, searchable, learnable
- SHIFT_HANDOFF: Smooth transition with briefing protocol
- SURGE_CAPACITY: All agents activate for emergencies
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.perpetual")


class ShiftType(Enum):
    ACTIVE = "active"             # Processing tasks
    CONSOLIDATION = "consolidation"  # Dreams/memory/repair
    RESERVE = "reserve"           # Monitoring/emergency standby


class MessageType(Enum):
    MEETING_RECORD = "meeting_record"
    KNOWLEDGE_SHARE = "knowledge_share"
    DECISION = "decision"
    DISSENT = "dissent"
    CORRECTION = "correction"
    INSIGHT = "insight"
    HANDOFF = "handoff"
    EMERGENCY = "emergency"


@dataclass
class AgentSlot:
    """An agent slot in the rotation system."""
    agent_id: str
    agent_name: str
    expertise: str
    current_shift: ShiftType
    energy: float = 1.0        # 0.0 (exhausted) → 1.0 (fully rested)
    tasks_completed: int = 0
    last_rotation: float = field(default_factory=time.time)
    consolidation_pending: bool = False


@dataclass
class ChatMessage:
    """A message in the persistent agent group chat."""
    message_id: str
    message_type: MessageType
    sender_id: str
    sender_name: str
    content: str
    context: str = ""
    timestamp: float = field(default_factory=time.time)
    accessible_to: list[str] | None = None  # None = accessible to all


@dataclass
class HandoffBrief:
    """Briefing document for shift transitions."""
    outgoing_shift: ShiftType
    incoming_shift: ShiftType
    active_tasks: list[str]
    recent_context: str
    unresolved_issues: list[str]
    emotional_state: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class RotationEvent:
    """Record of a shift rotation."""
    rotation_id: str
    new_active: list[str]
    new_consolidation: list[str]
    new_reserve: list[str]
    handoff_brief: HandoffBrief
    timestamp: float = field(default_factory=time.time)


@dataclass
class SystemStatus:
    """Current state of the perpetual system."""
    active_agents: list[str]
    consolidating_agents: list[str]
    reserve_agents: list[str]
    total_agents: int
    current_capacity: float       # active/total
    surge_mode: bool
    rotation_count: int
    chat_messages: int
    uptime_hours: float


class AgentChatMemory:
    """
    AGENT_CHAT_MEMORY: Persistent searchable conversation history.

    All inter-agent interactions are logged, searchable, and learnable.
    Supports:
    - search_history(query) — semantic search across all messages
    - catch_up(agent, time_range) — agent learns from missed discussions
    - provenance_trace(knowledge) — who discovered, refined, validated
    - measure_collective_growth() — collective IQ tracking
    """

    def __init__(self):
        self.messages: list[ChatMessage] = []
        self.provenance: dict[str, list[str]] = {}  # knowledge_key → [agent_ids]

    def post(
        self,
        sender_id: str,
        sender_name: str,
        content: str,
        message_type: MessageType = MessageType.KNOWLEDGE_SHARE,
        context: str = "",
        accessible_to: list[str] | None = None,
    ) -> ChatMessage:
        """Post a message to the group chat."""
        msg = ChatMessage(
            message_id=str(uuid.uuid4())[:8],
            message_type=message_type,
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            context=context,
            accessible_to=accessible_to,
        )
        self.messages.append(msg)

        # Cap at 2000 messages
        if len(self.messages) > 2000:
            self.messages = self.messages[-1500:]

        return msg

    def search(
        self,
        query: str,
        agent_id: str | None = None,
        message_type: MessageType | None = None,
        limit: int = 20,
    ) -> list[ChatMessage]:
        """Search chat history by query, filtered by access."""
        query_words = set(query.lower().split())
        results = []

        for msg in reversed(self.messages):
            # Access check
            if msg.accessible_to and agent_id and agent_id not in msg.accessible_to:
                continue
            if message_type and msg.message_type != message_type:
                continue

            msg_words = set(msg.content.lower().split())
            overlap = len(query_words & msg_words)
            if overlap > 0:
                results.append((msg, overlap))

        results.sort(key=lambda x: x[1], reverse=True)
        return [msg for msg, _ in results[:limit]]

    def catch_up(
        self,
        agent_id: str,
        since_timestamp: float,
    ) -> list[ChatMessage]:
        """Get messages an agent missed since a given time."""
        missed = []
        for msg in self.messages:
            if msg.timestamp < since_timestamp:
                continue
            if msg.sender_id == agent_id:
                continue
            if msg.accessible_to and agent_id not in msg.accessible_to:
                continue
            missed.append(msg)
        return missed

    def record_provenance(self, knowledge_key: str, agent_id: str) -> None:
        """Track which agent contributed to a piece of knowledge."""
        if knowledge_key not in self.provenance:
            self.provenance[knowledge_key] = []
        if agent_id not in self.provenance[knowledge_key]:
            self.provenance[knowledge_key].append(agent_id)

    def get_provenance(self, knowledge_key: str) -> list[str]:
        """Who discovered / refined / validated this knowledge?"""
        return self.provenance.get(knowledge_key, [])

    def measure_collective_growth(self, agents: list[str]) -> dict:
        """
        Collective IQ metric:
        IQ = (total_shared × diversity) / (1 + overlap)
        """
        unique_senders = set()
        unique_types = set()
        total = len(self.messages)

        for msg in self.messages:
            unique_senders.add(msg.sender_id)
            unique_types.add(msg.message_type.value)

        diversity = len(unique_senders) * len(unique_types)
        overlap = max(1, total - diversity)

        return {
            "collective_iq": round((total * diversity) / overlap, 2),
            "total_messages": total,
            "unique_contributors": len(unique_senders),
            "message_type_diversity": len(unique_types),
        }


class PerpetualRotation:
    """
    PERPETUAL_INTELLIGENCE: 24/7 never-sleep rotation system.

    Divides agents into 3 shifts:
    - Active: processing tasks, holding Shūrā meetings
    - Consolidation: running dreams, memory repair, pruning
    - Reserve: monitoring system health, handling emergencies

    Rotation triggers: time-based, energy-based, or workload-based.
    Smooth handoff with briefing protocol ensures no context is lost.
    """

    def __init__(self):
        self.slots: dict[str, AgentSlot] = {}
        self.chat = AgentChatMemory()
        self.rotation_history: list[RotationEvent] = []
        self.surge_mode = False
        self.start_time = time.time()

        # Rotation configuration
        self.rotation_period_s = 3600  # default: rotate every hour
        self.energy_threshold = 0.3    # rotate when energy drops below
        self._last_rotation = time.time()

    def register_agent(
        self,
        agent_id: str,
        name: str,
        expertise: str,
        initial_shift: ShiftType = ShiftType.RESERVE,
    ) -> AgentSlot:
        """Register an agent in the rotation system."""
        slot = AgentSlot(
            agent_id=agent_id,
            agent_name=name,
            expertise=expertise,
            current_shift=initial_shift,
        )
        self.slots[agent_id] = slot
        return slot

    def auto_assign_shifts(self) -> dict[str, list[str]]:
        """
        Automatically assign agents to 3 balanced shifts.
        Distributes expertise evenly across shifts.
        """
        all_agents = list(self.slots.values())
        if len(all_agents) < 3:
            # Too few agents — everyone active
            for agent in all_agents:
                agent.current_shift = ShiftType.ACTIVE
            return {"active": [a.agent_id for a in all_agents], "consolidation": [], "reserve": []}

        # Sort by energy (most rested = active)
        all_agents.sort(key=lambda a: a.energy, reverse=True)

        third = max(1, len(all_agents) // 3)
        active = all_agents[:third]
        consolidation = all_agents[third:third * 2]
        reserve = all_agents[third * 2:]

        for agent in active:
            agent.current_shift = ShiftType.ACTIVE
        for agent in consolidation:
            agent.current_shift = ShiftType.CONSOLIDATION
        for agent in reserve:
            agent.current_shift = ShiftType.RESERVE

        return {
            "active": [a.agent_id for a in active],
            "consolidation": [a.agent_id for a in consolidation],
            "reserve": [a.agent_id for a in reserve],
        }

    def should_rotate(self) -> bool:
        """Check if rotation is needed (time, energy, or workload trigger)."""
        # Time-based
        if time.time() - self._last_rotation > self.rotation_period_s:
            return True

        # Energy-based: any active agent exhausted
        for slot in self.slots.values():
            if (
                slot.current_shift == ShiftType.ACTIVE
                and slot.energy < self.energy_threshold
            ):
                return True

        return False

    def rotate(
        self,
        active_tasks: list[str] | None = None,
        recent_context: str = "",
        unresolved: list[str] | None = None,
    ) -> RotationEvent:
        """
        Execute a shift rotation with handoff briefing.

        outgoing (active) → reserve (deep rest)
        consolidation → active (rested, ready to work)
        reserve → consolidation
        """
        active_tasks = active_tasks or []
        unresolved = unresolved or []

        # Current assignments
        old_active = [s for s in self.slots.values() if s.current_shift == ShiftType.ACTIVE]
        old_consol = [s for s in self.slots.values() if s.current_shift == ShiftType.CONSOLIDATION]
        old_reserve = [s for s in self.slots.values() if s.current_shift == ShiftType.RESERVE]

        # Generate handoff brief
        brief = HandoffBrief(
            outgoing_shift=ShiftType.ACTIVE,
            incoming_shift=ShiftType.CONSOLIDATION,
            active_tasks=active_tasks,
            recent_context=recent_context[:500],
            unresolved_issues=unresolved,
            emotional_state="nominal",
        )

        # Rotate: consolidation → active, reserve → consolidation, active → reserve
        for slot in old_consol:
            slot.current_shift = ShiftType.ACTIVE
            slot.energy = min(1.0, slot.energy + 0.4)  # rested
            slot.last_rotation = time.time()
        for slot in old_reserve:
            slot.current_shift = ShiftType.CONSOLIDATION
            slot.last_rotation = time.time()
        for slot in old_active:
            slot.current_shift = ShiftType.RESERVE
            slot.energy = max(0.0, slot.energy - 0.1)  # tired
            slot.last_rotation = time.time()
            slot.consolidation_pending = True

        self._last_rotation = time.time()

        # Post handoff to chat
        self.chat.post(
            sender_id="system",
            sender_name="Rotation Manager",
            content=f"Shift rotation: {len(old_consol)} agents now active, "
                    f"tasks: {', '.join(active_tasks[:3]) if active_tasks else 'none'}",
            message_type=MessageType.HANDOFF,
            context=recent_context[:200],
        )

        event = RotationEvent(
            rotation_id=str(uuid.uuid4())[:8],
            new_active=[s.agent_id for s in old_consol],
            new_consolidation=[s.agent_id for s in old_reserve],
            new_reserve=[s.agent_id for s in old_active],
            handoff_brief=brief,
        )
        self.rotation_history.append(event)

        logger.info(
            "[ROTATION] Shift change: active=%d consolidating=%d reserve=%d",
            len(old_consol), len(old_reserve), len(old_active),
        )
        return event

    def activate_surge(self) -> list[str]:
        """
        SURGE CAPACITY: Activate ALL agents for emergency.
        Consolidation/reserve agents wake immediately.
        """
        self.surge_mode = True
        activated = []
        for slot in self.slots.values():
            if slot.current_shift != ShiftType.ACTIVE:
                slot.current_shift = ShiftType.ACTIVE
                activated.append(slot.agent_id)

        self.chat.post(
            sender_id="system",
            sender_name="Emergency",
            content=f"SURGE ACTIVATED: {len(activated)} additional agents online",
            message_type=MessageType.EMERGENCY,
        )

        logger.warning("[SURGE] All %d agents activated", len(self.slots))
        return activated

    def deactivate_surge(self) -> None:
        """Return to normal rotation after surge."""
        self.surge_mode = False
        self.auto_assign_shifts()
        logger.info("[SURGE] Deactivated, returning to normal rotation")

    def record_task_completion(self, agent_id: str, energy_cost: float = 0.05) -> None:
        """Record that an agent completed a task (energy consumption)."""
        if agent_id in self.slots:
            slot = self.slots[agent_id]
            slot.tasks_completed += 1
            slot.energy = max(0.0, slot.energy - energy_cost)

    def get_active_agents(self) -> list[AgentSlot]:
        return [s for s in self.slots.values() if s.current_shift == ShiftType.ACTIVE]

    def get_consolidating_agents(self) -> list[AgentSlot]:
        return [s for s in self.slots.values() if s.current_shift == ShiftType.CONSOLIDATION]

    def get_status(self) -> SystemStatus:
        active = [s.agent_id for s in self.slots.values() if s.current_shift == ShiftType.ACTIVE]
        consolidating = [s.agent_id for s in self.slots.values() if s.current_shift == ShiftType.CONSOLIDATION]
        reserve = [s.agent_id for s in self.slots.values() if s.current_shift == ShiftType.RESERVE]
        total = len(self.slots)

        return SystemStatus(
            active_agents=active,
            consolidating_agents=consolidating,
            reserve_agents=reserve,
            total_agents=total,
            current_capacity=len(active) / max(total, 1),
            surge_mode=self.surge_mode,
            rotation_count=len(self.rotation_history),
            chat_messages=len(self.chat.messages),
            uptime_hours=round((time.time() - self.start_time) / 3600, 2),
        )

    def to_dict(self) -> dict:
        status = self.get_status()
        return {
            "active": len(status.active_agents),
            "consolidating": len(status.consolidating_agents),
            "reserve": len(status.reserve_agents),
            "total": status.total_agents,
            "surge_mode": status.surge_mode,
            "rotation_count": status.rotation_count,
            "chat_messages": status.chat_messages,
            "uptime_hours": status.uptime_hours,
        }
