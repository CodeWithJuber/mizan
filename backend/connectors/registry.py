"""Browse the official MCP Registry (registry.modelcontextprotocol.io), cached."""

from __future__ import annotations

import time
from typing import Any

import httpx

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"
CACHE_SECONDS = 3600
_cache: dict[tuple[str, int, str], tuple[float, dict]] = {}


def _simplify(entry: dict) -> dict:
    server = entry.get("server") or entry
    remotes = [
        {
            "type": remote.get("type", ""),
            "url": remote.get("url", ""),
            "headers": [
                {
                    "name": header.get("name", ""),
                    "description": header.get("description", ""),
                    "required": bool(header.get("isRequired")),
                    "secret": bool(header.get("isSecret")),
                }
                for header in remote.get("headers") or []
            ],
        }
        for remote in server.get("remotes") or []
        if remote.get("type") in {"streamable-http", "sse"} and remote.get("url")
    ]
    packages = [
        {
            "registry": package.get("registryType") or package.get("registry_type", ""),
            "identifier": package.get("identifier") or package.get("name", ""),
            "version": package.get("version", ""),
            "runtime": package.get("runtimeHint", ""),
            "env": [
                {
                    "name": env.get("name", ""),
                    "description": env.get("description", ""),
                    "required": bool(env.get("isRequired")),
                    "secret": bool(env.get("isSecret")),
                }
                for env in package.get("environmentVariables") or []
            ],
        }
        for package in server.get("packages") or []
    ]
    repository = server.get("repository") or {}
    return {
        "name": server.get("name", ""),
        "title": server.get("title") or server.get("name", ""),
        "description": server.get("description", ""),
        "version": server.get("version", ""),
        "repository": repository.get("url", "") if isinstance(repository, dict) else "",
        "remotes": remotes,
        "packages": packages,
    }


async def search(query: str = "", limit: int = 30, cursor: str = "") -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    key = (query.strip().lower(), limit, cursor)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    params: dict[str, Any] = {"limit": limit, "version": "latest"}
    if query.strip():
        params["search"] = query.strip()[:100]
    if cursor:
        params["cursor"] = cursor[:300]
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.get(REGISTRY_URL, params=params)
        response.raise_for_status()
        data = response.json()
    result = {
        "servers": [_simplify(entry) for entry in data.get("servers", [])],
        "next_cursor": (data.get("metadata") or {}).get("nextCursor")
        or (data.get("metadata") or {}).get("next_cursor"),
    }
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), result)
    return result
