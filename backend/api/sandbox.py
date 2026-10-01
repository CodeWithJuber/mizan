"""Sandboxed code execution API.

POST /api/sandbox/run — runs user-supplied Python/JavaScript code inside an
isolated sandbox and returns captured output. Authentication is applied at
router-mount time (see backend/api/main.py) so this module stays import-safe.

Executor preference order (JEV-locked):
  1. microsandbox (libkrun microVM) — preferred, when importable AND its
     backend is reachable.
  2. hardened Docker — `docker run --rm --cap-drop ALL --read-only
     --no-new-privileges --network none` with CPU/memory/PID limits and an
     enforced wall-clock timeout.
  3. Neither available → fail CLOSED with HTTP 503. Code is NEVER executed
     outside a sandbox.

Defense in depth: wall-clock timeout (process/sandbox killed on expiry),
stdout/stderr size caps, CPU/memory/PID limits (Docker), and an append-only
JSONL audit log of every run at ``{data_dir}/sandbox_audit.log``.

microsandbox SDK surface verified against microsandbox-0.7.4
(PyPI name ``microsandbox``, ``from microsandbox import Sandbox``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("mizan.sandbox")

router = APIRouter(tags=["sandbox"])

MAX_CODE_CHARS = 100_000
MAX_TIMEOUT_S = 120
DEFAULT_TIMEOUT_S = 30
MAX_OUTPUT_BYTES = 100 * 1024  # 100 KiB cap per stream


# ── Schemas ──────────────────────────────────────────────────────────────────


class SandboxRunRequest(BaseModel):
    """Request body for POST /api/sandbox/run."""

    language: Literal["python", "javascript"] = Field(..., description="'python' or 'javascript'")
    code: str = Field(
        ..., min_length=1, max_length=MAX_CODE_CHARS, description="Source code to execute"
    )
    timeout_s: int = Field(
        default=DEFAULT_TIMEOUT_S,
        ge=1,
        le=MAX_TIMEOUT_S,
        description="Wall-clock timeout in seconds (1..120)",
    )


class SandboxRunResult(BaseModel):
    """Response body for POST /api/sandbox/run."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int
    sandbox: Literal["microsandbox", "docker"]


class SandboxProviderStatus(BaseModel):
    """Response body for GET /api/sandbox/status."""

    provider: str | None
    available: bool
    detail: str


# ── Audit log ────────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data"))


def _audit_path() -> Path:
    return _data_dir() / "sandbox_audit.log"


def _audit_log(record: dict) -> None:
    """Append-only audit record of a sandbox run (never raises)."""
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:  # noqa: BLE001 - audit must never break execution
        logger.warning("sandbox audit log failed: %s", e)


# ── Output caps ──────────────────────────────────────────────────────────────


def _cap(text: str) -> str:
    """Truncate a stream to MAX_OUTPUT_BYTES, marking truncation honestly."""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= MAX_OUTPUT_BYTES:
        return text
    cut = data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    return cut + f"\n... [truncated: output exceeded {MAX_OUTPUT_BYTES} bytes]"


# ── Provider detection ───────────────────────────────────────────────────────


def _microsandbox_importable() -> bool:
    try:
        import microsandbox  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def detect_provider() -> str | None:
    """Return the preferred available sandbox provider, or None (fail closed)."""
    if _microsandbox_importable():
        return "microsandbox"
    if _docker_available():
        return "docker"
    return None


# ── Executor 1: microsandbox (libkrun microVM) ───────────────────────────────


_MICROSANDBOX_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
}

_MICROSANDBOX_BIN = {
    "python": "python3",
    "javascript": "node",
}


async def _run_microsandbox(language: str, code: str, timeout_s: int) -> SandboxRunResult:
    """Run code in a microsandbox microVM. Raises on any backend failure so the
    caller can fall through to Docker or fail closed."""
    from microsandbox import Sandbox  # local import: optional dependency
    from microsandbox.errors import ExecTimeoutError

    started = time.monotonic()
    image = _MICROSANDBOX_IMAGES[language]
    binary = _MICROSANDBOX_BIN[language]
    handle = None
    try:
        # ephemeral sandbox: destroyed on remove; no host mounts, no network.
        handle = await asyncio.wait_for(
            Sandbox.create(
                f"mizan-sandbox-{uuid.uuid4().hex[:12]}",
                image=image,
                memory=256,
                cpus=1,
                ephemeral=True,
            ),
            timeout=timeout_s,
        )
        try:
            out = await handle.exec(
                binary,
                args=["-"],
                timeout=float(timeout_s),
                stdin=code.encode("utf-8"),
            )
            stdout, stderr, exit_code, timed_out = (
                _cap(out.stdout_text),
                _cap(out.stderr_text),
                out.exit_code,
                False,
            )
        except ExecTimeoutError:
            stdout, stderr, exit_code, timed_out = (
                "",
                f"[sandbox] execution timed out after {timeout_s}s (killed)",
                124,
                True,
            )
    finally:
        if handle is not None:
            try:
                await asyncio.wait_for(handle.remove(), timeout=15)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                logger.warning("microsandbox cleanup failed", exc_info=True)

    return SandboxRunResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=int((time.monotonic() - started) * 1000),
        sandbox="microsandbox",
    )


