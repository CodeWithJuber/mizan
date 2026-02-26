"""
Hook System (Ta'liq - تعليق — Attachment/Hook)
=================================================

"And hold firmly to the rope of Allah" — Quran 3:103

Hooks let plugins modify data as it flows through the system.
Unlike events (fire-and-forget), hooks pass data through a chain
of handlers and return the (possibly modified) result.

HOW TO USE (for non-technical folks):
    Think of hooks like a factory assembly line:
    1. Data enters the line
    2. Each worker (hook handler) can inspect and modify it
    3. The final modified data comes out the other end

EXAMPLE:
    from core.hooks import hook_registry

    # Register a hook that modifies the system prompt
    @hook_registry.register("agent.system_prompt")
    async def add_custom_instructions(data):
        data["prompt"] += "\\nAlways be polite."
        return data

    # Apply hooks somewhere in the system
    result = await hook_registry.apply("agent.system_prompt", {"prompt": "You are MIZAN."})
    # result["prompt"] == "You are MIZAN.\\nAlways be polite."
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("mizan.hooks")


@dataclass
class HookHandler:
    """A registered hook handler."""
    callback: Callable
    hook_name: str
    priority: int = 0      # Higher = runs first
    source: str = ""       # Who registered (plugin name)


class HookRegistry:
    """
    Central hook registry for MIZAN.

    Hooks are different from events:
    - Events: fire-and-forget notifications
    - Hooks: data transformation pipeline (each handler modifies and returns data)

    Supported hooks:
    - agent.system_prompt     — Modify the system prompt before sending to LLM
    - agent.messages          — Modify message history before sending to LLM
    - agent.response          — Modify agent response before returning to user
    - agent.tool.before       — Modify tool parameters before execution
    - agent.tool.after        — Modify tool results after execution
    - chat.input              — Modify user input before processing
    - chat.output             — Modify output before sending to user
    - api.request             — Modify incoming API request data
    - api.response            — Modify outgoing API response data
    - memory.before_store     — Modify memory before storing
    - memory.after_query      — Modify query results before returning
    - provider.before_call    — Modify LLM call parameters
    - provider.after_call     — Modify LLM response
    """

    def __init__(self):
        self._hooks: Dict[str, List[HookHandler]] = defaultdict(list)

    def register(self, hook_name: str, priority: int = 0, source: str = ""):
        """
        Decorator to register a hook handler.

        Usage:
            @hook_registry.register("chat.input")
            async def modify_input(data):
                data["content"] = data["content"].strip()
                return data
        """
        def decorator(func):
            handler = HookHandler(
                callback=func,
                hook_name=hook_name,
                priority=priority,
                source=source,
            )
            self._hooks[hook_name].append(handler)
            self._hooks[hook_name].sort(key=lambda h: h.priority, reverse=True)
            return func
        return decorator

    def add_hook(self, hook_name: str, callback: Callable,
                 priority: int = 0, source: str = ""):
        """Programmatic way to add a hook handler."""
        handler = HookHandler(
            callback=callback,
            hook_name=hook_name,
            priority=priority,
            source=source,
        )
        self._hooks[hook_name].append(handler)
        self._hooks[hook_name].sort(key=lambda h: h.priority, reverse=True)

    def remove_hook(self, hook_name: str, callback: Callable):
        """Remove a specific hook handler."""
        self._hooks[hook_name] = [
            h for h in self._hooks[hook_name] if h.callback != callback
        ]

    def remove_all_from_source(self, source: str):
        """Remove all hooks registered by a specific source (e.g., a plugin being unloaded)."""
        for name in list(self._hooks.keys()):
            self._hooks[name] = [
                h for h in self._hooks[name] if h.source != source
            ]

    async def apply(self, hook_name: str, data: Any) -> Any:
        """
        Apply all handlers for a hook in priority order.

        Each handler receives the data and must return it (possibly modified).
        The output of one handler becomes the input of the next.
        """
        handlers = self._hooks.get(hook_name, [])
        if not handlers:
            return data

        for handler in handlers:
            try:
                result = await handler.callback(data)
                if result is not None:
                    data = result
            except Exception as e:
                logger.error(f"[TA'LIQ] Hook error in '{hook_name}' from '{handler.source}': {e}")

        return data

    def has_hooks(self, hook_name: str) -> bool:
        """Check if any handlers are registered for a hook."""
        return bool(self._hooks.get(hook_name))

    def list_hooks(self) -> List[Dict]:
        """List all registered hooks."""
        result = []
        for name, handlers in self._hooks.items():
            for h in handlers:
                result.append({
                    "hook": name,
                    "source": h.source,
                    "priority": h.priority,
                })
        return result


# ── Global Hook Registry ──
hook_registry = HookRegistry()


# ── Standard Hook Points ──
HOOKS = {
    # Agent hooks
    "agent.system_prompt": "Modify the system prompt before LLM call",
    "agent.messages": "Modify message history before LLM call",
    "agent.response": "Modify agent response before returning",
    "agent.tool.before": "Modify tool parameters before execution",
    "agent.tool.after": "Modify tool results after execution",

    # Chat hooks
    "chat.input": "Modify user input before processing",
    "chat.output": "Modify output before sending to user",

    # API hooks
    "api.request": "Modify incoming API request data",
    "api.response": "Modify outgoing API response data",

    # Memory hooks
    "memory.before_store": "Modify memory data before storing",
    "memory.after_query": "Modify query results before returning",

    # Provider hooks
    "provider.before_call": "Modify LLM call parameters",
    "provider.after_call": "Modify LLM response",
}
