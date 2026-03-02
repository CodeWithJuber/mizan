"""Persistent priority task queue backed by aiosqlite."""

import asyncio
import heapq
import json
import time
import uuid
from dataclasses import dataclass, field

import aiosqlite

from task_queue.priorities import TaskPriority

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        priority INTEGER NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        agent_id TEXT,
        result TEXT,
        error TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
"""

_RESTORE_SQL = (
    "SELECT task_id, priority, payload, status, agent_id, created_at "
    "FROM tasks WHERE status = 'pending' ORDER BY priority, created_at"
)

_INSERT_SQL = (
    "INSERT OR REPLACE INTO tasks "
    "(task_id, priority, payload, status, agent_id, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_UPDATE_SQL = (
    "UPDATE tasks SET status = ?, result = ?, error = ?, updated_at = ? "
    "WHERE task_id = ?"
)


@dataclass(order=True)
class QueuedTask:
    """A task in the priority queue."""

    priority: int
    created_at: float = field(compare=True)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    payload: dict = field(default_factory=dict, compare=False)
    status: str = field(default="pending", compare=False)
    agent_id: str | None = field(default=None, compare=False)
    result: dict | None = field(default=None, compare=False)
    error: str | None = field(default=None, compare=False)


class MizanTaskQueue:
    """Priority task queue with aiosqlite persistence."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._heap: list[QueuedTask] = []
        self._lock = asyncio.Lock()
        self._tasks: dict[str, QueuedTask] = {}
        self._event = asyncio.Event()

    async def initialize(self) -> None:
        """Create tables and restore pending tasks from DB."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE_SQL)
            await db.commit()
            await self._restore_pending(db)

    async def _restore_pending(self, db: aiosqlite.Connection) -> None:
        """Load pending tasks from the database into the in-memory heap."""
        async with db.execute(_RESTORE_SQL) as cursor:
            async for row in cursor:
                task = QueuedTask(
                    priority=row[1],
                    created_at=row[5],
                    task_id=row[0],
                    payload=json.loads(row[2]),
                    status=row[3],
                    agent_id=row[4],
                )
                heapq.heappush(self._heap, task)
                self._tasks[task.task_id] = task

    async def enqueue(
        self,
        payload: dict,
        priority: int = TaskPriority.HAJAH,
        agent_id: str | None = None,
    ) -> str:
        """Add a task to the queue. Returns task_id."""
        task = QueuedTask(
            priority=priority,
            created_at=time.time(),
            payload=payload,
            agent_id=agent_id,
        )

        async with self._lock:
            heapq.heappush(self._heap, task)
            self._tasks[task.task_id] = task

        await self._persist_task(task)
        self._event.set()
        return task.task_id

    async def dequeue(self) -> QueuedTask | None:
        """Pop highest priority task. Returns None if empty."""
        async with self._lock:
            while self._heap:
                task = heapq.heappop(self._heap)
                if task.status == "pending":
                    task.status = "running"
                    await self._update_status(task.task_id, "running")
                    return task
            self._event.clear()
        return None

    async def wait_for_task(self, timeout: float = 30.0) -> QueuedTask | None:
        """Wait for next available task with timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return await self.dequeue()

    async def complete(self, task_id: str, result: dict) -> None:
        """Mark task as complete with result."""
        if task_id in self._tasks:
            self._tasks[task_id].status = "complete"
            self._tasks[task_id].result = result
        await self._update_status(task_id, "complete", result=result)

    async def fail(self, task_id: str, error: str) -> None:
        """Mark task as failed with error message."""
        if task_id in self._tasks:
            self._tasks[task_id].status = "failed"
            self._tasks[task_id].error = error
        await self._update_status(task_id, "failed", error=error)

    async def get_task(self, task_id: str) -> QueuedTask | None:
        """Get task by ID."""
        return self._tasks.get(task_id)

    async def list_tasks(self, status: str | None = None) -> list[QueuedTask]:
        """List all tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: (t.priority, t.created_at))

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending task. Returns True if cancelled."""
        task = self._tasks.get(task_id)
        if task and task.status == "pending":
            task.status = "cancelled"
            await self._update_status(task_id, "cancelled")
            return True
        return False

    @property
    def pending_count(self) -> int:
        """Number of tasks still pending."""
        return sum(1 for t in self._tasks.values() if t.status == "pending")

    async def _persist_task(self, task: QueuedTask) -> None:
        """Insert or replace a task in the database."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                _INSERT_SQL,
                (
                    task.task_id,
                    task.priority,
                    json.dumps(task.payload),
                    task.status,
                    task.agent_id,
                    task.created_at,
                    time.time(),
                ),
            )
            await db.commit()

    async def _update_status(
        self,
        task_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Update task status in the database."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                _UPDATE_SQL,
                (
                    status,
                    json.dumps(result) if result else None,
                    error,
                    time.time(),
                    task_id,
                ),
            )
            await db.commit()
