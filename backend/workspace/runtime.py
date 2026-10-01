"""Trusted container bootstrap. This module only runs INSIDE an isolated job container."""

from __future__ import annotations

import base64
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

MAX_FILE = 1024 * 1024
MAX_TOTAL = 10 * 1024 * 1024
MAX_FILES = 500
MAX_OUTPUT = 100000


def safe_path(path: str) -> Path:
    pieces = path.split("/")
    if len(path) > 512 or any(
        item in {"", ".", ".."} or "\\" in item or "\x00" in item for item in pieces
    ):
        raise ValueError("Invalid project path")
    return Path("/workspace").joinpath(*pieces)


def run(payload: dict) -> dict:
    files = payload["files"]
    if len(files) > MAX_FILES:
        raise ValueError("Project quota exceeded")
    total = 0
    for directory in payload.get("directories", []):
        safe_path(directory).mkdir(parents=True, exist_ok=True)
    for name, encoded in files.items():
        data = base64.b64decode(encoded, validate=True)
        total += len(data)
        if len(data) > MAX_FILE or total > MAX_TOTAL:
            raise ValueError("Project quota exceeded")
        path = safe_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    command = {
        "shell": ["/bin/sh", "-lc", payload["command"]],
        "python": ["python3", "-c", payload["command"]],
        "javascript": ["node", "-e", payload["command"]],
    }[payload["language"]]
    retained = [bytearray(), bytearray()]
    truncated = [False]

    def drain(pipe, target):
        try:
            while chunk := pipe.read(32768):
                room = MAX_OUTPUT - len(target)
                target.extend(chunk[: max(0, room)])
                if len(chunk) > room:
                    truncated[0] = True
        finally:
            pipe.close()

    started = time.monotonic()
    with subprocess.Popen(
        command,
        cwd="/workspace",
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as process:
        readers = [
            threading.Thread(target=drain, args=(pipe, buffer), daemon=True)
            for pipe, buffer in zip((process.stdout, process.stderr), retained, strict=True)
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            exit_code = process.wait(timeout=payload["timeout_s"])
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
        finally:
            # Also kill detached background children after a successful shell command.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=5)
    output = {}
    output_directories = []
    export_error = False
    try:
        total = 0
        entries = 0
        for parent, directories, names in os.walk("/workspace", followlinks=False):
            for name in directories + names:
                entries += 1
                path = Path(parent) / name
                info = path.lstat()
                if entries > MAX_FILES or not (
                    stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
                ):
                    raise ValueError("Unsafe generated project entry")
                if stat.S_ISDIR(info.st_mode):
                    output_directories.append(str(path.relative_to("/workspace")))
                    continue
                if info.st_size > MAX_FILE:
                    raise ValueError("Generated file quota exceeded")
                total += info.st_size
                if total > MAX_TOTAL:
                    raise ValueError("Generated project quota exceeded")
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as handle:
                    data = handle.read(MAX_FILE + 1)
                if len(data) > MAX_FILE:
                    raise ValueError("Generated file quota exceeded")
                output[str(path.relative_to("/workspace"))] = base64.b64encode(data).decode("ascii")
    except (OSError, ValueError):
        export_error = True
        output = {}
        output_directories = []
    return {
        "stdout": bytes(retained[0]).decode("utf-8", errors="replace"),
        "stderr": bytes(retained[1]).decode("utf-8", errors="replace"),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "truncated": truncated[0],
        "files": output,
        "directories": output_directories,
        "export_error": export_error,
    }


if __name__ == "__main__":
    request = json.loads(sys.stdin.buffer.read(16 * 1024 * 1024 + 1))
    print(json.dumps(run(request)), flush=True)
