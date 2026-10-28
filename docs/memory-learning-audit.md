# Memory and learning audit

> Dated record (October 2026, after PR #101). It describes the code as it was then; the current architecture is in [architecture.md](architecture.md) and its [diagrams](diagrams/README.md).

The old quoted greeting is historical evidence. It does not establish that the
same greeting was emitted after PR101. The audit found a current missing durable
preference path and an unsafe legacy capture export contract independently of
that quote.

## Distinct operations

| Operation | Actual behavior | Does it update model weights? |
| --- | --- | --- |
| Conversation history | Saves messages and restores owned sessions | No |
| Cross-session recall | Selects up to five relevant/recent user messages from the last 200 in other owned sessions | No |
| Explicit chat preferences | Stores owner-scoped language, greeting, avoided greetings and custom instructions until replaced or deleted | No |
| Learner capture | Saves successful observed model responses as private, unreviewed candidates | No |
| Candidate review/export | Records an explicit reviewer decision bound to the exact captured content; exports model authorship and review evidence | No |
| Owned reviewed memory | Replays an accepted answer for an exact owner/request match | No |
| Training | Runs a separately requested training process over supplied data and produces checkpoints | Yes, for that training run |

Preference storage does not infer religion or identity from a greeting, copy old
assistant claims, or automatically turn ordinary chat into persistent
instructions. Preferences are explicit user choices. They must be injected as
user-level instructions with the current request taking precedence. They do not
become system policy, verified facts, or training data. Deleting a saved
preference removes that preference record; it does not erase separately retained
chat history.

## Fixed storage/export defects

- Durable preferences now use a separate `chat_preferences` table keyed by
  authenticated owner and preference key. Global provider configuration is not
  reused as a user profile. Tests cover process restart, more than 200 subsequent
  messages, replacement, deletion, bounds and cross-owner isolation.
- The capture export previously defaulted to quality 0, so new unreviewed model
  answers could be emitted as plain training text. A numeric quality score could
  also be counted as reviewed despite there being no reviewer evidence.
- Export now requires an accepted review, authenticated reviewer identifier,
  evidence, and a content hash matching prompt, response, provider and model.
  The default quality threshold is 0.8. Lowering the threshold explicitly never
  bypasses review. Changing a score invalidates its prior review.
- Exports use the `reviewed_model_interaction` schema with `prompt`,
  `model_response`, model authorship, capture/review timestamps and review
  evidence. `original_data_eligible` and `independently_verified` remain false.
  They deliberately omit the `text`/`messages` fields consumed by training
  loaders. Review does not transform a generated answer into an original source.
- `mizan-owned` and `mizan-support` responses remain excluded from this legacy
  exporter even after review. The existing owned-memory review ledger is a
  separate operation.

## Migration

`RuhLearner.initialize()` adds review columns and an append-only decision log in
one SQLite transaction. Existing captures, metadata and quality scores are kept.
Historical quality-only rows receive `review_status='unreviewed'`; there is no
automatic approval or backfilled reviewer. Reinitialization is idempotent. A
direct export of an unmigrated store returns no reviewed records and does not
rewrite the store. Old exports in the permissive training-text format should not
be treated as reviewed original data merely because they already exist.

The chat preference table is added during normal `DhikrMemorySystem`
initialization. No legacy conversation or global configuration is silently
adopted as an owner's preference.

## API integration and remaining limits

The authenticated API must derive owner/reviewer identifiers from the session.
It must not accept another owner's ID from a request body. Chat transports share
the same preference retrieval through `chat_context`; the settings UI must save
and delete the same owner-scoped records. The learner export endpoint must create
`DataExporter(learner.db_path)` for `RuhLearner.for_owner(user.user_id)` and use
`records()` or `export_jsonl()`. The old zero-argument constructor and `.export()`
method do not exist.

The optional mem0 integration is disabled by default and uses session IDs, so it
does not substitute for durable cross-session user preferences. Unowned legacy
sessions are excluded from automatic cross-session recall; importing them needs
explicit ownership attribution. Normal non-admin chat gets a private Dhikr DB;
other endpoints that call global agents need their own equivalent authorization.

The dashboard's training launcher is a separate legacy Ruh training path. It
previously always passed `--generate-data`, writing root/concept seed examples
before training. Seed generation now requires explicit `generate_seed_data=true`
and the UI starts with that option unchecked. A normal run requires nonempty
supplied JSONL and refuses known `seed_roots.jsonl`/`seed_concepts.jsonl` files
unless the generated-example option is chosen. This filename check identifies
known scaffolding; it is not provenance verification of arbitrary supplied data.
Status/history label inputs as `supplied_unverified` or
`generated_seed_examples`, with `original_data_verified=false`. This launcher
is not the provenance-checked `mizan_reply` original-data CLI.

A child's completion event no longer records success before its process exits.
The actual exit status decides completed/failed, launch failures clear the
running flag, and start/stop operations are serialized. The dashboard labels
exportable items as reviewed candidates and an untracked export time as "Not
tracked", rather than asserting no export ever occurred.

A checkpoint file existing does not prove it is loaded, selected for chat,
evaluated, or capable of replacing the external model.

Further model development requires independently sourced, rights-compatible
training records, separate evaluation data, recorded training runs, demonstrated
quality, and explicit checkpoint selection. Chat capture and review do not
automatically provide those prerequisites. No automatic weight training,
checkpoint promotion, or general intelligence is claimed by these changes.

Validation for this storage change: 53 targeted tests passed across preference,
learner review, existing learner, owned-provider and memory suites. Ruff passed;
targeted mypy passed using a fresh cache directory.

Training follow-up validation: 20 targeted tests passed, including seven new
manager cases and the existing stderr-drain regression, with overlap in the
memory/learner tests above. The new tests mock model subprocess creation; no
training run is launched. Ruff, targeted mypy and frontend type checking passed.

Integration validation: 70 existing comprehensive memory/runtime tests and
three API tests passed. API tests cover persisted preference deletion, owner
isolation through SSE, forged owner/reviewer fields, authenticated candidate
review/export and the explicit training seed flag. The API tests mock model
execution and training launch.
