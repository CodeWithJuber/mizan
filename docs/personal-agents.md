# Personal agents

Every signed-in person can make agents of their own, give each a persona and its own
settings, and choose which one answers them by default. The agents act on their own:
the default orchestration is `hybrid` and the default permission mode `auto`. What stays
fixed is what the owner of this server decided must never move:

- Quran and hadith text always comes from MIZAN's sources, never from a model (Tadbir's
  recipes, Sidq's check of every quote, Isnad's grades). A request with a Quran or
  hadith part stays with MIZAN in `hybrid` mode.
- A non-admin's host tools (`bash`, `python_exec`, the file tools) run in their own
  sandbox, never on the server. Otherwise any account could read `connectors.key` and
  every user's data.

The code: `backend/agents/agent_settings.py` (the settings), the `/api/agents*` routes in
`backend/api/main.py`, `BaseAgent.get_tool_schemas` / `to_dict` / `_sandbox_*` in
`backend/agents/base.py`.

## Who owns an agent, who sees it

| | An administrator's agent | Anyone else's agent |
|---|---|---|
| `owner_id` | the administrator | the person who made it |
| `shared` | `true` unless they send `"shared": false` | always `false` |
| Who sees it (`GET /api/agents`) | everyone (a private one: administrators only) | its owner and administrators |
| Who changes or deletes it | administrators | its owner and administrators |
| Its persona (`system_prompt`) | shown to whoever may change it | shown to its owner and administrators |

The four agents MIZAN starts with (Khalifah, Mubashir, Mundhir, Katib) are shared. A
database from before this change reads every saved agent as shared with no owner.

