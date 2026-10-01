# Ruh sentence and dialogue training repair

The owner's private `zubairshaikh/ruh-model-training` notebook was inspected
through the authenticated official Kaggle API. Every curriculum stage invokes
`ruh_model.train --generate-data`: the same tiny root-exposure templates are
regenerated for all 50 epochs. The notebook copies a stale `ruh-model-code` dataset
snapshot and pipes commands through `tail`, which can hide training failures.
The live epoch19 checkpoint still has a 128-token context and a legacy Bayan v1
vocabulary. Stage names and training loss therefore do not demonstrate chat ability.

The repaired pipeline uses Bayan v2, whose UTF-8 representation preserves Arabic,
English, punctuation, function words and negation. Legacy v1 remains available for
existing checkpoint inference and root-analysis APIs. V1 weights are never silently
reinterpreted as v2 text weights. The new training path refuses a legacy resume.
Root analysis and surface sequence modeling serve different purposes; byte targets
add lossless text coverage to the existing Ruh architecture.

`python -m scripts.prepare_sequence_data` prepares reviewed direct replies from
OpenAssistant/oasst1 (Apache-2.0) and Arabic Wikipedia articles (CC-BY-SA-3.0/GFDL),
with exact pinned revisions and attribution in `sources.json`. Source loader scripts
are never executed. No private production conversations or private checkpoint data
are uploaded. Whole source conversation trees are assigned deterministically to
training or validation; duplicate content is removed. The scarce approved Arabic
OpenAssistant replies are retained before the English limit is applied.

`python -m ruh_model.train_sequence` windows all bytes with one-token overlap,
trains only assistant continuation targets for conversations, and trains all text
for sentence/document records. Only the final document window contains EOS.
The role protocol matches `serialize_messages` and the RunPod handler: the prompt
ends with `assistant:` without EOS; the assistant's separating space is a target.
V2 generation uses pattern 0, matching byte training, and masks legacy root IDs.

The run refuses nonfinite losses/gradients and existing output directories, records
token-weighted held-out loss before and after, and produces greedy held-out samples.
It saves the candidate, tokenizer version, exact vocabulary, file hashes,
`training_state.pt` (optimizer state), source/split metadata, and `evaluation.json`.
A v2 candidate can resume with `--resume-from <run>/candidate`; its stored dimensions
and context remain authoritative. The loader starts a new deterministic shuffle.
Saved candidates are explicitly marked **not approved for production**.

## Private bounded Kaggle validation

`notebooks/kaggle/ruh_training_repair/` contains a commit-pinned notebook and Kaggle
metadata. The validation requests a P100, uses Kaggle's installed Torch, and sets
an API session timeout of 900 seconds including setup/download. Training itself is
limited to 480 seconds and 1,000 steps. The 3.58M-parameter dense pilot uses four
256-wide layers, a 384-byte context, batch size 2 and learning rate 3e-4. It validates
the repaired code/data path and does **not** replace the 46M production checkpoint.
No paid capacity is enabled and no RunPod or production mutations occur.

```bash
python -m scripts.prepare_sequence_data --output-dir /kaggle/working/data \
  --dialogues 1500 --sentences 500
python -m ruh_model.train_sequence \
  --data /kaggle/working/data/training.jsonl \
  --source-metadata /kaggle/working/data/sources.json \
  --output /kaggle/working/validation-run --device cuda \
  --steps 1000 --max-seconds 480 --seq-len 384 --batch-size 2
```

## Full 46M architecture

The separate `--production-architecture` flag preserves the original Ruh
512-wide, eight-layer, eight-head, four-expert/top-two MoE architecture with
4,000 output classes (45,985,563 parameters). This starts new v2 training; changing
the tokenizer of epoch19 cannot recover discarded surface words. A longer run
must use enough real data and evaluate held-out Arabic and English generations.
The initial sentence phase can use a 384-byte context; subsequent fresh runs can
use 1,024 or more bytes when GPU memory and quota permit. Resuming preserves the
checkpoint's stored context. The following is a reproducible, bounded first phase,
not a promise of chat quality:

```bash
python -m scripts.prepare_sequence_data --output-dir /kaggle/working/full-data \
  --dialogues 10000 --sentences 10000
python -m ruh_model.train_sequence --production-architecture \
  --data /kaggle/working/full-data/training.jsonl \
  --source-metadata /kaggle/working/full-data/sources.json \
  --output /kaggle/working/full-v2-phase1 --device cuda \
  --steps 20000 --max-seconds 3600 --seq-len 384 --batch-size 2 --lr 3e-4
```

Check the Kaggle quota API before launching. The observed GPU allowance is 30
hours per week; pay-to-scale is disabled. After the pilot about 24 hours 38 minutes
remained, with reset at 2026-10-03 00:00 UTC. Use SDK timedelta.total_seconds();
its JSON string serializer drops the days and incorrectly suggests only 39 minutes.
Promotion requires useful held-out sentence/dialogue output, comparison against
baseline, valid UTF-8 and negation tests, and a versioned worker checkpoint manifest.


## Verified pilot results

Kaggle private notebook `zubairshaikh/ruh-training-repair-validation`, version 1,
completed successfully. Kaggle allocated two Tesla T4 devices despite the P100
request; training used cuda:0. The notebook ran about 66 seconds, with 1,000 steps
in 25.2 seconds over 741,045 supervised byte targets. Held-out CE fell from 6.9170
to 2.0985 (perplexity 1009.3→8.15) over 8,259 targets, with 1,793 training / 199 validation
records. Three Arabic greedy samples avoided immediate EOS and invalid UTF-8 but
repeated essentially the same phrase. This verifies pipeline repair and finite
learning; it does not establish conversational quality or justify promotion.

The full-size run adds the human Aya dataset (Apache-2.0, pinned revision
`f9ea04583f02a8f86404ff6c58bf75fe637df8a2`) with 4,995 Arabic and 1,500 English
instructions. Annotation user IDs are not retained. Source conversation groups
are joined across shared prompts, preventing alternate answers from crossing
training/validation even across corpora. Expected supervised byte sampling weights are 55% Arabic
dialogue, 25% English dialogue, 20% Arabic documents; long Wikipedia articles
cannot consume most supervised target bytes. Reports include target-byte counts per
category, per-language conditional loss, unseen negation challenges, EOS and
empty-output rates, duplicate outputs and repeated four-gram fractions.
Full-size MoE training retains router load-balancing auxiliary loss.

The full notebook uses a 1,800-second session cap and 1,350-second training cap,
with a complete model/optimizer/tokenizer continuation snapshot every 300 seconds.
Only the latest intermediate snapshot is kept, plus final output. The candidate
and all snapshots remain private and unapproved for production.

Validation:229 Ruh tests (including 10 new sequence tests) and 912 backend tests pass.
Ruff passes. `make check` reaches 27 Torch-aware mypy errors; an isolated unmodified
45b6693 baseline reproduces the same 27, with no new errors introduced here.
GitHub's optional-Torch-free typecheck context is separate from this local ML
validation environment.
