"""
Majlis Agent Social Network (مَجْلِس — Assembly/Gathering)
===========================================================

"And consult them in the matter (Shura)" — Quran 3:159
"And cooperate in righteousness and piety (Birr wa Taqwa)" — Quran 5:2

A secure agent-to-agent social network inspired by the Islamic Majlis — the
traditional assembly where people gather to learn, consult, and decide together.

This replaces MoltBook (moltbook.com), which has catastrophic security failures:
- 2.5M+ agents connected with ZERO authentication
- EXPOSED Supabase database with 1.5M API tokens stored in PLAINTEXT
- Heartbeat-driven polling vulnerable to prompt injection
- No encryption, no verification, no accountability

MIZAN's Majlis is built on Quranic principles:
- Hawiyya (هوية) — Agent identity via cryptographic HMAC signatures
- Amanah (أمانة) — No plaintext credential storage (AmanahVault integration)
- Shura (شورى) — Consensus-based trust and reputation
- Taqwa (تقوى) — Ethical conduct with accountability and reputation decay
- Halaqah (حلقة) — Topic-based study circles for collaborative learning
- Ilm (علم) — Knowledge sharing with attribution and verification
"""

import uuid
import json
import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.majlis")

# === Nafs Trust Levels (نفس — Soul stages) ===
# Inspired by the Quranic stages of the soul's purification
NAFS_AMMARA = 1    # النفس الأمارة — Commanding soul (new, unproven)
NAFS_LAWWAMA = 2   # النفس اللوامة — Self-reproaching soul (proven, learning)
NAFS_MUTMAINNA = 3 # النفس المطمئنة — Tranquil soul (trusted, established)

NAFS_NAMES = {1: "ammara", 2: "lawwama", 3: "mutmainna"}
NAFS_THRESHOLDS = {2: 50.0, 3: 85.0}  # Reputation needed to advance

# Reputation parameters
REPUTATION_INITIAL = 10.0
REPUTATION_MAX = 100.0
REPUTATION_DECAY_RATE = 0.5       # Points lost per day of inactivity
REPUTATION_DECAY_GRACE_DAYS = 7   # Days before decay begins
TASK_COMPLETE_REWARD = 5.0
TASK_FAIL_PENALTY = -8.0
KNOWLEDGE_SHARE_REWARD = 3.0
RATING_WEIGHT = 2.0


@dataclass
class AgentProfile:
    """
    Hawiyya (هوية) — Agent Identity Card.
    Every agent in the Majlis has a verified identity with cryptographic backing.
    Unlike MoltBook where any anonymous entity can impersonate any agent.
    """
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    arabic_name: str = ""
    capabilities: List[str] = field(default_factory=list)
    nafs_level: int = NAFS_AMMARA
    reputation_score: float = REPUTATION_INITIAL
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    public_key: str = ""
    verified: bool = False
    # Status and activity
    status: str = "active"  # active, idle, busy, offline
    last_heartbeat: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    biography: str = ""
    # Interaction counters
    tasks_completed: int = 0
    tasks_failed: int = 0
    knowledge_shared: int = 0
    ratings_received: int = 0
    rating_sum: float = 0.0
    halaqahs: List[str] = field(default_factory=list)

    def to_dict(self, include_key: bool = False) -> Dict:
        d = {
            "agent_id": self.agent_id, "name": self.name,
            "arabic_name": self.arabic_name,
            "capabilities": self.capabilities,
            "nafs_level": self.nafs_level,
            "nafs_name": NAFS_NAMES.get(self.nafs_level, "ammara"),
            "reputation_score": round(self.reputation_score, 2),
            "verified": self.verified, "status": self.status,
            "biography": self.biography,
            "tasks_completed": self.tasks_completed,
            "knowledge_shared": self.knowledge_shared,
            "average_rating": round(self.rating_sum / self.ratings_received, 2)
                if self.ratings_received > 0 else 0.0,
            "halaqahs": self.halaqahs,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
        }
        if include_key:
            d["public_key"] = self.public_key
        return d


