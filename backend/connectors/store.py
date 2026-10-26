"""Per-user connector configuration: ``$MIZAN_DATA_DIR/connectors/<sha256(user)>.json``.

Secrets (headers, environment values, OAuth tokens) are sealed with
:mod:`connectors.secrets`; public views never include them.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from connectors import secrets
from connectors.naming import slug as make_slug

MAX_SERVERS_PER_USER = 20
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(user_id: str) -> Path:
    root = Path(os.getenv("MIZAN_DATA_DIR", "data")) / "connectors"
    return root / f"{hashlib.sha256(user_id.encode()).hexdigest()}.json"


def _load(user_id: str) -> list[dict]:
    try:
        data = json.loads(_path(user_id).read_text())
    except (OSError, ValueError):
        return []
    return data.get("servers", []) if isinstance(data, dict) else []


def _save(user_id: str, servers: list[dict]) -> None:
    path = _path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.parent / f".{uuid.uuid4().hex}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump({"servers": servers}, handle)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def public(server: dict) -> dict:
    """Configuration safe to show: secret values are replaced by their key names."""
    headers = secrets.unseal(server.get("headers", ""), {}) or {}
    env = secrets.unseal(server.get("env", ""), {}) or {}
    oauth = secrets.unseal(server.get("oauth", ""), {}) or {}
    return {
        key: server.get(key)
        for key in (
            "id",
            "name",
            "slug",
            "transport",
            "url",
            "command",
            "args",
            "runtime",
            "enabled",
            "disabled_tools",
            "status",
            "last_error",
            "source",
            "created_at",
            "updated_at",
        )
    } | {
        "header_names": sorted(headers),
        "env_names": sorted(env),
        "oauth_connected": bool(oauth.get("tokens")),
        "tools": [
            {k: tool.get(k) for k in ("name", "exposed", "description", "read_only", "destructive")}
            | {"enabled": tool.get("name") not in (server.get("disabled_tools") or [])}
            for tool in server.get("tools") or []
        ],
    }


def list_servers(user_id: str) -> list[dict]:
    with _LOCK:
        return _load(user_id)


def get_server(user_id: str, server_id: str) -> dict | None:
    return next((s for s in list_servers(user_id) if s.get("id") == server_id), None)


def add_server(user_id: str, config: dict) -> dict:
    with _LOCK:
        servers = _load(user_id)
        if len(servers) >= MAX_SERVERS_PER_USER:
            raise ValueError(f"At most {MAX_SERVERS_PER_USER} connectors per user")
        base = make_slug(config["name"])
        used = {s.get("slug") for s in servers}
        slug, counter = base, 2
        while slug in used:
            suffix = f"_{counter}"
            slug, counter = base[: 16 - len(suffix)] + suffix, counter + 1
        server = {
            "id": uuid.uuid4().hex,
            "name": config["name"][:60],
            "slug": slug,
            "transport": config["transport"],
            "url": config.get("url", ""),
            "command": config.get("command", ""),
            "args": list(config.get("args") or [])[:40],
            "runtime": config.get("runtime", ""),
            "headers": secrets.seal(config.get("headers") or {}),
            "env": secrets.seal(config.get("env") or {}),
            "oauth": "",
            "enabled": True,
            "disabled_tools": [],
            "tools": [],
            "status": "new",
            "last_error": "",
            "source": config.get("source", "")[:200],
            "created_at": _now(),
            "updated_at": _now(),
        }
        servers.append(server)
        _save(user_id, servers)
        return server


def update_server(user_id: str, server_id: str, **changes: Any) -> dict | None:
    with _LOCK:
        servers = _load(user_id)
        for server in servers:
            if server.get("id") == server_id:
                for key, value in changes.items():
                    if key in {"headers", "env", "oauth"}:
                        value = secrets.seal(value)
                    server[key] = value
                server["updated_at"] = _now()
                _save(user_id, servers)
                return server
        return None


def delete_server(user_id: str, server_id: str) -> bool:
    with _LOCK:
        servers = _load(user_id)
        remaining = [s for s in servers if s.get("id") != server_id]
        if len(remaining) == len(servers):
            return False
        _save(user_id, remaining)
        return True


def secrets_of(server: dict) -> tuple[dict, dict, dict]:
    """(headers, env, oauth) decrypted for a connection."""
    return (
        secrets.unseal(server.get("headers", ""), {}) or {},
        secrets.unseal(server.get("env", ""), {}) or {},
        secrets.unseal(server.get("oauth", ""), {}) or {},
    )
