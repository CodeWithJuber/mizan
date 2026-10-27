"""MCP transport for stdio servers that run inside a sandbox session.

Users without host access still get local (stdio) MCP servers: the command runs
in their own hardened session container on the private runner, and the runner
relays its stdin/stdout over a WebSocket, one JSON-RPC message per text frame.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
from mcp.client._transport import TransportStreams
from mcp.shared.message import SessionMessage
from mcp.types import jsonrpc_message_adapter

from workspace import session_client

logger = logging.getLogger("mizan.connectors.runner")


async def ensure_session(user_id: str, server_id: str) -> str:
    key = str(session_client.session_key(user_id, server_id, kind="mcp"))
    await session_client.call(
        "PUT",
        f"/sessions/{key}",
        {"nonce": secrets.token_hex(16), "kind": "mcp", "preview_prefix": ""},
        timeout=90,
    )
    return key


@asynccontextmanager
async def runner_stdio_client(
    user_id: str, server_id: str, argv: list[str], env: dict[str, str]
) -> AsyncGenerator[TransportStreams, None]:
    import websockets

    key = await ensure_session(user_id, server_id)
    read_writer, read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    write_stream, write_reader = anyio.create_memory_object_stream[SessionMessage](0)
    async with websockets.connect(
        session_client.runner_ws_url(f"/sessions/{key}/stdio"),
        additional_headers=session_client.runner_headers(),
        max_size=8 * 1024 * 1024,
        open_timeout=20,
    ) as socket:
        await socket.send(json.dumps({"argv": argv, "env": env}, separators=(",", ":")))

        async def reader() -> None:
            try:
                async with read_writer:
                    async for frame in socket:
                        text = frame.decode() if isinstance(frame, bytes) else frame
                        try:
                            message = jsonrpc_message_adapter.validate_json(text, by_name=False)
                        except ValueError as exc:
                            await read_writer.send(exc)
                            continue
                        await read_writer.send(SessionMessage(message))
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                pass
            except websockets.WebSocketException:
                logger.info("sandboxed MCP server closed")

        async def writer() -> None:
            try:
                async with write_reader:
                    async for item in write_reader:
                        await socket.send(
                            item.message.model_dump_json(by_alias=True, exclude_unset=True)
                        )
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                pass
            except websockets.WebSocketException:
                await read_writer.aclose()

        async with anyio.create_task_group() as group:
            group.start_soon(reader)
            group.start_soon(writer)
            try:
                yield read_stream, write_stream
            finally:
                group.cancel_scope.cancel()
                for stream in (read_stream, write_stream, read_writer, write_reader):
                    await stream.aclose()
