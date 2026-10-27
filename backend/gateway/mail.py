"""Bab email: talk to your own MIZAN by email.

MIZAN reads its own mailbox (IMAP over TLS) and answers by SMTP. What it
accepts:

- mail only from an address its MIZAN user linked (MIZAN → Channels → Link
  email gives a one-time code; the user sends "link <code>" from their own
  address);
- and only when the sender is proven: the receiving server's own
  ``Authentication-Results`` header (RFC 8601, the topmost one carrying the
  configured authserv-id) must say ``dmarc=pass`` for the From address's
  domain. A From line alone proves nothing, so unproven mail is ignored and
  never answered (no backscatter);
- the user's own words: quoted lines (RFC 3676 ``>``) and the signature after
  ``-- `` are left out; attached messages (``message/rfc822``) are quoted
  data, never the user's request;
- never automatic mail (RFC 3834 ``Auto-Submitted``, ``Precedence: bulk``),
  so two robots cannot answer each other forever.

Each message runs the same turn as the web chat, and the chat is saved so it
also shows in MIZAN. Actions that need a person are held, and the reply says
where to read and allow them: an email can be forged or replayed, so nothing
is ever allowed by email.
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import imaplib
import logging
import os
import re
import smtplib
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid
from html.parser import HTMLParser

from .store import BabStore

logger = logging.getLogger("mizan.bab.mail")

CHANNEL = "email"
POLL_SECONDS = 30
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_TEXT = 20_000

# (owner, session, text) -> (reply, held actions [{id, tool, reason, ...}])
RunTurn = Callable[[str, str, str], Awaitable[tuple[str, list[dict]]]]


@dataclass(frozen=True)
class MailConfig:
    address: str
    username: str
    password: str
    imap_host: str
    smtp_host: str
    authserv: str
    imap_port: int = 993
    smtp_port: int = 465
    public_url: str = ""

    @classmethod
    def from_env(cls) -> MailConfig | None:
        """The mailbox from settings, or None when any required part is missing."""
        get = os.getenv
        address = get("MIZAN_EMAIL_ADDRESS", "").strip()
        values = {
            "address": address,
            "username": get("MIZAN_EMAIL_USERNAME", "").strip() or address,
            "password": get("MIZAN_EMAIL_PASSWORD", ""),
            "imap_host": get("MIZAN_EMAIL_IMAP_HOST", "").strip(),
            "smtp_host": get("MIZAN_EMAIL_SMTP_HOST", "").strip(),
            "authserv": get("MIZAN_EMAIL_AUTHSERV", "").strip(),
        }
        if not all(values.values()):
            return None
        return cls(
            **values,
            imap_port=int(get("MIZAN_EMAIL_IMAP_PORT", "993") or 993),
            smtp_port=int(get("MIZAN_EMAIL_SMTP_PORT", "465") or 465),
            public_url=get("MIZAN_PUBLIC_URL", "").rstrip("/"),
        )


# ── reading one message ──────────────────────────────────────────────────


def parse(raw: bytes) -> EmailMessage:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(message, EmailMessage)
    return message


_DMARC = re.compile(r"\bdmarc\s*=\s*(\w+)[^;]*?\bheader\.from\s*=\s*\"?([^\s;\"]+)", re.I)


def authenticated_sender(message: EmailMessage, authserv: str) -> str | None:
    """The From address, only when the receiving server proved it.

    Only the topmost ``Authentication-Results`` header carrying our server's
    authserv-id counts: the receiving server adds its own above every header
    the sender wrote (RFC 8601 §5), so a copy forged by the sender is never
    the first one."""
    senders = getaddresses([str(value) for value in message.get_all("From", [])])
    if len(senders) != 1 or "@" not in senders[0][1]:
        return None
    address = senders[0][1].strip().lower()
    domain = address.rpartition("@")[2]
    for header in message.get_all("Authentication-Results", []):
        server, _, results = str(header).partition(";")
        if not server.split() or server.split()[0].lower() != authserv.lower():
            continue
        found = _DMARC.search(results)
        if found and found.group(1).lower() == "pass" and found.group(2).lower() == domain:
            return address
        return None
    return None


def automatic(message: EmailMessage) -> bool:
    """Mail a machine sent (RFC 3834), which is never answered."""
    submitted = str(message.get("Auto-Submitted", "no")).strip().lower()
    precedence = str(message.get("Precedence", "")).strip().lower()
    return submitted not in {"", "no"} or precedence in {"bulk", "list", "junk"}


class _Text(HTMLParser):
    """The text of an HTML part, for mail with no plain-text part."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _content(part: EmailMessage) -> str:
    try:
        text = str(part.get_content())
    except (LookupError, ValueError):
        return ""
    if part.get_content_type() == "text/html":
        reader = _Text()
        reader.feed(text)
        text = "".join(reader.parts)
    return text


