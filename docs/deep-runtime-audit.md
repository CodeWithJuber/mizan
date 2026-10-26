# Runtime audit and repairs

Post-deployment results, including the active isolated runner and full research
import, are recorded in [production validation](production-validation-2026-10-25.md).

This audit separates historical transcripts, repository coverage, executable
paths, and observed production state. A historical greeting is not evidence of
a regression after a later deployment. Greeting and language preferences belong
to the authenticated user; they are not a global religious judgment or a hidden
identity hardcoded into the application.

## Observed baseline

The earlier chat repair PR #101 deployed commit
`03aa5b7cfd06fe4c3233089350cfa45ff9352cb9`. Its deployment log confirms application
health and anonymous-authentication denial. Authenticated browser inspection then
showed 263 saved messages in 13 owned conversations. The separate knowledge-record
list was empty. These are different stores, not evidence that transcripts were lost.

The Ruh dashboard reported a checkpoint path present, no loaded local chat model,
and OpenRouter's configured Nvidia model as the active chat generator. A configured
remote endpoint had not been checked for liveness. The workspace page reported no
configured isolated runner. Those observations do not establish successful code
execution, local inference, training, or general intelligence.

## Reproduced problems and changes

| Path | Reproduced problem | Change and boundary |
| --- | --- | --- |
| Preferences | Transcript recall ages out and cannot reliably preserve explicit reply preferences. | Owner-scoped preference CRUD, prompt injection as user-level attributed preferences, and editable Memory controls. Current corrections take precedence. |
| Provider settings | Cached private agents keep stale configuration; model IDs and saved per-agent settings are inconsistent. | Revision-aware refresh waits for the execution lock; provider IDs are normalized and per-agent overrides persisted. A global switch clears those overrides. |
| Provider completion | SDK waits default to long retries; partial EOF and malformed tool arguments can look successful. | Configurable bounded network waits, zero SDK retries by default, explicit completion receipts, and rejection of invalid tool arguments. Healthy streaming has no artificial total-duration deadline. |
| Tool invocation | Catching an arbitrary function-body `TypeError` can run a side effect twice. | Bind arguments before one invocation; no implicit host package installation or retry after a tool body executes. |
| Completion metrics | Abstention, empty/tool-only output and partial summaries can become successful lessons. | Preserve observed completion status across API/storage/UI; abstentions, missing receipts and incomplete output do not become positive lessons or learner captures. Delivered text does not establish verified task success. |
| Ruh heuristic | Reading energy repeatedly credits the same elapsed time; a synthetic energy gate blocks ordinary chat. | Credit elapsed time once and keep energy advisory. It is not a resource-availability measurement. |
| Workspace dispatch | Nonadmin users cannot invoke their permitted workspace tools; selected admin projects can still dispatch host-execution aliases. | One trusted-handler policy filters schemas and dispatch. Selected projects expose isolated workspace tools and bounded memory helpers. |
| Preview | JS/TS use the wrong runtime; other languages open template files; artifacts leak between selected chat views. | Correct source entry/runtime, current-session filtering, newest-version selection and accurate file extensions. |
| Learning export | Numeric scores alone admit unreviewed model output; the API calls a nonexistent exporter method. | Explicit owner-bound review of an immutable content hash, working JSONL streaming, and model-authorship provenance. Exported candidates are deliberately not training-text records. |
| Manual training | The manager always generates seed fixtures; a child `complete` message can hide later process failure. | Supplied data by default, explicit seed opt-in with provenance labels, and success only after a zero exit status. |
| Council | Shared-agent evaluation bypasses execution locking and can expose global memory to ordinary users. | Administrative endpoint boundary and locked, no-tools council evaluation. |
| Legacy chat transports | WebSocket task/multimodal branches bypass administrative ownership; failed socket writes do not stop execution; raised REST setup errors leave no terminal event. | Match HTTP role restrictions, cancel on failed socket delivery, preserve partial status, and terminate raised execution failures without replay. |
| Owned reply model | The normal agent system prompt exceeds every shipped 2048-token byte-model context. | Explicit host-owned compact rendering, original-request review identity, preserved user context, measured input/output budgets and understandable overflow abstention. Arbitrary system text is never silently truncated. |

## Research coverage and capability boundary

