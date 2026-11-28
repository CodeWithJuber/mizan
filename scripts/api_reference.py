#!/usr/bin/env python3
"""Write MIZAN's complete API reference from the app itself.

    python scripts/api_reference.py

writes two files:

- ``docs/api-reference.md``: every route, grouped by area, with who may call
  it (public, any signed-in user, administrator) and what it does;
- ``docs/openapi.json``: the OpenAPI 3 schema with every request body, for
  Postman, Insomnia, Bruno or any OpenAPI client (import the file, set the
  server URL and a Bearer token or ``X-API-Key``).

Who may call a route is read from the same tables the app enforces
(``_PUBLIC_API``, ``_OPEN_API_PREFIXES``, ``_ADMIN_PREFIXES`` in
``api/main.py``) and from handlers that check the administrator role.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The same list as enforce_api_access in api/main.py (agent routes check ownership
# themselves: anyone may make and change agents of their own).
_WRITES_NEED_ADMIN = (
    "/api/providers",
    "/api/preferences",
    "/api/skills",
    "/api/sandbox",
    "/api/memory",
)


def _app():
    scratch = tempfile.mkdtemp(prefix="mizan-api-reference-")
    os.environ.setdefault("MIZAN_DATA_DIR", scratch)
    os.environ.setdefault("DB_PATH", str(Path(scratch) / "memory.db"))
    os.environ.setdefault("SECRET_KEY", "api-reference-only-" * 3)
    sys.path.insert(0, str(ROOT / "backend"))
    from api import main

    return main


def access(main, path: str, method: str, endpoint) -> str:
    if path in main._PUBLIC_API or path.startswith(main._OPEN_API_PREFIXES):
        return "public"
    if path.startswith(main._PUBLIC_API_PREFIXES):
        return "capability URL"
    admin = path.startswith(main._ADMIN_PREFIXES) or path == "/api/version"
    if method not in {"GET", "HEAD", "OPTIONS"} and path.startswith(_WRITES_NEED_ADMIN):
        admin = True
    try:
        source = inspect.getsource(endpoint)
    except (OSError, TypeError):
        source = ""
    if "_debug_access(" in source:
        return "debug mode (admins by default, `MIZAN_DEBUG_MODE`)"
    if "_require_admin(" in source or 'has_role("admin")' in source:
        # Some handlers serve every user and add more for administrators.
        return "admin" if admin or "_require_admin(" in source else "user (more for admin)"
    return "admin" if admin else "user"


def summary(endpoint) -> str:
    doc = inspect.getdoc(endpoint) or ""
    first = " ".join(doc.split("\n\n", 1)[0].split())
    if first:
        return first
    # No docstring: the handler's own name says what it does ("list runs").
    name = getattr(endpoint, "__name__", "").strip("_").replace("_", " ")
    return name[:1].upper() + name[1:] if name else ""


def _walk(routes, prefix: str = ""):
    """Every route with its full path, routers included under their prefixes."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            yield from _walk(original.routes, prefix + (getattr(context, "prefix", "") or ""))
        else:
            yield prefix + (getattr(route, "path", "") or ""), route


def routes(main) -> list[dict]:
    found = []
    seen = set()
    for path, route in _walk(main.app.routes):
        if not path.startswith(("/api", "/ws")):
            continue
        methods = sorted(getattr(route, "methods", None) or {"WS"})
        for method in methods:
            if method in {"HEAD", "OPTIONS"} or (method, path) in seen:
                continue
            seen.add((method, path))
            endpoint = getattr(route, "endpoint", None)
            kind = "WEBSOCKET" if method == "WS" else method
            found.append(
                {
                    "method": kind,
                    "path": path,
                    "access": "user (token in the URL)" if kind == "WEBSOCKET" else
                    access(main, path, method, endpoint),
                    "summary": summary(endpoint),
                }
            )  # fmt: skip
    return found


def area(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if parts[0] == "ws":
        return "websocket"
    if len(parts) >= 3 and parts[1] == "v1":
        return "v1"
    return parts[1] if len(parts) > 1 else "root"


def markdown(found: list[dict]) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in found:
        grouped[area(item["path"])].append(item)
    lines = [
        "# MIZAN API reference",
        "",
        "Every route the backend serves, generated from the app "
        "(`python scripts/api_reference.py`; do not edit by hand). How to sign in, "
        "the chat stream's events and worked examples are in "
        "[api-testing.md](api-testing.md). The same routes with every request body "
        "are in [openapi.json](openapi.json): import it into Postman, Insomnia or "
        "Bruno, set the server URL and a Bearer token or `X-API-Key`.",
        "",
        "**Who**: `public` needs nothing; `user` needs a token or API key; `admin` "
        "needs an administrator; `user (more for admin)` serves every user and shows "
        "an administrator more; `debug mode` follows `MIZAN_DEBUG_MODE` (admins, users "
        "or off); `capability URL` is a dev-server preview whose link is the credential. "
        "The summaries come from each handler's docstring, or its name when it has none.",
        "",
        f"{len(found)} routes in {len(grouped)} areas.",
        "",
        "Areas: " + " · ".join(f"[{name}](#{name})" for name in sorted(grouped)),
        "",
    ]
    for name in sorted(grouped):
        lines += [f"## {name}", "", "| Method | Path | Who | What it does |", "|---|---|---|---|"]
        for item in sorted(grouped[name], key=lambda entry: (entry["path"], entry["method"])):
            text = item["summary"].replace("|", "\\|") or "—"
            lines.append(f"| {item['method']} | `{item['path']}` | {item['access']} | {text} |")
        lines.append("")
    return "\n".join(lines)


def openapi(main, found: list[dict]) -> dict:
    schema = main.app.openapi()
    schema.setdefault("components", {})["securitySchemes"] = {
        "bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
    }
    schema["servers"] = [{"url": "https://your-mizan.example"}]
    who = {(item["method"].lower(), item["path"]): item["access"] for item in found}
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            access_level = who.get((method, path), "user")
            operation["x-mizan-access"] = access_level
            if access_level not in {"public", "capability URL"}:
                operation["security"] = [{"bearer": []}, {"apiKey": []}]
    return schema


def main_() -> None:
    main = _app()
    found = routes(main)
    (ROOT / "docs" / "api-reference.md").write_text(markdown(found) + "\n", encoding="utf-8")
    (ROOT / "docs" / "openapi.json").write_text(
        json.dumps(openapi(main, found), indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(found)} routes written to docs/api-reference.md and docs/openapi.json")


if __name__ == "__main__":
    main_()
