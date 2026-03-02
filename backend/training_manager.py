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
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    ) -> dict[str, Any]:
        """Spawn a training subprocess and begin monitoring.

        Returns a status dict. Raises ValueError if already running.
        """
        if self._state.running:
            raise ValueError("Training is already in progress")

        # Validate environment
        ruh_dir = Path("ruh_model")
        if not ruh_dir.exists():
            raise ValueError("ruh_model/ directory not found")

        # Build command
        cmd = [
            "python", "-m", "ruh_model.train",
            "--stage", stage,
            "--data-dir", data_dir,
            "--checkpoint-dir", checkpoint_dir,
            "--log-every", str(log_every),
            "--generate-data",
            "--json-progress",
        ]
        if config_path:
            cmd.extend(["--config", config_path])

        logger.info("Starting training: %s", " ".join(cmd))

        # Reset state
        self._state = TrainingState(
            running=True,
            stage=stage,
            message=f"Starting {stage} training...",
            started_at=time.time(),
        )

        await self._broadcast_state()

        # Spawn subprocess
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path.cwd()),
        )

        # Start monitoring task
        self._monitor_task = asyncio.create_task(
            self._monitor_output(), name="training_monitor"
        )

        return self.get_status()

    async def stop_training(self) -> dict[str, Any]:
        """Terminate the running training process.

        Returns final status dict. Raises ValueError if not running.
        """
        if not self._state.running:
            raise ValueError("No training is in progress")

        if self._process and self._process.returncode is None:
            self._process.terminate()
            # Wait briefly for graceful shutdown
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

        self._state.running = False
        self._state.message = "Training stopped by user"
        await self._broadcast_state()
        self._save_run_to_history("stopped")

        return self.get_status()

    async def _monitor_output(self) -> None:
        """Read stdout JSON lines from the training subprocess."""
        if not self._process or not self._process.stdout:
            return

        try:
            async for line in self._process.stdout:
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue
                try:
                    data = json.loads(decoded)
                    await self._handle_progress(data)
                except json.JSONDecodeError:
                    # Regular log line — ignore
                    logger.debug("Train output: %s", decoded)

            # Process ended
            return_code = await self._process.wait()
            if self._state.running:
                self._state.running = False
                if return_code == 0:
                    self._state.message = "Training completed successfully"
                    self._save_run_to_history("completed")
                else:
                    stderr_bytes = await self._process.stderr.read() if self._process.stderr else b""
                    stderr = stderr_bytes.decode("utf-8", errors="replace")[-500:]
                    self._state.message = f"Training failed (exit {return_code}): {stderr}"
                    self._save_run_to_history("failed")
                await self._broadcast_state()

        except asyncio.CancelledError:
            logger.info("Training monitor cancelled")
        except Exception as exc:
            logger.error("Training monitor error: %s", exc)
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
                f"Loss: {self._state.loss:.4f}" if self._state.loss else ""
            )

        elif msg_type == "epoch":
            avg_loss = data.get("avg_loss")
            if avg_loss is not None:
                self._state.losses.append(avg_loss)
            self._state.epoch = data.get("epoch", 0)
            self._state.message = (
                f"Epoch {self._state.epoch}/{self._state.total_epochs} complete. "
                f"Avg loss: {avg_loss:.4f}" if avg_loss else ""
            )

        elif msg_type == "complete":
            self._state.running = False
            final_loss = data.get("final_loss")
            self._state.message = (
                f"Training complete. Final loss: {final_loss:.4f}"
                if final_loss else "Training complete."
            )
            self._save_run_to_history("completed")

        await self._broadcast_state()

    async def _broadcast_state(self) -> None:
        """Send current state to all WebSocket clients."""
        if self._broadcast_fn:
            try:
                await self._broadcast_fn({
                    "type": "training_progress",
                    **self.get_status(),
                })
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
        }
        self._history.append(run_entry)
        self._persist_history()

    def _load_history(self) -> list[dict[str, Any]]:
        """Load training history from disk."""
        if _HISTORY_FILE.exists():
            try:
                with open(_HISTORY_FILE, encoding="utf-8") as fh:
                    return json.load(fh)
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
