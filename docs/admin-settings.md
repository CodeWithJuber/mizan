# Admin settings

Administrators manage server settings in **Settings → Developer → System settings**. The
groups (`backend/runtime_settings.py`) are:

- Model: who directs the work (`MIZAN_ORCHESTRATION`), the feature switches
  (debug mode, Ta'lim, Muhasaba, Truth Gate, Ahl al-Dhikr, Amanah, Muraqabah,
  Tajdid, Tadqiq and its audit rate), spending limits, Lisan's models, provider and default model, chat
  effort and output limits, owned-model-only mode, projects per user
- API keys: Anthropic, OpenRouter, OpenAI, the hybrid base model, Hugging Face,
  ARC
- Chat limits
- Learning & memory
- NLP & hybrid
- Connectors & coding: public URL, local MCP servers, private connector hosts,
  project skills
- Channels: Telegram, Discord and Slack tokens, MIZAN's mailbox, WhatsApp, and
  voice input (Sama')

Each setting shows where its value comes from: **Set here**, **From server
.env**, or **Default**.

## How values are stored

- Saved values live in `$MIZAN_DATA_DIR/runtime_settings.json`. API keys and
  tokens in that file are encrypted with the data key
  (`$MIZAN_DATA_DIR/connectors.key`, or the keys in the `MIZAN_CONNECTORS_KEY`
  environment variable: the first seals, all open, the key file still opens
  what it sealed; see `connectors.md`). The data key is never a setting here.
- At startup they are applied after the server's `.env`, so a value set here
  wins.
- **Reset** returns a setting to the server's own `.env` or default.
- Secrets are never sent back to the browser. The page only shows whether one
  is set.
- Every change is a signed Sakk receipt in the `system` chain: which settings,
  by whom, and an HMAC of the new values (never the values themselves).
  Settings, channel tokens and allowlists change only from an administrator's
  signed-in request; no agent tool can change them ([Sakk](sakk.md)).

## When a change takes effect

| Badge | Meaning |
|-------|---------|
| Applies immediately | The next request reads it. |
| Switches the model now | Provider, default model, owned-only mode and the Anthropic, OpenRouter and OpenAI keys: every agent gets the new model at once. |
| Needs a backend restart | Read at startup. The page lists pending restarts. |

The API is `GET` / `PUT /api/settings/runtime`, administrators only.

- `PUT` takes `{"values": {"KEY": value}}`. A `null` value resets that key.
- One invalid value rejects the whole batch, with a message for each field.
- Every change is written to the audit log (keys only, never values).

Infrastructure secrets and paths are deliberately not editable here:

- `SECRET_KEY` and admin credentials
- database paths
- the runner URL and token

They stay in the server's `.env`.
