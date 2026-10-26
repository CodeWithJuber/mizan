"""Model-facing tool names and schemas for MCP tools."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

PREFIX = "mcp__"
MAX_NAME = 64
MAX_SCHEMA_BYTES = 6 * 1024
MAX_DESCRIPTION = 1000


def slug(text: str, limit: int = 16) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (value or "server")[:limit].strip("_") or "server"


def tool_name(server_slug: str, tool: str) -> str:
    """``mcp__<server>__<tool>`` within 64 safe characters (hash suffix on overflow)."""
    safe_tool = re.sub(r"[^A-Za-z0-9_-]+", "_", tool).strip("_") or "tool"
    name = f"{PREFIX}{server_slug}__{safe_tool}"
    if len(name) <= MAX_NAME:
        return name
    digest = hashlib.sha256(tool.encode()).hexdigest()[:8]
    room = MAX_NAME - len(PREFIX) - len(server_slug) - 2 - 9
    return f"{PREFIX}{server_slug}__{safe_tool[:room]}_{digest}"


def input_schema(schema: Any) -> dict:
    """An object schema small enough for every provider; falls back to free-form."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    result = copy.deepcopy(schema)
    result.pop("$schema", None)
    result["type"] = "object"
    result.setdefault("properties", {})
    try:
        encoded = json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}}
    if len(encoded.encode()) > MAX_SCHEMA_BYTES:
        properties = result.get("properties") or {}
        return {
            "type": "object",
            "properties": {
                key: {"description": str((value or {}).get("description", ""))[:200]}
                if isinstance(value, dict)
                else {}
                for key, value in list(properties.items())[:40]
            },
            "required": [r for r in result.get("required", []) if r in properties][:40],
        }
    return result


def description(server_name: str, text: str | None) -> str:
    body = " ".join(str(text or "").split())
    return f"[{server_name} MCP] {body}"[:MAX_DESCRIPTION]
