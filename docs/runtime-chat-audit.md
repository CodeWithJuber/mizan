# Chat, memory and workspace runtime repair

> Dated record (October 2026, PR #101). It describes the code as it was then; the current architecture is in [architecture.md](architecture.md) and its [diagrams](diagrams/README.md).

This is the historical PR #101 baseline. The runner and research import gaps
below were subsequently addressed; the production evidence was recorded in a
validation report that is not published.

The October 25 chat exports and authenticated production UI showed a working
web deployment with incomplete runtime integration. A passing health probe
establishes service availability, not memory, inference quality or code execution.

| Area | Observed failure | Repair / remaining requirement |
| --- | --- | --- |
| Chat errors | Upstream 502 errors became assistant text and successful task records | Provider failures propagate as terminal errors; visible partial output and completed tools prevent full-task retries |
| Continuity | Chat routes omitted session IDs; WebSocket sessions lost history after restart; history restoration selected the oldest 50 messages | All chat transports pass session IDs, latest chronological history and bounded user-scoped conversation recall |
| Memory provenance | Saved chat history was not recalled across sessions | Recall includes up to five recent/relevant user statements from the owner's last 200 messages in other owned sessions, with source IDs and timestamps; assistant claims and unowned legacy sessions are excluded |
| Learning dashboard | Stats constructed `RuhLearner` without its required database argument; main chat did not capture pairs | Successful observed model replies become private unreviewed candidates; dashboard reads that same owner store and polls it |
| Model status | `loaded` was hardcoded false; enabled configuration was labeled active | Report observed in-process local load state, checkpoint existence, active response models and training state separately |
| Image preview | Binary PNG was opened through the text-file endpoint, so it never became selectable | Raster images select without text reads/saves and publish through decoder-validated artifacts |
| Chat artifacts | Model had to invent/provide the session ID; artifacts could disappear when later generation failed | Server binds the actual session, rejects mismatches and emits verified saved artifacts immediately after tool completion |
| Workspace steps | Same-turn file writes, runs and publishing were raced | Workspace tool batches execute in their supplied order; the prompt requires inspect/edit/run/publish receipts |
| Production execution | UI displayed “The isolated coding runner has not been configured”; Run was disabled | An isolated runner still needs provisioning/configuration; this patch does not enable a production Docker socket or host-shell fallback |
| Primary model | Production settings showed OpenRouter with `nvidia/nemotron-3.5-super-vl:free` | No model switch is hidden in this repair. Owned mode and an evaluated local checkpoint are separate deployment work |

## Capability boundary

Conversation recall, captured training candidates, reviewed memory and neural
weight training are different operations. Captured pairs have quality score zero;
they are not automatically approved, trained on or promoted. The dashboard's
exportable count requires the existing explicit quality review threshold and
excludes owned/support outputs. Automatic weight training and checkpoint
promotion are not implemented. A named checkpoint or configured endpoint is not
evidence that it can converse, code or use tools.

Quranic faculty names describe software modules. Their heuristic scores do not
establish AGI, consciousness, belief or factual/religious correctness. The prompt
now requires source verification before precise Quran quotations/references;
this is guidance, not a deterministic citation verifier.

Research archive provenance is documented in `OWN_ARCHITECTURE_INTEGRATION.md`.
Preserving research source files does not execute them. Its full pinned archive
must be imported into the server volume; this audit did not establish that the
production archive import exists. Owned mode currently uses reviewed exact-context
memory, a configured local reply decoder, or abstention. Turning it on alone does
not make a capable general-purpose model.

## Production acceptance after merge

1. Confirm the deployed commit, sign in and inspect actual response model metadata.
2. With one account, save a distinctive instruction in session A, start B and
   verify attributed recall. Another account must not see it. Repeat after restart.
3. Simulate a provider failure after a text prefix and after a completed tool:
   error status, preserved partial output, no repeated tool and no success lesson.
4. Publish a saved PNG and HTML/code file. Preview must open; image bytes must
   remain unchanged. A later provider failure must not hide the saved artifact.
5. Check that a successful model reply increments only that user's candidate
   count, leaves reviewed/exportable count unchanged, and starts no training job.
6. Follow `coding-workspaces.md` to provision an isolated worker. Require a real
   `workspace_run` receipt, generated file and preview before declaring execution
   ready. The main deployment currently updates backend/frontend images only;
   published runner images do not imply a running worker.
7. Evaluate any local checkpoint on held-out conversation, memory and coding
   tasks before replacing the primary response provider. Record the measured
   capability limits; no AGI claim follows from these checks.

## Validation for this repair

`make check`: Ruff and mypy passed; 1,135 Python tests passed and 8 environment-dependent tests were skipped. Frontend type checking, production build and all seven utility test files passed. The local checks did not exercise a live isolated Docker worker or paid model training. Authenticated production inspection established the active OpenRouter model and missing runner before this patch; the patched behavior still requires post-deployment verification.
