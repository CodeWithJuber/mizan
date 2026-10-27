"""Live MCP connections with the official SDK (``mcp`` 2.x).

One owner task per (user, server) enters and leaves ``mcp.Client`` (the
SDK's anyio scopes must open and close in the same task); callers use the
open session concurrently. Idle connections close after 10 minutes and
reconnect on the next call.

OAuth uses the SDK's ``OAuthClientProvider``. From the Connectors page the
owner task waits for the browser to return to ``/api/connectors/oauth/callback``;
during a chat a connector that needs authorization fails fast instead.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from connectors import naming, net_guard, store

logger = logging.getLogger("mizan.connectors")

IDLE_SECONDS = 600
CALL_TIMEOUT_SECONDS = 120
OAUTH_WAIT_SECONDS = 600
MAX_TOOLS_PER_SERVER = 300
MAX_CONNECTIONS_PER_USER = 10
MAX_RESULT_CHARS = 20_000


class ConnectorError(RuntimeError):
    pass


class AuthorizationRequired(ConnectorError):
    def __init__(self, url: str = ""):
        super().__init__("This connector needs authorization; connect it from the Connectors page")
        self.url = url


def host_stdio_allowed(is_admin: bool) -> bool:
    """Who may launch a stdio server as a process on the backend host.

    ``admin`` (default): administrators only. ``all``: every user (the
    operator accepts that users can run commands on the host). ``off``.
    """
    policy = os.getenv("MIZAN_MCP_HOST_STDIO", "admin").strip().lower()
    return policy == "all" or (policy == "admin" and is_admin)


@dataclass
class _PendingAuth:
    user_id: str
    server_id: str
    future: asyncio.Future
    created: float = field(default_factory=time.time)


class OAuthBroker:
    """Single-use OAuth ``state`` → waiting connection (10-minute lifetime)."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingAuth] = {}

    def open(self, state: str, user_id: str, server_id: str) -> asyncio.Future:
        self._expire()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[state] = _PendingAuth(user_id, server_id, future)
        return future

    def complete(self, state: str, code: str, iss: str | None = None) -> bool:
        from mcp.shared.auth import AuthorizationCodeResult

        pending = self._pending.pop(state, None)
        if pending is None or pending.future.done():
            return False
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
        for state in [s for s, p in self._pending.items() if p.created < cutoff]:
            pending = self._pending.pop(state)
            if not pending.future.done():
                pending.future.cancel()


