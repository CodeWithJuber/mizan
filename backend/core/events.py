"""
Event Bus (Nida' - نداء — The Call)
=====================================

"And when the call (Nida') is made for prayer..." — Quran 62:9

A fully decoupled event system that lets any module communicate
without importing each other. This is the backbone of MIZAN's
plugin architecture.

HOW TO USE (for non-technical folks):
    1. Any module can "emit" an event (like shouting into a room)
    2. Any module can "listen" for events (like listening for your name)
    3. Modules never need to know about each other

EXAMPLE:
    from core.events import event_bus

    # Listen for an event
    @event_bus.on("agent.task.completed")
    async def my_handler(data):
        print(f"Agent finished: {data['agent_name']}")

    # Emit an event
    await event_bus.emit("agent.task.completed", {"agent_name": "Hafiz"})
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("mizan.events")


@dataclass
class Event:
    """A single event in the system."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    id: str = field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])


@dataclass
class EventHandler:
    """A registered event handler."""

    callback: Callable
    event_pattern: str
    priority: int = 0  # Higher = runs first
    source: str = ""  # Who registered this (plugin name, module, etc.)
    once: bool = False  # If True, auto-remove after first call


class EventBus:
    """
    Central event bus for MIZAN.

    Supports:
    - Exact match events: "agent.task.completed"
    - Wildcard patterns: "agent.*", "agent.task.*"
    - Priority ordering: Higher priority handlers run first
    - One-shot handlers: Run once then auto-remove
    - Async handlers: All handlers are async
    """

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[EventHandler] = []
        self._history: list[Event] = []
        self._max_history = 100

    def on(self, event_pattern: str, priority: int = 0, once: bool = False, source: str = ""):
        """
        Decorator to register an event handler.

        Usage:
            @event_bus.on("agent.task.completed")
            async def handle_completion(data):
                print(data)

            @event_bus.on("agent.*", priority=10)
            async def handle_all_agent_events(data):
                log(data)
        """

        def decorator(func):
            handler = EventHandler(
                callback=func,
                event_pattern=event_pattern,
                priority=priority,
                source=source,
                once=once,
            )
            if "*" in event_pattern:
                self._wildcard_handlers.append(handler)
                self._wildcard_handlers.sort(key=lambda h: h.priority, reverse=True)
            else:
                self._handlers[event_pattern].append(handler)
                self._handlers[event_pattern].sort(key=lambda h: h.priority, reverse=True)
            return func

        return decorator

    def add_listener(
        self,
        event_pattern: str,
        callback: Callable,
        priority: int = 0,
        source: str = "",
        once: bool = False,
    ):
        """Programmatic way to add a listener (non-decorator)."""
        handler = EventHandler(
            callback=callback,
            event_pattern=event_pattern,
            priority=priority,
            source=source,
            once=once,
        )
        if "*" in event_pattern:
            self._wildcard_handlers.append(handler)
            self._wildcard_handlers.sort(key=lambda h: h.priority, reverse=True)
        else:
            self._handlers[event_pattern].append(handler)
            self._handlers[event_pattern].sort(key=lambda h: h.priority, reverse=True)

    def remove_listener(self, event_pattern: str, callback: Callable):
        """Remove a specific listener."""
        if "*" in event_pattern:
            self._wildcard_handlers = [h for h in self._wildcard_handlers if h.callback != callback]
        else:
            self._handlers[event_pattern] = [
                h for h in self._handlers[event_pattern] if h.callback != callback
            ]

    def remove_all_from_source(self, source: str):
        """Remove all handlers registered by a specific source (e.g., a plugin)."""
        for pattern in list(self._handlers.keys()):
            self._handlers[pattern] = [h for h in self._handlers[pattern] if h.source != source]
        self._wildcard_handlers = [h for h in self._wildcard_handlers if h.source != source]

    async def emit(self, event_name: str, data: dict[str, Any] = None, source: str = ""):
        """
        Emit an event to all matching handlers.

        Returns list of handler results.
        """
        event = Event(name=event_name, data=data or {}, source=source)

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        results = []
        to_remove = []

        # Exact match handlers
        for handler in self._handlers.get(event_name, []):
            try:
                result = await handler.callback(event.data)
                results.append(result)
                if handler.once:
                    to_remove.append((event_name, handler))
            except Exception as e:
                logger.error(f"[NIDA] Handler error for '{event_name}': {e}")

        # Wildcard handlers
        for handler in self._wildcard_handlers:
            if self._matches_pattern(event_name, handler.event_pattern):
                try:
                    result = await handler.callback(event.data)
                    results.append(result)
                    if handler.once:
                        to_remove.append(("*", handler))
                except Exception as e:
                    logger.error(f"[NIDA] Wildcard handler error for '{event_name}': {e}")

        # Clean up one-shot handlers
        for pattern, handler in to_remove:
            if pattern == "*":
                self._wildcard_handlers.remove(handler)
            else:
                self._handlers[pattern].remove(handler)

        return results

    def _matches_pattern(self, event_name: str, pattern: str) -> bool:
        """Check if an event name matches a wildcard pattern."""
        if pattern == "*":
            return True

        pattern_parts = pattern.split(".")
        name_parts = event_name.split(".")

        for i, part in enumerate(pattern_parts):
            if part == "*":
                return True
            if i >= len(name_parts):
                return False
            if part != name_parts[i]:
                return False

        return len(pattern_parts) == len(name_parts)

    def get_history(self, event_name: str = None, limit: int = 50) -> list[dict]:
        """Get recent event history."""
        events = self._history
        if event_name:
            events = [e for e in events if e.name == event_name]
        return [
            {"name": e.name, "data": e.data, "source": e.source, "timestamp": e.timestamp}
            for e in events[-limit:]
        ]

    def list_handlers(self) -> list[dict]:
        """List all registered handlers (useful for debugging)."""
        result = []
        for pattern, handlers in self._handlers.items():
            for h in handlers:
                result.append(
                    {
                        "pattern": pattern,
                        "source": h.source,
                        "priority": h.priority,
                        "once": h.once,
                    }
                )
        for h in self._wildcard_handlers:
            result.append(
                {
                    "pattern": h.event_pattern,
                    "source": h.source,
                    "priority": h.priority,
                    "once": h.once,
                }
            )
        return result


