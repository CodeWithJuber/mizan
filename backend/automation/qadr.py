"""
Qadr Scheduler (قَدَر — Predestination)
==========================================

"Indeed, all things We created with predestination (Qadr)" — Quran 54:49

Cron-like task scheduler that executes through the full agent pipeline.
"""

import asyncio
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.qadr")


@dataclass
class ScheduledJob:
    """A scheduled job"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    cron: str = ""              # Cron expression (e.g., "0 9 * * *")
    task: str = ""              # Task description for agent
    agent_id: Optional[str] = None
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "cron": self.cron,
            "task": self.task,
            "agent_id": self.agent_id,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
        }


class QadrScheduler:
    """
    Cron-like task scheduler.
    Jobs execute through the full MIZAN agent pipeline.
    """

    def __init__(self):
        self.jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._executor: Optional[Callable] = None

    def set_executor(self, executor: Callable):
        """Set the function to execute scheduled tasks"""
        self._executor = executor

    async def add_job(self, name: str, cron: str, task: str,
                      agent_id: str = None) -> ScheduledJob:
        """Add a new scheduled job"""
        job = ScheduledJob(
            name=name,
            cron=cron,
            task=task,
            agent_id=agent_id,
        )

        # Calculate next run
        job.next_run = self._next_run_time(cron)

        self.jobs[job.id] = job
        logger.info(f"[QADR] Job added: {name} ({cron}) -> next: {job.next_run}")
        return job

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            return True
        return False

    async def start(self):
        """Start the scheduler loop"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("[QADR] Scheduler started")

    async def stop(self):
        """Stop the scheduler"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[QADR] Scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop — checks every 60 seconds"""
        while self._running:
            try:
                now = datetime.now(timezone.utc)

                for job in list(self.jobs.values()):
                    if not job.enabled or not job.next_run:
                        continue

                    next_run = datetime.fromisoformat(job.next_run)
                    if now >= next_run:
                        # Execute the job
                        logger.info(f"[QADR] Executing job: {job.name}")
                        if self._executor:
                            try:
                                await self._executor(job.task, job.agent_id)
                            except Exception as e:
                                logger.error(f"[QADR] Job {job.name} failed: {e}")

                        job.last_run = now.isoformat()
                        job.run_count += 1
                        job.next_run = self._next_run_time(job.cron)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[QADR] Scheduler error: {e}")

            await asyncio.sleep(60)  # Check every minute

    def _next_run_time(self, cron: str) -> Optional[str]:
        """Calculate next run time from cron expression"""
        try:
            from croniter import croniter
            now = datetime.now(timezone.utc)
            cron_iter = croniter(cron, now)
            next_time = cron_iter.get_next(datetime)
            return next_time.isoformat()
        except ImportError:
            logger.warning("[QADR] croniter not installed, using 1-hour interval")
            return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        except Exception as e:
            logger.error(f"[QADR] Invalid cron: {cron}: {e}")
            return None

    def add_heartbeat(self, interval_minutes: int = 5,
                      callback: Optional[Callable] = None):
        """Add a heartbeat that runs alongside cron jobs.

        The heartbeat fires every *interval_minutes* and invokes *callback*
        (if provided) with the list of pending/due jobs.  Results are also
        forwarded to the configured executor when appropriate.
        """
        self._heartbeat = HeartbeatScheduler(
            interval_minutes=interval_minutes,
            callback=callback,
            scheduler=self,
        )
        logger.info(
            f"[QADR] Heartbeat attached (interval={interval_minutes}m)"
        )
        return self._heartbeat

    def list_jobs(self) -> List[Dict]:
        """List all scheduled jobs"""
        return [job.to_dict() for job in self.jobs.values()]


# ---------------------------------------------------------------------------
# Heartbeat Scheduler
# ---------------------------------------------------------------------------

@dataclass
class HeartbeatEntry:
    """Audit record for a single heartbeat tick."""
    timestamp: str
    pending_jobs: int
    due_jobs_executed: int
    errors: List[str] = field(default_factory=list)


class HeartbeatScheduler:
    """
    Proactive heartbeat that runs at a configurable interval.

    On each tick it:
      1. Checks for pending scheduled jobs in the parent QadrScheduler.
      2. Executes any jobs that are due.
      3. Logs the heartbeat to an internal audit trail.
      4. Invokes an optional callback with a summary dict.

    Fully async-compatible — use ``await start()`` / ``await stop()``.
    """

    def __init__(
        self,
        interval_minutes: int = 5,
        callback: Optional[Callable] = None,
        scheduler: Optional["QadrScheduler"] = None,
    ):
        self.interval_minutes = interval_minutes
        self._callback = callback
        self._scheduler = scheduler
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._audit_log: List[HeartbeatEntry] = []

    # -- public API ---------------------------------------------------------

    async def start(self):
        """Start the heartbeat loop."""
        if self._running:
            logger.warning("[HEARTBEAT] Already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"[HEARTBEAT] Started (every {self.interval_minutes}m)"
        )

    async def stop(self):
        """Stop the heartbeat loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[HEARTBEAT] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_audit_log(self) -> List[Dict]:
        """Return the heartbeat audit trail as a list of dicts."""
        return [
            {
                "timestamp": e.timestamp,
                "pending_jobs": e.pending_jobs,
                "due_jobs_executed": e.due_jobs_executed,
                "errors": e.errors,
            }
            for e in self._audit_log
        ]

    # -- internals ----------------------------------------------------------

    async def _loop(self):
        """Core heartbeat loop."""
        interval_seconds = self.interval_minutes * 60
        while self._running:
            try:
                summary = await self._tick()
                if self._callback:
                    try:
                        result = self._callback(summary)
                        # Support both sync and async callbacks
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as exc:
                        logger.error(f"[HEARTBEAT] Callback error: {exc}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[HEARTBEAT] Loop error: {exc}")

            await asyncio.sleep(interval_seconds)

    async def _tick(self) -> Dict:
        """Execute a single heartbeat tick."""
        now = datetime.now(timezone.utc)
        errors: List[str] = []
        due_executed = 0
        pending_count = 0

        if self._scheduler:
            for job in list(self._scheduler.jobs.values()):
                if not job.enabled:
                    continue
                if not job.next_run:
                    continue

                pending_count += 1
                next_run = datetime.fromisoformat(job.next_run)

                if now >= next_run:
                    # Job is due — execute it
                    logger.info(
                        f"[HEARTBEAT] Executing due job: {job.name}"
                    )
                    if self._scheduler._executor:
                        try:
                            await self._scheduler._executor(
                                job.task, job.agent_id
                            )
                            due_executed += 1
                        except Exception as exc:
                            msg = f"Job {job.name} failed: {exc}"
                            logger.error(f"[HEARTBEAT] {msg}")
                            errors.append(msg)
                    else:
                        due_executed += 1  # counted but no executor

                    job.last_run = now.isoformat()
                    job.run_count += 1
                    job.next_run = self._scheduler._next_run_time(job.cron)

        entry = HeartbeatEntry(
            timestamp=now.isoformat(),
            pending_jobs=pending_count,
            due_jobs_executed=due_executed,
            errors=errors,
        )
        self._audit_log.append(entry)

        summary = {
            "timestamp": entry.timestamp,
            "pending_jobs": entry.pending_jobs,
            "due_jobs_executed": entry.due_jobs_executed,
            "errors": entry.errors,
        }
        logger.info(
            f"[HEARTBEAT] tick — pending={pending_count} "
            f"executed={due_executed} errors={len(errors)}"
        )
        return summary
