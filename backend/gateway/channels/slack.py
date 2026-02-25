"""
Slack Channel (Bab Slack)
==========================

Slack integration using slack-bolt.
"""

import asyncio
import logging
from typing import Dict, Optional

from .base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("mizan.channel.slack")


class SlackChannel(ChannelAdapter):
    """
    Slack Bab — connects MIZAN to Slack.

    Config:
    - bot_token: Slack bot OAuth token (xoxb-...)
    - app_token: Slack app-level token (xapp-...) for Socket Mode
    - signing_secret: Slack signing secret
    """

    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._app = None
        self._handler = None

    async def connect(self):
        """Start the Slack bot"""
        bot_token = self.config.get("bot_token")
        app_token = self.config.get("app_token")

        if not bot_token or not app_token:
            logger.error("[SLACK] bot_token and app_token required")
            return

        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

            self._app = AsyncApp(token=bot_token)

            @self._app.event("message")
            async def handle_message(event, say):
                # Ignore bot messages
                if event.get("bot_id"):
                    return

                msg = IncomingMessage(
                    channel="slack",
                    sender_id=event.get("user", ""),
                    sender_name=event.get("user", ""),
                    content=event.get("text", ""),
                    group_id=event.get("channel", ""),
                    metadata={
                        "ts": event.get("ts"),
                        "channel_type": event.get("channel_type"),
                    },
                )

                await self._handle_incoming(msg)

            @self._app.event("app_mention")
            async def handle_mention(event, say):
                msg = IncomingMessage(
                    channel="slack",
                    sender_id=event.get("user", ""),
                    content=event.get("text", ""),
                    group_id=event.get("channel", ""),
                    metadata={"type": "mention"},
                )

                await self._handle_incoming(msg)

            self._handler = AsyncSocketModeHandler(self._app, app_token)
            asyncio.create_task(self._handler.start_async())

            self.is_connected = True
            logger.info("[SLACK] Bot connected via Socket Mode")

        except ImportError:
            logger.error("[SLACK] slack-bolt not installed. pip install slack-bolt")
        except Exception as e:
            logger.error(f"[SLACK] Connection failed: {e}")

    async def disconnect(self):
        """Stop the Slack bot"""
        if self._handler:
            await self._handler.close_async()
        self.is_connected = False

    async def send_message(self, recipient_id: str, content: str,
                            attachments: list = None):
        """Send a message via Slack"""
        if not self._app or not self.is_connected:
            return

        try:
            await self._app.client.chat_postMessage(
                channel=recipient_id,
                text=content,
            )
        except Exception as e:
            logger.error(f"[SLACK] Send failed: {e}")
