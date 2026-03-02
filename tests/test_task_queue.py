"""Tests for the MizanTaskQueue persistent priority task queue."""

import sys
from pathlib import Path

# Ensure backend/ is on sys.path so task_queue package resolves
_backend_dir = str(Path(__file__).parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from task_queue.priorities import TaskPriority  # noqa: E402
from task_queue.task_queue import MizanTaskQueue, QueuedTask  # noqa: E402


class TestTaskPriorityOrdering:
    """Test that priority levels sort correctly via the heap."""

    async def test_dharurah_dequeued_before_hajah(self, temp_db: str) -> None:
        """DHARURAH (necessity) tasks should be dequeued before HAJAH (need)."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        await task_queue.enqueue({"action": "background"}, priority=TaskPriority.HAJAH)
        await task_queue.enqueue({"action": "critical"}, priority=TaskPriority.DHARURAH)

        task = await task_queue.dequeue()
        assert task is not None
        assert task.priority == TaskPriority.DHARURAH
        assert task.payload == {"action": "critical"}

    async def test_hajah_dequeued_before_tahsiniyyah(self, temp_db: str) -> None:
        """HAJAH tasks should be dequeued before TAHSINIYYAH (improvement)."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        await task_queue.enqueue({"action": "optimize"}, priority=TaskPriority.TAHSINIYYAH)
        await task_queue.enqueue({"action": "user-request"}, priority=TaskPriority.HAJAH)

        task = await task_queue.dequeue()
        assert task is not None
        assert task.priority == TaskPriority.HAJAH

    async def test_full_priority_ordering(self, temp_db: str) -> None:
        """All four priority levels should dequeue in ascending numeric order."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        # Enqueue in reverse priority order
        await task_queue.enqueue({"level": "takmiliyyah"}, priority=TaskPriority.TAKMILIYYAH)
        await task_queue.enqueue({"level": "tahsiniyyah"}, priority=TaskPriority.TAHSINIYYAH)
        await task_queue.enqueue({"level": "hajah"}, priority=TaskPriority.HAJAH)
        await task_queue.enqueue({"level": "dharurah"}, priority=TaskPriority.DHARURAH)

        results: list[int] = []
        for _ in range(4):
            task = await task_queue.dequeue()
            assert task is not None
            results.append(task.priority)

        assert results == [
            TaskPriority.DHARURAH,
            TaskPriority.HAJAH,
            TaskPriority.TAHSINIYYAH,
            TaskPriority.TAKMILIYYAH,
        ]

    async def test_same_priority_ordered_by_creation_time(self, temp_db: str) -> None:
        """Tasks at the same priority should be dequeued in FIFO order."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        first_id = await task_queue.enqueue({"order": 1}, priority=TaskPriority.HAJAH)
        await task_queue.enqueue({"order": 2}, priority=TaskPriority.HAJAH)

        task = await task_queue.dequeue()
        assert task is not None
        assert task.task_id == first_id


class TestEnqueueDequeue:
    """Test basic enqueue/dequeue lifecycle."""

    async def test_enqueue_returns_task_id(self, temp_db: str) -> None:
        """enqueue() should return a non-empty task ID string."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue({"action": "test"})
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    async def test_dequeue_returns_none_when_empty(self, temp_db: str) -> None:
        """dequeue() should return None when the queue is empty."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task = await task_queue.dequeue()
        assert task is None

    async def test_dequeued_task_has_running_status(self, temp_db: str) -> None:
        """A dequeued task should transition to 'running' status."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue({"action": "process"})
        task = await task_queue.dequeue()

        assert task is not None
        assert task.status == "running"
        assert task.task_id == task_id

    async def test_complete_marks_task_done(self, temp_db: str) -> None:
        """complete() should set status to 'complete' and store the result."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue({"action": "compute"})
        await task_queue.dequeue()

        await task_queue.complete(task_id, {"answer": 42})
        stored = await task_queue.get_task(task_id)

        assert stored is not None
        assert stored.status == "complete"
        assert stored.result == {"answer": 42}

    async def test_fail_marks_task_failed(self, temp_db: str) -> None:
        """fail() should set status to 'failed' and store the error."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue({"action": "risky"})
        await task_queue.dequeue()

        await task_queue.fail(task_id, "something went wrong")
        stored = await task_queue.get_task(task_id)

        assert stored is not None
        assert stored.status == "failed"
        assert stored.error == "something went wrong"

    async def test_cancel_pending_task(self, temp_db: str) -> None:
        """cancel() should mark a pending task as cancelled."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue({"action": "cancelable"})
        cancelled = await task_queue.cancel(task_id)

        assert cancelled is True
        stored = await task_queue.get_task(task_id)
        assert stored is not None
        assert stored.status == "cancelled"

    async def test_cancel_running_task_returns_false(self, temp_db: str) -> None:
        """cancel() should return False for a non-pending task."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue({"action": "in-progress"})
        await task_queue.dequeue()  # transitions to running

        cancelled = await task_queue.cancel(task_id)
        assert cancelled is False


class TestListAndCount:
    """Test listing and counting tasks."""

    async def test_list_pending_returns_only_pending(self, temp_db: str) -> None:
        """list_tasks(status='pending') should exclude non-pending tasks."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        await task_queue.enqueue({"action": "a"}, priority=TaskPriority.HAJAH)
        await task_queue.enqueue({"action": "b"}, priority=TaskPriority.HAJAH)
        await task_queue.enqueue({"action": "c"}, priority=TaskPriority.HAJAH)

        # Dequeue one (transitions to running)
        await task_queue.dequeue()

        pending = await task_queue.list_tasks(status="pending")
        assert len(pending) == 2
        assert all(task.status == "pending" for task in pending)

    async def test_list_all_tasks(self, temp_db: str) -> None:
        """list_tasks() without status filter should return all tasks."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        await task_queue.enqueue({"action": "x"})
        await task_queue.enqueue({"action": "y"})
        await task_queue.dequeue()

        all_tasks = await task_queue.list_tasks()
        assert len(all_tasks) == 2

    async def test_pending_count_tracks_correctly(self, temp_db: str) -> None:
        """pending_count property should reflect current pending tasks."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        assert task_queue.pending_count == 0

        await task_queue.enqueue({"action": "first"})
        await task_queue.enqueue({"action": "second"})
        assert task_queue.pending_count == 2

        await task_queue.dequeue()
        assert task_queue.pending_count == 1


class TestInitialize:
    """Test database initialization and persistence."""

    async def test_initialize_creates_table(self, temp_db: str) -> None:
        """initialize() should create the tasks table without error."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        # Should be able to enqueue immediately after init
        task_id = await task_queue.enqueue({"action": "post-init"})
        assert task_id

    async def test_initialize_idempotent(self, temp_db: str) -> None:
        """Calling initialize() multiple times should not raise."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()
        await task_queue.initialize()  # second call should be safe

    async def test_persistence_across_instances(self, temp_db: str) -> None:
        """Tasks persisted by one queue instance should be restored by another."""
        queue_a = MizanTaskQueue(db_path=temp_db)
        await queue_a.initialize()
        await queue_a.enqueue({"action": "persist-me"}, priority=TaskPriority.DHARURAH)

        # Create a new instance pointing to the same DB
        queue_b = MizanTaskQueue(db_path=temp_db)
        await queue_b.initialize()

        task = await queue_b.dequeue()
        assert task is not None
        assert task.payload == {"action": "persist-me"}
        assert task.priority == TaskPriority.DHARURAH

    async def test_enqueue_with_agent_id(self, temp_db: str) -> None:
        """Tasks should store the optional agent_id."""
        task_queue = MizanTaskQueue(db_path=temp_db)
        await task_queue.initialize()

        task_id = await task_queue.enqueue(
            {"action": "assigned"},
            agent_id="agent-nafs-1",
        )

        task = await task_queue.get_task(task_id)
        assert task is not None
        assert task.agent_id == "agent-nafs-1"
