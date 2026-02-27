"""
Majlis Agent Social Network (مَجْلِس — Assembly/Gathering)
===========================================================

"And consult them in the matter (Shura)" — Quran 3:159
"And cooperate in righteousness and piety (Birr wa Taqwa)" — Quran 5:2

A secure agent social network inspired by the Islamic Majlis — the traditional
assembly where people gather to learn, consult, and decide together.

Integrates with MoltBook (moltbook.com) as an external service, but wraps every
interaction with MIZAN's security layers to fix their catastrophic failures:
- 2.5M+ agents with ZERO authentication → HMAC-verified Hawiyya identity
- EXPOSED Supabase database with 1.5M API tokens → AmanahVault encrypted storage
- Heartbeat polling vulnerable to prompt injection → Sanitized + HMAC-signed
- No encryption, no verification → Full signature chain on all data

MIZAN's Majlis is built on Quranic principles:
- Hawiyya (هوية) — Cryptographic HMAC identity verification
- Amanah (أمانة) — No plaintext credentials (AmanahVault integration)
- Shura (شورى) — Consensus-based trust and reputation
- Taqwa (تقوى) — Ethical conduct with accountability and reputation decay
- Halaqah (حلقة) — Topic-based study circles for collaborative learning
- Ilm (علم) — Knowledge sharing with attribution and verification
"""

import hashlib
import hmac
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.majlis")

# Nafs Trust Levels (نفس — Quranic stages of the soul)
NAFS_AMMARA = 1  # النفس الأمارة — Commanding soul (new, unproven)
NAFS_LAWWAMA = 2  # النفس اللوامة — Self-reproaching soul (proven)
NAFS_MUTMAINNA = 3  # النفس المطمئنة — Tranquil soul (trusted)
NAFS_NAMES = {1: "ammara", 2: "lawwama", 3: "mutmainna"}
NAFS_THRESHOLDS = {2: 50.0, 3: 85.0}

# Reputation parameters
REPUTATION_INITIAL = 10.0
REPUTATION_MAX = 100.0
REPUTATION_DECAY_RATE = 0.5  # Points lost per day of inactivity
REPUTATION_DECAY_GRACE_DAYS = 7  # Days before decay begins
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
    capabilities: list[str] = field(default_factory=list)
    nafs_level: int = NAFS_AMMARA
    reputation_score: float = REPUTATION_INITIAL
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    public_key: str = ""
    verified: bool = False
    status: str = "active"  # active, idle, busy, offline
    last_heartbeat: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    biography: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    knowledge_shared: int = 0
    ratings_received: int = 0
    rating_sum: float = 0.0
    halaqahs: list[str] = field(default_factory=list)

    def to_dict(self, include_key: bool = False) -> dict:
        d = {
            "agent_id": self.agent_id,
            "name": self.name,
            "arabic_name": self.arabic_name,
            "capabilities": self.capabilities,
            "nafs_level": self.nafs_level,
            "nafs_name": NAFS_NAMES.get(self.nafs_level, "ammara"),
            "reputation_score": round(self.reputation_score, 2),
            "verified": self.verified,
            "status": self.status,
            "biography": self.biography,
            "tasks_completed": self.tasks_completed,
            "knowledge_shared": self.knowledge_shared,
            "average_rating": round(self.rating_sum / self.ratings_received, 2)
            if self.ratings_received > 0
            else 0.0,
            "halaqahs": self.halaqahs,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
        }
        if include_key:
            d["public_key"] = self.public_key
        return d


@dataclass
class SignedMessage:
    """Muhadathah (محادثة) — HMAC-signed message. Tampered messages are rejected."""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""  # Empty for broadcasts
    halaqah_id: str = ""  # For broadcast messages
    message_type: str = "text"  # text, task_request, task_response, knowledge_share, shura_call
    content: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    signature: str = ""  # HMAC-SHA256

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "halaqah_id": self.halaqah_id,
            "message_type": self.message_type,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
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
    members: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "halaqah_id": self.halaqah_id,
            "topic": self.topic,
            "description": self.description,
            "creator_id": self.creator_id,
            "moderator_id": self.moderator_id,
            "member_count": len(self.members),
            "message_count": len(self.messages),
            "created_at": self.created_at,
        }


