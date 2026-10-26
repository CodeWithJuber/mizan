"""Owner-scoped MCP connectors: add, connect (OAuth), browse the registry, remove."""

from __future__ import annotations

import contextlib
import html
import os
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api.artifacts import require_auth
from connectors import net_guard, registry, store
from connectors.manager import (
    AuthorizationRequired,
    ConnectorError,
    host_stdio_allowed,
    manager,
)
from security.auth import TokenPayload

router = APIRouter(prefix="/api/connectors", tags=["connectors"])
CALLBACK_PATH = "/api/connectors/oauth/callback"
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,100}$")


def require_editor(user: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not user.has_min_role("user"):
        raise HTTPException(403, "Managing connectors requires the user or administrator role")
    return user


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    transport: Literal["http", "stdio"]
    url: str = Field(default="", max_length=500)
    headers: dict[str, str] = Field(default_factory=dict, max_length=20)
    command: str = Field(default="", max_length=200)
    args: list[str] = Field(default_factory=list, max_length=40)
    env: dict[str, str] = Field(default_factory=dict, max_length=40)
    source: str = Field(default="", max_length=200)


class ConnectorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    enabled: bool | None = None
    headers: dict[str, str] | None = Field(default=None, max_length=20)
    env: dict[str, str] | None = Field(default=None, max_length=40)
    disabled_tools: list[str] | None = Field(default=None, max_length=300)


def _validate_secrets(headers: dict[str, str] | None, env: dict[str, str] | None) -> None:
    for name, value in (headers or {}).items():
        if not _HEADER_NAME.match(name) or len(value) > 4000 or "\n" in value:
            raise HTTPException(422, f"Invalid header {name!r}")
    for name, value in (env or {}).items():
        if not _ENV_NAME.match(name) or len(value) > 4000:
            raise HTTPException(422, f"Invalid environment variable {name!r}")


def _public_base(request: Request) -> str:
    configured = os.getenv("MIZAN_PUBLIC_URL", "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _owned(user: TokenPayload, server_id: str) -> dict:
    server = (
        store.get_server(user.user_id, server_id)
        if re.fullmatch(r"[0-9a-f]{32}", server_id)
        else None
    )
    if server is None:
        raise HTTPException(404, "Connector not found")
    owned: dict = server
    return owned


@router.get("")
async def list_connectors(user: TokenPayload = Depends(require_auth)):
    return {
        "connectors": [store.public(server) for server in store.list_servers(user.user_id)],
        "capabilities": {
            "remote": True,
            "host_stdio": host_stdio_allowed(user.has_role("admin")),
            "sandbox_stdio": False,
        },
    }


@router.get("/registry")
async def browse_registry(
    search: str = Query(default="", max_length=100),
    cursor: str = Query(default="", max_length=300),
    limit: int = Query(default=30, ge=1, le=100),
    user: TokenPayload = Depends(require_auth),
):
    try:
        return await registry.search(search, limit, cursor)
    except Exception:
        raise HTTPException(502, "The MCP Registry is unavailable right now") from None


@router.post("")
async def add_connector(body: ConnectorCreate, user: TokenPayload = Depends(require_editor)):
    _validate_secrets(body.headers, body.env)
    config = body.model_dump()
    if body.transport == "http":
        try:
            await net_guard.check_url(body.url, require_https=True)
        except net_guard.BlockedDestination as exc:
            raise HTTPException(422, str(exc)) from None
        config.update(command="", args=[], env={})
    else:
        if not body.command.strip() or any(len(a) > 500 for a in body.args):
            raise HTTPException(422, "A command (and arguments up to 500 characters) is required")
        config["url"], config["headers"] = "", {}
        config["runtime"] = "host" if host_stdio_allowed(user.has_role("admin")) else "sandbox"
    try:
        server = store.add_server(user.user_id, config)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return store.public(server)


@router.get("/{server_id}")
async def get_connector(server_id: str, user: TokenPayload = Depends(require_auth)):
    return store.public(_owned(user, server_id))


@router.patch("/{server_id}")
async def update_connector(
    server_id: str, body: ConnectorUpdate, user: TokenPayload = Depends(require_editor)
):
    _owned(user, server_id)
    _validate_secrets(body.headers, body.env)
    changes = {key: value for key, value in body.model_dump().items() if value is not None}
    server = store.update_server(user.user_id, server_id, **changes)
    if {"headers", "env", "enabled"} & changes.keys():
        await manager.disconnect(user.user_id, server_id)
    return store.public(server or {})


@router.delete("/{server_id}")
async def delete_connector(server_id: str, user: TokenPayload = Depends(require_editor)):
    server = _owned(user, server_id)
    await manager.disconnect(user.user_id, server_id)
    if server.get("transport") == "stdio" and server.get("runtime") != "host":
        from workspace import session_client

        if session_client.available():
            key = session_client.session_key(user.user_id, server_id, kind="mcp")
            with contextlib.suppress(HTTPException):
                await session_client.call("DELETE", f"/sessions/{key}")
    store.delete_server(user.user_id, server_id)
    return {"deleted": server_id}


@router.post("/{server_id}/connect")
async def connect_connector(
    server_id: str, request: Request, user: TokenPayload = Depends(require_editor)
):
    """Connect now; OAuth servers return an authorization URL to open in a new window."""
    _owned(user, server_id)
    store.update_server(user.user_id, server_id, callback_url=_public_base(request) + CALLBACK_PATH)
    await manager.disconnect(user.user_id, server_id)
    try:
        connection = await manager.connect(user.user_id, server_id, interactive=True)
    except AuthorizationRequired:
        raise HTTPException(409, "Authorization is required; try Connect again") from None
    except ConnectorError as exc:
        raise HTTPException(502, str(exc)[:300]) from None
    server = store.public(store.get_server(user.user_id, server_id) or {})
    if connection.alive:
        return {"status": "connected", "connector": server}
    if connection.auth_url:
        return {
            "status": "authorization_required",
            "authorization_url": connection.auth_url,
            "connector": server,
        }
    return {"status": "connecting", "connector": server}


@router.post("/{server_id}/disconnect")
async def disconnect_connector(server_id: str, user: TokenPayload = Depends(require_editor)):
    _owned(user, server_id)
    await manager.disconnect(user.user_id, server_id)
    return store.public(store.update_server(user.user_id, server_id, status="disconnected") or {})


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    state: str = Query(default="", max_length=500),
    code: str = Query(default="", max_length=4000),
    iss: str | None = Query(default=None, max_length=500),
    error: str = Query(default="", max_length=200),
):
    """Browser return from an authorization server (public: the single-use state is the key)."""
    if error:
        accepted = manager.oauth.fail(state, error)
        message = f"Authorization was not granted ({error})."
    else:
        accepted = bool(state and code) and manager.oauth.complete(state, code, iss)
        message = (
            "Connected. You can close this window and return to MIZAN."
            if accepted
            else "This authorization link has expired or was already used. Connect again."
        )
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>MIZAN connector</title>"
        "<body style='font-family:system-ui;padding:2rem;max-width:32rem;margin:auto'>"
        f"<h1>{'✓' if accepted else '✕'} MIZAN</h1><p>{html.escape(message)}</p></body>",
        status_code=200 if accepted else 400,
    )