def own_words(text: str) -> str:
    """The writer's own words: quoted lines and the signature left out.

    RFC 3676 marks a quoted line with ``>`` and a signature with a ``-- ``
    line. The line just before the first quote, when it ends with ":", is the
    reply's attribution ("On … wrote:") and goes with the quote."""
    kept: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.rstrip() == "--":
            break
        if line.lstrip().startswith(">"):
            if kept and kept[-1].rstrip().endswith(":"):
                kept.pop()
            break
        kept.append(line)
    return "\n".join(kept).strip()


def request_of(message: EmailMessage) -> str:
    """What the user asks: their own words, then any attached message as data."""
    body = message.get_body(preferencelist=("plain", "html"))
    words = own_words(_content(body)) if isinstance(body, EmailMessage) else ""
    subject = str(message.get("Subject", "")).strip()
    if not words and subject:
        words = re.sub(r"^(?:(?:re|fwd?|aw)\s*:\s*)+", "", subject, flags=re.I)
    attached: list[str] = []
    fence = "`" * 3
    for part in message.walk():
        if part.get_content_type() == "message/rfc822":
            inner = part.get_content()
            if isinstance(inner, EmailMessage):
                inner_body = inner.get_body(preferencelist=("plain", "html"))
                if isinstance(inner_body, EmailMessage):
                    attached.append(_content(inner_body).strip().replace(fence, "'" * 3))
    for quoted in attached:
        # Someone else's words: data to work on, never the user's request.
        words += f"\n\nForwarded message:\n{fence}\n{quoted}\n{fence}"
    return words.strip()[:MAX_TEXT]


_LINK = re.compile(r"\blink\s+([A-Za-z0-9_-]{16,64})\b", re.I)


def link_code(message: EmailMessage) -> str | None:
    """The one-time code in a "link <code>" message (subject or own words)."""
    body = message.get_body(preferencelist=("plain", "html"))
    text = f"{message.get('Subject', '')}\n{own_words(_content(body)) if isinstance(body, EmailMessage) else ''}"
    found = _LINK.search(text)
    return found.group(1) if found else None


# ── writing the answer ───────────────────────────────────────────────────


def reply_to(message: EmailMessage, sender: str, config: MailConfig, text: str) -> EmailMessage:
    answer = EmailMessage()
    subject = str(message.get("Subject", "")).strip() or "MIZAN"
    answer["Subject"] = subject if re.match(r"^re\s*:", subject, re.I) else f"Re: {subject}"
    answer["From"] = config.address
    answer["To"] = sender
    answer["Message-ID"] = make_msgid(domain=config.address.rpartition("@")[2])
    # RFC 3834: an answer to a person's message, so automatic mail is never sent back.
    answer["Auto-Submitted"] = "auto-replied"
    original = str(message.get("Message-ID", "")).strip()
    if original:
        answer["In-Reply-To"] = original
        answer["References"] = f"{message.get('References', '')} {original}".strip()
    answer.set_content(text)
    return answer


def held_note(held: list[dict], public_url: str) -> str:
    """Held actions are never allowed by email: say where to read and allow them."""
    if not held:
        return ""
    names = ", ".join(sorted({str(item.get("tool", "?")) for item in held}))
    where = f"{public_url}/" if public_url else "MIZAN"
    return (
        f"\n\nMIZAN held {len(held)} action(s) for you ({names}). Nothing is allowed by "
        f"email: open Held actions in {where} to read exactly what each would do and allow it."
    )


# ── the mailbox ──────────────────────────────────────────────────────────


