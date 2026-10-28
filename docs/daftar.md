# Daftar: what MIZAN keeps about you

Personal agents remember things about their users. Few let the user see all of it, say where each memory came from, change it, or take it to another system. Daftar (`backend/memory/daftar.py`) is one ledger of everything MIZAN keeps about a user, on the **Memory** page.

## What is in the ledger

| Kind | What it is | Where it comes from | You can |
|---|---|---|---|
| **Note** | Something to remember | You added it, imported it, a knowledge source, or you said "remember that …" in a chat (kept in your own words, tied to that chat) | Edit, set an expiry, forget |
| **Preference** | How MIZAN should answer (language, greeting, custom instructions, self-review) | The chat you set it in | Edit, forget |
| **Chat summary** | MIZAN's running summary of a long chat | That chat | Read (it follows the chat) |
| **Learned** | Phrasings, verified programs and repair lessons from your verified work | Your verified requests | Manage in **Majlis → Learning** |

Every entry shows:
- where it came from (a chat by its title, "you added it", "imported", or a knowledge source)
- when it was made
- when MIZAN last used it, or "not used yet"
- for notes, when it will be forgotten

"Last used" is written whenever MIZAN recalls the note for an answer.

## Your words from other chats

When the model answers, it may be shown up to five things you wrote in your other chats, as your statements and not as facts. Only statements about the request are chosen: its distinctive words are the ones your earlier messages use that carry more information than an average word of general language (never "what", "the", "hai"), and a statement is shown only when it holds more than half of their information. A request that shares no such word with your chats recalls nothing. Messages sent as `stateless` (tests) are never recalled, and neither is a message Amanah reads as an instruction aimed at the AI. The answer then says so under it: **Used 2 lines from other chats**, which opens to the lines and their dates. MIZAN's own recipes (Quran, hadith, calculations, programs) do not use them. To stop this, set the chat preference `cross_chat_recall: off`. Deleting a chat removes its words from what can be recalled ([Mahw](mahw.md)).

## Privacy

- **Notes are kept per user.** A user's notes go to that user's own memory database (`$MIZAN_DATA_DIR/private/<hash>/memory.db`), the same one their agents recall from. One user never sees another's.
- **Administrators** keep using the main store, which the admin-only `/api/memory/*` routes also serve.

## Forgetting

- **One entry:** press **Forget**.
- **A topic:**
  1. Type it (for example "my old job").
  2. Press **Show what would go** to see every note and preference about it (BM25 over their words).
  3. Press **Forget these N**. Nothing is removed before you confirm.
- **Expiry:** a note can be given one ("forget after 1 week"). An expired note is never recalled, and it is removed the next time the ledger is read.
- **Everywhere:** a forgotten note is also removed from its search vector and from the pathway network, which is rebuilt from the notes you keep. You get a receipt saying what was removed and whether any copy was found afterwards ([Mahw](mahw.md)).
- **A whole chat:** delete it from the chat's History list ([Mahw](mahw.md)).

## Taking it with you

- **Export Markdown:** a readable list grouped by kind, with provenance for each entry.
- **Export JSON:** a portable `mizan-daftar/1` file with notes and preferences.
- **Import:** brings notes and preferences into another MIZAN account. Imported notes are marked "imported". An entry that carries instructions aimed at the AI is skipped ([Amanah](amanah.md)), so an import cannot plant a prompt injection in memory.

## API

All routes act on the signed-in user's own ledger.

| Route | Purpose |
|---|---|
| `GET /api/daftar?query=&kind=` | The ledger and counts per kind |
| `POST /api/daftar` | Add a note (`content`, `tags`, `expires`) |
| `PATCH /api/daftar/{id}` | Edit a note (`content`, `tags`, `expires`) or a preference (`content`) |
| `POST /api/daftar/forget` | `{ids}` to forget entries; `{topic}` to preview; `{topic, confirm: true}` to forget the topic. Forgetting notes returns Mahw's `receipt` |
| `GET /api/daftar/receipts` | Receipts of what you asked MIZAN to forget, newest first |
| `GET /api/daftar/export?format=md\|json` | Download the ledger |
| `POST /api/daftar/import` | Import a `mizan-daftar/1` JSON export |

## Storage

The `memories` table gained `source`, `created`, `last_used` and `expires` columns, and `chat_preferences` gained `session_id`. They are added in place when an older database opens; old rows show "saved before MIZAN kept provenance".