The audit verified all 12 source hashes in `research/registry/runtime_sources.json`.
The Reverified archive manifest accounts for 2,363 recursive leaf occurrences:
2,349 already included, 11 recovered, and 3 previously recovered. Its top-level
comparison contains 255 identical records and 15 records corrected in a later
release. These are manifest and source-hash checks, not a fresh verification of
every original ZIP byte or the server's imported archive.

The pinned importer requires consolidated bundle SHA-256
`0fda16988214d7949592d018b9edab5157d6e7a0b437d74f1d155d164e6531f6` (241,577,161
bytes). Another upload has the same filename but different bytes; substituting it
must fail verification. Archive preservation alone does not execute its algorithms
or train weights. The research ledger retains unresolved metric inconsistencies,
negative pilot results and benchmark contamination concerns.

Mizan's orchestration, private memory, tool dispatch and bounded symbolic algorithms
are executable software. When OpenRouter is selected, it still generates language.
Hybrid mode also invokes a base generator. Owned mode has no hosted fallback and
can replay exact reviewed requests, invoke an explicitly supplied local checkpoint,
or abstain. Tiny fixture checkpoints in tests prove integration, not conversational
quality. No production model training or automatic checkpoint promotion is implied
by these repairs.

Research tools expose attributed pinned-index retrieval and typed finite/existential
context resolution to authorized normal chat. The resolver is stateless and only
reasons over the supplied schema and observations; it cannot certify that those
observations are true. An unimported archive yields an explicit unavailable result.

## Operational verification

Run `make check` with a healthy isolated mypy cache, Ruff's format check, frontend
typecheck/build and utility checks. CI additionally builds the isolated Docker
images and performs actual code execution, plotting and file/artifact checks.
The rootless production runner has separate provisioning, rollback and host smoke
verification described in `docs/runner-setup.md`; a running container alone is not
the acceptance criterion.

## Remaining latency attribution

Two successful browser requests after the later application deployment exposed
a timing gap. The first applied the saved salaam/Hinglish preferences and answered
`6 × 7 = 42`; its observed completion was `end_turn`, with `answer_delivered=true`
and `task_verified=false`. A later research request returned actual imported paths
including `PACKAGE_CONTENTS.json` and `HF_LINKS.md`, attributed to
`pinned_research_archive`.

| Observed request | UI total | Recorded provider time | Unclassified difference |
| --- | --- | --- | --- |
| First greeting/calculation | 59.2 s | One completed call: 12,944.3 ms | About 46.3 s |
| Research lookup | 75.7 s | Three completed calls: 11,975.7 + 5,903.8 + 3,232.8 ms | About 54.6 s |

These differences are not measured cognitive computation or demonstrated cold
starts. The trace starts before context preparation and agent-lock acquisition;
provider usage records completed provider receipts, excluding queue waits and
failed attempts without a receipt. Admin sessions share their agent template;
nonadmin sessions share a private instance keyed by owner and template, not by
chat session. The execution lock covers the entire request, including learning
capture. Concurrent message growth was observed, making queue contention
plausible, but the production traces do not prove that it accounts for these gaps.

A controlled local probe held the first request's provider for 250 ms. A second
request to the same agent took 257.1 ms overall, emitted its first thinking event
after 253.7 ms, and recorded one provider call of 0.4 ms. This reproduces the
queue/receipt timing mismatch without network access. It is not a production
performance measurement.

The research tool searches an already-built local FTS index in a worker thread;
it does not extract/reindex the archive or load a language model. Its declared
input accepts `query` only and results are capped at eight. The browser prompt
also requested `limit=2`, so a parameter-correction turn is possible; the two
`tool_use` receipts alone do not prove the exact arguments or their duration.
Memory graph traversal and secondary persistence also lack per-phase timings.

The bounded next repair is observability: expose monotonic `queue_wait_ms`,
`context_build_ms`, every provider attempt's duration/outcome, tool durations,
`finalization_ms` and total server time. Emit and render per-request `queued` then
`running` status; the current frontend ignores ordinary status events except the
buffered-provider hint. Preserve the execution lock and cancellation behavior.
If a queue-wait deadline is introduced, it must apply only before lock acquisition,
report that no model/tool execution started, and never interrupt an active provider
or automatically resubmit a request. No latency fix was applied during recovery.

Remaining product boundaries include the ten-project quota with no archive UI,
single-file previews, self-contained HTML assets and the smaller image-artifact
size limit. Training toward provider independence still requires suitable data,
measured held-out evaluation and a deliberate checkpoint promotion decision.
