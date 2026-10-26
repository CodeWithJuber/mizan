# Owned learning cycle

This lifecycle trains Mizan's local reply weights from an approved original-data snapshot, measures a candidate against a fixed development suite, and atomically activates or rejects it. A previous selection can be restored without replacing checkpoint files. OpenRouter is not called by the cycle.

Learning is off by default. No production corpus or trained checkpoint is manufactured from the research archive, old chats, reviewed model answers, or unit-test fixtures. The Ruh Model page's **Own learning** panel shows setup, watch state, bundles, runs, and rollback separately from hosted-model training.

## Activation and controls

Set `MIZAN_OWNED_LEARNING_DIR` to a private persistent directory outside the application source tree, for example `/data/mizan/owned_learning`. Leaving it unset keeps this registry integration unconfigured. Configuring a directory does not itself authorize training: a valid enabled policy and an approved bundle are also required. First-model activation additionally requires `allow_first_model: true` in that policy.

`MIZAN_OWNED_LEARNING_AUTORUN` defaults to `false`. When explicitly enabled, the watcher checks for approved ready bundles every 60 seconds and uses the same bounded cycle and admission gates as a manual run. It does not approve data, relax the policy, or turn conversation activity into training permission.

Authenticated admin controls are:

| Operation | Interface |
|---|---|
| Inspect configuration, bundles, runs and active generation | `GET /api/owned/learning` |
| Run one approved bundle | `POST /api/owned/learning/run` with `{"bundle_id":"approved-v1"}` |
| Restore the previous selection | `POST /api/owned/learning/rollback` with the currently observed `expected_generation` |

The module API is `status(root)`, `list_bundles(root)`, `run_cycle(root, bundle_id)`, `rollback(root, expected_generation)`, and `resolve_active(root)`. A successful active resolution supplies the immutable checkpoint path, its SHA256 and registry generation. Invalid artifacts fail closed.

From the repository checkout, the equivalent CLI commands are:

```bash
PYTHONPATH=backend:. python -m mizan_owned.learning_cycle status --root /data/mizan/owned_learning
PYTHONPATH=backend:. python -m mizan_owned.learning_cycle digest --root /data/mizan/owned_learning --bundle-id approved-v1
PYTHONPATH=backend:. python -m mizan_owned.learning_cycle run --root /data/mizan/owned_learning --bundle-id approved-v1
PYTHONPATH=backend:. python -m mizan_owned.learning_cycle rollback --root /data/mizan/owned_learning --expected-generation 2
```

The production image places `mizan_owned` directly under `/app`; there, use the same `python -m mizan_owned.learning_cycle` commands without the checkout `PYTHONPATH` prefix. Runtime sources and their 12-file manifest are packaged for verification; the pinned trainer and model sources are not rewritten by this integration.

## Bundle and original-data review

Place a bundle at `<root>/bundles/<bundle_id>`. IDs contain letters, digits, underscores or hyphens and are at most 64 characters. The bundle contains exactly these fixed inputs plus the referenced files beneath `assets/`:

| File | Purpose |
|---|---|
| `train.jsonl` | Accepted original training records, all declaring `split: "train"` |
| `dev.jsonl` | Accepted development/regression records, all declaring `split: "dev"` |
| `sources.jsonl` | Source declarations and exact original-asset hashes |
| `config.json` | Explicit bounded model configuration and CPU training settings |
| `approval.json` | Operator review bound to the bundle digest |
| `assets/...` | Exactly the original assets referenced by the source manifest |

Extra top-level files, test files, unrelated assets, symlinks and escaping paths are refused. The cycle copies and rechecks all inputs before training. It consumes the private snapshot, not the editable bundle directory.

Records follow `mizan.reply.v1`; start from [record.template.json](../research/own_model/schemas/record.template.json) and [source.template.json](../research/own_model/schemas/source.template.json). Placeholder text is rejected. A record identifies its conversation/passage group, language, task, input messages, evidence and separate target. Its provenance includes rights, source IDs, an accepted review and named reviewers. `human_original` needs named authors distinct from its reviewers. `source_transcription` requires an explicit transcription method and extraction lineage. Source assets must exist and match their declared SHA256; evidence text has its own exact-byte hash.

