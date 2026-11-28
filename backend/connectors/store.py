"""Per-user connector configuration: ``$MIZAN_DATA_DIR/connectors/<sha256(user)>.json``.

Secrets (headers, environment values, OAuth tokens and a pre-registered client's
secret) are sealed with :mod:`connectors.secrets`; public views never include them.

Every tool the model is offered resolves through this file, so reads are cached
in memory by the file's modification time and size: a read costs one ``stat``,
and every write drops the cache. The cached records are shared, so callers treat
what ``list_servers``/``get_server`` return as read-only and change a record only
through :func:`update_server`.
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
SEALED = ("headers", "env", "oauth", "oauth_secret")
POLICIES = ("allow", "ask", "never")
DEFAULT_CONNECT_S = 30
DEFAULT_STDIO_INSTALL_CONNECT_S = 90  # npx/uvx may download the package first
DEFAULT_CALL_S = 120
_LOCK = threading.RLock()
_cache: dict[str, tuple[tuple[int, int], list[dict]]] = {}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(user_id: str) -> Path:
    root = Path(os.getenv("MIZAN_DATA_DIR", "data")) / "connectors"
    return root / f"{hashlib.sha256(user_id.encode()).hexdigest()}.json"


def _read(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    servers = data.get("servers", []) if isinstance(data, dict) else []
    return [server for server in servers if isinstance(server, dict)]


def _load(user_id: str) -> list[dict]:
    """Fresh records from disk, safe to change and save (callers hold ``_LOCK``)."""
    return _read(_path(user_id))


def _cached(user_id: str) -> list[dict]:
    path = _path(user_id)
    try:
        info = path.stat()
    except OSError:
        return []
    stamp = (info.st_mtime_ns, info.st_size)
    key = str(path)
    hit = _cache.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    servers = _read(path)
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (stamp, servers)
    return servers


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
        _cache.pop(str(path), None)


def invalidate(user_id: str | None = None) -> None:
    with _LOCK:
        if user_id is None:
            _cache.clear()
        else:
            _cache.pop(str(_path(user_id)), None)


# ── timeouts, policies, auth ─────────────────────────────────────────────


def installs_package(server: dict) -> bool:
    command = os.path.basename(str(server.get("command") or "")).lower()
    return server.get("transport") == "stdio" and command in {"npx", "uvx", "bunx", "pnpx"}


def timeouts(server: dict) -> dict[str, float]:
    """The connector's connect and call timeouts (seconds), defaults filled in."""
    configured = server.get("timeouts") or {}
    connect_default = (
        DEFAULT_STDIO_INSTALL_CONNECT_S if installs_package(server) else DEFAULT_CONNECT_S
    )
    connect = configured.get("connect_s") or connect_default
    call = configured.get("call_s") or DEFAULT_CALL_S
    return {"connect_s": float(connect), "call_s": float(call)}


def policy(server: dict, tool_name: str) -> str:
    """allow (default) · ask (approval even in auto mode) · never (not offered)."""
    if tool_name in (server.get("disabled_tools") or []):
        return "never"
    value = str((server.get("policies") or {}).get(tool_name, "allow"))
    return value if value in POLICIES else "allow"


def held_reason(tool: dict) -> str | None:
    held = tool.get("held")
    if not held:
        return None
    if held in ("flagged", "poisoned"):
        return "poisoned"
    return "changed" if held == "changed" else "new" if held == "new" else "poisoned"


def secrets_readable(server: dict) -> bool:
    try:
        for field in SEALED:
            secrets.unseal(server.get(field, ""), None, strict=True)
    except secrets.SecretsUnreadable:
        return False
    return True


