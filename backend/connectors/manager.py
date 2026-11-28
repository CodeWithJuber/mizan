"""Live MCP connections with the official SDK (``mcp`` 2.x).

One owner task per (user, server) enters and leaves ``mcp.Client`` (the SDK's
anyio scopes must open and close in the same task); callers use the open
session concurrently. Transports: Streamable HTTP, the older HTTP+SSE, and stdio
(in the person's sandbox, or as a process on the host where the policy allows).

Lifetime and health:

- a connection closes after 10 idle minutes and reconnects on the next call;
- an idle open connection is pinged every two minutes and closed when it does
  not answer, so the next call starts a fresh session;
- a call that fails because the session ended (the server restarted and no
  longer knows the session, the process exited, the stream closed) reconnects
  and is retried once when the request cannot have run: the server refused the
  session, or the tool is read-only or idempotent;
- the connect and call limits are per connector (``timeouts``), and a timeout
  comes back as ``{"error": …, "code": "connector_timeout"}``.

OAuth uses the SDK's ``OAuthClientProvider`` (PKCE, dynamic registration, a
client metadata document, or a pre-registered client). Tokens are kept sealed
with their absolute expiry, so a connection opened after the token expired
refreshes it before the first request, and a 401 is answered by a refresh
before any new authorization is asked. From the Connectors page the owner task
waits for the browser to return; during a chat a connector that needs
authorization fails fast instead.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from connectors import naming, net_guard, secrets, store

logger = logging.getLogger("mizan.connectors")

IDLE_SECONDS = 600
HEALTH_IDLE_SECONDS = 120
HEALTH_TIMEOUT_SECONDS = 10
REAP_INTERVAL_SECONDS = 60
CALL_TIMEOUT_SECONDS = store.DEFAULT_CALL_S
OAUTH_WAIT_SECONDS = 600
MAX_TOOLS_PER_SERVER = 300
MAX_CONNECTIONS_PER_USER = 10
MAX_RESULT_CHARS = 20_000
MAX_INSTRUCTIONS = 2000
LOG_LINES = 200
ELICITATION_TIMEOUT_SECONDS = 300
ERROR_RETRY_SECONDS = 300
RESOURCE_TOOLS = ("resources_list", "resources_read")


class ConnectorError(RuntimeError):
    code = "connector_error"
    permanent = False

    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class AuthorizationRequired(ConnectorError):
    code = "auth_required"

    def __init__(self, url: str = ""):
        super().__init__("This connector needs authorization; connect it from the Connectors page")
        self.url = url


class ConnectorTimeout(ConnectorError):
    code = "connector_timeout"


class ConnectorNotAllowed(ConnectorError):
    code = "connector_not_allowed"
    permanent = True


def host_stdio_allowed(is_admin: bool) -> bool:
    """Who may launch a stdio server as a process on the backend host.

    ``admin`` (default): administrators only. ``all``: every user (the
    operator accepts that users can run commands on the host). ``off``.
    """
    policy = os.getenv("MIZAN_MCP_HOST_STDIO", "admin").strip().lower()
    return policy == "all" or (policy == "admin" and is_admin)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ── OAuth ────────────────────────────────────────────────────────────────


@dataclass
class _PendingAuth:
    user_id: str
    server_id: str
    future: asyncio.Future
    created: float = field(default_factory=time.time)


class OAuthBroker:
    """Single-use OAuth ``state`` → the waiting connection of one user (10 minutes).

    The state names the user and connector that started the authorization: only
    that user can complete it (``complete(..., user_id=…)``), and the code is
    exchanged by that user's connection, so tokens land only on that connector."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingAuth] = {}

    def open(self, state: str, user_id: str, server_id: str) -> asyncio.Future:
        self._expire()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[state] = _PendingAuth(user_id, server_id, future)
        return future

    def pending(self, state: str) -> _PendingAuth | None:
        self._expire()
        item = self._pending.get(state)
        return item if item is not None and not item.future.done() else None

    def complete(
        self, state: str, code: str, iss: str | None = None, *, user_id: str | None = None
    ) -> bool:
        from mcp.shared.auth import AuthorizationCodeResult

        pending = self._pending.get(state)
        if pending is None or pending.future.done():
            return False
        if user_id is not None and pending.user_id != user_id:
            return False
        self._pending.pop(state, None)
        pending.future.set_result(AuthorizationCodeResult(code=code, state=state, iss=iss))
        return True

    def fail(self, state: str, reason: str) -> bool:
        pending = self._pending.pop(state, None)
        if pending is None or pending.future.done():
            return False
        pending.future.set_exception(ConnectorError(f"Authorization was not granted: {reason}"))
        return True

    def _expire(self) -> None:
        cutoff = time.time() - OAUTH_WAIT_SECONDS
        for state in [s for s, p in self._pending.items() if p.created < cutoff or p.future.done()]:
            pending = self._pending.pop(state)
            if not pending.future.done():
                pending.future.cancel()


