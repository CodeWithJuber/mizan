"""
Bab (بَاب) — The Gateway
===========================

"Enter the gate with prostration" — Quran 2:58

Persistent asyncio gateway managing all communication channels.
Routes messages through the Quranic processing pipeline:
Bab (Gate) → Sama' (Perception) → Fikr (Processing) → Amal (Action) → Bab (Response)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from .channels.base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("mizan.gateway")


@dataclass
class GatewayConfig:
    """Gateway configuration"""
    enabled_channels: List[str] = field(default_factory=lambda: ["webchat"])
    max_sessions_per_channel: int = 1000
    session_timeout_hours: int = 24
    require_verification: bool = True
    verification_timeout_minutes: int = 5


@dataclass
class GatewaySession:
    """Session for a user on a channel"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = ""
    channel_user_id: str = ""
    verified: bool = False
    verification_code: Optional[str] = None
    trust_level: float = 0.0  # 0-1, Amanah trust score
    history: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "channel": self.channel,
            "channel_user_id": self.channel_user_id,
            "verified": self.verified,
            "trust_level": self.trust_level,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "agent_id": self.agent_id,
            "history_length": len(self.history),
        }


class MessageRouter:
    """
    Routes incoming messages to the appropriate agent.
    Uses content classification and Mizan load balancing.
    """

    # Intent keywords for routing
    INTENT_MAP = {
        "katib": ["code", "script", "program", "function", "test", "debug", "git", "deploy"],
        "mubashir": ["search", "browse", "find", "web", "url", "website", "link"],
        "mundhir": ["research", "analyze", "report", "study", "review", "compare"],
        "rasul": ["email", "message", "notify", "send", "webhook"],
    }

    def classify_intent(self, content: str) -> str:
        """Classify message intent to determine best agent role"""
        content_lower = content.lower()
        for role, keywords in self.INTENT_MAP.items():
            if any(kw in content_lower for kw in keywords):
                return role
        return "wakil"  # Default general agent

    def select_agent(self, intent: str, agents: Dict, balancer=None) -> Optional[str]:
        """Select best agent for the intent"""
        # Try to find agent matching the role
        for agent_id, agent in agents.items():
            if agent.role == intent:
                return agent_id

        # Fallback to load balancer
        if balancer:
            return balancer.select_agent()

        # Fallback to first available
        if agents:
            return list(agents.keys())[0]

        return None


class MizanGateway:
    """
    The central gateway managing all communication channels.

    Handles:
    - Channel lifecycle (connect/disconnect)
    - Message routing to agents
    - Session management per channel/user
    - DM verification (Amanah trust model)
    """

    def __init__(self, config: GatewayConfig = None, wali=None, memory=None):
        self.config = config or GatewayConfig()
        self.wali = wali
        self.memory = memory

        self.channels: Dict[str, ChannelAdapter] = {}
        self.sessions: Dict[str, GatewaySession] = {}
        self.router = MessageRouter()
        self._running = False
        self._message_handler: Optional[Callable] = None

    def register_channel(self, name: str, channel: ChannelAdapter):
        """Register a channel adapter"""
        self.channels[name] = channel
        logger.info(f"[BAB] Channel registered: {name}")

    def set_message_handler(self, handler: Callable):
        """Set the handler for incoming messages"""
        self._message_handler = handler

    async def start(self):
        """Start all registered channels"""
        self._running = True
        logger.info(f"[BAB] Gateway starting with {len(self.channels)} channels...")

        for name, channel in self.channels.items():
            if name in self.config.enabled_channels:
                try:
                    channel.set_message_callback(self._on_message)
                    await channel.connect()
                    logger.info(f"[BAB] Channel connected: {name}")
                except Exception as e:
                    logger.error(f"[BAB] Channel {name} failed to connect: {e}")

        logger.info("[BAB] Gateway started")

    async def stop(self):
        """Stop all channels"""
        self._running = False
        for name, channel in self.channels.items():
            try:
                await channel.disconnect()
                logger.info(f"[BAB] Channel disconnected: {name}")
            except Exception as e:
                logger.error(f"[BAB] Channel {name} disconnect error: {e}")

        logger.info("[BAB] Gateway stopped")

    async def _on_message(self, message: IncomingMessage):
        """Handle an incoming message from any channel"""
        # Get or create session
        session_key = f"{message.channel}:{message.sender_id}"
        session = self.sessions.get(session_key)

        if not session:
            session = GatewaySession(
                channel=message.channel,
                channel_user_id=message.sender_id,
            )
            self.sessions[session_key] = session

            # New user verification if required
            if self.config.require_verification and not session.verified:
                code = str(uuid.uuid4())[:6].upper()
                session.verification_code = code
                logger.info(f"[BAB] New user {message.sender_id} on {message.channel}, verification: {code}")

                # Send verification response through channel
                channel = self.channels.get(message.channel)
                if channel:
                    await channel.send_message(
                        message.sender_id,
                        f"Welcome to MIZAN (ميزان). Your verification code is: {code}\n"
                        f"Reply with this code to activate your session.",
                    )
                return

        # Check if this is a verification response
        if not session.verified and session.verification_code:
            if message.content.strip().upper() == session.verification_code:
                session.verified = True
                session.trust_level = 0.5
                session.verification_code = None

                channel = self.channels.get(message.channel)
                if channel:
                    await channel.send_message(
                        message.sender_id,
                        "بسم الله — Verified! You are now connected to MIZAN.\n"
                        "How can I help you today?",
                    )
                return
            else:
                channel = self.channels.get(message.channel)
                if channel:
                    await channel.send_message(
                        message.sender_id,
                        "Invalid verification code. Please try again.",
                    )
                return

        # Update session
        session.last_active = datetime.now(timezone.utc).isoformat()
        session.history.append({
            "role": "user",
            "content": message.content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Audit log
        if self.wali:
            self.wali.audit.log("channel_message", {
                "channel": message.channel,
                "sender": message.sender_id,
                "length": len(message.content),
            })

        # Forward to message handler
        if self._message_handler:
            response = await self._message_handler(message, session)

            # Send response back through channel
            channel = self.channels.get(message.channel)
            if channel and response:
                await channel.send_message(message.sender_id, response)

                session.history.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # Increase trust over time
                session.trust_level = min(1.0, session.trust_level + 0.01)

    def get_sessions(self, channel: str = None) -> List[Dict]:
        """Get active sessions, optionally filtered by channel"""
        sessions = self.sessions.values()
        if channel:
            sessions = [s for s in sessions if s.channel == channel]
        return [s.to_dict() for s in sessions]

    def get_channel_status(self) -> List[Dict]:
        """Get status of all channels"""
        return [
            {
                "name": name,
                "enabled": name in self.config.enabled_channels,
                "connected": channel.is_connected,
                "type": channel.__class__.__name__,
            }
            for name, channel in self.channels.items()
        ]
