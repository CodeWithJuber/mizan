"""Shahid (شاهد, witness): MIZAN uses web pages in its browser sandbox, and can show what it did.

A browsing job runs on the private runner in a one-shot hardened container
(``workspace/browse.py`` and ``browse_agent.py``); nothing of the browser is kept
after it. MIZAN fixes everything that matters before the browser starts:

- **Where**: the origins are the hosts of the links in the user's own words
  (never a link inside pasted text or an image). The browser may follow a link
  only within them; a page's scripts and images may come from any public host,
  and the network refuses everything that is not public.
- **What**: Lisan proposes the steps (go to, click, fill, press, read,
  screenshot); MIZAN checks each one. A field is filled only with words the user
  wrote: MIZAN never types what the user did not say.
- **Changes**: every request that would change something (a form posted, an
  order placed) is held. MIZAN shows the person exactly what would be sent and
  runs the job again with that one request approved, through the same Allow/Deny
  as every other action (``shahid_submit`` is a mutating tool).
- **Witness**: each step's full URL and the SHA-256 of the page's accessibility
  snapshot, text and screenshot are written into the owner's signed receipts
  (Sakk); the screenshot is kept with the chat like an image the user sent.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urlsplit

from workspace.browse_agent import KEYS, MAX_STEPS, ROLES, host_in, valid

logger = logging.getLogger("mizan.tadbir.shahid")
TIMEOUT_S = 90


def available() -> bool:
    from workspace import session_client

    return bool(session_client.available())


def origins_from(urls: list[str]) -> list[str]:
    """The hosts of the user's links, each with its ``www.`` twin."""
    found: list[str] = []
    for url in urls:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if not host or "." not in host:
            continue
        bare = host.removeprefix("www.")
        for name in (bare, f"www.{bare}"):
            if name not in found:
                found.append(name)
    return found[:8]


def https(url: str) -> str:
    parts = urlsplit(url)
    return url if parts.scheme == "https" else parts._replace(scheme="https").geturl()


def plan(steps: Any, origins: list[str], message: str) -> tuple[list[dict] | None, str]:
    """MIZAN's check of Lisan's steps: (the steps to run, or None with the reason)."""
    if not isinstance(steps, list) or not steps:
        return None, "no steps"
    clean: list[dict] = []
    said = " ".join(message.split()).casefold()
    for step in steps[:MAX_STEPS]:
        if not isinstance(step, dict):
            return None, "a step is not an object"
        action = step.get("do")
        if action == "goto":
            clean.append({"do": "goto", "url": https(str(step.get("url") or ""))})
        elif action == "click":
            role = step.get("role")
            entry = {"do": "click", "name": str(step.get("name") or step.get("text") or "")[:200]}
            if role in ROLES:
                entry["role"] = str(role)
            clean.append(entry)
        elif action == "fill":
            value = str(step.get("value") or "")
            if " ".join(value.split()).casefold() not in said:
                return None, f"MIZAN fills a field only with the user's own words, not {value!r}"
            clean.append(
                {"do": "fill", "label": str(step.get("label") or "")[:200], "value": value}
            )
        elif action == "press" and step.get("key") in KEYS:
            clean.append({"do": "press", "key": step["key"]})
        elif action in {"read", "screenshot"}:
            clean.append({"do": action})
        elif action == "wait":
            clean.append({"do": "wait", "ms": min(int(step.get("ms") or 1000), 5000)})
        else:
            return None, f"unknown step {action!r}"
    # What the answer is written from, and what the person can see.
    if not any(step["do"] == "read" for step in clean[-2:]):
        clean.append({"do": "read"})
    if not any(step["do"] == "screenshot" for step in clean):
        clean.append({"do": "screenshot"})
    clean = clean[:MAX_STEPS]
    problem = valid({"origins": origins, "steps": clean})
    return (None, problem) if problem else (clean, "")


async def browse(
    owner: str, origins: list[str], steps: list[dict], approved: list[str] | None = None
) -> dict:
    """Run one job on the runner; keep the screenshot and the witness receipts."""
    from workspace import session_client

    body = {
        "origins": origins,
        "steps": steps,
        "approved": list(approved or []),
        "timeout_s": TIMEOUT_S,
    }
    result = await session_client.call("POST", "/browse", body, timeout=TIMEOUT_S + 30)
    if result.get("error"):
        return {"error": str(result["error"])[:300]}
    shot = str(result.pop("screenshot", "") or "")
    if shot:
        result["screenshot_sha"] = _keep_screenshot(owner, shot)
    _witness(owner, result, approved or [])
    found: dict = result
    return found


def _keep_screenshot(owner: str, data: str) -> str | None:
    from perception import basar

    try:
        image = basar.prepare(base64.b64decode(data))
        basar.store(owner, image)
        return str(image.sha)
    except Exception:  # noqa: BLE001 - the answer stands without its picture
        logger.warning("[SHAHID] screenshot not kept", exc_info=True)
        return None


def _witness(owner: str, result: dict, approved: list[str]) -> None:
    from security import sakk

    for number, step in enumerate(result.get("steps") or [], 1):
        sakk.record(
            owner,
            "browse",
            {
                "step": number,
                "do": step.get("do"),
                "ok": step.get("ok"),
                "url": step.get("url"),
                "state_sha256": step.get("state_sha256"),
                "text_sha256": step.get("text_sha256"),
                "screenshot_sha256": step.get("screenshot_sha256"),
                "held": step.get("held") or [],
                "approved": approved,
            },
            f"Shahid {step.get('do')} {step.get('url', '')}"[:200],
        )


def held_summary(result: dict) -> list[dict]:
    """What the page tried to send, for the person who decides."""
    return [
        {"request": entry.get("key"), "data": entry.get("data", "")}
        for entry in result.get("held") or []
    ]


def in_origins(url: str, origins: list[str]) -> bool:
    return bool(host_in(urlsplit(url).hostname or "", origins))
