# Bab (باب): your own MIZAN from Telegram

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
- **Forwarded text:** treated as quoted data inside a fence, never as your request (the same rule as pasted text, [Amanah](amanah.md)).
- **Actions:** no one can answer an approval prompt in the middle of a run, so actions that need a person are **held** (the same as for watchers, [agentic coding](agentic-coding.md)). They come back as **Allow once / Deny** buttons under the reply. A button works only for the account linked to that action's owner, and only once.
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

Links, codes and the poll position live in `$MIZAN_DATA_DIR/bab.db`.
