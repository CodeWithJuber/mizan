"""Private sandbox control plane. Run separately from the public Mizan backend.

This service requires a dedicated Docker daemon and a shared private API token.
Only the job containers execute code; no host command or mounts come from callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import subprocess
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from .sessions import (
    SessionError,
    Terminal,
    http_through,
    name_of,
    sessions,
    stdio_process,
)
from .sessions import (
    limits as session_limits,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    reaper = asyncio.create_task(sessions.reaper())
    try:
        yield
    finally:
        reaper.cancel()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
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


# ── Persistent sessions ────────────────────────────────────────────────────


def _token_ok(value: str | None) -> bool:
    token = os.getenv("MIZAN_WORKSPACE_RUNNER_TOKEN", "")
    return (
        len(token) >= 32
        and bool(value)
        and hmac.compare_digest((value or "").encode(), f"Bearer {token}".encode())
    )


async def _body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Request exceeds the allowed size")
        body.extend(chunk)
    return bytes(body)


@contextlib.contextmanager
def _session_errors():
    try:
        yield
    except SessionError as exc:
        raise HTTPException(exc.status, exc.detail, headers={"X-Mizan-Runner": "error"}) from None


class SessionStart(BaseModel):
    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["workspace", "mcp"] = "workspace"
    preview_prefix: str = Field(default="", max_length=300)


class SessionExec(BaseModel):
    command: str = Field(min_length=1, max_length=10000)
    language: Literal["shell", "python", "javascript"]
    timeout_s: int = Field(ge=1, le=900)


class ServiceStart(BaseModel):
    port: int = Field(ge=1024, le=65535)
    command: str = Field(min_length=1, max_length=2000)
    mode: Literal["base", "root"] = "base"


@app.get("/sessions/{key}", dependencies=[Depends(require_runner_token)])
async def session_status(key: str) -> dict:
    with _session_errors():
        info = await sessions.inspect(key)
        services = (
            (await sessions.agent(key, "services", {})).get("services", [])
            if info.running and info.kind == "workspace"
            else []
        )
    return {
        "running": info.running,
        "nonce": info.nonce,
        "kind": info.kind,
        "egress": info.egress,
        "services": services,
        "limits": session_limits(info.kind),
    }


@app.put("/sessions/{key}", dependencies=[Depends(require_runner_token)])
async def session_start(key: str, body: SessionStart) -> dict:
    with _session_errors():
        info = await sessions.start(key, body.nonce, body.kind, body.preview_prefix)
    return {"running": True, "nonce": info.nonce, "kind": info.kind, "egress": info.egress}


@app.delete("/sessions/{key}", dependencies=[Depends(require_runner_token)])
async def session_stop(key: str) -> dict:
    with _session_errors():
        await sessions.stop(key)
    return {"running": False}


async def _agent_call(key: str, command: str, request: Request, limit: int, timeout: float):
    payload = json.loads(await _body(request, limit) or b"{}")
    if not isinstance(payload, dict):
        raise HTTPException(422, "Invalid request")
    with _session_errors():
        reply = await sessions.agent(key, command, payload, timeout=timeout)
    if reply.get("error") == "failed":
        raise HTTPException(422, str(reply.get("detail", "Sandbox request failed"))[:300])
    return reply


@app.post("/sessions/{key}/manifest", dependencies=[Depends(require_runner_token)])
async def session_manifest(key: str, request: Request) -> dict:
    return cast(dict, await _agent_call(key, "manifest", request, 1024, 120))


@app.post("/sessions/{key}/sync", dependencies=[Depends(require_runner_token)])
async def session_sync(key: str, request: Request) -> dict:
    return cast(dict, await _agent_call(key, "sync", request, 24 * 1024 * 1024, 120))


@app.post("/sessions/{key}/export", dependencies=[Depends(require_runner_token)])
async def session_export(key: str, request: Request) -> dict:
    return cast(dict, await _agent_call(key, "export", request, 4 * 1024 * 1024, 120))


@app.post("/sessions/{key}/exec", dependencies=[Depends(require_runner_token)])
async def session_exec(key: str, body: SessionExec) -> dict:
    with _session_errors():
        reply = await sessions.agent(key, "exec", body.model_dump(), timeout=body.timeout_s + 30)
    if reply.get("error"):
        raise HTTPException(422, str(reply.get("detail", "Command failed to start"))[:300])
    return reply


@app.post("/sessions/{key}/services", dependencies=[Depends(require_runner_token)])
async def service_start(key: str, body: ServiceStart) -> dict:
    with _session_errors():
        reply = await sessions.agent(key, "service-start", body.model_dump(), timeout=30)
    sessions.modes[(key, body.port)] = body.mode
    if reply.get("error"):
        raise HTTPException(422, str(reply.get("detail", "Service failed to start"))[:300])
    return reply


@app.delete("/sessions/{key}/services/{port}", dependencies=[Depends(require_runner_token)])
async def service_stop(key: str, port: int) -> dict:
    with _session_errors():
        reply = await sessions.agent(key, "service-stop", {"port": port}, timeout=30)
        bridge = sessions.bridges.pop((key, port), None)
        if bridge is not None:
            await bridge.close()
    sessions.modes.pop((key, port), None)
    return reply


@app.get("/sessions/{key}/services/{port}/logs", dependencies=[Depends(require_runner_token)])
async def service_logs(key: str, port: int) -> dict:
    with _session_errors():
        return await sessions.agent(key, "service-logs", {"port": port}, timeout=30)


@app.api_route(
    "/sessions/{key}/proxy/{port}/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    dependencies=[Depends(require_runner_token)],
)
async def session_proxy(key: str, port: int, path: str, request: Request):
    """Forward one HTTP request to a dev server inside the session."""
    if not 1024 <= port <= 65535:
        raise HTTPException(404, "Unknown port")
    prefix = request.headers.get("x-mizan-prefix", "")
    body = await _body(request, 10 * 1024 * 1024)
    with _session_errors():
        await sessions.require(key, request.headers.get("x-mizan-nonce", ""))
        # The backend passes the raw (still percent-encoded) path and query.
        target = request.headers.get("x-mizan-target") or "/" + path
        if (
            not target.startswith("/")
            or len(target) > 8192
            or not target.isprintable()
            or " " in target
        ):
            raise SessionError(400, "Invalid preview path")
        if await sessions.mode(key, port) == "root" and prefix and target.startswith(prefix):
            target = target[len(prefix) :] or "/"
            if not target.startswith("/"):
                target = "/" + target
        elif not request.headers.get("x-mizan-target") and request.url.query:
            target += "?" + request.url.query
        bridge = await sessions.bridge(key, port)
        forwarded = [
            (name, value)
            for name, value in request.headers.items()
            if name.lower()
            in {
                "accept",
                "accept-language",
                "accept-encoding",
                "content-type",
                "if-none-match",
                "if-modified-since",
                "range",
                "user-agent",
                "cache-control",
                "x-requested-with",
            }
        ]
        status, headers, chunks = await http_through(
            bridge, request.method, target, forwarded, body
        )
    return StreamingResponse(chunks, status_code=status, headers=dict(headers))


@app.websocket("/sessions/{key}/terminal")
async def session_terminal(websocket: WebSocket, key: str):
    """Interactive shell: binary frames carry bytes, text frames carry resize JSON."""
    if not _token_ok(websocket.headers.get("authorization")):
        await websocket.close(code=4401)
        return
    try:
        await sessions.require(key)
    except SessionError:
        await websocket.close(code=4404)
        return
    if sessions.terminals.get(key, 0) >= 4:
        await websocket.close(code=4429)
        return
    await websocket.accept()
    sessions.terminals[key] = sessions.terminals.get(key, 0) + 1
    terminal = Terminal(name_of(key))
    try:
        await terminal.start(
            int(websocket.query_params.get("cols", 100)),
            int(websocket.query_params.get("rows", 30)),
        )

        async def pump_out() -> None:
            async for chunk in terminal.output():
                sessions.touch(key)
                await websocket.send_bytes(chunk)
            await websocket.close()

        out = asyncio.create_task(pump_out())
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                sessions.touch(key)
                if message.get("bytes"):
                    terminal.write(message["bytes"])
                elif message.get("text"):
                    with contextlib.suppress(ValueError, TypeError, KeyError):
                        control = json.loads(message["text"])
                        if control.get("type") == "resize":
                            terminal.resize(control["cols"], control["rows"])
                        elif control.get("type") == "input":
                            terminal.write(str(control["data"]).encode())
        finally:
            out.cancel()
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        await terminal.close()
        sessions.terminals[key] = max(0, sessions.terminals.get(key, 1) - 1)


@app.websocket("/sessions/{key}/stdio")
async def session_stdio(websocket: WebSocket, key: str):
    """Pipe a stdio MCP server: one JSON-RPC message per text frame."""
    if not _token_ok(websocket.headers.get("authorization")):
        await websocket.close(code=4401)
        return
    try:
        await sessions.require(key)
    except SessionError:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    process = None
    try:
        start = json.loads(await websocket.receive_text())
        argv = [str(item) for item in start.get("argv", [])][:41]
        env = {str(k): str(v) for k, v in (start.get("env") or {}).items()}
        if not argv or any(len(item) > 1000 for item in argv):
            await websocket.close(code=4422)
            return
        process = await stdio_process(name_of(key), argv, env)
        assert process.stdin and process.stdout

        async def pump_out() -> None:
            assert process and process.stdout
            while line := await process.stdout.readline():
                sessions.touch(key)
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    await websocket.send_text(text)
            await websocket.close(code=1000)

        out = asyncio.create_task(pump_out())
        try:
            while True:
                text = await websocket.receive_text()
                sessions.touch(key)
                process.stdin.write(text.replace("\n", " ").encode() + b"\n")
                await process.stdin.drain()
        finally:
            out.cancel()
    except (WebSocketDisconnect, RuntimeError, OSError, ValueError, SessionError):
        pass
    finally:
        if process is not None and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
