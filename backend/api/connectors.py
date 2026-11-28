"""Owner-scoped MCP connectors: add, connect (OAuth), test, browse, remove.

Every route acts on the signed-in user's own connectors. The OAuth callback and
MIZAN's client metadata document are public (an authorization server's browser
redirect carries no session); the callback page then completes the sign-in with
the person's own credential, so only the user who started it can finish it.
"""

from __future__ import annotations

import contextlib
import html
import os
import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api.artifacts import require_auth
from connectors import net_guard, presets, registry, store
from connectors.manager import (
    CALLBACK_PATH,
    METADATA_PATH,
    AuthorizationRequired,
    ConnectorError,
    acknowledge_tools,
    host_stdio_allowed,
    manager,
    set_policy,
    trust_tool,
)
from security.auth import TokenPayload

router = APIRouter(prefix="/api/connectors", tags=["connectors"])
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,100}$")
_SCOPE = re.compile(r"^[\x21\x23-\x5B\x5D-\x7E]{1,200}$")  # RFC 6749 scope-token
_RUNNER_CHECK: dict[str, float | bool] = {"at": 0.0, "ok": False}

Transport = Literal["http", "sse", "stdio"]


def require_editor(user: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not user.has_min_role("user"):
        raise HTTPException(403, "Managing connectors requires the user or administrator role")
    return user


class OAuthClient(BaseModel):
    """A client registered with the authorization server beforehand (no dynamic
    registration): its ID, an optional secret (sealed) and the scopes to ask for."""

    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str | None = Field(default=None, max_length=2000)
    scopes: list[str] = Field(default_factory=list, max_length=40)


class Timeouts(BaseModel):
    connect_s: int | None = Field(default=None, ge=1, le=600)
    call_s: int | None = Field(default=None, ge=1, le=3600)


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    transport: Transport
    url: str = Field(default="", max_length=500)
    headers: dict[str, str] = Field(default_factory=dict, max_length=20)
    command: str = Field(default="", max_length=200)
    args: list[str] = Field(default_factory=list, max_length=40)
    env: dict[str, str] = Field(default_factory=dict, max_length=40)
    source: str = Field(default="", max_length=200)
    oauth: OAuthClient | None = None
    timeouts: Timeouts | None = None


class ConnectorUpdate(BaseModel):
    """Only the fields given change. ``headers``/``env`` merge per key (null removes
    a key); ``oauth: null`` removes a pre-registered client."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    enabled: bool | None = None
    transport: Transport | None = None
    url: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=200)
    args: list[str] | None = Field(default=None, max_length=40)
    headers: dict[str, str | None] | None = Field(default=None, max_length=20)
    env: dict[str, str | None] | None = Field(default=None, max_length=40)
    oauth: OAuthClient | None = None
    timeouts: Timeouts | None = None
    disabled_tools: list[str] | None = Field(default=None, max_length=300)


class ToolName(BaseModel):
    tool: str = Field(min_length=1, max_length=200)


class ToolPolicy(BaseModel):
    tool: str = Field(min_length=1, max_length=200)
    policy: Literal["allow", "ask", "never"]


class ToolNames(BaseModel):
    tools: list[str] = Field(default_factory=list, max_length=300)


class PromptRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, str] = Field(default_factory=dict, max_length=40)


class OAuthCompletion(BaseModel):
    state: str = Field(min_length=1, max_length=500)
    code: str = Field(min_length=1, max_length=4000)
    iss: str | None = Field(default=None, max_length=500)


def _validate_secrets(headers: dict | None, env: dict | None) -> None:
    for name, value in (headers or {}).items():
        if not _HEADER_NAME.match(name) or (
            value is not None and (len(value) > 4000 or "\n" in value or "\r" in value)
        ):
            raise HTTPException(422, f"Invalid header {name!r}")
    for name, value in (env or {}).items():
        if not _ENV_NAME.match(name) or (value is not None and len(value) > 4000):
            raise HTTPException(422, f"Invalid environment variable {name!r}")


def _validate_oauth(oauth: OAuthClient | None) -> None:
    if oauth is not None and any(not _SCOPE.match(scope) for scope in oauth.scopes):
        raise HTTPException(422, "Each OAuth scope is one word without spaces or quotes")


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


def _view(user_id: str, server: dict) -> dict:
    status, error = manager.live_status(user_id, server)
    view: dict = store.public(server, status=status, last_error=error)
    return view


def _sandbox_available() -> bool:
    from workspace import session_client

    return bool(session_client.available())


async def _runner_answers() -> bool:
    """The sandbox runner answers now (checked at most every 30 seconds)."""
    if not _sandbox_available():
        return False
    if time.monotonic() - float(_RUNNER_CHECK["at"]) < 30:
        return bool(_RUNNER_CHECK["ok"])
    from workspace import session_client

    try:
        await session_client.call("GET", "/health", timeout=3)
        ok = True
    except Exception:  # noqa: BLE001 - reported as unavailable
        ok = False
    _RUNNER_CHECK.update(at=time.monotonic(), ok=ok)
    return ok


async def _stop_sandbox(user_id: str, server: dict) -> None:
    if server.get("transport") != "stdio" or server.get("runtime") == "host":
        return
    from workspace import session_client

    if session_client.available():
        key = session_client.session_key(user_id, server["id"], kind="mcp")
        with contextlib.suppress(HTTPException):
            await session_client.call("DELETE", f"/sessions/{key}")


async def _check_remote(url: str) -> None:
    try:
        await net_guard.check_url(url, require_https=True)
    except net_guard.BlockedDestination as exc:
        raise HTTPException(422, str(exc)) from None


def _stdio_runtime(is_admin: bool) -> str:
    if host_stdio_allowed(is_admin):
        return "host"
    if not _sandbox_available():
        raise HTTPException(
            422,
            "Local (stdio) servers run in the sandbox runner, which this MIZAN server does not "
            "have; use a remote URL, or ask the administrator to set up the runner",
        )
    return "sandbox"


def _connector_error(exc: ConnectorError) -> HTTPException:
    return HTTPException(502, str(exc)[:300])


# ── listing, presets, registry ───────────────────────────────────────────


@router.get("")
async def list_connectors(user: TokenPayload = Depends(require_auth)):
    sandbox = _sandbox_available()
    return {
        "connectors": [_view(user.user_id, server) for server in store.list_servers(user.user_id)],
        "capabilities": {
            "remote": True,
            "host_stdio": host_stdio_allowed(user.has_role("admin")),
            "sandbox_stdio": sandbox,
            "runner_available": await _runner_answers() if sandbox else False,
        },
    }


@router.get("/presets")
async def list_presets(user: TokenPayload = Depends(require_auth)):
    """Curated connectors, each checked against the vendor's own documentation."""
    return {"presets": presets.presets()}


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
    _validate_oauth(body.oauth)
    config = body.model_dump()
    if body.transport in {"http", "sse"}:
        await _check_remote(body.url)
        config.update(command="", args=[], env={})
    else:
        if not body.command.strip() or any(len(a) > 500 for a in body.args):
            raise HTTPException(422, "A command (and arguments up to 500 characters) is required")
        config["url"], config["headers"], config["oauth"] = "", {}, None
        config["runtime"] = _stdio_runtime(user.has_role("admin"))
    try:
        server = store.add_server(user.user_id, config)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    manager.log(user.user_id, server["id"], f"[mizan] added ({server['transport']})")
    return _view(user.user_id, server)


# ── OAuth (public browser return, CIMD, completion) ──────────────────────


@router.get("/oauth/client-metadata.json")
async def oauth_client_metadata(request: Request):
    """MIZAN's OAuth client metadata document (CIMD): its URL is MIZAN's client ID at
    authorization servers that accept client metadata documents."""
    base = _public_base(request)
    return {
        "client_id": base + METADATA_PATH,
        "client_name": "MIZAN",
        "client_uri": base,
        "redirect_uris": [base + CALLBACK_PATH],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "web",
    }


_CALLBACK_SCRIPT = """
<script>
(async () => {
  const params = new URLSearchParams(location.search);
  const mark = document.getElementById("mark"), msg = document.getElementById("msg");
  const say = (ok, text) => { mark.textContent = ok ? "\\u2713" : "\\u2715"; msg.textContent = text; };
  const body = {state: params.get("state"), code: params.get("code"), iss: params.get("iss")};
  let token = null;
  try { token = localStorage.getItem("mizan_token"); } catch (e) {}
  if (!token) {
    if (window.opener) {
      window.opener.postMessage({type: "mizan:connector-oauth-code", ...body}, "*");
      say(true, "Return to MIZAN to finish connecting.");
    } else {
      say(false, "Open this link in the browser where you are signed in to MIZAN, then connect again.");
    }
    return;
  }
  try {
    const response = await fetch("/api/connectors/oauth/complete", {
      method: "POST",
      headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token},
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    const ok = response.ok && data.state === "connected";
    const error = ok ? null : (data.error || data.detail || "Authorization did not complete. Connect again.");
    say(ok, ok ? "Connected. You can close this window and return to MIZAN." : error);
    if (window.opener) {
      window.opener.postMessage(
        {type: "mizan:connector-oauth", state: data.state || "error", connector_id: data.connector_id || null, error},
        location.origin);
    }
    if (ok) setTimeout(() => window.close(), 1500);
  } catch (e) {
    say(false, "MIZAN could not be reached. Connect again.");
  }
})();
</script>
"""


def _page(mark: str, message: str, script: str = "", status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>MIZAN connector</title>"
        "<body style='font-family:system-ui;padding:2rem;max-width:32rem;margin:auto'>"
        f"<h1><span id=mark>{mark}</span> MIZAN</h1><p id=msg>{html.escape(message)}</p>"
        f"{script}</body>",
        status_code=status,
    )


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    state: str = Query(default="", max_length=500),
    code: str = Query(default="", max_length=4000),
    iss: str | None = Query(default=None, max_length=500),
    error: str = Query(default="", max_length=200),
):
    """Browser return from an authorization server.

    Public (the redirect carries no session). The page finishes the sign-in with the
    person's own MIZAN credential (``POST /oauth/complete``), and shows "Connected"
    only after MIZAN has exchanged the code for tokens."""
    if error:
        manager.oauth.fail(state, error)
        return _page("✕", f"Authorization was not granted ({error}).", status=400)
    if not (state and code) or manager.oauth.pending(state) is None:
        return _page(
            "✕",
            "This authorization link has expired or was already used. Connect again.",
            status=400,
        )
    return _page("…", "Finishing the connection…", _CALLBACK_SCRIPT)


