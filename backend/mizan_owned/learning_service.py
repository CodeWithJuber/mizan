"""Asynchronous supervision of the bounded, local owned-learning CLI.

No chat text, credentials, model-selection change, or paid compute is supplied to
the worker. Original-data admission and checkpoint gates live in learning_cycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import sys
import uuid
from pathlib import Path

BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SUPERVISOR_TIMEOUT = 1830


def configured_root() -> Path | None:
    value = os.getenv("MIZAN_OWNED_LEARNING_DIR", "").strip()
    return Path(value).expanduser().resolve() if value else None


def worker_environment() -> dict[str, str]:
    backend = Path(__file__).resolve().parents[1]
    source = backend.parent if backend.name == "backend" else backend
    return {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join(dict.fromkeys((str(backend), str(source)))),
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "LANG": "C.UTF-8",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }


def autorun() -> bool:
    """Train automatically when an approved bundle is ready (on unless switched off)."""
    return os.getenv("MIZAN_OWNED_LEARNING_AUTORUN", "true").lower() in {"1", "true", "yes"}


class OwnedLearningService:
    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._watcher: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stopping = False
        self.last_job: dict | None = None

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def automation_active(self) -> bool:
        return self._watcher is not None and not self._watcher.done() and autorun()

    async def snapshot(self) -> dict:
        from mizan_owned.learning_cycle import LearningError, status

        root = configured_root()
        payload: dict = {"configured": root is not None, "active": None, "generation": 0}
        if root is not None:
            try:
                payload.update(await asyncio.to_thread(status, root))
            except (LearningError, OSError):
                payload.update(status="unavailable", error="Learning state could not be verified.")
        payload.update(
            configured=root is not None,
            service_busy=self.busy,
            service_job=self.last_job,
            automation_configured=autorun(),
            automation_active=self.automation_active,
            ready_for_general_chat=False,
            chat_capture_is_training_data=False,
        )
        return payload

    async def start_cycle(self, bundle_id: str, *, requested_by: str) -> dict:
        from mizan_owned.learning_cycle import LearningBusy, list_bundles

        if not BUNDLE_ID.fullmatch(bundle_id):
            raise ValueError("Invalid bundle identifier")
        root = configured_root()
        if root is None:
            raise ValueError("Owned learning is not configured")
        if sys.platform != "linux":
            raise ValueError("The bounded learning worker requires Linux")
        async with self._guard:
            if self.busy or self._stopping:
                raise LearningBusy("A learning cycle is running or the service is stopping")
            bundles = await asyncio.to_thread(list_bundles, root)
            if not any(
                row.get("bundle_id") == bundle_id and row.get("state") == "ready" for row in bundles
            ):
                raise ValueError("Bundle is unavailable, unapproved, invalid, or already processed")
            self.last_job = {
                "id": uuid.uuid4().hex,
                "bundle_id": bundle_id,
                "state": "queued",
                "requested_by": requested_by,
            }
            self._task = asyncio.create_task(self._run(root, bundle_id, self.last_job))
            return dict(self.last_job)

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=10)
        # A cooperative leader can exit while a descendant ignores TERM. The
        # dedicated group must be cleaned even after the leader has been reaped.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()

    async def _run(self, root: Path, bundle_id: str, job: dict) -> None:
        spawning = asyncio.create_task(
            asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "mizan_owned.learning_cycle",
                "run",
                "--root",
                str(root),
                "--bundle-id",
                bundle_id,
                env=worker_environment(),
                cwd=str(Path(__file__).resolve().parents[1]),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        )
        process = None
        try:
            process = await asyncio.shield(spawning)
            self._process = process
            if self._stopping:
                job["state"] = "interrupted"
                return
            job["state"] = "running"
            code = await asyncio.wait_for(process.wait(), timeout=SUPERVISOR_TIMEOUT)
            job.update(state="finished" if code == 0 else "failed", exit_code=code)
            # A successful process exit is not an accepted candidate: the durable
            # cycle receipt separately reports rejection, activation and gates.
        except asyncio.CancelledError:
            if process is None:
                with contextlib.suppress(OSError):
                    process = await spawning
            job["state"] = "interrupted"
            raise
        except TimeoutError:
            job["state"] = "timed_out"
        except OSError:
            job["state"] = "failed"
        finally:
            if process is not None:
                await self._terminate(process)
            self._process = None

    async def start(self) -> None:
        self._stopping = False
        if configured_root() is not None:
            # The watcher reads the switch on every pass, so turning automatic
            # training on or off in System settings takes effect without a restart.
            self._watcher = asyncio.create_task(self._watch())

    async def _watch(self) -> None:
        from mizan_owned.learning_cycle import LearningError, list_bundles

        while not self._stopping:
            try:
                root = configured_root()
                if root is not None and autorun() and not self.busy:
                    bundles = await asyncio.to_thread(list_bundles, root)
                    for row in bundles:
                        if row.get("state") == "ready":
                            await self.start_cycle(
                                row["bundle_id"], requested_by="configured_automation"
                            )
                            break
            except (LearningError, OSError, ValueError):
                # Invalid data/state is not retrained or promoted. Keep the API
                # available to show the durable admission/validation evidence.
                pass
            await asyncio.sleep(60)

    async def stop(self) -> None:
        self._stopping = True
        if self._watcher is not None:
            self._watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher
            self._watcher = None
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


learning_service = OwnedLearningService()
