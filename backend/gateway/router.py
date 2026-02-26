"""
Channel Router (مسار — Masar)
==============================

Routes incoming messages from all channels to the appropriate agent,
manages per-channel sessions, and handles response delivery.
"""

import asyncio
import logging
from typing import Callable, Dict, Optional

from gateway.channels.base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("mizan.router")

# Maximum message length per channel
CHANNEL_LIMITS = {
    "telegram": 4096,
    "discord": 2000,
    "whatsapp": 4096,
    "slack": 4000,
    "webchat": 10000,
}


class ChannelRouter:
    """
    Manages all channel adapters and routes messages to agents.
    """

    def __init__(self, memory=None):
        self._adapters: Dict[str, ChannelAdapter] = {}
        self._message_handler: Optional[Callable] = None
        self.memory = memory
        self._running = False

    def register(self, name: str, adapter: ChannelAdapter):
        """Register a channel adapter."""
        self._adapters[name] = adapter
        adapter.set_message_callback(
            lambda msg: self._on_message(name, msg)
        )
        logger.info(f"[ROUTER] Registered channel: {name}")

    def set_handler(self, handler: Callable):
        """
        Set the message handler function.
        handler(channel, sender_id, content, session_key) -> str
        """
        self._message_handler = handler

    async def start(self):
        """Start all registered channel adapters."""
        self._running = True
        for name, adapter in self._adapters.items():
            try:
                await adapter.connect()
                logger.info(f"[ROUTER] Channel started: {name}")
            except Exception as e:
                logger.error(f"[ROUTER] Failed to start {name}: {e}")

    async def stop(self):
        """Stop all channel adapters."""
        self._running = False
        for name, adapter in self._adapters.items():
            try:
                await adapter.disconnect()
                logger.info(f"[ROUTER] Channel stopped: {name}")
            except Exception as e:
                logger.error(f"[ROUTER] Error stopping {name}: {e}")

    async def start_channel(self, name: str) -> bool:
        """Start a specific channel."""
        adapter = self._adapters.get(name)
        if not adapter:
            return False
        try:
            await adapter.connect()
            logger.info(f"[ROUTER] Channel started: {name}")
            return True
        except Exception as e:
            logger.error(f"[ROUTER] Failed to start {name}: {e}")
            return False

    async def stop_channel(self, name: str) -> bool:
        """Stop a specific channel."""
        adapter = self._adapters.get(name)
        if not adapter:
            return False
        try:
            await adapter.disconnect()
            logger.info(f"[ROUTER] Channel stopped: {name}")
            return True
        except Exception as e:
            logger.error(f"[ROUTER] Error stopping {name}: {e}")
            return False

    def get_status(self) -> Dict:
        """Get status of all channels."""
        statuses = {}
        for name, adapter in self._adapters.items():
            statuses[name] = {
                "connected": adapter.is_connected,
                "config_keys": list(adapter.config.keys()),
            }
        return statuses

    def get_channel_status(self, name: str) -> Optional[Dict]:
        """Get status of a specific channel."""
        adapter = self._adapters.get(name)
        if not adapter:
            return None
        return {
            "name": name,
            "connected": adapter.is_connected,
            "config_keys": list(adapter.config.keys()),
        }

    async def send_to_channel(self, channel: str, recipient_id: str,
                               content: str) -> bool:
        """Send a message to a specific channel, handling chunking."""
        adapter = self._adapters.get(channel)
        if not adapter or not adapter.is_connected:
            return False

        max_len = CHANNEL_LIMITS.get(channel, 4096)
        chunks = _chunk_message(content, max_len)

        for chunk in chunks:
            try:
                await adapter.send_message(recipient_id, chunk)
            except Exception as e:
                logger.error(f"[ROUTER] Send failed on {channel}: {e}")
                return False
        return True

    async def _on_message(self, channel: str, message: IncomingMessage):
        """Handle incoming message from any channel."""
        if not self._message_handler:
            logger.warning("[ROUTER] No message handler set")
            return

        session_key = f"{channel}:{message.sender_id}"
        if message.group_id:
            session_key = f"{channel}:{message.group_id}:{message.sender_id}"

        logger.info(
            f"[ROUTER] Message from {channel}/{message.sender_name}: "
            f"{message.content[:50]}..."
        )

        try:
            response = await self._message_handler(
                channel=channel,
                sender_id=message.sender_id,
                content=message.content,
                session_key=session_key,
            )
            if response:
                await self.send_to_channel(
                    channel, message.sender_id, response
                )
        except Exception as e:
            logger.error(f"[ROUTER] Handler error: {e}")
            await self.send_to_channel(
                channel, message.sender_id,
                "I encountered an error processing your message. Please try again."
            )

    @property
    def channels(self) -> list:
        """List registered channel names."""
        return list(self._adapters.keys())


def _chunk_message(text: str, max_length: int) -> list:
    """Split a long message into chunks, breaking at paragraph or sentence boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to break at paragraph
        cut = remaining[:max_length].rfind("\n\n")
        if cut < max_length // 2:
            # Try sentence boundary
            cut = remaining[:max_length].rfind(". ")
            if cut < max_length // 2:
                # Try word boundary
                cut = remaining[:max_length].rfind(" ")
                if cut < max_length // 2:
                    cut = max_length - 1

        chunk = remaining[:cut + 1].rstrip()
        chunks.append(chunk)
        remaining = remaining[cut + 1:].lstrip()

    return chunks
