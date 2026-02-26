"""
Webhook receiver and trigger system
=====================================

Receives external webhook calls, verifies their signatures, and dispatches
them to registered handler functions within the MIZAN automation pipeline.
"""

import json
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Callable, Dict, Optional

logger = logging.getLogger("mizan.webhooks")


class WebhookManager:
    """
    Central registry for webhook endpoints.

    Each webhook has an optional HMAC-SHA256 *secret* used to verify incoming
    payloads, and an optional async *handler* that is invoked on trigger.
    """

    def __init__(self):
        self._webhooks: Dict[str, dict] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(self, webhook_id: str, name: str, secret: str = "",
                 handler: Callable = None):
        """Register a webhook endpoint."""
        self._webhooks[webhook_id] = {
            "id": webhook_id,
            "name": name,
            "secret": secret,
            "created_at": datetime.utcnow().isoformat(),
            "trigger_count": 0,
            "last_triggered": None,
        }
        if handler:
            self._handlers[webhook_id] = handler
        logger.info(f"[WEBHOOK] Registered: {name} (id={webhook_id})")

    def verify_signature(self, webhook_id: str, payload: bytes,
                         signature: str) -> bool:
        """Verify webhook signature using HMAC-SHA256.

        If the webhook has no secret configured, verification is skipped and
        the call is considered trusted.

        Parameters
        ----------
        webhook_id:
            The registered webhook identifier.
        payload:
            Raw request body as bytes.
        signature:
            The ``X-Hub-Signature-256`` (or equivalent) header value,
            expected in the form ``sha256=<hex-digest>``.

        Returns
        -------
        bool
            ``True`` when the signature is valid (or no secret is set).
        """
        webhook = self._webhooks.get(webhook_id)
        if not webhook or not webhook.get("secret"):
            return True  # No secret = no verification

        expected = hmac.new(
            webhook["secret"].encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    async def trigger(self, webhook_id: str, payload: dict) -> dict:
        """Trigger a webhook.

        Increments the trigger count, records the timestamp, and invokes
        the registered handler (if any).

        Returns a result dict with either ``{"success": True, ...}`` or
        ``{"error": "..."}`` on failure.
        """
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            logger.warning(f"[WEBHOOK] Trigger failed — unknown id: {webhook_id}")
            return {"error": "Webhook not found"}

        webhook["trigger_count"] += 1
        webhook["last_triggered"] = datetime.utcnow().isoformat()

        handler = self._handlers.get(webhook_id)
        if handler:
            try:
                result = await handler(payload)
                logger.info(f"[WEBHOOK] Triggered: {webhook['name']}")
                return {"success": True, "result": result}
            except Exception as e:
                logger.error(
                    f"[WEBHOOK] Handler error for {webhook['name']}: {e}"
                )
                return {"error": str(e)}

        logger.info(
            f"[WEBHOOK] Triggered (no handler): {webhook['name']}"
        )
        return {"success": True, "message": "Webhook triggered (no handler)"}

    def list_webhooks(self) -> list:
        """Return metadata for all registered webhooks."""
        return list(self._webhooks.values())

    def get_webhook(self, webhook_id: str) -> Optional[dict]:
        """Look up a single webhook by id."""
        return self._webhooks.get(webhook_id)

    def delete(self, webhook_id: str) -> bool:
        """Remove a webhook and its handler. Returns True if it existed."""
        if webhook_id in self._webhooks:
            name = self._webhooks[webhook_id].get("name", webhook_id)
            del self._webhooks[webhook_id]
            self._handlers.pop(webhook_id, None)
            logger.info(f"[WEBHOOK] Deleted: {name}")
            return True
        return False
