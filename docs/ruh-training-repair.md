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
metadata. The validation requests one P100, uses Kaggle's installed Torch, and sets
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

## Full 46M architecture after quota reset

The separate `--production-architecture` flag preserves the original Ruh
512-wide, eight-layer, eight-head, four-expert/top-two MoE architecture with
4,000 output classes (45,994,799 parameters). This starts new v2 training; changing
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

Check the Kaggle quota API before launching. The observed GPU allowance is six
hours per week; pay-to-scale is disabled. At inspection about 39 minutes remained,
with reset at 2026-10-03 00:00 UTC. The full run remains a later quota-reset task.
Promotion requires useful held-out sentence/dialogue output, comparison against
baseline, valid UTF-8 and negation tests, and a versioned worker checkpoint manifest.
