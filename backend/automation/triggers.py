"""
Event Triggers
===============

Webhook receivers and event-driven automation.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger("mizan.triggers")


@dataclass
class WebhookTrigger:
    """A webhook trigger configuration"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    path: str = ""  # URL path for the webhook
    task_template: str = ""  # Task to execute when triggered
    agent_id: str | None = None
    enabled: bool = True
    secret: str | None = None  # Optional HMAC secret
    last_triggered: str | None = None
    trigger_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "task_template": self.task_template,
            "agent_id": self.agent_id,
            "enabled": self.enabled,
            "last_triggered": self.last_triggered,
            "trigger_count": self.trigger_count,
        }


class TriggerManager:
    """Manages webhook and event triggers"""

    def __init__(self):
        self.webhooks: dict[str, WebhookTrigger] = {}
        self._executor: Callable | None = None

    def set_executor(self, executor: Callable):
        self._executor = executor

    async def register_webhook(
        self, name: str, task_template: str, agent_id: str = None, secret: str = None
    ) -> WebhookTrigger:
        """Register a new webhook trigger"""
        webhook = WebhookTrigger(
            name=name,
            path=f"/webhooks/{uuid.uuid4().hex[:12]}",
            task_template=task_template,
            agent_id=agent_id,
            secret=secret,
        )
        self.webhooks[webhook.id] = webhook
        logger.info(f"[TRIGGER] Webhook registered: {name} at {webhook.path}")
        return webhook

    async def handle_webhook(self, webhook_id: str, payload: dict) -> dict:
        """Handle an incoming webhook"""
        webhook = self.webhooks.get(webhook_id)
        if not webhook or not webhook.enabled:
            return {"error": "Webhook not found or disabled"}

        # Build task from template + payload
        task = webhook.task_template
        for key, value in payload.items():
            task = task.replace(f"{{{key}}}", str(value))

        webhook.last_triggered = datetime.now(UTC).isoformat()
        webhook.trigger_count += 1

        # Execute
        if self._executor:
            try:
                result = await self._executor(task, webhook.agent_id)
                return {"success": True, "result": str(result)[:500]}
            except Exception as e:
                return {"error": str(e)}

        return {"error": "No executor configured"}

    def list_webhooks(self) -> list[dict]:
        return [w.to_dict() for w in self.webhooks.values()]
