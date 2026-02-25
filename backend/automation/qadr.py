"""
Qadr Scheduler (قَدَر — Predestination)
==========================================

"Indeed, all things We created with predestination (Qadr)" — Quran 54:49

Cron-like task scheduler that executes through the full agent pipeline.
"""

import asyncio
import uuid
import logging
from datetime import datetime, timedelta
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
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

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
                now = datetime.utcnow()

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
            now = datetime.utcnow()
            cron_iter = croniter(cron, now)
            next_time = cron_iter.get_next(datetime)
            return next_time.isoformat()
        except ImportError:
            logger.warning("[QADR] croniter not installed, using 1-hour interval")
            return (datetime.utcnow() + timedelta(hours=1)).isoformat()
        except Exception as e:
            logger.error(f"[QADR] Invalid cron: {cron}: {e}")
            return None

    def list_jobs(self) -> List[Dict]:
        """List all scheduled jobs"""
        return [job.to_dict() for job in self.jobs.values()]
