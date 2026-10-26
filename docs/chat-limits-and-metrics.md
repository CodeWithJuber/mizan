# Chat output limits and metric provenance

An answer that contains only a length-limit warning is not a successful answer.
Mizan now rejects an empty, length-limited provider response with the safe
`output_budget_exhausted` code. It does not replay tools, count that result as
successful learning, or substitute private provider reasoning for answer text.
Visible truncated answers may use at most two text-only continuations.

The per-call output budget defaults to 4,096 tokens. Configure it with an agent's
`max_output_tokens` setting or `MIZAN_CHAT_MAX_OUTPUT_TOKENS`; the allowed range
is 256–16,384. Emotion/tone rules no longer determine this budget. These are
application bounds, not a promise of unlimited answers or provider availability.

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