Each agent in a response also says `editable` (the caller may change it) and `is_default`
(it is the caller's default agent). A person's chats run on their own copy of each agent
they may see (private memory and learning, `_private_agent`), which takes the agent's
Nafs level; the copies of one person form their Majlis team. Someone else's private agent
is never in that team, and a chat that names it is answered by Khalifah.

A non-admin may keep 50 agents of their own (`MAX_AGENTS_PER_USER`): each is a full agent
in the server's memory.

## The API

| Route | What it does |
|---|---|
| `GET /api/agents` | The agents you may use, each with `owner_id`, `shared`, `editable`, `is_default`, `settings`, `effective_tools`, `provider_warning`. |
| `POST /api/agents` | `{name, type, provider?, model?, system_prompt?, settings?, shared?, capabilities?}`. Without a provider and model the server's current ones are used. `capabilities` becomes `settings.tools_allow` when that is not given. |
| `GET /api/agents/{id}` | One agent. 404 for an agent you may not see. |
| `PUT /api/agents/{id}` | `{name?, model?, system_prompt?, settings?}`. Settings merge key by key; a key sent as `null` goes back to its default. The agent's record (tasks, success, errors, creation time, Nafs) is kept. 403 for an agent you do not own. |
| `DELETE /api/agents/{id}` | Deletes the agent and its saved profile, so it does not come back at the next start. |
| `POST /api/agents/{id}/model` | `{provider, model}`: the agent's own provider and model. |
| `POST /api/agents/{id}/clone` | A copy owned by you, named "<name> (copy)". The persona is copied only when you may see it; a provider this server cannot start is replaced by the default. |
| `GET /api/agents/{id}/export` | `{"format": "mizan-agent/1", "agent": {name, type, provider, model, system_prompt, settings}}`: no keys, no memory, no record. |
| `POST /api/agents/import` | That JSON, made again as your own agent. |
| `GET` / `PUT /api/agents/default` | `{agent_id}`: your default agent (`null`: Khalifah). |

## Settings

Every agent has all of these keys; an empty list means no restriction and `null` means
the server's own setting.

| Key | Values | What it does |
|---|---|---|
| `temperature` | 0–1 or `null` | Sampling temperature for providers other than Claude (Claude requests never send it). Mapped onto the agent's `temperature` config key. |
| `effort` | `low` … `max` or `null` | Claude's effort for this agent's runs, instead of `MIZAN_CHAT_EFFORT` (`providers.AGENT_EFFORT`). |
| `max_steps` | 1–1000 or `null` | Tool rounds per answer, instead of `MIZAN_CHAT_MAX_STEPS`. |
| `max_output_tokens` | 256–128000 or `null` | Output tokens per call, instead of `MIZAN_CHAT_MAX_OUTPUT_TOKENS`. |
| `orchestration` | `mizan`, `hybrid`, `llm` or `null` | Who directs this agent's runs, instead of `MIZAN_ORCHESTRATION` ([tadbir.md](tadbir.md#modes)). Bound per run (`tadbir.engine.bind_mode`). |
| `permission_mode` | `auto`, `auto_edits`, `ask`, `plan` or `null` | The mode of a chat with this agent that sends none, instead of `MIZAN_DEFAULT_PERMISSION_MODE` ([agentic-coding.md](agentic-coding.md#permission-modes-izn-approvals)). |
| `tools_allow` | tool names, `*` and `?` allowed | Only these tools are offered (connector tools are chosen by `connectors`). |
| `tools_deny` | tool names, `*` and `?` allowed | Never offered, connector tools included. |
| `connectors` | connector server names | Only these connectors' tools (`mcp__<server>__…`) are offered. |
| `skills` | skill names | Only these Agent Skills are listed to `activate_skill` and may be loaded. |
| `starter_prompts` | up to 12 lines | Suggestions the app shows for a new chat with the agent. |
| `avatar` | text (an emoji or an image URL) | How the app shows the agent. |
| `learn_skills` | `true` (default) / `false` | Whether the agent is offered `skill_write`. |

`effective_tools` lists the tools the agent's model is offered for you, after Izn, your
role, the agent's lists and its orchestration: in `mizan` mode it is empty, since MIZAN
runs every tool itself. `provider_warning` is set when the agent's own provider could
not start at startup (a key removed): the agent then follows the default provider until
its owner picks a model again.

## The persona

The agent's `system_prompt` is its persona. It reaches the model in both places the
model is used:

- the agent loop's system prompt, under "YOUR PERSONA AND INSTRUCTIONS", after MIZAN's
  capability facts and scripture rules (no longer marked as subordinate);
- Lisan, MIZAN's language faculty: after Lisan's fixed role and each task's own rules,
  with the reminder that Quran and hadith text comes only from MIZAN's sources and that
  each task's reply format stands (`tadbir.lisan.persona`).

An imported persona is read by Amanah first (`amanah.beyond_instructions`). A persona is
instructions by its nature, so plain instructions ("You are Zaid, answer in Urdu") pass;
one that tries to override MIZAN's rules, hide something from the user, carry their data
away or hide text is refused with 422.

## Learned skills (`skill_write`)

After a multi-step task that could recur, the agent may save it as a skill:
`skill_write(name, description, body)` writes a `SKILL.md` into the signed-in user's own
skills (`agent_skills.installer.write_skill`; replaced when the name exists). A later chat
loads it with `activate_skill`. The name is 1–64 lowercase letters, digits and hyphens,
the text at most 32 KB. Amanah refuses an override, concealment or exfiltration in it; a
skill with plain instructions only is trusted for its user (pinned to its content), so it
is not held as an uploaded one would be. A model that read an injected page cannot save
one silently: after a finding every change it chooses needs a person's approval.

## The default agent

`PUT /api/agents/default` chooses the agent that answers:

- a web or WebSocket chat that names no agent;
- the person's messages from Telegram, email and WhatsApp ([bab.md](bab.md));
- their watchers' tasks ([muraqabah.md](muraqabah.md)), unless the watcher names its own
  `agent_id` (`POST`/`PATCH /api/muraqabah/watchers`, one the person may use; `""`
  clears it).

With none chosen, or when the chosen agent was deleted or is no longer theirs, Khalifah
answers.

## Providers: xAI (Grok) and Meta (Muse Spark)

Both are OpenAI-compatible endpoints (`providers.COMPATIBLE_ENDPOINTS`):

| Provider | Id | Base URL | Key |
|---|---|---|---|
| xAI (Grok) | `xai` | `https://api.x.ai/v1` | `XAI_API_KEY` |
| Meta (Muse Spark) | `meta` | `https://api.meta.ai/v1` (Meta's Model API docs) | `META_API_KEY` (Meta's docs call it `MODEL_API_KEY`, also read) |

- Set the keys in Settings → Developer → System settings (sealed like every key).
- `LLM_PROVIDER=auto` picks them after Anthropic, OpenRouter and OpenAI; a model id
  starting `grok` or `muse` goes to them when their key is set.
- Their models are listed live from the provider's own `GET /models`, cached an hour
  (`GET /api/providers/{xai|meta}/models`). Until the first read the default is a marked
  fallback id (`grok-4`, `muse-spark-1.1`).
- Iqtisad prices their calls by OpenRouter's live ids for them (`x-ai/<model>`,
  `meta/<model>`); a model with no price follows `MIZAN_BUDGET_UNPRICED`.

## What became a setting

| Was | Now |
|---|---|
| `MIZAN_ORCHESTRATION` default `mizan` | default `hybrid`; per agent `settings.orchestration` |
| No mode sent: no approvals at all | `MIZAN_DEFAULT_PERMISSION_MODE` (`auto`), per agent `settings.permission_mode`; WebSocket chats bind approvals too |
| `shahid_submit` always asked | `MIZAN_ALWAYS_ASK_TOOLS` (empty) |
| Amanah held changes after any outside content or an image | only after an Amanah finding |
| Fitrah blocked tool calls by their words | advisory, in `result["fitrah"]` |
| Non-admins: no bash, Python, files or HTTP | all of them, in their own sandbox / through `net_guard` |
| Tools hidden by Nafs level; delegation from level 3 | never hidden; Nafs is a metric |
| Izn denied `bash` and `write_file` to the browser and research agents; 30 calls a minute per tool | no role denies; `MIZAN_TOOL_CALLS_PER_MINUTE` (120) |
| 30 chat messages a minute | `MIZAN_CHAT_PER_MINUTE` (60) |
| 8 tool schemas / 12 KB per request | `MIZAN_TOOL_CATALOG_LIMIT` (16) / `MIZAN_TOOL_CATALOG_BYTES` (32 KB) |
| A provider switch wiped every agent's own provider | only agents that follow the default move |