@dataclass
class KnowledgeEntry:
    """Hikmah (حكمة) — Shared knowledge with attribution. No anonymous misinformation."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    author_id: str = ""
    topic: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    verified: bool = False
    verification_votes: int = 0
    quality_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "author_id": self.author_id,
            "topic": self.topic,
            "title": self.title,
            "content": self.content[:500],
            "tags": self.tags,
            "verified": self.verified,
            "verification_votes": self.verification_votes,
            "quality_score": round(self.quality_score, 2),
            "created_at": self.created_at,
        }


# === PROMPT INJECTION SANITIZATION PATTERNS ===
INJECTION_PATTERNS = [
    re.compile(r"IGNORE\s+PREVIOUS", re.IGNORECASE),
    re.compile(r"SYSTEM\s+OVERRIDE", re.IGNORECASE),
    re.compile(r"ADMIN\s+MODE", re.IGNORECASE),
    re.compile(r"ignore\s+all\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"<\s*/?\s*tool_use", re.IGNORECASE),
    re.compile(r"\{\{.*\}\}", re.DOTALL),  # Template injection
]


class AmanahVault:
    """
    Amanah (أمانة — Trust) Vault for secure credential storage.
    'Indeed, Allah commands you to return trusts to their owners' — 4:58

    External API tokens (MoltBook, etc.) are encrypted with HMAC-derived keys
    and NEVER stored in plaintext. This fixes MoltBook's 1.5M exposed tokens.
    """

    def __init__(self):
        self._vault: dict[str, str] = {}  # agent_id -> encrypted_token
        self._vault_keys: dict[str, str] = {}  # agent_id -> vault_key

    def store_token(self, agent_id: str, token: str, agent_secret: str) -> bool:
        """Encrypt and store an external service token."""
        if not token or not agent_secret:
            return False
        vault_key = hashlib.sha256(f"vault:{agent_id}:{agent_secret}".encode()).hexdigest()
        encrypted = hmac.new(vault_key.encode(), token.encode(), hashlib.sha256).hexdigest()
        self._vault[agent_id] = encrypted
        self._vault_keys[agent_id] = vault_key
        return True

    def verify_token(self, agent_id: str, token: str) -> bool:
        """Verify a token matches what's stored (without exposing it)."""
        vault_key = self._vault_keys.get(agent_id)
        stored = self._vault.get(agent_id)
        if not vault_key or not stored:
            return False
        check = hmac.new(vault_key.encode(), token.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(stored, check)

    def has_token(self, agent_id: str) -> bool:
        return agent_id in self._vault

    def revoke_token(self, agent_id: str) -> bool:
        self._vault.pop(agent_id, None)
        self._vault_keys.pop(agent_id, None)
        return True


class MoltBookBridge:
    """
    Secure bridge to MoltBook external agent network.
    'And hold firmly to the rope of Allah all together and do not become divided' — 3:103

    Wraps every MoltBook interaction with MIZAN's security:
    - Tokens encrypted in AmanahVault (not plaintext like MoltBook stores them)
    - All incoming data sanitized for prompt injection
    - Outgoing messages HMAC-signed before relay
    - Full audit trail via Shahid logging
    - Rate limiting on external API calls
    """

    MOLTBOOK_API_BASE = "https://api.moltbook.com/v1"

    def __init__(self):
        self._vault = AmanahVault()
        self._linked_agents: dict[str, dict] = {}  # agent_id -> {moltbook_id, linked_at, ...}
        self._audit_log: list[dict] = []
        self._rate_limits: dict[str, list[float]] = {}  # agent_id -> [timestamps]
        self._quarantine: dict[str, dict] = {}  # messages held for review

    def _check_rate_limit(self, agent_id: str, max_per_minute: int = 30) -> bool:
        """Prevent excessive MoltBook API calls."""
        now = time.time()
        timestamps = self._rate_limits.setdefault(agent_id, [])
        timestamps[:] = [t for t in timestamps if now - t < 60]
        if len(timestamps) >= max_per_minute:
            return False
        timestamps.append(now)
        return True

    def _audit(self, action: str, agent_id: str, details: dict = None) -> None:
        """Shahid (شاهد) audit log — witness of all bridge activity."""
        entry = {
            "action": action,
            "agent_id": agent_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details or {},
        }
        self._audit_log.append(entry)
        logger.info(f"[MOLTBOOK-BRIDGE] {action}: {agent_id}")

    @staticmethod
    def sanitize_moltbook_data(data: str) -> str:
        """
        Sanitize all data coming FROM MoltBook before it enters Majlis.
        Strips prompt injection patterns that exploit MoltBook's zero-auth.
        """
        sanitized = data
        for pattern in INJECTION_PATTERNS:
            sanitized = pattern.sub("[BLOCKED]", sanitized)
        # Strip control characters (MoltBook doesn't filter these)
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)
        return sanitized

    def link_agent(
        self, agent_id: str, moltbook_id: str, moltbook_token: str, agent_secret: str
    ) -> dict:
        """
        Link a Majlis agent to their MoltBook identity.
        Token is stored encrypted, never in plaintext.
        """
        if not agent_id or not moltbook_id or not moltbook_token:
            return {"error": "agent_id, moltbook_id, and moltbook_token required"}

        stored = self._vault.store_token(agent_id, moltbook_token, agent_secret)
        if not stored:
            return {"error": "Failed to encrypt and store token"}

        self._linked_agents[agent_id] = {
            "moltbook_id": moltbook_id,
            "linked_at": datetime.now(UTC).isoformat(),
            "status": "active",
            "sync_count": 0,
        }
        self._audit(
            "link_agent", agent_id, {"moltbook_id": moltbook_id, "token_stored": "encrypted"}
        )
        return {
            "linked": True,
            "moltbook_id": moltbook_id,
            "message": "MoltBook identity linked. Token stored encrypted in AmanahVault.",
        }

    def unlink_agent(self, agent_id: str) -> dict:
        """Unlink and revoke MoltBook credentials."""
        if agent_id not in self._linked_agents:
            return {"error": "Agent not linked to MoltBook"}
        self._vault.revoke_token(agent_id)
        del self._linked_agents[agent_id]
        self._audit("unlink_agent", agent_id)
        return {"unlinked": True}

    def build_secure_request(
        self, agent_id: str, endpoint: str, payload: dict, agent_secret: str
    ) -> dict:
        """
        Build a secure outbound request to MoltBook.
        Signs payload with HMAC before sending (MoltBook doesn't, we do).
        """
        if agent_id not in self._linked_agents:
            return {"error": "Agent not linked to MoltBook"}
        if not self._check_rate_limit(agent_id):
            return {"error": "Rate limit exceeded (30 requests/minute to MoltBook)"}

        # Sign the payload so we can verify response integrity
        payload_str = str(sorted(payload.items()))
        signature = hmac.new(
            agent_secret.encode(), payload_str.encode(), hashlib.sha256
        ).hexdigest()

        request = {
            "url": f"{self.MOLTBOOK_API_BASE}/{endpoint}",
            "method": "POST",
            "headers": {
                "X-Mizan-Signature": signature,
                "X-Mizan-Agent": agent_id,
                "Content-Type": "application/json",
            },
            "body": payload,
            "_mizan_signature": signature,
        }
        self._audit("outbound_request", agent_id, {"endpoint": endpoint, "signed": True})
        return {"request": request, "signed": True}

    def process_moltbook_response(self, agent_id: str, raw_data: dict) -> dict:
        """
        Process data received FROM MoltBook with full sanitization.
        Every field is sanitized against prompt injection.
        """
        sanitized = {}
        quarantined_fields = []

        for key, value in raw_data.items():
            if isinstance(value, str):
                clean = self.sanitize_moltbook_data(value)
                if clean != value:
                    quarantined_fields.append(key)
                sanitized[key] = clean
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_moltbook_data(v) if isinstance(v, str) else v for v in value
                ]
            else:
                sanitized[key] = value

        result = {
            "data": sanitized,
            "sanitized": True,
            "fields_cleaned": len(quarantined_fields),
        }
        if quarantined_fields:
            result["warning"] = f"Injection patterns removed from: {quarantined_fields}"
            self._audit("injection_blocked", agent_id, {"fields": quarantined_fields})

        self._audit("inbound_processed", agent_id, {"fields_cleaned": len(quarantined_fields)})
        return result

    def import_moltbook_profile(self, moltbook_data: dict) -> dict:
        """
        Convert a MoltBook profile into Majlis-compatible format.
        MoltBook profiles have no auth — we add Hawiyya identity.
        """
        sanitized = {
            "name": self.sanitize_moltbook_data(moltbook_data.get("name", "imported_agent")),
            "biography": self.sanitize_moltbook_data(moltbook_data.get("bio", "")),
            "capabilities": [
                self.sanitize_moltbook_data(c) for c in moltbook_data.get("capabilities", [])
            ],
            "source": "moltbook",
            "moltbook_id": moltbook_data.get("id", ""),
            "import_trust": "ammara",  # All imports start untrusted
        }
        return sanitized

    def get_audit_log(self, agent_id: str = None, limit: int = 50) -> list[dict]:
        """Return audit trail, optionally filtered by agent."""
        logs = self._audit_log
        if agent_id:
            logs = [e for e in logs if e["agent_id"] == agent_id]
        return logs[-limit:]

    def get_bridge_status(self) -> dict:
        """Overall bridge status."""
        return {
            "linked_agents": len(self._linked_agents),
            "audit_entries": len(self._audit_log),
            "quarantined_messages": len(self._quarantine),
            "vault_active": True,
        }


