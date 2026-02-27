"""
Telegram Channel (Bab Telegram)
================================

Telegram bot integration using python-telegram-bot.
"""

import logging

from .base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("mizan.channel.telegram")


class TelegramChannel(ChannelAdapter):
    """
    Telegram Bab — connects MIZAN to Telegram.

    Config:
    - bot_token: Telegram bot token from @BotFather
    """

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._app = None

    async def connect(self):
        """Start the Telegram bot"""
        bot_token = self.config.get("bot_token")
        if not bot_token:
            logger.error("[TELEGRAM] No bot_token configured")
            return

        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters

            self._app = ApplicationBuilder().token(bot_token).build()

            # Handle all text messages
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_telegram_message)
            )

            # Start polling in background
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()

            self.is_connected = True
            logger.info("[TELEGRAM] Bot connected and polling")

        except ImportError:
            logger.error(
                "[TELEGRAM] python-telegram-bot not installed. pip install python-telegram-bot"
            )
        except Exception as e:
            logger.error(f"[TELEGRAM] Connection failed: {e}")

    async def disconnect(self):
        """Stop the Telegram bot"""
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.error(f"[TELEGRAM] Disconnect error: {e}")
        self.is_connected = False

    async def send_message(self, recipient_id: str, content: str, attachments: list = None):
        """Send a message via Telegram"""
        if not self._app or not self.is_connected:
            return

        try:
            # Split long messages (Telegram limit: 4096 chars)
            chunks = [content[i : i + 4000] for i in range(0, len(content), 4000)]
            for chunk in chunks:
                await self._app.bot.send_message(
                    chat_id=int(recipient_id),
                    text=chunk,
                )
        except Exception as e:
            logger.error(f"[TELEGRAM] Send failed: {e}")

    async def _on_telegram_message(self, update, context):
        """Handle incoming Telegram message"""
        if not update.message or not update.message.text:
            return

        msg = IncomingMessage(
            channel="telegram",
            sender_id=str(update.message.from_user.id),
            sender_name=update.message.from_user.first_name or "",
            content=update.message.text,
            group_id=str(update.message.chat_id) if update.message.chat.type != "private" else None,
            metadata={
                "chat_type": update.message.chat.type,
                "message_id": update.message.message_id,
            },
        )

        await self._handle_incoming(msg)
