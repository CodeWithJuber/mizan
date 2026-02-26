"""
Request Logger Plugin — Monitor Everything
=============================================

A practical plugin that logs all tasks, chats, and events.
Useful for debugging, auditing, and understanding what MIZAN is doing.
"""

import json
import logging
from datetime import datetime

from core.plugins import PluginBase

logger = logging.getLogger("mizan.plugin.request_logger")


class Plugin(PluginBase):

    async def on_load(self):
        self._log_count = 0

        # Listen to lifecycle events
        self.on_event("task.started", self.log_task_start)
        self.on_event("task.completed", self.log_task_complete)
        self.on_event("task.failed", self.log_task_fail)

        # Hook into chat to log conversations
        self.add_hook("chat.input", self.log_chat_input)
        self.add_hook("chat.output", self.log_chat_output)

        logger.info("[RequestLogger] Plugin loaded — monitoring all events")

    async def on_unload(self):
        logger.info(f"[RequestLogger] Unloaded — logged {self._log_count} events")

    async def log_task_start(self, data):
        self._log_count += 1
        logger.info(f"[TASK START] Agent={data.get('agent', '?')} Task={data.get('task', '?')[:100]}")

    async def log_task_complete(self, data):
        self._log_count += 1
        duration = data.get("duration_ms", 0)
        logger.info(f"[TASK DONE] Agent={data.get('agent', '?')} Duration={duration:.0f}ms")

    async def log_task_fail(self, data):
        self._log_count += 1
        logger.warning(f"[TASK FAIL] Agent={data.get('agent', '?')} Error={data.get('error', '?')[:200]}")

    async def log_chat_input(self, data):
        self._log_count += 1
        content = data.get("content", "")[:100]
        logger.debug(f"[CHAT IN] {content}")
        return data  # Must return data for hooks

    async def log_chat_output(self, data):
        self._log_count += 1
        content = data.get("content", "")[:100]
        logger.debug(f"[CHAT OUT] {content}")
        return data
