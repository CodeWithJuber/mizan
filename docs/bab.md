# Bab (باب): your own MIZAN from Telegram, by email and on your devices

When an administrator saves a Telegram bot token, MIZAN runs the bot itself. It uses long polling over the Bot API (`httpx`), so no public webhook is needed. Each user links their own Telegram account. The code is in `backend/gateway/telegram.py` and `backend/gateway/store.py`.

## Turning it on (administrator)

1. In Telegram, ask @BotFather for a new bot and copy its token.
2. In MIZAN → Settings → System settings, save it as `TELEGRAM_BOT_TOKEN`. It is stored sealed, like other secrets. Restart the backend.
3. Channels then shows Telegram as **Connected**. `MIZAN_TELEGRAM=off` keeps the bot stopped even with a token.

## Linking (each user)

1. MIZAN → Channels → **Link Telegram** gives a one-time link: `t.me/<bot>?start=<code>`. The code is 128 random bits. Only its SHA-256 is kept. It works once, for 10 minutes.
2. Open the link on your phone and press **Start**. The bot replies "Linked".
3. A user has one linked account. Linking again replaces it. `/unlink` in Telegram, or **Unlink** in MIZAN, removes it.

## What the bot does

- **Who it answers:**
  - only private chats, and only a linked account;
  - a group, another bot, or an account that is not linked never reaches MIZAN;
  - an unlinked account is told how to link.
- **The turn:** each message runs the same turn as the web chat: your own agent, your gates, Tadbir, Iqtisad. The chat is saved to MIZAN, where it shows in History. `/new` starts a new chat.
- **Voice notes:** heard on MIZAN's own server ([Sama'](sama.md)), shown back as "Heard: …" and then answered like text. A forwarded voice note is fenced as data like forwarded text.
- **Forwarded text:** treated as quoted data inside a fence, never as your request (the same rule as pasted text, [Amanah](amanah.md)).
- **Actions:** no one can answer an approval prompt in the middle of a run, so actions that need a person are **held** (the same as for watchers, [agentic coding](agentic-coding.md)). Each comes back as its own card after the reply: the tool, why, **the exact parameters** and their fingerprint (the first 12 characters of their SHA-256), with **Allow once / Deny**. The Allow button carries the fingerprint, so a press allows exactly what the card showed; a parameter list too long for a card gets only Deny, and is allowed from Held actions in MIZAN, where it can be read whole. A button works only for the account linked to that action's owner, and only once. Links in replies are sent without previews.
- **Watchers:** Muraqabah notices are posted to MIZAN and also sent to your Telegram, with buttons for anything held.
- **Long replies:** split at paragraph, line or word boundaries to fit Telegram's 4,096-character limit.
- **Limits:**
  - one message at a time per user, and at most 4 users' turns at once;
  - updates are processed at most once: the poll position is saved before the work, so a restart never answers, and pays for, the same message twice.

## API

| Route | Purpose |
|---|---|
| `GET /api/bab/telegram` | Whether the bot runs, its username, and whether you are linked |
| `POST /api/bab/telegram/link` | A one-time link for your account |
| `DELETE /api/bab/telegram/link` | Unlink your account |

| `GET /api/bab/email` | Whether MIZAN reads its mailbox, its address, and your linked address |
| `POST /api/bab/email/link` | A one-time code: mail `link <code>` to MIZAN from your own address |
| `DELETE /api/bab/email/link` | Unlink your address |

Links, codes and the poll positions live in `$MIZAN_DATA_DIR/bab.db`.

## Email

MIZAN gets its own mailbox and answers mail from the address each user links
(`backend/gateway/mail.py`, standard library only: IMAP over TLS, SMTP).

- **Turning it on (administrator):** System settings → Channels: MIZAN's
  address, an app password for it, the IMAP and SMTP servers, and the
  receiving server's name as it writes it first in `Authentication-Results`
  (Gmail: `mx.google.com`). MIZAN reads the inbox every 30 seconds,
  read-only: nothing is marked, moved or deleted. On first start, mail
  already there is not answered.
- **Linking (each user):** MIZAN → Channels → **Link email** gives a one-time
  code (10 minutes). Send a mail from your own address to MIZAN's with the
  subject `link <code>`; MIZAN replies when it is linked.
- **Who it answers:** only a linked address, and only when the sender is
  proven. A From line proves nothing, so the receiving server's own
  `Authentication-Results` header (RFC 8601; the topmost one carrying its
  name, which a sender cannot put above it) must say `dmarc=pass` for the
  From address's domain. Unproven, unlinked and automatic mail (RFC 3834
  `Auto-Submitted`, `Precedence: bulk`) is ignored and never answered, so
  nothing bounces to forged senders and two robots never answer each other.
- **What is read:** your own words. Quoted lines (`>`, with the "On … wrote:"
  line before them) and the signature after `-- ` are left out. An attached
  message (`message/rfc822`) is fenced as quoted data, never as your request.
  HTML-only mail is read as its text. Messages over 1 MB are skipped.
- **The turn:** the same as the web chat's; the chat shows in MIZAN. The
  answer goes back as a reply in the same thread (`In-Reply-To`,
  `References`), marked `Auto-Submitted: auto-replied`.
- **Actions are never allowed by email.** Mail can be forged or replayed, so
  held actions are named in the reply with a pointer to Held actions in MIZAN,
  where each shows exactly what it would do.

## Notifications on your devices (Web Push)

MIZAN is installable as an app (`manifest.webmanifest`, icons). It sends standard Web Push to every device where you turned notifications on, even when the app is closed. It uses VAPID (RFC 8292) and end-to-end encrypted payloads (RFC 8291), sent with `pywebpush` (MPL-2.0). The code is in `backend/gateway/push.py`.

- **Turning it on:** MIZAN → Channels → **Notifications on this device** → Turn on. The browser asks for permission, and MIZAN keeps the subscription for this device only. **Test** sends one notice. On iPhone, add MIZAN to the Home Screen first.
- **What sends:** watcher notices, including the ones that hold an action for you.
- **The lock screen:** shows only "MIZAN has a new notice". To show the text, set the chat preference `push_preview: on`. Pressing a notice opens the watcher chat.
- **Where MIZAN sends:**
  - only to known push services over HTTPS: Google FCM, Mozilla, Apple, Microsoft WNS;
  - a subscription to any other address is refused, so MIZAN never posts to an address a browser chose;
  - a device the push service reports gone (404/410) is removed.
- **Signing key:** MIZAN makes its own key on first use. It is sealed with the data key (`connectors.key`) and kept in `bab.db`.
- **The service worker** (`/sw.js`) only shows notifications. It caches nothing and handles no requests, so a deploy is never served stale. nginx serves it and the manifest with `no-cache`.

| Route | Purpose |
|---|---|
| `GET /api/bab/push/key` | MIZAN's public key to subscribe with, and how many of your devices are on |
| `POST /api/bab/push/subscription` | Turn notifications on for this device |
| `DELETE /api/bab/push/subscription?endpoint=` | Turn them off |
| `POST /api/bab/push/test` | Send yourself a test notice |
