# Testing MIZAN through its API

Everything the web app does goes through MIZAN's HTTP API, so you can test it
with `curl`, Postman, a script, or `scripts/mizan_client.py` (standard library
only).

The base URL is your server, for example `https://your-mizan.example`; every
route below starts with `/api`. FastAPI's own `/docs` page is not served
through the production proxy. This page explains the main routes;
**every** route (292, with who may call it) is in
[api-reference.md](api-reference.md), and [openapi.json](openapi.json) has
them all with their request bodies: import it into Postman, Insomnia or
Bruno, set the server URL, and use a Bearer token or `X-API-Key`.

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

A token lasts 24 hours.
- `GET /api/auth/me` says whose it is, its roles, and when it was issued and expires.
- `POST /api/auth/logout` ends it at once.
- `POST /api/auth/logout {"everywhere": true}` also ends every other token the
  account was given before now. Use it when a token may have leaked.

Revocations are kept on disk, so a restart never brings a revoked token back.

**Limits.** Each limit answers 429 with `Retry-After`, `RateLimit-Limit` and
`RateLimit-Remaining`:
- failed sign-ins: 5 a minute per client address and per account name (a
  successful sign-in costs nothing);
- chat messages: 30 a minute per user, bursts of 10;
- public routes: per client address.

**Other guarantees.**
- A request with no valid credential gets 401 before its body is read.
- Cross-origin responses carry `Access-Control-Allow-Credentials` only together
  with a matched, echoed origin.

Some routes need an admin account: the AGI test, every user's spending, and
system settings. Debug mode follows `MIZAN_DEBUG_MODE`.

## Errors, docs and lists

- **Errors.** Every error has one shape. `detail` is what FastAPI always sent;
  `error` is a stable object with `code` (`unauthenticated`, `forbidden`,
  `not_found`, `invalid_request`, `rate_limited`, `unavailable`, `internal`, …),
  `status` and `message`.
- **Docs.** The live OpenAPI is public at `/api/openapi.json`, with a browsable
  page at `/api/docs`. Who may call each route is in
  [api-reference.md](api-reference.md).
- **Lists.** `GET /api/agents?detail=false&limit=20&offset=0` gives each agent
  in a few fields, a page at a time. `GET /api/status?detail=false` does the
  same for the dashboard. The full profiles run to several kilobytes per agent.

## Chat

**`POST /api/chat/stream`** sends one message and returns the answer as
Server-Sent Events. Body:

| Field | Required | Meaning |
|---|---|---|
| `session_id` | yes | Any id you choose (letters, digits, `_` and `-`, at most 100); the same id continues the same chat |
| `request_id` | no | A fresh UUID per message. Sending the same id again answers 409 instead of running twice, so after a dropped connection read `GET /api/chat/{session_id}/run-state` rather than resending. If you leave it out, MIZAN makes one and returns it in every event; a resend is then a new request |
| `content` | yes | The message |
| `permission_mode` | no | `auto`, `auto_edits`, `ask` or `plan` |
| `timezone` | no | An IANA name such as `Asia/Karachi`, for dates and prayer times |
| `workspace_id` | no | A coding project to work in |
| `images` | no | Up to 4 images, each `{"media_type": "image/png", "data": "<base64>"}`, at most 10 MB; see [Basar](basar.md) |
| `thinking` | no | `true` adds the agents' internal telemetry: `thinking` events, and `cognitive` and `thinking_trace` in `chat_complete`. Without it the stream carries the answer, its status and its receipts |
| `stateless` | no | `true` for an evaluation or test session (the no-memory flag). MIZAN recalls nothing from your other chats, learns nothing from the run, keeps nothing as a training candidate and saves no note ("remember this" is answered as not kept). The chat's own messages are still saved, marked so that no later chat recalls them. Reported in `usage.memory`. The AGI test and debug comparisons are always stateless |

```bash
curl -N $MIZAN/api/chat/stream -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"test-1\",\"request_id\":\"$(python3 -c 'import uuid;print(uuid.uuid4())')\",\"content\":\"What is 17*23?\"}"
```

Events arrive in this order:

- `status` and `typing`: progress.
- `todo`: MIZAN's plan steps.
- `thinking`: only when the request has `thinking: true`.
- `chat_stream`: the answer, in its `chunk` field.
- `chat_complete` or `error`. The closing event holds:
  - `response`: the full answer. It equals the `chat_stream` chunks joined,
    with two exceptions: when the Truth Gate corrected or removed a claim
    (`usage.sidq` lists each change), or when a tool's output carried an
    instruction and its planted words were taken out of the answer
    (`usage.amanah.removed_from_answer`). Notes
    about the answer (what sources said, a ruling question's referral to a
    scholar in `usage.ahl.referral`) are never added to the text;
  - `usage`: model, tokens and cost, plus `isnad` (each claim's grade), `sidq`
    (Truth Gate), `ahl` (what sources said), `amanah` (injections removed) and
    `orchestrator` (`mizan` when MIZAN did the work itself);
    each of these is present only when it applies (no claims to grade, no
    gate run, no source asked, nothing injected), so read them as optional;
  - `task_verified` and `completion_status`.

**`POST /api/chat`** takes only `session_id`, `content`, `timezone` and the
optional `agent_id` and `model_override`: no `request_id`, images, project,
permission mode, `thinking` or `stateless`. It answers
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
| `GET /api/chat/held`, `POST /api/chat/held/{id}` | Actions an unattended run (a watcher, a Telegram, email or WhatsApp message) held for you |

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
| `POST /api/imtihan/runs/{id}/publish` | Publish its aggregate report on the public reliability page (`DELETE` takes it down) |
| `GET`/`POST /api/imtihan/panel`, `DELETE /api/imtihan/panel/{person}` | The human panel: its items, answers given under a pseudonym, and erasing a person's answers |
| `POST`/`GET /api/imtihan/panel/invites`, `DELETE /api/imtihan/panel/invites/{id}` | Invite links (`/panel/<code>`) for one person to answer alone with no account; the code is shown once |
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
| `GET /api/public/reliability`, `GET /api/public/reliability/{run_id}` | The published AGI-test scorecards, and one of them |
| `GET /api/public/sakk` | The signed checkpoints of every receipt chain (the 30 latest), with the public key |
| `GET`/`POST /api/public/panel/{code}` | A human-panel invite: the items to answer, and the answers (the first answer to an item is final; no verdict is returned) |
| `GET`/`POST /api/public/whatsapp` | Meta's WhatsApp webhook; events must be signed with the app secret ([Bab](bab.md)) |
| `POST /api/v1/root-analyze`, `/api/v1/tokenize`, `/api/v1/q28-features` | The public versioned Arabic APIs ([Sarf](sarf.md) answers root-analyze) |

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
