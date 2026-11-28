"""Connector tools in the agent's own tool flow (schemas, provenance, calls).

Offered: every tool of the user's enabled connectors that is not held by Amanah,
not switched off (policy ``never``), of a connector that is not waiting for the
person to sign in and has not just failed (``manager.offered``), plus
``resources_list``/``resources_read`` for a server that offers resources. A
server's own instructions ride along on its tools' descriptions, so the model
reads them only when it is offered that server's tools.
"""

from __future__ import annotations

from connectors import naming, store
from connectors.manager import manager, offered, resolve_tool, resource_tools

MAX_NOTE = 300


def _note(server: dict) -> str:
    """The server's instructions, unless Amanah read instructions aimed at the AI in
    them when they were listed (``instructions_flagged``)."""
    if server.get("instructions_flagged"):
        return ""
    return " ".join(str(server.get("instructions") or "").split())[:MAX_NOTE]


def user_tool_schemas(user_id: str) -> list[dict]:
    """Schemas of every usable tool of the user's connectors."""
    if not user_id:
        return []
    schemas = []
    for server in store.list_servers(user_id):
        if not offered(server):
            continue
        note = _note(server)
        for tool in [*(server.get("tools") or []), *resource_tools(server)]:
            if tool.get("held") or store.policy(server, str(tool.get("name") or "")) == "never":
                continue  # held by Amanah until the user trusts it, or switched off
            description = str(tool.get("description", ""))
            if note:
                description = f"{description} (Server note: {note})"[: naming.MAX_DESCRIPTION]
            schemas.append(
                {
                    "name": tool["exposed"],
                    "description": description,
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


def asks_first(user_id: str, name: str) -> bool:
    """The person set this tool to ``ask``: a person approves each call, in any mode."""
    resolved = resolve_tool(user_id, name) if name.startswith(naming.PREFIX) else None
    if resolved is None or resolved[1].get("synthetic"):
        return False
    return bool(store.policy(resolved[0], str(resolved[1].get("name") or "")) == "ask")


async def call(user_id: str, name: str, arguments: dict) -> dict:
    result: dict = await manager.call(user_id, name, arguments)
    return result