# ── Executor 2: hardened Docker fallback ─────────────────────────────────────


_DOCKER_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
}

_DOCKER_CMD = {
    "python": ["python3", "/code/main.py"],
    "javascript": ["node", "/code/main.js"],
}

_DOCKER_EXT = {"python": "main.py", "javascript": "main.js"}


def _run_docker_sync(language: str, code: str, timeout_s: int) -> SandboxRunResult:
    """Blocking Docker run (executed in a thread by the caller)."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mizan-sandbox-") as tmp:
        code_path = Path(tmp) / _DOCKER_EXT[language]
        code_path.write_text(code, encoding="utf-8")
        # Mode 0444: the container only needs to read it.
        code_path.chmod(0o444)
        cmd = [
            "docker",
            "run",
            "--rm",
            "--cap-drop",
            "ALL",
            "--read-only",
            "--no-new-privileges",
            "--network",
            "none",
            "--cpus",
            "1.0",
            "--memory",
            "256m",
            "--pids-limit",
            "64",
            "-v",
            f"{code_path}:/code/{_DOCKER_EXT[language]}:ro",
            _DOCKER_IMAGES[language],
            *_DOCKER_CMD[language],
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            exit_code, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or b"").decode("utf-8", errors="replace")
            stderr = (e.stderr or b"").decode("utf-8", errors="replace")
            stderr += f"\n[sandbox] execution timed out after {timeout_s}s (killed)"
            exit_code, timed_out = 124, True

    return SandboxRunResult(
        stdout=_cap(stdout),
        stderr=_cap(stderr),
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=int((time.monotonic() - started) * 1000),
        sandbox="docker",
    )


async def _run_docker(language: str, code: str, timeout_s: int) -> SandboxRunResult:
    return await asyncio.to_thread(_run_docker_sync, language, code, timeout_s)


# ── Dispatch ─────────────────────────────────────────────────────────────────


async def execute_code(
    language: str, code: str, timeout_s: int, user_id: str = ""
) -> SandboxRunResult:
    """Execute code via the preferred available sandbox provider.

    Raises HTTPException(503) when no provider is available — never runs
    un-sandboxed.
    """
    if language not in ("python", "javascript"):
        raise HTTPException(400, f"Unsupported language: {language}")
    if not code or len(code) > MAX_CODE_CHARS:
        raise HTTPException(400, "code must be 1..100000 characters")

    started = time.monotonic()
    run_id = uuid.uuid4().hex[:12]
    provider = detect_provider()

    try:
        if provider == "microsandbox":
            try:
                result = await _run_microsandbox(language, code, timeout_s)
            except Exception as e:  # noqa: BLE001 - fall through to Docker
                logger.warning("microsandbox run failed, trying docker: %s", e)
                if _docker_available():
                    result = await _run_docker(language, code, timeout_s)
                else:
                    raise
        elif provider == "docker":
            result = await _run_docker(language, code, timeout_s)
        else:
            raise HTTPException(
                503,
                "code execution unavailable: no sandbox provider (install microsandbox or docker)",
            )
    finally:
        _audit_log(
            {
                "ts": time.time(),
                "run_id": run_id,
                "user_id": user_id or None,
                "language": language,
                "code_chars": len(code),
                "timeout_s": timeout_s,
                "provider": provider,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
    return result


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/api/sandbox/run", response_model=SandboxRunResult)
async def sandbox_run(req: SandboxRunRequest):
    """Execute code in an isolated sandbox. Auth applied at mount time."""
    # user id resolution is best-effort here; auth is enforced by the mount.
    return await execute_code(req.language, req.code, req.timeout_s)


@router.get("/api/sandbox/status", response_model=SandboxProviderStatus)
async def sandbox_status():
    """Report which sandbox provider (if any) is available."""
    provider = detect_provider()
    if provider == "microsandbox":
        detail = "microsandbox (libkrun microVM) SDK importable"
    elif provider == "docker":
        detail = "docker CLI available (hardened flags)"
    else:
        detail = "no sandbox provider: code execution is disabled (fail closed)"
    return SandboxProviderStatus(provider=provider, available=provider is not None, detail=detail)