class EncryptedTokenStorage:
    """SDK TokenStorage backed by the sealed ``oauth`` field of a connector."""

    def __init__(self, user_id: str, server_id: str):
        self.user_id, self.server_id = user_id, server_id

    def _oauth(self) -> dict:
        server = store.get_server(self.user_id, self.server_id) or {}
        oauth: dict = store.secrets_of(server)[2]
        return oauth

    def _update(self, key: str, value: dict) -> None:
        oauth = self._oauth()
        oauth[key] = value
        store.update_server(self.user_id, self.server_id, oauth=oauth)

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        data = self._oauth().get("tokens")
        return OAuthToken.model_validate(data) if data else None

    async def set_tokens(self, tokens) -> None:
        self._update("tokens", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        data = self._oauth().get("client_info")
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def set_client_info(self, client_info) -> None:
        self._update("client_info", client_info.model_dump(mode="json", exclude_none=True))


def map_result(result: Any) -> dict:
    """CallToolResult → receipt; ``is_error`` becomes an error the agent can see."""
    texts, notes = [], []
    for block in getattr(result, "content", None) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            texts.append(str(getattr(block, "text", "")))
        elif kind == "image":
            notes.append(f"[image: {getattr(block, 'mime_type', 'image')}]")
        elif kind in {"resource", "resource_link"}:
            resource = getattr(block, "resource", block)
            uri = getattr(resource, "uri", "")
            text = getattr(resource, "text", None)
            texts.append(str(text) if text else f"[resource: {uri}]")
        else:
            notes.append(f"[{kind or 'content'}]")
    text = "\n".join(texts + notes)
    receipt: dict[str, Any] = {"content": text[:MAX_RESULT_CHARS]}
    if len(text) > MAX_RESULT_CHARS:
        receipt["truncated"] = True
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        receipt["structured"] = structured
    if getattr(result, "is_error", False):
        return {"error": text[:2000] or "The MCP tool reported an error", **receipt}
    return receipt


def fingerprint(description: str, schema: dict) -> str:
    """What a tool told the model about itself; a change after approval is held."""
    payload = json.dumps([description or "", schema], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def tool_snapshot(server: dict, tools: list[Any]) -> list[dict]:
    """The server's tools as the model will see them, with Amanah's checks.

    A tool is pinned to the description and schema the user first accepted. A
    later change (a "rug pull") or a description that instructs the AI (tool
    poisoning) holds the tool back from the model until the user trusts it.
    """
    from tadbir import amanah

    pins = server.get("pins") or {}
    snapshot, used = [], set()
    for tool in tools[:MAX_TOOLS_PER_SERVER]:
        exposed = naming.tool_name(server["slug"], tool.name)
        if exposed in used:
            continue
        used.add(exposed)
        annotations = getattr(tool, "annotations", None)
        schema = naming.input_schema(getattr(tool, "input_schema", None))
        stamp = fingerprint(tool.description or "", schema)
        entry = {
            "name": tool.name,
            "exposed": exposed,
            "description": naming.description(server["name"], tool.description),
            "input_schema": schema,
            "read_only": bool(getattr(annotations, "read_only_hint", False)),
            "destructive": bool(getattr(annotations, "destructive_hint", False)),
            "fingerprint": stamp,
        }
        findings = amanah.scan(
            f"{tool.description or ''}\n{json.dumps(schema, ensure_ascii=False)}", exposed
        )
        if tool.name in pins and pins[tool.name] != stamp:
            entry["held"] = "changed"
        elif tool.name not in pins and findings:
            entry["held"] = "flagged"
        if findings:
            entry["amanah"] = [finding["excerpt"] for finding in findings[:3]]
        snapshot.append(entry)
    return snapshot


def pins_after(server: dict, snapshot: list[dict]) -> dict:
    """First-seen tools that passed the checks are pinned; held ones keep the old pin."""
    pins = dict(server.get("pins") or {})
    for tool in snapshot:
        if not tool.get("held") and tool["name"] not in pins:
            pins[tool["name"]] = tool["fingerprint"]
    return pins


def trust_tool(user_id: str, server_id: str, name: str) -> dict | None:
    """The user accepts a held tool as it is now."""
    server = store.get_server(user_id, server_id)
    if server is None:
        return None
    tools = [dict(tool) for tool in server.get("tools") or []]
    found = False
    for tool in tools:
        if tool.get("name") == name and tool.get("fingerprint"):
            tool.pop("held", None)
            found = True
            pins = {**(server.get("pins") or {}), name: tool["fingerprint"]}
    if not found:
        return None
    return store.update_server(user_id, server_id, tools=tools, pins=pins)


class Connection:
    def __init__(self, manager: ConnectorManager, user_id: str, server: dict, interactive: bool):
        self.manager, self.user_id, self.server = manager, user_id, server
        self.interactive = interactive
        self.client: Any = None
        self.ready = asyncio.Event()
        self.auth_url: str = ""
        self.auth_event = asyncio.Event()
        self.closing = asyncio.Event()
        self.error: BaseException | None = None
        self.inflight = 0
        self.last_used = time.monotonic()
        self.task: asyncio.Task | None = None

    @property
    def alive(self) -> bool:
        return self.client is not None and not self.closing.is_set()

    def start(self) -> None:
        self.task = asyncio.create_task(self._owner(), name=f"mcp:{self.server['slug']}")

    async def _owner(self) -> None:
        try:
            client = await self.manager.build_client(self)
            async with client:
                self.client = client
                tools = await list_all_tools(client)
                snapshot = tool_snapshot(self.server, tools)
                store.update_server(
                    self.user_id,
                    self.server["id"],
                    tools=snapshot,
                    pins=pins_after(self.server, snapshot),
                    status="connected",
                    last_error="",
                )
                self.server = store.get_server(self.user_id, self.server["id"]) or self.server
                self.ready.set()
                await self.closing.wait()
        except BaseException as exc:  # noqa: BLE001 - recorded for the caller
            self.error = exc
            if isinstance(exc, AuthorizationRequired) or _has(exc, AuthorizationRequired):
                status = "auth_required"
            else:
                status = "error"
            if not isinstance(exc, asyncio.CancelledError):
                store.update_server(
                    self.user_id,
                    self.server["id"],
                    status=status,
                    last_error=_describe(exc)[:300],
                )
        finally:
            self.client = None
            self.ready.set()
            self.auth_event.set()

    async def redirect(self, url: str) -> None:
        if not self.interactive:
            raise AuthorizationRequired(url)
        state = parse_qs(urlsplit(url).query).get("state", [""])[0]
        if not state:
            raise ConnectorError("The authorization server returned no state")
        self.manager.oauth.open(state, self.user_id, self.server["id"])
        self.auth_url = url
        self._state = state
        self.auth_event.set()

    async def callback(self):
        pending = self.manager.oauth._pending.get(getattr(self, "_state", ""))
        if pending is None:
            raise ConnectorError("Authorization expired; connect again")
        return await asyncio.wait_for(pending.future, timeout=OAUTH_WAIT_SECONDS)


def _has(exc: BaseException, kind: type) -> bool:
    if isinstance(exc, kind):
        return True
    return any(_has(inner, kind) for inner in getattr(exc, "exceptions", ()) or ())


def _describe(exc: BaseException) -> str:
    inner = getattr(exc, "exceptions", None)
    if inner:
        return _describe(inner[0])
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def list_all_tools(client: Any) -> list[Any]:
    tools: list[Any] = []
    cursor = None
    for _ in range(20):
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = getattr(page, "next_cursor", None)
        if not cursor or len(tools) >= MAX_TOOLS_PER_SERVER:
            break
    return tools


class ConnectorManager:
    def __init__(self) -> None:
        self.connections: dict[tuple[str, str], Connection] = {}
        self.oauth = OAuthBroker()
        # Tests (and the sandbox runner later) may supply their own client.
        self.client_factory: Callable[[Connection], Any] | None = None
        self._reaper: asyncio.Task | None = None
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def build_client(self, connection: Connection) -> Any:
        if self.client_factory is not None:
            return self.client_factory(connection)
        from mcp import Client, Implementation

        server = connection.server
        headers, env, _oauth = store.secrets_of(server)
        info = Implementation(name="mizan", version="3")
        if server["transport"] == "http":
            return Client(
                await self._http_transport(connection, headers),
                read_timeout_seconds=CALL_TIMEOUT_SECONDS,
                client_info=info,
            )
        if server["transport"] == "stdio":
            if server.get("runtime") != "host":
                from workspace import session_client

                if not session_client.available():
                    raise ConnectorError(
                        "Local MCP servers for this account run in the sandbox runner, which "
                        "is not enabled on this server; ask the administrator, or use a "
                        "remote URL"
                    )
                from .runner_transport import runner_stdio_client

                return Client(
                    runner_stdio_client(
                        connection.user_id,
                        server["id"],
                        [server["command"], *list(server.get("args") or [])],
                        env,
                    ),
                    read_timeout_seconds=CALL_TIMEOUT_SECONDS,
                    client_info=info,
                )
            from mcp import StdioServerParameters

            safe_env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
            parameters = StdioServerParameters(
                command=server["command"],
                args=list(server.get("args") or []),
                env={**safe_env, **env},
            )
            return Client(parameters, read_timeout_seconds=CALL_TIMEOUT_SECONDS, client_info=info)
        raise ConnectorError("Unknown connector transport")

    async def _http_transport(self, connection: Connection, headers: dict) -> Any:
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        url = connection.server["url"]
        await net_guard.check_url(url, require_https=True)
        auth = None
        if not any(name.lower() == "authorization" for name in headers):
            from mcp.client.auth import OAuthClientProvider
            from mcp.shared.auth import OAuthClientMetadata
            from pydantic import AnyUrl

            callback = connection.server.get("callback_url") or _default_callback()
            if callback:
                auth = OAuthClientProvider(
                    server_url=url,
                    client_metadata=OAuthClientMetadata(
                        client_name="MIZAN",
                        redirect_uris=[AnyUrl(str(callback))],
                        grant_types=["authorization_code", "refresh_token"],
                        response_types=["code"],
                        token_endpoint_auth_method="none",  # noqa: S106 - public PKCE client
                    ),
                    storage=EncryptedTokenStorage(connection.user_id, connection.server["id"]),
                    redirect_handler=connection.redirect,
                    callback_handler=connection.callback,
                )
        http = create_mcp_http_client(headers=headers or None, auth=auth)
        http.event_hooks = {"request": [net_guard.request_hook], "response": []}
        return streamable_http_client(url, http_client=http)

    def _lock(self, key: tuple[str, str]) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def connect(
        self, user_id: str, server_id: str, *, interactive: bool = False, wait: float = 20.0
    ) -> Connection:
        key = (user_id, server_id)
        async with self._lock(key):
            current = self.connections.get(key)
            if current is not None and current.alive:
                return current
            if current is not None and current.task is not None and not current.task.done():
                # Still starting, or waiting for the user's browser authorization.
                if current.auth_url and not interactive:
                    raise AuthorizationRequired(current.auth_url)
                if not current.auth_url:
                    await asyncio.wait_for(asyncio.shield(current.ready.wait()), timeout=wait)
                    if current.alive:
                        return current
                elif interactive:
                    return current
            server = store.get_server(user_id, server_id)
            if server is None:
                raise ConnectorError("Connector not found")
            if not server.get("enabled", True):
                raise ConnectorError("Connector is disabled")
            open_for_user = [
                c for (u, _), c in self.connections.items() if u == user_id and c.alive
            ]
            if len(open_for_user) >= MAX_CONNECTIONS_PER_USER:
                await self._close(min(open_for_user, key=lambda c: c.last_used))
            connection = Connection(self, user_id, server, interactive)
            self.connections[key] = connection
            connection.start()
        ready = asyncio.create_task(connection.ready.wait())
        auth = asyncio.create_task(connection.auth_event.wait())
        try:
            await asyncio.wait({ready, auth}, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
        finally:
            ready.cancel()
            auth.cancel()
        if connection.error is not None and not connection.alive:
            if _has(connection.error, AuthorizationRequired):
                raise AuthorizationRequired()
            raise ConnectorError(_describe(connection.error))
        return connection

    async def call(self, user_id: str, exposed: str, arguments: dict) -> dict:
        resolved = resolve_tool(user_id, exposed)
        if resolved is None:
            return {"error": f"Unknown connector tool {exposed}"}
        server, tool = resolved
        try:
            connection = await self.connect(user_id, server["id"])
        except AuthorizationRequired:
            return {
                "error": "This connector needs authorization: open Connectors and press Connect",
                "connector": server["name"],
                "auth_required": True,
            }
        except ConnectorError as exc:
            return {"error": str(exc)[:300], "connector": server["name"]}
        if not connection.alive:
            return {"error": "Connector is not connected", "connector": server["name"]}
        connection.inflight += 1
        connection.last_used = time.monotonic()
        try:
            result = await asyncio.wait_for(
                connection.client.call_tool(tool["name"], arguments or {}),
                timeout=CALL_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return {"error": "The connector did not answer in time", "connector": server["name"]}
        except Exception as exc:  # noqa: BLE001 - a receipt, not a crash
            return {"error": _describe(exc)[:300], "connector": server["name"]}
        finally:
            connection.inflight -= 1
            connection.last_used = time.monotonic()
        return {**map_result(result), "connector": server["name"]}

    async def _close(self, connection: Connection) -> None:
        connection.closing.set()
        if connection.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(connection.task), timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                connection.task.cancel()
        self.connections.pop((connection.user_id, connection.server["id"]), None)

    async def disconnect(self, user_id: str, server_id: str) -> None:
        connection = self.connections.get((user_id, server_id))
        if connection is not None:
            await self._close(connection)

    async def reap_idle(self) -> None:
        now = time.monotonic()
        for connection in list(self.connections.values()):
            idle = now - connection.last_used > IDLE_SECONDS and connection.inflight == 0
            if idle or (connection.task is not None and connection.task.done()):
                await self._close(connection)

    def start(self) -> None:
        async def loop() -> None:
            while True:
                await asyncio.sleep(60)
                try:
                    await self.reap_idle()
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
                and tool.get("name") not in (server.get("disabled_tools") or [])
            ):
                return server, tool
    return None


manager = ConnectorManager()
