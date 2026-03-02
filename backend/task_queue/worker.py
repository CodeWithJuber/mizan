"""Async task worker that consumes from MizanTaskQueue."""

import asyncio
import logging
from typing import Awaitable, Callable

from task_queue.task_queue import QueuedTask

logger = logging.getLogger("mizan.queue.worker")


class TaskWorker:
    """Background worker that processes tasks from the queue."""

    def __init__(
        self,
        queue: "MizanTaskQueue",
        handler: Callable[[dict], Awaitable[dict]],
        max_concurrent: int = 3,
    ) -> None:
        self._queue = queue
        self._handler = handler
        self._max_concurrent = max_concurrent
        self._running: bool = False
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the worker loop. Blocks until stop() is called."""
        self._running = True
        logger.info("TaskWorker started (max_concurrent=%d)", self._max_concurrent)
        while self._running:
            task = await self._queue.wait_for_task(timeout=5.0)
            if task is None:
                continue
            await self._semaphore.acquire()
            async_task = asyncio.create_task(self._process(task))
            self._active_tasks.add(async_task)
            async_task.add_done_callback(self._active_tasks.discard)

    async def stop(self) -> None:
        """Stop the worker and wait for in-flight tasks to finish."""
        self._running = False
        if self._active_tasks:
            logger.info("Waiting for %d active tasks to complete", len(self._active_tasks))
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        logger.info("TaskWorker stopped")

    async def _process(self, task: QueuedTask) -> None:
        """Process a single task through the handler."""
        try:
            result = await self._handler(task.payload)
            await self._queue.complete(task.task_id, result)
            logger.debug("Task %s completed", task.task_id)
        except Exception as exc:
            logger.error("Task %s failed: %s", task.task_id, exc)
            await self._queue.fail(task.task_id, str(exc))
        finally:
            self._semaphore.release()

    @property
    def is_running(self) -> bool:
        """Whether the worker loop is active."""
        return self._running

    @property
    def active_count(self) -> int:
        """Number of tasks currently being processed."""
        return len(self._active_tasks)
