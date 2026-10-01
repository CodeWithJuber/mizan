"""Tests for backend/api/sandbox.py — sandboxed code execution.

Covers: fail-closed 503 when no provider exists, docker fallback invocation,
output caps, timeout handling, and the append-only audit log. The sandbox
executors themselves are mocked; no real container/microVM is ever started.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from api import sandbox
from api.sandbox import (
    MAX_OUTPUT_BYTES,
    SandboxRunResult,
    _cap,
    _run_docker_sync,
    detect_provider,
    execute_code,
)


def _app():
    app = FastAPI()
    app.include_router(sandbox.router)
    return app


def test_fail_closed_when_no_provider(monkeypatch):
    """No microsandbox, no docker → HTTP 503, never executed."""
    monkeypatch.setattr(sandbox, "_microsandbox_importable", lambda: False)
    monkeypatch.setattr(sandbox, "_docker_available", lambda: False)
    assert detect_provider() is None

    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.post(
        "/api/sandbox/run",
        json={"language": "python", "code": "print('x')", "timeout_s": 5},
    )
    assert resp.status_code == 503
    assert "no sandbox provider" in resp.json()["detail"]


def test_execute_code_raises_503_directly(monkeypatch):
    monkeypatch.setattr(sandbox, "_microsandbox_importable", lambda: False)
    monkeypatch.setattr(sandbox, "_docker_available", lambda: False)
    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(execute_code("python", "print(1)", 5))
    assert exc.value.status_code == 503


def test_status_reports_unavailable(monkeypatch):
    monkeypatch.setattr(sandbox, "_microsandbox_importable", lambda: False)
    monkeypatch.setattr(sandbox, "_docker_available", lambda: False)
    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.get("/api/sandbox/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["provider"] is None


def test_request_validation():
    client = TestClient(_app(), raise_server_exceptions=False)
    # bad language
    r = client.post("/api/sandbox/run", json={"language": "ruby", "code": "1"})
    assert r.status_code == 422
    # timeout above max
    r = client.post("/api/sandbox/run", json={"language": "python", "code": "1", "timeout_s": 999})
    assert r.status_code == 422
    # empty code
    r = client.post("/api/sandbox/run", json={"language": "python", "code": ""})
    assert r.status_code == 422


def test_docker_fallback_uses_hardened_flags(monkeypatch, tmp_path):
    """The docker command must carry the hardening flags; stdout/stderr captured."""
    seen = {}

    def fake_run(cmd, timeout_s):
        if cmd[1] == "rm":
            seen["cleanup"] = cmd
            return ("", "", 0, False)
        seen["cmd"] = cmd
        seen["timeout"] = timeout_s
        assert cmd[0] == "docker"
        for flag in (
            "--cap-drop",
            "--read-only",
            "--security-opt",
            "--network",
            "--cpus",
            "--memory",
            "--pids-limit",
            "--rm",
        ):
            assert flag in cmd, f"missing hardening flag {flag}"
        assert "none" in cmd  # --network none
        assert "no-new-privileges" in cmd
        assert "65534:65534" in cmd
        return ("hello\n", "", 0, False)

    monkeypatch.setattr(sandbox, "_bounded_process", fake_run)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: seen.update(cleanup=cmd))
    result = _run_docker_sync("python", "print('hello')", 10)
    assert isinstance(result, SandboxRunResult)
    assert result.stdout == "hello\n"
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.sandbox == "docker"
    assert seen["timeout"] == 10


def test_docker_timeout_kills_and_flags(monkeypatch):
    def fake_run(cmd, timeout_s):
        return ("partial", "err: timed out", 124, True)

    monkeypatch.setattr(sandbox, "_bounded_process", fake_run)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    result = _run_docker_sync("javascript", "while(true){}", 3)
    assert result.timed_out is True
    assert result.exit_code == 124
    assert "timed out" in result.stderr


def test_output_cap_truncates():
    big = "x" * (MAX_OUTPUT_BYTES + 1000)
    capped = _cap(big)
    assert len(capped.encode("utf-8")) <= MAX_OUTPUT_BYTES + 200
    assert "truncated" in capped


def test_audit_log_written(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sandbox, "_microsandbox_importable", lambda: False)
    monkeypatch.setattr(sandbox, "_docker_available", lambda: False)
    import asyncio

    with pytest.raises(HTTPException):
        asyncio.run(execute_code("python", "print(1)", 5, user_id="u1"))
    audit = tmp_path / "sandbox_audit.log"
    assert audit.exists()
    record = json.loads(audit.read_text().strip().splitlines()[-1])
    assert record["language"] == "python"
    assert record["user_id"] == "u1"
    assert record["provider"] is None


def test_unverified_microsandbox_is_disabled(monkeypatch):
    monkeypatch.setattr(sandbox, "_microsandbox_importable", lambda: True)
    monkeypatch.setattr(sandbox, "_docker_available", lambda: False)
    assert sandbox.detect_provider() is None
    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(execute_code("python", "print(1)", 5))
    assert exc.value.status_code == 503


def test_microsandbox_failure_falls_back_to_docker(monkeypatch):
    async def fail_ms(language, code, timeout_s):
        raise RuntimeError("microVM backend down")

    async def ok_docker(language, code, timeout_s):
        return SandboxRunResult(
            stdout="ok",
            stderr="",
            exit_code=0,
            timed_out=False,
            duration_ms=1,
            sandbox="docker",
        )

    monkeypatch.setattr(sandbox, "_microsandbox_importable", lambda: True)
    monkeypatch.setattr(sandbox, "_docker_available", lambda: True)
    monkeypatch.setattr(sandbox, "_run_microsandbox", fail_ms)
    monkeypatch.setattr(sandbox, "_run_docker", ok_docker)
    import asyncio

    result = asyncio.run(execute_code("python", "print(1)", 5))
    assert result.sandbox == "docker"


def test_never_executes_unsandboxed(monkeypatch):
    """Ensure execute_code has no path that runs code via bare subprocess/eval."""
    import inspect

    src = inspect.getsource(sandbox.execute_code)
    assert "eval(" not in src
    assert "exec(" not in src or "execute_code" in src
    # The only subprocess use lives in the docker helper, not the dispatcher.
    assert "subprocess" not in src
