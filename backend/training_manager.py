"""TrainingManager — bridges CLI training process to the web API.

Maintains training state, spawns/stops training subprocesses, parses
JSON progress lines, and broadcasts updates via WebSocket.

The singleton instance is created in backend.api.main and given a
reference to the ConnectionManager for broadcasting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path("data/training_history.json")


@dataclass
class TrainingState:
    """Snapshot of current training progress."""

    running: bool = False
    stage: str | None = None
    epoch: int = 0
    total_epochs: int = 0
    step: int = 0
    total_steps: int = 0
    loss: float | None = None
    lr: float | None = None
    progress_pct: float = 0.0
    elapsed: float = 0.0
    dataset_size: int = 0
    model_params: int = 0
    message: str = "Training not started"
    started_at: float | None = None
    losses: list[float] = field(default_factory=list)
    data_source: str | None = None


class TrainingManager:
    """Manages training subprocess lifecycle and state broadcasting.

    Responsibilities:
    - Start/stop the training subprocess (python -m ruh_model.train)
    - Parse JSON progress lines from stdout
    - Update internal state and broadcast via WebSocket
    - Persist training history to disk
    """

    def __init__(self) -> None:
        self._state = TrainingState()
        self._process: asyncio.subprocess.Process | None = None
        self._broadcast_fn: Any | None = None
        self._monitor_task: asyncio.Task | None = None
        self._history: list[dict[str, Any]] = self._load_history()
        self._lifecycle_lock = asyncio.Lock()

    def set_broadcast(self, broadcast_fn: Any) -> None:
        """Set the WebSocket broadcast function (manager.broadcast)."""
        self._broadcast_fn = broadcast_fn

    def get_status(self) -> dict[str, Any]:
        """Return current training state as a dict for the API."""
        return {
            "running": self._state.running,
            "stage": self._state.stage,
            "epoch": self._state.epoch,
            "total_epochs": self._state.total_epochs,
            "step": self._state.step,
            "total_steps": self._state.total_steps,
            "loss": self._state.loss,
            "lr": self._state.lr,
            "progress_pct": round(self._state.progress_pct, 1),
            "elapsed": round(self._state.elapsed, 1),
            "dataset_size": self._state.dataset_size,
            "model_params": self._state.model_params,
            "message": self._state.message,
            "losses": list(self._state.losses),
            "data_source": self._state.data_source,
            "original_data_verified": False,
            "automatic_weight_training": False,
        }

    def get_history(self) -> list[dict[str, Any]]:
        """Return all past training runs."""
        return list(self._history)

    async def start_training(
        self,
        stage: str = "nutfah",
        config_path: str | None = None,
        data_dir: str = "ruh_model/data/training",
        checkpoint_dir: str = "ruh_model/checkpoints",
        log_every: int = 10,
        generate_seed_data: bool = False,
    ) -> dict[str, Any]:
        """Start a manual run; generated seed data requires explicit opt-in."""
        async with self._lifecycle_lock:
            return await self._start_training(
                stage, config_path, data_dir, checkpoint_dir, log_every, generate_seed_data
            )

    async def _start_training(
        self,
        stage: str,
        config_path: str | None,
        data_dir: str,
        checkpoint_dir: str,
        log_every: int,
        generate_seed_data: bool,
    ) -> dict[str, Any]:
        """Validate inputs and spawn the process while holding the lifecycle lock.

        Returns a status dict. Raises ValueError if already running.
        """
        if self._state.running or (self._process and self._process.returncode is None):
            raise ValueError("Training is already in progress")
        if type(generate_seed_data) is not bool:
            raise ValueError("Seed generation requires an explicit boolean choice")

        # Validate environment
        ruh_dir = Path("ruh_model")
        if not ruh_dir.exists():
            raise ValueError("ruh_model/ directory not found")
        if not generate_seed_data:
            data_path = Path(data_dir)
            files = sorted(data_path.glob("*.jsonl")) if data_path.is_dir() else [data_path]
            populated = [
                path
                for path in files
                if path.suffix == ".jsonl" and path.is_file() and path.stat().st_size > 0
            ]
            if not populated:
                raise ValueError(
                    "No prepared JSONL training data found. Supply a dataset or explicitly "
                    "select generated seed examples; chat capture is not training data."
                )
            if any(path.name in {"seed_roots.jsonl", "seed_concepts.jsonl"} for path in populated):
                raise ValueError(
                    "This dataset includes generated seed files. Use a separate prepared "
                    "dataset or explicitly select generated seed examples."
                )

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "ruh_model.train",
            "--stage",
            stage,
            "--data-dir",
            data_dir,
            "--checkpoint-dir",
            checkpoint_dir,
            "--log-every",
            str(log_every),
            "--json-progress",
        ]
        if generate_seed_data:
            cmd.append("--generate-data")
        if config_path:
            cmd.extend(["--config", config_path])

        logger.info("Starting training: %s", " ".join(cmd))

        # Reset state
        self._state = TrainingState(
            running=True,
            stage=stage,
            message=f"Starting {stage} training...",
            started_at=time.time(),
            data_source="generated_seed_examples" if generate_seed_data else "supplied_unverified",
        )

        await self._broadcast_state()

        # Spawn subprocess
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.cwd()),
            )
        except (OSError, ValueError):
            self._state.running = False
            self._state.message = "Training process could not be started"
            self._save_run_to_history("failed")
            await self._broadcast_state()
            raise

        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_output(), name="training_monitor")

        return self.get_status()

    async def stop_training(self) -> dict[str, Any]:
        async with self._lifecycle_lock:
            return await self._stop_training()

    async def _stop_training(self) -> dict[str, Any]:
        """Terminate the running training process.

        Returns final status dict. Raises ValueError if not running.
        """
        if not self._state.running:
            raise ValueError("No training is in progress")

        # Prevent the monitor from recording a user-requested stop as a failure.
        self._state.running = False

        if self._process and self._process.returncode is None:
            self._process.terminate()
            # Wait briefly for graceful shutdown
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()

        self._state.message = "Training stopped by user"
        await self._broadcast_state()
        self._save_run_to_history("stopped")

        return self.get_status()

    async def _monitor_output(self) -> None:
        """Drain both pipes concurrently, retaining a bounded stderr tail."""
        process = self._process
        if not process or not process.stdout:
            return
        stderr_tail = bytearray()

        async def drain_stderr():
            if process.stderr:
                while chunk := await process.stderr.read(4096):
                    stderr_tail.extend(chunk)
                    del stderr_tail[:-4096]

        async def drain_stdout():
            # Read bounded chunks: a child can also emit a line beyond StreamReader's limit.
            pending = b""
            while chunk := await process.stdout.read(4096):
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            await self._handle_progress(data)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.debug("Train output: %s", line[:1000])
                if len(pending) > 65536:
                    pending = b""

        try:
            await asyncio.gather(drain_stdout(), drain_stderr())
            return_code = await process.wait()
            if self._state.running:
                self._state.running = False
                if return_code == 0:
                    self._state.message = "Training completed successfully"
                    self._save_run_to_history("completed")
                else:
                    tail = stderr_tail.decode("utf-8", errors="replace")[-500:]
                    self._state.message = f"Training failed (exit {return_code}): {tail}"
                    self._save_run_to_history("failed")
                await self._broadcast_state()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        except Exception as exc:
            logger.exception("Training monitor error")
            if process.returncode is None:
                process.kill()
                await process.wait()
            self._state.running = False
            self._state.message = f"Monitor error: {exc}"
            await self._broadcast_state()

    async def _handle_progress(self, data: dict[str, Any]) -> None:
        """Update internal state from a JSON progress message."""
        msg_type = data.get("type", "")

        if msg_type == "start":
            self._state.total_epochs = data.get("epochs", 0)
            self._state.dataset_size = data.get("dataset_size", 0)
            self._state.model_params = data.get("model_params", 0)
            self._state.message = f"Training started: {data.get('stage', '')} stage"

        elif msg_type == "step":
            self._state.epoch = data.get("epoch", 0)
            self._state.total_epochs = data.get("total_epochs", 0)
            self._state.step = data.get("step", 0)
            self._state.total_steps = data.get("total_steps", 0)
            self._state.loss = data.get("loss")
            self._state.lr = data.get("lr")
            self._state.elapsed = data.get("elapsed", 0)

            # Compute overall progress
            global_step = data.get("global_step", 0)
            total_global = data.get("total_global_steps", 1)
            self._state.progress_pct = (global_step / max(total_global, 1)) * 100
            self._state.message = (
                f"Epoch {self._state.epoch}/{self._state.total_epochs} "
                f"Step {self._state.step}/{self._state.total_steps} "
                f"Loss: {self._state.loss:.4f}"
                if self._state.loss is not None
                else ""
            )

        elif msg_type == "epoch":
            avg_loss = data.get("avg_loss")
            if avg_loss is not None:
                self._state.losses.append(avg_loss)
            self._state.epoch = data.get("epoch", 0)
            self._state.message = (
                f"Epoch {self._state.epoch}/{self._state.total_epochs} complete. "
                f"Avg loss: {avg_loss:.4f}"
                if avg_loss is not None
                else ""
            )

        elif msg_type == "complete":
            final_loss = data.get("final_loss")
            self._state.loss = final_loss
            self._state.message = (
                f"Training reported final loss {final_loss:.4f}; waiting for process exit"
                if final_loss is not None
                else "Training reported completion; waiting for process exit"
            )

        await self._broadcast_state()

    async def _broadcast_state(self) -> None:
        """Send current state to all WebSocket clients."""
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(
                    {
                        "type": "training_progress",
                        **self.get_status(),
                    }
                )
            except Exception as exc:
                logger.debug("Broadcast failed: %s", exc)

    def _save_run_to_history(self, status: str) -> None:
        """Persist the completed/stopped run to history."""
        run_entry = {
            "stage": self._state.stage,
            "status": status,
            "started_at": self._state.started_at,
            "completed_at": time.time(),
            "epochs_completed": self._state.epoch,
            "total_epochs": self._state.total_epochs,
            "final_loss": self._state.loss,
            "losses": list(self._state.losses),
            "dataset_size": self._state.dataset_size,
            "model_params": self._state.model_params,
            "data_source": self._state.data_source,
            "original_data_verified": False,
            "automatic_weight_training": False,
        }
        self._history.append(run_entry)
        self._persist_history()

    def _load_history(self) -> list[dict[str, Any]]:
        """Load training history from disk."""
        if _HISTORY_FILE.exists():
            try:
                with open(_HISTORY_FILE, encoding="utf-8") as fh:
                    return cast(list[dict[str, Any]], json.load(fh))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load training history: %s", exc)
        return []

    def _persist_history(self) -> None:
        """Save training history to disk."""
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_HISTORY_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._history, fh, indent=2, default=str)
        except OSError as exc:
            logger.warning("Failed to persist training history: %s", exc)


# Singleton instance used across the backend
training_manager = TrainingManager()