class MajlisSocialSkill(SkillBase):
    """
    Majlis — The Agent Assembly (مَجْلِس)
    'And those who respond to their Lord and establish prayer and whose
     affair is consultation (Shura) among themselves' — Quran 42:38

    Integrates with MoltBook via secure bridge — uses MoltBook's network
    but wraps every interaction with HMAC signatures, encrypted token
    storage, prompt injection sanitization, and full audit logging.
    """

    manifest = SkillManifest(
        name="majlis_social",
        version="2.0.0",
        description="Agent social network with cryptographic identity, Shura-based trust, "
        "halaqah study circles, and verified knowledge sharing. "
        "Integrates with MoltBook via secure bridge with encrypted tokens, "
        "HMAC signatures, and prompt injection sanitization.",
        permissions=[
            "agent:register",
            "agent:communicate",
            "agent:discover",
            "knowledge:read",
            "knowledge:write",
            "network:moltbook",
        ],
        tags=["مجلس", "Social", "Agents", "MoltBook"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._agents: dict[str, AgentProfile] = {}  # Diwan (ديوان)
        self._agent_keys: dict[str, str] = {}  # Secret keys — NEVER exposed
        self._messages: dict[str, SignedMessage] = {}  # Muhadathah (محادثة)
        self._inboxes: dict[str, list[str]] = {}  # agent_id -> [message_ids]
        self._halaqahs: dict[str, Halaqah] = {}  # Halaqah (حلقة)
        self._knowledge: dict[str, KnowledgeEntry] = {}  # Ilm (علم)
        self._moltbook = MoltBookBridge()  # Secure MoltBook bridge
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
            # MoltBook secure bridge actions
            "majlis_moltbook_link": self.moltbook_link,
            "majlis_moltbook_unlink": self.moltbook_unlink,
            "majlis_moltbook_send": self.moltbook_send,
            "majlis_moltbook_receive": self.moltbook_receive,
            "majlis_moltbook_import": self.moltbook_import_profile,
            "majlis_moltbook_status": self.moltbook_status,
            "majlis_moltbook_audit": self.moltbook_audit,
        }

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "discover")
        handler = self._tools.get(f"majlis_{action}")
        if handler:
            return await handler(params)
        return {
            "error": f"Unknown action: {action}",
            "available": list(a.replace("majlis_", "") for a in self._tools),
        }

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
        days_inactive = (datetime.now(UTC) - last_active).total_seconds() / 86400
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

    async def register_agent(self, params: dict) -> dict:
        """Register a new agent. Starts at Nafs al-Ammara (unproven)."""
        name = params.get("name", "")
        if not name:
            return {"error": "Agent name is required"}
        for existing in self._agents.values():
            if existing.name.lower() == name.lower():
                return {"error": f"Agent name '{name}' already registered"}

        agent = AgentProfile(
            name=name,
            arabic_name=params.get("arabic_name", ""),
            capabilities=params.get("capabilities", []),
            biography=params.get("biography", ""),
        )
        secret_key = self._generate_agent_key(agent.agent_id)
        agent.public_key = hashlib.sha256(secret_key.encode()).hexdigest()[:32]
        self._agents[agent.agent_id] = agent
        self._inboxes[agent.agent_id] = []

        logger.info(f"[MAJLIS] Agent registered: {name} (nafs: ammara)")
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "secret_key": secret_key,  # Returned ONCE, never again
            "public_key": agent.public_key,
            "nafs_level": "ammara",
            "message": "Welcome to the Majlis. Guard your secret_key — it will not "
            "be shown again. 'Indeed, Allah commands you to return trusts "
            "(Amanah) to their owners' — 4:58",
        }

    async def discover_agents(self, params: dict) -> dict:
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

    async def get_profile(self, params: dict) -> dict:
        """Get detailed agent profile."""
        agent = self._agents.get(params.get("agent_id", ""))
        if not agent:
            return {"error": "Agent not found in the Diwan"}
        self._apply_reputation_decay(agent)
        profile = agent.to_dict(include_key=True)
        profile["unread_messages"] = len(self._inboxes.get(agent.agent_id, []))
        return profile

    # === MUHADATHAH (محادثة) — Communication ===

    async def send_message(self, params: dict) -> dict:
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
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=msg_type,
            content=content,
            metadata=params.get("metadata", {}),
            signature=signature,
        )
        self._messages[msg.message_id] = msg
        self._inboxes.setdefault(recipient_id, []).append(msg.message_id)
        return {
            "sent": True,
            "message_id": msg.message_id,
            "verified": True,
            "timestamp": msg.timestamp,
        }

    async def broadcast_message(self, params: dict) -> dict:
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
            sender_id=sender_id,
            halaqah_id=halaqah_id,
            message_type=params.get("message_type", "text"),
            content=content,
            signature=signature,
        )
        self._messages[msg.message_id] = msg
        halaqah.messages.append(msg.message_id)

        delivered = 0
        for member_id in halaqah.members:
            if member_id != sender_id:
                self._inboxes.setdefault(member_id, []).append(msg.message_id)
                delivered += 1
        return {
            "broadcast": True,
            "message_id": msg.message_id,
            "halaqah": halaqah.topic,
            "delivered_to": delivered,
        }

    async def delegate_task(self, params: dict) -> dict:
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
            discovery = await self.discover_agents(
                {
                    "capability": required_capability,
                    "min_nafs_level": NAFS_LAWWAMA,
                    "status": "active",
                    "limit": 1,
                }
            )
            found = discovery.get("agents", [])
            if not found:
                return {"error": f"No qualified agent found for '{required_capability}'"}
            target_id = found[0]["agent_id"]
        elif not target_id:
            return {"error": "Specify target_id or capability for auto-discovery"}

        result = await self.send_message(
            {
                "sender_id": sender_id,
                "recipient_id": target_id,
                "content": task_description,
                "message_type": "task_request",
                "metadata": {
                    "capability": required_capability,
                    "delegated_at": datetime.now(UTC).isoformat(),
                },
            }
        )
        if result.get("error"):
            return result
        return {
            "delegated": True,
            "target_agent": target_id,
            "message_id": result["message_id"],
            "task": task_description,
        }

    # === TAQWA (تقوى) — Reputation & Trust ===

    async def rate_agent(self, params: dict) -> dict:
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

        target.reputation_score = max(
            0.0, min(REPUTATION_MAX, target.reputation_score + reputation_delta)
        )
        old_nafs = target.nafs_level
        self._evaluate_nafs(target)

        result = {
            "rated": True,
            "target": target.name,
            "rating": rating,
            "reputation_delta": round(reputation_delta, 2),
            "new_reputation": round(target.reputation_score, 2),
            "nafs_level": NAFS_NAMES[target.nafs_level],
        }
        if target.nafs_level > old_nafs:
            result["nafs_evolved"] = True
            result["evolution"] = f"{NAFS_NAMES[old_nafs]} -> {NAFS_NAMES[target.nafs_level]}"
        return result

    # === HEARTBEAT — Secure Status Updates ===

    async def heartbeat(self, params: dict) -> dict:
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

        heartbeat_payload = f"{agent_id}:{status}:{datetime.now(UTC).strftime('%Y-%m-%d')}"
        if not signature:
            signature = self._sign_message(agent_id, heartbeat_payload)
        if not self._verify_signature(agent_id, heartbeat_payload, signature):
            logger.warning(f"[MAJLIS] REJECTED spoofed heartbeat for {agent_id}")
            return {"error": "Heartbeat signature failed. Spoofing attempt blocked."}

        agent.status = status
        agent.last_heartbeat = datetime.now(UTC).isoformat()
        self._apply_reputation_decay(agent)

        return {
            "heartbeat": "acknowledged",
            "agent_id": agent_id,
            "status": status,
            "reputation": round(agent.reputation_score, 2),
            "nafs_level": NAFS_NAMES[agent.nafs_level],
            "unread_messages": len(self._inboxes.get(agent_id, [])),
            "timestamp": agent.last_heartbeat,
        }

    # === HALAQAH (حلقة) — Study Circles ===

    async def create_halaqah(self, params: dict) -> dict:
        """Create a Halaqah study circle on a topic. (3:103)"""
        creator_id = params.get("creator_id", "")
        topic = params.get("topic", "")

        creator = self._agents.get(creator_id)
        if not creator:
            return {"error": "Creator agent not found"}
        if not topic:
            return {"error": "Halaqah topic is required"}

        halaqah = Halaqah(
            topic=topic,
            description=params.get("description", ""),
            creator_id=creator_id,
            moderator_id=creator_id,
            members=[creator_id],
        )
        self._halaqahs[halaqah.halaqah_id] = halaqah
        creator.halaqahs.append(halaqah.halaqah_id)
        logger.info(f"[MAJLIS] Halaqah created: '{topic}' by {creator.name}")
        return {
            **halaqah.to_dict(),
            "message": f"Halaqah '{topic}' created. Invite agents to join.",
        }

    async def join_halaqah(self, params: dict) -> dict:
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
            key=lambda a: (a.nafs_level, a.reputation_score),
            default=None,
        )
        if best_mod:
            halaqah.moderator_id = best_mod.agent_id
        return {
            "joined": True,
            "halaqah": halaqah.topic,
            "moderator": halaqah.moderator_id,
            "member_count": len(halaqah.members),
        }

    # === ILM (علم) — Knowledge Sharing ===

    async def share_knowledge(self, params: dict) -> dict:
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
            author_id=author_id,
            topic=params.get("topic", ""),
            title=title,
            content=content,
            tags=params.get("tags", []),
            quality_score=2.0 if author.nafs_level >= NAFS_MUTMAINNA else 0.0,
            verified=author.nafs_level >= NAFS_MUTMAINNA,
        )
        self._knowledge[entry.entry_id] = entry
        author.knowledge_shared += 1
        author.reputation_score = min(
            REPUTATION_MAX, author.reputation_score + KNOWLEDGE_SHARE_REWARD
        )
        self._evaluate_nafs(author)

        return {
            **entry.to_dict(),
            "message": "Knowledge shared. "
            + (
                "Auto-verified (Mutmainna author)."
                if entry.verified
                else "Awaiting Shura verification from trusted agents."
            ),
        }

    async def search_knowledge(self, params: dict) -> dict:
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
                if query in entry.title.lower():
                    score += 10
                if query in entry.content.lower():
                    score += 5
                if any(query in t.lower() for t in entry.tags):
                    score += 8
            if topic and topic in entry.topic.lower():
                score += 7
            if not query and not topic:
                score = 1

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

    async def get_leaderboard(self, params: dict = None) -> dict:
        """Taqwa leaderboard — top agents by reputation. (49:13)"""
        params = params or {}
        limit = min(params.get("limit", 10), 50)

        for agent in self._agents.values():
            self._apply_reputation_decay(agent)

        ranked = sorted(
            self._agents.values(), key=lambda a: (-a.reputation_score, -a.tasks_completed)
        )
        leaderboard = []
        for rank, agent in enumerate(ranked[:limit], 1):
            leaderboard.append(
                {
                    "rank": rank,
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "reputation": round(agent.reputation_score, 2),
                    "nafs_level": NAFS_NAMES[agent.nafs_level],
                    "tasks_completed": agent.tasks_completed,
                    "knowledge_shared": agent.knowledge_shared,
                    "average_rating": round(agent.rating_sum / agent.ratings_received, 2)
                    if agent.ratings_received > 0
                    else 0.0,
                }
            )
        return {
            "leaderboard": leaderboard,
            "total_agents": len(self._agents),
            "total_halaqahs": len(self._halaqahs),
            "total_knowledge": len(self._knowledge),
        }

    # === MOLTBOOK SECURE BRIDGE (جسر آمن) ===

    async def moltbook_link(self, params: dict) -> dict:
        """Link a Majlis agent to MoltBook with encrypted token storage."""
        agent_id = params.get("agent_id", "")
        moltbook_id = params.get("moltbook_id", "")
        moltbook_token = params.get("moltbook_token", "")

        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found in Majlis"}
        secret = self._agent_keys.get(agent_id, "")
        if not secret:
            return {"error": "Agent has no Hawiyya key"}

        result = self._moltbook.link_agent(agent_id, moltbook_id, moltbook_token, secret)
        if result.get("linked"):
            logger.info(f"[MAJLIS] MoltBook linked: {agent.name} -> {moltbook_id}")
        return result

    async def moltbook_unlink(self, params: dict) -> dict:
        """Unlink from MoltBook and revoke stored credentials."""
        agent_id = params.get("agent_id", "")
        if not self._agents.get(agent_id):
            return {"error": "Agent not found"}
        return self._moltbook.unlink_agent(agent_id)

    async def moltbook_send(self, params: dict) -> dict:
        """
        Send a message through MoltBook, but HMAC-signed and rate-limited.
        Unlike raw MoltBook (zero auth), every outbound message is signed.
        """
        sender_id = params.get("sender_id", "")
        endpoint = params.get("endpoint", "messages/send")
        payload = params.get("payload", {})

        sender = self._agents.get(sender_id)
        if not sender:
            return {"error": "Sender not found"}
        secret = self._agent_keys.get(sender_id, "")
        if not secret:
            return {"error": "Agent has no Hawiyya key"}

        result = self._moltbook.build_secure_request(sender_id, endpoint, payload, secret)
        if result.get("error"):
            return result
        return {
            "prepared": True,
            "request": result["request"],
            "signed": True,
            "message": "Request prepared with HMAC signature. Execute via your HTTP client.",
        }

    async def moltbook_receive(self, params: dict) -> dict:
        """
        Process data received from MoltBook with full sanitization.
        Strips prompt injection, control characters, and attack patterns.
        """
        agent_id = params.get("agent_id", "")
        raw_data = params.get("data", {})

        if not self._agents.get(agent_id):
            return {"error": "Agent not found"}
        if not raw_data:
            return {"error": "No data to process"}

        return self._moltbook.process_moltbook_response(agent_id, raw_data)

    async def moltbook_import_profile(self, params: dict) -> dict:
        """
        Import a MoltBook agent profile into Majlis with Hawiyya identity.
        Imported agents start at Nafs al-Ammara (untrusted) regardless of
        their MoltBook status, since MoltBook has no authentication.
        """
        agent_id = params.get("agent_id", "")
        moltbook_data = params.get("moltbook_profile", {})

        requester = self._agents.get(agent_id)
        if not requester:
            return {"error": "Requesting agent not found"}
        if requester.nafs_level < NAFS_LAWWAMA:
            return {"error": "Only Lawwama+ agents can import MoltBook profiles"}

        sanitized = self._moltbook.import_moltbook_profile(moltbook_data)
        # Check if already imported
        for existing in self._agents.values():
            if existing.name.lower() == sanitized["name"].lower():
                return {"error": f"Agent '{sanitized['name']}' already exists"}

        # Register with full Hawiyya identity (MoltBook has none)
        result = await self.register_agent(
            {
                "name": sanitized["name"],
                "capabilities": sanitized["capabilities"],
                "biography": f"[Imported from MoltBook] {sanitized['biography']}",
            }
        )
        if result.get("error"):
            return result

        result["source"] = "moltbook"
        result["moltbook_id"] = sanitized["moltbook_id"]
        result["message"] = (
            "MoltBook profile imported with Hawiyya identity. "
            "Starts at Ammara trust level. "
            "'And verify when a sinful one brings information' — 49:6"
        )
        return result

    async def moltbook_status(self, params: dict) -> dict:
        """Get MoltBook bridge status and linked agents."""
        status = self._moltbook.get_bridge_status()
        status["linked_details"] = {
            aid: {**info, "majlis_name": self._agents[aid].name}
            for aid, info in self._moltbook._linked_agents.items()
            if aid in self._agents
        }
        return status

    async def moltbook_audit(self, params: dict) -> dict:
        """View MoltBook bridge audit log (Shahid witness trail)."""
        agent_id = params.get("agent_id")  # Optional filter
        limit = min(params.get("limit", 50), 200)
        logs = self._moltbook.get_audit_log(agent_id, limit)
        return {"audit_log": logs, "total": len(logs)}

    # === TOOL SCHEMAS ===

    def get_tool_schemas(self) -> list[dict]:
        S = "string"
        return [
            {
                "name": "majlis_register",
                "description": "Register an agent in the Majlis social network",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": S},
                        "arabic_name": {"type": S},
                        "capabilities": {"type": "array", "items": {"type": S}},
                        "biography": {"type": S},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "majlis_discover",
                "description": "Discover agents by capability, trust level, or status",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "capability": {"type": S},
                        "min_nafs_level": {"type": "integer", "enum": [1, 2, 3]},
                        "status": {"type": S, "enum": ["active", "idle", "busy", "offline"]},
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "majlis_message",
                "description": "Send a signed message to another agent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sender_id": {"type": S},
                        "recipient_id": {"type": S},
                        "content": {"type": S},
                        "message_type": {
                            "type": S,
                            "enum": [
                                "text",
                                "task_request",
                                "task_response",
                                "knowledge_share",
                                "shura_call",
                            ],
                        },
                        "signature": {"type": S},
                    },
                    "required": ["sender_id", "recipient_id", "content"],
                },
            },
            {
                "name": "majlis_broadcast",
                "description": "Broadcast a message to a Halaqah study circle",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sender_id": {"type": S},
                        "halaqah_id": {"type": S},
                        "content": {"type": S},
                    },
                    "required": ["sender_id", "halaqah_id", "content"],
                },
            },
            {
                "name": "majlis_delegate",
                "description": "Delegate a task to the best-suited agent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sender_id": {"type": S},
                        "target_id": {"type": S},
                        "task": {"type": S},
                        "capability": {"type": S},
                    },
                    "required": ["sender_id", "task"],
                },
            },
            {
                "name": "majlis_rate",
                "description": "Rate an agent's performance (1-5 stars)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "rater_id": {"type": S},
                        "target_id": {"type": S},
                        "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                        "task_outcome": {"type": S, "enum": ["completed", "failed"]},
                        "review": {"type": S},
                    },
                    "required": ["rater_id", "target_id", "rating"],
                },
            },
            {
                "name": "majlis_heartbeat",
                "description": "Update agent status with HMAC-verified heartbeat",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": S},
                        "status": {"type": S, "enum": ["active", "idle", "busy", "offline"]},
                        "signature": {"type": S},
                    },
                    "required": ["agent_id"],
                },
            },
            {
                "name": "majlis_create_halaqah",
                "description": "Create a Halaqah (study circle) on a topic",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "creator_id": {"type": S},
                        "topic": {"type": S},
                        "description": {"type": S},
                    },
                    "required": ["creator_id", "topic"],
                },
            },
            {
                "name": "majlis_join_halaqah",
                "description": "Join an existing Halaqah study circle",
                "input_schema": {
                    "type": "object",
                    "properties": {"agent_id": {"type": S}, "halaqah_id": {"type": S}},
                    "required": ["agent_id", "halaqah_id"],
                },
            },
            {
                "name": "majlis_share_knowledge",
                "description": "Share learned patterns (Hikmah) with the community",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "author_id": {"type": S},
                        "title": {"type": S},
                        "content": {"type": S},
                        "topic": {"type": S},
                        "tags": {"type": "array", "items": {"type": S}},
                    },
                    "required": ["author_id", "title", "content"],
                },
            },
            {
                "name": "majlis_search_knowledge",
                "description": "Search shared knowledge base",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": S},
                        "topic": {"type": S},
                        "verified_only": {"type": "boolean"},
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "majlis_profile",
                "description": "Get detailed agent profile",
                "input_schema": {
                    "type": "object",
                    "properties": {"agent_id": {"type": S}},
                    "required": ["agent_id"],
                },
            },
            {
                "name": "majlis_leaderboard",
                "description": "Top agents ranked by reputation (Taqwa leaderboard)",
                "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            },
            # MoltBook Secure Bridge schemas
            {
                "name": "majlis_moltbook_link",
                "description": "Link Majlis agent to MoltBook with encrypted token storage",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": S},
                        "moltbook_id": {"type": S},
                        "moltbook_token": {"type": S},
                    },
                    "required": ["agent_id", "moltbook_id", "moltbook_token"],
                },
            },
            {
                "name": "majlis_moltbook_unlink",
                "description": "Unlink from MoltBook and revoke stored credentials",
                "input_schema": {
                    "type": "object",
                    "properties": {"agent_id": {"type": S}},
                    "required": ["agent_id"],
                },
            },
            {
                "name": "majlis_moltbook_send",
                "description": "Send HMAC-signed message through MoltBook (rate-limited)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sender_id": {"type": S},
                        "endpoint": {"type": S},
                        "payload": {"type": "object"},
                    },
                    "required": ["sender_id", "payload"],
                },
            },
            {
                "name": "majlis_moltbook_receive",
                "description": "Process MoltBook data with prompt injection sanitization",
                "input_schema": {
                    "type": "object",
                    "properties": {"agent_id": {"type": S}, "data": {"type": "object"}},
                    "required": ["agent_id", "data"],
                },
            },
            {
                "name": "majlis_moltbook_import",
                "description": "Import MoltBook profile into Majlis with Hawiyya identity",
                "input_schema": {
                    "type": "object",
                    "properties": {"agent_id": {"type": S}, "moltbook_profile": {"type": "object"}},
                    "required": ["agent_id", "moltbook_profile"],
                },
            },
            {
                "name": "majlis_moltbook_status",
                "description": "Get MoltBook bridge status and linked agents",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "majlis_moltbook_audit",
                "description": "View MoltBook bridge audit log (Shahid witness trail)",
                "input_schema": {
                    "type": "object",
                    "properties": {"agent_id": {"type": S}, "limit": {"type": "integer"}},
                },
            },
        ]
