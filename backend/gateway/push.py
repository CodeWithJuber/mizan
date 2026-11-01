"""Web Push: MIZAN's notices on the user's phone or computer, even with the app closed.

Standard Web Push (RFC 8030) with VAPID (RFC 8292) and end-to-end encrypted
payloads (RFC 8291), sent with ``pywebpush``. MIZAN signs with one key pair of
its own, made on first use; the private key is sealed with the data key and
kept in ``bab.db``.

A browser subscription is accepted only for a known push service (Google,
Mozilla, Apple, Microsoft) over HTTPS, so MIZAN never posts to an address a
client chose. A subscription the service reports gone (404/410) is removed.
By default the lock screen shows only "MIZAN has a new notice"; the chat
preference ``push_preview: on`` shows the text.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .store import BabStore

logger = logging.getLogger("mizan.bab.push")

# Push services browsers use today; anything else is refused.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
)
TTL_SECONDS = 24 * 60 * 60


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint or "")
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and parts.port in (None, 443)
        and not parts.username
        and any(host == known or host.endswith("." + known) for known in PUSH_HOSTS)
    )


def _ensure_tables(store: BabStore) -> None:
    with store._connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS push (endpoint TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
            "p256dh TEXT NOT NULL, auth TEXT NOT NULL, created TEXT NOT NULL, last_ok TEXT)"
        )


def subscribe(store: BabStore, owner: str, endpoint: str, p256dh: str, auth: str) -> None:
    if not allowed_endpoint(endpoint):
        raise ValueError("Not a known push service")
    for value in (p256dh, auth):
        base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))  # raises on junk
    _ensure_tables(store)
    with store._lock, store._connect() as conn:
        conn.execute(
            "INSERT INTO push VALUES (?,?,?,?,?,NULL) ON CONFLICT(endpoint) DO UPDATE SET "
            "owner_id=excluded.owner_id, p256dh=excluded.p256dh, auth=excluded.auth",
            (endpoint, owner, p256dh, auth, datetime.now(UTC).isoformat()),
        )


def unsubscribe(store: BabStore, owner: str, endpoint: str) -> bool:
    _ensure_tables(store)
    with store._lock, store._connect() as conn:
        return (
            conn.execute(
                "DELETE FROM push WHERE owner_id = ? AND endpoint = ?", (owner, endpoint)
            ).rowcount
            > 0
        )


def subscriptions(store: BabStore, owner: str) -> list[dict]:
    _ensure_tables(store)
    with store._connect() as conn:
        rows = conn.execute("SELECT * FROM push WHERE owner_id = ?", (owner,)).fetchall()
    return [dict(row) for row in rows]


# ── MIZAN's own signing key ──────────────────────────────────────────────


def _vapid(store: BabStore) -> Any:
    from py_vapid import Vapid02

    from connectors.secrets import seal, unseal

    sealed = store.get("vapid_private")
    if sealed:
        pem = unseal(sealed)
        if pem:
            return Vapid02.from_pem(str(pem).encode())
    vapid = Vapid02()
    vapid.generate_keys()
    pem = vapid.private_pem().decode()
    store.put("vapid_private", seal(pem))
    return vapid


def public_key(store: BabStore) -> str:
    """The application server key browsers subscribe with (base64url, no padding)."""
    from cryptography.hazmat.primitives import serialization

    raw = _vapid(store).public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _contact() -> str:
    import os

    site = os.getenv("MIZAN_PUBLIC_URL", "").strip()
    return site if site.startswith("https://") else "mailto:mizan@localhost.invalid"


def _send_one(store: BabStore, subscription: dict, payload: str) -> str:
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
            },
            data=payload,
            vapid_private_key=_vapid(store),
            vapid_claims={"sub": _contact()},
            ttl=TTL_SECONDS,
            timeout=10,
        )
        return "sent"
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return "gone"
        logger.info("[PUSH] not delivered (%s)", status)
        return "failed"


async def notify(
    store: BabStore,
    owner: str,
    title: str,
    body: str,
    url: str = "/",
    *,
    preview: bool = False,
    tag: str = "",
) -> dict[str, int]:
    """Send one notice to every device the owner turned notifications on for."""
    counts = {"sent": 0, "gone": 0, "failed": 0}
    found = subscriptions(store, owner)
    if not found:
        return counts
    payload = json.dumps(
        {
            "title": title,
            "body": body[:300] if preview else "MIZAN has a new notice",
            "url": url if url.startswith("/") else "/",
            "tag": tag[:64],
        },
        ensure_ascii=False,
    )
    for subscription in found:
        outcome = await asyncio.to_thread(_send_one, store, subscription, payload)
        counts[outcome] += 1
        if outcome == "gone":
            unsubscribe(store, owner, subscription["endpoint"])
    return counts
