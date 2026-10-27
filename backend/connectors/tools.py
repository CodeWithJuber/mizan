"""Connector tools in the agent's own tool flow (schemas, provenance, calls)."""

from __future__ import annotations

from connectors import naming, store
from connectors.manager import manager, resolve_tool


def user_tool_schemas(user_id: str) -> list[dict]:
    """Schemas of every enabled tool of the user's enabled connectors."""
    if not user_id:
        return []
    schemas = []
    for server in store.list_servers(user_id):
        if not server.get("enabled", True):
            continue
        disabled = set(server.get("disabled_tools") or [])
        for tool in server.get("tools") or []:
            if tool.get("name") in disabled:
                continue
            schemas.append(
                {
                    "name": tool["exposed"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema")
                    or {"type": "object", "properties": {}},
                }
            )
    return schemas


def is_user_tool(user_id: str, name: str) -> bool:
    return bool(user_id) and resolve_tool(user_id, name) is not None


def read_only_hint(user_id: str, name: str) -> bool:
    resolved = resolve_tool(user_id, name) if name.startswith(naming.PREFIX) else None
    return bool(resolved and resolved[1].get("read_only") and not resolved[1].get("destructive"))


async def call(user_id: str, name: str, arguments: dict) -> dict:
    result: dict = await manager.call(user_id, name, arguments)
    return result
