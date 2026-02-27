"""
WhatsApp Channel (Bab WhatsApp)
================================

WhatsApp integration via WhatsApp Business API / Cloud API.
"""

import logging

import httpx

from .base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("mizan.channel.whatsapp")


class WhatsAppChannel(ChannelAdapter):
    """
    WhatsApp Bab — connects MIZAN to WhatsApp.

    Uses Meta's WhatsApp Cloud API.

    Config:
    - access_token: WhatsApp Cloud API access token
    - phone_number_id: WhatsApp business phone number ID
    - verify_token: Webhook verification token
    - api_version: API version (default: v18.0)
    """

    BASE_URL = "https://graph.facebook.com"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._webhook_callback = None

    async def connect(self):
        """Mark as connected — actual connection is via webhook"""
        access_token = self.config.get("access_token")
        phone_id = self.config.get("phone_number_id")

        if not access_token or not phone_id:
            logger.error("[WHATSAPP] access_token and phone_number_id required")
            return

        self.is_connected = True
        logger.info("[WHATSAPP] Channel ready (webhook mode)")

    async def disconnect(self):
        """Disconnect"""
        self.is_connected = False

    async def send_message(self, recipient_id: str, content: str, attachments: list = None):
        """Send a WhatsApp message"""
        access_token = self.config.get("access_token")
        phone_id = self.config.get("phone_number_id")
        api_version = self.config.get("api_version", "v18.0")

        if not access_token or not phone_id:
            return

        url = f"{self.BASE_URL}/{api_version}/{phone_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": content[:4096]},  # WhatsApp limit
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )
                if response.status_code != 200:
                    logger.error(f"[WHATSAPP] Send failed: {response.text}")
        except Exception as e:
            logger.error(f"[WHATSAPP] Send failed: {e}")

    async def handle_webhook(self, payload: dict) -> IncomingMessage | None:
        """
        Handle incoming WhatsApp webhook.
        Called from the API webhook endpoint.
        Returns IncomingMessage if it's a valid user message.
        """
        try:
            entry = payload.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])

            if not messages:
                return None

            wa_msg = messages[0]
            if wa_msg.get("type") != "text":
                return None

            contact = value.get("contacts", [{}])[0]

            msg = IncomingMessage(
                channel="whatsapp",
                sender_id=wa_msg.get("from", ""),
                sender_name=contact.get("profile", {}).get("name", ""),
                content=wa_msg.get("text", {}).get("body", ""),
                metadata={
                    "message_id": wa_msg.get("id"),
                    "timestamp": wa_msg.get("timestamp"),
                },
            )

            await self._handle_incoming(msg)
            return msg

        except Exception as e:
            logger.error(f"[WHATSAPP] Webhook parse error: {e}")
            return None

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Verify WhatsApp webhook subscription"""
        verify_token = self.config.get("verify_token", "")
        if mode == "subscribe" and token == verify_token:
            return challenge
        return None
