# Testing MIZAN through its API

Everything the web app does goes through MIZAN's HTTP API, so you can test it
with `curl`, Postman, a script, or `scripts/mizan_client.py` (standard library
only).

The base URL is your server, for example `https://your-mizan.example`; every
route below starts with `/api`. FastAPI's own `/docs` page is not served
through the production proxy, so this page lists the routes.

## Sign in

Each call needs one of two credentials:

- **Token.** `Authorization: Bearer <token>`. Get one from
  `POST /api/auth/login` with `{"username": "...", "password": "..."}`; the
  response is `{"token", "user_id", "username", "roles"}`.
- **API key.** `X-API-Key: <key>`. Create one with `POST /api/auth/api-key`
  while signed in.

```bash
export MIZAN=https://your-mizan.example
TOKEN=$(curl -s $MIZAN/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"you","password":"…"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')
```

Some routes need an admin account: the AGI test, every user's spending, and
system settings. Debug mode follows `MIZAN_DEBUG_MODE`.

## Chat

**`POST /api/chat/stream`** sends one message and returns the answer as
Server-Sent Events. Body:

| Field | Required | Meaning |
|---|---|---|
| `session_id` | yes | Any id you choose; the same id continues the same chat |
| `request_id` | yes | A fresh UUID per message. Never reuse it for a retry |
| `content` | yes | The message |
| `permission_mode` | no | `auto`, `auto_edits`, `ask` or `plan` |
| `timezone` | no | An IANA name such as `Asia/Karachi`, for dates and prayer times |
| `workspace_id` | no | A coding project to work in |
| `images` | no | Up to 4 images, each `{"media_type": "image/png", "data": "<base64>"}`, at most 10 MB; see [Basar](basar.md) |

```bash
curl -N $MIZAN/api/chat/stream -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"test-1\",\"request_id\":\"$(python3 -c 'import uuid;print(uuid.uuid4())')\",\"content\":\"What is 17*23?\"}"
```

Events arrive in this order:

- `status` and `typing`: progress.
- `todo`: MIZAN's plan steps.
- `thinking`.
- `chat_stream`: the answer, in its `chunk` field.
- `chat_complete` or `error`. The closing event holds:
  - `response`: the full answer;
  - `usage`: model, tokens and cost, plus `isnad` (each claim's grade), `sidq`
    (Truth Gate), `ahl` (what sources said), `amanah` (injections removed) and
    `orchestrator` (`mizan` when MIZAN did the work itself);
  - `task_verified` and `completion_status`.

**`POST /api/chat`** takes the same body without `request_id`. It answers
`{"status": "processing"}` at once; the answer is saved to the chat and also
pushed over the WebSocket `/ws/{client_id}`.

| Route | What it does |
|---|---|
| `GET /api/chat/{session_id}` | The chat's messages, newest page; `?before=<id>` pages back |
| `GET /api/chat/sessions/list` | Your chats |
| `GET /api/chat/{session_id}/run-state` | Whether an answer is still being written |
| `POST /api/chat/{session_id}/stop` | Stop it |
| `DELETE /api/chat/{session_id}` | Erase the chat everywhere (Mahw) and get a receipt |
| `GET /api/chat/approvals`, `POST /api/chat/approvals/{id}` | Actions waiting for your Allow/Deny |
| `GET /api/chat/held`, `POST /api/chat/held/{id}` | Actions a watcher held while you were away |

## Base model against MIZAN (debug mode)

**`POST /api/debug/compare`** with `{"prompt": "...", "session_id": optional, "permission_mode": "auto"|"plan"}`.
It sends one message to the base model alone and to MIZAN, and returns both
answers with:
- MIZAN's trace: understanding, plan, tools, `lisan.*` prompts, model usage;
- the checks on both answers: unsupported numbers, unbacked actions, Quran and
  hadith quote fidelity;
- Isnad grades for both arms.

`GET /api/debug/runs` and `GET /api/debug/runs/{id}` list earlier runs.

```bash
curl $MIZAN/api/debug/compare -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"prompt":"13, 26, 64, 118, 274, ?, 628, 778, 1126 find the missing number"}'
```

## AGI test (admin)

| Route | What it does |
|---|---|
| `GET /api/imtihan/tasks` | The blocks and their tasks |
| `POST /api/imtihan/run` | Start a run in the background. Body: `{"blocks": ["ibrah", "quran"] or null for all, "repeats": 1-3}` |
| `GET /api/imtihan/runs`, `GET /api/imtihan/runs/{id}` | Progress and the report: Wilson intervals, pass^k, calibration, the index |
| `POST /api/imtihan/runs/{id}/cancel` | Stop a run |
| `POST /api/imtihan/runs/{id}/publish` | Publish its aggregate report on the public reliability page |
| `GET`/`POST /api/imtihan/arc3` | The official ARC-AGI-3 games, when `ARC_API_KEY` is set |

## Proofs and your data

| Route | What it does |
|---|---|
| `GET /api/sakk` | Your signed action receipts |
| `GET /api/sakk/verify` | Check your receipt chain |
| `GET /api/sakk/export` | Export it for `scripts/verify_sakk.py`, which checks it offline |
| `GET /api/daftar`, `POST /api/daftar` | Your memory ledger; add a note |
| `GET /api/daftar/receipts` | Receipts of what was erased |
| `GET /api/iqtisad` | Your spending and limits |
| `GET /api/voice`, `POST /api/voice/transcribe` | Speech to text on MIZAN's server (multipart `file`) |
| `GET /api/media/{sha}` | One of your own chat images |

## Public routes (no sign-in)

| Route | What it does |
|---|---|
| `GET /api/health` | Status and version |
| `GET /api/public/reliability` | The published AGI-test scorecard |
| `GET /api/public/sakk` | The daily signed root of every receipt chain, with the public key |

## The client script

```bash
export MIZAN_URL=https://your-mizan.example
export MIZAN_TOKEN=…            # or MIZAN_API_KEY=…
python scripts/mizan_client.py chat "Saturn ka sabse bada chand kaunsa hai?"
python scripts/mizan_client.py chat "Design an HTML page for this and preview it" --image design.png
python scripts/mizan_client.py compare "Who built the Taj Mahal?"
python scripts/mizan_client.py imtihan-run --blocks ibrah
python scripts/mizan_client.py verify
```

`python scripts/mizan_client.py --help` lists every command.
