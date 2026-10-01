# Ruh model training — retrain pipeline

**Status (2026-09-29):** the 4-stage curriculum ran end-to-end on Kaggle
GPUs (T4 x2) with no errors — loss 5.2660 → 1.0827 across 50 epochs. See
[Measured run, 2026-09-29](#measured-run-2026-09-29). The training code is
[`ruh_model/`](../../../ruh_model); entry point
[`ruh_model/train.py`](../../../ruh_model/train.py).

## What it is

The Ruh model is Mizan's own small transformer language model, trained in
four developmental curriculum stages named after the Qur'anic embryology
sequence (nutfah → alaqah → mudghah → khalq_akhar). Each stage trains on
harder data with a lower learning rate and longer sequences than the last,
resuming from the previous stage's final checkpoint.

This is **research training infrastructure**, not a released foundation
model. There is no benchmark against external baselines and no shipped
checkpoint in this repository — see [Honest boundaries](#honest-boundaries).

## The four stages

From [`ruh_model/training/curriculum.py`](../../../ruh_model/training/curriculum.py)
(`NafsCurriculum`). Epochs and batch size are **stage properties, not CLI
flags** — `train.py` does not accept `--epochs` or `--batch-size`.

| #   | Stage        | Epochs | Batch | Curriculum emphasis                                      |
| --- | ------------ | ------ | ----- | ------------------------------------------------------ |
| 1   | `nutfah`     | 5      | 16    | Embryonic: simple sentences, high LR, short sequences   |
| 2   | `alaqah`     | 10     | 8     | Clinging: paragraphs, moderate LR, medium sequences     |
| 3   | `mudghah`    | 15     | 4     | Formation: documents + reasoning, low LR, long sequences |
| 4   | `khalq_akhar`| 20     | 2     | New creation: full capability, minimal LR, max sequences|

## Run it

Single stage, from the repo root:

```bash
python -m ruh_model.train --stage nutfah \
    --checkpoint-dir /path/to/checkpoints_nutfah
```

Full curriculum — each stage resumes from the **previous stage's last
epoch checkpoint**:

```bash
python -m ruh_model.train --stage nutfah \
    --checkpoint-dir /path/to/checkpoints_nutfah

python -m ruh_model.train --stage alaqah \
    --resume-from /path/to/checkpoints_nutfah/epoch_4 \
    --checkpoint-dir /path/to/checkpoints_alaqah

python -m ruh_model.train --stage mudghah \
    --resume-from /path/to/checkpoints_alaqah/epoch_9 \
    --checkpoint-dir /path/to/checkpoints_mudghah

python -m ruh_model.train --stage khalq_akhar \
    --resume-from /path/to/checkpoints_mudghah/epoch_14 \
    --checkpoint-dir /path/to/checkpoints_khalq
```

Checkpoints are saved per epoch as `<checkpoint-dir>/epoch_<N>`
(zero-indexed), so the last epoch of a 5-epoch stage is `epoch_4`.
Always resume from the last epoch directory of the previous stage.

Other useful flags (from `train.py --help`):

```text
--data-dir DIR        training JSONL directory (default: ruh_model/data/training)
--generate-data       generate seed training data before training
--samples-per-root N  samples per root when generating (default: 10)
--config PATH         YAML config overriding --stage (needs name, max_seq_len,
                      lr, epochs, batch_size)
--log-every N         log loss every N steps (default: 10)
--json-progress       emit JSON progress lines (for API integration)
```

Seed data (no dataset on hand):

```bash
python -m ruh_model.train --stage nutfah --generate-data
```

### Kaggle GPU workflow

The reference GPU run uses a Kaggle notebook
(`kaggle.com/code/zubairshaikh/notebook00da3d7a2d`):

1. Accelerator: **GPU T4 x2**.
2. Clone the repo and install deps in a setup cell
   (`pip install -e .` plus torch for CUDA).
3. Smoke-test first: run the nutfah stage and confirm loss decreases
   before committing to the full curriculum.
4. Run the four stage commands above with `/kaggle/working/checkpoints_*`
   as checkpoint dirs; each stage resumes from the previous stage's last
   `epoch_N`.
5. Save the notebook — checkpoints persist in `/kaggle/working` for the
   session; download anything you need before it expires.

Total wall time for the reference run was ~50 minutes on T4 x2.

## Measured run, 2026-09-29

All four stages completed with `Training complete.` and no errors.
Losses are per-epoch training losses printed by the trainer.

| Stage        | Epochs | Time    | First loss | Final loss | Improvement |
| ------------ | ------ | ------- | ---------- | ---------- | ----------- |
| nutfah       | 5      | 99 s    | 5.2660     | 1.3444     | 74.5%       |
| alaqah       | 10     | 330 s   | 1.3325     | 1.1581     | 13.1%       |
| mudghah      | 15     | 843 s   | 1.1730     | 1.1135     | 5.1%        |
| khalq_akhar  | 20     | 1785 s  | 1.0974     | 1.0827     | 1.3%        |

**Overall: 5.2660 → 1.0827.** Final checkpoint:
`/kaggle/working/checkpoints_khalq/epoch_19`.

Per-epoch progression (training loss):

- nutfah: 5.2660 → 1.8321 → 1.5067 → 1.3868 → 1.3444
- alaqah: 1.3325 → 1.2910 → 1.2554 → 1.2293 → 1.2127 → 1.1937 → 1.1861 → 1.1803 → 1.1682 → 1.1581
- mudghah: 1.1730 → 1.1863 → 1.1729 → 1.1780 → 1.1665 → 1.1638 → 1.1549 → 1.1491 → 1.1431 → 1.1310 → 1.1331 → 1.1218 → 1.1233 → 1.1191 → 1.1135
- khalq_akhar: 1.0974 → 1.1037 → 1.1061 → 1.1026 → 1.1087 → 1.1095 → 1.1132 → 1.1040 → 1.0997 → 1.1015 → 1.1046 → 1.1000 → 1.0934 → 1.0950 → 1.0907 → 1.0836 → 1.0827 → 1.0940 → 1.0906 → 1.0827

## Checkpoint layout

Each stage writes one directory per epoch inside its checkpoint dir:

```text
checkpoints_nutfah/epoch_0 … epoch_4
checkpoints_alaqah/epoch_0 … epoch_9
checkpoints_mudghah/epoch_0 … epoch_14
checkpoints_khalq/epoch_0 … epoch_19
```

Load a checkpoint for inference or further training with
`RuhModel.from_pretrained(<epoch-dir>)` (`--resume-from` uses the same path).

## Honest boundaries

- The numbers above are **training losses on the training data**, not
  held-out evaluation and not a benchmark against any external model or
  baseline. They show the pipeline works and loss decreases; they do not
  establish model quality.
- Checkpoints from the 2026-09-29 run live in the Kaggle session's
  `/kaggle/working` directory — they are **not shipped in this repository**
  and Kaggle working dirs expire. Re-run the pipeline to reproduce them.
- The improvement percentages are computed as
  `(1 − final/first) × 100` per stage by the trainer itself.
- GPU cost for the reference run: ~50 minutes of Kaggle T4 x2 weekly quota.
