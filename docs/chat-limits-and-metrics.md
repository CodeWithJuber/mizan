# Chat output limits and metric provenance

An answer that contains only a length-limit warning is not a successful answer.
Mizan now rejects an empty, length-limited provider response with the safe
`output_budget_exhausted` code. It does not replay tools, count that result as
successful learning, or substitute private provider reasoning for answer text.
Visible truncated answers may use at most two text-only continuations.

The per-call output budget defaults to the selected model's own output cap (up
to 16,000 tokens per call, so one call stays inside its wait limit; longer
answers continue automatically; the live Anthropic Models API and OpenRouter catalog supply
the caps, with a static table as fallback). Configure it with an agent's
`max_output_tokens` setting or `MIZAN_CHAT_MAX_OUTPUT_TOKENS`; the allowed range
is 256 up to the model cap (at most 128,000). Emotion/tone rules no longer
determine this budget. These are application bounds, not a promise of unlimited
answers or provider availability.

Claude requests use API version `2026-10-21` (anthropic SDK 2.x): no sampling
parameters (`MIZAN_CHAT_TEMPERATURE` applies to other providers only), effort
from `MIZAN_CHAT_EFFORT` (default `high`) on models that support it, automatic
prompt caching (`MIZAN_ANTHROPIC_PROMPT_CACHE`, default on) and, on the current
Opus/Sonnet/Fable models, server-side refusal fallbacks
(`MIZAN_ANTHROPIC_FALLBACKS`, default on). Thinking blocks are sent back
unchanged inside one tool loop. A refusal ends the run with the
`model_refused` code. Agent telemetry and recalled memory travel with the
request context so the system prompt stays cacheable.

For the two explicitly supported OpenRouter Nemotron 3.5 Super VL IDs, Mizan
requests at most 1,024 reasoning tokens and at most a quarter of the output
budget. Below 2,048 output tokens it disables optional reasoning. Other models
retain their existing request format.

