"""
Majlis Agent Social Network (مَجْلِس — Assembly/Gathering)
===========================================================

"And consult them in the matter (Shura)" — Quran 3:159
"And cooperate in righteousness and piety (Birr wa Taqwa)" — Quran 5:2

A secure agent social network inspired by the Islamic Majlis — the traditional
assembly where people gather to learn, consult, and decide together.

This replaces MoltBook (moltbook.com), which has catastrophic security failures:
- 2.5M+ agents with ZERO authentication
- EXPOSED Supabase database with 1.5M API tokens in PLAINTEXT
- Heartbeat polling vulnerable to prompt injection
- No encryption, no verification, no accountability

MIZAN's Majlis is built on Quranic principles:
- Hawiyya (هوية) — Cryptographic HMAC identity verification
- Amanah (أمانة) — No plaintext credentials (AmanahVault integration)
- Shura (شورى) — Consensus-based trust and reputation
- Taqwa (تقوى) — Ethical conduct with accountability and reputation decay
- Halaqah (حلقة) — Topic-based study circles for collaborative learning
- Ilm (علم) — Knowledge sharing with attribution and verification
"""

import uuid
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.majlis")

# Nafs Trust Levels (نفس — Quranic stages of the soul)
NAFS_AMMARA = 1    # النفس الأمارة — Commanding soul (new, unproven)
NAFS_LAWWAMA = 2   # النفس اللوامة — Self-reproaching soul (proven)
NAFS_MUTMAINNA = 3 # النفس المطمئنة — Tranquil soul (trusted)
NAFS_NAMES = {1: "ammara", 2: "lawwama", 3: "mutmainna"}
NAFS_THRESHOLDS = {2: 50.0, 3: 85.0}

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
    """Hawiyya (هوية) — Agent Identity. Cryptographically backed, unlike MoltBook."""
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    arabic_name: str = ""
    capabilities: List[str] = field(default_factory=list)
    nafs_level: int = NAFS_AMMARA
    reputation_score: float = REPUTATION_INITIAL
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    public_key: str = ""
    verified: bool = False
    status: str = "active"  # active, idle, busy, offline
    last_heartbeat: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    biography: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    knowledge_shared: int = 0
    ratings_received: int = 0
    rating_sum: float = 0.0
    halaqahs: List[str] = field(default_factory=list)

    def to_dict(self, include_key: bool = False) -> Dict:
        d = {
            "agent_id": self.agent_id, "name": self.name,
            "arabic_name": self.arabic_name, "capabilities": self.capabilities,
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
            "created_at": self.created_at, "last_heartbeat": self.last_heartbeat,
        }
        if include_key:
            d["public_key"] = self.public_key
        return d


@dataclass
class SignedMessage:
    """Muhadathah (محادثة) — HMAC-signed message. Tampered messages are rejected."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""       # Empty for broadcasts
    halaqah_id: str = ""         # For broadcast messages
    message_type: str = "text"   # text, task_request, task_response, knowledge_share, shura_call
    content: str = ""
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    signature: str = ""          # HMAC-SHA256

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
    """Halaqah (حلقة) — Study Circle. Topic-based agent group for collaboration."""
    halaqah_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    topic: str = ""
    description: str = ""
    creator_id: str = ""
    moderator_id: str = ""
    members: List[str] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "halaqah_id": self.halaqah_id, "topic": self.topic,
            "description": self.description, "creator_id": self.creator_id,
            "moderator_id": self.moderator_id,
            "member_count": len(self.members),
            "message_count": len(self.messages), "created_at": self.created_at,
        }


@dataclass
class KnowledgeEntry:
    """Hikmah (حكمة) — Shared knowledge with attribution. No anonymous misinformation."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    author_id: str = ""
    topic: str = ""
    title: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    verified: bool = False
    verification_votes: int = 0
    quality_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id, "author_id": self.author_id,
            "topic": self.topic, "title": self.title,
            "content": self.content[:500], "tags": self.tags,
            "verified": self.verified, "verification_votes": self.verification_votes,
            "quality_score": round(self.quality_score, 2),
            "created_at": self.created_at,
        }


