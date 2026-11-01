"""Session helper. Runs only INSIDE a workspace session container.

The runner calls ``docker exec -i <session> python3 /session_agent.py <command>``
with a JSON request on stdin and reads one JSON reply from stdout. ``bridge``
instead multiplexes TCP connections to a port inside the container over
stdin/stdout so the runner can reach dev servers without any network path.

Stdlib only: the same file is imported by the backend for the shared rules.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import shutil
import signal
import stat
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(os.getenv("MIZAN_SESSION_ROOT", "/workspace"))
STATE = Path(os.getenv("MIZAN_SESSION_STATE", "/tmp/mizan"))
# Dependency, build and cache folders stay in the session; they are never synced.
HEAVY = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".cache",
        "dist",
        "build",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".parcel-cache",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "coverage",
        "target",
    }
)
MAX_WALK = 20000
MAX_OUTPUT = 100000
LOG_BYTES = 256 * 1024
FRAME = struct.Struct(">IBI")
OPEN, DATA, CLOSE, FAIL = 1, 2, 3, 4
MAX_FRAME = 1024 * 1024


def heavy(path: str) -> bool:
    return any(part in HEAVY for part in path.split("/"))


def safe_path(path: str) -> Path:
    pieces = path.split("/")
    if len(path) > 512 or any(
        item in {"", ".", ".."} or "\\" in item or "\x00" in item for item in pieces
    ):
        raise ValueError("Invalid project path")
    return ROOT.joinpath(*pieces)


def command_env() -> dict[str, str]:
    passed = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "MIZAN_PREVIEW_PREFIX",
        "TERM",
    )
    env = {name: os.environ[name] for name in passed if name in os.environ}
    env.update(
        PATH=f"{ROOT}/.cache/python-user/bin:{ROOT}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
        HOME="/tmp/home",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        PIP_CACHE_DIR=f"{ROOT}/.cache/pip",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        npm_config_cache=f"{ROOT}/.cache/npm",
        # /tmp is noexec; caches and user installs live on the volume (see sessions.SESSION_ENV).
        XDG_CACHE_HOME=f"{ROOT}/.cache",
        PYTHONUSERBASE=f"{ROOT}/.cache/python-user",
        npm_config_update_notifier="false",
        npm_config_fund="false",
        npm_config_audit="false",
        MPLBACKEND="Agg",
        MPLCONFIGDIR="/tmp/matplotlib",
    )
    return env


def walk() -> tuple[dict[str, os.stat_result], list[str], list[str], bool]:
    """Regular files and folders outside dependency/build folders."""
    files: dict[str, os.stat_result] = {}
    directories: list[str] = []
    skipped: list[str] = []
    seen = 0
    for parent, names, filenames in os.walk(ROOT, followlinks=False):
        base = Path(parent).relative_to(ROOT)
        keep = []
        for name in sorted(names):
            relative = (base / name).as_posix()
            if name in HEAVY:
                continue
            if (Path(parent) / name).is_symlink():
                skipped.append(relative)
                continue
            keep.append(name)
            directories.append(relative)
        names[:] = keep
        for name in sorted(filenames):
            seen += 1
            if seen > MAX_WALK:
                return files, directories, skipped, True
            relative = (base / name).as_posix()
            info = (Path(parent) / name).lstat()
            if stat.S_ISREG(info.st_mode):
                files[relative] = info
            else:
                skipped.append(relative)
    return files, directories, skipped, False


def digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    sha = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as handle:
        while chunk := handle.read(1 << 16):
            sha.update(chunk)
    return sha.hexdigest()


def manifest(_request: dict) -> dict:
    files, directories, skipped, over = walk()
    return {
        "files": {path: digest(ROOT / path) for path in files},
        "directories": directories,
        "skipped": skipped[:100],
        "over_limit": over,
    }


def _clear(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def sync(request: dict) -> dict:
    written = removed = 0
    for directory in request.get("directories", []):
        target = safe_path(directory)
        if target.exists() and not target.is_dir():
            _clear(target)
        target.mkdir(parents=True, exist_ok=True)
    for path in request.get("delete", []):
        if heavy(path):
            continue
        target = safe_path(path)
        if target.exists() or target.is_symlink():
            _clear(target)
            removed += 1
    for path, encoded in request.get("files", {}).items():
        if heavy(path):
            continue
        target = safe_path(path)
        for parent in reversed(target.relative_to(ROOT).parents):
            node = ROOT / parent
            if node != ROOT and (node.is_symlink() or (node.exists() and not node.is_dir())):
                _clear(node)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        temporary = target.with_name(f".{target.name}.mizan-sync")
        temporary.write_bytes(base64.b64decode(encoded, validate=True))
        os.replace(temporary, target)
        written += 1
    return {"written": written, "removed": removed}


def export(request: dict) -> dict:
    """Files that differ from the caller's baseline manifest, within its quota."""
    baseline: dict[str, str] = request.get("baseline", {})
    max_files = int(request.get("max_files", 500))
    max_bytes = int(request.get("max_bytes", 10 * 1024 * 1024))
    max_file = int(request.get("max_file", 1024 * 1024))
    files, directories, skipped, over = walk()
    if over or len(files) + len(directories) > max_files:
        return {"error": "quota", "detail": f"More than {max_files} project entries"}
    total = sum(info.st_size for info in files.values())
    if total > max_bytes:
        return {"error": "quota", "detail": f"Project files exceed {max_bytes} bytes"}
    changed: dict[str, str] = {}
    for path, info in files.items():
        if info.st_size > max_file:
            return {"error": "quota", "detail": f"{path} exceeds {max_file} bytes"}
        if baseline.get(path) == digest(ROOT / path):
            continue
        changed[path] = base64.b64encode((ROOT / path).read_bytes()).decode("ascii")
    deleted = [path for path in baseline if not heavy(path) and path not in files]
    return {
        "files": changed,
        "deleted": deleted,
        "directories": directories,
        "skipped": skipped[:100],
    }