@router.post("/oauth/complete")
async def oauth_complete(body: OAuthCompletion, user: TokenPayload = Depends(require_editor)):
    """Finish a sign-in this user started: MIZAN exchanges the code and answers once
    the connector is connected (or why not)."""
    pending = manager.oauth.pending(body.state)
    if pending is None or pending.user_id != user.user_id:
        raise HTTPException(404, "This authorization has expired or was started by another account")
    server_id = pending.server_id
    if not manager.oauth.complete(body.state, body.code, body.iss, user_id=user.user_id):
        raise HTTPException(404, "This authorization has expired or was already used")
    result = await manager.wait_oauth(user.user_id, server_id, timeout=30)
    return {**result, "connector_id": server_id}


# ── one connector ─────────────────────────────────────────────────────────


@router.get("/{server_id}")
async def get_connector(server_id: str, user: TokenPayload = Depends(require_auth)):
    return _view(user.user_id, _owned(user, server_id))


def _merge(current: dict, changes: dict | None) -> dict:
    merged = dict(current)
    for name, value in (changes or {}).items():
        for existing in [key for key in merged if key.lower() == name.lower()]:
            merged.pop(existing)
        if value is not None:
            merged[name] = value
    return merged


@router.patch("/{server_id}")
async def update_connector(
    server_id: str, body: ConnectorUpdate, user: TokenPayload = Depends(require_editor)
):
    server = _owned(user, server_id)
    given = body.model_fields_set
    _validate_secrets(body.headers, body.env)
    _validate_oauth(body.oauth)
    headers, env, _ = store.secrets_of(server) if store.secrets_readable(server) else ({}, {}, {})
    changes: dict = {}
    transport = body.transport or server.get("transport")
    if body.name is not None:
        changes["name"] = body.name[:60]
    if body.enabled is not None:
        changes["enabled"] = body.enabled
    if body.disabled_tools is not None:
        changes["disabled_tools"] = list(dict.fromkeys(body.disabled_tools))
    if body.timeouts is not None:
        # Given limits change; one given as null goes back to its default.
        merged = dict(server.get("timeouts") or {})
        for key in body.timeouts.model_fields_set:
            value = getattr(body.timeouts, key)
            if value:
                merged[key] = value
            else:
                merged.pop(key, None)
        changes["timeouts"] = merged
    drop_tokens = False
    if transport in {"http", "sse"}:
        url = body.url if body.url is not None else server.get("url", "")
        if transport != server.get("transport") or url != server.get("url"):
            await _check_remote(url)
        if url != server.get("url") or server.get("transport") == "stdio":
            drop_tokens = True
        changes.update(transport=transport, url=url, command="", args=[], env={}, runtime="")
        if body.headers is not None:
            changes["headers"] = _merge(headers, body.headers)
        if "oauth" in given:
            config = server.get("oauth_config") or {}
            if body.oauth is None:
                changes.update(oauth_config={}, oauth_secret="")
                drop_tokens = drop_tokens or bool(config)
            else:
                same_client = body.oauth.client_id == config.get("client_id")
                changes["oauth_config"] = {"client_id": body.oauth.client_id} | (
                    {"scopes": body.oauth.scopes} if body.oauth.scopes else {}
                )
                if body.oauth.client_secret is not None:
                    changes["oauth_secret"] = body.oauth.client_secret
                elif not same_client:
                    changes["oauth_secret"] = ""
                if not same_client or body.oauth.scopes != list(config.get("scopes") or []):
                    drop_tokens = True
    else:
        command = body.command if body.command is not None else server.get("command", "")
        args = body.args if body.args is not None else list(server.get("args") or [])
        if not str(command).strip() or any(len(a) > 500 for a in args):
            raise HTTPException(422, "A command (and arguments up to 500 characters) is required")
        changes.update(transport="stdio", command=command, args=args[:40], url="", headers={})
        if server.get("transport") != "stdio":
            changes["runtime"] = _stdio_runtime(user.has_role("admin"))
            changes.update(oauth_config={}, oauth_secret="")
            drop_tokens = True
        if body.env is not None:
            changes["env"] = _merge(env, body.env)
    if drop_tokens:
        changes["oauth"] = {}
    reconnect = bool(
        given
        & {"enabled", "transport", "url", "command", "args", "headers", "env", "oauth", "timeouts"}
    )
    if reconnect:
        await manager.disconnect(user.user_id, server_id)
        if body.enabled is False or changes.get("transport") != server.get("transport"):
            await _stop_sandbox(user.user_id, server)
    updated = store.update_server(user.user_id, server_id, **changes) or server
    manager.log(user.user_id, server_id, f"[mizan] settings changed: {', '.join(sorted(given))}")
    return _view(user.user_id, updated)


