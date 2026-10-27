"""Allowlisting HTTPS egress proxy for workspace sessions (stdlib only).

Sessions sit on an internal Docker network whose only way out is this proxy.
It accepts ``CONNECT host:443`` for allowlisted package/code hosts, resolves the
name itself and refuses any address that is not globally routable, so a
session cannot reach the host, other containers or metadata services.

With ``MIZAN_EGRESS_MODE=public`` (the browser sandbox, Shahid) any host is
accepted, still only on port 443 and only when every address it resolves to is
globally routable; which pages the browser may visit is decided inside it.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import os
import socket
import sys

DEFAULT_ALLOW = (
    "registry.npmjs.org,registry.yarnpkg.com,pypi.org,files.pythonhosted.org,"
    "github.com,codeload.github.com,objects.githubusercontent.com,"
    "raw.githubusercontent.com,release-assets.githubusercontent.com,nodejs.org,"
    "esm.sh,cdn.jsdelivr.net,unpkg.com"
)
MAX_CONNECTIONS = 256
IDLE_SECONDS = 300


def allowlist(raw: str | None = None) -> tuple[set[str], tuple[str, ...]]:
    """Exact hosts, and suffixes for entries written as ``.example.com``."""
    entries = [
        item.strip().lower()
        for item in (raw if raw is not None else os.getenv("MIZAN_SANDBOX_EGRESS_ALLOW", ""))
        .replace(" ", ",")
        .split(",")
        if item.strip()
    ] or DEFAULT_ALLOW.split(",")
    exact = {item for item in entries if not item.startswith(".")}
    suffixes = tuple(item for item in entries if item.startswith("."))
    return exact, suffixes


def public_mode() -> bool:
    return os.getenv("MIZAN_EGRESS_MODE", "").strip().lower() == "public"


def host_allowed(host: str, rules: tuple[set[str], tuple[str, ...]]) -> bool:
    if public_mode():
        return True
    host = host.lower().rstrip(".")
    exact, suffixes = rules
    return host in exact or any(host.endswith(suffix) for suffix in suffixes)


def parse_connect(line: str) -> tuple[str, int] | None:
    parts = line.split()
    if len(parts) != 3 or parts[0].upper() != "CONNECT" or not parts[2].startswith("HTTP/1."):
        return None
    host, _, port = parts[1].rpartition(":")
    host = host.strip("[]")
    if not host or not port.isdigit():
        return None
    return host, int(port)


async def public_address(host: str, port: int) -> str | None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return None
    addresses = [str(info[4][0]) for info in infos]
    if not addresses or not all(ipaddress.ip_address(item).is_global for item in addresses):
        return None
    return addresses[0]


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await asyncio.wait_for(reader.read(65536), IDLE_SECONDS):
            writer.write(chunk)
            await writer.drain()
    except (OSError, TimeoutError):
        pass
    finally:
        with contextlib.suppress(OSError):
            writer.close()


class Proxy:
    def __init__(self, rules: tuple[set[str], tuple[str, ...]]):
        self.rules = rules
        self.slots = asyncio.Semaphore(MAX_CONNECTIONS)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.slots.locked():
            writer.close()
            return
        async with self.slots:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 15)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, OSError):
                writer.close()
                return
            target = parse_connect(head.split(b"\r\n", 1)[0].decode("latin-1"))
            address = None
            if target and target[1] == 443 and host_allowed(target[0], self.rules):
                address = await public_address(*target)
            if target is None or address is None:
                print(f"egress denied {target[0] if target else '-'}", flush=True)
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                with contextlib.suppress(OSError):
                    await writer.drain()
                writer.close()
                return
            try:
                upstream_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(address, target[1]), 15
                )
            except (OSError, TimeoutError):
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                writer.close()
                return
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer))


async def main(port: int = 3128) -> None:
    proxy = Proxy(allowlist())
    server = await asyncio.start_server(proxy.handle, "0.0.0.0", port, limit=16384)  # noqa: S104
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3128))
