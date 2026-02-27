"""
Base Channel Adapter
=====================

Every channel is a Bab (بَاب — Gate) into MIZAN.
Each adapter converts platform-specific messages to/from the unified format.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IncomingMessage:
    """Unified incoming message from any channel"""
    channel: str = ""          # Channel name (telegram, discord, etc.)
    sender_id: str = ""        # Platform-specific user ID
    sender_name: str = ""      # Display name
    content: str = ""          # Text content
    group_id: Optional[str] = None  # Group/channel ID if applicable
    reply_to: Optional[str] = None  # ID of message being replied to
    attachments: list = field(default_factory=list)  # File attachments
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChannelAdapter(ABC):
    """
    Base class for all channel adapters.

    Each adapter must implement:
    - connect(): Establish connection to the platform
    - disconnect(): Clean disconnect
    - send_message(): Send a message to a user
    - set_message_callback(): Set handler for incoming messages
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.is_connected = False
        self._message_callback: Optional[Callable] = None

    def set_message_callback(self, callback: Callable):
        """Set the callback for incoming messages"""
        self._message_callback = callback

    @abstractmethod
    async def connect(self):
        """Connect to the platform"""
        pass

    @abstractmethod
    async def disconnect(self):
        """Disconnect from the platform"""
        pass

    @abstractmethod
    async def send_message(self, recipient_id: str, content: str,
                            attachments: list = None):
        """Send a message to a recipient"""
        pass

    async def _handle_incoming(self, message: IncomingMessage):
        """Forward incoming message to callback"""
        if self._message_callback:
            await self._message_callback(message)