def _expires(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(float(value), UTC).isoformat(timespec="seconds")


def auth_view(server: dict) -> dict:
    """How the connector authenticates, without any secret."""
    headers = secrets.unseal(server.get("headers", ""), {}) or {}
    oauth = secrets.unseal(server.get("oauth", ""), {}) or {}
    config = server.get("oauth_config") or {}
    tokens = oauth.get("tokens") or {}
    client = oauth.get("client_info") or {}
    has_authorization = any(name.lower() == "authorization" for name in headers)
    if server.get("transport") == "stdio":
        kind = "none"
    elif has_authorization:
        kind = "headers"
    elif tokens or config.get("client_id") or client or server.get("status") == "auth_required":
        kind = "oauth"
    elif headers:
        kind = "headers"
    else:
        kind = "none"
    scopes = list(config.get("scopes") or [])
    if not scopes and tokens.get("scope"):
        scopes = str(tokens["scope"]).split()
    return {
        "type": kind,
        "signed_in": bool(tokens.get("access_token")) if kind == "oauth" else kind == "headers",
        "expires_at": _expires(oauth.get("expires_at")) if kind == "oauth" else None,
        "client_id": (config.get("client_id") or client.get("client_id") or None)
        if kind == "oauth"
        else None,
        "scopes": scopes if kind == "oauth" else [],
    }


def public_tool(server: dict, tool: dict) -> dict:
    reason = held_reason(tool)
    return {
        "name": tool.get("name"),
        "exposed": tool.get("exposed"),
        "description": tool.get("description"),
        "read_only": bool(tool.get("read_only")),
        "destructive": bool(tool.get("destructive")),
        "enabled": tool.get("name") not in (server.get("disabled_tools") or []),
        "held": reason is not None,
        "held_reason": reason,
        "new": bool(tool.get("new")) and reason is None,
        "policy": policy(server, str(tool.get("name") or "")),
        "input_schema": tool.get("input_schema") or {"type": "object", "properties": {}},
        "previous": tool.get("previous") if reason == "changed" else None,
        "amanah": list(tool.get("amanah") or []),
    }


def public(server: dict, *, status: str | None = None, last_error: str | None = None) -> dict:
    """Configuration safe to show: secret values are replaced by their key names.

    ``status``/``last_error`` are the live values (the manager knows whether a
    connection is open); without them the stored ones are shown."""
    readable = secrets_readable(server)
    headers = secrets.unseal(server.get("headers", ""), {}) or {}
    env = secrets.unseal(server.get("env", ""), {}) or {}
    oauth = secrets.unseal(server.get("oauth", ""), {}) or {}
    tools = [public_tool(server, tool) for tool in server.get("tools") or []]
    shown_status = status or server.get("status") or "disconnected"
    error = last_error if last_error is not None else (server.get("last_error") or None)
    if not readable:
        shown_status, error = "error", str(secrets.SecretsUnreadable())
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
            "source",
            "created_at",
            "updated_at",
        )
    } | {
        "status": shown_status,
        "last_error": error or None,
        "header_names": sorted(headers),
        "env_names": sorted(env),
        "oauth_connected": bool(oauth.get("tokens")),
        "auth": auth_view(server),
        "timeouts": {key: int(value) for key, value in timeouts(server).items()},
        "instructions": server.get("instructions") or None,
        "counts": {
            "total": len(tools),
            "enabled": sum(
                1
                for tool in tools
                if tool["enabled"] and not tool["held"] and tool["policy"] != "never"
            ),
            "held": sum(1 for tool in tools if tool["held"]),
            "new": sum(1 for tool in tools if tool["new"]),
        },
        "tools": tools,
    }


# ── records ──────────────────────────────────────────────────────────────


def list_servers(user_id: str) -> list[dict]:
    """The user's connectors (shared cached records: read-only)."""
    with _LOCK:
        return _cached(user_id)


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
        oauth_config = config.get("oauth") or {}
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
            "oauth_secret": secrets.seal(oauth_config.get("client_secret") or ""),
            "oauth_config": {
                key: oauth_config[key] for key in ("client_id", "scopes") if oauth_config.get(key)
            },
            "timeouts": {
                key: value for key, value in (config.get("timeouts") or {}).items() if value
            },
            "policies": {},
            "enabled": True,
            "disabled_tools": [],
            "tools": [],
            "pin_version": 2,
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
                    if key in SEALED:
                        value = secrets.seal(value)
                    server[key] = value
                server["updated_at"] = _now()
                _save(user_id, servers)
                return server
        return None


def change_oauth(user_id: str, server_id: str, change) -> dict | None:
    """Read, change and write the sealed OAuth state in one step (``change(oauth)``
    edits the dict in place)."""
    with _LOCK:
        servers = _load(user_id)
        for server in servers:
            if server.get("id") == server_id:
                oauth = secrets.unseal(server.get("oauth", ""), {}, strict=True) or {}
                change(oauth)
                server["oauth"] = secrets.seal(oauth)
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
    """(headers, env, oauth) decrypted for a connection; raises
    :class:`connectors.secrets.SecretsUnreadable` when the key no longer opens them."""
    return (
        secrets.unseal(server.get("headers", ""), {}, strict=True) or {},
        secrets.unseal(server.get("env", ""), {}, strict=True) or {},
        secrets.unseal(server.get("oauth", ""), {}, strict=True) or {},
    )


def oauth_client_secret(server: dict) -> str:
    return str(secrets.unseal(server.get("oauth_secret", ""), "", strict=True) or "")
