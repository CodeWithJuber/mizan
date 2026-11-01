"""Server sandbox sessions: lifecycle, sync, commands, dev-server previews, terminal.

Sessions run on the private workspace runner (never on the backend host). The
preview route is public by design: its capability path is the credential, and
every response is served under ``Content-Security-Policy: sandbox`` so the
previewed page always has an opaque origin and cannot read Mizan's storage.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Literal, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.websockets import WebSocketDisconnect

from api.artifacts import require_auth
from api.coding_workspace import require_editor
from security.auth import TokenPayload
from workspace import session_client
from workspace.execution import configuration
from workspace.store import WorkspaceStore

router = APIRouter(prefix="/api/workspaces", tags=["coding workspaces"])
ws_router = APIRouter()

PREVIEW_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"
_PREVIEW_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "content-encoding",
    "content-language",
    "content-disposition",
    "content-range",
    "accept-ranges",
    "cache-control",
    "etag",
    "last-modified",
    "expires",
    "vary",
    "location",
}
_PREVIEW_REQUEST_HEADERS = {
    "accept",
    "accept-language",
    "accept-encoding",
    "content-type",
    "if-none-match",
    "if-modified-since",
    "range",
    "user-agent",
    "cache-control",
    "x-requested-with",
}
MAX_PREVIEW_BODY = 10 * 1024 * 1024


class SessionCommand(BaseModel):
    command: str = Field(min_length=1, max_length=10000)
    language: Literal["python", "javascript", "shell"] = "shell"
    timeout_s: int = Field(default=120, ge=1, le=900)


class ServiceRequest(BaseModel):
    port: int = Field(ge=1024, le=65535)
    command: str = Field(min_length=1, max_length=2000)
    mode: Literal["base", "root"] = "base"


# ── Preview (public capability URLs; registered before /{workspace_id}) ──


@router.api_route(
    "/preview/{cap}/{port}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
async def preview_root(cap: str, port: int) -> RedirectResponse:
    return RedirectResponse(f"{session_client.PREVIEW_ROOT}/{cap}/{port}/", status_code=307)


@router.api_route(
    "/preview/{cap}/{port}/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def preview(cap: str, port: int, path: str, request: Request):
    parsed = session_client.parse_capability(cap)
    if parsed is None or not 1024 <= port <= 65535:
        raise HTTPException(404, "Preview not found")
    key, nonce = parsed
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_PREVIEW_BODY:
            raise HTTPException(413, "Preview request too large")
        body.extend(chunk)
    raw_path = request.scope.get("raw_path") or request.url.path.encode()
    target = raw_path.decode("latin-1")
    if request.url.query:
        target += "?" + request.url.query
    url, token = configuration()
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in _PREVIEW_REQUEST_HEADERS
    }
    headers.update(
        {
            "Authorization": f"Bearer {token}",
            "X-Mizan-Nonce": nonce,
            "X-Mizan-Prefix": f"{session_client.PREVIEW_ROOT}/{cap}/{port}",
            "X-Mizan-Target": target,
        }
    )
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(120, connect=10), trust_env=False, follow_redirects=False
    )
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                f"{url}/sessions/{key}/proxy/{port}/{path}",
                headers=headers,
                content=bytes(body),
            ),
            stream=True,
        )
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(502, "The preview is unavailable") from None
    if upstream.headers.get("x-mizan-runner") == "error" or upstream.status_code == 401:
        detail = "The sandbox session for this preview is not running"
        with contextlib.suppress(ValueError, httpx.HTTPError):
            detail = str(json.loads(await upstream.aread()).get("detail", detail))[:200]
        await upstream.aclose()
        await client.aclose()
        status = upstream.status_code if upstream.status_code in (400, 404, 502, 504) else 502
        raise HTTPException(status, detail)
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in _PREVIEW_RESPONSE_HEADERS
    }
    response_headers.update(
        {
            "Content-Security-Policy": PREVIEW_CSP,
            "Access-Control-Allow-Origin": "*",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex",
        }
    )

    async def close() -> None:
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=response_headers,
        background=BackgroundTask(close),
    )


# ── Session lifecycle and commands ────────────────────────────────────────


@router.get("/{workspace_id}/session")
async def session_status(workspace_id: str, user: TokenPayload = Depends(require_auth)) -> dict:
    return cast(dict, await session_client.status(user.user_id, workspace_id))


@router.post("/{workspace_id}/session")
async def session_start(workspace_id: str, user: TokenPayload = Depends(require_editor)) -> dict:
    return cast(dict, await session_client.start(user.user_id, workspace_id))


@router.delete("/{workspace_id}/session")
async def session_stop(workspace_id: str, user: TokenPayload = Depends(require_editor)) -> dict:
    return cast(dict, await session_client.stop(user.user_id, workspace_id))


@router.post("/{workspace_id}/session/sync")
async def session_sync(workspace_id: str, user: TokenPayload = Depends(require_editor)) -> dict:
    WorkspaceStore(user.user_id).project(workspace_id)
    return cast(dict, await session_client.reconcile(user.user_id, workspace_id))


@router.post("/{workspace_id}/session/exec")
async def session_exec(
    workspace_id: str, body: SessionCommand, user: TokenPayload = Depends(require_editor)
) -> dict:
    WorkspaceStore(user.user_id).project(workspace_id)
    return cast(
        dict,
        await session_client.execute(
            user.user_id, workspace_id, body.command, body.language, body.timeout_s
        ),
    )


@router.post("/{workspace_id}/session/services")
async def service_start(
    workspace_id: str, body: ServiceRequest, user: TokenPayload = Depends(require_editor)
) -> dict:
    WorkspaceStore(user.user_id).project(workspace_id)
    return cast(
        dict,
        await session_client.start_service(
            user.user_id, workspace_id, body.port, body.command, body.mode
        ),
    )


@router.delete("/{workspace_id}/session/services/{port}")
async def service_stop(
    workspace_id: str, port: int, user: TokenPayload = Depends(require_editor)
) -> dict:
    return cast(dict, await session_client.stop_service(user.user_id, workspace_id, port))


@router.get("/{workspace_id}/session/services/{port}/logs")
async def service_logs(
    workspace_id: str, port: int, user: TokenPayload = Depends(require_auth)
) -> dict:
    return cast(dict, await session_client.service_logs(user.user_id, workspace_id, port))


# ── Terminal (under /ws/ so the proxy upgrades the connection) ────────────


TERMINAL_PROTOCOL = "mizan.terminal"


def _subprotocol_token(websocket: WebSocket) -> str:
    """Browsers send the token as a ``bearer.<jwt>`` subprotocol, keeping it out of URLs and logs."""
    offered = websocket.headers.get("sec-websocket-protocol", "").split(",")
    return next((item.strip()[7:] for item in offered if item.strip().startswith("bearer.")), "")


@ws_router.websocket("/ws/workspaces/{workspace_id}/terminal")
async def terminal(websocket: WebSocket, workspace_id: str):
    """Relay an interactive shell in the session; bytes both ways, resize as JSON text."""
    try:
        token = _subprotocol_token(websocket)
        if not token:
            raise HTTPException(401, "Authentication required")
        user = await require_auth(authorization=f"Bearer {token}", x_api_key=None)
        if not user.has_min_role("user"):
            raise HTTPException(403, "Terminal requires the user role")
        WorkspaceStore(user.user_id).project(workspace_id)
        if not await session_client.running(user.user_id, workspace_id):
            raise HTTPException(409, "Start the sandbox session first")
    except HTTPException as exc:
        await websocket.close(code=4400 + min(exc.status_code - 400, 99), reason=str(exc.detail))
        return
    import websockets

    key = session_client.session_key(user.user_id, workspace_id)
    cols = websocket.query_params.get("cols", "100")
    rows = websocket.query_params.get("rows", "30")
    await websocket.accept(subprotocol=TERMINAL_PROTOCOL)
    try:
        async with websockets.connect(
            session_client.runner_ws_url(f"/sessions/{key}/terminal?cols={cols}&rows={rows}"),
            additional_headers=session_client.runner_headers(),
            max_size=1024 * 1024,
            open_timeout=15,
        ) as runner:

            async def downstream() -> None:
                async for message in runner:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            relay = asyncio.create_task(downstream())
            try:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message.get("bytes") is not None:
                        await runner.send(message["bytes"][:65536])
                    elif message.get("text") is not None:
                        text = message["text"][:65536]
                        with contextlib.suppress(ValueError, TypeError):
                            control = json.loads(text)
                            if isinstance(control, dict) and control.get("type") in {
                                "resize",
                                "input",
                            }:
                                await runner.send(text)
                    if relay.done():
                        break
            finally:
                relay.cancel()
    except (WebSocketDisconnect, OSError, websockets.WebSocketException):
        pass
    finally:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
