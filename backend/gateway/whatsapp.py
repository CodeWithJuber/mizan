"""Bab WhatsApp: the official Cloud API, used only as Meta's terms allow.

Section 4.7 of the Meta Terms for WhatsApp Business Platform (23 Sep 2026)
prohibits AI providers whose AI is the primary functionality. Regulators
compelled exceptions, which Meta's own "AI Providers" pricing page lists:
Italy and the other EEA markets (European Commission interim measures,
9 Jun 2026), Brazil (CADE, 4 Mar 2026) and Türkiye (Competition Board,
5 Jun 2026). So MIZAN decides per linked number, from its country:

- **assistant**: a number in a compelled market chats with MIZAN as in the
  web app (the same turn, its gates and Tadbir);
- **ancillary** everywhere else: MIZAN never chats there. A message gets one
  fixed answer pointing to the app; MIZAN's own notices still come, as
  approved templates outside the 24-hour window (a template is a paid
  message, admitted by Iqtisad before it is sent).

What it accepts: webhook events signed by Meta (``X-Hub-Signature-256``,
HMAC-SHA256 of the body with the app secret) for MIZAN's own phone number,
text messages from linked numbers ("link <code>" links one). Words that came
through WhatsApp are never captured for training (s.4.7 forbids using
platform data to train or improve models). Held actions are never allowed
from WhatsApp; the reply points to Held actions in MIZAN.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from .store import BabStore

logger = logging.getLogger("mizan.bab.whatsapp")

CHANNEL = "whatsapp"
GRAPH = "https://graph.facebook.com"
MAX_TEXT = 4000  # WhatsApp allows 4,096 characters in a text body
WINDOW_SECONDS = 24 * 3600  # Meta's customer-service window

# Markets where Meta lists compelled access for AI providers (its AI Providers
# pricing page, read 27 Oct 2026): the EEA (EU 27, Iceland, Liechtenstein,
# Norway), Brazil and Türkiye. A legal fact, kept as data; update it when
# Meta's page or the measures change.
EEA = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE "
    "IS LI NO".split()
)
COMPELLED = EEA | {"BR", "TR"}

# (owner, session, text) -> (reply, held actions)
RunTurn = Callable[[str, str, str], Awaitable[tuple[str, list[dict]]]]


@dataclass(frozen=True)
class WhatsAppConfig:
    token: str
    phone_id: str
    app_secret: str
    verify_token: str
    version: str = "v24.0"
    template: str = ""
    template_language: str = "en"
    template_usd: float | None = None
    public_url: str = ""

    @classmethod
    def from_env(cls) -> WhatsAppConfig | None:
        get = os.getenv
        values = {
            "token": get("WHATSAPP_TOKEN", "").strip(),
            "phone_id": get("MIZAN_WHATSAPP_PHONE_ID", "").strip(),
            "app_secret": get("MIZAN_WHATSAPP_APP_SECRET", "").strip(),
            "verify_token": get("MIZAN_WHATSAPP_VERIFY_TOKEN", "").strip(),
        }
        if not all(values.values()):
            return None
        price = get("MIZAN_WHATSAPP_TEMPLATE_USD", "").strip()
        try:
            usd = float(price) if price else None
        except ValueError:
            usd = None
        return cls(
            **values,
            version=get("MIZAN_WHATSAPP_GRAPH_VERSION", "").strip() or "v24.0",
            template=get("MIZAN_WHATSAPP_TEMPLATE", "").strip(),
            template_language=get("MIZAN_WHATSAPP_TEMPLATE_LANGUAGE", "").strip() or "en",
            template_usd=usd,
            public_url=get("MIZAN_PUBLIC_URL", "").rstrip("/"),
        )


def region(wa_id: str) -> str | None:
    """The country of a WhatsApp number (its E.164 digits), or None."""
    import phonenumbers

    digits = re.sub(r"\D", "", wa_id or "")
    if not digits:
        return None
    try:
        found = phonenumbers.region_code_for_number(phonenumbers.parse("+" + digits))
    except phonenumbers.NumberParseException:
        return None
    return found if found and found != "ZZ" else None


def mode(wa_id: str) -> str:
    """assistant where Meta was compelled to admit assistants, else ancillary."""
    return "assistant" if region(wa_id) in COMPELLED else "ancillary"


def signed(body: bytes, header: str, secret: str) -> bool:
    """Whether Meta signed this webhook body (``sha256=<hex HMAC>``)."""
    if not header.startswith("sha256=") or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256=") :])


def messages_of(payload: dict, phone_id: str) -> list[dict]:
    """The messages a webhook event carries for MIZAN's own number."""
    found = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            if str((value.get("metadata") or {}).get("phone_number_id", "")) != phone_id:
                continue
            for message in value.get("messages") or []:
                found.append(
                    {
                        "id": str(message.get("id", "")),
                        "from": re.sub(r"\D", "", str(message.get("from", ""))),
                        "type": str(message.get("type", "")),
                        "text": str((message.get("text") or {}).get("body", "")),
                        "forwarded": bool((message.get("context") or {}).get("forwarded")),
                    }
                )
    return found