def _drain(pipe, target: bytearray, truncated: list[bool]) -> None:
    try:
        while chunk := pipe.read(32768):
            room = MAX_OUTPUT - len(target)
            target.extend(chunk[: max(0, room)])
            if len(chunk) > room:
                truncated[0] = True
    finally:
        pipe.close()


def run_command(request: dict) -> dict:
    command = {
        "shell": ["/bin/sh", "-lc", request["command"]],
        "python": ["python3", "-c", request["command"]],
        "javascript": ["node", "-e", request["command"]],
    }[request["language"]]
    os.makedirs("/tmp/home", exist_ok=True)
    retained = [bytearray(), bytearray()]
    truncated = [False]
    started = time.monotonic()
    with subprocess.Popen(
        command,
        cwd=ROOT,
        env=command_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as process:
        readers = [
            threading.Thread(target=_drain, args=(pipe, buffer, truncated), daemon=True)
            for pipe, buffer in zip((process.stdout, process.stderr), retained, strict=True)
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            exit_code = process.wait(timeout=int(request["timeout_s"]))
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, 124
        finally:
            # A command's stray background children end with it; use services
            # for long-running processes.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=5)
    return {
        "stdout": bytes(retained[0]).decode("utf-8", errors="replace"),
        "stderr": bytes(retained[1]).decode("utf-8", errors="replace"),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "truncated": truncated[0],
    }


# ── Services (dev servers) ────────────────────────────────────────────────


def _service_file(port: int) -> Path:
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    return STATE / "services" / f"{port}.json"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    with contextlib.suppress(OSError):
        status = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return status != "Z"
    return True


def service_list(_request: dict | None = None) -> dict:
    result = []
    folder = STATE / "services"
    for item in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            info = json.loads(item.read_text())
        except (OSError, ValueError):
            continue
        info["alive"] = _alive(int(info.get("pid", 0)))
        result.append(info)
    return {"services": result}


def service_stop(request: dict) -> dict:
    path = _service_file(int(request["port"]))
    if not path.exists():
        return {"stopped": False}
    info = json.loads(path.read_text())
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(int(info["pid"]), signal.SIGTERM)
        for _ in range(20):
            if not _alive(int(info["pid"])):
                break
            time.sleep(0.1)
        os.killpg(int(info["pid"]), signal.SIGKILL)
    path.unlink(missing_ok=True)
    return {"stopped": True}


def service_start(request: dict) -> dict:
    port = int(request["port"])
    path = _service_file(port)
    service_stop({"port": port})
    path.parent.mkdir(parents=True, exist_ok=True)
    command = str(request["command"])
    if not command or len(command) > 2000:
        raise ValueError("Invalid service command")
    mode = "root" if request.get("mode") == "root" else "base"
    supervisor = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "supervise", str(port), command],
        cwd=ROOT,
        env={
            **os.environ,
            **command_env(),
            "MIZAN_SESSION_ROOT": str(ROOT),
            "MIZAN_SESSION_STATE": str(STATE),
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    info = {"port": port, "pid": supervisor.pid, "command": command, "mode": mode}
    info["started_at"] = time.time()
    path.write_text(json.dumps(info))
    return info


def service_logs(request: dict) -> dict:
    port = int(request["port"])
    _service_file(port)
    log = STATE / "services" / f"{port}.log"
    try:
        text = log.read_bytes()[-int(request.get("bytes", 65536)) :]
    except FileNotFoundError:
        text = b""
    return {"port": port, "log": text.decode("utf-8", errors="replace")}


def supervise(port: int, command: str) -> None:
    """Run a service, keeping only the latest output in its log file."""
    os.makedirs("/tmp/home", exist_ok=True)
    log = STATE / "services" / f"{port}.log"
    ring = bytearray()
    lock = threading.Lock()
    child = subprocess.Popen(
        ["/bin/sh", "-lc", command],
        cwd=ROOT,
        env=command_env() | {"PORT": str(port)},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def read() -> None:
        assert child.stdout is not None
        while chunk := child.stdout.read1(65536):  # type: ignore[attr-defined]
            with lock:
                ring.extend(chunk)
                del ring[: max(0, len(ring) - LOG_BYTES)]

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    while True:
        finished = child.poll() is not None
        if finished:
            reader.join(timeout=2)
        with lock:
            data = bytes(ring)
        temporary = log.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, log)
        if finished:
            with lock:
                ring.extend(f"\n[exited with code {child.returncode}]\n".encode())
                log.write_bytes(bytes(ring))
            return
        time.sleep(1)


# ── TCP bridge ─────────────────────────────────────────────────────────────


async def bridge(port: int) -> None:
    """Multiplex connections to 127.0.0.1:<port> over stdin/stdout frames."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_FRAME * 2)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    transport, protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(transport, protocol, None, loop)
    lock = asyncio.Lock()
    queues: dict[int, asyncio.Queue[bytes | None]] = {}

    async def send(stream: int, kind: int, payload: bytes = b"") -> None:
        async with lock:
            writer.write(FRAME.pack(stream, kind, len(payload)) + payload)
            await writer.drain()

    async def serve(stream: int, queue: asyncio.Queue[bytes | None]) -> None:
        try:
            tcp_reader, tcp_writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), 10
            )
        except (OSError, TimeoutError):
            queues.pop(stream, None)
            await send(stream, FAIL)
            return

        async def upstream() -> None:
            while (item := await queue.get()) is not None:
                tcp_writer.write(item)
                await tcp_writer.drain()
            tcp_writer.close()

        forward = asyncio.create_task(upstream())
        try:
            while chunk := await tcp_reader.read(65536):
                await send(stream, DATA, chunk)
        except OSError:
            pass
        finally:
            forward.cancel()
            tcp_writer.close()
            queues.pop(stream, None)
            await send(stream, CLOSE)

    while True:
        try:
            header = await reader.readexactly(FRAME.size)
        except asyncio.IncompleteReadError:
            return
        stream, kind, length = FRAME.unpack(header)
        if length > MAX_FRAME:
            return
        payload = await reader.readexactly(length) if length else b""
        if kind == OPEN and stream not in queues:
            queues[stream] = asyncio.Queue()
            asyncio.create_task(serve(stream, queues[stream]))
        elif kind == DATA and stream in queues:
            queues[stream].put_nowait(payload)
        elif kind == CLOSE and stream in queues:
            queues[stream].put_nowait(None)


COMMANDS = {
    "manifest": manifest,
    "sync": sync,
    "export": export,
    "exec": run_command,
    "services": service_list,
    "service-start": service_start,
    "service-stop": service_stop,
    "service-logs": service_logs,
}


def main(argv: list[str]) -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    if argv[:1] == ["bridge"]:
        asyncio.run(bridge(int(argv[1])))
        return 0
    if argv[:1] == ["supervise"]:
        supervise(int(argv[1]), argv[2])
        return 0
    handler = COMMANDS.get(argv[0] if argv else "")
    if handler is None:
        print(json.dumps({"error": "unknown command"}))
        return 2
    request = json.loads(sys.stdin.buffer.read(32 * 1024 * 1024 + 1) or b"{}")
    try:
        reply = handler(request)
    except (OSError, ValueError, KeyError) as exc:
        reply = {"error": "failed", "detail": str(exc)[:500]}
    sys.stdout.write(json.dumps(reply))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