# ── Global Event Bus Instance ──
# This is THE event bus for the entire application.
# Import it anywhere: from core.events import event_bus
event_bus = EventBus()


# ── Standard Event Names ──
# These are the events MIZAN emits. Plugins can listen to any of these.

EVENTS = {
    # Agent lifecycle
    "agent.created": "Fired when a new agent is created",
    "agent.deleted": "Fired when an agent is deleted",
    "agent.state.changed": "Fired when an agent's state changes",
    # Task lifecycle
    "task.started": "Fired when an agent starts a task",
    "task.completed": "Fired when a task completes successfully",
    "task.failed": "Fired when a task fails",
    "task.tool.called": "Fired when an agent calls a tool",
    "task.tool.result": "Fired when a tool returns a result",
    # Memory
    "memory.stored": "Fired when a new memory is stored",
    "memory.queried": "Fired when memory is queried",
    "memory.consolidated": "Fired when memories are consolidated",
    # Chat
    "chat.message.received": "Fired when a user sends a message",
    "chat.message.sent": "Fired when the system sends a response",
    # Provider
    "provider.switched": "Fired when the LLM provider is changed",
    "provider.health.checked": "Fired after a health check",
    # Plugin
    "plugin.loaded": "Fired when a plugin is loaded",
    "plugin.unloaded": "Fired when a plugin is unloaded",
    "plugin.error": "Fired when a plugin encounters an error",
    # System
    "system.startup": "Fired when MIZAN starts",
    "system.shutdown": "Fired when MIZAN is shutting down",
    "system.error": "Fired on system-level errors",
    # Channel
    "channel.connected": "Fired when a channel connects",
    "channel.disconnected": "Fired when a channel disconnects",
    "channel.message.incoming": "Fired when a message arrives from a channel",
    # Webhook
    "webhook.triggered": "Fired when a webhook is triggered",
    # Security
    "security.auth.success": "Fired on successful authentication",
    "security.auth.failure": "Fired on failed authentication",
    "security.rate.limited": "Fired when rate limit is hit",
}