`machine_draft` and `machine_generation` remain ineligible even when somebody marks the answer reviewed. Accepting an OpenRouter answer or an owned-model reply into reviewed memory does not change its authorship and does not make it original-data gold. This cycle does not consume those review exports. Hashes and review declarations establish identity and accountability; they do not independently prove authorship, source authenticity, religious interpretation or factual correctness.

After preparing and reviewing the fixed inputs, obtain the digest with the `digest` command. Create `approval.json` only for the exact reviewed digest:

```json
{
  "schema_version": "mizan.owned.learning.approval.v1",
  "bundle_sha256": "<exact digest returned by the command>",
  "approved": true,
  "original_data_attested": true,
  "reviewer_id": "<actual-reviewer-id>",
  "evidence": "<actual review evidence and original-data basis>"
}
```

The angle-bracket values above are documentation placeholders, not approval evidence. `approval.json` is excluded from the input digest; its own hash is recorded in the run receipt. Exact private copies of the approval and policy are retained with the candidate and checked when resolving an accepted artifact. Editing an input or asset changes the digest and invalidates the approval; revoking or changing approval during a cycle prevents activation.

The supplied `reply_small.json` configuration uses automatic device selection. For this lifecycle, explicitly set `training.device` to `"cpu"` and use `amp: "none"` before computing the bundle digest. All model fields must be explicit. The wrapper bounds dimensions before model allocation and the pinned preflight validates the configuration and encoded lengths.

## Admission policy

The operator supplies `<root>/policy.json`. There are no permissive admission defaults: every gate must be present. This disabled example shows the schema; its numerical thresholds are an illustration, not a validated benchmark recommendation:

```json
{
  "schema_version": "mizan.owned.learning.policy.v1",
  "enabled": false,
  "allow_first_model": false,
  "gates": {
    "min_train_examples": 100,
    "min_dev_examples": 20,
    "max_dev_hinge": 0.5,
    "min_dev_byte_accuracy": 0.95,
    "min_generation_exact_match": 0.9,
    "min_generation_eos_rate": 1.0,
    "max_hinge_regression": 0.0,
    "max_byte_accuracy_drop": 0.0,
    "max_generation_exact_drop": 0.0
  }
}
```

Choose and review the policy before examining candidate results. Enabling the policy permits activation only when all absolute gates pass, and when a current model exists, all comparison gates also pass. Setting `allow_first_model` authorizes the first candidate to be judged by the absolute gates; it does not bypass them.

The cycle measures every development record with a fixed generation budget. It records teacher-forced hinge loss and byte accuracy, plus complete generated exact matches and EOS completion. A target match without EOS is not a complete generated exact match. The current active checkpoint is evaluated on the same development suite; failure to load or evaluate it rejects the comparison instead of assigning it a zero score. EOS completion cannot regress; permitted hinge, byte-accuracy and generated-exact changes are explicitly bounded by policy.

After first activation, the development identity is frozen: exact `dev.jsonl` bytes, its referenced source declarations/assets, generation budget, and hinge-margin convention. Changing it requires a separately reviewed evaluation design, not silently treating a new suite as comparable. This suite is repeatedly used to select models, so it is **development/regression data, not an untouched test set**. The learning cycle never loads `test.jsonl`. A separate frozen-release evaluation may use an untouched test set; feeding its results back into repeated selection would spend that holdout.

These gates demonstrate measured behavior on the declared suite. Byte prediction, exact matches, completion rate, optimizer steps and accepted status are not evidence of general conversational competence, factual reliability, Quranic authenticity or AGI. Receipts retain `factual_accuracy_established: false` and `ready_for_general_chat: false`.

## Fresh training, promotion and rollback