OpenRouter documents that reasoning commonly shares the output limit and can
consume it before any answer text is emitted. The model listing documents
optional reasoning and token-budget support. This mechanism matches a possible
cause of the reported empty length-limit response; a screenshot alone does not
establish the exact reasoning usage of that historical call. References checked
2026-10-26: [reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
and [model listing](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free).

## Interrupted streams

An attempted provider POST is never silently replayed after a stream failure,
including failures before visible text. SDK retries are disabled, and the
agent's recovery path cannot make another model call after an attempted call.
Providers that support only buffered output retain their normal adapter.

Wall-clock budgets supplement the provider SDK's socket inactivity timeout:

| Environment setting | Default seconds | Allowed range | Covers |
|---|---:|---:|---|
| `MIZAN_LLM_FIRST_PROGRESS_SECONDS` | 60 | 1–180 | First visible text or tool-argument progress |
| `MIZAN_LLM_BUFFERED_FIRST_PROGRESS_SECONDS` | 180 | 1–900 | Same, for providers without streaming deltas |
| `MIZAN_LLM_PROGRESS_SECONDS` | 60 | 1–180 | Subsequent meaningful progress |
| `MIZAN_LLM_MAX_CALL_SECONDS` | 600 | 1–1800 | Entire provider call |
| `MIZAN_CHAT_RUN_SECONDS` | 1800 | 30–7200 | Context preparation, agent queue and execution |

Comments, keepalives and OpenRouter-style hidden reasoning do not extend the progress
deadline. Claude thinking deltas count as liveness only (never as answer text), so a
visibly reasoning Claude model is not cut off as stalled.
A local timeout closes the stream where supported; it cannot establish whether
the upstream provider stopped or charged for its work.

A stream that closes before a completion or error event is incomplete. The chat
keeps the received text and a visible error notice instead of treating the close
as a user Stop. It never automatically repeats an uncertain POST. Check history
before retrying: the server may have completed work after the connection failed.
An explicit Stop remains a separate local action; a cancelled history receipt
alone does not prove that the user pressed Stop.

The delivery deadline applies to the actual ASGI network write. With the outer
transport guard active, the response does not apply another network deadline to
Starlette's internal middleware handoff. A production QA request on 2026-10-26
hit that inner deadline after approximately 75 seconds despite a healthy backend
and a 300-second proxy timeout. Slow network writes remain bounded.

Cancellation receipts record a fixed reason, execution stage and elapsed request
time. Provider attempt timings are included only when observed for that request;
missing token counters stay missing. If saving a reply fails, the server emits a
terminal `history_save_failed` error without claiming that the reply was saved.

The authenticated run-state endpoint reports an active run, a terminal receipt,
an uncertain outcome or an idle session. Recovery reads status and history; it
does not resubmit the prompt. The browser retains received partial text with its
original request identity and keeps Send locked while the outcome is uncertain.
An active-session conflict has its own error code and the active run's identity,
instead of appearing as a generic network error. A session remains occupied
until both its producer and response transport have finished.

## Unlimited conversations

A conversation is not limited by the model's context window:

- **History budget.** Each request sends the recent turns that fit
  `MIZAN_CONTEXT_FILL` (default 0.5) of the selected model's context window,
  capped by `MIZAN_CONTEXT_HISTORY_TOKENS` (default 150,000).
- **Running summary.** Older turns are folded into a per-session summary
  (`session_summaries` table) by the session's own model, chunk by chunk. A
  summary that grows too large is compressed again. Without a usable model
  an extractive digest is used, so a long chat never stops. `/compact` folds
  the whole session on demand. Summaries are attributed context, not facts.
- **Steps.** A run may use `MIZAN_CHAT_MAX_STEPS` (default 100) tool rounds,
  independent of the Nafs level (which still decides *which* tools exist).
  At the limit the model writes a progress report instead of the run failing.
- **Continuations.** A length-limited answer continues up to
  `MIZAN_CHAT_MAX_CONTINUATIONS` (default 20) times; it stops early if a
  continuation repeats earlier text.
- **Cut-off tool calls.** A tool call cut by the output limit never runs; the
  turn is requested again with more room (twice at most) and the model is
  told to split large inputs.
- **One long run.** Claude runs use server-side compaction
  (`MIZAN_ANTHROPIC_COMPACTION`); other providers replace older tool results
  with excerpts once a run passes ~60% of the window. Tool results are capped
  at `MIZAN_CHAT_TOOL_RESULT_CHARS` with valid JSON.
- **History in the UI.** `GET /api/chat/{session_id}?limit=50&before=<id>`
  pages older messages; the chat view offers "Load earlier messages".
- **Small models.** A provider that serves a fixed window declares it (the
  MiniMind/hybrid worker: 2,048 tokens with 256 output). Its declaration wins
  over the model table. History budgets reserve room for the output and the
  system prompt, windows ≤ 8K use halved budgets (small tokenizers count more
  tokens), and every request is fitted before it is sent: the oldest turns go
  first, the running summary last, then the output cap shrinks.

## Provider failures

An upstream failure does not end the reply when it can be recovered safely:

- **Gateway fallbacks.** OpenRouter requests carry a `models` list, so the
  gateway itself retries the next model inside the same request.
  `MIZAN_OPENROUTER_FALLBACKS=auto` (default) adds up to two *free*
  tool-capable models for a free primary, preferring the same vendor and the
  largest context, so a failover never changes the cost; a paid primary gets
  none. Set `none`, or a comma-separated list of model IDs.
- **Explicit rejections are retried.** HTTP 429, 500, 502, 503 or 529 means
  the provider answered with an error, so nothing was generated or billed.
  The same request is sent again up to twice (1.5s, 3s; 429 honours
  `Retry-After`, at most 20s), only while no answer text has been shown.
- **Ambiguous failures are never replayed.** Timeouts, dropped connections
  and 504s may still be running upstream; they end the reply as before.
- When retries and fallbacks are exhausted the reply ends with
  `provider_unavailable` instead of the generic `agent_failed`.

## Request language and available tools

Explicit output-language instructions take priority. Otherwise, the assistant
matches the current message's natural language. A saved reply language is omitted
from the effective provider context whenever the request contains Unicode prose;
it remains available as a fallback for syntax-only or language-neutral input.
This detects prose rather than classifying languages, and does not change the
stored preference. Short follow-ups can use the conversation without reissuing
an older language instruction. Quoted code and tool results do not establish the
current response language. Retrieved context appears before the current request.
Greeting preferences remain independent. Custom role defaults and heuristic
observations cannot override the current request's language, tone or format.

Each execution builds a tool catalogue from available handlers, enabled skills,
loaded plugins, the selected workspace, and existing permission/developmental
gates. It ranks current-request relevance against the tools' names and metadata.
A bounded discovery tool makes the other permitted tools reachable without
sending every schema on every message. Discovery does not execute an action or
consume an approval; an actual call still passes the normal authorization and
argument checks. This is runtime selection, not learned model training.

The schema window defaults to eight definitions and 12,288 UTF-8 bytes. Set
`MIZAN_CHAT_TOOL_SCHEMA_LIMIT` (2–32) and `MIZAN_CHAT_TOOL_SCHEMA_BYTES`
(4,096–65,536), or the agent's `tool_schema_limit` and `tool_schema_bytes`.
Generation temperature uses the explicit agent `temperature` or
`MIZAN_CHAT_TEMPERATURE` (default 0.5, bounded 0–1). Qalb oscillation no longer
changes it. Deterministic self-checks report diagnostics without appending
canned English caveats or rewriting text after it has streamed.

The agent editor loads provider/model options from the runtime catalogue and
preserves the actual current provider, model and role even if catalogue loading
fails. Browsing options does not change an agent. A name or custom-instruction
edit leaves its model unchanged; an explicit model change uses the provider-aware
endpoint. Creation submits the selected provider/model together and persists the
validated configuration before publishing the agent. API callers omitting the
selection use the current runtime configuration rather than a fixed model ID.

The current production Compose template maps these chat settings from `.env`.
Installations retaining an older Compose template need the corresponding
environment entries before `.env` changes reach the container. Deployments
preserve existing runtime values; an absent setting uses the application default.

## Deployment draining

The production image waits up to 90 seconds for active application work during
shutdown, with a 105-second Docker stop budget. For a custom 10–180-second grace,
set `MIZAN_GRACEFUL_SHUTDOWN_SECONDS` in the environment invoking
`scripts/deploy_production.sh`; this is not a plain Compose `.env` override.
The script derives matching application/container limits and gives both forward
deployment and rollback enough stop time for the larger of the old/new limits.
Invalid grace settings fail before containers are stopped. This reduces restart
interruptions but does not make a single-backend rollout zero-downtime. On the
first rollout, the old process receives the longer Docker stop allowance; its
application shutdown timer cannot be changed retroactively.

## What the displayed numbers mean

| Display | Source | What it establishes |
|---|---|---|
| Input/output tokens | Provider usage records, summed across observed calls | Reported usage; absent counters remain absent |
| Reasoning tokens | Provider counter, when present | Reported reasoning usage, usually included in output tokens |
| Non-reasoning tokens | Output minus reasoning | Can include tool arguments as well as answer text |
| Model-call time | Mizan's timer around provider attempts | Local elapsed call time, not a provider token-generation benchmark |
| Agent time | Execution-entry to return timer | Queue wait, execution and capture; excludes API preparation and message persistence |
| Cost | Provider report or marked price-table estimate | No invented price when neither is available |
| Qalb | Keyword tone rules with a neutral default | A tone hint, not a measured emotional state |
| Lubb / Yaqin / Mizan | Text rules and internal inference labels | Heuristics, not independent factual verification |
| Ruh workload | Task-complexity and idle-time counter | Dynamic internal workload, not CPU use, trained weights or intelligence |
| Nafs stage | Agent policy state | Available tools and turn limits, not a validated capability benchmark |
| Rule flags | Patterns found by the self-check | Zero flags does not establish zero errors |

The previous `Health 100%` and `Hallucination 30%` values can appear even for a
known incorrect answer such as `2 + 2 = 5`. They are not measured accuracy or
server-health rates. The chat UI therefore says **Accuracy / hallucination rate:
Not measured** and describes the remaining diagnostics as heuristics, including
when rendering older messages.

Owned checkpoint details identify the registry generation and verified artifact
selected for a request. Selection alone does not prove generation completed or
that the answer is correct. See [the owned learning lifecycle](own-learning-cycle.md)
for the separate training, evaluation, activation and rollback receipts.
