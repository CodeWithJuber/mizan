# Admin settings

Administrators manage server settings in **Settings → System settings**. The
groups are:

- Model and API keys
- chat limits
- learning and memory
- NLP and hybrid
- connectors and coding
- channel tokens

## How values are stored

- Saved values live in `$MIZAN_DATA_DIR/runtime_settings.json`. API keys and
  tokens in that file are encrypted with the data key
  (`$MIZAN_DATA_DIR/connectors.key`).
- At startup they are applied after the server's `.env`, so a value set here
  wins.
- **Reset** returns a setting to the server's own `.env` or default.
- Secrets are never sent back to the browser. The page only shows whether one
  is set.

## When a change takes effect

| Badge | Meaning |
|-------|---------|
| Applies immediately | The next request reads it. |
| Switches the model now | Provider, default model and API keys: every agent gets the new model at once. |
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
