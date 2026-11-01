"""Backend side of persistent workspace sessions on the private runner.

The project store stays the source of truth. A session holds a working copy
(plus dependency folders such as node_modules that never sync). ``reconcile``
does a three-way merge against the manifest of the last sync: edits made in
the editor are pushed, files changed inside the session are pulled, and an
editor edit wins when both sides touched the same file.

Preview URLs are capabilities: ``/api/workspaces/preview/<cap>/<port>/`` where
``cap`` binds the session key and its random start nonce with an HMAC keyed
from the runner token. They work in a sandboxed frame without a login, die
when the session stops, and the backend serves them under a CSP sandbox so the
page never runs with Mizan's origin.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import HTTPException

from .execution import configuration
from .session_agent import heavy
from .store import MAX_FILE_BYTES, MAX_FILES, MAX_PROJECT_BYTES, WorkspaceStore

PREVIEW_ROOT = "/api/workspaces/preview"
_CAP = re.compile(r"^[0-9a-f]{96}$")
_locks: dict[str, asyncio.Lock] = {}


def available() -> bool:
    url, token = configuration()
    return bool(url and len(token) >= 32)


def session_key(user_id: str, workspace_id: str, kind: str = "workspace") -> str:
    return hashlib.sha256(f"{kind}\0{user_id}\0{workspace_id}".encode()).hexdigest()[:32]


def _mac(key: str, nonce: str) -> str:
    secret = hashlib.sha256(b"mizan-preview\0" + configuration()[1].encode()).digest()
    return hmac.new(secret, f"{key}:{nonce}".encode(), hashlib.sha256).hexdigest()[:32]


def capability(key: str, nonce: str) -> str:
    return f"{key}{nonce}{_mac(key, nonce)}"


def parse_capability(cap: str) -> tuple[str, str] | None:
    if not available() or not _CAP.fullmatch(cap):
        return None
    key, nonce, mac = cap[:32], cap[32:64], cap[64:]
    return (key, nonce) if hmac.compare_digest(mac, _mac(key, nonce)) else None


def preview_prefix(key: str, nonce: str) -> str:
    return f"{PREVIEW_ROOT}/{capability(key, nonce)}"


def preview_url(key: str, nonce: str, port: int) -> str:
    return f"{preview_prefix(key, nonce)}/{port}/"


# A runner older than this backend answers its missing routes with FastAPI's own
# 404 "Not Found"; the runner's real refusals carry X-Mizan-Runner: error.
_OLDER_RUNNER = {
    "/sessions": "The private runner on this server predates sandbox sessions; "
    "the next deploy upgrades it",
    "/browse": "The private runner on this server predates the browser sandbox; "
    "the next deploy upgrades it",
}


def _status_error(status: int, detail: str) -> HTTPException:
    if status in (404, 409, 413, 422, 429):
        return HTTPException(status, detail)
    if status == 504:
        return HTTPException(504, detail or "The sandbox did not answer in time")
    return HTTPException(503, detail or "The sandbox runner is unavailable")


async def call(method: str, path: str, body: Any = None, timeout: float = 60) -> dict:
    url, token = configuration()
    if not available():
        raise HTTPException(503, "Server sandbox sessions need the private runner")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout + 10), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.request(
                method,
                f"{url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
    except httpx.HTTPError:
        raise HTTPException(503, "The sandbox runner is unavailable") from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200:
        detail = str(data.get("detail", ""))[:300]
        if (
            response.status_code == 404
            and detail == "Not Found"
            and response.headers.get("x-mizan-runner") != "error"
        ):
            for prefix, message in _OLDER_RUNNER.items():
                if path.startswith(prefix):
                    raise HTTPException(503, message)
        raise _status_error(response.status_code, detail)
    return cast(dict, data)


# ── Last-sync manifests (the common ancestor of the three-way merge) ──────


def _sync_file(key: str) -> Path:
    root = Path(os.getenv("MIZAN_DATA_DIR", "data")) / "session_sync"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root / f"{key}.json"


def _load_base(key: str, nonce: str) -> dict[str, str] | None:
    try:
        data = json.loads(_sync_file(key).read_text())
    except (OSError, ValueError):
        return None
    if data.get("nonce") != nonce or not isinstance(data.get("files"), dict):
        return None
    return cast(dict, data["files"])


def _save_base(key: str, nonce: str, files: dict[str, str]) -> None:
    path = _sync_file(key)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"nonce": nonce, "files": files}))
    os.replace(temporary, path)


def _forget_base(key: str) -> None:
    _sync_file(key).unlink(missing_ok=True)


def _digests(snapshot: dict[str, str]) -> dict[str, str]:
    return {
        path: hashlib.sha256(base64.b64decode(data)).hexdigest()
        for path, data in snapshot.items()
        if not heavy(path)
    }


# ── Session operations ────────────────────────────────────────────────────


async def status(user_id: str, workspace_id: str) -> dict:
    WorkspaceStore(user_id).project(workspace_id)
    if not available():
        return {"available": False, "running": False, "services": []}
    key = session_key(user_id, workspace_id)
    data = await call("GET", f"/sessions/{key}")
    services = [
        {**item, "preview_url": preview_url(key, data["nonce"], int(item["port"]))}
        for item in data.get("services", [])
        if data.get("running")
    ]
    return {
        "available": True,
        "running": bool(data.get("running")),
        "egress": bool(data.get("egress")),
        "services": services,
        "limits": data.get("limits", {}),
    }


async def start(user_id: str, workspace_id: str) -> dict:
    store = WorkspaceStore(user_id)
    store.project(workspace_id)
    key = session_key(user_id, workspace_id)
    nonce = secrets.token_hex(16)
    data = await call(
        "PUT",
        f"/sessions/{key}",
        {"nonce": nonce, "kind": "workspace", "preview_prefix": preview_prefix(key, nonce)},
        timeout=90,
    )
    sync = await reconcile(user_id, workspace_id)
    return {"running": True, "egress": bool(data.get("egress")), "sync": sync}


async def stop(user_id: str, workspace_id: str) -> dict:
    WorkspaceStore(user_id).project(workspace_id)
    key = session_key(user_id, workspace_id)
    try:
        await reconcile(user_id, workspace_id)
    except HTTPException:
        pass
    await call("DELETE", f"/sessions/{key}", timeout=60)
    _forget_base(key)
    return {"running": False}


async def _nonce(key: str) -> str:
    data = await call("GET", f"/sessions/{key}")
    if not data.get("running"):
        raise HTTPException(409, "Start the sandbox session first")
    return str(data["nonce"])


async def reconcile(user_id: str, workspace_id: str) -> dict:
    """Three-way sync between the project store and the session's working copy."""
    store = WorkspaceStore(user_id)
    key = session_key(user_id, workspace_id)
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        nonce = await _nonce(key)
        snapshot, directories = store.snapshot_state(workspace_id)
        local = _digests(snapshot)
        listed = (await call("POST", f"/sessions/{key}/manifest", {})).get("files") or {}
        remote = {str(p): str(v) for p, v in dict(listed).items() if not heavy(str(p))}
        base = _load_base(key, nonce)
        if base is None:
            # First sync of this session: the project store wins everywhere.
            push = {
                path for path in local.keys() | remote.keys() if local.get(path) != remote.get(path)
            }
            pull: set[str] = set()
        else:
            store_changes = {p for p in local.keys() | base.keys() if local.get(p) != base.get(p)}
            session_changes = {
                p for p in remote.keys() | base.keys() if remote.get(p) != base.get(p)
            }
            push = {p for p in store_changes if local.get(p) != remote.get(p)}
            pull = {p for p in session_changes - store_changes if local.get(p) != remote.get(p)}
        conflicts = sorted(p for p in push if base is not None and remote.get(p) != base.get(p))
        if push or directories:
            await call(
                "POST",
                f"/sessions/{key}/sync",
                {
                    "files": {p: snapshot[p] for p in push if p in snapshot},
                    "delete": sorted(p for p in push if p not in snapshot),
                    "directories": [d for d in directories if not heavy(d)],
                },
                timeout=120,
            )
        warning = ""
        pulled: list[str] = []
        if pull:
            exported = await call(
                "POST",
                f"/sessions/{key}/export",
                {
                    "baseline": {p: local[p] for p in local},
                    "max_files": MAX_FILES,
                    "max_bytes": MAX_PROJECT_BYTES,
                    "max_file": MAX_FILE_BYTES,
                },
                timeout=120,
            )
            if exported.get("error"):
                warning = f"Session files were not copied back: {exported.get('detail', '')}"
            else:
                result = dict(snapshot)
                for path in pull:
                    if path in exported.get("files", {}):
                        result[path] = exported["files"][path]
                    elif path in exported.get("deleted", []):
                        result.pop(path, None)
                try:
                    pulled = store.apply_run(workspace_id, snapshot, result, None, directories)
                    snapshot = result
                except HTTPException as exc:
                    warning = f"Session files were not copied back: {exc.detail}"
        final = _digests(snapshot)
        if warning and base is not None:
            # Retry the pull next time: keep the old ancestor for those paths.
            for path in pull:
                if path in base:
                    final[path] = base[path]
                else:
                    final.pop(path, None)
        _save_base(key, nonce, final)
        return {
            "pushed": sorted(push),
            "pulled": pulled,
            "conflicts": conflicts,
            "warning": warning,
        }


