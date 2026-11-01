# Ruh Model (روح)

> **Experimental transformer with legacy Arabic root generation and a lossless tokenizer for new training.**

Ruh is a pure-PyTorch transformer that operates in **root-space** instead of token-space. "Root-space" means a root and pattern inventory catalogued from Quranic Arabic morphology, used as lexicon ids. That catalogue is not built yet: today the inventory is a hand-authored list of 55 roots (`backend/qca/roots.py`). Where standard LLMs split text into BPE subwords, Ruh tokenizes text as `(root_id, pattern_id)` pairs — the same factored representation used by Arabic morphology for 1,400+ years. This yields **~7.8× embedding-param compression** over standard lookup tables (`4000×512 ÷ (4000×64 + 200×32) = 7.8×`) and is designed to enable cross-lingual understanding via shared Semitic roots (unverified — no cross-lingual benchmark has been run yet).

**Scripture is never a training target.** The Quran is a source MIZAN quotes by lookup from pinned editions. It is never a training target of Ruh or any other model in this repository; it (and hadith text) may be an input, a retrieval source or an evaluation set. `data/scripture.py` holds the rule and `tests/test_scripture_targets.py` checks it on real batches (see `docs/quranic_training_paths.md`, including the known gap: an ayah quoted inside a general corpus row is masked only when the row declares it).

**Checkpoint compatibility:** the published epoch-19 checkpoint uses Bayan v1 (62 mapped IDs) and remains a constrained root generator. Its original seed corpus does not establish sentence-level chat, English NLP accuracy, or reliable instruction following. Removing inference EOS fixes a formatting defect; it does not supply missing training.

New training uses **Bayan v2**, preserving UTF-8 surface bytes, negation, punctuation, unknown words, and function words. Byte IDs occupy a separate range after the frozen root IDs. This changes the prediction task and requires a newly trained checkpoint; do not change an old checkpoint's tokenizer version. Checkpoints save `vocab.json` and `tokenizer.json` with the weights/config. Missing vocabularies are rejected for v2; only legacy v1 may use the frozen compatibility vocabulary.

The confidence head and MoE balance term now receive gradients. Consistency is conditional on records containing `paraphrase`; it compares the masked mean distributions of paired sequences, not unaligned token positions. Ordinary records do not enable this objective. These losses are experimental regularizers, not proof of truthfulness.

