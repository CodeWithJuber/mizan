#!/usr/bin/env python3
"""Bounded, read-only diagnostics for the single authorized QA chat stream.

Raw Docker logs, Nginx configuration, environment values and message content
are never printed. The database child imports no application modules.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import resource
import selectors
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

START = "2026-10-26T06:24:00Z"
END = "2026-10-26T06:28:00Z"
QA_TEXT = (
    "Verification 107: 2 + 2 kitna hota hai? Hinglish mein ek line ka jawab do. "
    "Koi tool mat chalao."
)
DOCKER = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)?\Z")
STATES = {"accepted", "running", "complete", "cancelled", "error", "rejected", "failed"}
COMPLETIONS = {
    "complete",
    "incomplete",
    "failed",
    "empty_response",
    "missing_receipt",
    "unverified_answer",
}
MAX_GRAPH_BYTES = 64 * 1024 * 1024
CHILD_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024
CODES = {"delivery_stopped", "stream_failed", "agent_failed", "output_budget_exhausted"}
STACK_FILES = (
    "api/main.py",
    "api/chat_stream.py",
    "agents/base.py",
    "providers.py",
    "starlette/responses.py",
    "starlette/middleware/base.py",
    "starlette/requests.py",
    "anyio/_backends/_asyncio.py",
    "asyncio/tasks.py",
    "asyncio/timeouts.py",
    "asyncio/queues.py",
    "httpx/_client.py",
    "httpx/_transports/default.py",
    "httpcore/_async/connection_pool.py",
    "httpcore/_async/http11.py",
    "httpcore/_async/connection.py",
    "openai/_base_client.py",
    "openai/_streaming.py",
    "uvicorn/protocols/http/httptools_impl.py",
    "uvicorn/protocols/http/h11_impl.py",
)
LOG_CATEGORIES = {
    "cancelled_error": ("CancelledError",),
    "client_disconnect": (
        "ClientDisconnect",
        "client disconnected",
        "client prematurely closed",
    ),
    "end_of_stream": ("EndOfStream",),
    "transport_deadline": ("Chat transport exceeded the delivery deadline",),
    "slow_reader": ("Chat reader is too slow",),
    "delivery_stopped": ("Chat delivery stopped", "Chat delivery was interrupted"),
    "response_limit": ("Chat response exceeds the output limit",),
    "event_limit": ("Chat event exceeds the delivery limit",),
    "cancelled_reader_unavailable": ("Cancelled chat reader unavailable",),
    "chat_stream_failed": ("Chat stream failed for message",),
    "provider_stream_fallback": ("[FIKR] Streaming failed",),
    "provider_timeout": (
        "APITimeoutError",
        "ReadTimeout",
        "ConnectTimeout",
        "PoolTimeout",
    ),
    "timeout_error": ("TimeoutError", "timed out"),
    "connection_error": (
        "APIConnectionError",
        "ConnectionResetError",
        "BrokenPipeError",
        "RemoteProtocolError",
    ),
    "os_error": ("OSError",),
    "database_busy": ("database is locked", "database table is locked", "SQLITE_BUSY"),
    "exception_group": ("ExceptionGroup",),
    "upstream_closed": (
        "upstream prematurely closed",
        "upstream timed out",
        "recv() failed",
    ),
    "worker_exit": (
        "Finished server process",
        "Shutting down",
        "Worker exiting",
        "worker process exited",
    ),
    "server_start": ("Started server process", "Application startup complete"),
    "oom_signal": ("out of memory", "oom-kill", "OOMKilled"),
}


def run(
    args: list[str],
    *,
    stdin: str | None = None,
    timeout: float = 25,
    maximum: int = 4 * 1024 * 1024,
) -> tuple[int, str, str, bool]:
    """Drain bounded pipes without ever forwarding command diagnostics."""
    process = None
    buffers = {"out": bytearray(), "err": bytearray()}
    truncated = False
    code = -1
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env={
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C.UTF-8",
            },
        )
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "out")
            selector.register(process.stderr, selectors.EVENT_READ, "err")
            pending = memoryview(stdin.encode()) if stdin is not None else memoryview(b"")
            if stdin is not None:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "in")
            deadline = time.monotonic() + timeout
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    code = -2
                    break
                for key, _ in selector.select(min(remaining, 0.25)):
                    if key.data == "in":
                        if pending:
                            written = os.write(key.fileobj.fileno(), pending[:4096])
                            pending = pending[written:]
                        if not pending:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        continue
                    chunk = os.read(key.fileobj.fileno(), 16384)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = maximum - sum(len(value) for value in buffers.values())
                    buffers[key.data].extend(chunk[:available])
                    if len(chunk) > available:
                        truncated, code = True, -3
                        break
                if truncated:
                    break
            else:
                code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except (OSError, subprocess.TimeoutExpired):
        code = -1
    finally:
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=3)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    return (
        code,
        buffers["out"].decode("utf-8", "replace"),
        buffers["err"].decode("utf-8", "replace"),
        truncated,
    )


def safe_timestamp(value):
    return value if isinstance(value, str) and TIMESTAMP.fullmatch(value) else None


def safe_number(value):
    return (
        value
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e12
        else None
    )


def selected_container(item: dict) -> dict:
    state = item.get("State", {})
    host = item.get("HostConfig", {})
    health = state.get("Health", {}).get("Status")
    image = item.get("Image", "")
    return {
        "image_id": image if re.fullmatch(r"sha256:[0-9a-f]{64}", image) else None,
        "status": state.get("Status")
        if state.get("Status")
        in {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
        else None,
        "running": state.get("Running") is True,
        "started_at": safe_timestamp(state.get("StartedAt")),
        "finished_at": safe_timestamp(state.get("FinishedAt")),
        "restart_count": safe_number(item.get("RestartCount")),
        "oom_killed": state.get("OOMKilled") is True,
        "exit_code": safe_number(state.get("ExitCode")),
        "health": health if health in {"starting", "healthy", "unhealthy"} else None,
        "memory_limit_bytes": safe_number(host.get("Memory")),
        "memory_swap_limit_bytes": safe_number(host.get("MemorySwap")),
        "nano_cpus": safe_number(host.get("NanoCpus")),
        "pids_limit": safe_number(host.get("PidsLimit")),
    }


def summarize_logs(raw: str) -> dict:
    categories: Counter = Counter()
    frames: Counter = Counter()
    stream_http: Counter = Counter()
    recognized_times = []
    for line in raw.splitlines():
        matched = False
        for category, needles in LOG_CATEGORIES.items():
            if any(needle.lower() in line.lower() for needle in needles):
                categories[category] += 1
                matched = True
        frame = re.search(r'File "([^"]{1,240})", line ([0-9]{1,7})', line)
        if frame:
            filename = next((name for name in STACK_FILES if frame[1].endswith("/" + name)), None)
            if filename:
                frames[(filename, int(frame[2]))] += 1
                matched = True
        http = re.search(r'"POST /api/chat/stream HTTP/[0-9.]+"\s+([1-5][0-9]{2})(?:\s|$)', line)
        if http:
            stream_http[http[1]] += 1
            matched = True
        if matched:
            timestamp = line.partition(" ")[0]
            if safe_timestamp(timestamp):
                recognized_times.append(timestamp)
    return {
        "line_count": len(raw.splitlines()),
        "categories": dict(sorted(categories.items())),
        "stack_locations": [
            {"file": name, "line": line, "count": count}
            for (name, line), count in sorted(frames.items())[:64]
        ],
        "chat_stream_http_status_counts": dict(sorted(stream_http.items())),
        "first_matched_at": min(recognized_times) if recognized_times else None,
        "last_matched_at": max(recognized_times) if recognized_times else None,
    }


def nginx_directives(raw: str) -> list[dict]:
    selected = []
    stack: list[str] = []
    file_number = 0
    directive = re.compile(
        r"^\s*(proxy_read_timeout|proxy_send_timeout|proxy_connect_timeout|send_timeout|"
        r"keepalive_timeout|client_body_timeout|proxy_buffering|proxy_request_buffering|"
        r"proxy_ignore_client_abort|proxy_http_version|gzip)\s+"
        r"(on|off|[0-9]+(?:ms|s|m|h|d)?|1\.0|1\.1)\s*;\s*$"
    )
    for number, raw_line in enumerate(raw.splitlines(), 1):
        if raw_line.startswith("# configuration file "):
            file_number += 1
            stack.clear()
            continue
        line = raw_line.split("#", 1)[0].strip()
        while line.startswith("}"):
            if stack:
                stack.pop()
            line = line[1:].lstrip()
        match = directive.fullmatch(line)
        if match:
            selected.append(
                {
                    "file_number": file_number,
                    "line": number,
                    "scope": list(stack),
                    "directive": match[1],
                    "value": match[2],
                }
            )
        if line.endswith("{"):
            label = line[:-1].strip()
            if label in {"http", "server", "events"}:
                stack.append(label)
            else:
                location = re.fullmatch(
                    r"location\s+(?:(?:=|\^~)\s+)?(/api/chat/stream|/api/|/ws/|/)",
                    label,
                )
                stack.append("location:" + location[1] if location else "other_block")
        if len(selected) >= 128:
            break
    return selected


def metadata_receipt(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError
    except (TypeError, ValueError):
        return {"metadata_valid": False}
    result = {"metadata_valid": True}
    for key, allowed in (
        ("status", STATES),
        ("completion_status", COMPLETIONS),
        ("code", CODES),
        ("learning_capture", {"unreviewed_candidate", "unavailable"}),
    ):
        item = value.get(key)
        result[key] = item if isinstance(item, str) and item in allowed else None
    for key in ("partial", "usage_incomplete", "answer_delivered", "task_verified"):
        result[key] = value.get(key) if type(value.get(key)) is bool else None
    usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
    result["usage_counters"] = {
        key: safe_number(usage.get(key))
        for key in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "visible_output_tokens",
            "latency_ms",
        )
    }
    calls = usage.get("calls")
    result["usage_counters"]["recorded_call_count"] = (
        len(calls) if isinstance(calls, list) else None
    )
    timings = usage.get("timings") if isinstance(usage.get("timings"), dict) else {}
    result["timings"] = {
        key: safe_number(timings.get(key))
        for key in (
            "queue_wait_ms",
            "execution_ms",
            "provider_ms",
            "other_execution_ms",
            "tool_ms",
            "total_ms",
            "provider_attempt_count",
        )
    }
    return result


def read_qa_db(path: Path) -> dict:
    result = {
        "scope": "exact QA content and its request-linked assistant/ledger only",
        "matches": [],
    }
    deadline = time.monotonic() + 5
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.set_progress_handler(lambda: 1 if time.monotonic() >= deadline else 0, 1000)
        conn.execute("BEGIN")
        seeds = conn.execute(
            "SELECT session_id, length(content), created_at, substr(metadata,1,32768) "
            "FROM agent_messages WHERE role='user' AND content=? "
            "AND created_at>=? AND created_at<? ORDER BY created_at DESC LIMIT 4",
            (QA_TEXT, START[:19], END[:19]),
        ).fetchall()
        for session, length, created, raw in seeds:
            row = {
                "user": {
                    "role": "user",
                    "content_length": length,
                    "created_at": safe_timestamp(created),
                    **metadata_receipt(raw),
                },
                "assistant": [],
                "ledger": [],
            }
            try:
                request_id = json.loads(raw or "{}").get("request_id")
                if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                row["request_link"] = "missing_or_invalid"
                result["matches"].append(row)
                continue
            row["request_link"] = "verified_uuid"
            messages = conn.execute(
                "SELECT length(content),created_at,substr(metadata,1,32768) FROM agent_messages "
                "WHERE session_id=? AND role='assistant' AND "
                "json_extract(CASE WHEN json_valid(metadata) THEN metadata ELSE '{}' END,'$.request_id')=? "
                "ORDER BY created_at LIMIT 4",
                (session, request_id),
            ).fetchall()
            row["assistant"] = [
                {
                    "role": "assistant",
                    "content_length": size,
                    "created_at": safe_timestamp(at),
                    **metadata_receipt(meta),
                }
                for size, at, meta in messages
            ]
            ledger = conn.execute(
                "SELECT status,created_at,updated_at FROM chat_stream_requests "
                "WHERE session_id=? AND request_id=? AND owner_id=("
                "SELECT owner_id FROM chat_sessions WHERE session_id=?) LIMIT 2",
                (session, request_id, session),
            ).fetchall()
            row["ledger"] = [
                {
                    "status": state if state in STATES else None,
                    "created_at": safe_timestamp(at),
                    "updated_at": safe_timestamp(updated),
                }
                for state, at, updated in ledger
            ]
            result["matches"].append(row)
        return result
    finally:
        conn.close()


def read_graph_counts(db_path: Path) -> dict:
    """Count the persisted snapshot without loading application code or outputting keys."""
    result = {
        "status": "unavailable",
        "bytes": None,
        "concepts": None,
        "pathways": None,
    }
    graph_path = db_path.with_name("masalik_network.json")
    try:
        descriptor = os.open(graph_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                result["status"] = "not_regular_file"
                return result
            result["bytes"] = before.st_size
            if before.st_size > MAX_GRAPH_BYTES:
                result["status"] = "over_size_limit"
                return result
            payload = handle.read(MAX_GRAPH_BYTES + 1)
            after = os.fstat(handle.fileno())
        if len(payload) > MAX_GRAPH_BYTES:
            result["status"] = "over_size_limit"
            return result
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            result["status"] = "changed_during_read"
            return result
        value = json.loads(payload)
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), dict) for key in ("concepts", "pathways")
        ):
            result["status"] = "invalid_structure"
            return result
        result.update(
            status="counted",
            concepts=len(value["concepts"]),
            pathways=len(value["pathways"]),
        )
    except FileNotFoundError:
        result["status"] = "missing"
    except (ValueError, RecursionError):
        result["status"] = "invalid_json"
    except MemoryError:
        result["status"] = "memory_limit"
    except OSError:
        result["status"] = "unreadable"
    return result


def child_report() -> dict:
    # The backend exec child has its own deadline even if the Docker CLI disconnects.
    signal.alarm(12)
    # Only these two environment keys are inspected; neither value is printed.
    db_path = Path(os.environ.get("DB_PATH", "/data/mizan_memory.db"))
    mem0_enabled = os.environ.get("MEM0_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = (
            min(CHILD_ADDRESS_SPACE_BYTES, hard)
            if hard != resource.RLIM_INFINITY
            else CHILD_ADDRESS_SPACE_BYTES
        )
        if soft != resource.RLIM_INFINITY:
            limit = min(limit, soft)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (OSError, ValueError):
        return {"status": "unavailable", "reason": "child_memory_bound_unavailable"}
    try:
        result = read_qa_db(db_path)
    except (OSError, ValueError, sqlite3.Error, MemoryError):
        result = {"status": "unavailable", "reason": "read_only_database_probe_failed"}
    result["mem0_enabled"] = mem0_enabled
    result["persisted_graph"] = read_graph_counts(db_path)
    return result


def main() -> int:
    if sys.argv[1:] == ["--db-only"]:
        print(json.dumps(child_report(), allow_nan=False))
        return 0
    if sys.argv[1:] or os.geteuid() != 0:
        raise SystemExit("Existing root deployment connection and fixed diagnostic scope required")
    report = {
        "scope": "read-only fixed QA diagnosis; raw content and credentials withheld",
        "log_window_utc": {"since": START, "until": END},
    }
    for container in ("mizan-backend", "mizan-nginx"):
        code, output, _, truncated = run([*DOCKER, "inspect", container], maximum=1024 * 1024)
        try:
            report[container] = selected_container(json.loads(output)[0]) if code == 0 else {}
        except (ValueError, TypeError, KeyError, IndexError):
            report[container] = {}
        report[container].update(inspect_exit=code, inspect_truncated=truncated)
        code, output, errors, truncated = run(
            [
                *DOCKER,
                "logs",
                "--timestamps",
                "--since",
                START,
                "--until",
                END,
                "--tail",
                "3000",
                container,
            ]
        )
        report[container]["window_logs"] = {
            "exit": code,
            "truncated": truncated,
            **summarize_logs(output + "\n" + errors),
        }
    code, output, _, truncated = run([*DOCKER, "exec", "mizan-nginx", "nginx", "-T"])
    report["container_nginx"] = {
        "config_exit": code,
        "truncated": truncated,
        "selected_directives": nginx_directives(output),
    }
    host_nginx = next(
        (
            name
            for name in ("/usr/sbin/nginx", "/usr/local/nginx/sbin/nginx")
            if Path(name).is_file()
        ),
        None,
    )
    report["host_nginx"] = {"binary_present": host_nginx is not None}
    if host_nginx:
        code, output, _, truncated = run([host_nginx, "-T"])
        report["host_nginx"].update(
            config_exit=code,
            truncated=truncated,
            selected_directives=nginx_directives(output),
        )
    code, output, _, truncated = run(
        [*DOCKER, "exec", "-i", "mizan-backend", "python3", "-", "--db-only"],
        stdin=Path(__file__).read_text(),
        timeout=15,
        maximum=64 * 1024,
    )
    try:
        report["qa_database"] = (
            json.loads(output) if code == 0 and not truncated else {"status": "unavailable"}
        )
    except ValueError:
        report["qa_database"] = {"status": "unavailable"}
    report["qa_database_probe_exit"] = code
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