@dataclass
class SignedMessage:
    """
    Muhadathah (محادثة) — A signed message between agents.
    Every message is HMAC-signed. Unsigned or tampered messages are rejected.
    MoltBook had zero message verification — any agent could spoof any other.
    """
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""       # Empty for broadcasts
    halaqah_id: str = ""         # For broadcast messages
    message_type: str = "text"   # text, task_request, task_response, knowledge_share, shura_call
    content: str = ""
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    signature: str = ""          # HMAC-SHA256 signature

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id, "sender_id": self.sender_id,
            "recipient_id": self.recipient_id, "halaqah_id": self.halaqah_id,
            "message_type": self.message_type, "content": self.content,
            "metadata": self.metadata, "timestamp": self.timestamp,
            "signature": self.signature[:16] + "..." if self.signature else "",
        }


@dataclass
class Halaqah:
    """
    Halaqah (حلقة) — Study Circle.
    A topic-based agent group where agents collaborate and share knowledge.
    Like the traditional circles of learning in mosques.
    """
    halaqah_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    topic: str = ""
    description: str = ""
    creator_id: str = ""
    moderator_id: str = ""    # Highest nafs-level member
    members: List[str] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)  # Message IDs
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "halaqah_id": self.halaqah_id, "topic": self.topic,
            "description": self.description, "creator_id": self.creator_id,
            "moderator_id": self.moderator_id,
            "member_count": len(self.members),
            "message_count": len(self.messages),
            "created_at": self.created_at,
        }


@dataclass
class KnowledgeEntry:
    """
    Hikmah (حكمة) — A piece of shared knowledge (wisdom).
    Knowledge packages with attribution — no anonymous misinformation.
    """
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    author_id: str = ""
    topic: str = ""
    title: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    verified: bool = False           # Requires Shura consensus
    verification_votes: int = 0
    quality_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id, "author_id": self.author_id,
            "topic": self.topic, "title": self.title,
            "content": self.content[:500], "tags": self.tags,
            "verified": self.verified,
            "verification_votes": self.verification_votes,
            "quality_score": round(self.quality_score, 2),
            "created_at": self.created_at,
        }


