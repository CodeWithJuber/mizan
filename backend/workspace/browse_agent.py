"""Shahid (شاهد, witness): one browsing job inside the browser sandbox.

Runs in the ``workspace-browser`` image (Playwright for Python + Chromium) as a
one-shot container. It reads a job from stdin, carries out its typed steps in a
fresh browser, and writes one JSON object to stdout. Nothing here comes from a
model unchecked: MIZAN validated the steps before the job was sent.

- Navigation goes only to the job's origins (hosts MIZAN took from the user's
  own words). Other requests, a page's scripts and images, may go to any public
  host; the network (the egress proxy) refuses everything that is not public.
- A request that would change something (any method but GET, HEAD or OPTIONS:
  a form posted, an order placed) is held, unless the job lists it as approved.
  MIZAN asks a person and runs the job again with that one request approved.
- WebSockets, service workers and downloads are refused.
- Each step is witnessed: the full URL (fragment included) and the SHA-256 of
  the page's accessibility snapshot, its text and its screenshot, which MIZAN
  writes into the owner's signed receipts (Sakk).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
from urllib.parse import urlsplit

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SCHEMES = frozenset({"https"})  # pages are read over TLS only
ROLES = frozenset(
    {"button", "link", "tab", "menuitem", "checkbox", "radio", "option", "combobox", "textbox"}
)
KEYS = frozenset({"Enter", "Tab", "Escape", "ArrowDown", "ArrowUp", "PageDown", "PageUp", "Space"})
MAX_STEPS = 12
MAX_TEXT = 20_000
MAX_SNAPSHOT = 20_000
STEP_MS = 15_000
MAX_LISTED = 50


def host_in(host: str, origins: list[str]) -> bool:
    """An exact host, or a host under an origin written as ``.example.com``."""
    host = (host or "").lower().rstrip(".")
    for origin in origins:
        origin = origin.lower().rstrip(".")
        if origin.startswith("."):
            if host == origin[1:] or host.endswith(origin):
                return True
        elif host == origin:
            return True
    return False


def request_key(method: str, url: str) -> str:
    """How a held request is named for approval: method, origin and path (no query)."""
    parts = urlsplit(url)
    return f"{method.upper()} {parts.scheme}://{(parts.hostname or '').lower()}{parts.path or '/'}"


def decide(method: str, url: str, navigation: bool, origins: list[str], approved: list[str]) -> str:
    """allow | block | hold for one request the page makes."""
    parts = urlsplit(url)
    if parts.scheme in {"data", "blob", "about"}:
        return "allow"
    if parts.scheme not in SCHEMES or not parts.hostname:
        return "block"
    if navigation and not host_in(parts.hostname, origins):
        return "block"
    if method.upper() not in SAFE_METHODS:
        return "allow" if request_key(method, url) in approved else "hold"
    return "allow"


def digest(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def valid(job: dict) -> str | None:
    """Why a job cannot run (MIZAN checks this before sending; checked again here)."""
    origins = job.get("origins")
    steps = job.get("steps")
    if not isinstance(origins, list) or not origins or not all(isinstance(o, str) for o in origins):
        return "a job needs the origins it may visit"
    if not isinstance(steps, list) or not 0 < len(steps) <= MAX_STEPS:
        return f"a job has 1 to {MAX_STEPS} steps"
    for step in steps:
        action = step.get("do") if isinstance(step, dict) else None
        if action == "goto":
            parts = urlsplit(str(step.get("url") or ""))
            if parts.scheme not in SCHEMES or not host_in(parts.hostname or "", origins):
                return "every page visited must be an https page of the job's origins"
        elif action == "click":
            if step.get("role") is not None and step.get("role") not in ROLES:
                return "unknown role"
            if not str(step.get("name") or step.get("text") or "").strip():
                return "a click names what it clicks"
        elif action == "fill":
            if not str(step.get("label") or "").strip() or not isinstance(step.get("value"), str):
                return "a fill names its field and value"
        elif action == "press":
            if step.get("key") not in KEYS:
                return "unknown key"
        elif action not in {"read", "screenshot", "wait"}:
            return f"unknown step {action!r}"
    return None


async def run(job: dict) -> dict:
    from playwright.async_api import async_playwright

    origins = list(job["origins"])
    approved = [str(item) for item in job.get("approved") or []]
    held: list[dict] = []
    blocked: list[dict] = []
    records: list[dict] = []
    found: dict = {"text": "", "snapshot": "", "screenshot": ""}

    async def guard(route, request):
        navigation = request.is_navigation_request()
        verdict = decide(request.method, request.url, navigation, origins, approved)
        if verdict == "allow":
            await route.continue_()
            return
        entry = {"method": request.method, "url": request.url[:500], "navigation": navigation}
        if verdict == "hold":
            entry["key"] = request_key(request.method, request.url)
            # What would be sent, so the person deciding sees it.
            entry["data"] = (request.post_data or "")[:500]
            held.append(entry)
        elif len(blocked) < MAX_LISTED:
            blocked.append(entry)
        # A refused navigation is aborted (net::ERR_ABORTED): the browser stays on
        # the page it is on and shows no error page, so the steps after a
        # refused link or a held form still have their page.
        await route.abort("aborted" if navigation else "blockedbyclient")

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            args=["--disable-dev-shm-usage"], proxy={"server": proxy} if proxy else None
        )
        context = await browser.new_context(
            service_workers="block",
            accept_downloads=False,
            viewport={"width": 1280, "height": 800},
            locale=str(job.get("locale") or "en-US"),
        )
        page = await context.new_page()
        await page.route("**/*", guard)
        await page.route_web_socket("**/*", lambda socket: socket.close())
        page.set_default_timeout(STEP_MS)

        for step in job["steps"]:
            action = step["do"]
            record: dict = {"do": action, "ok": True}
            held_before = len(held)
            try:
                if action == "goto":
                    response = await page.goto(step["url"], wait_until="domcontentloaded")
                    record["status"] = response.status if response else None
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:  # noqa: BLE001 - a busy page is still read as it is
                        pass
                elif action == "click":
                    target = (
                        page.get_by_role(step["role"], name=step["name"])
                        if step.get("role")
                        else page.get_by_text(str(step.get("text") or step.get("name")))
                    )
                    await target.first.click()
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:  # noqa: BLE001
                        pass
                elif action == "fill":
                    field = page.get_by_label(step["label"])
                    if not await field.count():
                        field = page.get_by_placeholder(step["label"])
                    await field.first.fill(step["value"])
                elif action == "press":
                    await page.keyboard.press(step["key"])
                elif action == "wait":
                    await page.wait_for_timeout(min(int(step.get("ms") or 1000), 5000))
                elif action == "read":
                    found["snapshot"] = (await page.locator("body").aria_snapshot())[:MAX_SNAPSHOT]
                    found["text"] = (await page.inner_text("body"))[:MAX_TEXT]
                    record["text_sha256"] = digest(found["text"])
                elif action == "screenshot":
                    image = await page.screenshot(full_page=False)
                    found["screenshot"] = base64.b64encode(image).decode()
                    record["screenshot_sha256"] = digest(image)
            except Exception as exc:  # noqa: BLE001 - every failure is reported, none hidden
                record["ok"] = False
                record["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
            if len(held) > held_before:
                record["held"] = [entry["key"] for entry in held[held_before:]]
            record["url"] = page.url
            try:
                record["title"] = (await page.title())[:300]
                record["state_sha256"] = digest(await page.locator("body").aria_snapshot())
            except Exception:  # noqa: BLE001
                pass
            records.append(record)
            if not record["ok"] and action == "goto":
                break  # nothing after a page that did not open is meaningful
        await browser.close()

    return {
        "steps": records,
        "held": held,
        "blocked": blocked,
        "final_url": records[-1]["url"] if records else "",
        **found,
    }


def main() -> None:
    try:
        job = json.loads(sys.stdin.read(1_000_000) or "{}")
    except ValueError:
        job = {}
    problem = valid(job) if isinstance(job, dict) else "the job is not an object"
    if problem:
        print(json.dumps({"error": problem}))
        return
    timeout = min(max(int(job.get("timeout_s") or 60), 5), 180)
    try:
        result = asyncio.run(asyncio.wait_for(run(job), timeout))
    except TimeoutError:
        result = {"error": f"the job did not finish in {timeout} s"}
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
