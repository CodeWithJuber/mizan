"""Shahid's self-test with a real browser: python3 browse_selftest.py

Serves a small shop on two loopback addresses and checks, in real Chromium, that
a link to another origin is not followed, an order form is held until approved,
an approved order goes through, and every step is witnessed. CI runs it inside
the ``workspace-browser`` image; it prints one JSON line and exits non-zero on
any failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import browse_agent  # noqa: E402

ORDERS: list[str] = []


class Shop(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, body: str, status: int = 200) -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        port = self.server.server_address[1]
        if self.path.startswith("/elsewhere"):
            self._send("<h1>Elsewhere</h1>")
            return
        self._send(
            "<title>Shop</title><h1>Dates shop</h1><p>Ajwa dates, 1 kg: 40 AED</p>"
            f'<a href="http://127.0.0.2:{port}/elsewhere">Elsewhere</a>'
            '<form method="post" action="/order"><label>Name <input name="name"></label>'
            "<button>Order</button></form>"
        )

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        ORDERS.append(self.rfile.read(length).decode())
        self._send("<h1>Ordered</h1>")


async def check() -> dict:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
    other = ThreadingHTTPServer(("127.0.0.2", server.server_address[1]), Shop)
    for item in (server, other):
        threading.Thread(target=item.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    browse_agent.SCHEMES = frozenset({"https", "http"})  # a loopback fixture has no TLS
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        os.environ.pop(name, None)
    steps = [
        {"do": "goto", "url": base},
        {"do": "read"},
        {"do": "click", "role": "link", "name": "Elsewhere"},
        {"do": "fill", "label": "Name", "value": "Zubair"},
        {"do": "click", "role": "button", "name": "Order"},
        {"do": "screenshot"},
    ]
    job = {"origins": ["127.0.0.1"], "steps": steps}
    problem = browse_agent.valid(job)
    first = await browse_agent.run(job)
    orders_before_approval = list(ORDERS)
    held = [entry["key"] for entry in first["held"]]
    second = await browse_agent.run({**job, "approved": held})
    found = {
        "valid": problem is None,
        "read the page": "Ajwa dates" in first["text"],
        "other origin not visited": first["steps"][2]["url"] == base
        and any(entry["navigation"] for entry in first["blocked"]),
        "order held": held == ["POST http://127.0.0.1/order"] and not orders_before_approval,
        "approved order sent": ORDERS == ["name=Zubair"],
        "approved page shows it": "Ordered" in (second["steps"][-1].get("title") or "")
        or second["final_url"].endswith("/order"),
        "witnessed": all(step.get("state_sha256") for step in first["steps"])
        and bool(first["steps"][-1].get("screenshot_sha256")),
        "full url kept": first["steps"][0]["url"] == base,
    }
    for item in (server, other):
        item.shutdown()
    return found


def main() -> None:
    found = asyncio.run(check())
    print(json.dumps(found))
    sys.exit(0 if all(found.values()) else 1)


if __name__ == "__main__":
    main()
