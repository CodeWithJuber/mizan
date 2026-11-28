"""Bounded, request-local tool discovery; selection is not authorization.

The caller supplies only visible runtime capabilities. Ranking uses their own
names/descriptions, with no language/intent table or additional model call.
Unselected capabilities remain discoverable; invocation still uses the normal
executor's ownership, permission and argument checks.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from copy import deepcopy

DISCOVER_TOOL = "mizan_discover_tools"
# The schema window per request (MIZAN_TOOL_CATALOG_LIMIT / _BYTES); the older
# MIZAN_CHAT_TOOL_SCHEMA_* names still work when the new ones are not set.
DEFAULT_WINDOW = (16, 32_768)


def window_limits() -> tuple[int, int]:
    """(tools, bytes) offered per request, discovery included, from the settings."""

    def read(new: str, old: str, default: int, low: int, high: int) -> int:
        raw = os.getenv(new) or os.getenv(old) or ""
        try:
            return max(low, min(high, int(float(raw)))) if raw.strip() else default
        except (TypeError, ValueError, OverflowError):
            return default

    return (
        read("MIZAN_TOOL_CATALOG_LIMIT", "MIZAN_CHAT_TOOL_SCHEMA_LIMIT", DEFAULT_WINDOW[0], 2, 32),
        read(
            "MIZAN_TOOL_CATALOG_BYTES",
            "MIZAN_CHAT_TOOL_SCHEMA_BYTES",
            DEFAULT_WINDOW[1],
            4096,
            65_536,
        ),
    )


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[^\W_]+", text.casefold()) if len(word) > 2}


def _group(name: str) -> str:
    """Name group for the directory: connector tools group by their server."""
    if name.startswith("mcp__"):
        return "mcp__" + name[5:].split("__", 1)[0]
    return name.split("_", 1)[0]


def _bytes(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    )


def schema_snapshot(schema: object) -> dict | None:
    """Reject invalid extension metadata before it can break a provider request."""
    if not isinstance(schema, dict):
        return None
    name = schema.get("name")
    if (
        not isinstance(name, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) is None
        or not isinstance(schema.get("description", ""), str)
        or not isinstance(schema.get("input_schema"), dict)
    ):
        return None
    try:
        encoded = json.dumps(schema, ensure_ascii=False, allow_nan=False).encode("utf-8")
        snapshot: object = json.loads(encoded)
        return snapshot if isinstance(snapshot, dict) else None
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return None


class ToolCatalog:
    """One execution's schema window over its permitted capability snapshot."""

    def __init__(
        self,
        schemas: list[dict],
        task: str,
        *,
        context_names: set[str] | None = None,
        max_tools: int = 8,
        max_bytes: int = 12_288,
    ):
        self.max_tools = max(2, min(32, max_tools))
        self.max_bytes = max(4096, min(65_536, max_bytes))
        self._schemas = {}
        for schema in schemas:
            snapshot = schema_snapshot(schema)
            if snapshot is not None and snapshot["name"] != DISCOVER_TOOL:
                self._schemas[snapshot["name"]] = snapshot
        self._terms = {
            name: _terms(name + " " + str(schema.get("description", "")))
            for name, schema in self._schemas.items()
        }
        self._frequency = Counter(term for terms in self._terms.values() for term in terms)
        groups = sorted({_group(name) for name in self._schemas})
        self._discovery = {
            "name": DISCOVER_TOOL,
            "description": (
                "Find and load available tool definitions for the next model turn; this does "
                "not execute actions. Use names for exact tools, query to search descriptions, "
                "or an empty query with cursor to browse every available tool. Loaded tools "
                "replace the current schema window; execution permissions still apply. "
                f"Available tools: {len(self._schemas)}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 400},
                    "names": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 64},
                        "maxItems": self.max_tools - 1,
                    },
                    "cursor": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        }
        # The directory is optional metadata; the discovery schema itself must
        # fit the same byte budget even with many unusual extension names.
        base_description = str(self._discovery["description"])
        visible_groups: list[str] = []
        for group in groups[:24]:
            candidate_groups = [*visible_groups, group[:40]]
            self._discovery["description"] = (
                base_description + " Name groups: " + ", ".join(candidate_groups) + "."
            )
            if _bytes([self._discovery]) > self.max_bytes:
                break
            visible_groups = candidate_groups
        self._discovery["description"] = base_description + (
            " Name groups: " + ", ".join(visible_groups) + "." if visible_groups else ""
        )
        self._loaded: list[str] = []
        self._load(self._rank(task, context_names or set(), relevant_only=True))

    def _rank(
        self, query: str, context_names: set[str] | None = None, *, relevant_only: bool = False
    ) -> list[str]:
        terms = _terms(query)
        context_names = context_names or set()
        scores = {}
        for name, tool_terms in self._terms.items():
            exact = bool(re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", query, re.I))
            matches = terms & tool_terms
            if (
                relevant_only
                and not exact
                and name not in context_names
                and not terms & _terms(name)
                and len(matches) < 2
            ):
                # One incidental description word (for example, a request's
                # output format) is weak evidence for sending an action schema.
                # Explicit discovery still searches those matches normally.
                continue
            score = sum(math.log1p(len(self._schemas) / self._frequency[term]) for term in matches)
            score += 1000 if exact else 0
            score += 1 if name in context_names else 0
            if score or not relevant_only:
                scores[name] = score
        return sorted(scores, key=lambda name: (-scores[name], name))

    def _load(self, names: list[str]) -> list[dict]:
        selected: list[str] = []
        skipped = []
        for name in dict.fromkeys(names):
            if name not in self._schemas:
                skipped.append({"name": name, "reason": "not_available"})
                continue
            candidate = [self._discovery, *(self._schemas[n] for n in [*selected, name])]
            if len(candidate) > self.max_tools or _bytes(candidate) > self.max_bytes:
                skipped.append({"name": name, "reason": "schema_window_limit"})
            else:
                selected.append(name)
        self._loaded = selected
        return skipped

    def schemas(self) -> list[dict]:
        if not self._schemas:
            return []
        return deepcopy([self._discovery, *(self._schemas[name] for name in self._loaded)])

    def discover(self, params: dict) -> dict:
        """Return metadata and select the next window, without calling any tool."""
        if not isinstance(params, dict) or set(params) - {"query", "names", "cursor"}:
            return {"error": "Expected only query, names and cursor"}
        query, names, cursor = (
            params.get("query", ""),
            params.get("names", []),
            params.get("cursor", 0),
        )
        if (
            not isinstance(query, str)
            or len(query) > 400
            or not isinstance(names, list)
            or len(names) >= self.max_tools
            or any(not isinstance(name, str) or len(name) > 64 for name in names)
            or type(cursor) is not int
            or cursor < 0
        ):
            return {"error": "Invalid discovery arguments"}
        ranked = names if names else self._rank(query)
        page = ranked[cursor : cursor + self.max_tools - 1]
        skipped = self._load(page)
        next_cursor = cursor + len(page)
        return {
            "kind": "tool_discovery_only",
            "tools": [
                {"name": name, "description": str(self._schemas[name].get("description", ""))[:240]}
                for name in page
                if name in self._schemas
            ],
            "loaded_for_next_turn": list(self._loaded),
            "not_loaded": skipped,
            "next_cursor": next_cursor if next_cursor < len(ranked) else None,
            "total_matches": len(ranked),
        }
