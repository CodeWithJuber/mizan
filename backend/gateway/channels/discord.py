"""
Discord Channel (Bab Discord)
===============================

Discord bot integration using discord.py.
"""

import asyncio
import logging

from .base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("mizan.channel.discord")


class DiscordChannel(ChannelAdapter):
    """
    Discord Bab — connects MIZAN to Discord.

    Config:
    - bot_token: Discord bot token
    - guild_ids: Optional list of guild IDs to operate in
    """

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._client = None
        self._task = None

    async def connect(self):
        """Start the Discord bot"""
        bot_token = self.config.get("bot_token")
        if not bot_token:
            logger.error("[DISCORD] No bot_token configured")
            return

        try:
            import discord

            intents = discord.Intents.default()
            intents.message_content = True

            self._client = discord.Client(intents=intents)

            @self._client.event
            async def on_ready():
                self.is_connected = True
                logger.info(f"[DISCORD] Bot connected as {self._client.user}")

            @self._client.event
            async def on_message(message):
                # Ignore own messages
                if message.author == self._client.user:
                    return

                # Check if bot is mentioned or in DM
                is_dm = isinstance(message.channel, discord.DMChannel)
                is_mentioned = self._client.user in message.mentions

                if is_dm or is_mentioned:
                    content = message.content
                    # Remove mention from content
                    if is_mentioned:
                        content = content.replace(f"<@{self._client.user.id}>", "").strip()

                    msg = IncomingMessage(
                        channel="discord",
                        sender_id=str(message.author.id),
                        sender_name=message.author.display_name,
                        content=content,
                        group_id=str(message.guild.id) if message.guild else None,
                        metadata={
                            "channel_id": str(message.channel.id),
                            "is_dm": is_dm,
                        },
                    )

                    await self._handle_incoming(msg)

            # Run bot in background
            self._task = asyncio.create_task(self._client.start(bot_token))
            logger.info("[DISCORD] Bot starting...")

        except ImportError:
            logger.error("[DISCORD] discord.py not installed. pip install discord.py")
        except Exception as e:
            logger.error(f"[DISCORD] Connection failed: {e}")

    async def disconnect(self):
        """Stop the Discord bot"""
        if self._client:
            await self._client.close()
        if self._task:
            self._task.cancel()
        self.is_connected = False

    async def send_message(self, recipient_id: str, content: str, attachments: list = None):
        """Send a message via Discord DM"""
        if not self._client or not self.is_connected:
            return

        try:
            user = await self._client.fetch_user(int(recipient_id))
            dm = await user.create_dm()

            # Split long messages (Discord limit: 2000 chars)
            chunks = [content[i : i + 1900] for i in range(0, len(content), 1900)]
            for chunk in chunks:
                await dm.send(chunk)
        except Exception as e:
            logger.error(f"[DISCORD] Send failed: {e}")
