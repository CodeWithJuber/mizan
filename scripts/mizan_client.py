#!/usr/bin/env python3
"""A small client for MIZAN's HTTP API, to test it without the web app.

Standard library only. Set the server and a credential, then run a command:

    export MIZAN_URL=https://your-mizan.example        # no trailing /api
    export MIZAN_TOKEN=...                             # from "login", or
    export MIZAN_API_KEY=...                           # from "api-key"

    python scripts/mizan_client.py login USERNAME            # prints a token (password asked)
    python scripts/mizan_client.py api-key                   # makes an API key for you
    python scripts/mizan_client.py health
    python scripts/mizan_client.py chat "What is 17*23?"     # streams the answer
    python scripts/mizan_client.py chat "Aur 19*23?" --session my-test
    python scripts/mizan_client.py chat "Design an HTML page for this" --image design.png
    python scripts/mizan_client.py history my-test
    python scripts/mizan_client.py compare "Who built the Taj Mahal?"   # base model vs MIZAN
    python scripts/mizan_client.py imtihan-run --blocks ibrah           # AGI test (admin)
    python scripts/mizan_client.py imtihan-runs
    python scripts/mizan_client.py receipts                  # your signed action receipts
    python scripts/mizan_client.py verify                    # check your receipt chain
    python scripts/mizan_client.py spending
    python scripts/mizan_client.py reliability               # public, no credential

Every command prints JSON; ``chat`` prints the answer as it arrives and then
the closing event (Isnad grades, Truth Gate, sources asked, usage).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def base() -> str:
    url = os.getenv("MIZAN_URL", "").rstrip("/")
    if not url:
        sys.exit("Set MIZAN_URL, for example https://your-mizan.example")
    if not url.startswith(("https://", "http://")):
        sys.exit("MIZAN_URL must start with https:// (or http:// for a local server)")
    return url.removesuffix("/api")


def headers() -> dict[str, str]:
    found = {"Content-Type": "application/json", "Accept": "application/json"}
    if os.getenv("MIZAN_TOKEN"):
        found["Authorization"] = f"Bearer {os.environ['MIZAN_TOKEN']}"
    elif os.getenv("MIZAN_API_KEY"):
        found["X-API-Key"] = os.environ["MIZAN_API_KEY"]
    return found


def call(method: str, path: str, body: dict | None = None, timeout: float = 120.0) -> object:
    data = json.dumps(body).encode() if body is not None else None
    # base() accepts only http(s) addresses.
    request = urllib.request.Request(base() + path, data=data, method=method, headers=headers())  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - the user's own server
            text = response.read().decode()
    except urllib.error.HTTPError as error:
        sys.exit(f"HTTP {error.code}: {error.read().decode()[:500]}")
    return json.loads(text) if text else {}


def show(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def chat(text: str, session: str | None, mode: str | None, images: list[str]) -> None:
    """One message over the streaming route (Server-Sent Events)."""
    body: dict = {
        "session_id": session or f"api-{int(time.time())}",
        "request_id": str(uuid.uuid4()),
        "content": text,
    }
    if mode:
        body["permission_mode"] = mode
    if images:
        body["images"] = [
            {
                "media_type": mimetypes.guess_type(path)[0] or "image/png",
                "data": base64.b64encode(Path(path).read_bytes()).decode(),
            }
            for path in images
        ]
    request = urllib.request.Request(  # noqa: S310 - base() accepts only http(s)
        base() + "/api/chat/stream",
        data=json.dumps(body).encode(),
        method="POST",
        headers={**headers(), "Accept": "text/event-stream"},
    )
    event = ""
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
        for raw in response:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "chat_stream":
                    print(data.get("chunk", ""), end="", flush=True)
                elif event in {"chat_complete", "error"}:
                    print()
                    closing = {
                        k: v for k, v in data.items() if k not in {"thinking_trace", "cognitive"}
                    }
                    show(closing)
                    print(f"session_id: {body['session_id']}", file=sys.stderr)
                    return


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command")
    parser.add_argument("argument", nargs="?")
    parser.add_argument("--session")
    parser.add_argument("--mode", choices=["auto", "auto_edits", "ask", "plan"])
    parser.add_argument("--image", action="append", default=[], help="attach an image (up to 4)")
    parser.add_argument("--blocks", help="comma-separated AGI-test blocks, e.g. ibrah,quran")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    command, argument = args.command, args.argument
    if command == "login":
        password = getpass.getpass("Password: ")
        show(call("POST", "/api/auth/login", {"username": argument, "password": password}))
    elif command == "api-key":
        show(call("POST", "/api/auth/api-key", {}))
    elif command == "health":
        show(call("GET", "/api/health"))
    elif command == "chat":
        chat(argument or sys.exit("chat needs a message"), args.session, args.mode, args.image)
    elif command == "history":
        show(call("GET", f"/api/chat/{argument}"))
    elif command == "sessions":
        show(call("GET", "/api/chat/sessions/list"))
    elif command == "compare":
        body: dict = {"prompt": argument}
        if args.session:
            body["session_id"] = args.session
        show(call("POST", "/api/debug/compare", body, timeout=600))
    elif command == "imtihan-tasks":
        show(call("GET", "/api/imtihan/tasks"))
    elif command == "imtihan-run":
        blocks = [b for b in (args.blocks or "").split(",") if b] or None
        show(call("POST", "/api/imtihan/run", {"blocks": blocks, "repeats": args.repeats}))
    elif command == "imtihan-runs":
        show(call("GET", "/api/imtihan/runs"))
    elif command == "imtihan-result":
        show(call("GET", f"/api/imtihan/runs/{argument}"))
    elif command == "receipts":
        show(call("GET", "/api/sakk"))
    elif command == "verify":
        show(call("GET", "/api/sakk/verify"))
    elif command == "spending":
        show(call("GET", "/api/iqtisad"))
    elif command == "daftar":
        show(call("GET", "/api/daftar"))
    elif command == "reliability":
        show(call("GET", "/api/public/reliability"))
    else:
        sys.exit(f"Unknown command {command!r}; see --help")


if __name__ == "__main__":
    main()