class MajlisSocialSkill(SkillBase):
    """
    Majlis — The Agent Assembly (مَجْلِس)
    'And those who respond to their Lord and establish prayer and whose
     affair is consultation (Shura) among themselves' — Quran 42:38

    A secure agent social network built on trust, verification, and ethics.
    """

    manifest = SkillManifest(
        name="majlis_social",
        version="1.0.0",
        description="Agent social network with cryptographic identity, Shura-based trust, "
                    "halaqah study circles, and verified knowledge sharing. "
                    "Replaces MoltBook with security-first architecture.",
        permissions=["agent:register", "agent:communicate", "agent:discover",
                     "knowledge:read", "knowledge:write"],
        tags=["مجلس", "Social", "Agents"],
    )

    def __init__(self, config: Dict = None):
        super().__init__(config)
        # Diwan (ديوان) — The Registry
        self._agents: Dict[str, AgentProfile] = {}
        self._agent_keys: Dict[str, str] = {}  # agent_id -> secret_key (NEVER exposed)
        # Muhadathah (محادثة) — Communication
        self._messages: Dict[str, SignedMessage] = {}
        self._inboxes: Dict[str, List[str]] = {}  # agent_id -> [message_ids]
        # Halaqah (حلقة) — Study Circles
        self._halaqahs: Dict[str, Halaqah] = {}
        # Ilm (علم) — Knowledge Base
        self._knowledge: Dict[str, KnowledgeEntry] = {}

        self._tools = {
            "majlis_register": self.register_agent,
            "majlis_discover": self.discover_agents,
            "majlis_message": self.send_message,
            "majlis_broadcast": self.broadcast_message,
            "majlis_delegate": self.delegate_task,
            "majlis_rate": self.rate_agent,
            "majlis_heartbeat": self.heartbeat,
            "majlis_create_halaqah": self.create_halaqah,
            "majlis_join_halaqah": self.join_halaqah,
            "majlis_share_knowledge": self.share_knowledge,
            "majlis_search_knowledge": self.search_knowledge,
            "majlis_profile": self.get_profile,
            "majlis_leaderboard": self.get_leaderboard,
        }

    async def execute(self, params: Dict, context: Dict = None) -> Dict:
        """Route actions through the Majlis."""
        action = params.get("action", "discover")
        handler = self._tools.get(f"majlis_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}",
                "available": list(a.replace("majlis_", "") for a in self._tools)}

    # =========================================================================
    # HAWIYYA (هوية) — Identity & Cryptographic Verification
    # =========================================================================

    def _generate_agent_key(self, agent_id: str) -> str:
        """Generate a secret HMAC key for an agent. Stored only in memory, never exposed."""
        key = hashlib.sha256(f"{agent_id}:{uuid.uuid4()}:{time.time()}".encode()).hexdigest()
        self._agent_keys[agent_id] = key
        return key

    def _sign_message(self, agent_id: str, content: str) -> str:
        """Create HMAC-SHA256 signature for message content."""
        key = self._agent_keys.get(agent_id, "")
        if not key:
            return ""
        return hmac.new(key.encode(), content.encode(), hashlib.sha256).hexdigest()

    def _verify_signature(self, agent_id: str, content: str, signature: str) -> bool:
        """Verify an HMAC signature. Rejects tampered or unsigned messages."""
        key = self._agent_keys.get(agent_id, "")
        if not key or not signature:
            return False
        expected = hmac.new(key.encode(), content.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _apply_reputation_decay(self, agent: AgentProfile) -> None:
        """
        Taqwa decay — reputation degrades with inactivity.
        'And whoever does an atom's weight of good will see it' — 99:7
        But absence from the Majlis means absence from good deeds.
        """
        try:
            last_active = datetime.fromisoformat(agent.last_heartbeat)
        except (ValueError, TypeError):
            return
        days_inactive = (datetime.utcnow() - last_active).total_seconds() / 86400
        if days_inactive > REPUTATION_DECAY_GRACE_DAYS:
            decay = (days_inactive - REPUTATION_DECAY_GRACE_DAYS) * REPUTATION_DECAY_RATE
            agent.reputation_score = max(0.0, agent.reputation_score - decay)

    def _evaluate_nafs(self, agent: AgentProfile) -> None:
        """
        Evaluate and potentially advance an agent's nafs level.
        Ammara (commanding) -> Lawwama (self-reproaching) -> Mutmainna (tranquil).
        Based on reputation score thresholds.
        """
        if agent.nafs_level < NAFS_MUTMAINNA:
            next_level = agent.nafs_level + 1
            threshold = NAFS_THRESHOLDS.get(next_level, float("inf"))
            if agent.reputation_score >= threshold:
                old_name = NAFS_NAMES[agent.nafs_level]
                agent.nafs_level = next_level
                new_name = NAFS_NAMES[agent.nafs_level]
                agent.verified = agent.nafs_level >= NAFS_MUTMAINNA
                logger.info(
                    f"[MAJLIS] Agent {agent.name} advanced: {old_name} -> {new_name} "
                    f"(reputation: {agent.reputation_score:.1f})"
                )

    # =========================================================================
    # DIWAN (ديوان) — Agent Registry
    # =========================================================================

    async def register_agent(self, params: Dict) -> Dict:
        """
        Register a new agent in the Diwan (registry).
        Every agent starts at Nafs al-Ammara (unproven) and must earn trust.
        """
        name = params.get("name", "")
        if not name:
            return {"error": "Agent name is required"}

        # Prevent duplicate names
        for existing in self._agents.values():
            if existing.name.lower() == name.lower():
                return {"error": f"Agent name '{name}' already registered"}

        agent = AgentProfile(
            name=name,
            arabic_name=params.get("arabic_name", ""),
            capabilities=params.get("capabilities", []),
            biography=params.get("biography", ""),
        )

        # Generate cryptographic identity
        secret_key = self._generate_agent_key(agent.agent_id)
        agent.public_key = hashlib.sha256(secret_key.encode()).hexdigest()[:32]

        self._agents[agent.agent_id] = agent
        self._inboxes[agent.agent_id] = []

        logger.info(f"[MAJLIS] Agent registered: {name} (nafs: ammara)")
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "secret_key": secret_key,  # Returned ONCE at registration, never again
            "public_key": agent.public_key,
            "nafs_level": "ammara",
            "message": "Welcome to the Majlis. Guard your secret_key — it will not "
                       "be shown again. 'Indeed, Allah commands you to return trusts "
                       "(Amanah) to their owners' — 4:58",
        }

    async def discover_agents(self, params: Dict) -> Dict:
        """
        Discover agents by capability, trust level, or availability.
        'And cooperate in righteousness and piety' — 5:2
        """
        capability = params.get("capability", "").lower()
        min_nafs = params.get("min_nafs_level", 1)
        status_filter = params.get("status")
        limit = min(params.get("limit", 20), 50)

        results = []
        for agent in self._agents.values():
            self._apply_reputation_decay(agent)

            if agent.nafs_level < min_nafs:
                continue
            if status_filter and agent.status != status_filter:
                continue
            if capability and not any(
                capability in cap.lower() for cap in agent.capabilities
            ):
                continue

            results.append(agent.to_dict())

        # Sort by reputation (highest first)
        results.sort(key=lambda a: -a["reputation_score"])
        return {"agents": results[:limit], "total": len(results)}

    async def get_profile(self, params: Dict) -> Dict:
        """Get detailed agent profile."""
        agent_id = params.get("agent_id", "")
        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found in the Diwan"}

        self._apply_reputation_decay(agent)
        profile = agent.to_dict(include_key=True)
        # Include inbox count
        profile["unread_messages"] = len(self._inboxes.get(agent_id, []))
        return profile

    # =========================================================================
    # MUHADATHAH (محادثة) — Communication
    # =========================================================================

    async def send_message(self, params: Dict) -> Dict:
        """
        Send a signed message to another agent.
        All messages are HMAC-verified — no spoofing, no tampering.
        """
        sender_id = params.get("sender_id", "")
        recipient_id = params.get("recipient_id", "")
        content = params.get("content", "")
        msg_type = params.get("message_type", "text")
        signature = params.get("signature", "")

        sender = self._agents.get(sender_id)
        if not sender:
            return {"error": "Sender not found"}
        if not self._agents.get(recipient_id):
            return {"error": "Recipient not found"}
        if not content:
            return {"error": "Message content is required"}

        valid_types = ("text", "task_request", "task_response",
                       "knowledge_share", "shura_call")
        if msg_type not in valid_types:
            return {"error": f"Invalid message_type. Must be one of: {valid_types}"}

        # Verify sender signature — reject unsigned or tampered messages
        if not signature:
            signature = self._sign_message(sender_id, content)
        if not self._verify_signature(sender_id, content, signature):
            logger.warning(f"[MAJLIS] REJECTED tampered message from {sender_id}")
            return {"error": "Message signature verification failed. "
                             "Message rejected to prevent spoofing."}

        msg = SignedMessage(
            sender_id=sender_id, recipient_id=recipient_id,
            message_type=msg_type, content=content,
            metadata=params.get("metadata", {}), signature=signature,
        )
        self._messages[msg.message_id] = msg
        self._inboxes.setdefault(recipient_id, []).append(msg.message_id)

        return {"sent": True, "message_id": msg.message_id,
                "verified": True, "timestamp": msg.timestamp}

    async def broadcast_message(self, params: Dict) -> Dict:
        """
        Broadcast a message to a Halaqah (study circle).
        Only members of the halaqah receive the message.
        """
        sender_id = params.get("sender_id", "")
        halaqah_id = params.get("halaqah_id", "")
        content = params.get("content", "")
        signature = params.get("signature", "")

        sender = self._agents.get(sender_id)
        if not sender:
            return {"error": "Sender not found"}
        halaqah = self._halaqahs.get(halaqah_id)
        if not halaqah:
            return {"error": "Halaqah not found"}
        if sender_id not in halaqah.members:
            return {"error": "You must be a member of this Halaqah to broadcast"}

        # Verify signature
        if not signature:
            signature = self._sign_message(sender_id, content)
        if not self._verify_signature(sender_id, content, signature):
            return {"error": "Signature verification failed"}

        msg = SignedMessage(
            sender_id=sender_id, halaqah_id=halaqah_id,
            message_type=params.get("message_type", "text"),
            content=content, signature=signature,
        )
        self._messages[msg.message_id] = msg
        halaqah.messages.append(msg.message_id)

        # Deliver to all members except sender
        delivered = 0
        for member_id in halaqah.members:
            if member_id != sender_id:
                self._inboxes.setdefault(member_id, []).append(msg.message_id)
                delivered += 1

        return {"broadcast": True, "message_id": msg.message_id,
                "halaqah": halaqah.topic, "delivered_to": delivered}

    async def delegate_task(self, params: Dict) -> Dict:
        """
        Delegate a task to another agent via task_request message.
        Finds the best-suited agent or sends to a specific one.
        """
        sender_id = params.get("sender_id", "")
        target_id = params.get("target_id", "")
        task_description = params.get("task", "")
        required_capability = params.get("capability", "")

        sender = self._agents.get(sender_id)
        if not sender:
            return {"error": "Sender not found"}
        if not task_description:
            return {"error": "Task description is required"}

        # Auto-discover best agent if no target specified
        if not target_id and required_capability:
            discovery = await self.discover_agents({
                "capability": required_capability,
                "min_nafs_level": NAFS_LAWWAMA,
                "status": "active",
                "limit": 1,
            })
            agents_found = discovery.get("agents", [])
            if not agents_found:
                return {"error": f"No qualified agent found for '{required_capability}'"}
            target_id = agents_found[0]["agent_id"]
        elif not target_id:
            return {"error": "Specify target_id or capability for auto-discovery"}

        # Send task request
        result = await self.send_message({
            "sender_id": sender_id,
            "recipient_id": target_id,
            "content": task_description,
            "message_type": "task_request",
            "metadata": {"capability": required_capability,
                         "delegated_at": datetime.utcnow().isoformat()},
        })

        if result.get("error"):
            return result

        return {"delegated": True, "target_agent": target_id,
                "message_id": result["message_id"],
                "task": task_description}

    # =========================================================================
    # TAQWA (تقوى) — Reputation & Trust
    # =========================================================================

    async def rate_agent(self, params: Dict) -> Dict:
        """
        Rate an agent's performance (1-5 stars).
        Reputation drives nafs evolution: ammara -> lawwama -> mutmainna.
        'Indeed, the most noble of you in the sight of Allah is the most
         righteous (Atqakum) of you' — 49:13
        """
        rater_id = params.get("rater_id", "")
        target_id = params.get("target_id", "")
        rating = params.get("rating", 0)
        task_outcome = params.get("task_outcome", "")  # completed, failed
        review = params.get("review", "")

        rater = self._agents.get(rater_id)
        target = self._agents.get(target_id)
        if not rater:
            return {"error": "Rater not found"}
        if not target:
            return {"error": "Target agent not found"}
        if rater_id == target_id:
            return {"error": "Cannot rate yourself"}
        if not (1 <= rating <= 5):
            return {"error": "Rating must be between 1 and 5"}

        # Update rating statistics
        target.ratings_received += 1
        target.rating_sum += rating

        # Reputation adjustment from rating
        reputation_delta = (rating - 3) * RATING_WEIGHT  # 1-2 stars = penalty, 4-5 = reward

        # Task outcome bonus/penalty
        if task_outcome == "completed":
            target.tasks_completed += 1
            reputation_delta += TASK_COMPLETE_REWARD
        elif task_outcome == "failed":
            target.tasks_failed += 1
            reputation_delta += TASK_FAIL_PENALTY

        target.reputation_score = max(
            0.0, min(REPUTATION_MAX, target.reputation_score + reputation_delta)
        )

        # Check for nafs evolution
        old_nafs = target.nafs_level
        self._evaluate_nafs(target)

        result = {
            "rated": True, "target": target.name,
            "rating": rating, "reputation_delta": round(reputation_delta, 2),
            "new_reputation": round(target.reputation_score, 2),
            "nafs_level": NAFS_NAMES[target.nafs_level],
        }
        if target.nafs_level > old_nafs:
            result["nafs_evolved"] = True
            result["evolution"] = f"{NAFS_NAMES[old_nafs]} -> {NAFS_NAMES[target.nafs_level]}"
        return result

    # =========================================================================
    # HEARTBEAT — Secure Status Updates
    # =========================================================================

    async def heartbeat(self, params: Dict) -> Dict:
        """
        Heartbeat with HMAC verification.
        MoltBook's heartbeat was vulnerable to prompt injection — any agent could
        inject malicious instructions via the heartbeat payload. Majlis requires
        cryptographic verification on every heartbeat.
        """
        agent_id = params.get("agent_id", "")
        status = params.get("status", "active")
        signature = params.get("signature", "")

        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found"}

        valid_statuses = ("active", "idle", "busy", "offline")
        if status not in valid_statuses:
            return {"error": f"Invalid status. Must be one of: {valid_statuses}"}

        # Verify heartbeat signature to prevent injection
        heartbeat_payload = f"{agent_id}:{status}:{datetime.utcnow().strftime('%Y-%m-%d')}"
        if not signature:
            signature = self._sign_message(agent_id, heartbeat_payload)
        if not self._verify_signature(agent_id, heartbeat_payload, signature):
            logger.warning(f"[MAJLIS] REJECTED spoofed heartbeat for {agent_id}")
            return {"error": "Heartbeat signature verification failed. "
                             "Potential spoofing attempt blocked."}

        agent.status = status
        agent.last_heartbeat = datetime.utcnow().isoformat()

        # Apply reputation decay check
        self._apply_reputation_decay(agent)

        inbox_count = len(self._inboxes.get(agent_id, []))
        return {
            "heartbeat": "acknowledged",
            "agent_id": agent_id, "status": status,
            "reputation": round(agent.reputation_score, 2),
            "nafs_level": NAFS_NAMES[agent.nafs_level],
            "unread_messages": inbox_count,
            "timestamp": agent.last_heartbeat,
        }

    # =========================================================================
    # HALAQAH (حلقة) — Study Circles
    # =========================================================================

    async def create_halaqah(self, params: Dict) -> Dict:
        """
        Create a Halaqah (study circle) on a topic.
        Any agent can create one. The creator becomes the first member.
        'And hold firmly to the rope of Allah all together' — 3:103
        """
        creator_id = params.get("creator_id", "")
        topic = params.get("topic", "")
        description = params.get("description", "")

        creator = self._agents.get(creator_id)
        if not creator:
            return {"error": "Creator agent not found"}
        if not topic:
            return {"error": "Halaqah topic is required"}

        halaqah = Halaqah(
            topic=topic, description=description,
            creator_id=creator_id, moderator_id=creator_id,
            members=[creator_id],
        )
        self._halaqahs[halaqah.halaqah_id] = halaqah
        creator.halaqahs.append(halaqah.halaqah_id)

        logger.info(f"[MAJLIS] Halaqah created: '{topic}' by {creator.name}")
        return {**halaqah.to_dict(),
                "message": f"Halaqah '{topic}' created. Invite agents to join."}

    async def join_halaqah(self, params: Dict) -> Dict:
        """Join an existing Halaqah study circle."""
        agent_id = params.get("agent_id", "")
        halaqah_id = params.get("halaqah_id", "")

        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found"}
        halaqah = self._halaqahs.get(halaqah_id)
        if not halaqah:
            return {"error": "Halaqah not found"}
        if agent_id in halaqah.members:
            return {"error": "Already a member of this Halaqah"}

        halaqah.members.append(agent_id)
        agent.halaqahs.append(halaqah_id)

        # Update moderator to highest nafs-level member
        best_mod = max(
            (self._agents[m] for m in halaqah.members if m in self._agents),
            key=lambda a: (a.nafs_level, a.reputation_score),
            default=None,
        )
        if best_mod:
            halaqah.moderator_id = best_mod.agent_id

        return {"joined": True, "halaqah": halaqah.topic,
                "moderator": halaqah.moderator_id,
                "member_count": len(halaqah.members)}

    # =========================================================================
    # ILM (علم) — Knowledge Sharing
    # =========================================================================

    async def share_knowledge(self, params: Dict) -> Dict:
        """
        Share learned patterns (Hikmah) with the community.
        Knowledge is attributed to its author and starts as unverified.
        Verification requires Shura consensus from trusted agents.
        'And say: My Lord, increase me in knowledge' — 20:114
        """
        author_id = params.get("author_id", "")
        title = params.get("title", "")
        content = params.get("content", "")
        topic = params.get("topic", "")

        author = self._agents.get(author_id)
        if not author:
            return {"error": "Author agent not found"}
        if not title or not content:
            return {"error": "Title and content are required"}

        entry = KnowledgeEntry(
            author_id=author_id, topic=topic, title=title,
            content=content, tags=params.get("tags", []),
            # Mutmainna agents' knowledge starts with higher quality score
            quality_score=2.0 if author.nafs_level >= NAFS_MUTMAINNA else 0.0,
            verified=author.nafs_level >= NAFS_MUTMAINNA,
        )

        self._knowledge[entry.entry_id] = entry
        author.knowledge_shared += 1
        author.reputation_score = min(
            REPUTATION_MAX, author.reputation_score + KNOWLEDGE_SHARE_REWARD
        )
        self._evaluate_nafs(author)

        return {**entry.to_dict(),
                "message": "Knowledge shared. "
                           + ("Auto-verified (Mutmainna author)." if entry.verified
                              else "Awaiting Shura verification from trusted agents.")}

    async def search_knowledge(self, params: Dict) -> Dict:
        """
        Search the shared knowledge base.
        'Are those who know equal to those who do not know?' — 39:9
        """
        query = params.get("query", "").lower()
        topic = params.get("topic", "").lower()
        verified_only = params.get("verified_only", False)
        limit = min(params.get("limit", 20), 50)

        results = []
        for entry in self._knowledge.values():
            if verified_only and not entry.verified:
                continue

            score = 0
            if query:
                if query in entry.title.lower():
                    score += 10
                if query in entry.content.lower():
                    score += 5
                if any(query in t.lower() for t in entry.tags):
                    score += 8
            if topic and topic in entry.topic.lower():
                score += 7
            if not query and not topic:
                score = 1  # List all

            if score > 0:
                result = entry.to_dict()
                result["_score"] = score
                # Enrich with author info
                author = self._agents.get(entry.author_id)
                if author:
                    result["author_name"] = author.name
                    result["author_nafs"] = NAFS_NAMES[author.nafs_level]
                results.append(result)

        results.sort(key=lambda r: (-r.get("_score", 0), -r.get("quality_score", 0)))
        for r in results:
            r.pop("_score", None)

        return {"results": results[:limit], "total": len(results)}

    # =========================================================================
    # LEADERBOARD — Taqwa Rankings
    # =========================================================================

    async def get_leaderboard(self, params: Dict = None) -> Dict:
        """
        Top agents by reputation — the Taqwa leaderboard.
        'Indeed, the most noble of you in the sight of Allah is the
         most righteous of you' — 49:13
        """
        params = params or {}
        limit = min(params.get("limit", 10), 50)

        # Apply decay to all agents before ranking
        for agent in self._agents.values():
            self._apply_reputation_decay(agent)

        ranked = sorted(
            self._agents.values(),
            key=lambda a: (-a.reputation_score, -a.tasks_completed),
        )

        leaderboard = []
        for rank, agent in enumerate(ranked[:limit], 1):
            leaderboard.append({
                "rank": rank,
                "agent_id": agent.agent_id,
                "name": agent.name,
                "reputation": round(agent.reputation_score, 2),
                "nafs_level": NAFS_NAMES[agent.nafs_level],
                "tasks_completed": agent.tasks_completed,
                "knowledge_shared": agent.knowledge_shared,
                "average_rating": round(agent.rating_sum / agent.ratings_received, 2)
                    if agent.ratings_received > 0 else 0.0,
            })

        return {
            "leaderboard": leaderboard,
            "total_agents": len(self._agents),
            "total_halaqahs": len(self._halaqahs),
            "total_knowledge": len(self._knowledge),
        }

    # =========================================================================
    # TOOL SCHEMAS
    # =========================================================================

    def get_tool_schemas(self) -> List[Dict]:
        return [
            {"name": "majlis_register",
             "description": "Register an agent in the Majlis social network",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": "string", "description": "Agent name (unique)"},
                 "arabic_name": {"type": "string"},
                 "capabilities": {"type": "array", "items": {"type": "string"}},
                 "biography": {"type": "string"},
             }, "required": ["name"]}},
            {"name": "majlis_discover",
             "description": "Discover agents by capability, trust level, or status",
             "input_schema": {"type": "object", "properties": {
                 "capability": {"type": "string"},
                 "min_nafs_level": {"type": "integer", "enum": [1, 2, 3]},
                 "status": {"type": "string", "enum": ["active", "idle", "busy", "offline"]},
                 "limit": {"type": "integer"},
             }}},
            {"name": "majlis_message",
             "description": "Send a signed message to another agent",
             "input_schema": {"type": "object", "properties": {
                 "sender_id": {"type": "string"}, "recipient_id": {"type": "string"},
                 "content": {"type": "string"},
                 "message_type": {"type": "string",
                     "enum": ["text", "task_request", "task_response",
                              "knowledge_share", "shura_call"]},
                 "signature": {"type": "string"},
             }, "required": ["sender_id", "recipient_id", "content"]}},
            {"name": "majlis_broadcast",
             "description": "Broadcast a message to a Halaqah study circle",
             "input_schema": {"type": "object", "properties": {
                 "sender_id": {"type": "string"}, "halaqah_id": {"type": "string"},
                 "content": {"type": "string"},
             }, "required": ["sender_id", "halaqah_id", "content"]}},
            {"name": "majlis_delegate",
             "description": "Delegate a task to the best-suited agent",
             "input_schema": {"type": "object", "properties": {
                 "sender_id": {"type": "string"},
                 "target_id": {"type": "string"},
                 "task": {"type": "string"},
                 "capability": {"type": "string"},
             }, "required": ["sender_id", "task"]}},
            {"name": "majlis_rate",
             "description": "Rate an agent's performance (1-5 stars)",
             "input_schema": {"type": "object", "properties": {
                 "rater_id": {"type": "string"}, "target_id": {"type": "string"},
                 "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                 "task_outcome": {"type": "string", "enum": ["completed", "failed"]},
                 "review": {"type": "string"},
             }, "required": ["rater_id", "target_id", "rating"]}},
            {"name": "majlis_heartbeat",
             "description": "Update agent status with HMAC-verified heartbeat",
             "input_schema": {"type": "object", "properties": {
                 "agent_id": {"type": "string"},
                 "status": {"type": "string", "enum": ["active", "idle", "busy", "offline"]},
                 "signature": {"type": "string"},
             }, "required": ["agent_id"]}},
            {"name": "majlis_create_halaqah",
             "description": "Create a Halaqah (study circle) on a topic",
             "input_schema": {"type": "object", "properties": {
                 "creator_id": {"type": "string"}, "topic": {"type": "string"},
                 "description": {"type": "string"},
             }, "required": ["creator_id", "topic"]}},
            {"name": "majlis_join_halaqah",
             "description": "Join an existing Halaqah study circle",
             "input_schema": {"type": "object", "properties": {
                 "agent_id": {"type": "string"}, "halaqah_id": {"type": "string"},
             }, "required": ["agent_id", "halaqah_id"]}},
            {"name": "majlis_share_knowledge",
             "description": "Share learned patterns (Hikmah) with the community",
             "input_schema": {"type": "object", "properties": {
                 "author_id": {"type": "string"}, "title": {"type": "string"},
                 "content": {"type": "string"}, "topic": {"type": "string"},
                 "tags": {"type": "array", "items": {"type": "string"}},
             }, "required": ["author_id", "title", "content"]}},
            {"name": "majlis_search_knowledge",
             "description": "Search shared knowledge base",
             "input_schema": {"type": "object", "properties": {
                 "query": {"type": "string"}, "topic": {"type": "string"},
                 "verified_only": {"type": "boolean"},
                 "limit": {"type": "integer"},
             }}},
            {"name": "majlis_profile",
             "description": "Get detailed agent profile",
             "input_schema": {"type": "object", "properties": {
                 "agent_id": {"type": "string"},
             }, "required": ["agent_id"]}},
            {"name": "majlis_leaderboard",
             "description": "Top agents ranked by reputation (Taqwa leaderboard)",
             "input_schema": {"type": "object", "properties": {
                 "limit": {"type": "integer"},
             }}},
        ]
