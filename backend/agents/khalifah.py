"""
Khalifah Agent (خليفة - Steward/Orchestrator)
===============================================

"Indeed, I will make upon the earth a Khalifah (steward)." — Quran 2:30

The Khalifah is the 24/7 main orchestrator: it receives every user message,
classifies intent, routes to the task queue or streams a direct response,
records all interactions for the Ruh Model, and emits visible thinking steps
throughout.

Design principles:
- Standalone orchestrator; does not subclass BaseAgent to avoid the full QCA
  bootstrap cost on every import.
- All I/O is async.
- Immutable conversation context (append-only list, never mutated in place).
- Errors are surfaced explicitly — no silent swallowing.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from cognitive.thinking_stream import ThinkingPhase, ThinkingStep, ThinkingStream
from learner.ruh_learner import RuhLearner
from providers import BaseLLMProvider, create_provider, get_default_model

from task_queue.priorities import TaskPriority
from task_queue.task_queue import MizanTaskQueue

logger = logging.getLogger(__name__)

# Keywords that signal the user wants background work rather than conversation.
_TASK_KEYWORDS: frozenset[str] = frozenset(
    {
        "run",
        "execute",
        "schedule",
        "process",
        "analyse",
        "analyze",
        "generate",
        "build",
        "create",
        "search",
        "fetch",
        "download",
        "upload",
        "train",
        "calculate",
        "compute",
        "scrape",
    }
)

_QUESTION_STARTERS: frozenset[str] = frozenset(
    {"what", "why", "how", "when", "where", "who", "which", "is", "are", "does", "do", "can", "could", "would", "should"}
)

_SYSTEM_PROMPT = (
    "You are Mizan (ميزان — the Balance), a thoughtful AI assistant grounded "
    "in wisdom and excellence (ihsan). Respond clearly, concisely, and helpfully."
)
_MAX_CONTEXT_MESSAGES = 20  # Rolling window; oldest messages are evicted first.
_DEFAULT_MAX_TOKENS = 2048


class KhalifahAgent:
    """24/7 orchestrator that routes messages, manages tasks, and streams responses."""

    def __init__(self, db_path: str = "data/mizan.db") -> None:
        self._db_path = db_path
        self._task_queue = MizanTaskQueue(db_path=db_path)
        self._learner = RuhLearner(db_path=db_path)
        self._thinking = ThinkingStream()
        # client_id → list of {"role": str, "content": str}
        self._conversations: dict[str, list[dict[str, str]]] = {}
        self._initialized = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize DB connections for the task queue and learner."""
        if self._initialized:
            return
        await asyncio.gather(
            self._task_queue.initialize(),
            self._learner.initialize(),
        )
        self._initialized = True
        logger.info("KhalifahAgent initialized (db_path=%s)", self._db_path)

    async def shutdown(self) -> None:
        """Flush any pending state and release resources."""
        logger.info("KhalifahAgent shutting down")
        self._initialized = False

    # ── Main entry point ──────────────────────────────────────────────────────

    async def process_message(
        self,
        message: str,
        client_id: str,
        on_thinking: Callable[[str, ThinkingStep], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Route a user message and stream response chunks.

        Yields str chunks suitable for direct WebSocket relay.
        on_thinking receives (request_id, ThinkingStep) for each cognitive step.
        """
        request_id = str(uuid.uuid4())
        trace = self._thinking.create_trace(request_id)

        if on_thinking:
            self._thinking.on_step(on_thinking)

        # 1. PERCEPTION — log that input arrived
        self._thinking.add_step(
            request_id,
            ThinkingPhase.PERCEPTION,
            f"Received message from {client_id}: {message[:120]}",
            confidence=0.95,
            metadata={"client_id": client_id, "length": len(message)},
        )

        # 2. Classify intent
        intent = await self._classify_intent(message)
        self._thinking.add_step(
            request_id,
            ThinkingPhase.COMPREHENSION,
            f"Intent classified as '{intent}'",
            confidence=0.8,
            metadata={"intent": intent},
        )

        response_chunks: list[str] = []

        if intent == "task":
            task_id = await self._enqueue_task(message, client_id)
            reply = (
                f"Task accepted (id: {task_id}). "
                "I'll process it in the background and notify you when complete."
            )
            yield reply
            response_chunks = [reply]
        else:
            context = self._get_context(client_id)
            async for chunk in self._generate_response(message, context):
                yield chunk
                response_chunks.append(chunk)

        # 3. Update conversation context (immutable append)
        full_response = "".join(response_chunks)
        self._conversations[client_id] = _append_turns(
            self._conversations.get(client_id, []),
            message,
            full_response,
        )

        # 4. REFLECTION
        self._thinking.add_step(
            request_id,
            ThinkingPhase.REFLECTION,
            f"Response delivered ({len(full_response)} chars). Intent was '{intent}'.",
            confidence=0.9,
        )
        self._thinking.complete(request_id)

        # 5. Capture for Ruh Learner (fire-and-forget; never blocks streaming)
        asyncio.create_task(
            self._capture_interaction(message, full_response, client_id)
        )

    # ── Intent classification ─────────────────────────────────────────────────

    async def _classify_intent(self, message: str) -> str:
        """Return 'chat', 'task', or 'question' using keyword heuristics."""
        normalised = message.lower().strip()
        first_word = normalised.split()[0] if normalised.split() else ""

        if first_word in _TASK_KEYWORDS:
            return "task"

        if first_word in _QUESTION_STARTERS or normalised.endswith("?"):
            return "question"

        return "chat"

    # ── Task queue ────────────────────────────────────────────────────────────

    async def _enqueue_task(self, message: str, client_id: str) -> str:
        """Persist task to the priority queue and return its task_id."""
        task_id = await self._task_queue.enqueue(
            payload={"message": message, "client_id": client_id, "enqueued_at": time.time()},
            priority=TaskPriority.HAJAH,
            agent_id=client_id,
        )
        logger.info("Enqueued task %s for client %s", task_id, client_id)
        return task_id

    async def get_active_tasks(self, client_id: str) -> list[dict[str, Any]]:
        """Return pending and running tasks for a given client."""
        all_tasks = await self._task_queue.list_tasks()
        return [
            {
                "task_id": task.task_id,
                "status": task.status,
                "priority": task.priority,
                "created_at": task.created_at,
                "payload": task.payload,
            }
            for task in all_tasks
            if task.agent_id == client_id and task.status in ("pending", "running")
        ]

    # ── Response generation ───────────────────────────────────────────────────

    async def _generate_response(
        self,
        message: str,
        context: list[dict[str, str]],
    ) -> AsyncGenerator[str, None]:
        """Call the configured LLM provider and yield text chunks."""
        provider = _build_provider()
        if provider is None:
            error_msg = "No LLM provider available. Please configure an API key."
            logger.error(error_msg)
            yield error_msg
            return

        model = get_default_model(provider.provider_name)
        messages = [*context, {"role": "user", "content": message}]

        try:
            with provider.stream(
                model=model,
                max_tokens=_DEFAULT_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                for chunk in stream.text_stream:
                    yield chunk
        except Exception as exc:
            logger.error("Streaming error from provider %s: %s", provider.provider_name, exc)
            yield f"[Error generating response: {exc}]"

    # ── Learner capture ───────────────────────────────────────────────────────

    async def _capture_interaction(
        self,
        prompt: str,
        response: str,
        client_id: str,
    ) -> None:
        """Record the interaction for Ruh Model training; swallow non-critical errors."""
        provider = _build_provider()
        provider_name = provider.provider_name if provider else "unknown"
        model = get_default_model(provider_name) if provider else "unknown"

        try:
            await self._learner.capture(
                prompt=prompt,
                response=response,
                provider=provider_name,
                model=model,
                metadata={"client_id": client_id},
            )
        except Exception as exc:
            # Learning failures must never break the main response flow.
            logger.warning("RuhLearner capture failed: %s", exc)

    # ── Context helpers ───────────────────────────────────────────────────────

    def _get_context(self, client_id: str) -> list[dict[str, str]]:
        """Return the rolling conversation context for a client."""
        return self._conversations.get(client_id, [])


# ── Module-level helpers (pure functions, no side effects) ─────────────────


def _append_turns(
    history: list[dict[str, str]],
    user_message: str,
    assistant_reply: str,
) -> list[dict[str, str]]:
    """Return a new history list with the latest turns appended and window applied."""
    updated = [
        *history,
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_reply},
    ]
    # Keep only the most recent N messages (pairs counted individually)
    if len(updated) > _MAX_CONTEXT_MESSAGES:
        updated = updated[-_MAX_CONTEXT_MESSAGES:]
    return updated


def _build_provider() -> BaseLLMProvider | None:
    """Instantiate the default provider; returns None if misconfigured."""
    return create_provider()