@router.delete("/{server_id}")
async def delete_connector(server_id: str, user: TokenPayload = Depends(require_editor)):
    server = _owned(user, server_id)
    await manager.disconnect(user.user_id, server_id)
    await _stop_sandbox(user.user_id, server)
    store.delete_server(user.user_id, server_id)
    manager.forget(user.user_id, server_id)
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
        connection = await manager.connect(
            user.user_id, server_id, interactive=True, raise_on_timeout=False
        )
    except AuthorizationRequired:
        raise HTTPException(409, "Authorization is required; try Connect again") from None
    except ConnectorError as exc:
        raise _connector_error(exc) from None
    server = _view(
        user.user_id, store.get_server(user.user_id, server_id) or _owned(user, server_id)
    )
    if connection.alive:
        return {"status": "connected", "connector": server}
    if connection.auth_url:
        return {
            "status": "authorization_required",
            "authorization_url": connection.auth_url,
            "connector": server,
        }
    return {"status": "connecting", "connector": server}


@router.get("/{server_id}/oauth/status")
async def connector_oauth_status(server_id: str, user: TokenPayload = Depends(require_auth)):
    """For the sign-in window: pending · connected · error (with why)."""
    return manager.oauth_status(user.user_id, _owned(user, server_id))


@router.post("/{server_id}/signout")
async def signout_connector(server_id: str, user: TokenPayload = Depends(require_editor)):
    """Revoke the OAuth tokens where the server allows it, and forget them."""
    _owned(user, server_id)
    await manager.signout(user.user_id, server_id)
    return {"ok": True}