async def execute(
    user_id: str, workspace_id: str, command: str, language: str, timeout_s: int
) -> dict:
    key = session_key(user_id, workspace_id)
    before = await reconcile(user_id, workspace_id)
    result = await call(
        "POST",
        f"/sessions/{key}/exec",
        {"command": command, "language": language, "timeout_s": timeout_s},
        timeout=timeout_s + 40,
    )
    after = await reconcile(user_id, workspace_id)
    return {
        "stdout": str(result.get("stdout", ""))[:100000],
        "stderr": str(result.get("stderr", ""))[:100000],
        "exit_code": int(result.get("exit_code", 1)),
        "timed_out": bool(result.get("timed_out", False)),
        "duration_ms": int(result.get("duration_ms", 0)),
        "truncated": bool(result.get("truncated", False)),
        "changed_files": after["pulled"],
        "sync_warning": after["warning"] or before["warning"],
        "sandbox": "session",
    }


async def start_service(
    user_id: str, workspace_id: str, port: int, command: str, mode: str
) -> dict:
    key = session_key(user_id, workspace_id)
    await reconcile(user_id, workspace_id)
    nonce = await _nonce(key)
    info = await call(
        "POST",
        f"/sessions/{key}/services",
        {"port": port, "command": command, "mode": mode},
    )
    return {**info, "preview_url": preview_url(key, nonce, port)}


async def stop_service(user_id: str, workspace_id: str, port: int) -> dict:
    WorkspaceStore(user_id).project(workspace_id)
    return await call("DELETE", f"/sessions/{session_key(user_id, workspace_id)}/services/{port}")


async def service_logs(user_id: str, workspace_id: str, port: int) -> dict:
    WorkspaceStore(user_id).project(workspace_id)
    return await call("GET", f"/sessions/{session_key(user_id, workspace_id)}/services/{port}/logs")


async def running(user_id: str, workspace_id: str) -> bool:
    if not available():
        return False
    try:
        data = await call("GET", f"/sessions/{session_key(user_id, workspace_id)}")
    except HTTPException:
        return False
    return bool(data.get("running"))


def runner_ws_url(path: str) -> str:
    url, _ = configuration()
    return re.sub(r"^http", "ws", url) + path


def runner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {configuration()[1]}"}
