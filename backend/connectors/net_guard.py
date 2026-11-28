"""Keep remote MCP traffic (including OAuth discovery) on public addresses.

Every request a connector client makes is checked: the host must resolve to
global addresses only, so a server URL or an OAuth metadata document cannot
point MIZAN at its own network (other containers, metadata services). An
administrator may allow private hosts with MIZAN_MCP_ALLOW_PRIVATE_HOSTS.

The check and the connection use the same lookup: :func:`pinned_transport`
gives connector HTTP clients a transport whose connections go only to an
address that was just checked, so a host cannot answer the check with a public
address and the connection with a private one (DNS rebinding). The TLS server
name and the Host header stay the host's own.

OAuth endpoints (metadata, registration, token, revocation) must be https:
only the MCP endpoint itself may be plain http, and only on a host the
administrator allowed. With ``MIZAN_DEV`` set (development and tests), http on
the loopback address is accepted for OAuth too.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    import httpx


class BlockedDestination(ValueError):
    pass


def private_hosts_allowed() -> set[str]:
    raw = os.getenv("MIZAN_MCP_ALLOW_PRIVATE_HOSTS", "")
    return {host.strip().lower() for host in raw.split(",") if host.strip()}


def dev_mode() -> bool:
    return os.getenv("MIZAN_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(ip.is_global and not ip.is_multicast and not (mapped and not mapped.is_global))


async def resolve_public(host: str, port: int) -> list[str]:
    """The host's addresses, all of them public (or the host is allowed)."""
    host = host.lower().strip("[]")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise BlockedDestination(f"Cannot resolve {host}") from exc
        addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise BlockedDestination(f"Cannot resolve {host}")
    if host in private_hosts_allowed():
        return addresses
    for address in addresses:
        if not _public(address):
            raise BlockedDestination(f"{host} resolves to a non-public address")
    return addresses


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
    await resolve_public(host, port)


async def request_hook(request) -> None:
    """httpx request hook: re-check every request, redirects and OAuth calls included."""
    await check_url(str(request.url))


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, (parts.hostname or "").lower(), parts.port or (443 if scheme == "https" else 80)


def connector_request_hook(endpoint: str):
    """A request hook for one connector: the MCP endpoint's origin keeps the rules it
    was added under; every other request (OAuth metadata, registration, token,
    revocation on another host) must be https (http loopback only with MIZAN_DEV)."""
    endpoint_origin = _origin(endpoint)

    async def hook(request) -> None:
        url = str(request.url)
        if _origin(url) == endpoint_origin:
            await check_url(url)
            return
        await check_oauth_url(url)

    return hook


async def check_oauth_url(url: str) -> None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" and not (dev_mode() and host in _LOOPBACK):
        raise BlockedDestination("OAuth endpoints must use https")
    if parts.username or parts.password:
        raise BlockedDestination("Credentials in URLs are not allowed")
    if host in private_hosts_allowed() or (dev_mode() and host in _LOOPBACK):
        return
    await resolve_public(host, parts.port or 443)


def pinned_transport(**kwargs: Any):
    """An ``httpx2`` transport that connects only to an address it checked a moment
    before (no DNS rebinding between the check and the connection)."""
    import httpcore2
    import httpx2

    class _CheckedBackend(httpcore2.AsyncNetworkBackend):
        def __init__(self) -> None:
            self._inner = httpcore2.AnyIOBackend()

        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> Any:
            addresses = await resolve_public(host, port)
            last: Exception | None = None
            for address in addresses[:4]:
                try:
                    return await self._inner.connect_tcp(
                        address,
                        port,
                        timeout=timeout,
                        local_address=local_address,
                        socket_options=socket_options,
                    )
                except Exception as exc:  # noqa: BLE001 - try the host's next address
                    last = exc
            raise last or OSError(f"Cannot connect to {host}")

        async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> Any:
            raise BlockedDestination("Unix sockets are not allowed for connectors")

        async def sleep(self, seconds: float) -> None:
            await self._inner.sleep(seconds)

    class _PinnedTransport(httpx2.AsyncHTTPTransport):
        def __init__(self) -> None:
            # An explicit transport means no proxy from the environment, so the
            # connection really goes to the checked address; CA bundles still apply.
            super().__init__(**kwargs)
            self._pool = httpcore2.AsyncConnectionPool(
                ssl_context=httpx2.create_ssl_context(),
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
                network_backend=_CheckedBackend(),
            )

    return _PinnedTransport()


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
