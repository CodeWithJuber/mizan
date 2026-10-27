"""Keep remote MCP traffic (including OAuth discovery) on public addresses.

Every request a connector client makes is checked: the host must resolve to
global addresses only, so a server URL or an OAuth metadata document cannot
point MIZAN at its own network (other containers, metadata services). An
administrator may allow private hosts with MIZAN_MCP_ALLOW_PRIVATE_HOSTS.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    import httpx


class BlockedDestination(ValueError):
    pass


def private_hosts_allowed() -> set[str]:
    raw = os.getenv("MIZAN_MCP_ALLOW_PRIVATE_HOSTS", "")
    return {host.strip().lower() for host in raw.split(",") if host.strip()}


async def check_url(url: str, *, require_https: bool = False) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise BlockedDestination("Only http(s) URLs are allowed")
    if parts.username or parts.password:
        raise BlockedDestination("Credentials in URLs are not allowed; use headers")
    host = parts.hostname.lower()
    if host in private_hosts_allowed():
        return
    if require_https and parts.scheme != "https":
        raise BlockedDestination("Remote MCP servers must use https")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise BlockedDestination(f"Cannot resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        mapped = getattr(address, "ipv4_mapped", None)
        if not address.is_global or address.is_multicast or (mapped and not mapped.is_global):
            raise BlockedDestination(f"{host} resolves to a non-public address")


async def request_hook(request) -> None:
    """httpx2 request hook: re-check every request, redirects and OAuth calls included."""
    await check_url(str(request.url))


async def pinned_destination(url: str) -> tuple[httpx.URL, str, str]:
    """A public HTTP(S) URL resolved once and pinned to that address (no DNS
    rebinding between the check and the request), with the Host header and
    TLS server name kept."""
    import httpx

    parsed = httpx.URL(url)
    if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.userinfo:
        raise ValueError("Only public HTTP(S) URLs without credentials are allowed")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parsed.host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
    )
    ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
    if not ips or any(
        not ip.is_global
        or ip.is_multicast
        or (
            isinstance(ip, ipaddress.IPv6Address)
            and ip.ipv4_mapped is not None
            and not ip.ipv4_mapped.is_global
        )
        for ip in ips
    ):
        raise ValueError("URL resolves to a non-public address")
    host_header = parsed.netloc.decode("ascii")
    # Connect to the validated literal, eliminating the second DNS lookup/rebinding gap.
    return parsed.copy_with(host=str(ips[0])), host_header, parsed.host
