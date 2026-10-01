"""Private sandbox control plane. Run separately from the public Mizan backend.

This service requires a dedicated Docker daemon and a shared private API token.
Only the job containers execute code; no host command or mounts come from callers.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import subprocess
import threading
import uuid
from typing import Literal, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_SLOTS = asyncio.Semaphore(2)
MAX_BODY = 16 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024


def require_runner_token(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv("MIZAN_WORKSPACE_RUNNER_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Runner authentication not configured")
    expected = f"Bearer {token}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401, "Runner authentication required")


class RunnerRequest(BaseModel):
    command: str = Field(min_length=1, max_length=10000)
    language: Literal["shell", "python", "javascript"]
    timeout_s: int = Field(ge=1, le=120)
    files: dict[str, str] = Field(max_length=500)
    directories: list[str] = Field(default_factory=list, max_length=500)


def environment() -> dict[str, str]:
    allowed = ("PATH", "DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONFIG")
    return {name: os.environ[name] for name in allowed if name in os.environ}


def cleanup(name: str) -> None:
    result = subprocess.run(
        ["docker", "rm", "-f", name],
        env=environment(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 and f"No such container: {name}".encode() not in result.stderr:
        raise OSError("Could not verify isolated job removal")


def execute(payload: dict) -> dict:
    name = f"mizan-workspace-{uuid.uuid4().hex}"
    image = os.getenv("MIZAN_WORKSPACE_RUNTIME_IMAGE", "mizan-workspace-runtime:v1")
    command = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        name,
        "--init",
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--read-only",
        "--security-opt",
        "no-new-privileges",
        "--network",
        "none",
        "--cpus",
        "1",
        "--memory",
        "384m",
        "--memory-swap",
        "384m",
        "--pids-limit",
        "64",
        "--ulimit",
        "nofile=256:256",
        "--tmpfs",
        "/workspace:rw,noexec,nosuid,nodev,size=32m,mode=700,uid=65534,gid=65534",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
    ]
    for variable in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "FTP_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "ftp_proxy",
    ):
        command.extend(["--env", f"{variable}="])
    command.extend(["-i", image, "python3", "/runtime.py"])
    retained = [bytearray(), bytearray()]

    def drain(pipe, target):
        try:
            while chunk := pipe.read(32768):
                target.extend(chunk[: max(0, MAX_RESPONSE + 1 - len(target))])
        finally:
            pipe.close()

    process = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment(),
        )
        readers = [
            threading.Thread(target=drain, args=(pipe, target), daemon=True)
            for pipe, target in zip((process.stdout, process.stderr), retained, strict=True)
        ]
        for reader in readers:
            reader.start()

        def write_request():
            try:
                process.stdin.write(json.dumps(payload).encode())
            except BrokenPipeError:
                pass
            finally:
                process.stdin.close()

        writer = threading.Thread(target=write_request, daemon=True)
        writer.start()
        try:
            exit_code = process.wait(timeout=payload["timeout_s"] + 20)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "Isolated execution exceeded its deadline") from None
        for reader in readers:
            reader.join(timeout=5)
        writer.join(timeout=5)
        if exit_code != 0 or len(retained[0]) > MAX_RESPONSE:
            raise HTTPException(503, "Isolated runtime failed or produced an oversized response")
        try:
            return cast(dict, json.loads(retained[0]))
        except ValueError:
            raise HTTPException(503, "Isolated runtime produced an invalid response") from None
    except (OSError, BrokenPipeError, subprocess.TimeoutExpired):
        raise HTTPException(503, "Isolated runtime unavailable") from None
    finally:
        termination_failed = False
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                termination_failed = True
        # CLI termination is independent of daemon cleanup: a broken daemon can
        # never leave Popen.__exit__ waiting indefinitely or keep the API slot.
        try:
            cleanup(name)
        except (OSError, subprocess.TimeoutExpired):
            raise HTTPException(503, "Isolated job cleanup could not be verified") from None
        if termination_failed:
            raise HTTPException(503, "Isolated Docker client termination failed")


@app.get("/health", dependencies=[Depends(require_runner_token)])
async def health() -> dict:
    def check() -> bool:
        try:
            image = os.getenv("MIZAN_WORKSPACE_RUNTIME_IMAGE", "mizan-workspace-runtime:v1")
            result = subprocess.run(
                ["docker", "image", "inspect", image],
                env=environment(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    return {"isolated": True, "available": await asyncio.to_thread(check)}


@app.post("/run", dependencies=[Depends(require_runner_token)])
async def run(request: Request) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise HTTPException(413, "Project request exceeds the allowed size")
        body.extend(chunk)
    try:
        payload = RunnerRequest.model_validate_json(body).model_dump()
    except ValueError:
        raise HTTPException(422, "Invalid project execution request") from None
    if _SLOTS.locked():
        raise HTTPException(429, "Isolated runner is busy")
    async with _SLOTS:
        # Shield cleanup even if the backend/client disconnects during execution.
        task = asyncio.create_task(asyncio.to_thread(execute, payload))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
