"""Bab Telegram: talk to your own MIZAN from Telegram.

Uses the Telegram Bot API over HTTPS (httpx), with long polling, so no public
webhook is needed. What it accepts:

- private chats only, and only from a Telegram account its MIZAN user linked
  (MIZAN → Channels → Link Telegram gives a one-time link);
- text (forwarded text counts as quoted data, never as the user's request);
- voice notes, when the server can hear (Sama'): transcribed on MIZAN's own
  server, shown back as "Heard: ...", then answered like typed text;
- the buttons under a reply that allow or deny an action MIZAN held, from the
  same linked account only.

Each message runs the same turn as the web chat (the user's own agent, gates,
Tadbir), and the chat is saved so it also shows in MIZAN. Commands: /new
starts a new chat, /unlink removes the link.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .store import BabStore

logger = logging.getLogger("mizan.bab.telegram")

CHANNEL = "telegram"
API = "https://api.telegram.org"
MAX_TEXT = 4000  # Telegram's limit is 4096 characters per message
POLL_SECONDS = 50

# (owner, session, text) -> (reply, held actions [{id, tool, reason}])
RunTurn = Callable[[str, str, str], Awaitable[tuple[str, list[dict]]]]
# (owner, held id, "allow" | "deny") -> a line for the user
Decide = Callable[[str, str, str], Awaitable[str]]
# (owner, session, audio, mime) -> the words heard; ValueError carries a line for the user
Hear = Callable[[str, str, bytes, str], Awaitable[str]]
MAX_VOICE_BYTES = 2 * 1024 * 1024
MAX_VOICE_SECONDS = 90


class TelegramError(RuntimeError):
    def __init__(self, status: int, description: str):
        self.status = status
        super().__init__(f"Telegram {status}: {description}")


def chunks(text: str, size: int = MAX_TEXT) -> list[str]:
    """Split on paragraph, then line, then word boundaries, never mid-word when avoidable."""
    text = text.strip() or "—"
    parts: list[str] = []
    while len(text) > size:
        cut = max(text.rfind("\n\n", 0, size), text.rfind("\n", 0, size), text.rfind(" ", 0, size))
        cut = cut if cut > size // 2 else size
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    parts.append(text)
    return parts


def held_buttons(held: list[dict]) -> dict | None:
    if not held:
        return None
    rows = [
        [
            {
                "text": f"Allow once: {item['tool']}"[:60],
                "callback_data": f"held:{item['id']}:allow",
            },
            {"text": "Deny", "callback_data": f"held:{item['id']}:deny"},
        ]
        for item in held[:5]
    ]
    return {"inline_keyboard": rows}


_HELD = re.compile(r"^held:([0-9a-f]{32}):(allow|deny)$")


class TelegramBot:
    def __init__(
        self,
        token: str,
        store: BabStore,
        run_turn: RunTurn,
        decide: Decide,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency: int = 4,
        hear: Hear | None = None,
    ):
        self._base = f"{API}/bot{token}"
        self._files = f"{API}/file/bot{token}"
        self.store = store
        self.run_turn = run_turn
        self.decide = decide
        self.hear = hear
        self._client = httpx.AsyncClient(timeout=POLL_SECONDS + 15, transport=transport)
        self._owner_locks: dict[str, asyncio.Lock] = {}
        self._gate = asyncio.Semaphore(concurrency)
        self._me: dict | None = None
        self.running = False
        self.error = ""

    async def close(self) -> None:
        await self._client.aclose()

    async def call(self, method: str, **params: Any) -> Any:
        response = await self._client.post(f"{self._base}/{method}", json=params)
        try:
            body = response.json()
        except ValueError:
            raise TelegramError(response.status_code, "not JSON") from None
        if not body.get("ok"):
            raise TelegramError(response.status_code, str(body.get("description", "")))
        return body.get("result")

    async def me(self) -> dict:
        if self._me is None:
            self._me = await self.call("getMe")
        return self._me

    async def link_url(self, code: str) -> str:
        username = (await self.me()).get("username", "")
        return f"https://t.me/{username}?start={code}"

    async def send(self, chat_id: Any, text: str, buttons: dict | None = None) -> None:
        parts = chunks(text)
        for index, part in enumerate(parts):
            extra = {"reply_markup": buttons} if buttons and index == len(parts) - 1 else {}
            await self.call(
                "sendMessage", chat_id=chat_id, text=part, disable_web_page_preview=True, **extra
            )

    # ── one update ───────────────────────────────────────────────────────

    async def handle(self, update: dict) -> None:
        try:
            if "callback_query" in update:
                await self._on_button(update["callback_query"])
            elif "message" in update:
                await self._on_message(update["message"])
        except Exception:  # noqa: BLE001 - one bad update must not stop the bot
            logger.exception("[BAB] Telegram update failed")

    async def _on_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if chat.get("type") != "private" or sender.get("is_bot"):
            return  # never answer in groups or to other bots
        chat_id: int | str = chat.get("id") or 0
        external = str(sender.get("id", ""))
        text = str(message.get("text") or message.get("caption") or "").strip()
        if text.startswith("/start"):
            code = text.partition(" ")[2].strip()
            if code:
                owner = self.store.redeem(code, CHANNEL, external, str(chat_id))
                await self.send(
                    chat_id,
                    "Linked. Messages here now go to your own MIZAN, and its notices come here."
                    if owner
                    else "That link has expired or was already used. Make a new one in MIZAN → Channels.",
                )
                return
        link = self.store.link(CHANNEL, external)
        if link is None:
            await self.send(
                chat_id,
                "This bot answers only the MIZAN users who linked it. "
                "Open MIZAN → Channels → Link Telegram to link your account.",
            )
            return
        if text == "/new":
            self.store.new_session(CHANNEL, external)
            await self.send(chat_id, "New chat started.")
            return
        if text == "/unlink":
            self.store.unlink(CHANNEL, link["owner_id"])
            await self.send(chat_id, "Unlinked. This bot will no longer answer you.")
            return
        owner = link["owner_id"]
        voice = message.get("voice") or message.get("audio")
        if not text and voice and self.hear is not None:
            try:
                text = await self._heard(owner, link["session_id"], voice)
            except ValueError as exc:
                await self.send(chat_id, str(exc))
                return
            await self.send(chat_id, f"Heard: {text}" if text else "I heard no words in that.")
        if not text:
            await self.send(chat_id, "For now MIZAN reads text messages and voice notes here.")
            return
        if _forwarded(message):
            # Someone else's words: data to work on, never the user's request.
            text = f"Forwarded message:\n```\n{text}\n```"
        lock = self._owner_locks.setdefault(owner, asyncio.Lock())
        async with lock, self._gate:
            await self._typing(chat_id)
            reply, held = await self.run_turn(owner, link["session_id"], text)
        await self.send(chat_id, reply, held_buttons(held))

    async def _heard(self, owner: str, session: str, voice: dict) -> str:
        """Download a voice note (sizes checked before and while reading) and hear it."""
        hear = self.hear
        if hear is None:
            raise ValueError("For now MIZAN reads text messages here.")
        if int(voice.get("file_size") or 0) > MAX_VOICE_BYTES:
            raise ValueError("That voice note is over 2 MB; send a shorter one.")
        if int(voice.get("duration") or 0) > MAX_VOICE_SECONDS:
            raise ValueError("That voice note is over 90 seconds; send a shorter one.")
        found = await self.call("getFile", file_id=voice.get("file_id", ""))
        path = str((found or {}).get("file_path", ""))
        if not path or ".." in path:
            raise ValueError("Telegram did not give that voice note back; try again.")
        audio = bytearray()
        async with self._client.stream("GET", f"{self._files}/{path}") as response:
            if response.status_code != 200:
                raise ValueError("Telegram did not give that voice note back; try again.")
            async for piece in response.aiter_bytes():
                audio += piece
                if len(audio) > MAX_VOICE_BYTES:
                    raise ValueError("That voice note is over 2 MB; send a shorter one.")
        mime = str(voice.get("mime_type") or "audio/ogg")
        return (await hear(owner, session, bytes(audio), mime)).strip()

    async def _on_button(self, query: dict) -> None:
        sender = str((query.get("from") or {}).get("id", ""))
        match = _HELD.match(str(query.get("data", "")))
        link = self.store.link(CHANNEL, sender)
        answer = "That button is not yours."
        if match and link is not None:
            answer = await self.decide(link["owner_id"], match.group(1), match.group(2))
        await self.call("answerCallbackQuery", callback_query_id=query.get("id"), text=answer[:180])
        message = query.get("message") or {}
        if link is not None and message.get("chat", {}).get("id") is not None:
            await self.send(message["chat"]["id"], answer)

    async def _typing(self, chat_id: Any) -> None:
        try:
            await self.call("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:  # noqa: BLE001 - only a courtesy
            pass

    # ── polling ──────────────────────────────────────────────────────────

    async def poll_once(self) -> int:
        offset = int(self.store.get("telegram_offset", "0") or 0)
        updates = await self.call(
            "getUpdates",
            offset=offset,
            timeout=POLL_SECONDS,
            allowed_updates=["message", "callback_query"],
        )
        for update in updates or []:
            # At most once: the position moves before the work, so a crash
            # never answers (and spends on) the same message twice.
            self.store.put("telegram_offset", str(int(update["update_id"]) + 1))
            asyncio.create_task(self.handle(update))
        return len(updates or [])

    async def run(self, stop: asyncio.Event) -> None:
        self.running, self.error = True, ""
        delay = 1.0
        try:
            while not stop.is_set():
                try:
                    await self.poll_once()
                    delay = 1.0
                except TelegramError as exc:
                    if exc.status in {401, 404}:
                        self.error = "The Telegram bot token was rejected"
                        logger.error("[BAB] %s", self.error)
                        return
                    self.error = str(exc)
                except (httpx.HTTPError, ValueError) as exc:
                    self.error = f"{type(exc).__name__}"
                if self.error:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except TimeoutError:
                        pass
                    delay = min(delay * 2, 60.0)
                    self.error = ""
        finally:
            self.running = False


def _forwarded(message: dict) -> bool:
    return any(
        key in message
        for key in (
            "forward_origin",
            "forward_from",
            "forward_date",
            "forward_sender_name",
            "forward_from_chat",
        )
    )