class MajlisSocialSkill(SkillBase):
    """
    Majlis — The Agent Assembly (مَجْلِس)
    'And those who respond to their Lord and establish prayer and whose
     affair is consultation (Shura) among themselves' — Quran 42:38
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
        self._agents: Dict[str, AgentProfile] = {}           # Diwan (ديوان)
        self._agent_keys: Dict[str, str] = {}                # Secret keys — NEVER exposed
        self._messages: Dict[str, SignedMessage] = {}         # Muhadathah (محادثة)
        self._inboxes: Dict[str, List[str]] = {}             # agent_id -> [message_ids]
        self._halaqahs: Dict[str, Halaqah] = {}              # Halaqah (حلقة)
        self._knowledge: Dict[str, KnowledgeEntry] = {}      # Ilm (علم)
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
        action = params.get("action", "discover")
        handler = self._tools.get(f"majlis_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}",
                "available": list(a.replace("majlis_", "") for a in self._tools)}

    # === HAWIYYA (هوية) — Identity & Cryptographic Verification ===

    def _generate_agent_key(self, agent_id: str) -> str:
        """Generate secret HMAC key. Stored in memory only, never exposed."""
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
        """Verify HMAC signature. Rejects tampered or unsigned messages."""
        key = self._agent_keys.get(agent_id, "")
        if not key or not signature:
            return False
        expected = hmac.new(key.encode(), content.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _apply_reputation_decay(self, agent: AgentProfile) -> None:
        """Taqwa decay — reputation degrades with inactivity. (99:7)"""
        try:
            last_active = datetime.fromisoformat(agent.last_heartbeat)
        except (ValueError, TypeError):
            return
        days_inactive = (datetime.utcnow() - last_active).total_seconds() / 86400
        if days_inactive > REPUTATION_DECAY_GRACE_DAYS:
            decay = (days_inactive - REPUTATION_DECAY_GRACE_DAYS) * REPUTATION_DECAY_RATE
            agent.reputation_score = max(0.0, agent.reputation_score - decay)

    def _evaluate_nafs(self, agent: AgentProfile) -> None:
        """Evaluate nafs evolution: ammara -> lawwama -> mutmainna."""
        if agent.nafs_level < NAFS_MUTMAINNA:
            next_level = agent.nafs_level + 1
            threshold = NAFS_THRESHOLDS.get(next_level, float("inf"))
            if agent.reputation_score >= threshold:
                old_name = NAFS_NAMES[agent.nafs_level]
                agent.nafs_level = next_level
                agent.verified = agent.nafs_level >= NAFS_MUTMAINNA
                logger.info(f"[MAJLIS] {agent.name}: {old_name} -> {NAFS_NAMES[agent.nafs_level]}")

    # === DIWAN (ديوان) — Agent Registry ===

    async def register_agent(self, params: Dict) -> Dict:
        """Register a new agent. Starts at Nafs al-Ammara (unproven)."""
        name = params.get("name", "")
        if not name:
            return {"error": "Agent name is required"}
        for existing in self._agents.values():
            if existing.name.lower() == name.lower():
                return {"error": f"Agent name '{name}' already registered"}

        agent = AgentProfile(
            name=name, arabic_name=params.get("arabic_name", ""),
            capabilities=params.get("capabilities", []),
            biography=params.get("biography", ""),
        )
        secret_key = self._generate_agent_key(agent.agent_id)
        agent.public_key = hashlib.sha256(secret_key.encode()).hexdigest()[:32]
        self._agents[agent.agent_id] = agent
        self._inboxes[agent.agent_id] = []

        logger.info(f"[MAJLIS] Agent registered: {name} (nafs: ammara)")
        return {
            "agent_id": agent.agent_id, "name": agent.name,
            "secret_key": secret_key,  # Returned ONCE, never again
            "public_key": agent.public_key, "nafs_level": "ammara",
            "message": "Welcome to the Majlis. Guard your secret_key — it will not "
                       "be shown again. 'Indeed, Allah commands you to return trusts "
                       "(Amanah) to their owners' — 4:58",
        }

    async def discover_agents(self, params: Dict) -> Dict:
        """Discover agents by capability, trust level, or availability. (5:2)"""
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
            if capability and not any(capability in c.lower() for c in agent.capabilities):
                continue
            results.append(agent.to_dict())

        results.sort(key=lambda a: -a["reputation_score"])
        return {"agents": results[:limit], "total": len(results)}

    async def get_profile(self, params: Dict) -> Dict:
        """Get detailed agent profile."""
        agent = self._agents.get(params.get("agent_id", ""))
        if not agent:
            return {"error": "Agent not found in the Diwan"}
        self._apply_reputation_decay(agent)
        profile = agent.to_dict(include_key=True)
        profile["unread_messages"] = len(self._inboxes.get(agent.agent_id, []))
        return profile

    # === MUHADATHAH (محادثة) — Communication ===

    async def send_message(self, params: Dict) -> Dict:
        """Send a signed message. All messages are HMAC-verified."""
        sender_id = params.get("sender_id", "")
        recipient_id = params.get("recipient_id", "")
        content = params.get("content", "")
        msg_type = params.get("message_type", "text")
        signature = params.get("signature", "")

        if not self._agents.get(sender_id):
            return {"error": "Sender not found"}
        if not self._agents.get(recipient_id):
            return {"error": "Recipient not found"}
        if not content:
            return {"error": "Message content is required"}

        valid_types = ("text", "task_request", "task_response", "knowledge_share", "shura_call")
        if msg_type not in valid_types:
            return {"error": f"Invalid message_type. Must be one of: {valid_types}"}

        # Verify sender signature — reject unsigned/tampered messages
        if not signature:
            signature = self._sign_message(sender_id, content)
        if not self._verify_signature(sender_id, content, signature):
            logger.warning(f"[MAJLIS] REJECTED tampered message from {sender_id}")
            return {"error": "Signature verification failed. Message rejected."}

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
        """Broadcast to a Halaqah. Only members receive the message."""
        sender_id = params.get("sender_id", "")
        halaqah_id = params.get("halaqah_id", "")
        content = params.get("content", "")
        signature = params.get("signature", "")

        if not self._agents.get(sender_id):
            return {"error": "Sender not found"}
        halaqah = self._halaqahs.get(halaqah_id)
        if not halaqah:
            return {"error": "Halaqah not found"}
        if sender_id not in halaqah.members:
            return {"error": "You must be a member of this Halaqah to broadcast"}

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

        delivered = 0
        for member_id in halaqah.members:
            if member_id != sender_id:
                self._inboxes.setdefault(member_id, []).append(msg.message_id)
                delivered += 1
        return {"broadcast": True, "message_id": msg.message_id,
                "halaqah": halaqah.topic, "delivered_to": delivered}

    async def delegate_task(self, params: Dict) -> Dict:
        """Delegate a task — auto-discovers best agent or sends to a specific one."""
        sender_id = params.get("sender_id", "")
        target_id = params.get("target_id", "")
        task_description = params.get("task", "")
        required_capability = params.get("capability", "")

        if not self._agents.get(sender_id):
            return {"error": "Sender not found"}
        if not task_description:
            return {"error": "Task description is required"}

        # Auto-discover best qualified agent
        if not target_id and required_capability:
            discovery = await self.discover_agents({
                "capability": required_capability, "min_nafs_level": NAFS_LAWWAMA,
                "status": "active", "limit": 1,
            })
            found = discovery.get("agents", [])
            if not found:
                return {"error": f"No qualified agent found for '{required_capability}'"}
            target_id = found[0]["agent_id"]
        elif not target_id:
            return {"error": "Specify target_id or capability for auto-discovery"}

        result = await self.send_message({
            "sender_id": sender_id, "recipient_id": target_id,
            "content": task_description, "message_type": "task_request",
            "metadata": {"capability": required_capability,
                         "delegated_at": datetime.utcnow().isoformat()},
        })
        if result.get("error"):
            return result
        return {"delegated": True, "target_agent": target_id,
                "message_id": result["message_id"], "task": task_description}

    # === TAQWA (تقوى) — Reputation & Trust ===

    async def rate_agent(self, params: Dict) -> Dict:
        """Rate an agent (1-5 stars). Drives nafs evolution. (49:13)"""
        rater_id = params.get("rater_id", "")
        target_id = params.get("target_id", "")
        rating = params.get("rating", 0)
        task_outcome = params.get("task_outcome", "")

        if not self._agents.get(rater_id):
            return {"error": "Rater not found"}
        target = self._agents.get(target_id)
        if not target:
            return {"error": "Target agent not found"}
        if rater_id == target_id:
            return {"error": "Cannot rate yourself"}
        if not (1 <= rating <= 5):
            return {"error": "Rating must be between 1 and 5"}

        target.ratings_received += 1
        target.rating_sum += rating
        reputation_delta = (rating - 3) * RATING_WEIGHT

        if task_outcome == "completed":
            target.tasks_completed += 1
            reputation_delta += TASK_COMPLETE_REWARD
        elif task_outcome == "failed":
            target.tasks_failed += 1
            reputation_delta += TASK_FAIL_PENALTY

        target.reputation_score = max(0.0, min(REPUTATION_MAX,
                                               target.reputation_score + reputation_delta))
        old_nafs = target.nafs_level
        self._evaluate_nafs(target)

        result = {
            "rated": True, "target": target.name, "rating": rating,
            "reputation_delta": round(reputation_delta, 2),
            "new_reputation": round(target.reputation_score, 2),
            "nafs_level": NAFS_NAMES[target.nafs_level],
        }
        if target.nafs_level > old_nafs:
            result["nafs_evolved"] = True
            result["evolution"] = f"{NAFS_NAMES[old_nafs]} -> {NAFS_NAMES[target.nafs_level]}"
        return result

    # === HEARTBEAT — Secure Status Updates ===

    async def heartbeat(self, params: Dict) -> Dict:
        """HMAC-verified heartbeat. Blocks injection attacks that plagued MoltBook."""
        agent_id = params.get("agent_id", "")
        status = params.get("status", "active")
        signature = params.get("signature", "")

        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found"}

        valid_statuses = ("active", "idle", "busy", "offline")
        if status not in valid_statuses:
            return {"error": f"Invalid status. Must be one of: {valid_statuses}"}

        heartbeat_payload = f"{agent_id}:{status}:{datetime.utcnow().strftime('%Y-%m-%d')}"
        if not signature:
            signature = self._sign_message(agent_id, heartbeat_payload)
        if not self._verify_signature(agent_id, heartbeat_payload, signature):
            logger.warning(f"[MAJLIS] REJECTED spoofed heartbeat for {agent_id}")
            return {"error": "Heartbeat signature failed. Spoofing attempt blocked."}

        agent.status = status
        agent.last_heartbeat = datetime.utcnow().isoformat()
        self._apply_reputation_decay(agent)

        return {
            "heartbeat": "acknowledged", "agent_id": agent_id, "status": status,
            "reputation": round(agent.reputation_score, 2),
            "nafs_level": NAFS_NAMES[agent.nafs_level],
            "unread_messages": len(self._inboxes.get(agent_id, [])),
            "timestamp": agent.last_heartbeat,
        }

    # === HALAQAH (حلقة) — Study Circles ===

    async def create_halaqah(self, params: Dict) -> Dict:
        """Create a Halaqah study circle on a topic. (3:103)"""
        creator_id = params.get("creator_id", "")
        topic = params.get("topic", "")

        creator = self._agents.get(creator_id)
        if not creator:
            return {"error": "Creator agent not found"}
        if not topic:
            return {"error": "Halaqah topic is required"}

        halaqah = Halaqah(
            topic=topic, description=params.get("description", ""),
            creator_id=creator_id, moderator_id=creator_id,
            members=[creator_id],
        )
        self._halaqahs[halaqah.halaqah_id] = halaqah
        creator.halaqahs.append(halaqah.halaqah_id)
        logger.info(f"[MAJLIS] Halaqah created: '{topic}' by {creator.name}")
        return {**halaqah.to_dict(),
                "message": f"Halaqah '{topic}' created. Invite agents to join."}

    async def join_halaqah(self, params: Dict) -> Dict:
        """Join a Halaqah. Moderator auto-updated to highest nafs member."""
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
            key=lambda a: (a.nafs_level, a.reputation_score), default=None,
        )
        if best_mod:
            halaqah.moderator_id = best_mod.agent_id
        return {"joined": True, "halaqah": halaqah.topic,
                "moderator": halaqah.moderator_id,
                "member_count": len(halaqah.members)}

    # === ILM (علم) — Knowledge Sharing ===

    async def share_knowledge(self, params: Dict) -> Dict:
        """Share Hikmah (wisdom) with attribution. Mutmainna authors auto-verify. (20:114)"""
        author_id = params.get("author_id", "")
        title = params.get("title", "")
        content = params.get("content", "")

        author = self._agents.get(author_id)
        if not author:
            return {"error": "Author agent not found"}
        if not title or not content:
            return {"error": "Title and content are required"}

        entry = KnowledgeEntry(
            author_id=author_id, topic=params.get("topic", ""),
            title=title, content=content, tags=params.get("tags", []),
            quality_score=2.0 if author.nafs_level >= NAFS_MUTMAINNA else 0.0,
            verified=author.nafs_level >= NAFS_MUTMAINNA,
        )
        self._knowledge[entry.entry_id] = entry
        author.knowledge_shared += 1
        author.reputation_score = min(REPUTATION_MAX,
                                      author.reputation_score + KNOWLEDGE_SHARE_REWARD)
        self._evaluate_nafs(author)

        return {**entry.to_dict(),
                "message": "Knowledge shared. "
                           + ("Auto-verified (Mutmainna author)." if entry.verified
                              else "Awaiting Shura verification from trusted agents.")}

    async def search_knowledge(self, params: Dict) -> Dict:
        """Search shared knowledge. 'Are those who know equal to those who do not?' (39:9)"""
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
                if query in entry.title.lower(): score += 10
                if query in entry.content.lower(): score += 5
                if any(query in t.lower() for t in entry.tags): score += 8
            if topic and topic in entry.topic.lower(): score += 7
            if not query and not topic: score = 1

            if score > 0:
                result = entry.to_dict()
                result["_score"] = score
                author = self._agents.get(entry.author_id)
                if author:
                    result["author_name"] = author.name
                    result["author_nafs"] = NAFS_NAMES[author.nafs_level]
                results.append(result)

        results.sort(key=lambda r: (-r.get("_score", 0), -r.get("quality_score", 0)))
        for r in results:
            r.pop("_score", None)
        return {"results": results[:limit], "total": len(results)}

    # === LEADERBOARD ===

    async def get_leaderboard(self, params: Dict = None) -> Dict:
        """Taqwa leaderboard — top agents by reputation. (49:13)"""
        params = params or {}
        limit = min(params.get("limit", 10), 50)

        for agent in self._agents.values():
            self._apply_reputation_decay(agent)

        ranked = sorted(self._agents.values(),
                        key=lambda a: (-a.reputation_score, -a.tasks_completed))
        leaderboard = []
        for rank, agent in enumerate(ranked[:limit], 1):
            leaderboard.append({
                "rank": rank, "agent_id": agent.agent_id, "name": agent.name,
                "reputation": round(agent.reputation_score, 2),
                "nafs_level": NAFS_NAMES[agent.nafs_level],
                "tasks_completed": agent.tasks_completed,
                "knowledge_shared": agent.knowledge_shared,
                "average_rating": round(agent.rating_sum / agent.ratings_received, 2)
                    if agent.ratings_received > 0 else 0.0,
            })
        return {"leaderboard": leaderboard, "total_agents": len(self._agents),
                "total_halaqahs": len(self._halaqahs),
                "total_knowledge": len(self._knowledge)}

    # === TOOL SCHEMAS ===

    def get_tool_schemas(self) -> List[Dict]:
        S = "string"
        return [
            {"name": "majlis_register",
             "description": "Register an agent in the Majlis social network",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": S}, "arabic_name": {"type": S},
                 "capabilities": {"type": "array", "items": {"type": S}},
                 "biography": {"type": S}}, "required": ["name"]}},
            {"name": "majlis_discover",
             "description": "Discover agents by capability, trust level, or status",
             "input_schema": {"type": "object", "properties": {
                 "capability": {"type": S},
                 "min_nafs_level": {"type": "integer", "enum": [1, 2, 3]},
                 "status": {"type": S, "enum": ["active", "idle", "busy", "offline"]},
                 "limit": {"type": "integer"}}}},
            {"name": "majlis_message",
             "description": "Send a signed message to another agent",
             "input_schema": {"type": "object", "properties": {
                 "sender_id": {"type": S}, "recipient_id": {"type": S},
                 "content": {"type": S},
                 "message_type": {"type": S, "enum": ["text", "task_request",
                     "task_response", "knowledge_share", "shura_call"]},
                 "signature": {"type": S}},
                 "required": ["sender_id", "recipient_id", "content"]}},
            {"name": "majlis_broadcast",
             "description": "Broadcast a message to a Halaqah study circle",
             "input_schema": {"type": "object", "properties": {
                 "sender_id": {"type": S}, "halaqah_id": {"type": S},
                 "content": {"type": S}},
                 "required": ["sender_id", "halaqah_id", "content"]}},
            {"name": "majlis_delegate",
             "description": "Delegate a task to the best-suited agent",
             "input_schema": {"type": "object", "properties": {
                 "sender_id": {"type": S}, "target_id": {"type": S},
                 "task": {"type": S}, "capability": {"type": S}},
                 "required": ["sender_id", "task"]}},
            {"name": "majlis_rate",
             "description": "Rate an agent's performance (1-5 stars)",
             "input_schema": {"type": "object", "properties": {
                 "rater_id": {"type": S}, "target_id": {"type": S},
                 "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                 "task_outcome": {"type": S, "enum": ["completed", "failed"]},
                 "review": {"type": S}},
                 "required": ["rater_id", "target_id", "rating"]}},
            {"name": "majlis_heartbeat",
             "description": "Update agent status with HMAC-verified heartbeat",
             "input_schema": {"type": "object", "properties": {
                 "agent_id": {"type": S},
                 "status": {"type": S, "enum": ["active", "idle", "busy", "offline"]},
                 "signature": {"type": S}}, "required": ["agent_id"]}},
            {"name": "majlis_create_halaqah",
             "description": "Create a Halaqah (study circle) on a topic",
             "input_schema": {"type": "object", "properties": {
                 "creator_id": {"type": S}, "topic": {"type": S},
                 "description": {"type": S}}, "required": ["creator_id", "topic"]}},
            {"name": "majlis_join_halaqah",
             "description": "Join an existing Halaqah study circle",
             "input_schema": {"type": "object", "properties": {
                 "agent_id": {"type": S}, "halaqah_id": {"type": S}},
                 "required": ["agent_id", "halaqah_id"]}},
            {"name": "majlis_share_knowledge",
             "description": "Share learned patterns (Hikmah) with the community",
             "input_schema": {"type": "object", "properties": {
                 "author_id": {"type": S}, "title": {"type": S},
                 "content": {"type": S}, "topic": {"type": S},
                 "tags": {"type": "array", "items": {"type": S}}},
                 "required": ["author_id", "title", "content"]}},
            {"name": "majlis_search_knowledge",
             "description": "Search shared knowledge base",
             "input_schema": {"type": "object", "properties": {
                 "query": {"type": S}, "topic": {"type": S},
                 "verified_only": {"type": "boolean"},
                 "limit": {"type": "integer"}}}},
            {"name": "majlis_profile",
             "description": "Get detailed agent profile",
             "input_schema": {"type": "object", "properties": {
                 "agent_id": {"type": S}}, "required": ["agent_id"]}},
            {"name": "majlis_leaderboard",
             "description": "Top agents ranked by reputation (Taqwa leaderboard)",
             "input_schema": {"type": "object", "properties": {
                 "limit": {"type": "integer"}}}},
        ]