Each new bundle trains fresh weights from its complete approved snapshot. Later snapshots must retain every training row and source declaration of the currently active version unchanged, then add reviewed originals as needed. The fixed development suite remains separate. This retention check prevents this particular lifecycle from quietly replacing its accumulated training set. Corrections or removals of previously admitted rows need an explicit data-revision design; do not rename records to hide changed lineage.

The pinned trainer's `--resume` supports exact epoch-boundary continuation only: its train/dev/source hashes, architecture, update settings, runtime and topology must match. It cannot resume on newly added data. This integration does not relabel changed data as exact resume or fabricate a parent checkpoint manifest. Warm-start learning on new data would require a separate, honestly recorded lineage and optimizer contract.

One nonblocking writer lock covers the entire cycle. Concurrent runs and rollback return busy until the bounded worker ends. The cycle validates the source pins, creates and verifies an immutable snapshot, runs CPU preflight and training, and copies the completed checkpoint into a separate read-only artifact. It evaluates the candidate, records the admission decision and its hashes, rechecks the policy and registry generation, then atomically replaces `registry.json` when accepted. It never promotes an incomplete training file.

Candidates live under `<root>/candidates/<bundle_sha256>/`, with the snapshot, worker results, reports, immutable `checkpoint.pt` and receipt. Identical bundle bytes are idempotent: rerunning returns the existing receipt rather than silently training again. An incomplete previous attempt is recorded as interrupted and cannot silently resume or activate. `accepted` records a passed candidate decision; use the returned `activated` flag and current registry generation to establish which checkpoint is actually selected.

Rollback requires the generation the operator just observed, verifies the prior artifact, and atomically restores that selection while incrementing generation. A stale generation is refused. The first activation can be rolled back to no active checkpoint. A broken current checkpoint does not prevent retreat to a valid predecessor. Provider requests resolve the registry selection and use the matching checkpoint digest, allowing both activation and rollback to take effect without silently retaining a stale model. Registry-managed inference continues to label generated replies as unverified.

## Resource and failure bounds

The defaults are local CPU only, one CPU thread, a 4,096 MiB process address-space ceiling, at most 900 seconds for a cycle, 60 seconds for preflight, 600 seconds for training, and 120 seconds per evaluation stage. The cycle deadline bounds the total; individual stage maxima are not an entitlement to exceed it. Defaults also limit input files to 16 MiB each, the bundle to 64 MiB/512 files, training to 2,000 records, development to 128 records, parameters to 5 million, and generation to 64 byte/EOS tokens per record. `limits` overrides are validated against fixed upper bounds; they cannot enable CUDA or remote compute.

These limits do not create extra server capacity or provide a separate machine. Admission requires observable bounded cgroup-v2 memory headroom for the worker allowance plus a 512 MiB API reserve, including controlling ancestor usage. Unknown or insufficient headroom is a refusal, not an assumed capacity. This is a conservative admission check, not a memory reservation or an isolation boundary; other activity can still change available resources. In particular, a backend container limited to 2 GiB cannot be treated as having the default 4 GiB training budget. No production learning runs automatically just because code or a research archive was deployed.

The Linux worker has address-space, CPU, file-size and descriptor limits, inherits the writer lock, and is killed if its parent dies. Timeout and handled cancellation terminate and reap its process group before the cycle releases its own lock or reports completion. Failed validation, training, evaluation or admission leaves the selected checkpoint unchanged. Before-commit interruption does not activate a candidate. An error or cancellation after the atomic selection commit is reconciled against the actual registry and can return accepted/activated with a `completion_note`; `activation_durability_confirmed` is true only after successful re-fsync and otherwise remains false. Source changes, corrupt artifacts and incomplete state are refusals, not reasons to fall back to hosted inference or to invent a successful training result.

After a crash, inspect `status`, the immutable candidate receipt and the active registry generation before retrying or repairing state. Do not delete registry files or candidate artifacts to force admission. Test fixtures exercise these mechanics in temporary directories and are never an approved production corpus.
