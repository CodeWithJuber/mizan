"""Browse the official MCP Registry (registry.modelcontextprotocol.io), cached.

The registry's current API is ``/v0.1/servers``; ``/v0/servers`` answers the same
shape and is the fallback. Only entries the registry lists as ``active`` are
shown (``_meta["io.modelcontextprotocol.registry/official"].status``: deprecated
and deleted versions are left out). Each package carries a ready ``install``:
the command, arguments and environment variables to add it as a local server.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

import httpx

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
FALLBACK_URL = "https://registry.modelcontextprotocol.io/v0/servers"
OFFICIAL_META = "io.modelcontextprotocol.registry/official"
CACHE_SECONDS = 3600
_cache: dict[tuple[str, int, str], tuple[float, dict]] = {}


def _field(item: dict) -> dict:
    return {
        "name": str(item.get("name") or ""),
        "description": str(item.get("description") or ""),
        "required": bool(item.get("isRequired")),
        "secret": bool(item.get("isSecret")),
        **({"default": str(item["default"])} if item.get("default") not in (None, "") else {}),
        **({"value": str(item["value"])} if item.get("value") not in (None, "") else {}),
        **({"choices": [str(c) for c in item["choices"]]} if item.get("choices") else {}),
        **({"format": str(item["format"])} if item.get("format") else {}),
    }


def _argument_values(arguments: list[dict] | None) -> list[str]:
    """Registry arguments as argv words: named ``--flag value``, positional ``value``.

    A value the registry gives (or its default) is used; a required one without a
    value is shown as ``<name>`` for the person to fill in; an optional one without
    a value is left out."""
    words: list[str] = []
    for argument in arguments or []:
        if not isinstance(argument, dict):
            continue
        value = argument.get("value")
        if value in (None, ""):
            value = argument.get("default")
        if value in (None, "") and not argument.get("isRequired"):
            continue
        name = str(argument.get("name") or argument.get("valueHint") or "value")
        hint = str(argument.get("valueHint") or name).lstrip("-") or "value"
        text = str(value) if value not in (None, "") else f"<{hint}>"
        if argument.get("type") == "named":
            flag = name if name.startswith("-") else f"--{name}"
            words.append(flag)
            if value is not True:
                words.append(text)
        else:
            words.append(text)
    return words


def install_for(package: dict) -> dict:
    """How to run a registry package as a local (stdio) server.

    npm → ``npx -y name@version …``, pypi → ``uvx name==version …``, oci →
    ``docker run -i --rm image:tag …``; other registries (or a package that only
    speaks HTTP) are ``supported: false``."""
    registry = str(package.get("registryType") or package.get("registry_type") or "").lower()
    identifier = str(package.get("identifier") or package.get("name") or "")
    version = str(package.get("version") or "")
    transport = package.get("transport") or {}
    transport_type = (
        str(transport.get("type") or "stdio") if isinstance(transport, dict) else "stdio"
    )
    env_vars = [
        _field(env) for env in package.get("environmentVariables") or [] if isinstance(env, dict)
    ]
    runtime_args = _argument_values(package.get("runtimeArguments"))
    package_args = _argument_values(package.get("packageArguments"))
    base = {"runtime": "", "command": "", "args": [], "env_vars": env_vars}
    if not identifier:
        return base | {"supported": False, "reason": "The registry entry names no package"}
    if transport_type != "stdio":
        return base | {
            "supported": False,
            "reason": f"This package runs its own {transport_type} server; add its URL instead",
        }
    if registry == "npm":
        spec = f"{identifier}@{version}" if version and version != "latest" else identifier
        yes = [] if {"-y", "--yes"} & set(runtime_args) else ["-y"]
        return base | {
            "runtime": "npx",
            "command": "npx",
            "args": [*yes, *runtime_args, spec, *package_args],
            "supported": True,
        }
    if registry == "pypi":
        spec = f"{identifier}=={version}" if version and version != "latest" else identifier
        return base | {
            "runtime": "uvx",
            "command": "uvx",
            "args": [*runtime_args, spec, *package_args],
            "supported": True,
        }
    if registry == "oci":
        image = identifier
        tail = image.rsplit("/", 1)[-1]
        if version and ":" not in tail and "@" not in image:
            image = f"{image}:{version}"
        env_flags = [word for env in env_vars for word in ("-e", env["name"]) if env["name"]]
        return base | {
            "runtime": "docker",
            "command": "docker",
            "args": ["run", "-i", "--rm", *env_flags, *runtime_args, image, *package_args],
            "supported": True,
        }
    return base | {
        "runtime": registry,
        "supported": False,
        "reason": f"Packages from {registry or 'this registry'} cannot be started here",
    }


def _status(entry: dict) -> str:
    meta = entry.get("_meta") or {}
    official = meta.get(OFFICIAL_META) if isinstance(meta, dict) else None
    if not isinstance(official, dict):
        return "active"  # an older response without registry metadata
    return str(official.get("status") or "active").lower()


def _official(entry: dict, server: dict, remotes: list[dict]) -> bool:
    """The entry is published by the organisation whose service it reaches.

    Registry names are verified namespaces: a reverse-DNS name (``com.notion/…``)
    is proven by DNS or HTTP. An entry counts as official when that domain owns a
    remote URL's host or the entry's website (``com.notion/mcp`` →
    ``mcp.notion.com``). A GitHub namespace (``io.github.<owner>/…``) proves only
    who published it, not whose service it is, so it is never marked."""
    meta = entry.get("_meta") or {}
    if not isinstance(meta, dict) or not isinstance(meta.get(OFFICIAL_META), dict):
        return False
    name = str(server.get("name") or "")
    namespace = name.split("/", 1)[0].lower()
    parts = namespace.split(".")
    if len(parts) < 2 or parts[:2] == ["io", "github"]:
        return False
    domain = ".".join(reversed(parts))
    hosts = [(urlsplit(remote.get("url", "")).hostname or "").lower() for remote in remotes]
    hosts.append((urlsplit(str(server.get("websiteUrl") or "")).hostname or "").lower())
    return any(host == domain or host.endswith("." + domain) for host in hosts if host)


def _simplify(entry: dict) -> dict:
    server = entry.get("server") or entry
    remotes = [
        {
            "type": remote.get("type", ""),
            "transport": "sse" if remote.get("type") == "sse" else "http",
            "url": remote.get("url", ""),
            "headers": [_field(header) for header in remote.get("headers") or []],
            "variables": {
                str(key): _field({"name": key, **(value if isinstance(value, dict) else {})})
                for key, value in (remote.get("variables") or {}).items()
            },
        }
        for remote in server.get("remotes") or []
        if remote.get("type") in {"streamable-http", "sse"} and remote.get("url")
    ]
    packages = []
    for package in server.get("packages") or []:
        if not isinstance(package, dict):
            continue
        transport = package.get("transport") or {}
        packages.append(
            {
                "registry": package.get("registryType") or package.get("registry_type", ""),
                "identifier": package.get("identifier") or package.get("name", ""),
                "version": package.get("version", ""),
                "runtime": package.get("runtimeHint", ""),
                "transport": transport.get("type", "stdio") if isinstance(transport, dict) else "",
                "env": [_field(env) for env in package.get("environmentVariables") or []],
                "runtime_arguments": [
                    _field(arg)
                    for arg in package.get("runtimeArguments") or []
                    if isinstance(arg, dict)
                ],
                "package_arguments": [
                    _field(arg)
                    for arg in package.get("packageArguments") or []
                    if isinstance(arg, dict)
                ],
                "install": install_for(package),
            }
        )
    repository = server.get("repository") or {}
    return {
        "name": server.get("name", ""),
        "title": server.get("title") or server.get("name", ""),
        "description": server.get("description", ""),
        "version": server.get("version", ""),
        "repository": repository.get("url", "") if isinstance(repository, dict) else "",
        "website": server.get("websiteUrl", ""),
        "official": _official(entry, server, remotes),
        "remotes": remotes,
        "packages": packages,
    }


async def _fetch(client: httpx.AsyncClient, params: dict) -> dict:
    last: Exception | None = None
    for url in (REGISTRY_URL, FALLBACK_URL):
        try:
            response = await client.get(url, params=params)
            if response.status_code == 404:
                last = httpx.HTTPStatusError(
                    "not found", request=response.request, response=response
                )
                continue
            response.raise_for_status()
            data: dict = response.json()
            return data
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
    raise last or RuntimeError("The MCP Registry did not answer")


async def search(query: str = "", limit: int = 30, cursor: str = "") -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    key = (query.strip().lower(), limit, cursor)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    params: dict[str, Any] = {"limit": limit, "version": "latest"}
    if len(query.strip()) >= 3:  # the registry refuses shorter searches (422)
        params["search"] = query.strip()[:100]
    if cursor:
        params["cursor"] = cursor[:300]
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        data = await _fetch(client, params)
    result = {
        "servers": [
            _simplify(entry)
            for entry in data.get("servers", [])
            if isinstance(entry, dict) and _status(entry) == "active"
        ],
        "next_cursor": (data.get("metadata") or {}).get("nextCursor")
        or (data.get("metadata") or {}).get("next_cursor"),
    }
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), result)
    return result
