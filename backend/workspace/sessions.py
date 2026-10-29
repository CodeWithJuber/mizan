"""Persistent workspace sessions on the runner's dedicated Docker daemon.

A session is one long-lived, hardened container per (user, project): a disk
volume at /workspace, no capabilities, read-only root, an unprivileged user and
resource limits. Its only network is an internal Docker network whose single
exit is the allowlisting egress proxy (or no network at all). The runner talks
to it exclusively through ``docker exec``: JSON calls to /session_agent.py, a
framed TCP bridge for dev-server previews, a PTY for terminals and plain
stdio for MCP servers. Nothing in a session can reach the runner or backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import logging
import os
import pty
import re
import signal
import struct
import termios
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.workspace.sessions")

KEY = re.compile(r"^[0-9a-f]{32}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")
PREFIX = "mizan-session-"
NETWORK_PREFIX = "mizan-session-net-"
EGRESS = "mizan-sandbox-egress"
AGENT = ["python3", "-I", "/session_agent.py"]
# /tmp is noexec; caches live on the session volume (never synced), where native
# addons a package unpacks into its cache (@swc/core) can run.
SESSION_CACHE = "/workspace/.cache"
MAX_REPLY = 40 * 1024 * 1024
FRAME = struct.Struct(">IBI")
OPEN, DATA, CLOSE, FAIL = 1, 2, 3, 4
MAX_TERMINALS = 4


class SessionError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def limits(kind: str) -> dict[str, str]:
    if kind == "mcp":
        return {
            "memory": setting("MIZAN_MCP_SESSION_MEMORY", "384m"),
            "cpus": setting("MIZAN_MCP_SESSION_CPUS", "0.5"),
            "pids": setting("MIZAN_MCP_SESSION_PIDS", "128"),
            "max": setting("MIZAN_MCP_SESSION_MAX", "4"),
        }
    return {
        "memory": setting("MIZAN_SESSION_MEMORY", "768m"),
        "cpus": setting("MIZAN_SESSION_CPUS", "1"),
        "pids": setting("MIZAN_SESSION_PIDS", "256"),
        "max": setting("MIZAN_SESSION_MAX", "2"),
    }


def egress_enabled() -> bool:
    return setting("MIZAN_SANDBOX_EGRESS", "allowlist").lower() == "allowlist"


def idle_seconds() -> int:
    try:
        return max(60, int(setting("MIZAN_SESSION_IDLE_SECONDS", "1800")))
    except ValueError:
        return 1800


def runtime_image() -> str:
    return os.getenv("MIZAN_WORKSPACE_RUNTIME_IMAGE", "mizan-workspace-runtime:v1")


def docker_env() -> dict[str, str]:
    allowed = ("PATH", "DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONFIG")
    return {name: os.environ[name] for name in allowed if name in os.environ}


def name_of(key: str) -> str:
    if not KEY.fullmatch(key):
        raise SessionError(404, "Session not found")
    return PREFIX + key


async def docker(
    *args: str, payload: bytes | None = None, timeout: float = 30, limit: int = MAX_REPLY
) -> tuple[int, bytes, bytes]:
    """Run the Docker CLI with bounded output; never through a shell."""
    process = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdin=asyncio.subprocess.PIPE if payload is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=docker_env(),
    )

    async def read(stream: asyncio.StreamReader | None, cap: int) -> bytes:
        data = bytearray()
        while stream is not None and (chunk := await stream.read(65536)):
            if len(data) < cap + 1:
                data.extend(chunk[: cap + 1 - len(data)])
        return bytes(data)

    async def feed() -> None:
        if process.stdin is None:
            return
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            if payload:
                process.stdin.write(payload)
                await process.stdin.drain()
        process.stdin.close()

    try:
        _, out, err = await asyncio.wait_for(
            asyncio.gather(feed(), read(process.stdout, limit), read(process.stderr, 16384)),
            timeout,
        )
        code = await asyncio.wait_for(process.wait(), 10)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise SessionError(504, "The sandbox did not answer in time") from None
    if len(out) > limit:
        raise SessionError(502, "The sandbox reply exceeded the allowed size")
    return code, out, err


@dataclass
class SessionInfo:
    key: str
    running: bool
    nonce: str = ""
    kind: str = "workspace"
    egress: bool = False


class Sessions:
    """Session lifecycle plus the live bridges and terminals that use them."""

    def __init__(self) -> None:
        self.activity: dict[str, float] = {}
        self.bridges: dict[tuple[str, int], Bridge] = {}
        self.modes: dict[tuple[str, int], str] = {}
        self.terminals: dict[str, int] = {}
        self._start_lock = asyncio.Lock()

    def touch(self, key: str) -> None:
        self.activity[key] = time.monotonic()

    async def inspect(self, key: str) -> SessionInfo:
        code, out, _ = await docker(
            "inspect", "--format", "{{json .State.Running}} {{json .Config.Labels}}", name_of(key)
        )
        if code != 0:
            return SessionInfo(key, False)
        running, _, labels_raw = out.decode().strip().partition(" ")
        labels = json.loads(labels_raw or "{}") or {}
        return SessionInfo(
            key,
            running == "true",
            labels.get("mizan.nonce", ""),
            labels.get("mizan.kind", "workspace"),
            labels.get("mizan.egress") == "allowlist",
        )

    async def running(self, kind: str | None = None) -> list[str]:
        args = ["ps", "--filter", "label=mizan.session", "--format", "{{.Names}}"]
        if kind:
            args += ["--filter", f"label=mizan.kind={kind}"]
        code, out, _ = await docker(*args)
        if code != 0:
            raise SessionError(503, "The sandbox daemon is unavailable")
        return [
            line.removeprefix(PREFIX) for line in out.decode().split() if line.startswith(PREFIX)
        ]

    async def ensure_proxy(self) -> None:
        code, out, _ = await docker("inspect", "--format", "{{.State.Running}}", EGRESS)
        if code != 0 or out.strip() != b"true":
            await docker("rm", "-f", EGRESS)
            allow = os.getenv("MIZAN_SANDBOX_EGRESS_ALLOW", "")
            code, _, err = await docker(
                "run", "-d", "--pull", "never", "--name", EGRESS, "--restart", "unless-stopped",
                "--init", "--user", "65534:65534", "--cap-drop", "ALL", "--read-only",
                "--security-opt", "no-new-privileges", "--memory", "128m", "--memory-swap", "128m",
                "--pids-limit", "64", "--network", "bridge",
                "--env", f"MIZAN_SANDBOX_EGRESS_ALLOW={allow}",
                "--label", "mizan.egress=proxy",
                runtime_image(), "python3", "-I", "/egress_proxy.py", "3128",
            )  # fmt: skip
            if code != 0:
                logger.warning("egress proxy failed: %s", err[:300])
                raise SessionError(503, "Could not start the sandbox egress proxy")

    async def ensure_network(self, key: str) -> str:
        """One internal network per session: its only peer is the egress proxy."""
        network = NETWORK_PREFIX + key
        await self.ensure_proxy()
        code, _, err = await docker("network", "create", "--internal", network)
        if code != 0 and b"already exists" not in err:
            raise SessionError(503, "Could not create the sandbox network")
        code, _, err = await docker("network", "connect", "--alias", "egress", network, EGRESS)
        if code != 0 and b"already exists" not in err and b"already attached" not in err:
            raise SessionError(503, "Could not attach the egress proxy")
        return network

    async def remove_network(self, key: str) -> None:
        network = NETWORK_PREFIX + key
        await docker("network", "disconnect", "-f", network, EGRESS)
        await docker("network", "rm", network)

    async def start(self, key: str, nonce: str, kind: str, preview_prefix: str) -> SessionInfo:
        name = name_of(key)
        if not NONCE.fullmatch(nonce) or kind not in {"workspace", "mcp"}:
            raise SessionError(422, "Invalid session request")
        if not re.fullmatch(r"(/[A-Za-z0-9._~-]+)*", preview_prefix) or len(preview_prefix) > 300:
            raise SessionError(422, "Invalid preview prefix")
        async with self._start_lock:
            current = await self.inspect(key)
            if current.running:
                self.touch(key)
                return current
            await docker("rm", "-f", name)
            budget = limits(kind)
            if len(await self.running(kind)) >= int(budget["max"]):
                raise SessionError(429, "All sandbox sessions are busy; try again later")
            egress = egress_enabled()
            network = await self.ensure_network(key) if egress else "none"
            proxy = "http://egress:3128" if egress else ""
            args = [
                "run", "-d", "--pull", "never", "--name", name, "--hostname", "sandbox",
                "--init", "--user", "65534:65534", "--cap-drop", "ALL", "--read-only",
                "--security-opt", "no-new-privileges",
                "--network", network,
                "--cpus", budget["cpus"], "--memory", budget["memory"],
                "--memory-swap", budget["memory"], "--pids-limit", budget["pids"],
                "--ulimit", "nofile=4096:4096",
                "--mount", f"type=volume,src={name},dst=/workspace",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
                "--label", f"mizan.session={key}", "--label", f"mizan.nonce={nonce}",
                "--label", f"mizan.kind={kind}",
                "--label", f"mizan.egress={'allowlist' if egress else 'off'}",
                "--env", f"HTTP_PROXY={proxy}", "--env", f"HTTPS_PROXY={proxy}",
                "--env", f"http_proxy={proxy}", "--env", f"https_proxy={proxy}",
                "--env", "NO_PROXY=localhost,127.0.0.1", "--env", "no_proxy=localhost,127.0.0.1",
                "--env", f"MIZAN_PREVIEW_PREFIX={preview_prefix}",
                "--env", "TERM=xterm-256color", "--env", "HOME=/tmp/home",
                "--env", f"XDG_CACHE_HOME={SESSION_CACHE}",
                runtime_image(), "sleep", "infinity",
            ]  # fmt: skip
            code, _, err = await docker(*args, timeout=60)
            if code != 0:
                logger.warning("session start failed: %s", err[:300])
                await docker("rm", "-f", name)
                if egress:
                    await self.remove_network(key)
                raise SessionError(503, "The sandbox could not start a session")
            self.touch(key)
            return SessionInfo(key, True, nonce, kind, egress)

    async def stop(self, key: str) -> None:
        name = name_of(key)
        for bridge_key in [item for item in self.bridges if item[0] == key]:
            await self.bridges.pop(bridge_key).close()
        for mode_key in [item for item in self.modes if item[0] == key]:
            self.modes.pop(mode_key, None)
        self.activity.pop(key, None)
        await docker("rm", "-f", name, timeout=30)
        await docker("volume", "rm", "-f", name, timeout=30)
        await self.remove_network(key)

    async def require(self, key: str, nonce: str | None = None) -> SessionInfo:
        info = await self.inspect(key)
        if not info.running or (nonce is not None and nonce != info.nonce):
            raise SessionError(404, "No running sandbox session")
        self.touch(key)
        return info

    async def agent(self, key: str, command: str, request: dict, timeout: float = 60) -> dict:
        await self.require(key)
        code, out, err = await docker(
            "exec", "-i", name_of(key), *AGENT, command,
            payload=json.dumps(request).encode(), timeout=timeout,
        )  # fmt: skip
        if code != 0:
            logger.warning("session agent %s failed: %s", command, err[:300])
            raise SessionError(503, "The sandbox session did not respond")
        try:
            reply = json.loads(out)
        except ValueError:
            raise SessionError(502, "Invalid sandbox reply") from None
        if not isinstance(reply, dict):
            raise SessionError(502, "Invalid sandbox reply")
        return reply

    async def bridge(self, key: str, port: int) -> Bridge:
        bridge = self.bridges.get((key, port))
        if bridge is None or not bridge.alive:
            if bridge is not None:
                await bridge.close()
            bridge = Bridge(name_of(key), port)
            await bridge.start()
            self.bridges[(key, port)] = bridge
        return bridge

    async def mode(self, key: str, port: int) -> str:
        if (key, port) not in self.modes:
            services = (await self.agent(key, "services", {})).get("services", [])
            found: dict = next((item for item in services if item.get("port") == port), {})
            self.modes[(key, port)] = "root" if found.get("mode") == "root" else "base"
        return self.modes[(key, port)]

    async def reap(self) -> None:
        now = time.monotonic()
        try:
            alive = set(await self.running())
        except SessionError:
            return
        for key in alive:
            self.activity.setdefault(key, now)
            if now - self.activity[key] > idle_seconds() and not self.terminals.get(key):
                logger.info("stopping idle sandbox session %s", key[:8])
                await self.stop(key)
        for (key, port), bridge in list(self.bridges.items()):
            if key not in alive or now - bridge.used > 600:
                await self.bridges.pop((key, port)).close()

    async def reaper(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self.reap()
            except Exception:  # noqa: BLE001 - keep the reaper alive
                logger.exception("sandbox reaper failed")


# ── Framed TCP bridge (runner side) ──────────────────────────────────────


@dataclass
class _Stream:
    queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    failed: bool = False


class Bridge:
    """One ``session_agent.py bridge`` process carrying many TCP streams."""

    def __init__(self, container: str, port: int):
        self.container = container
        self.port = port
        self.process: asyncio.subprocess.Process | None = None
        self.streams: dict[int, _Stream] = {}
        self.next_id = 1
        self.lock = asyncio.Lock()
        self.reader: asyncio.Task | None = None
        self.used = time.monotonic()

    @property
    def alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", self.container, *AGENT, "bridge", str(self.port),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=docker_env(), limit=4 * 1024 * 1024,
        )  # fmt: skip
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        assert self.process and self.process.stdout
        try:
            while True:
                header = await self.process.stdout.readexactly(FRAME.size)
                stream_id, kind, length = FRAME.unpack(header)
                if length > 2 * 1024 * 1024:
                    break
                payload = await self.process.stdout.readexactly(length) if length else b""
                stream = self.streams.get(stream_id)
                if stream is None:
                    continue
                if kind == DATA:
                    stream.queue.put_nowait(payload)
                elif kind in (CLOSE, FAIL):
                    stream.failed = kind == FAIL
                    stream.queue.put_nowait(None)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            for stream in self.streams.values():
                stream.queue.put_nowait(None)

    async def send(self, stream_id: int, kind: int, payload: bytes = b"") -> None:
        if not self.alive or self.process is None or self.process.stdin is None:
            raise SessionError(502, "The preview bridge closed")
        async with self.lock:
            for start in range(0, max(len(payload), 1), 1024 * 1024):
                chunk = payload[start : start + 1024 * 1024]
                self.process.stdin.write(FRAME.pack(stream_id, kind, len(chunk)) + chunk)
                await self.process.stdin.drain()

    async def open(self) -> int:
        self.used = time.monotonic()
        stream_id = self.next_id
        self.next_id = (self.next_id % 0xFFFFFFF0) + 1
        self.streams[stream_id] = _Stream()
        await self.send(stream_id, OPEN)
        return stream_id

    async def read(self, stream_id: int, timeout: float = 120) -> bytes | None:
        stream = self.streams[stream_id]
        try:
            item = await asyncio.wait_for(stream.queue.get(), timeout)
        except TimeoutError:
            raise SessionError(504, "The dev server did not answer in time") from None
        if item is None and stream.failed:
            raise SessionError(502, f"Nothing is listening on port {self.port} in the session")
        return item

    async def release(self, stream_id: int) -> None:
        if self.streams.pop(stream_id, None) is not None and self.alive:
            with contextlib.suppress(SessionError, ConnectionError):
                await self.send(stream_id, CLOSE)

    async def close(self) -> None:
        if self.process is not None and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.kill()
            await self.process.wait()
        if self.reader is not None:
            self.reader.cancel()


_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


async def http_through(
    bridge: Bridge, method: str, target: str, headers: list[tuple[str, str]], body: bytes
) -> tuple[int, list[tuple[str, str]], AsyncIterator[bytes]]:
    """Send one HTTP/1.1 request over a bridge stream and stream the response."""
    import h11

    connection = h11.Connection(h11.CLIENT)
    outgoing = [("Host", f"localhost:{bridge.port}"), ("Connection", "close")]
    outgoing += [(k, v) for k, v in headers if k.lower() not in _HOP_BY_HOP]
    if body or method in {"POST", "PUT", "PATCH"}:
        outgoing.append(("Content-Length", str(len(body))))
    stream_id = await bridge.open()
    try:
        data = connection.send(h11.Request(method=method, target=target, headers=outgoing))
        if body:
            data += connection.send(h11.Data(data=body))
        data += connection.send(h11.EndOfMessage())
        await bridge.send(stream_id, DATA, data)
        while True:
            event = connection.next_event()
            if event is h11.NEED_DATA:
                connection.receive_data(await bridge.read(stream_id) or b"")
                continue
            if isinstance(event, h11.InformationalResponse):
                continue
            if isinstance(event, h11.Response):
                break
            raise SessionError(502, "The dev server closed the connection")
    except h11.ProtocolError:
        await bridge.release(stream_id)
        raise SessionError(502, "The dev server sent an invalid response") from None
    except BaseException:
        await bridge.release(stream_id)
        raise
    status = event.status_code
    response_headers = [
        (key.decode("latin-1"), value.decode("latin-1"))
        for key, value in event.headers
        if key.decode("latin-1").lower() not in _HOP_BY_HOP - {"content-length"}
    ]

    async def body_iterator() -> AsyncIterator[bytes]:
        try:
            while True:
                item = connection.next_event()
                if item is h11.NEED_DATA:
                    connection.receive_data(await bridge.read(stream_id) or b"")
                    continue
                if isinstance(item, h11.Data):
                    yield bytes(item.data)
                    continue
                break
        except h11.ProtocolError:
            return
        finally:
            await bridge.release(stream_id)

    return status, response_headers, body_iterator()


# ── Terminals and stdio ───────────────────────────────────────────────────


class Terminal:
    """``docker exec -it`` on a private PTY; bytes in, bytes out."""

    def __init__(self, container: str):
        self.container = container
        self.master = -1
        self.process: asyncio.subprocess.Process | None = None

    async def start(self, cols: int = 100, rows: int = 30) -> None:
        master, slave = pty.openpty()
        self.master = master
        self.resize(cols, rows)

        # The CLI only needs a TTY on its stdio; resizes are signalled explicitly.
        self.process = await asyncio.create_subprocess_exec(
            "docker", "exec", "-it", "-w", "/workspace", "-e", "TERM=xterm-256color",
            "-e", "HOME=/tmp/home", self.container, "/bin/bash", "-l",
            stdin=slave, stdout=slave, stderr=slave, env=docker_env(), start_new_session=True,
        )  # fmt: skip
        os.close(slave)
        os.set_blocking(master, False)

    def resize(self, cols: int, rows: int) -> None:
        cols, rows = max(10, min(int(cols), 500)), max(4, min(int(rows), 200))
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        if self.process is not None and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.send_signal(signal.SIGWINCH)

    async def output(self) -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        while True:
            ready: asyncio.Future[None] = loop.create_future()
            loop.add_reader(self.master, ready.set_result, None)
            try:
                await ready
            finally:
                loop.remove_reader(self.master)
            try:
                chunk = os.read(self.master, 65536)
            except BlockingIOError:
                continue
            except OSError:
                return
            if not chunk:
                return
            yield chunk

    def write(self, data: bytes) -> None:
        view = memoryview(data[:65536])
        while view:
            try:
                written = os.write(self.master, view)
            except BlockingIOError:
                continue
            view = view[written:]

    async def close(self) -> None:
        if self.process is not None and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.kill()
            await self.process.wait()
        if self.master >= 0:
            with contextlib.suppress(OSError):
                os.close(self.master)
            self.master = -1


async def stdio_process(container: str, argv: list[str], env: dict[str, str]):
    """Start an MCP stdio server inside a session container."""
    args = ["exec", "-i", "-w", "/workspace"]
    for key, value in env.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key) or len(value) > 4096:
            raise SessionError(422, "Invalid environment variable")
        args += ["-e", f"{key}={value}"]
    return await asyncio.create_subprocess_exec(
        "docker", *args, container, *argv,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=docker_env(), limit=8 * 1024 * 1024,
    )  # fmt: skip


sessions = Sessions()