def chunks(text: str, size: int = MAX_TEXT) -> list[str]:
    text = text.strip() or "—"
    parts: list[str] = []
    while len(text) > size:
        cut = max(text.rfind("\n\n", 0, size), text.rfind("\n", 0, size), text.rfind(" ", 0, size))
        cut = cut if cut > size // 2 else size
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    parts.append(text)
    return parts


_LINK = re.compile(r"^\s*/?link\s+([A-Za-z0-9_-]{16,64})\s*$", re.I)


class WhatsAppBot:
    def __init__(
        self,
        config: WhatsAppConfig,
        store: BabStore,
        run_turn: RunTurn,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency: int = 4,
    ):
        self.config = config
        self.store = store
        self.run_turn = run_turn
        self._client = httpx.AsyncClient(timeout=30, transport=transport)
        self._owner_locks: dict[str, asyncio.Lock] = {}
        self._gate = asyncio.Semaphore(concurrency)
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._tasks: set[asyncio.Task] = set()
        self.error = ""

    async def close(self) -> None:
        await self._client.aclose()

    # ── sending ──────────────────────────────────────────────────────────

    async def _post(self, body: dict) -> dict:
        url = f"{GRAPH}/{self.config.version}/{self.config.phone_id}/messages"
        response = await self._client.post(
            url,
            json={"messaging_product": "whatsapp", **body},
            headers={"Authorization": f"Bearer {self.config.token}"},
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            error = (data.get("error") or {}) if isinstance(data, dict) else {}
            self.error = f"{response.status_code}: {str(error.get('message', ''))[:160]}"
            raise httpx.HTTPStatusError(self.error, request=response.request, response=response)
        return data

    async def send_text(self, to: str, text: str) -> None:
        for part in chunks(text):
            # Links in MIZAN's words are never previewed.
            await self._post(
                {"to": to, "type": "text", "text": {"body": part, "preview_url": False}}
            )

    def in_window(self, wa_id: str) -> bool:
        last = self.store.get(f"whatsapp:last_in:{wa_id}")
        return bool(last) and time.time() - float(last) < WINDOW_SECONDS

    async def notify(self, owner: str, text: str) -> str:
        """One of MIZAN's own notices to the owner's linked number: free text
        inside the 24-hour window, else an approved template paid through
        Iqtisad. Returns what happened."""
        link = self.store.link_for_owner(CHANNEL, owner)
        if link is None:
            return "not linked"
        wa_id = str(link["external_id"])
        if self.in_window(wa_id):
            await self.send_text(wa_id, text)
            return "sent"
        if not self.config.template or self.config.template_usd is None:
            return "no template"  # outside the window only a paid template may be sent
        from api import iqtisad

        try:
            iqtisad.charge_fee(owner, self.config.template_usd, "whatsapp:template")
        except iqtisad.BudgetExhausted:
            return "over budget"
        await self._post(
            {
                "to": wa_id,
                "type": "template",
                "template": {
                    "name": self.config.template,
                    "language": {"code": self.config.template_language},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": text[:900]}]}
                    ],
                },
            }
        )
        return "template"

    # ── receiving ────────────────────────────────────────────────────────

    def accept(self, payload: dict) -> int:
        """Take a verified webhook event; each new message is answered in the
        background (Meta wants the webhook answered at once)."""
        count = 0
        for message in messages_of(payload, self.config.phone_id):
            if not message["id"] or message["id"] in self._seen:
                continue  # Meta delivers again when it is unsure: answer once
            self._seen[message["id"]] = None
            while len(self._seen) > 2000:
                self._seen.popitem(last=False)
            task = asyncio.create_task(self._handle_logged(message))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            count += 1
        return count

    async def _handle_logged(self, message: dict) -> None:
        try:
            await self.handle(message)
        except Exception:  # noqa: BLE001 - one message must not stop the channel
            logger.exception("WhatsApp message not answered")

    async def handle(self, message: dict) -> None:
        wa_id = message["from"]
        if not wa_id:
            return
        self.store.put(f"whatsapp:last_in:{wa_id}", str(time.time()))
        if message["type"] != "text":
            if self.store.link(CHANNEL, wa_id) is not None:
                await self.send_text(wa_id, "MIZAN reads text messages here.")
            return
        text = message["text"].strip()
        code = _LINK.match(text)
        if code is not None:
            owner = self.store.redeem(code.group(1), CHANNEL, wa_id, wa_id)
            if owner is not None:
                await self.send_text(wa_id, self._linked_note(wa_id))
                return
        link = self.store.link(CHANNEL, wa_id)
        if link is None or not text:
            return  # not linked: ignored
        if mode(wa_id) != "assistant":
            await self.send_text(wa_id, self._ancillary_note())
            return
        if message["forwarded"]:
            # Someone else's words: data to work on, never the user's request.
            text = f"Forwarded message:\n```\n{text}\n```"
        owner = str(link["owner_id"])
        lock = self._owner_locks.setdefault(owner, asyncio.Lock())
        async with lock, self._gate:
            reply, held = await self.run_turn(owner, str(link["session_id"]), text)
        await self.send_text(wa_id, reply + _held_note(held, self.config.public_url))

    def _linked_note(self, wa_id: str) -> str:
        if mode(wa_id) == "assistant":
            return "Linked. Messages from this number now go to your own MIZAN."
        return "Linked for MIZAN's notices. " + self._ancillary_note()

    def _ancillary_note(self) -> str:
        where = f" {self.config.public_url}" if self.config.public_url else ""
        return (
            "Under Meta's WhatsApp terms MIZAN may chat on WhatsApp only in the EEA, Brazil "
            "and Türkiye, so here it sends only your notices. Talk to MIZAN in the app"
            f"{where} or on Telegram."
        )


def _held_note(held: list[dict], public_url: str) -> str:
    if not held:
        return ""
    names = ", ".join(sorted({str(item.get("tool", "?")) for item in held}))
    where = f"{public_url}/" if public_url else "MIZAN"
    return (
        f"\n\nMIZAN held {len(held)} action(s) for you ({names}). Nothing is allowed from "
        f"WhatsApp: open Held actions in {where} to read exactly what each would do."
    )


def challenge(params: dict[str, Any], verify_token: str) -> str | None:
    """Meta's subscription check: echo the challenge when the token matches."""
    if params.get("hub.mode") != "subscribe":
        return None
    given = str(params.get("hub.verify_token", ""))
    if not verify_token or not hmac.compare_digest(given, verify_token):
        return None
    return str(params.get("hub.challenge", ""))
