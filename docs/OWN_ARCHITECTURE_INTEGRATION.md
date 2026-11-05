# Mizan owns inference; OpenRouter supplies requested support drafts

Owned mode is opt-in. Since 2026-10-26 the default Compose configuration and
`.env.example` use `LLM_PROVIDER=auto` and `MIZAN_OWNED_ONLY=false`; set the
values under [Runtime configuration](#runtime-configuration) to select
`mizan-owned`. The existing agent loop, permissions, authenticated users and provider API remain
the entry points. `MIZAN_OWNED_ONLY=true` prevents provider autodetection, saved
provider preferences and per-message model overrides from selecting hosted
inference. Selecting `LLM_PROVIDER=mizan-owned` also enables this boundary.
The optional mem0 external extraction/embedding path is disabled in owned mode.
Turning `MIZAN_OWNED_ONLY` off in Settings → Developer → System settings rebuilds
every agent from `LLM_PROVIDER` and `DEFAULT_MODEL` and saves that as the provider
preference restored at start-up. Until then the saved `mizan-owned` preference keeps
agents on the own model after a restart, even with `LLM_PROVIDER=auto`; switching
provider under Models & providers also clears it.

Normal inference runs reviewed exact-context memory, then the local Mizan reply
core, then an explicit abstention. It never calls the support adapter. Output
from the reply core is marked `own_model_unverified`; it cannot issue tool calls
or certify itself. The existing agent/security architecture still controls the
host tools. This release does not pretend the research decoder can independently
plan and execute arbitrary tasks.

## Research integration and provenance

| Research component | Integration status |
| --- | --- |
| Corrected 24 October causal byte reply core | Exact source in `mizan_reply/`; real provider adapter, trainer, evaluator, checkpoint and decoder |
| Stage 30 finite context and existential episode reasoning | Exact source in `mizan_research/`; bounded authenticated context API with explicit observations and retraction |
| Stage 30 context revision and candidate elimination | Preserved supporting source; no automatic natural-language interpretation or schema migration |
| Earlier ZIPs, chat exports, proofs, counterexamples, root experiments and data | Pinned complete bundle importer, full source inventory and local searchable index |
| OpenRouter | Explicit admin support endpoint; text proposals only, no tools, no chat fallback |
| Reviewed learning | User-scoped exact-context memory, hash-bound review, correction and retraction |
| Neural learning | Original-data training CLI is executable and tested; no automatic training or checkpoint promotion from chat |

`research/registry/runtime_sources.json` pins the SHA256 of every copied runtime
source. The source inventory covers 131 collected entries, 130 distinct
filename/hash pairs and 44 unique ZIP byte versions. The consolidated bundle
preserves 22,706 distinct recursive leaf contents with zero missing source
hashes in the merge audit. Nested archive containers are not guaranteed to be
reconstructible byte for byte. Exact contents and origins remain traceable.

The full bundle is kept outside Git because it contains 241,577,161 bytes. Import
the delivered `Mizan-Full-Architecture-Integration-2026-10-24.zip`:

```sh
python -m backend.mizan_owned.research /path/to/Mizan-Full-Architecture-Integration-2026-10-24.zip --destination data/research
```

Required SHA256:
`0fda16988214d7949592d018b9edab5157d6e7a0b437d74f1d155d164e6531f6`.
The archive includes `Mizan-Full-Reverified-2026-10-23.zip`'s recovered content.
The importer checks the pinned bytes, paths, symlinks, member count and size;
extracts into a new directory; and never executes or unpickles research files.
The verified import contains 21,486 members and indexes 7,665 UTF-8 text files.
Larger text files, binaries and nested ZIPs remain preserved without all being
indexed. Historical contradictory results remain historical, not training gold.

For Docker, import into the mounted `/data/research` volume and set
`MIZAN_RESEARCH_DIR=/data/research`. The archive itself is not fetched from the
network or baked into an image. Changing the archive requires an explicit new
pin and audit, not a bypass argument.

`GET /api/owned/research/search?q=metric%20inconsistency` returns path, source
hash and exact excerpts for an admin. Search is local SQLite FTS, not a model
answer. Consult `research/RESEARCH_LEDGER.md` before interpreting old results:
Δ_A's aggregate inconsistency is unresolved, 0.766751 is an audit bound rather
than measured accuracy, Δ_Q was negative, and the four-root bank had a shortcut.

## Runtime configuration

```dotenv
LLM_PROVIDER=mizan-owned
MIZAN_OWNED_ONLY=true
DEFAULT_MODEL=mizan-owned
MIZAN_OWNED_DB=data/mizan_owned.sqlite3
MIZAN_RESEARCH_DIR=data/research
MIZAN_REPLY_CHECKPOINT=
MIZAN_SUPPORT_MODEL=
```

Set `MIZAN_REPLY_CHECKPOINT` only to a trusted local checkpoint from the included
reply trainer; install PyTorch from the existing `ml` extra for local inference.
No checkpoint ships in this change. Missing, malformed, over-budget, incomplete
or invalid-UTF-8 generations abstain without a remote fallback. The supported
checkpoint format is the corrected byte model, not MiniMind or Ruh weights.
Health distinguishes a running controller from a useful general-chat model;
`ready_for_general_chat` remains false because that ability is unmeasured.

Legacy providers remain available when operators deliberately disable owned
mode and choose a different `LLM_PROVIDER`. There is no implicit change of mode
when the owned model fails. Unrelated explicitly requested legacy model routes
remain separate services; they are not used by the owned chat pipeline.

## API and review workflow

All routes require the existing JWT/API-key authentication. Support, review,
retraction, research search, export and learning also require an admin role
(`_ADMIN_PREFIXES` in `backend/api/main.py`). The ledger owner and
reviewer come from the authenticated principal, never a model-supplied flag.

1. `POST /api/owned/chat` accepts `{"system":"","messages":[{"role":"user","content":"..."}]}`.
   The existing chat/streaming agent path also uses the owned provider.
2. Explicitly call `POST /api/owned/support` with the same request when teacher
   assistance is wanted. Configure `OPENROUTER_API_KEY` and
   `MIZAN_SUPPORT_MODEL` beforehand. Only this operation sends the supplied
   prompt to OpenRouter. Its result is a **draft proposal**, never a normal-chat
   answer, tool instruction or training-gold record.
3. Inspect `GET /api/owned/reviews`. Review via
   `POST /api/owned/reviews/{id}` with `expected_hash`, `accepted` and `evidence`.
   Conflicting accepted answers require an explicit `supersedes` proposal ID.
   Incomplete drafts cannot be accepted. Reviewer identity is server-bound.
4. An accepted complete proposal can be replayed for the same owner and exact
   full request. Different context, system instructions or user identity cannot
   reuse it. This is memory learning, not generalization or a truth certificate.
5. `POST /api/owned/retract` with `{"evidence":"..."}` withdraws matching active
   lessons immediately. Rejected, superseded and retracted rows do not export.

`GET /api/owned/export` emits reviewed-memory records, not the original-data
training format. The legacy capture exporter excludes `mizan-owned` and
`mizan-support` outputs so model drafts cannot silently enter its permissive
quality-score pipeline. The current admin review UI is the API; normal users
cannot review or access another principal's ledger.

`POST /api/owned/context/resolve` accepts a declared `ontology`, `senses`,
`language`, `symbol`, query `context`, `observations` and optional `retract_ids`.
Default `mode="finite"` requires complete contexts for observations.
`mode="episodic_exists"` explicitly permits partial historical episodes with
existential semantics. Domains are capped at 256 cells and existential search
at 5,000 nodes. Ambiguity, conflicting evidence and resource exhaustion are
reported rather than guessed. The result is conditional on supplied labels and
schema completeness; it is not proof of free-text understanding or hidden intent.

## Growing the owned model

The original-data contract has deliberately been preserved: machine-authored
teacher output is not original-data gold even after an accepted review. Teacher
support can help find sources, propose annotations and diagnose errors. Prepare
independently reviewed human/source records with rights and provenance for
actual weight training. Do not relabel a teacher answer as human authorship.

The one exception is the owner's decision of 30 Oct 2026 (`docs/consent.md`):
a teacher's answer that MIZAN verified, from a teacher whose licence allows
training on its output, may be a target as a `licensed_teacher` record. It
names the teacher, the licence and the MIZAN check that passed, still needs an
accepted review, and is never grounded on Quran or hadith sources. Anthropic
and OpenAI output never qualifies.

```sh
python -m mizan_reply.cli preflight --train-data data/train.jsonl --dev-data data/dev.jsonl --sources data/sources.jsonl --config research/own_model/configs/reply_small.json --output-dir data/candidate
python -m mizan_reply.cli train --train-data data/train.jsonl --dev-data data/dev.jsonl --sources data/sources.jsonl --config research/own_model/configs/reply_small.json --output-dir data/candidate
python -m mizan_reply.cli evaluate --checkpoint data/candidate/latest.pt --train-data data/train.jsonl --dev-data data/dev.jsonl --sources data/sources.jsonl --data data/test.jsonl --split test --output data/candidate/test-report.json
```

The CLI validates original source assets, partition leakage, byte budgets and
checkpoint identity. `--resume` is exact continuation: it refuses changed data,
configuration, runtime or topology. It is not a warm-start shortcut for a new
dataset. New data needs a new training run; a safe migration/warm-start workflow
is future work. Hold out independent evaluation before selecting a candidate.
To deploy a reviewed candidate, set the local checkpoint path and restart;
rollback restores the previous path and restarts. No candidate is auto-promoted.

## Acceptance and limits

Tests cover owned routing, scoped replay, spoofed-review rejection, explicit
corrections, retraction, teacher/tool isolation, authenticated HTTP routes,
finite/existential ambiguity, pinned source hashes, safe archive import and the
real checkpoint adapter. The research suite exercises actual tensor
updates, causal/cache invariants, Unicode decoding and exact resume.

Full independence is a development target, not an achieved capability or a
guaranteed date. This integration moves orchestration and the implemented
reasoning/learning mechanisms into owned code. Useful open-ended language,
autonomous tool planning, universal root semantics and general accuracy still
need data and independent evaluation. Archived experimental programs are not
automatically live algorithms merely because their bytes are present.

The distributed parity test uses the same `rtol=2e-6, atol=2e-7` for loss metrics
as for parameters. The original archive used absolute tolerance alone for
metrics; GitHub CPU execution exposed a 3.95e-7 reduction-order difference at
loss 2.57. Exact token/sample counts and all parameter comparisons remain
checked. The 12 runtime source files are unchanged; this adjustment is confined
to test portability.