@router.post("/{server_id}/test")
async def test_connector(server_id: str, user: TokenPayload = Depends(require_editor)):
    """Connect, list the tools and ping: ``{ok, latency_ms, tools, error?}``."""
    _owned(user, server_id)
    return await manager.test(user.user_id, server_id)


@router.get("/{server_id}/logs")
async def connector_logs(server_id: str, user: TokenPayload = Depends(require_auth)):
    """The last 200 lines: connections, errors, the server's own log messages and,
    for a process on the host, what it wrote to stderr."""
    _owned(user, server_id)
    return {"lines": manager.log_lines(user.user_id, server_id)}


@router.get("/{server_id}/resources")
async def connector_resources(server_id: str, user: TokenPayload = Depends(require_auth)):
    _owned(user, server_id)
    try:
        return {"resources": await manager.list_resources(user.user_id, server_id)}
    except AuthorizationRequired:
        raise HTTPException(409, "Sign in first: press Connect") from None
    except ConnectorError as exc:
        raise _connector_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - the server's own error
        raise HTTPException(502, str(exc)[:300]) from None


@router.get("/{server_id}/prompts")
async def connector_prompts(server_id: str, user: TokenPayload = Depends(require_auth)):
    _owned(user, server_id)
    try:
        return {"prompts": await manager.list_prompts(user.user_id, server_id)}
    except AuthorizationRequired:
        raise HTTPException(409, "Sign in first: press Connect") from None
    except ConnectorError as exc:
        raise _connector_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - the server's own error
        raise HTTPException(502, str(exc)[:300]) from None