**Version:** 0.1.0

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [CLI Reference](#cli-reference)
- [Training Guide](#training-guide)
  - [Seed Data Generation](#seed-data-generation)
  - [Curriculum Stages](#curriculum-stages)
  - [YAML Configuration](#yaml-configuration)
  - [Full Real-Data Training](#full-real-data-training)
  - [Prepare Data to Disk](#prepare-data-to-disk)
  - [Real Data Pipeline (Programmatic)](#real-data-pipeline-programmatic)
  - [Resuming Training](#resuming-training)
- [Tokenizer (Bayan)](#tokenizer-bayan)
  - [Encoding & Decoding](#encoding--decoding)
  - [Text Analysis](#text-analysis)
  - [Q28 Articulatory Basis](#q28-articulatory-basis)
- [Inference & Generation](#inference--generation)
- [Model Save & Load](#model-save--load)
- [Configuration Reference](#configuration-reference)
- [Loss Function (Mizan)](#loss-function-mizan)
- [Component Deep Dive](#component-deep-dive)
  - [ISM Embedding](#ism-embedding)
  - [Qalb Attention](#qalb-attention)
  - [Sam-Basar Dual Processing](#sam-basar-dual-processing)
  - [Shura MoE](#shura-moe)
  - [Lubb Metacognition](#lubb-metacognition)
  - [Adaptive Depth](#adaptive-depth)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [API Integration](#api-integration)
- [Concepts & Naming](#concepts--naming)

---

## Quick Start

```bash
# From the mizan project root
cd /path/to/mizan

# Install HuggingFace datasets (required for real-data training)
pip install datasets

# === Option A: Quick start with seed data ===

# 1. Generate seed training data and train Stage 1
python -m ruh_model.train --stage nutfah --generate-data --verbose

# 2. Train Stage 2 (resuming from Stage 1 checkpoint)
python -m ruh_model.train --stage alaqah --resume-from ruh_model/checkpoints/epoch_4

# === Option B: Full real-data training from HuggingFace ===

# 1. Train Stage 1 with 100K real samples (default: Arabic Wikipedia; the Quran and
#    hadith are never training targets; OPUS and morphology need explicit RUH_DATA_SOURCES)
python -m ruh_model.train_full --stage nutfah --samples 100000 --device auto

# 2. Run ALL 4 stages with 500K samples (full curriculum)
python -m ruh_model.train_full --all-stages --samples 500000 --device cuda

# 3. Or prepare data to disk first, then train offline
python -m ruh_model.train_full --prepare-only --samples 500000 --output-dir data/real
python -m ruh_model.train_full --stage nutfah --data-dir data/real

# === Use the tokenizer ===
python -c "
from ruh_model.tokenizer.bayan import BayanTokenizer
tok = BayanTokenizer()
tokens = tok.encode('Knowledge is light')
print(tokens)
print(tok.decode(tokens))
"

# === Generate text from a trained model ===
python -c "
import torch
from ruh_model.model import RuhModel

model = RuhModel.from_pretrained('ruh_model/checkpoints/epoch_4')
root_ids = torch.tensor([[1, 42, 15]])   # BOS + two roots
pattern_ids = torch.tensor([[0, 1, 1]])
output = model.generate(root_ids, pattern_ids, max_new_tokens=20, temperature=0.8)
print(output)
"
```

---

## Architecture Overview

```
Input Text
    │
    ▼
┌─────────────────────────────┐
│   Bayan Tokenizer (مُبَيِّن)   │  text → [(root_id, pattern_id), ...]
│   Arabic: morphological     │
│   English: concept-map/Q28  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   ISM Embedding (اسم)       │  (root_id, pattern_id) → d_model vector
│   Factored: root + pattern  │  ~7.8× param compression vs standard lookup
│   Gated additive fusion     │
│   + RoPE positional enc     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   Block 0: SamBasarDual     │  Dual attention (hearing + sight)
│   ├ Sam' (سمع): causal      │  Sequential/temporal processing
│   ├ Basar (بصر): causal     │  Structural/pattern recognition
│   └ Fuad (فؤاد): gate       │  Learned fusion of Sam' + Basar
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   Blocks 1..N: QalbAttention │  Cardiac-oscillation modulated attention
│   ├ ψ = 1 + α·sin(2πt/T)   │  Complexity-adaptive period
│   ├ SwiGLU FFN (ISMFFN)     │  Or ShuraMoE every N blocks
│   └ Pre-norm residual       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   Final RMSNorm             │
│   + Weight-tied projection  │  d_model → n_roots logits
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   Mizan Loss (ميزان)         │  5-component composite objective
│   CE + Calibration +        │
│   Consistency + Fitrah +    │
│   Hisbah                    │
└─────────────────────────────┘
```

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| Root-space tokenization | Arabic morphology is inherently root-based; BPE fragments roots |
| Factored embedding | Root × Pattern decomposition gives ~7.8× embedding-param compression (measured: 2,048,000 ÷ 262,400 params) |
| Cardiac oscillation | Bio-inspired rhythmic attention modulation (Qalb = heart) |
| Dual first layer | Two causal pathways: sequential (Sam'/hearing) and structural (Basar/sight) |
| 5-component loss | Beyond CE: calibration, consistency, fitrah (entropy), hisbah (accountability) |
| Curriculum training | 4 developmental stages inspired by Quran 23:12-14 |

---

## Installation

### Prerequisites

- Python 3.11+
- PyTorch (CPU or CUDA; the `ml` extra pins `torch>=2.14.1,<2.15`)
- PyYAML

### Install Dependencies

```bash
# From mizan project root
pip install -e ".[ml]"     # torch, numpy, safetensors, datasets, huggingface-hub, ...

# Or
pip install torch pyyaml

# Or use the project's requirements (includes torch)
pip install -r backend/requirements.txt
```

### Verify Installation

```bash
python -c "from ruh_model import RuhConfig, RuhModel; print('OK')"
```

---

## CLI Reference

The training CLI is at `ruh_model/train.py`, invoked as a module:

```bash
python -m ruh_model.train [OPTIONS]
```

### All CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--stage` | `nutfah` | Curriculum stage: `nutfah`, `alaqah`, `mudghah`, `khalq_akhar` |
| `--data-dir` | `ruh_model/data/training` | Directory containing training `.jsonl` files |
| `--checkpoint-dir` | `ruh_model/checkpoints` | Directory to save model checkpoints |
| `--config` | `None` | Path to a YAML config file (overrides `--stage`) |
| `--generate-data` | `False` | Generate seed training data before training |
| `--samples-per-root` | `10` | Number of samples per root when generating data |
| `--resume-from` | `None` | Path to a checkpoint directory to resume from |
| `--log-every` | `10` | Log loss every N training steps |
| `--verbose` | `False` | Enable debug-level logging |
| `--json-progress` | `False` | Emit JSON progress lines to stdout (for API integration) |

### Example Commands

```bash
# Train Stage 1 with seed data generation
python -m ruh_model.train --stage nutfah --generate-data

# Train Stage 1 with more samples per root
python -m ruh_model.train --stage nutfah --generate-data --samples-per-root 25

# Train Stage 2 with custom data directory
python -m ruh_model.train --stage alaqah --data-dir my_data/arabic/

# Resume training from a checkpoint
python -m ruh_model.train --stage alaqah --resume-from ruh_model/checkpoints/epoch_4

# Train with a custom YAML config
python -m ruh_model.train --config ruh_model/configs/nutfah.yaml

# Verbose mode with frequent logging
python -m ruh_model.train --stage nutfah --generate-data --verbose --log-every 5
```

---

## Training Guide

### Seed Data Generation

Ruh includes a `SeedDataGenerator` that creates bilingual training data from the built-in `ARABIC_ROOTS` dictionary:

```bash
# Via CLI (generates data + trains)
python -m ruh_model.train --stage nutfah --generate-data --samples-per-root 10
```

This creates two files in `ruh_model/data/training/`:

| File | Content |
|------|---------|
| `seed_roots.jsonl` | Template-expanded sentences from root derivatives |
| `seed_concepts.jsonl` | Concept-map based cross-lingual samples |

Each line is a JSON object with a single `text` field:

```json
{"text": "أثر نور"}
{"text": "طلب نَفْس"}
{"text": "trust وكل"}
```

**Templates** (`ruh_model/data/generator.py`):

- **`seed_roots.jsonl`**: for each root, `samples_per_root` phrases from a randomly chosen word (the root or one of its derivatives) in a short template: Arabic templates such as `"{w} نور"`, `"هذا {w}"`, `"طلب {w}"` when the word is Arabic, English templates such as `"{w} is light"`, `"seek {w}"` otherwise.
- **`seed_concepts.jsonl`**: one `"{english} {arabic_root}"` line per `CONCEPT_MAP` entry.

#### Programmatic Data Generation

```python
from ruh_model.data.generator import SeedDataGenerator

gen = SeedDataGenerator(seed=42)

# Generate root-based training data
count = gen.generate("my_data/roots.jsonl", samples_per_root=20)
print(f"Generated {count} samples")

# Generate concept-map data
count = gen.generate_concept_map_data("my_data/concepts.jsonl")
print(f"Generated {count} concept samples")
```

### Curriculum Stages

Training follows the **Nafs Curriculum** — four progressive stages inspired by Quranic embryology (23:12-14):

| Stage | Arabic | Meaning | Seq Len | LR | Epochs | Batch | Description |
|-------|--------|---------|---------|-----|--------|-------|-------------|
| 1. `nutfah` | نطفة | Drop/Seed | 128 | 3e-4 | 5 | 16 | Simple sentences, high LR |
| 2. `alaqah` | علقة | Clinging | 512 | 1e-4 | 10 | 8 | Paragraphs, moderate LR |
| 3. `mudghah` | مضغة | Formation | 1024 | 5e-5 | 15 | 4 | Documents + reasoning |
| 4. `khalq_akhar` | خلق آخر | New Creation | 2048 | 1e-5 | 20 | 2 | Full capability |

**Multi-stage training workflow:**

```bash
# Stage 1: Embryonic
python -m ruh_model.train --stage nutfah --generate-data --verbose

# Stage 2: Clinging (resume from Stage 1 final checkpoint)
python -m ruh_model.train --stage alaqah --resume-from ruh_model/checkpoints/epoch_4

# Stage 3: Formation
python -m ruh_model.train --stage mudghah --resume-from ruh_model/checkpoints/epoch_9

# Stage 4: New Creation
python -m ruh_model.train --stage khalq_akhar --resume-from ruh_model/checkpoints/epoch_14
```

Each epoch saves a checkpoint to `ruh_model/checkpoints/epoch_N/` containing:
- `config.json` — serialized `RuhConfig`
- `model.pt` — PyTorch state dict
- `vocab.json`, `tokenizer.json` — the Bayan vocabulary and tokenizer version

#### Programmatic Curriculum Access

```python
from ruh_model.training.curriculum import NafsCurriculum

curriculum = NafsCurriculum()

# Get a specific stage
stage = curriculum.get_stage("alaqah")
print(f"{stage.name}: seq_len={stage.max_seq_len}, lr={stage.lr}")

# Get all stages in order
for stage in curriculum.get_all_stages():
    print(f"  {stage.name}: {stage.description}")
```

### YAML Configuration

Override built-in stages with custom YAML configs:

```yaml
# my_config.yaml
name: custom_stage
description: "Custom training configuration"

max_seq_len: 256
lr: 2.0e-4
epochs: 8
batch_size: 12

# Optional optimizer settings (used by trainer)
weight_decay: 0.01
max_grad_norm: 1.0
warmup_fraction: 0.1
```

```bash
python -m ruh_model.train --config my_config.yaml --data-dir my_data/
```

**Included configs:**

- `ruh_model/configs/nutfah.yaml` — Stage 1 defaults
- `ruh_model/configs/alaqah.yaml` — Stage 2 defaults
- `ruh_model/configs/mudghah.yaml` — Stage 3 defaults
- `ruh_model/configs/khalq_akhar.yaml` — Stage 4 defaults

Required YAML keys: `name`, `max_seq_len`, `lr`, `epochs`, `batch_size`.

### Full Real-Data Training

The CLI reads bounded batches from pinned public Parquet corpora using synchronous decoding. Install `datasets`, `pyarrow`, and `huggingface-hub` alongside PyTorch. Dataset scripts are not executed.

| Domain | Pinned dataset | Text column | Default weight |
|---|---|---|---|
| Quran | none: never a training target | — | 0 (a positive weight is refused) |
| Hadith | none: never a training target | — | 0 (a positive weight is refused) |
| Arabic Wikipedia | `wikimedia/wikipedia`, `20231101.ar` | `text` | 1.0 |

Exact revisions are recorded in `data/pipeline.py` (`DEFAULT_SOURCES`). OPUS and morphology have weight zero until explicit sources are configured. To add sources, set `RUH_DATA_SOURCES` to a JSON file mapping domain names to `path`, immutable `revision`, optional `name`, `split`, `column`, and `lang`; adjust the corresponding CLI weights. A Quran or hadith source cannot be added: a positive weight for a `quran`/`hadith` domain, or for a source whose `kind` is `verified_quran`/`quran`/`hadith` or that has `verse_columns`, is refused whatever permission it claims. A source row may declare the scripture it quotes (`scripture`: exact strings); those bytes are never supervised (Bayan v2 only; see `docs/quranic_training_paths.md`). Curate the corpus, check licenses, remove duplicates, and separate held-out examples before a large training run. Corpus stages do not automatically create grammar or instruction examples.

```bash
# Bounded preparation smoke test; no GPU or training job is started.
python -m ruh_model.train_full --prepare-only --samples 10 \
    --wiki-weight 1 --output-dir data/real

# New training uses v2. Supply curated sentence/dialogue records for chat.
python -m ruh_model.train_full --stage nutfah --data-dir data/real --device cuda
```

### Prepare Data to Disk

`--prepare-only` writes `{domain}_{lang}.jsonl`. Records may contain `text`, conversation `messages`, and optional `paraphrase` text. These fields reach the tokenizer and paired training objective. A raw corpus preparation success is not a model-quality evaluation.

### Real Data Pipeline (Programmatic)

```python
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.data.pipeline import RealDataPipeline

pipeline = RealDataPipeline(BayanTokenizer(version=2), max_seq_len=512,
                            mixing_ratios={"arabic_wiki": 1.0})
for batch in pipeline.get_dataloader(max_samples=5000, batch_size=8):
    print(batch["root_ids"].shape)
    break
```

Inference serializes system instructions, all conversation turns, and tool results, requests `encode(..., add_eos=False)`, and decodes/counts only the continuation. The legacy checkpoint was not trained on this conversation protocol. Temperature zero uses greedy sampling; generation masks IDs missing from the checkpoint vocabulary.

### Resuming Training

```bash
# From seed-data training checkpoints
python -m ruh_model.train --stage alaqah --resume-from ruh_model/checkpoints/epoch_4

# From real-data training checkpoints
python -m ruh_model.train_full --stage alaqah \
    --resume-from ruh_model/checkpoints/nutfah_final
```

The `--resume-from` flag loads both `config.json` and `model.pt` from the specified directory via `RuhModel.from_pretrained()`.

---

## Tokenizer (Bayan)

**Bayan** (مُبَيِّن, "The Clear One") is a morphologically-aware, root-cognizant tokenizer. Named after Quran 55:3-4: *"He created man. He taught him al-Bayan (clear expression)."*

Instead of BPE subwords, Bayan encodes each word as a `(root_id, pattern_id)` pair.

### Encoding & Decoding

```python
from ruh_model.tokenizer.bayan import BayanTokenizer

tok = BayanTokenizer()

# Encode text to (root_id, pattern_id) tuples
tokens = tok.encode("Knowledge is the light of the soul")
print(tokens)
# [(1, 0), (32, 7), (0, 15), (0, 15), (54, 7), (0, 15), (0, 15), (53, 7), (2, 0)]
#  BOS      knowledge  is(stop)  the(stop)  light     of(stop)  the(stop) soul      EOS

# Decode back to approximate text
text = tok.decode(tokens)
print(text)
# "عِلْم نَارَ نَفَسَ"  (v1: stopwords dropped; each root rendered as an Arabic derivative, best-effort)

# Batch encoding
texts = ["The pen is mightier than the sword", "العلم نور"]
batch = tok.encode_batch(texts)

# Arabic text
tokens_ar = tok.encode("العلم نور")
print(tokens_ar)
```

**Special tokens:**

| Token | Root ID | Purpose |
|-------|---------|---------|
| BOS | 1 | Beginning of sequence |
| EOS | 2 | End of sequence |
| PAD | 0 | Padding / stopwords |
| UNK | 3 | Unknown root |

**Language detection:** Automatic per-word. Arabic characters (Unicode ranges `\u0600-\u06FF`, etc.) route through morphological analysis; everything else goes through the English bridge.

**Encoding pipeline per word:**

1. **Stopword?** → `(PAD_ID, PATTERN_STOPWORD)`
2. **Arabic?** → `ArabicMorphAnalyzer` → extract trilateral root + classify pattern → lookup IDs
3. **English?** → `EnglishRootBridge` concept-map lookup → Q28 articulatory fallback → lookup IDs

### Text Analysis

```python
tok = BayanTokenizer()

# Detailed per-word analysis
analysis = tok.analyze("Knowledge leads to understanding")
for entry in analysis:
    print(f"  {entry['surface']:15s} → root={entry['root']}, pattern={entry['pattern']}")

# Arabic analysis
analysis = tok.analyze("كتب العلم في المدرسة")
for entry in analysis:
    print(f"  {entry['surface']:15s} → root={entry['root']}, pattern={entry['pattern']}, meaning={entry.get('root_meaning', '')}")
```

### Q28 Articulatory Basis

The **Q28** system represents the 28 Arabic letters as the phonetically complete basis for human speech. Each letter maps to a 6-dimensional articulatory feature vector:

```
[place_of_articulation, manner, voicing, emphasis, nasality, length]
```

This enables cross-lingual phonetic matching: English words are converted to IPA, mapped to Q28 articulatory features, and matched to the nearest Arabic root.

```python
from ruh_model.tokenizer.q28_articulatory import Q28ArticulatoryBasis

q28 = Q28ArticulatoryBasis()

# Convert text to Q28 articulatory coordinates
coords = q28.text_to_q28("science", lang="en")
print(coords)  # List of 6D feature vectors

# Find nearest Arabic root match
root_hint = q28.q28_to_root_hint(coords)
print(root_hint)  # Nearest matching Arabic root
```

---

## Inference & Generation

```python
import torch
from ruh_model.model import RuhModel
from ruh_model.config import RuhConfig

# Load a trained model
model = RuhModel.from_pretrained("ruh_model/checkpoints/epoch_4")
model.eval()

# Or create a fresh model
config = RuhConfig(d_model=512, n_layers=8)
model = RuhModel(config)

# Prepare input (BOS token + some root IDs)
root_ids = torch.tensor([[1, 42, 15, 87]])      # (1, 4) - batch of 1
pattern_ids = torch.tensor([[0, 1, 1, 1]])       # (1, 4)

# Autoregressive generation
with torch.no_grad():
    output = model.generate(
        root_ids=root_ids,
        pattern_ids=pattern_ids,
        max_new_tokens=50,
        temperature=0.8,          # Lower = more deterministic
        default_pattern_id=1,     # Pattern ID for generated tokens
    )
print(output.shape)  # at most (1, 54) — original 4 + up to 50 generated (stops once every row emits EOS)

# Forward pass (get logits + optional loss)
result = model(root_ids, pattern_ids)
logits = result["logits"]  # (1, 4, 4000) — probabilities over root vocab
print(f"Logits shape: {logits.shape}")

# With labels for training loss
labels = torch.tensor([[42, 15, 87, 2]])  # Shifted targets (next-root prediction)
result = model(root_ids, pattern_ids, labels=labels)
print(f"Loss: {result['loss'].item():.4f}")
print(f"CE: {result['loss_breakdown'].ce:.4f}")
print(f"Fitrah: {result['loss_breakdown'].fitrah:.4f}")
```

---

## Model Save & Load

```python
from ruh_model.model import RuhModel
from ruh_model.config import RuhConfig

# Create and train a model...
model = RuhModel(RuhConfig())

# Save to directory
model.save_pretrained("my_model/v1")
# Creates:
#   my_model/v1/config.json     (all RuhConfig fields)
#   my_model/v1/model.pt        (PyTorch state dict)
#   my_model/v1/vocab.json      (Bayan vocabulary)
#   my_model/v1/tokenizer.json  ({"version": 1 | 2})

# Load from directory
loaded = RuhModel.from_pretrained("my_model/v1")
print(loaded.count_parameters())
```

**Checkpoint format:**

```
my_model/v1/
├── config.json     # {"d_model": 512, "n_heads": 8, ...}
├── model.pt        # torch state_dict
├── vocab.json      # Bayan vocabulary
└── tokenizer.json  # {"version": 1}
```

---

## Configuration Reference

All configuration is centralized in `RuhConfig`:

```python
from ruh_model.config import RuhConfig

config = RuhConfig(
    # --- Model dimensions ---
    d_model=512,           # Main hidden dimension
    d_root=64,             # Root embedding dimension
    d_pattern=32,          # Pattern embedding dimension

    # --- Transformer architecture ---
    n_heads=8,             # Attention heads
    n_layers=8,            # Transformer blocks

    # --- Vocabulary ---
    n_roots=4000,          # Root vocabulary size (IDs 0-3999)
    tokenizer_version=1,   # Bayan version (1 = legacy roots, 2 = lossless bytes)
    use_lubb=False,        # Add a confidence head feeding calibration/hisbah
    moe_aux_weight=0.01,   # Weight of the Shura MoE load-balancing loss
    n_patterns=200,        # Morphological patterns

    # --- Sequence ---
    max_seq_len=2048,      # Maximum sequence length

    # --- Regularisation ---
    dropout=0.1,

    # --- Feed-forward ---
    ffn_multiplier=2.667,  # SwiGLU expansion factor

    # --- Cardiac oscillation (Qalb attention) ---
    alpha=0.1,             # Sinusoidal modulation amplitude

    # --- Shura MoE ---
    n_experts=4,           # FFN experts per MoE layer
    moe_top_k=2,           # Top-k experts per token
    moe_interval=2,        # MoE every N blocks (0 = disabled)

    # --- Adaptive depth ---
    adaptive_depth_threshold=0.8,

    # --- Hardware ---
    device="cpu",          # "cpu" or "cuda"
)

# Derived properties
print(config.d_ffn)                 # 1365 (SwiGLU-adjusted)
print(config.estimated_param_count) # ~28M parameters
```

### Special Token IDs

| Constant | ID | Purpose |
|----------|----|---------|
| `PAD_ROOT` | 0 | Padding (ignored in loss) |
| `BOS_ROOT` | 1 | Beginning of sequence |
| `EOS_ROOT` | 2 | End of sequence |
| `UNK_ROOT` | 3 | Unknown root |
| `FIRST_REAL_ROOT` | 4 | First real root ID |

---

## Loss Function (Mizan)

**Mizan** (ميزان, "The Balance") is a 5-component composite training objective:

$$L_{\text{mizan}} = L_{\text{ce}} + \lambda_{\text{cal}} L_{\text{cal}} + \lambda_{\text{con}} L_{\text{con}} + \lambda_{\text{fit}} L_{\text{fit}} + \lambda_{\text{hisb}} L_{\text{hisb}}$$

| Component | Name | λ | Purpose |
|-----------|------|---|---------|
| $L_{\text{ce}}$ | Cross-Entropy | 1.0 | Standard next-root prediction |
| $L_{\text{cal}}$ | Calibration | 0.1 | ECE: confidence ≈ accuracy (requires Lubb) |
| $L_{\text{con}}$ | Consistency | 0.05 | KL-div between paraphrase pairs |
| $L_{\text{fit}}$ | Fitrah | 0.01 | Entropy regularization toward 0.3 × log(V) |
| $L_{\text{hisb}}$ | Hisbah | 0.02 | Penalize high confidence on wrong answers |

```python
from ruh_model.loss.mizan_loss import MizanLoss

loss_fn = MizanLoss(
    pad_id=0,
    lambda_cal=0.1,
    lambda_con=0.05,
    lambda_fit=0.01,
    lambda_hisb=0.02,
    vocab_size=4000,
)

output = loss_fn(logits, labels, confidence=None, paraphrase_logits=None)
print(f"Total: {output.total.item():.4f}")
print(f"  CE:          {output.ce:.4f}")
print(f"  Calibration: {output.calibration:.4f}")
print(f"  Consistency: {output.consistency:.4f}")
print(f"  Fitrah:      {output.fitrah:.4f}")
print(f"  Hisbah:      {output.hisbah:.4f}")
```

---

## Component Deep Dive

### ISM Embedding

**ISM** (اسم, "Name") — factored embedding that decomposes tokens into root identity and morphological pattern:

```
root_id  → root_embedding (d_root=64)   → root_proj (d_model)
                                              ↓
                                         root_proj + pattern_proj + (interact * σ(gate))  →  d_model
                                              ↑
pattern_id → pattern_embedding (d_pattern=32) → pattern_proj (d_model)
```

**Compression ratio (verified):** Standard embedding for 4,000 roots at d_model=512 requires 2,048,000 parameters. ISM uses `4000×64 + 200×32 = 262,400` embedding params — a **~7.8× reduction** (2,048,000 ÷ 262,400 = 7.8×). Earlier drafts claimed 146×; that figure fails the arithmetic and has been corrected here. No quality-parity benchmark (perplexity/downstream at matched model quality) has been run yet — the compression is real, the quality parity is unverified.

**Weight tying:** Output projection reuses the root embedding via `root_embedding.weight @ root_proj.T`, so encoding and decoding share the same learned root representations.

### Qalb Attention

**Qalb** (قلب, "Heart") — multi-head self-attention with cardiac oscillation:

$$\psi(t) = 1 + \alpha \cdot \sin\!\left(\frac{2\pi t}{T}\right)$$

Where:
- $\alpha = 0.1$ (configurable) — oscillation amplitude
- $T$ is complexity-adaptive: deeper layers get shorter periods
- $t$ = layer index (passed as `t_step`)

The oscillation modulates attention logits before softmax, creating rhythmic emphasis patterns across layers — inspired by the heart's natural oscillatory processing.

Includes RoPE positional encoding and supports optional `root_group_mask` for future root-grouped attention.

### Sam-Basar Dual Processing

The first transformer block uses **SamBasarDual** instead of plain QalbAttention:

- **Sam'** (سمع, "Hearing"): Causal/sequential attention — processes information temporally like hearing spoken language. Uses QalbAttention with a causal mask.
- **Basar** (بصر, "Sight"): Structural attention over what has unfolded — each position attends to itself and earlier positions. Uses QalbAttention with a causal mask (it was bidirectional before the causality fix, which leaked future tokens into autoregressive training).
- **Fuad** (فؤاد, "Heart/Core"): A learned sigmoid gate that fuses the two pathways:

$$\text{output} = \sigma(g) \cdot \text{Sam'} + (1 - \sigma(g)) \cdot \text{Basar}$$

This dual processing mirrors the Quranic description of perception through hearing and sight (Quran 67:23).

### Shura MoE

**Shura** (شورى, "Consultation") — Mixture of Experts with 4 domain-specialized FFN experts:

| Expert | Domain |
|--------|--------|
| 0 | Theology |
| 1 | Ethics |
| 2 | Language |
| 3 | General |

Uses top-2 routing with a learned gating network. Includes Switch Transformer-style load-balancing auxiliary loss to prevent expert collapse.

Configured via `moe_interval`: when set to 2, every other block (after block 0) uses ShuraMoE instead of standard ISMFFN.

### Lubb Metacognition

**Lubb** (لُبّ, "Core/Essence") — metacognitive assessment module with three heads:

| Head | Output | Purpose |
|------|--------|---------|
| Confidence | Sigmoid (0-1) | How certain the model is |
| Yaqin | 3-class softmax | Certainty level: Ilm al-Yaqin / Ayn al-Yaqin / Haqq al-Yaqin |
| Quality | 2D (coherence, relevance) | Self-assessed output quality |

`RuhModel` does not instantiate `LubbMetacognition`. With `RuhConfig(use_lubb=True)` (default `False`) it adds its own sigmoid confidence head over the mean-pooled hidden state; that confidence feeds the Mizan loss calibration and hisbah terms.

### Adaptive Depth

Per-layer gate that enables early computation exit using ACT (Adaptive Computation Time):

```python
# Each layer computes a halting probability
halt_prob = sigmoid(gate(hidden))  # (B, 1)
# When cumulative halt > threshold, skip remaining layers
```

Includes regularization loss that encourages the model to use fewer layers when the input is simple. `AdaptiveDepthGate` (`layers/adaptive_depth.py`) is not used by `RuhModel`; `adaptive_depth_threshold` is not read by the model.

---

## Testing

```bash
# Run all Ruh model tests
cd /path/to/mizan
python -m pytest ruh_model/tests/ -v

# Run specific test files
python -m pytest ruh_model/tests/test_bayan.py -v    # Tokenizer tests
python -m pytest ruh_model/tests/test_ism.py -v      # Embedding tests

# Run with coverage
python -m pytest ruh_model/tests/ --cov=ruh_model --cov-report=term-missing
```

### Test Coverage

| Test File | Covers |
|-----------|--------|
| `test_bayan.py` | BayanTokenizer encode/decode/analyze, Arabic & English processing, stopwords, batch encoding, edge cases |
| `test_bayan_public_api.py` | Torch-free Bayan public API facade (loaded by file path) |
| `test_ism.py` | ISMEmbedding, RoPE and RMSNorm |
| `test_causality.py`, `test_generation_eos_batch.py` | Prefix invariance; batch rows stop independently at EOS |
| `test_quranic_paths.py`, `test_quranic_pipeline.py` | Quran text integrity, annotation, split leakage; scripture sources refused as training domains |
| `test_scripture_targets.py` | Scripture is never a target: no supervised label inside a declared ayah span (windows, pipeline epoch, collator, JSONL dataset); canary and positive Quran/hadith weights refused |
| `test_sequence_training.py`, `test_training_acceleration.py`, `test_training_controller.py`, `test_review_repairs.py` | Lossless sequence training, sparse MoE / mixed precision, controller cleanup, checkpoint-compatibility regressions |
| `test_eval_harness.py`, `test_eval_smoke.py`, `test_review_pipeline.py`, `test_sense.py`, `test_reader.py`, `test_dialect.py`, `test_scaffolds.py` | Eval harness, scholar-review queue, sense inventory, RootSpace Reader, dialect normalization, gated scaffolds |
| `conftest.py` | Shared fixtures: `sample_config` (small RuhConfig for fast tests), `default_vocab` |

---

## Project Structure

```
ruh_model/
├── __init__.py              # Package entry: exports RuhConfig, RuhModel (lazy torch import; v0.1.0)
├── config.py                # RuhConfig dataclass (all hyperparameters)
├── model.py                 # RuhModel: full transformer assembly
├── train.py                 # CLI: seed-data training (python -m ruh_model.train)
├── train_full.py            # CLI: real-data training (python -m ruh_model.train_full)
├── train_sequence.py        # CLI: bounded, evaluated Bayan v2 sequence training
│
├── attention/
│   ├── __init__.py
│   ├── qalb.py              # QalbAttention: cardiac-oscillation MHA + RoPE
│   └── sam_basar.py         # SamBasarDual: two causal branches (Sam' + Basar), gated fusion
│
├── embedding/
│   ├── __init__.py
│   ├── ism.py               # ISMEmbedding: factored root+pattern (~7.8× embedding-param reduction)
│   └── rope.py              # RotaryPositionEncoding + RMSNorm
│
├── layers/
│   ├── __init__.py
│   ├── transformer_block.py # RuhBlock: pre-norm residual (attn + FFN)
│   ├── ism_ffn.py           # ISMFFN: SwiGLU feed-forward
│   ├── shura_moe.py         # ShuraMoE: 4 domain experts, top-2 routing
│   ├── lubb.py              # LubbMetacognition: confidence/yaqin/quality heads (not used by RuhModel)
│   └── adaptive_depth.py    # AdaptiveDepthGate: early exit (not used by RuhModel)
│
├── loss/
│   ├── __init__.py
│   └── mizan_loss.py        # MizanLoss: 5-component composite objective
│
├── tokenizer/
│   ├── __init__.py
│   ├── bayan.py             # BayanTokenizer: text → (root_id, pattern_id); v1 legacy, v2 lossless
│   ├── public_api.py        # Torch-free Bayan facade (see tokenizer/README.md)
│   ├── conversation.py      # Conversation serialization shared by training and inference
│   ├── morphology.py        # ArabicMorphAnalyzer: suffix stripping + root extraction
│   ├── english_bridge.py    # EnglishRootBridge: concept-map + stemmer fallback
│   ├── q28_articulatory.py  # Q28: 28 Arabic letters as phonetic basis (6D vectors)
│   ├── root_vocab.py        # RootVocab: root↔ID and pattern↔ID mappings
│   ├── tasrif_ops.py        # TasrifEngine: 15 morphophonemic operators
│   └── legacy-v1.json       # Frozen Bayan v1 compatibility vocabulary
│
├── training/
│   ├── __init__.py
│   ├── curriculum.py        # NafsCurriculum: 4 developmental stages
│   ├── scheduler.py         # WarmupCosineScheduler: LR warmup + cosine decay
│   └── trainer.py           # RuhTrainer: full training loop + checkpointing
│
├── data/
│   ├── __init__.py
│   ├── dataset.py           # RuhDataset: JSONL → tokenized samples
│   ├── collator.py          # RuhCollator: right-padding, labels, scripture masking
│   ├── generator.py         # SeedDataGenerator: template-based data synthesis
│   ├── pipeline.py          # RealDataPipeline: pinned Parquet sources, weighted streaming
│   ├── scripture.py         # The rule: scripture is an input, never a training target
│   ├── quranic.py           # Pinned Quranic editions, input-only paths, evaluation-only canary
│   ├── quranic_evaluation.py # Quran quotation, citation and annotation evaluation
│   ├── sequence.py          # Lossless sentence windows and assistant targets (Bayan v2)
│   └── chat_sources.py      # Pinned, licensed public conversation data
│
├── configs/
│   ├── nutfah.yaml          # Stage 1 training config
│   ├── alaqah.yaml          # Stage 2 training config
│   ├── mudghah.yaml         # Stage 3 training config
│   ├── khalq_akhar.yaml     # Stage 4 training config
│   └── full_real.yaml       # Reference mixing notes; not read by either CLI (train_full has no --config)
│
├── benchmarks/              # qcsmp_adjudicated.py: Q-CSMP v2 → adjudicated WSD benchmark harness
├── eval/                    # Eval harnesses (beta): Q-CSMP, morphology vs CAMeL, dialect, adjudication
├── sense/                   # Torch-free sense inventory, disambiguation, provenance receipts
├── service/                 # analyze.py: deterministic morphology analysis service
├── reader/                  # RootSpace Reader backend (annotator, offline store)
├── review/                  # Scholar-review queue (beta)
├── dialect/                 # Dialect → root normalization
├── tajwid/                  # Tajwid rules engine + interface scaffold
├── export/                  # onnx.py: ONNX / int8 export scaffold (beta, unverified)
│
└── tests/                   # conftest.py + test_*.py (see Testing)
```

---

## API Integration

Ruh is integrated into the Mizan backend. The frontend can interact with the model via REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ruh/status` | GET | Model status (enabled, model path, device, loaded, remote configured) |
| `/api/ruh/generate` | POST | Generate with the local Ruh model (needs `RUH_ENABLED=true`) |
| `/api/ruh/tokenize` | POST | Bayan tokenization and analysis |
| `/api/ruh/tasrif-demo` | POST | Tasrif morphophonemic operators on articulatory vectors |
| `/api/ruh/checkpoints` | GET | Checkpoints under `ruh_model/checkpoints` |
| `/api/ruh/data-stats` | GET | Training data composition under `ruh_model/data/training` |
| `/api/ruh/architecture` | GET | Architecture info and parameter counts |
| `/api/ruh/{agent_id}` | GET | The agent's Ruh *energy* state (`backend/core/ruh_engine.py`), not the model |
| `/api/training/status`, `/history`, `/start`, `/stop` | GET/POST | Training runs (`start` needs `RUH_ENABLED=true`) |

**Backend code path:** `backend/providers.py` (`LLM_PROVIDER`/provider `ruh`) → `backend/providers_ruh.py` (`RuhModelProvider`); model `ruh-remote` uses `backend/providers_ruh_remote.py` (`RUNPOD_ENDPOINT_ID`, `RUNPOD_API_KEY`).

When properly configured with a trained model path:

```bash
# In .env
RUH_ENABLED=true
# Empty RUH_MODEL_PATH falls back to ruh_model/checkpoints/latest when it holds a model
RUH_MODEL_PATH=ruh_model/checkpoints/epoch_4
RUH_DEVICE=cpu  # or cuda
```

The provider loads the checkpoint lazily on its first request and provides root-space inference for the cognitive architecture.

---

## Concepts & Naming

Every component is named after a Quranic concept. Here's the glossary:

| Name | Arabic | Meaning | Component |
|------|--------|---------|-----------|
| **Ruh** | روح | Spirit/Soul | The model itself |
| **Bayan** | مُبَيِّن | Clear Expression | Tokenizer (Quran 55:3-4) |
| **ISM** | اسم | Name | Factored embedding (names = roots + patterns) |
| **Qalb** | قلب | Heart | Cardiac-oscillation attention |
| **Sam'** | سمع | Hearing | Causal/sequential attention path |
| **Basar** | بصر | Sight | Causal structural attention path |
| **Fuad** | فؤاد | Inner Heart | Fusion gate (Quran 67:23) |
| **Shura** | شورى | Consultation | Mixture of Experts (Quran 42:38) |
| **Lubb** | لُبّ | Core/Essence | Metacognition heads |
| **Mizan** | ميزان | Balance/Scale | Composite loss function (Quran 55:7-9) |
| **Nafs** | نفس | Self/Soul | Training curriculum stages |
| **Fitrah** | فطرة | Natural Disposition | Entropy regularization |
| **Hisbah** | حسبة | Self-Accountability | Wrong-confidence penalty |
| **Tasrif** | تصريف | Morphological Derivation | Phonemic operators |
| **Dhikr** | ذكر | Remembrance | Memory system (broader Mizan project) |

---

## License

Part of the [Mizan](https://github.com/CodeWithJuber/mizan) project. See the root `LICENSE` file.
