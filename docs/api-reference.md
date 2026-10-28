# MIZAN API reference

Every route the backend serves, generated from the app (`python scripts/api_reference.py`; do not edit by hand). How to sign in, the chat stream's events and worked examples are in [api-testing.md](api-testing.md). The same routes with every request body are in [openapi.json](openapi.json): import it into Postman, Insomnia or Bruno, set the server URL and a Bearer token or `X-API-Key`.

**Who**: `public` needs nothing; `user` needs a token or API key; `admin` needs an administrator; `user (more for admin)` serves every user and shows an administrator more; `debug mode` follows `MIZAN_DEBUG_MODE` (admins, users or off); `capability URL` is a dev-server preview whose link is the credential. The summaries come from each handler's docstring, or its name when it has none.

292 routes in 60 areas.

Areas: [agent-skills](#agent-skills) · [agents](#agents) · [artifacts](#artifacts) · [auth](#auth) · [automation](#automation) · [bab](#bab) · [channels](#channels) · [chat](#chat) · [cognitive](#cognitive) · [compare](#compare) · [connectors](#connectors) · [daftar](#daftar) · [debug](#debug) · [docs](#docs) · [doctor](#doctor) · [events](#events) · [extensibility](#extensibility) · [federation](#federation) · [gateway](#gateway) · [health](#health) · [hooks](#hooks) · [imtihan](#imtihan) · [integrations](#integrations) · [iqtisad](#iqtisad) · [knowledge](#knowledge) · [learner](#learner) · [media](#media) · [memory](#memory) · [middleware](#middleware) · [modes](#modes) · [muraqabah](#muraqabah) · [nafs](#nafs) · [openapi.json](#openapi.json) · [owned](#owned) · [perception](#perception) · [plan](#plan) · [plugins](#plugins) · [preferences](#preferences) · [providers](#providers) · [public](#public) · [qalb](#qalb) · [queue](#queue) · [ruh](#ruh) · [sakk](#sakk) · [sandbox](#sandbox) · [security](#security) · [settings](#settings) · [shura](#shura) · [skills](#skills) · [status](#status) · [tadbir](#tadbir) · [tasks](#tasks) · [training](#training) · [upload](#upload) · [v1](#v1) · [version](#version) · [voice](#voice) · [websocket](#websocket) · [workspaces](#workspaces) · [yaqin](#yaqin)

## agent-skills

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/agent-skills` | user | List skills |
| POST | `/api/agent-skills` | user | Write skill |
| POST | `/api/agent-skills/install` | user | Install skill |
| POST | `/api/agent-skills/upload` | user | Upload skill |
| DELETE | `/api/agent-skills/{name}` | user | Delete skill |
| GET | `/api/agent-skills/{name}` | user | Get skill |
| POST | `/api/agent-skills/{name}/enabled` | user | Toggle skill |
| GET | `/api/agent-skills/{name}/file` | user | Get skill file |
| POST | `/api/agent-skills/{name}/trust` | user | Accept a skill Amanah held, as its content is now (a later change is held again). |

## agents

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/agents` | user (more for admin) | List all agents with their Nafs profile; ``detail=false`` gives each in a few fields, and ``limit``/``offset`` page through them. |
| POST | `/api/agents` | admin | Resolve a provider once and persist the validated agent before publishing it. |
| DELETE | `/api/agents/{agent_id}` | admin | Delete agent |
| GET | `/api/agents/{agent_id}` | user (more for admin) | Get agent |
| PUT | `/api/agents/{agent_id}` | admin | Update an existing agent's name, model, or system prompt. |
| POST | `/api/agents/{agent_id}/model` | admin | Set model for a specific agent (does not affect other agents). |

## artifacts

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/artifacts/` | user | List artifacts route |
| POST | `/api/artifacts/` | user | Create artifact route |
| GET | `/api/artifacts/{artifact_id}` | user | Get artifact route |
| GET | `/api/artifacts/{artifact_id}/versions` | user | List versions route |
| POST | `/api/artifacts/{artifact_id}/versions` | user | Add version route |

## auth

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/auth/api-key` | user | Create an API key for the authenticated user |
| POST | `/api/auth/login` | public | Authenticate and get JWT token |
| POST | `/api/auth/logout` | user | End this token now (it stays revoked across restarts); with ``everywhere``, every token the account was given before now. |
| GET | `/api/auth/me` | user | Who this credential belongs to, its roles, and when the token expires. |
| POST | `/api/auth/register` | public | Register a new user |

## automation

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/automation/jobs` | admin | List all scheduled jobs |
| POST | `/api/automation/jobs` | admin | Create a new scheduled job |
| DELETE | `/api/automation/jobs/{job_id}` | admin | Remove a scheduled job |
| GET | `/api/automation/webhooks` | admin | List all webhook triggers |
| POST | `/api/automation/webhooks` | admin | Create a new webhook trigger |
| POST | `/api/automation/webhooks/{webhook_id}/trigger` | admin | Handle an incoming webhook trigger |

## bab

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/bab/email` | user | Whether MIZAN reads its own mailbox, its address, and whether your address is linked. |
| DELETE | `/api/bab/email/link` | user | Email unlink |
| POST | `/api/bab/email/link` | user | A one-time code (10 minutes): mail "link <code>" to MIZAN from your own address. |
| GET | `/api/bab/push/key` | user | MIZAN's public key for this browser to subscribe with, and its devices. |
| DELETE | `/api/bab/push/subscription` | user | Push unsubscribe |
| POST | `/api/bab/push/subscription` | user | Turn notifications on for this browser (a known push service only). |
| POST | `/api/bab/push/test` | user | Send yourself a test notice on every device you turned notifications on for. |
| GET | `/api/bab/telegram` | user | Whether MIZAN runs a Telegram bot, and whether your account is linked. |
| DELETE | `/api/bab/telegram/link` | user | Telegram unlink |
| POST | `/api/bab/telegram/link` | user | A one-time link (10 minutes) that ties a Telegram account to you. |
| GET | `/api/bab/whatsapp` | user | Whether MIZAN is on WhatsApp, your linked number, and what Meta's terms allow for it: assistant (compelled markets) or ancillary (notices only). |
| DELETE | `/api/bab/whatsapp/link` | user | Whatsapp unlink |
| POST | `/api/bab/whatsapp/link` | user | A one-time code (10 minutes): send "link <code>" to MIZAN's WhatsApp number. |

## channels

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/channels/{name}/start` | admin | Starting an external channel is not available: none runs yet. |
| GET | `/api/channels/{name}/status` | admin | The channel's real state (never 'connected' unless MIZAN runs it). |
| POST | `/api/channels/{name}/stop` | admin | Stop channel |
| POST | `/api/channels/{name}/test` | admin | Test channel |

## chat

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/chat` | user | Chat with an agent |
| GET | `/api/chat/approvals` | user | List chat approvals |
| POST | `/api/chat/approvals/{approval_id}` | user | Answer a pending tool approval of one of the caller's own live chats. |
| GET | `/api/chat/held` | user | Actions your watchers and other unattended runs held for your approval. |
| POST | `/api/chat/held/{held_id}` | user | Allow or deny one held action. Allowed, it runs exactly once, as it was held, through your own agent and its gates; the result is posted to the chat. |
| GET | `/api/chat/memory/summary` | user | Get conversation memory summary |
| GET | `/api/chat/preferences` | user | Get chat preferences |
| DELETE | `/api/chat/preferences/{key}` | user | Delete chat preference |
| PUT | `/api/chat/preferences/{key}` | user | Set chat preference |
| GET | `/api/chat/sessions/list` | user | The user's chats, newest first; ``limit``/``offset`` page through them and ``next_offset`` is where the next page starts (null at the end). |
| POST | `/api/chat/stream` | user | One authenticated POST produces one SSE stream; it is never replayed. |
| DELETE | `/api/chat/{session_id}` | user | Delete a chat and everything MIZAN derived from it (Mahw). The answer is a receipt: what was removed from each store, how many checks ran over what is left, and how many traces were found (none, when it worked). |
| GET | `/api/chat/{session_id}` | user | Newest ``limit`` messages; pass ``before=<message id>`` to page further back. |
| GET | `/api/chat/{session_id}/run-state` | user | Chat run state |
| POST | `/api/chat/{session_id}/stop` | user | Stop the user's active run in this chat (the Stop button). A dropped connection never does this: the run goes on and saves its answer. |

## cognitive

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/cognitive/route` | user | Route a query to the best Quranic cognitive method. |

## compare

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/compare` | user | Fan one prompt out to N models concurrently; blind labels only. |
| POST | `/api/compare/{compare_id}/reveal` | user | Reveal the model mapping; optionally run the LLM judge rubric. |

## connectors

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/connectors` | user (more for admin) | List connectors |
| POST | `/api/connectors` | user (more for admin) | Add connector |
| GET | `/api/connectors/oauth/callback` | public | Browser return from an authorization server (public: the single-use state is the key). |
| GET | `/api/connectors/registry` | user | Browse registry |
| DELETE | `/api/connectors/{server_id}` | user | Delete connector |
| GET | `/api/connectors/{server_id}` | user | Get connector |
| PATCH | `/api/connectors/{server_id}` | user | Update connector |
| POST | `/api/connectors/{server_id}/connect` | user | Connect now; OAuth servers return an authorization URL to open in a new window. |
| POST | `/api/connectors/{server_id}/disconnect` | user | Disconnect connector |
| POST | `/api/connectors/{server_id}/tools/{tool_name}/trust` | user | Accept a tool Amanah held (its description changed, or it instructs the AI). |

## daftar

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/daftar` | user | Daftar ledger |
| POST | `/api/daftar` | user | Save a note to remember; it goes to this user's own memory, which their agents recall. |
| GET | `/api/daftar/export` | user | Daftar export |
| POST | `/api/daftar/forget` | user | Forget chosen entries, or everything about a topic (first a preview, then confirm). |
| POST | `/api/daftar/import` | user | Daftar import |
| GET | `/api/daftar/receipts` | user | Receipts of what you asked MIZAN to forget, newest first. |
| PATCH | `/api/daftar/{entry_id}` | user | Daftar edit |

## debug

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/debug/compare` | debug mode (admins by default, `MIZAN_DEBUG_MODE`) | One message to the base model alone and to MIZAN, with MIZAN's full trace and checks. |
| DELETE | `/api/debug/runs` | debug mode (admins by default, `MIZAN_DEBUG_MODE`) | Clear debug runs |
| GET | `/api/debug/runs` | debug mode (admins by default, `MIZAN_DEBUG_MODE`) | Debug runs |
| GET | `/api/debug/runs/{run_id}` | debug mode (admins by default, `MIZAN_DEBUG_MODE`) | Debug run |
| GET | `/api/debug/status` | user (more for admin) | Debug status |

## docs

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/docs` | public | Swagger ui html |

## doctor

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/doctor` | admin | Self-healing diagnostic — check system health and auto-fix issues. "And We send down of the Quran that which is a healing (shifa)" — 17:82 |
| POST | `/api/doctor/fix` | admin | Run doctor with auto-fix enabled. |

## events

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/events` | admin | List all standard events and registered handlers. |
| GET | `/api/events/history` | admin | Get recent event history. |

## extensibility

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/extensibility` | admin | Overview of all extensibility points in MIZAN. Useful for developers who want to build plugins. |

## federation

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/federation/discover` | admin | Discover agents by capability. |
| POST | `/api/federation/route` | admin | Route a task to the best agent via Federation intelligence. |
| GET | `/api/federation/status` | admin | Get federation network status. |

## gateway

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/gateway/channels` | admin | Every channel with its real state. |
| GET | `/api/gateway/status` | admin | Get gateway status |

## health

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/health` | public | Health for monitoring and Docker: ``status`` for everyone; the version, uptime and each check only for a signed-in administrator. |

## hooks

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/hooks` | admin | List all standard hooks and registered handlers. |

## imtihan

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/imtihan/arc3` | admin | Imtihan arc3 status |
| POST | `/api/imtihan/arc3` | admin | MIZAN's explorer plays one official ARC-AGI-3 game (needs ARC_API_KEY). |
| GET | `/api/imtihan/panel` | admin | The human panel (imtihan/quwa.py): the text items people can answer, and who has. |
| POST | `/api/imtihan/panel` | admin | A panel member's answers (under a pseudonym), scored by the items' own rules. |
| GET | `/api/imtihan/panel/invites` | admin | Every invite link (never its code), whether it is active and how much was answered. |
| POST | `/api/imtihan/panel/invites` | admin | A link one person opens to answer the panel's items with no account. The code is shown once: only its SHA-256 is kept. |
| DELETE | `/api/imtihan/panel/invites/{invite_id}` | admin | Close an invite link; the answers given through it are kept. |
| DELETE | `/api/imtihan/panel/{person}` | admin | Erase every answer a panel member gave. |
| POST | `/api/imtihan/run` | admin | Start the AGI test in the background: every task to the base model and to MIZAN. |
| GET | `/api/imtihan/runs` | admin | Imtihan runs |
| GET | `/api/imtihan/runs/{run_id}` | admin | Imtihan run detail |
| POST | `/api/imtihan/runs/{run_id}/cancel` | admin | Imtihan cancel |
| DELETE | `/api/imtihan/runs/{run_id}/publish` | admin | Imtihan unpublish |
| POST | `/api/imtihan/runs/{run_id}/publish` | admin | Publish a finished run's aggregate report on the public reliability page. |
| GET | `/api/imtihan/tasks` | admin | Imtihan tasks |

## integrations

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/integrations` | admin | List integrations |
| POST | `/api/integrations` | admin | Add integration |
| DELETE | `/api/integrations/{int_id}` | admin | Delete integration |

## iqtisad

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/iqtisad` | user (more for admin) | What your model calls cost today and this month, against your limits. |
| GET | `/api/iqtisad/all` | admin | This month's model spend for every user (administrators). |
| PUT | `/api/iqtisad/limits` | user (more for admin) | Set your own limits. They can only make your budget smaller: the server's or an administrator's limit still applies when it is lower. |
| PUT | `/api/iqtisad/limits/{owner_id}` | admin | Set one user's limits (administrators). Null for both returns that user to the server's default limits. |

## knowledge

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/knowledge/ingest` | admin | Ingest knowledge from a URL or YouTube video into memory. |
| GET | `/api/knowledge/sources` | admin | List ingested knowledge sources. |
| POST | `/api/knowledge/upload` | admin | Upload a PDF file and ingest its content into memory. |

## learner

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/learner/export` | user | Download the caller's reviewed candidates with model authorship intact. |
| GET | `/api/learner/recent` | user | Get recent learning candidates |
| POST | `/api/learner/review/{interaction_id}` | user | Review learning candidate |
| GET | `/api/learner/stats` | user | Get learning data capture statistics. |

## media

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/media/{sha}` | user | One of your own images from a chat (Basar); never another user's. |

## memory

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/memory/consolidate` | admin | Consolidate memory |
| GET | `/api/memory/list` | admin | List this user's recent memories without search filtering. |
| POST | `/api/memory/query` | admin | Query memory |
| POST | `/api/memory/store` | admin | Save a note to this user's own memory, which their agents recall. |

## middleware

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/middleware` | admin | List all registered middleware pipelines. |

## modes

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/modes` | user | Available agent modes: 'single' (default ReAct path) and 'deep_research'. |
| POST | `/api/modes/deep-research` | user | Run the deep_research pipeline. Requires confirmed=true (else 409). |

## muraqabah

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/muraqabah` | user | Your watchers, your place, today's prayer times and quiet windows, and attention used. |
| GET | `/api/muraqabah/notices` | user | Watcher notices |
| POST | `/api/muraqabah/notices/{notice_id}/feedback` | user | Useful or not now: this teaches MIZAN when to interrupt you. |
| PUT | `/api/muraqabah/place` | user | Your place (for prayer times), calculation method, Asr school and attention settings. |
| POST | `/api/muraqabah/watchers` | user | Add watcher |
| DELETE | `/api/muraqabah/watchers/{watcher_id}` | user | Delete watcher |
| PATCH | `/api/muraqabah/watchers/{watcher_id}` | user | Update watcher |
| POST | `/api/muraqabah/watchers/{watcher_id}/run` | user | Run a watcher now; its notice is judged like any other (salah, attention). |

## nafs

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/nafs/tiers` | admin | Get all 7 Nafs tiers and their permission mappings. |
| GET | `/api/nafs/{agent_id}` | admin | Get 7-level Nafs status for an agent. |
| GET | `/api/nafs/{agent_id}/faculties` | admin | Get al-Insan faculty state for an agent: Hikmah wisdom and principles. |

## openapi.json

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/openapi.json` | public | Openapi |

## owned

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/owned/chat` | user | Owned chat |
| POST | `/api/owned/context/resolve` | user | Owned context |
| GET | `/api/owned/export` | admin | Owned export |
| GET | `/api/owned/learning` | admin | Owned learning status |
| POST | `/api/owned/learning/rollback` | admin | Owned learning rollback |
| POST | `/api/owned/learning/run` | admin | Owned learning run |
| GET | `/api/owned/research/search` | admin | Owned research search |
| POST | `/api/owned/retract` | admin | Owned retract |
| GET | `/api/owned/reviews` | admin | Owned reviews |
| POST | `/api/owned/reviews/{proposal_id}` | admin | Owned review |
| POST | `/api/owned/support` | admin | Owned support |

## perception

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/perception/analyze` | admin | Analyze multimodal input through the QCA perception pipeline. |

## plan

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/plan` | admin | Decompose a complex goal into sub-tasks using TafakkurPlanner |
| GET | `/api/plan/{plan_id}` | admin | Get status of a plan |
| POST | `/api/plan/{plan_id}/execute` | admin | Execute a previously created plan |

## plugins

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/plugins` | admin | List all discovered plugins with their status. |
| GET | `/api/plugins/tools` | admin | List all tools provided by loaded plugins. |
| POST | `/api/plugins/{name}/load` | admin | Load (activate) a plugin. |
| POST | `/api/plugins/{name}/reload` | admin | Reload a plugin (unload + load). |
| POST | `/api/plugins/{name}/unload` | admin | Unload (deactivate) a plugin. |

## preferences

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/preferences` | user | Return all persisted user preferences. |
| POST | `/api/preferences` | admin | Save one or more preferences. Body: {"key": "value", ...} |

## providers

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/providers` | user | List all LLM providers with their status, models, and configuration. Inspired by OpenClaw's multi-provider architecture. |
| POST | `/api/providers/switch` | admin | Switch the active LLM provider and model for all agents. Persists choice to database so it survives restarts. |
| GET | `/api/providers/{provider_name}/health` | user | Health check for a specific provider. Verifies API keys are valid and the provider is reachable. |
| GET | `/api/providers/{provider_name}/models` | user | List available models for a specific provider. For OpenRouter: fetches the live catalog with search/filter/pagination. For Ollama: fetches locally installed models. |

## public

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/public/panel/{code}` | public | The items an invited person answers, and which they already have (no verdicts). |
| POST | `/api/public/panel/{code}` | public | An invited person's answers: scored by the items' own rules and kept. The first answer to an item is final and no verdict is returned. |
| GET | `/api/public/reliability` | public | MIZAN's published AGI-test results (aggregates only) and its signed Sakk roots. |
| GET | `/api/public/reliability/{run_id}` | public | Public reliability run |
| GET | `/api/public/sakk` | public | MIZAN's receipt-signing public key and its recent signed daily roots. |
| GET | `/api/public/whatsapp` | public | Meta's webhook subscription check (hub.mode, hub.verify_token, hub.challenge). |
| POST | `/api/public/whatsapp` | public | Meta's webhook: accepted only when signed with the app secret. |

## qalb

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/qalb/analyze` | user (more for admin) | Analyze emotional state from a message. |
| GET | `/api/qalb/trend/{user_id}` | user (more for admin) | Get emotional trend for a user. |

## queue

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/queue/status` | admin | Get overall queue status with counts and worker state. |
| GET | `/api/queue/tasks` | admin | List tasks in the queue, optionally filtered by status. |
| POST | `/api/queue/tasks` | admin | Add a task to the priority queue. |
| DELETE | `/api/queue/tasks/{task_id}` | admin | Cancel a pending queued task. |
| GET | `/api/queue/tasks/{task_id}` | admin | Get status and details of a specific queued task. |

## ruh

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/ruh/architecture` | user | Get model architecture info and parameter counts. |
| GET | `/api/ruh/checkpoints` | user | List available model checkpoints with metadata. |
| GET | `/api/ruh/data-stats` | user | Get training data composition and statistics. |
| POST | `/api/ruh/generate` | user | Generate text using the local Rūḥ Model. |
| GET | `/api/ruh/status` | user | Get Rūḥ Model availability and configuration. |
| POST | `/api/ruh/tasrif-demo` | user | Apply tasrif morphophonemic operators to articulatory feature vectors. |
| POST | `/api/ruh/tokenize` | user | Tokenize text using the Bayān tokenizer and return analysis. |
| GET | `/api/ruh/{agent_id}` | user | Get Ruh energy state for an agent. |

## sakk

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/sakk` | user | Your action receipts, newest first: tool, outcome, time and chain hash. |
| GET | `/api/sakk/export` | user | Your chain, your digest key and MIZAN's signed proof, to check anywhere with scripts/verify_sakk.py. |
| GET | `/api/sakk/verify` | user | Recompute your whole chain and say whether every receipt still holds. |
| GET | `/api/sakk/verify/all` | admin | Sakk verify all |

## sandbox

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/sandbox/run` | admin | Execute code in an isolated sandbox. Auth applied at mount time. |
| GET | `/api/sandbox/status` | user | Report which sandbox provider (if any) is available. |

## security

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/security/audit` | admin | View security audit log (admin only) |
| GET | `/api/security/permissions` | admin | View agent permissions |

## settings

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/settings` | admin | Get all settings (secrets masked) |
| POST | `/api/settings` | admin | Update a setting (API key, config value, etc.) |
| GET | `/api/settings/runtime` | admin | Every operator setting with its current value (secrets are never returned). |
| PUT | `/api/settings/runtime` | admin | Runtime settings update |

## shura

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/shura` | admin | Multi-agent Shura consultation |

## skills

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/skills` | user | List all available skills |
| POST | `/api/skills/execute` | admin | Execute a skill action — routes to the appropriate built-in skill |
| POST | `/api/skills/install` | admin | Install a skill |
| POST | `/api/skills/uninstall` | admin | Uninstall a skill |

## status

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/status` | admin | Full system status - Mizan dashboard; ``detail=false`` lists each agent in a few fields. |

## tadbir

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/tadbir/harness` | admin | Lisan's instruction versions (Tajdid) and the models chosen for code work (Wazn), admin. |
| DELETE | `/api/tadbir/harness/{task}` | admin | Return one kind of work to MIZAN's built-in instruction (admin). |
| GET | `/api/tadbir/learning` | user | What MIZAN learned from its own verified work: who does which work, and your wording. |
| GET | `/api/tadbir/learning/live` | user | What MIZAN learned from your work since ``after``, as it happens (Sijill). |
| DELETE | `/api/tadbir/learning/wording` | user | Forget the wording MIZAN learned from this user's requests. |
| DELETE | `/api/tadbir/lessons` | user | Forget repair lessons |
| GET | `/api/tadbir/lessons` | user | Lessons MIZAN kept from its own verified repairs of your code (Tajriba). |
| POST | `/api/tadbir/muhasaba` | admin | Run MIZAN's self-review now (admin): re-check recent unverified answers. |
| DELETE | `/api/tadbir/programs` | user | Forget programs |
| GET | `/api/tadbir/programs` | user | The programs MIZAN verified for you and re-runs instead of asking the model (Hifz). |
| GET | `/api/tadbir/talim` | admin | Ta'lim (admin): what MIZAN can be taught, and every batch so far. |
| POST | `/api/tadbir/talim` | admin | Teach a batch of examples; kept only if it does not make MIZAN worse at what it already knew (leave-one-out before and after, paired bootstrap). |
| POST | `/api/tadbir/talim/import` | admin | Teach from a Hugging Face dataset split (read through the dataset viewer). |
| DELETE | `/api/tadbir/talim/{batch}` | admin | Talim undo |

## tasks

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/tasks` | admin | Execute a task - single or parallel |
| GET | `/api/tasks/history` | admin | Get task history |

## training

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/training/history` | admin | Get history of past training runs. |
| POST | `/api/training/start` | admin | Start a Rūḥ Model training run. |
| GET | `/api/training/status` | admin | Get current Rūḥ Model training status. |
| POST | `/api/training/stop` | admin | Stop the currently running training. |

## upload

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/upload` | user | Accept file uploads (PDF, images, docs) for processing. |

## v1

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/v1/analyze` | user | Analyze text into per-token morphology (deterministic, rule-based). |
| GET | `/api/v1/analyze/health` | user | Probe backend capabilities (tables loaded? model available?). |
| POST | `/api/v1/disambiguate` | user | Disambiguate word |
| POST | `/api/v1/embed` | user | POST /v1/embed — body ``{"texts": [...], "dims": 256}``. |
| POST | `/api/v1/normalize` | user | Normalize |
| POST | `/api/v1/q28-features` | public | Extract Q28 articulatory features for any text. |
| POST | `/api/v1/qwen3/chat` | user | Qwen3 chat |
| POST | `/api/v1/qwen3/chat/stream` | user | Qwen3 chat stream |
| POST | `/api/v1/qwen3/disambiguate` | user | Same deterministic pipeline as /v1/disambiguate, then Qwen3 reranks. |
| POST | `/api/v1/qwen3/grounded-analysis` | user | Qwen3 grounded analysis |
| POST | `/api/v1/qwen3/grounded-qa` | user | Qwen3 grounded qa |
| GET | `/api/v1/qwen3/health` | user | Qwen3 health |
| POST | `/api/v1/reader/build` | user | Build |
| GET | `/api/v1/reader/lookup` | user | Lookup |
| POST | `/api/v1/root-analyze` | public | Root, pattern (wazn), part of speech and meaning of each Arabic word, from the Quranic Arabic Corpus (the analyzer the chat uses too). |
| POST | `/api/v1/screen` | user | POST /v1/screen — body ``{"text": ..., "doc_type": ...}``. |
| POST | `/api/v1/tajwid/analyze` | user | Annotate Arabic text with tajwīd rules (Ḥafṣ ʿan ʿĀṣim). |
| GET | `/api/v1/tajwid/rules` | user | Return the tajwīd rule catalog with classical sources. |
| POST | `/api/v1/tokenize` | public | Tokenize text into (root_id, pattern_id) tuples. |

## version

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/version` | admin | Version info and update check |

## voice

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/voice` | user | Whether this server can turn speech into text, and today's allowance left. |
| POST | `/api/voice/transcribe` | user | A short voice recording as text for the composer (Sama'). The audio is heard on this server and kept nowhere; the person reads the words and sends them. |

## websocket

| Method | Path | Who | What it does |
|---|---|---|---|
| WEBSOCKET | `/ws/workspaces/{workspace_id}/terminal` | user (token in the URL) | Relay an interactive shell in the session; bytes both ways, resize as JSON text. |
| WEBSOCKET | `/ws/{client_id}` | user (token in the URL) | Websocket endpoint |

## workspaces

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/workspaces` | user (more for admin) | List workspaces |
| POST | `/api/workspaces` | user | Create workspace |
| GET | `/api/workspaces/hardware` | user (more for admin) | Hardware |
| GET | `/api/workspaces/preview/{cap}/{port}` | capability URL | Preview root |
| DELETE | `/api/workspaces/preview/{cap}/{port}/{path:path}` | capability URL | Preview |
| GET | `/api/workspaces/preview/{cap}/{port}/{path:path}` | capability URL | Preview |
| PATCH | `/api/workspaces/preview/{cap}/{port}/{path:path}` | capability URL | Preview |
| POST | `/api/workspaces/preview/{cap}/{port}/{path:path}` | capability URL | Preview |
| PUT | `/api/workspaces/preview/{cap}/{port}/{path:path}` | capability URL | Preview |
| POST | `/api/workspaces/{workspace_id}/artifact` | user | Artifact |
| POST | `/api/workspaces/{workspace_id}/checkpoint` | user | Checkpoint |
| GET | `/api/workspaces/{workspace_id}/checkpoints` | user | Checkpoints |
| GET | `/api/workspaces/{workspace_id}/diff` | user | Diff |
| POST | `/api/workspaces/{workspace_id}/directory` | user | Create directory |
| DELETE | `/api/workspaces/{workspace_id}/file` | user | Delete file |
| GET | `/api/workspaces/{workspace_id}/file` | user | Read file |
| PUT | `/api/workspaces/{workspace_id}/file` | user | Write file |
| GET | `/api/workspaces/{workspace_id}/files` | user | The project's text files in one response (for browser previews), bounded. |
| POST | `/api/workspaces/{workspace_id}/rename` | user | Rename file |
| POST | `/api/workspaces/{workspace_id}/run` | user | Execute project |
| DELETE | `/api/workspaces/{workspace_id}/session` | user | Session stop |
| GET | `/api/workspaces/{workspace_id}/session` | user | Session status |
| POST | `/api/workspaces/{workspace_id}/session` | user | Session start |
| POST | `/api/workspaces/{workspace_id}/session/exec` | user | Session exec |
| POST | `/api/workspaces/{workspace_id}/session/services` | user | Service start |
| DELETE | `/api/workspaces/{workspace_id}/session/services/{port}` | user | Service stop |
| GET | `/api/workspaces/{workspace_id}/session/services/{port}/logs` | user | Service logs |
| POST | `/api/workspaces/{workspace_id}/session/sync` | user | Session sync |
| GET | `/api/workspaces/{workspace_id}/tree` | user | Tree |

## yaqin

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/api/yaqin/stats` | user | Get Yaqin engine statistics. |
| POST | `/api/yaqin/tag` | user | Tag a piece of knowledge with its Yaqin certainty level. |