@router.post("/{server_id}/prompts/get")
async def connector_prompt(
    server_id: str, body: PromptRequest, user: TokenPayload = Depends(require_editor)
):
    """One prompt filled in with its arguments: ``{description, messages: [{role, text}]}``."""
    _owned(user, server_id)
    try:
        return await manager.get_prompt(user.user_id, server_id, body.name, body.arguments)
    except AuthorizationRequired:
        raise HTTPException(409, "Sign in first: press Connect") from None
    except ConnectorError as exc:
        raise _connector_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - the server's own error
        raise HTTPException(502, str(exc)[:300]) from None


@router.post("/{server_id}/tools/trust")
async def trust_connector_tool_named(
    server_id: str, body: ToolName, user: TokenPayload = Depends(require_editor)
):
    """Accept a tool Amanah held (it changed, or it instructs the AI), as it is now."""
    _owned(user, server_id)
    server = trust_tool(user.user_id, server_id, body.tool)
    if server is None:
        raise HTTPException(404, "No such tool")
    return _view(user.user_id, server)


@router.post("/{server_id}/tools/policy")
async def connector_tool_policy(
    server_id: str, body: ToolPolicy, user: TokenPayload = Depends(require_editor)
):
    """allow (default) · ask (a person approves each call, in any mode) · never (not offered)."""
    _owned(user, server_id)
    server = set_policy(user.user_id, server_id, body.tool, body.policy)
    if server is None:
        raise HTTPException(404, "No such tool")
    return _view(user.user_id, server)


@router.post("/{server_id}/tools/ack")
async def acknowledge_connector_tools(
    server_id: str, body: ToolNames, user: TokenPayload = Depends(require_editor)
):
    """The person has seen these new tools (their ``new`` mark is cleared)."""
    owned = _owned(user, server_id)
    server = acknowledge_tools(user.user_id, server_id, body.tools)
    return _view(user.user_id, server or owned)


@router.post("/{server_id}/tools/{tool_name}/trust")
async def trust_connector_tool(
    server_id: str, tool_name: str, user: TokenPayload = Depends(require_editor)
):
    """Accept a held tool, named in the path (kept for older clients)."""
    _owned(user, server_id)
    server = trust_tool(user.user_id, server_id, tool_name)
    if server is None:
        raise HTTPException(404, "No such tool")
    return _view(user.user_id, server)


@router.post("/{server_id}/disconnect")
async def disconnect_connector(server_id: str, user: TokenPayload = Depends(require_editor)):
    owned = _owned(user, server_id)
    await manager.disconnect(user.user_id, server_id)
    updated = store.update_server(user.user_id, server_id, status="disconnected") or owned
    return _view(user.user_id, updated)
