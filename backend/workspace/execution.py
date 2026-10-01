"""Send project snapshots to a private isolated executor; no local shell fallback."""

from __future__ import annotations

import os
import time

import httpx
from fastapi import HTTPException

from .store import WorkspaceStore

MAX_RUNNER_RESPONSE = 16 * 1024 * 1024


def configuration() -> tuple[str, str]:
    return os.getenv("MIZAN_WORKSPACE_RUNNER_URL", "").rstrip("/"), os.getenv(
        "MIZAN_WORKSPACE_RUNNER_TOKEN", ""
    )


async def capabilities(*, admin: bool = False) -> dict:
    url, token = configuration()
    available = False
    detail = "The isolated coding runner has not been configured"
    if url and token:
        try:
            async with httpx.AsyncClient(
                timeout=3, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.get(
                    f"{url}/health", headers={"Authorization": f"Bearer {token}"}
                )
                if response.status_code == 200:
                    data = response.json()
                    available = data.get("isolated") is True and data.get("available") is True
                detail = (
                    "Isolated project execution is ready"
                    if available
                    else "The isolated coding runner is unavailable"
                )
        except (httpx.HTTPError, ValueError):
            detail = "The isolated coding runner is unavailable"
    return {
        "execution_available": available,
        "execution_detail": detail,
        "languages": ["python", "javascript", "shell"],
        "hardware_inspection": admin,
        "host_shell": False,
        "network_access": False,
    }


async def run_project(
    store: WorkspaceStore, workspace_id: str, command: str, language: str, timeout_s: int
) -> dict:
    if (
        language not in {"python", "javascript", "shell"}
        or not command
        or len(command) > 10000
        or not 1 <= timeout_s <= 120
    ):
        raise HTTPException(422, "Invalid execution request")
    url, token = configuration()
    if not url or not token:
        raise HTTPException(503, "Isolated coding runner unavailable; configure a private runner")
    baseline, directories = store.snapshot_state(workspace_id)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s + 30), trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream(
                "POST",
                f"{url}/run",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "command": command,
                    "language": language,
                    "timeout_s": timeout_s,
                    "files": baseline,
                    "directories": directories,
                },
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        503, "Isolated coding runner could not execute this request"
                    )
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > MAX_RUNNER_RESPONSE:
                        raise HTTPException(502, "Runner response exceeded the allowed size")
                    chunks.extend(chunk)
                import json

                data = json.loads(chunks)
    except httpx.HTTPError:
        raise HTTPException(
            503, "Isolated coding runner unavailable or execution interrupted"
        ) from None
    except (ValueError, TypeError):
        raise HTTPException(502, "Invalid isolated runner response") from None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise HTTPException(502, "Invalid isolated runner response")
    if data.get("export_error"):
        raise HTTPException(
            422,
            "Execution created unsafe files or exceeded the project quota; project changes were not applied",
        )
    changed = store.apply_run(
        workspace_id, baseline, data["files"], data.get("directories"), directories
    )
    return {
        "stdout": str(data.get("stdout", ""))[:100000],
        "stderr": str(data.get("stderr", ""))[:100000],
        "exit_code": int(data.get("exit_code", 1)),
        "timed_out": bool(data.get("timed_out", False)),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "changed_files": changed,
        "truncated": bool(data.get("truncated", False)),
        "sandbox": "isolated-docker",
    }