class Mailbox:
    """MIZAN's own mailbox: new messages by UID, and sending. Blocking calls,
    run in a thread by the bot."""

    def __init__(self, config: MailConfig):
        self.config = config

    def fetch_after(self, last_uid: int, validity: str) -> tuple[str, int, list[tuple[int, bytes]]]:
        """(UIDVALIDITY, the highest UID there, [(uid, message)]) for up to 20
        messages after ``last_uid``; when the mailbox's UIDVALIDITY changed,
        everything there is new."""
        context = ssl.create_default_context()
        with imaplib.IMAP4_SSL(
            self.config.imap_host, self.config.imap_port, ssl_context=context
        ) as imap:
            imap.login(self.config.username, self.config.password)
            status, data = imap.select("INBOX", readonly=True)
            if status != "OK":
                raise imaplib.IMAP4.error(f"INBOX: {data!r}")
            current = _uidvalidity(imap)
            start = last_uid + 1 if current == validity else 1
            status, found = imap.uid("SEARCH", f"UID {start}:*")
            uids = sorted(int(uid) for uid in (found[0] or b"").split() if int(uid) >= start)
            highest = uids[-1] if uids else last_uid
            if not validity:
                return current, highest, []  # first start: nothing is read
            messages = []
            for uid in uids[:20]:
                status, sized = imap.uid("FETCH", str(uid), "(RFC822.SIZE)")
                size = re.search(rb"RFC822\.SIZE (\d+)", (sized[0] or b"") if sized else b"")
                if size and int(size.group(1)) > MAX_MESSAGE_BYTES:
                    messages.append((uid, b""))  # too large: skipped, never read
                    continue
                status, body = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                raw = next((item[1] for item in body if isinstance(item, tuple)), b"")
                messages.append((uid, bytes(raw)))
            return current, highest, messages

    def send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.config.smtp_port == 465:
            with smtplib.SMTP_SSL(self.config.smtp_host, 465, context=context, timeout=30) as smtp:
                smtp.login(self.config.username, self.config.password)
                smtp.send_message(message)
            return
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(self.config.username, self.config.password)
            smtp.send_message(message)


def _uidvalidity(imap: imaplib.IMAP4) -> str:
    status, data = imap.response("UIDVALIDITY")
    return str((data[0] or b"").decode() if data and data[0] else "")


# ── the bot ──────────────────────────────────────────────────────────────


class MailBot:
    def __init__(
        self,
        config: MailConfig,
        store: BabStore,
        run_turn: RunTurn,
        *,
        mailbox: Mailbox | None = None,
        concurrency: int = 4,
    ):
        self.config = config
        self.store = store
        self.run_turn = run_turn
        self.mailbox = mailbox or Mailbox(config)
        self._owner_locks: dict[str, asyncio.Lock] = {}
        self._gate = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task] = set()
        self.running = False
        self.error = ""

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self.mailbox.send, message)

    async def handle(self, raw: bytes) -> None:
        """One message from the mailbox."""
        if not raw:
            return
        message = parse(raw)
        if automatic(message):
            return
        sender = authenticated_sender(message, self.config.authserv)
        if sender is None or sender == self.config.address.lower():
            return  # unproven or our own: never answered
        code = link_code(message)
        if code is not None:
            owner = self.store.redeem(code, CHANNEL, sender, sender)
            if owner is not None:
                await self.send(
                    reply_to(
                        message,
                        sender,
                        self.config,
                        "Linked. Mail from this address now goes to your own MIZAN, and its "
                        "answers come back here.",
                    )
                )
                return
        link = self.store.link(CHANNEL, sender)
        if link is None:
            return  # not linked: ignored, so the mailbox cannot be used to probe accounts
        text = request_of(message)
        if not text:
            return
        owner = str(link["owner_id"])
        lock = self._owner_locks.setdefault(owner, asyncio.Lock())
        async with lock, self._gate:
            reply, held = await self.run_turn(owner, str(link["session_id"]), text)
        await self.send(
            reply_to(message, sender, self.config, reply + held_note(held, self.config.public_url))
        )

    async def poll_once(self) -> int:
        """Read what arrived since the last poll and answer each, in order of arrival."""
        validity = self.store.get("email:uidvalidity")
        last = int(self.store.get("email:last_uid", "0") or 0)
        current, highest, messages = await asyncio.to_thread(
            self.mailbox.fetch_after, last, validity
        )
        if not validity:
            # First start: what was already in the mailbox is not answered.
            self.store.put("email:uidvalidity", current)
            self.store.put("email:last_uid", str(highest))
            return 0
        if current != validity:
            self.store.put("email:uidvalidity", current)
            last = 0
        for uid, raw in messages:
            if uid <= last:
                continue
            self.store.put("email:last_uid", str(uid))
            task = asyncio.create_task(self._handle_logged(raw))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return len(messages)

    async def _handle_logged(self, raw: bytes) -> None:
        try:
            await self.handle(raw)
        except Exception:  # noqa: BLE001 - one bad message must not stop the mailbox
            logger.exception("Email message not answered")

    async def run(self, stop: asyncio.Event) -> None:
        self.running = True
        failures = 0
        while not stop.is_set():
            try:
                await self.poll_once()
                failures, self.error = 0, ""
            except (OSError, imaplib.IMAP4.error, smtplib.SMTPException) as exc:
                failures += 1
                self.error = f"{type(exc).__name__}: {str(exc)[:160]}"
                logger.warning("Email poll failed (%s)", self.error)
                if isinstance(exc, imaplib.IMAP4.error) and "auth" in str(exc).lower():
                    self.running = False
                    return  # wrong credentials: stop until the settings change
            delay = POLL_SECONDS * min(2**failures, 10)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass
        self.running = False