class EncryptedTokenStorage:
    """SDK TokenStorage backed by the sealed ``oauth`` field of a connector.

    Tokens are kept with their absolute expiry (``expires_at``), so a provider made
    for a later connection knows the token has expired and refreshes it first. A
    pre-registered client (``oauth_config.client_id``) is given to the SDK as the
    client's registration; a dynamic registration whose redirect URI is no longer
    MIZAN's callback is dropped so MIZAN registers again."""

    def __init__(
        self,
        user_id: str,
        server_id: str,
        callback: str = "",
        client_id: str = "",
        client_secret: str = "",
        scopes: list[str] | None = None,
    ):
        self.user_id, self.server_id = user_id, server_id
        self.callback = callback
        self.client_id, self.client_secret = client_id, client_secret
        self.scopes = list(scopes or [])
        self.provider: Any = None

    def _oauth(self) -> dict:
        server = store.get_server(self.user_id, self.server_id) or {}
        oauth: dict = store.secrets_of(server)[2]
        return oauth

    def stored_expiry(self) -> float | None:
        value = self._oauth().get("expires_at")
        return float(value) if isinstance(value, (int, float)) and value > 0 else None

    def stored_metadata(self) -> tuple[Any, Any, str | None]:
        """The authorization server's metadata, the resource's metadata and the
        server's URL, as discovered when the tokens were issued."""
        from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata

        oauth = self._oauth()
        metadata: Any = None
        resource: Any = None
        with contextlib.suppress(Exception):
            if oauth.get("as_metadata"):
                metadata = OAuthMetadata.model_validate(oauth["as_metadata"])
        with contextlib.suppress(Exception):
            if oauth.get("resource_metadata"):
                resource = ProtectedResourceMetadata.model_validate(oauth["resource_metadata"])
        return metadata, resource, oauth.get("auth_server_url")

    def _change(self, change: Callable[[dict], None]) -> None:
        store.change_oauth(self.user_id, self.server_id, change)

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        data = self._oauth().get("tokens")
        return OAuthToken.model_validate(data) if data else None

    async def set_tokens(self, tokens) -> None:
        now = time.time()
        expires_in = getattr(tokens, "expires_in", None)
        context = getattr(self.provider, "context", None)
        metadata = getattr(context, "oauth_metadata", None)
        resource = getattr(context, "protected_resource_metadata", None)
        auth_server = getattr(context, "auth_server_url", None)

        def change(oauth: dict) -> None:
            oauth["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
            oauth["obtained_at"] = now
            oauth["expires_at"] = now + float(expires_in) if expires_in else None
            if metadata is not None:
                # Kept so a later connection refreshes at the real token endpoint (the
                # SDK would otherwise guess /token on the MCP server's own origin).
                oauth["as_metadata"] = metadata.model_dump(mode="json", exclude_none=True)
                for name in ("revocation_endpoint", "token_endpoint", "issuer"):
                    value = getattr(metadata, name, None)
                    if value:
                        oauth[name] = str(value)
            if resource is not None:
                oauth["resource_metadata"] = resource.model_dump(mode="json", exclude_none=True)
            if auth_server:
                oauth["auth_server_url"] = str(auth_server)

        await asyncio.to_thread(self._change, change)

    def _preconfigured(self):
        from mcp.shared.auth import OAuthClientInformationFull

        return OAuthClientInformationFull(
            client_id=self.client_id,
            client_secret=self.client_secret or None,
            redirect_uris=[self.callback] if self.callback else None,
            token_endpoint_auth_method="client_secret_post" if self.client_secret else "none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(self.scopes) or None,
        )

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        if self.client_id:
            return self._preconfigured()
        oauth = self._oauth()
        data = oauth.get("client_info")
        if not data:
            return None
        info = OAuthClientInformationFull.model_validate(data)
        if self.stale(info) and not oauth.get("tokens"):
            await asyncio.to_thread(self.drop_client_info)
            return None
        return info

    def stale(self, info: Any) -> bool:
        """A registration made for another callback (MIZAN_PUBLIC_URL changed)."""
        if self.client_id or not self.callback or info is None:
            return False
        uris = [str(uri) for uri in getattr(info, "redirect_uris", None) or []]
        return bool(uris) and self.callback not in uris

    def drop_client_info(self) -> None:
        self._change(lambda oauth: oauth.pop("client_info", None))

    async def set_client_info(self, client_info) -> None:
        if self.client_id:
            return  # the pre-registered client is configuration, not state
        data = client_info.model_dump(mode="json", exclude_none=True)
        await asyncio.to_thread(self._change, lambda oauth: oauth.__setitem__("client_info", data))


def oauth_provider(
    *,
    server_url: str,
    storage: EncryptedTokenStorage,
    redirect_handler: Callable,
    callback_handler: Callable,
    client_metadata_url: str | None = None,
) -> Any:
    """The SDK's OAuth provider with MIZAN's three corrections: a stored token's
    expiry is restored, a 401 is answered by a refresh before a new authorization,
    and configured scopes are what the person is asked for."""
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata
    from pydantic import AnyUrl

    class MizanOAuth(OAuthClientProvider):
        async def _initialize(self) -> None:
            await super()._initialize()
            if self.context.current_tokens is None:
                return
            expiry = await asyncio.to_thread(storage.stored_expiry)
            if expiry:
                self.context.token_expiry_time = expiry
            metadata, resource, auth_server = await asyncio.to_thread(storage.stored_metadata)
            if metadata is not None and self.context.oauth_metadata is None:
                self.context.oauth_metadata = metadata
            if resource is not None and self.context.protected_resource_metadata is None:
                self.context.protected_resource_metadata = resource
            if auth_server and not self.context.auth_server_url:
                self.context.auth_server_url = auth_server

        async def _perform_authorization_code_grant(self) -> tuple[str, str]:
            if storage.scopes:
                self.context.client_metadata.scope = " ".join(storage.scopes)
            return await super()._perform_authorization_code_grant()

        async def _auth_flow(self, request):  # type: ignore[override]
            inner = super()._auth_flow(request)
            refreshed = False
            try:
                outgoing = await inner.__anext__()
                while True:
                    response = yield outgoing
                    if outgoing is request and response.status_code == 401 and not refreshed:
                        # A token the server no longer accepts: refresh it first; only
                        # when that fails does the SDK ask for a new authorization.
                        refreshed = True
                        if self.context.can_refresh_token():
                            refresh_response = yield await self._refresh_token()
                            if await self._handle_refresh_response(refresh_response):
                                self._add_auth_header(request)
                                response = yield request
                        if response.status_code == 401 and storage.stale(self.context.client_info):
                            self.context.client_info = None
                            await asyncio.to_thread(storage.drop_client_info)
                    outgoing = await inner.asend(response)
            except StopAsyncIteration:
                return
            finally:
                await inner.aclose()

    provider = MizanOAuth(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            client_name="MIZAN",
            redirect_uris=[AnyUrl(storage.callback)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",  # noqa: S106 - public PKCE client
            application_type="web",
            scope=" ".join(storage.scopes) or None,
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        client_metadata_url=client_metadata_url,
    )
    storage.provider = provider
    return provider


# ── results and tools ────────────────────────────────────────────────────


def map_result(result: Any, slug: str = "") -> dict:
    """CallToolResult → receipt; ``is_error`` becomes an error the agent can see."""
    texts, notes = [], []
    for block in getattr(result, "content", None) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            texts.append(str(getattr(block, "text", "")))
        elif kind == "image":
            notes.append(f"[image: {getattr(block, 'mime_type', 'image')}]")
        elif kind == "resource":
            resource = getattr(block, "resource", block)
            text = getattr(resource, "text", None)
            texts.append(str(text) if text else f"[resource: {getattr(resource, 'uri', '')}]")
        elif kind == "resource_link":
            uri = getattr(block, "uri", "")
            name = getattr(block, "name", "") or uri
            reader = naming.tool_name(slug, "resources_read") if slug else "the resources_read tool"
            texts.append(f"[resource link: {name} <{uri}> — read it with {reader}]")
        else:
            notes.append(f"[{kind or 'content'}]")
    text = "\n".join(texts + notes)
    receipt: dict[str, Any] = {"content": text[:MAX_RESULT_CHARS]}
    if len(text) > MAX_RESULT_CHARS:
        receipt["truncated"] = True
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        try:
            encoded = json.dumps(structured, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            encoded = str(structured)
        if len(encoded) <= MAX_RESULT_CHARS:
            receipt["structured"] = structured
        else:
            receipt["structured_preview"] = encoded[:MAX_RESULT_CHARS]
            receipt["structured_truncated"] = True
    if getattr(result, "is_error", False):
        return {"error": text[:2000] or "The MCP tool reported an error", **receipt}
    return receipt


def annotations_of(tool: Any) -> dict:
    """The tool's behaviour hints, by their protocol names (only those given)."""
    annotations = getattr(tool, "annotations", None)
    if annotations is None:
        return {}
    if isinstance(annotations, dict):
        source = annotations
        values = {
            "readOnlyHint": source.get("readOnlyHint", source.get("read_only_hint")),
            "destructiveHint": source.get("destructiveHint", source.get("destructive_hint")),
            "idempotentHint": source.get("idempotentHint", source.get("idempotent_hint")),
            "openWorldHint": source.get("openWorldHint", source.get("open_world_hint")),
        }
    else:
        values = {
            "readOnlyHint": getattr(annotations, "read_only_hint", None),
            "destructiveHint": getattr(annotations, "destructive_hint", None),
            "idempotentHint": getattr(annotations, "idempotent_hint", None),
            "openWorldHint": getattr(annotations, "open_world_hint", None),
        }
    return {key: bool(value) for key, value in values.items() if value is not None}


def fingerprint(description: str, schema: dict, annotations: dict | None = None) -> str:
    """What a tool told the model about itself; a change after approval is held.

    Without ``annotations`` this is the first version's fingerprint (description and
    schema only), kept to recognise pins made before annotations counted."""
    parts: list[Any] = [description or "", schema]
    if annotations is not None:
        parts.append(dict(sorted(annotations.items())))
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _previous(old: dict | None, pinned: str) -> dict | None:
    if not old:
        return None
    if old.get("held") == "changed" and old.get("previous"):
        previous: dict = old["previous"]
        return previous
    if old.get("fingerprint") != pinned:
        return None
    return {
        "description": old.get("raw_description", old.get("description", "")),
        "input_schema": old.get("input_schema") or {},
        "annotations": old.get("annotations") or {},
    }


def tool_snapshot(server: dict, tools: list[Any]) -> list[dict]:
    """The server's tools as the model will see them, with Amanah's checks.

    A tool is pinned to the description, schema and behaviour hints the user first
    accepted. A later change (a "rug pull", a read-only tool that stops saying so)
    or a description that instructs the AI (tool poisoning) holds the tool back
    from the model until the user trusts it; a changed tool keeps what was
    accepted before (``previous``) so the change can be shown. A tool that appears
    after the first listing is offered at once and marked ``new`` until the
    person has seen it.
    """
    from tadbir import amanah

    pins = server.get("pins") or {}
    upgraded = int(server.get("pin_version") or 1) >= 2
    before = {tool.get("name"): tool for tool in server.get("tools") or []}
    listed_before = bool(before) or bool(pins)
    snapshot, used = [], set()
    for tool in tools[:MAX_TOOLS_PER_SERVER]:
        exposed = naming.tool_name(server["slug"], tool.name)
        if exposed in used:
            continue
        used.add(exposed)
        annotations = annotations_of(tool)
        schema = naming.input_schema(getattr(tool, "input_schema", None))
        raw = tool.description or ""
        stamp = fingerprint(raw, schema, annotations)
        entry: dict[str, Any] = {
            "name": tool.name,
            "exposed": exposed,
            "description": naming.description(server["name"], raw),
            "raw_description": raw[: naming.MAX_DESCRIPTION],
            "input_schema": schema,
            "annotations": annotations,
            "read_only": bool(annotations.get("readOnlyHint")),
            "destructive": bool(annotations.get("destructiveHint")),
            "idempotent": bool(annotations.get("idempotentHint")),
            "fingerprint": stamp,
        }
        findings = amanah.scan(f"{raw}\n{json.dumps(schema, ensure_ascii=False)}", exposed)
        pinned = pins.get(tool.name)
        if pinned is not None and pinned != stamp:
            if not upgraded and pinned == fingerprint(raw, schema):
                entry["pin_upgrade"] = True  # pinned before hints counted: accepted once
            else:
                entry["held"] = "changed"
                entry["previous"] = _previous(before.get(tool.name), pinned)
        elif pinned is None and findings:
            entry["held"] = "flagged"
        if pinned is None and not entry.get("held") and listed_before:
            old = before.get(tool.name)
            entry["new"] = old is None or bool(old.get("new"))
        elif before.get(tool.name, {}).get("new") and not entry.get("held"):
            entry["new"] = True
        if findings:
            entry["amanah"] = [finding["excerpt"] for finding in findings[:3]]
        snapshot.append(entry)
    return snapshot


def pins_after(server: dict, snapshot: list[dict]) -> dict:
    """First-seen tools that passed the checks are pinned; held ones keep the old pin;
    pins made before behaviour hints counted are moved to the new fingerprint."""
    pins = dict(server.get("pins") or {})
    for tool in snapshot:
        if tool.get("held"):
            continue
        if tool["name"] not in pins or tool.pop("pin_upgrade", False):
            pins[tool["name"]] = tool["fingerprint"]
    for tool in snapshot:
        tool.pop("pin_upgrade", None)
    return pins


def trust_tool(user_id: str, server_id: str, name: str) -> dict | None:
    """The user accepts a held tool as it is now."""
    server = store.get_server(user_id, server_id)
    if server is None:
        return None
    tools = [dict(tool) for tool in server.get("tools") or []]
    found = False
    pins = dict(server.get("pins") or {})
    for tool in tools:
        if tool.get("name") == name and tool.get("fingerprint"):
            tool.pop("held", None)
            tool.pop("previous", None)
            tool["new"] = False
            found = True
            pins[name] = tool["fingerprint"]
    if not found:
        return None
    updated: dict | None = store.update_server(
        user_id, server_id, tools=tools, pins=pins, pin_version=2
    )
    return updated


def acknowledge_tools(user_id: str, server_id: str, names: list[str]) -> dict | None:
    """The person has seen these new tools."""
    server = store.get_server(user_id, server_id)
    if server is None:
        return None
    wanted = set(names)
    tools = [
        {**tool, "new": False} if tool.get("name") in wanted else dict(tool)
        for tool in server.get("tools") or []
    ]
    updated: dict | None = store.update_server(user_id, server_id, tools=tools)
    return updated


def set_policy(user_id: str, server_id: str, name: str, value: str) -> dict | None:
    """allow · ask · never for one tool (never is the tool switched off)."""
    server = store.get_server(user_id, server_id)
    if server is None or value not in store.POLICIES:
        return None
    if not any(tool.get("name") == name for tool in server.get("tools") or []):
        return None
    policies = {k: v for k, v in (server.get("policies") or {}).items() if k != name}
    disabled = [tool for tool in server.get("disabled_tools") or [] if tool != name]
    if value == "never":
        disabled.append(name)
    elif value == "ask":
        policies[name] = "ask"
    updated: dict | None = store.update_server(
        user_id, server_id, policies=policies, disabled_tools=disabled
    )
    return updated


def _resource_tool(server: dict, kind: str) -> dict:
    exposed = naming.tool_name(server["slug"], kind)
    if kind == "resources_list":
        description = (
            "List the resources (documents, files, records) this server offers, with their "
            "URIs. Read one with the resources_read tool."
        )
        schema: dict = {
            "type": "object",
            "properties": {"cursor": {"type": "string", "description": "Next page"}},
        }
    else:
        description = "Read one resource of this server by its URI (from resources_list or a link)."
        schema = {
            "type": "object",
            "properties": {"uri": {"type": "string", "description": "The resource URI"}},
            "required": ["uri"],
        }
    return {
        "name": kind,
        "exposed": exposed,
        "description": naming.description(server["name"], description),
        "input_schema": schema,
        "read_only": True,
        "destructive": False,
        "idempotent": True,
        "synthetic": kind,
    }


def resource_tools(server: dict) -> list[dict]:
    """``mcp__<server>__resources_list`` / ``__resources_read`` for a server that offers
    resources (a tool of the server's own with the same name wins)."""
    if not (server.get("capabilities") or {}).get("resources"):
        return []
    own = {tool.get("exposed") for tool in server.get("tools") or []}
    return [
        tool
        for tool in (_resource_tool(server, kind) for kind in RESOURCE_TOOLS)
        if tool["exposed"] not in own
    ]


def offered(server: dict, now: float | None = None) -> bool:
    """Whether the connector's tools are offered to the model at all."""
    if not server.get("enabled", True):
        return False
    status = server.get("status")
    if status == "auth_required":
        return False
    if status == "error":
        if server.get("error_permanent"):
            return False
        moment = time.time() if now is None else now
        return moment - float(server.get("error_at") or 0) > ERROR_RETRY_SECONDS
    return True


def resolve_tool(user_id: str, exposed: str) -> tuple[dict, dict] | None:
    if not exposed.startswith(naming.PREFIX):
        return None
    for server in store.list_servers(user_id):
        if not server.get("enabled", True):
            continue
        for tool in server.get("tools") or []:
            if (
                tool.get("exposed") == exposed
                and not tool.get("held")
                and store.policy(server, str(tool.get("name") or "")) != "never"
            ):
                return server, tool
        for tool in resource_tools(server):
            if tool["exposed"] == exposed:
                return server, tool
    return None


# ── connections ──────────────────────────────────────────────────────────


@dataclass(eq=False)
class _Caller:
    """Who is waiting on a call: for a server's question or progress that arrives
    outside the caller's own task (SSE and stdio servers)."""

    approvals: Any = None
    sink: Any = None

    @classmethod
    def capture(cls) -> _Caller:
        from agents.events import current_sink
        from security.approvals import current_approvals

        return cls(current_approvals(), current_sink())


def _session_closed(client: Any) -> bool:
    session = getattr(client, "_session", None)
    dispatcher = getattr(session, "_dispatcher", None)
    return bool(getattr(dispatcher, "_closed", False))


def _failure(exc: BaseException) -> str | None:
    """``session`` (the server did not accept the request: its session is gone, or
    it could not be reached), ``closed`` (the connection ended while waiting), or
    None (the tool itself failed)."""
    inner = getattr(exc, "exceptions", None)
    if inner:
        return _failure(inner[0])
    code = getattr(exc, "code", None)
    message = str(getattr(exc, "message", "") or exc).lower()
    if type(exc).__name__ == "MCPError":
        if code == -32000 and "closed" in message:
            return "closed"
        if (
            code == -32600
            and "session" in message
            and any(word in message for word in ("not found", "terminated", "expired", "unknown"))
        ):
            return "session"
        return None
    try:
        import anyio
        import httpx2
    except ImportError:  # pragma: no cover
        return None
    if isinstance(exc, httpx2.ConnectError):
        return "session"
    if isinstance(
        exc,
        (
            anyio.ClosedResourceError,
            anyio.BrokenResourceError,
            anyio.EndOfStream,
            httpx2.TransportError,
        ),
    ):
        return "closed"
    return None


def _has(exc: BaseException, kind: type) -> bool:
    if isinstance(exc, kind):
        return True
    return any(_has(inner, kind) for inner in getattr(exc, "exceptions", ()) or ())


def _find(exc: BaseException, kind: type) -> BaseException | None:
    if isinstance(exc, kind):
        return exc
    for inner in getattr(exc, "exceptions", ()) or ():
        found = _find(inner, kind)
        if found is not None:
            return found
    return None


def _describe(exc: BaseException) -> str:
    inner = getattr(exc, "exceptions", None)
    if inner:
        return _describe(inner[0])
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def list_all_tools(client: Any) -> list[Any]:
    tools: list[Any] = []
    cursor = None
    for _ in range(20):
        try:
            page = await client.list_tools(cursor=cursor, cache_mode="refresh")
        except TypeError:  # a client without the response cache
            page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = getattr(page, "next_cursor", None)
        if not cursor or len(tools) >= MAX_TOOLS_PER_SERVER:
            break
    return tools


def redact(line: str, known: tuple[str, ...] = ()) -> str:
    """A log line with credentials replaced by [redacted]: the connector's own sealed
    header and env values (exactly) and anything shaped like a credential (Satr's
    patterns, ``security/satr.py``)."""
    from security import satr

    for value in known:
        if value and len(value) >= 6:
            line = line.replace(value, "[redacted]")
    return str(satr.cover_text(line, labelled=False))


class _StderrTap:
    """A host process's stderr into the connector's log (last 200 lines)."""

    def __init__(self, write: Callable[[str], None]):
        read_fd, write_fd = os.pipe()
        self.writer = os.fdopen(write_fd, "w", buffering=1)
        self._reader = os.fdopen(read_fd, "r", errors="replace")
        self._write = write
        self._thread = threading.Thread(target=self._pump, daemon=True, name="mcp-stderr")
        self._thread.start()

    def _pump(self) -> None:
        with contextlib.suppress(Exception), self._reader:
            for line in self._reader:
                self._write(f"[stderr] {line.rstrip()[:500]}")

    def release(self) -> None:
        """Close the backend's copy of the pipe (the child keeps its own)."""
        with contextlib.suppress(Exception):
            self.writer.close()


class Connection:
    def __init__(self, manager: ConnectorManager, user_id: str, server: dict, interactive: bool):
        self.manager, self.user_id, self.server = manager, user_id, server
        self.known_secrets: tuple[str, ...] = ()
        self.interactive = interactive
        self.limits = store.timeouts(server)
        self.client: Any = None
        self.ready = asyncio.Event()
        self.auth_url: str = ""
        self.auth_event = asyncio.Event()
        self.closing = asyncio.Event()
        self.error: BaseException | None = None
        self.dead = ""
        self.timed_out = False
        self.inflight = 0
        self.callers: list[_Caller] = []
        self.last_used = time.monotonic()
        self.last_health = time.monotonic()
        self.task: asyncio.Task | None = None
        self.http_client: Any = None
        self.stderr: _StderrTap | None = None
        self._auth_future: asyncio.Future | None = None
        self._background: set[asyncio.Task] = set()
        self._init_timer: asyncio.TimerHandle | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.user_id, self.server["id"]

    @property
    def alive(self) -> bool:
        return self.client is not None and not self.closing.is_set() and not self.dead

    def log(self, line: str) -> None:
        self.manager.log(self.user_id, self.server["id"], redact(line, self.known_secrets))

    def start(self) -> None:
        self.task = asyncio.create_task(self._owner(), name=f"mcp:{self.server['slug']}")
        limit = self.limits["connect_s"] + (OAUTH_WAIT_SECONDS if self.interactive else 0)
        self._init_timer = asyncio.get_running_loop().call_later(limit, self._init_timeout)

    def _init_timeout(self) -> None:
        if not self.ready.is_set() and self.task is not None and not self.task.done():
            if self.auth_url and not self.interactive:
                return
            self.timed_out = True
            self.task.cancel()

    async def _owner(self) -> None:
        name = self.server["name"]
        try:
            client = await self.manager.build_client(self)
            async with client:
                self.client = client
                if self.stderr is not None:
                    self.stderr.release()
                await self.refresh_tools(client)
                self.ready.set()
                if self._init_timer is not None:
                    self._init_timer.cancel()
                if self.auth_url:
                    self.manager.oauth_done(self.user_id, self.server["id"], "connected")
                self.log(f"[mizan] connected ({self.server.get('transport')})")
                logger.info("Connector %s connected for a user", self.server.get("slug"))
                await self._watch(client)
        except BaseException as raised:  # noqa: BLE001 - recorded for the caller
            exc: BaseException = raised
            if self.timed_out:
                exc = ConnectorTimeout(
                    f"{name} did not finish connecting within {self.limits['connect_s']:.0f} "
                    "seconds"
                )
            cancelled = isinstance(exc, asyncio.CancelledError)
            status = "auth_required" if _has(exc, AuthorizationRequired) else "error"
            if self.ready.is_set() and not cancelled:
                # It was connected: the session ended (or its teardown failed), which the
                # next call answers by connecting again; not a connector error.
                self.dead = self.dead or f"the connection ended ({_describe(exc)[:200]})"
                cancelled = True
            else:
                self.error = exc
            if not cancelled:
                described = _describe(_find(exc, ConnectorError) or exc)[:300]
                permanent = bool(
                    _has(exc, secrets.SecretsUnreadable) or _has(exc, ConnectorNotAllowed)
                )
                store.update_server(
                    self.user_id,
                    self.server["id"],
                    status=status,
                    last_error=described,
                    error_at=time.time(),
                    error_permanent=permanent,
                )
                self.log(f"[mizan] {status}: {described}")
                logger.warning(
                    "Connector %s failed for a user: %s", self.server.get("slug"), described
                )
                if self.auth_url or self._auth_future is not None:
                    self.manager.oauth_done(self.user_id, self.server["id"], "error", described)
            if isinstance(exc, asyncio.CancelledError) and not self.timed_out:
                raise
        finally:
            if self._init_timer is not None:
                self._init_timer.cancel()
            self.client = None
            for task in list(self._background):
                task.cancel()
            if self.stderr is not None:
                self.stderr.release()
            if self.http_client is not None:
                with contextlib.suppress(Exception):
                    await self.http_client.aclose()
            if self.dead:
                store.update_server(
                    self.user_id,
                    self.server["id"],
                    status="disconnected",
                    last_error=self.dead,
                )
                self.log(f"[mizan] disconnected: {self.dead}")
            self.ready.set()
            self.auth_event.set()

    async def _watch(self, client: Any) -> None:
        """Wait until asked to close; notice a session the server or process ended."""
        while not self.closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.closing.wait(), timeout=2.0)
            if not self.closing.is_set() and _session_closed(client):
                self.dead = "the server closed the connection"
                return

    async def refresh_tools(self, client: Any | None = None) -> None:
        client = client or self.client
        tools = await list_all_tools(client)
        server = store.get_server(self.user_id, self.server["id"]) or self.server
        snapshot = tool_snapshot(server, tools)
        pins = pins_after(server, snapshot)
        instructions = ""
        capabilities: dict[str, bool] = {}
        with contextlib.suppress(Exception):
            instructions = str(getattr(client, "instructions", None) or "")[:MAX_INSTRUCTIONS]
        with contextlib.suppress(Exception):
            caps = client.server_capabilities
            capabilities = {
                "resources": getattr(caps, "resources", None) is not None,
                "prompts": getattr(caps, "prompts", None) is not None,
            }
        from tadbir import amanah

        flagged = bool(instructions) and bool(
            amanah.scan(instructions, f"mcp__{self.server['slug']}__instructions")
        )
        if flagged:
            self.log("[mizan] the server's instructions address the AI; they are not shown to it")
        held = [tool["name"] for tool in snapshot if tool.get("held")]
        new = [tool["name"] for tool in snapshot if tool.get("new")]
        store.update_server(
            self.user_id,
            self.server["id"],
            tools=snapshot,
            pins=pins,
            pin_version=2,
            instructions=instructions,
            instructions_flagged=flagged,
            capabilities=capabilities,
            status="connected",
            last_error="",
            error_at=0,
            error_permanent=False,
            connected_at=_now_iso(),
        )
        self.server = store.get_server(self.user_id, self.server["id"]) or self.server
        self.log(
            f"[mizan] {len(snapshot)} tools listed"
            + (f", held: {', '.join(held[:10])}" if held else "")
            + (f", new: {', '.join(new[:10])}" if new else "")
        )

    # SDK callbacks ----------------------------------------------------------

    async def redirect(self, url: str) -> None:
        if not self.interactive:
            raise AuthorizationRequired(url)
        state = parse_qs(urlsplit(url).query).get("state", [""])[0]
        if not state:
            raise ConnectorError("The authorization server returned no state")
        self._auth_future = self.manager.oauth.open(state, self.user_id, self.server["id"])
        self.manager.oauth_done(self.user_id, self.server["id"], "pending")
        self.auth_url = url
        self.log("[mizan] waiting for the person to authorize in the browser")
        self.auth_event.set()

    async def callback(self):
        if self._auth_future is None:
            raise ConnectorError("Authorization expired; connect again")
        return await asyncio.wait_for(self._auth_future, timeout=OAUTH_WAIT_SECONDS)

    async def on_log(self, params: Any) -> None:
        data = getattr(params, "data", "")
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
        source = getattr(params, "logger", None)
        self.log(
            f"[{getattr(params, 'level', 'info')}]{f' {source}:' if source else ''} {text[:500]}"
        )

    async def on_message(self, message: Any) -> None:
        if isinstance(message, Exception):
            self.log(f"[mizan] transport: {_describe(message)[:300]}")
            return
        method = str(getattr(message, "method", "") or "")
        if method == "notifications/tools/list_changed" or type(message).__name__ == (
            "ToolListChangedNotification"
        ):
            self.log("[mizan] the server's tools changed; listing them again")
            task = asyncio.create_task(self._relist())
            self._background.add(task)
            task.add_done_callback(self._background.discard)

    async def _relist(self) -> None:
        try:
            if self.alive:
                await self.refresh_tools()
        except Exception as exc:  # noqa: BLE001 - the old list stays
            self.log(f"[mizan] listing tools again failed: {_describe(exc)[:200]}")

    def _interactive_caller(self) -> _Caller | None:
        for caller in reversed(self.callers):
            approvals = caller.approvals
            if approvals is not None and approvals.interactive and caller.sink is not None:
                return caller
        return None

    async def elicit(self, context: Any, params: Any) -> Any:
        """A server's question to the person, asked in the live chat (or declined)."""
        import mcp_types as types

        from agents.events import bind_event_sink, current_sink, emit
        from connectors import elicitation
        from security.approvals import current_approvals

        approvals, sink = current_approvals(), current_sink()
        if approvals is None or sink is None:
            caller = self._interactive_caller()
            if caller is not None:
                approvals, sink = caller.approvals, caller.sink
        if (
            approvals is None
            or sink is None
            or not approvals.interactive
            or approvals.deferred
            or approvals.user_id != self.user_id
        ):
            self.log("[mizan] the server asked a question; no one is here to answer: declined")
            return types.ElicitResult(action="decline")
        schema = getattr(params, "requested_schema", None)
        url = getattr(params, "url", None)
        elicitation_id, future = elicitation.broker.open(
            self.user_id, approvals.session_id, self.server["name"]
        )
        try:
            with bind_event_sink(sink):
                await emit(
                    "elicitation",
                    {
                        "id": elicitation_id,
                        "server": self.server["name"],
                        "message": str(getattr(params, "message", ""))[:2000],
                        "schema": schema,
                        **({"url": str(url)} if url else {}),
                        "expires_in": ELICITATION_TIMEOUT_SECONDS,
                    },
                )
                try:
                    answer = await asyncio.wait_for(future, timeout=ELICITATION_TIMEOUT_SECONDS)
                except (TimeoutError, asyncio.CancelledError):
                    answer = {"action": "cancel", "content": {}}
                await emit(
                    "elicitation_resolved", {"id": elicitation_id, "action": answer["action"]}
                )
        finally:
            elicitation.broker.close(elicitation_id)
        action = answer.get("action", "cancel")
        content = answer.get("content") or {}
        if action == "accept" and isinstance(schema, dict) and schema:
            from tadbir import amal

            if amal.problems(content, schema):
                self.log("[mizan] the answer did not fit the server's question: cancelled")
                return types.ElicitResult(action="cancel")
        self.log(f"[mizan] the person answered the server's question: {action}")
        if action == "accept":
            return types.ElicitResult(action="accept", content=content)
        return types.ElicitResult(action=action)


class ConnectorManager:
    def __init__(self) -> None:
        self.connections: dict[tuple[str, str], Connection] = {}
        self.oauth = OAuthBroker()
        # Tests (and the sandbox runner later) may supply their own client.
        self.client_factory: Callable[[Connection], Any] | None = None
        # The owner's roles by user id (set by the app: launch-time policy checks).
        self.role_lookup: Callable[[str], list[str] | None] | None = None
        # How the protocol version is chosen: "auto" (probe 2026-07-28, fall back to
        # the initialize handshake) or "legacy" (the handshake only).
        self.client_mode = "auto"
        self._reaper: asyncio.Task | None = None
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.logs: dict[tuple[str, str], collections.deque[str]] = {}
        self._oauth_states: dict[tuple[str, str], dict] = {}

    # logs ---------------------------------------------------------------

    def log(self, user_id: str, server_id: str, line: str) -> None:
        buffer = self.logs.get((user_id, server_id))
        if buffer is None:
            buffer = self.logs[(user_id, server_id)] = collections.deque(maxlen=LOG_LINES)
        buffer.append(f"{_now_iso()} {redact(line)}")

    def log_lines(self, user_id: str, server_id: str) -> list[str]:
        return list(self.logs.get((user_id, server_id)) or [])

    def forget(self, user_id: str, server_id: str) -> None:
        self.logs.pop((user_id, server_id), None)
        self._oauth_states.pop((user_id, server_id), None)

    # OAuth state for the popup flow ---------------------------------------

    def oauth_done(self, user_id: str, server_id: str, state: str, error: str = "") -> None:
        record = self._oauth_states.get((user_id, server_id))
        if record is None or state == "pending":
            record = {"event": asyncio.Event()}
            self._oauth_states[(user_id, server_id)] = record
        record.update(state=state, error=error, at=time.time())
        if state != "pending":
            record["event"].set()

    def oauth_status(self, user_id: str, server: dict) -> dict:
        record = self._oauth_states.get((user_id, server["id"]))
        if record is not None:
            return {
                "state": record["state"],
                **({"error": record["error"]} if record.get("error") else {}),
            }
        connection = self.connections.get((user_id, server["id"]))
        if connection is not None and connection.alive:
            return {"state": "connected"}
        if store.auth_view(server)["signed_in"] and server.get("status") != "auth_required":
            return {"state": "connected"}
        return {"state": "error", "error": server.get("last_error") or "Not signed in"}

    async def wait_oauth(self, user_id: str, server_id: str, timeout: float = 30.0) -> dict:
        record = self._oauth_states.get((user_id, server_id))
        if record is None:
            return {"state": "error", "error": "No authorization is in progress"}
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(record["event"].wait(), timeout=timeout)
        return {
            "state": record["state"],
            **({"error": record["error"]} if record.get("error") else {}),
        }

    # clients ------------------------------------------------------------

    def _owner_is_admin(self, user_id: str) -> bool:
        from security.auth import current_user_id, request_has_role

        if current_user_id() == user_id:
            return bool(request_has_role("admin"))
        if self.role_lookup is not None:
            roles = self.role_lookup(user_id)
            return roles is not None and "admin" in roles
        return False

    def _home(self, user_id: str, server_id: str) -> Path:
        owner = hashlib.sha256(user_id.encode()).hexdigest()[:16]
        home = Path(os.getenv("MIZAN_DATA_DIR", "data")) / "connectors" / "home" / owner / server_id
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        return home

    def _callbacks(self, connection: Connection) -> dict:
        return {
            "elicitation_callback": connection.elicit,
            "logging_callback": connection.on_log,
            "message_handler": connection.on_message,
        }

    async def build_client(self, connection: Connection) -> Any:
        if self.client_factory is not None:
            return self.client_factory(connection)
        from mcp import Client, Implementation

        server = connection.server
        try:
            headers, env, _oauth = store.secrets_of(server)
        except secrets.SecretsUnreadable as exc:
            raise ConnectorError(str(exc), code=exc.code) from None
        # The log never repeats a value this connector was given in secret.
        connection.known_secrets = tuple(
            str(value) for value in [*(headers or {}).values(), *(env or {}).values()] if value
        )
        info = Implementation(name="mizan", version="3")
        options = {
            "read_timeout_seconds": connection.limits["call_s"],
            "client_info": info,
            "mode": self.client_mode,
            **self._callbacks(connection),
        }
        transport = server.get("transport")
        if transport in {"http", "sse"}:
            return Client(await self._http_transport(connection, headers), **options)
        if transport == "stdio":
            argv = [server["command"], *list(server.get("args") or [])]
            if server.get("runtime") != "host":
                from workspace import session_client

                if not session_client.available():
                    raise ConnectorNotAllowed(
                        "Local MCP servers for this account run in the sandbox runner, which "
                        "is not enabled on this server; ask the administrator, or use a "
                        "remote URL"
                    )
                from .runner_transport import runner_stdio_client

                return Client(
                    runner_stdio_client(connection.user_id, server["id"], argv, env), **options
                )
            # The host policy and the owner's role are checked at every launch, not
            # only when the connector was added.
            if not host_stdio_allowed(self._owner_is_admin(connection.user_id)):
                raise ConnectorNotAllowed(
                    "Local MCP servers on this server's host are not allowed for this account "
                    "now (MIZAN_MCP_HOST_STDIO); remove the connector and add it again to run "
                    "it in the sandbox"
                )
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            home = await asyncio.to_thread(self._home, connection.user_id, server["id"])
            minimal = {
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "HOME": str(home),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            }
            parameters = StdioServerParameters(
                command=server["command"],
                args=list(server.get("args") or []),
                env={**minimal, **env},
                cwd=str(home),
            )
            connection.stderr = _StderrTap(connection.log)
            return Client(stdio_client(parameters, errlog=connection.stderr.writer), **options)
        raise ConnectorError("Unknown connector transport")

    def _http_client(self, connection: Connection, headers: dict, auth: Any, timeout: Any = None):
        import httpx2
        from mcp.shared._httpx_utils import MCP_DEFAULT_SSE_READ_TIMEOUT, MCP_DEFAULT_TIMEOUT

        connect_s = min(connection.limits["connect_s"], MCP_DEFAULT_TIMEOUT)
        client = httpx2.AsyncClient(
            headers=headers or None,
            auth=auth,
            timeout=timeout or httpx2.Timeout(connect_s, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
            transport=net_guard.pinned_transport(),
            follow_redirects=False,
            event_hooks={
                "request": [net_guard.connector_request_hook(connection.server["url"])],
                "response": [],
            },
        )
        return client

    async def _http_transport(self, connection: Connection, headers: dict) -> Any:
        server = connection.server
        url = server["url"]
        await net_guard.check_url(url, require_https=True)
        auth = None
        if not any(name.lower() == "authorization" for name in headers):
            callback = server.get("callback_url") or _default_callback()
            if callback:
                config = server.get("oauth_config") or {}
                try:
                    secret = store.oauth_client_secret(server)
                except secrets.SecretsUnreadable as exc:
                    raise ConnectorError(str(exc), code=exc.code) from None
                storage = EncryptedTokenStorage(
                    connection.user_id,
                    server["id"],
                    callback=str(callback),
                    client_id=str(config.get("client_id") or ""),
                    client_secret=secret,
                    scopes=list(config.get("scopes") or []),
                )
                auth = oauth_provider(
                    server_url=url,
                    storage=storage,
                    redirect_handler=connection.redirect,
                    callback_handler=connection.callback,
                    client_metadata_url=None if storage.client_id else _metadata_url(str(callback)),
                )
        if server.get("transport") == "sse":
            from mcp.client.sse import sse_client

            def factory(headers=None, timeout=None, auth=None):
                return self._http_client(connection, headers or {}, auth, timeout)

            return sse_client(
                url,
                headers=headers or None,
                timeout=min(connection.limits["connect_s"], 30.0),
                httpx_client_factory=factory,
                auth=auth,
            )
        from mcp.client.streamable_http import streamable_http_client

        # The SDK closes only clients it made; this one is closed with the connection.
        connection.http_client = self._http_client(connection, headers, auth)
        return streamable_http_client(url, http_client=connection.http_client)

    def _lock(self, key: tuple[str, str]) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def connect(
        self,
        user_id: str,
        server_id: str,
        *,
        interactive: bool = False,
        wait: float | None = None,
        raise_on_timeout: bool = True,
    ) -> Connection:
        key = (user_id, server_id)
        async with self._lock(key):
            server = store.get_server(user_id, server_id)
            if server is None:
                raise ConnectorError("Connector not found", code="not_found")
            if not server.get("enabled", True):
                raise ConnectorError("Connector is disabled", code="disabled")
            limit = store.timeouts(server)["connect_s"] if wait is None else wait
            current = self.connections.get(key)
            if current is not None and current.alive:
                return current
            if current is not None and current.task is not None and not current.task.done():
                # Still starting, or waiting for the user's browser authorization.
                if current.auth_url and not interactive:
                    raise AuthorizationRequired(current.auth_url)
                if current.auth_url and interactive:
                    return current
                connection = current
            else:
                if current is not None:
                    self.connections.pop(key, None)
                if not store.secrets_readable(server):
                    error = secrets.SecretsUnreadable()
                    store.update_server(
                        user_id,
                        server_id,
                        status="error",
                        last_error=str(error),
                        error_at=time.time(),
                        error_permanent=True,
                    )
                    raise ConnectorError(str(error), code=error.code)
                await self._make_room(user_id)
                connection = Connection(self, user_id, server, interactive)
                self.connections[key] = connection
                connection.start()
        waiters = [
            asyncio.create_task(connection.ready.wait()),
            asyncio.create_task(connection.auth_event.wait()),
        ]
        try:
            await asyncio.wait(waiters, timeout=limit + 1, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()
        if connection.alive:
            return connection
        if connection.timed_out and connection.task is not None and not connection.task.done():
            # The start was cut off: let the owner finish unwinding (a process is
            # stopped within seconds) so its error is recorded before answering.
            await asyncio.wait({connection.task}, timeout=8)
        if connection.error is not None:
            error = connection.error
            if _has(error, AuthorizationRequired):
                raise AuthorizationRequired()
            known = _find(error, ConnectorError)
            if isinstance(known, ConnectorError):
                raise known
            raise ConnectorError(_describe(error))
        if interactive and connection.auth_url:
            return connection
        if connection.dead:
            raise ConnectorError(
                f"{connection.server['name']}: {connection.dead}", code="connector_disconnected"
            )
        if raise_on_timeout:
            raise ConnectorTimeout(
                f"{connection.server['name']} did not finish connecting within {limit:.0f} seconds"
            )
        return connection

    async def _make_room(self, user_id: str) -> None:
        """At most 10 open connections per user: close the least recently used idle one."""
        open_for_user = [c for (u, _), c in self.connections.items() if u == user_id and c.alive]
        if len(open_for_user) < MAX_CONNECTIONS_PER_USER:
            return
        idle = [c for c in open_for_user if c.inflight == 0]
        if idle:
            await self._close(min(idle, key=lambda c: c.last_used))

    async def call(self, user_id: str, exposed: str, arguments: dict) -> dict:
        resolved = resolve_tool(user_id, exposed)
        if resolved is None:
            return {"error": f"Unknown connector tool {exposed}", "code": "unknown_tool"}
        server, tool = resolved
        name = server["name"]
        limits = store.timeouts(server)
        caller = _Caller.capture()
        safe = bool(tool.get("synthetic") or tool.get("read_only") or tool.get("idempotent"))
        for attempt in range(2):
            try:
                connection = await self.connect(user_id, server["id"])
            except AuthorizationRequired:
                return {
                    "error": "This connector needs authorization: open Connectors and press Connect",
                    "connector": name,
                    "auth_required": True,
                    "code": "auth_required",
                }
            except ConnectorError as exc:
                return {"error": str(exc)[:300], "connector": name, "code": exc.code}
            connection.inflight += 1
            connection.last_used = time.monotonic()
            connection.callers.append(caller)
            try:
                result = await asyncio.wait_for(
                    self._invoke(connection, tool, arguments or {}, caller, limits["call_s"]),
                    timeout=limits["call_s"],
                )
            except TimeoutError:
                connection.log(f"[mizan] {tool['name']} timed out after {limits['call_s']:.0f}s")
                return {
                    "error": f"{name} did not answer within {limits['call_s']:.0f} seconds",
                    "connector": name,
                    "code": "connector_timeout",
                }
            except Exception as exc:  # noqa: BLE001 - a receipt, not a crash
                kind = _failure(exc)
                if kind is None:
                    return {"error": _describe(exc)[:300], "connector": name, "code": "tool_error"}
                connection.dead = connection.dead or (
                    "the server no longer knows this session"
                    if kind == "session"
                    else "the connection closed"
                )
                await self._close(connection)
                if attempt == 0 and (kind == "session" or safe):
                    connection.log("[mizan] reconnecting and trying the call once more")
                    continue
                return {
                    "error": f"The connection to {name} closed during the call; it may or may not "
                    "have run. MIZAN will reconnect on the next call",
                    "connector": name,
                    "code": "connector_disconnected",
                }
            finally:
                connection.inflight -= 1
                connection.last_used = time.monotonic()
                with contextlib.suppress(ValueError):
                    connection.callers.remove(caller)
            if isinstance(result, dict):
                return {**result, "connector": name}
            return {**map_result(result, server["slug"]), "connector": name}
        return {
            "error": f"{name} could not be reached",
            "connector": name,
            "code": "connector_disconnected",
        }

    async def _invoke(
        self, connection: Connection, tool: dict, arguments: dict, caller: _Caller, call_s: float
    ) -> Any:
        synthetic = tool.get("synthetic")
        if synthetic == "resources_list":
            listed = await self._list_resources(connection, str(arguments.get("cursor") or ""))
            return {"content": json.dumps(listed, ensure_ascii=False)[:MAX_RESULT_CHARS], **listed}
        if synthetic == "resources_read":
            uri = str(arguments.get("uri") or "")
            if not uri:
                return {"error": "A resource URI is required", "code": "invalid_arguments"}
            return await self._read_resource(connection, uri)
        progress = None
        if caller.sink is not None:
            from agents.events import bind_event_sink, emit

            sink, server_name, tool_name = caller.sink, connection.server["name"], tool["name"]

            async def progress(value: float, total: float | None, message: str | None) -> None:
                with bind_event_sink(sink):
                    await emit(
                        "tool_progress",
                        {
                            "tool": tool["exposed"],
                            "server": server_name,
                            "name": tool_name,
                            "progress": value,
                            "total": total,
                            "message": (message or "")[:500],
                        },
                    )

        return await connection.client.call_tool(
            tool["name"], arguments, read_timeout_seconds=call_s, progress_callback=progress
        )

    async def _list_resources(self, connection: Connection, cursor: str = "") -> dict:
        page = await connection.client.list_resources(cursor=cursor or None)
        return {
            "resources": [
                {
                    "uri": str(item.uri),
                    "name": item.name or str(item.uri),
                    "description": (item.description or "")[:500],
                    "mime_type": item.mime_type or "",
                }
                for item in page.resources[:500]
            ],
            "next_cursor": getattr(page, "next_cursor", None),
        }

    async def _read_resource(self, connection: Connection, uri: str) -> dict:
        result = await connection.client.read_resource(uri)
        parts = []
        for item in getattr(result, "contents", None) or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
            else:
                blob = getattr(item, "blob", "") or ""
                parts.append(
                    f"[binary {getattr(item, 'mime_type', None) or 'data'}, {len(blob) * 3 // 4} bytes]"
                )
        text = "\n".join(parts)
        receipt: dict[str, Any] = {"uri": uri, "content": text[:MAX_RESULT_CHARS]}
        if len(text) > MAX_RESULT_CHARS:
            receipt["truncated"] = True
        return receipt

    async def list_resources(self, user_id: str, server_id: str) -> list[dict]:
        connection = await self.connect(user_id, server_id)
        caps = connection.client.server_capabilities
        if getattr(caps, "resources", None) is None:
            return []
        found: list[dict] = []
        cursor = ""
        for _ in range(5):
            page = await self._list_resources(connection, cursor)
            found += page["resources"]
            cursor = page.get("next_cursor") or ""
            if not cursor or len(found) >= 500:
                break
        return found[:500]

    async def list_prompts(self, user_id: str, server_id: str) -> list[dict]:
        connection = await self.connect(user_id, server_id)
        caps = connection.client.server_capabilities
        if getattr(caps, "prompts", None) is None:
            return []
        page = await connection.client.list_prompts()
        return [
            {
                "name": prompt.name,
                "description": (prompt.description or "")[:1000],
                "arguments": [
                    {
                        "name": argument.name,
                        "description": (argument.description or "")[:500],
                        "required": bool(argument.required),
                    }
                    for argument in prompt.arguments or []
                ],
            }
            for prompt in page.prompts[:200]
        ]

    async def get_prompt(
        self, user_id: str, server_id: str, name: str, arguments: dict[str, str]
    ) -> dict:
        connection = await self.connect(user_id, server_id)
        result = await connection.client.get_prompt(name, arguments or None)
        messages = []
        for message in result.messages or []:
            content = message.content
            text = getattr(content, "text", None)
            messages.append(
                {
                    "role": message.role,
                    "text": str(text)[:MAX_RESULT_CHARS]
                    if text is not None
                    else f"[{content.type}]",
                }
            )
        return {"description": result.description or "", "messages": messages}

    async def test(self, user_id: str, server_id: str) -> dict:
        """Open a fresh connection (unless calls are running), list the tools, ping."""
        started = time.monotonic()
        current = self.connections.get((user_id, server_id))
        if current is not None and current.inflight == 0:
            await self._close(current)
        try:
            connection = await self.connect(user_id, server_id)
            await self._ping(connection)
        except AuthorizationRequired:
            return {
                "ok": False,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "tools": 0,
                "error": "Sign in first: press Connect",
            }
        except Exception as exc:  # noqa: BLE001 - the test reports it
            message = str(exc) if isinstance(exc, ConnectorError) else _describe(exc)
            self.log(user_id, server_id, f"[mizan] test failed: {message[:300]}")
            return {
                "ok": False,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "tools": 0,
                "error": message[:300],
            }
        server = store.get_server(user_id, server_id) or {}
        latency = int((time.monotonic() - started) * 1000)
        self.log(user_id, server_id, f"[mizan] test passed in {latency} ms")
        return {"ok": True, "latency_ms": latency, "tools": len(server.get("tools") or [])}

    async def _ping(self, connection: Connection) -> None:
        """A ping the server answers (an error reply still proves it is there)."""
        try:
            await asyncio.wait_for(
                connection.client.session.send_ping(), timeout=HEALTH_TIMEOUT_SECONDS
            )
        except Exception as exc:
            if type(exc).__name__ == "MCPError" and _failure(exc) is None:
                return  # e.g. ping is not a method on a 2026-07-28 server
            raise
        finally:
            connection.last_health = time.monotonic()

    def live_status(self, user_id: str, server: dict) -> tuple[str, str | None]:
        """connected · connecting · disconnected · error · auth_required · disabled."""
        if not server.get("enabled", True):
            return "disabled", None
        if not store.secrets_readable(server):
            return "error", str(secrets.SecretsUnreadable())
        connection = self.connections.get((user_id, server["id"]))
        if connection is not None:
            if connection.alive:
                return "connected", None
            if connection.task is not None and not connection.task.done():
                return "connecting", None
        stored = server.get("status")
        if stored in ("error", "auth_required"):
            return stored, server.get("last_error") or None
        return "disconnected", (
            server.get("last_error") or None
        ) if stored == "disconnected" else None

    async def _close(self, connection: Connection) -> None:
        connection.closing.set()
        if connection.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(connection.task), timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                connection.task.cancel()
            except Exception:  # noqa: BLE001 - recorded by the owner task
                pass
        if self.connections.get(connection.key) is connection:
            self.connections.pop(connection.key, None)
        server = store.get_server(*connection.key)
        if server is not None and server.get("status") == "connected":
            store.update_server(*connection.key, status="disconnected")
        connection.log("[mizan] connection closed")

    async def disconnect(self, user_id: str, server_id: str) -> None:
        connection = self.connections.get((user_id, server_id))
        if connection is not None:
            await self._close(connection)

    async def signout(self, user_id: str, server_id: str) -> None:
        """Revoke the tokens where the authorization server allows (RFC 7009) and
        forget them; a pre-registered client's configuration stays."""
        server = store.get_server(user_id, server_id)
        if server is None:
            return
        await self.disconnect(user_id, server_id)
        try:
            oauth = store.secrets_of(server)[2]
            secret = store.oauth_client_secret(server)
        except secrets.SecretsUnreadable:
            oauth, secret = {}, ""
        tokens = oauth.get("tokens") or {}
        endpoint = oauth.get("revocation_endpoint")
        config = server.get("oauth_config") or {}
        client_id = config.get("client_id") or (oauth.get("client_info") or {}).get("client_id")
        secret = secret or (oauth.get("client_info") or {}).get("client_secret") or ""
        if endpoint and tokens and client_id:
            await self._revoke(server, str(endpoint), tokens, str(client_id), str(secret))

        def forget_tokens(state: dict) -> None:
            for name in ("tokens", "expires_at", "obtained_at"):
                state.pop(name, None)

        try:
            store.change_oauth(user_id, server_id, forget_tokens)
        except secrets.SecretsUnreadable:
            store.update_server(user_id, server_id, oauth={})  # unreadable: nothing to keep
        store.update_server(user_id, server_id, status="disconnected", last_error="")
        self._oauth_states.pop((user_id, server_id), None)
        self.log(user_id, server_id, "[mizan] signed out")

    async def _revoke(
        self, server: dict, endpoint: str, tokens: dict, client_id: str, secret: str
    ) -> None:
        import httpx2

        try:
            await net_guard.check_oauth_url(endpoint)
        except net_guard.BlockedDestination:
            return
        async with httpx2.AsyncClient(
            timeout=10,
            transport=net_guard.pinned_transport(),
            follow_redirects=False,
            event_hooks={
                "request": [net_guard.connector_request_hook(server["url"])],
                "response": [],
            },
        ) as client:
            for hint in ("refresh_token", "access_token"):
                token = tokens.get(hint)
                if not token:
                    continue
                data = {"token": token, "token_type_hint": hint, "client_id": client_id}
                if secret:
                    data["client_secret"] = secret
                with contextlib.suppress(Exception):
                    await client.post(endpoint, data=data)

    async def check_health(self) -> None:
        """Ping idle open connections; close those that do not answer."""
        now = time.monotonic()
        for connection in list(self.connections.values()):
            if (
                not connection.alive
                or connection.inflight
                or now - connection.last_used < HEALTH_IDLE_SECONDS
                or now - connection.last_health < HEALTH_IDLE_SECONDS
            ):
                continue
            try:
                await self._ping(connection)
            except Exception as exc:  # noqa: BLE001 - the next call reconnects
                connection.dead = f"no answer to a health check ({_describe(exc)[:120]})"
                connection.log(f"[mizan] health check failed: {_describe(exc)[:200]}")
                await self._close(connection)

    async def reap_idle(self) -> None:
        now = time.monotonic()
        for connection in list(self.connections.values()):
            idle = now - connection.last_used > IDLE_SECONDS and connection.inflight == 0
            if idle or (connection.task is not None and connection.task.done()):
                await self._close(connection)
        for key in [
            k for k, lock in self._locks.items() if k not in self.connections and not lock.locked()
        ]:
            self._locks.pop(key, None)
        self.oauth._expire()
        cutoff = time.time() - 3600
        for key in [k for k, v in self._oauth_states.items() if v.get("at", 0) < cutoff]:
            self._oauth_states.pop(key, None)

    def start(self) -> None:
        async def loop() -> None:
            while True:
                await asyncio.sleep(REAP_INTERVAL_SECONDS)
                try:
                    await self.reap_idle()
                    await self.check_health()
                except Exception:  # noqa: BLE001
                    logger.debug("Connector reaper failed", exc_info=True)

        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(loop(), name="mcp-reaper")

    async def shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
        for connection in list(self.connections.values()):
            await self._close(connection)


def _default_callback() -> str:
    base = os.getenv("MIZAN_PUBLIC_URL", "").rstrip("/")
    return f"{base}/api/connectors/oauth/callback" if base else ""


METADATA_PATH = "/api/connectors/oauth/client-metadata.json"
CALLBACK_PATH = "/api/connectors/oauth/callback"


def _metadata_url(callback: str) -> str | None:
    """MIZAN's client metadata document (CIMD) for this callback: only on https."""
    if not callback.startswith("https://") or not callback.endswith(CALLBACK_PATH):
        return None
    return callback[: -len(CALLBACK_PATH)] + METADATA_PATH


manager = ConnectorManager()
