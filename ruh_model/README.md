# Ruh Model (روح)

> **Arabic-native language model built on triconsonantal root morphology.**

Ruh is a pure-PyTorch transformer that operates in **root-space** instead of token-space. Where standard LLMs split text into BPE subwords, Ruh tokenizes text as `(root_id, pattern_id)` pairs — the same factored representation used by Arabic morphology for 1,400+ years. This yields **146× embedding compression** over standard lookup tables and enables cross-lingual understanding via shared Semitic roots.

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

# 1. Train Stage 1 with 100K real samples (Quran, Hadith, Wikipedia, OPUS, Tashkeela)
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
│   Factored: root + pattern  │  146× compression vs standard lookup
│   Gated additive fusion     │
│   + RoPE positional enc     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   Block 0: SamBasarDual     │  Dual attention (hearing + sight)
│   ├ Sam' (سمع): causal      │  Sequential/temporal processing
│   ├ Basar (بصر): bidirect.  │  Structural/pattern recognition
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
| Factored embedding | Root × Pattern decomposition gives 146× compression |
| Cardiac oscillation | Bio-inspired rhythmic attention modulation (Qalb = heart) |
| Dual first layer | Separate causal (Sam'/hearing) and bidirectional (Basar/sight) pathways |
| 5-component loss | Beyond CE: calibration, consistency, fitrah (entropy), hisbah (accountability) |
| Curriculum training | 4 developmental stages inspired by Quran 23:12-14 |

---

## Installation

### Prerequisites

- Python 3.11+
- PyTorch 2.0+ (CPU or CUDA)
- PyYAML

### Install Dependencies

```bash
# From mizan project root
pip install torch pyyaml

# Or use the project's requirements
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

Each line is a JSON object:

```json
{"text": "The concept of knowledge is fundamental to theology", "lang": "en", "domain": "theology"}
{"text": "علم مشتق من الجذر ع-ل-م", "lang": "ar", "domain": "theology"}
```

**Template categories** (distribution: 50% English, 25% Arabic, 25% cross-lingual bridge):

- **English**: `"The concept of {derivative_en} is fundamental to {domain}"`
- **Arabic**: `"{derivative_ar} مشتق من الجذر {root}"`
- **Bridge**: `"The Arabic word {derivative_ar} means {derivative_en} and comes from the root {root}"`

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

Required YAML keys: `name`, `max_seq_len`, `lr`, `epochs`, `batch_size`.

### Full Real-Data Training

The `train_full.py` CLI streams data directly from **5 HuggingFace datasets** and trains through the Nafs curriculum. No manual data download required.

```bash
pip install datasets  # one-time dependency
```

**Data sources streamed automatically:**

| Loader | HuggingFace Dataset | Default Weight | Content |
|--------|-------------------|---------------|---------|
| `QuranLoader` | `ImruQays/Quran-Classical-Arabic-English-Parallel-texts` | 30% | 6,236 Quranic verses (Arabic + English) |
| `HadithLoader` | `SaiedAlshahrani/Hadith-Corpus` | 20% | Hadith collections (Arabic) |
| `ArabicWikiLoader` | `wikimedia/wikipedia` (ar) | 25% | Arabic Wikipedia articles (~10 GB, streamed) |
| `OpusLoader` | `Helsinki-NLP/opus-100` (ar-en) | 15% | Parallel Arabic-English sentences |
| `MorphoLoader` | `Bakbak/tashkeela-arabic-diacritized-text-corpus` | 10% | Diacritized morphological text |

#### Single-Stage Training

```bash
# Train Stage 1: nutfah (simple sentences, 128 seq len)
python -m ruh_model.train_full --stage nutfah --samples 100000

# Train Stage 2: alaqah (paragraphs, 512 seq len)
python -m ruh_model.train_full --stage alaqah --samples 200000 \
    --resume-from ruh_model/checkpoints/nutfah_final

# Train Stage 3: mudghah (documents, 1024 seq len)
python -m ruh_model.train_full --stage mudghah --samples 300000 \
    --resume-from ruh_model/checkpoints/alaqah_final

# Train Stage 4: khalq_akhar (full capability, 2048 seq len)
python -m ruh_model.train_full --stage khalq_akhar --samples 500000 \
    --resume-from ruh_model/checkpoints/mudghah_final
```

#### Full 4-Stage Curriculum (End-to-End)

```bash
# Run ALL stages automatically — each resumes from the previous
python -m ruh_model.train_full --all-stages --samples 500000 --device cuda --verbose

# With Apple Silicon (MPS)
python -m ruh_model.train_full --all-stages --samples 500000 --device mps

# Auto-detect best device
python -m ruh_model.train_full --all-stages --samples 500000 --device auto
```

#### Custom Data Mixing

```bash
# More Quran, less Wikipedia
python -m ruh_model.train_full --stage nutfah --samples 100000 \
    --quran-weight 0.5 --wiki-weight 0.1

# Hadith-heavy training
python -m ruh_model.train_full --stage alaqah --samples 200000 \
    --hadith-weight 0.5 --quran-weight 0.2 --wiki-weight 0.15 \
    --opus-weight 0.10 --morpho-weight 0.05
```

#### GPU Training (CUDA / MPS)

```bash
# NVIDIA GPU
python -m ruh_model.train_full --all-stages --samples 1000000 --device cuda

# Apple Silicon (M1/M2/M3/M4)
python -m ruh_model.train_full --all-stages --samples 500000 --device mps

# Multi-GPU note: not yet supported — use single GPU or DataParallel wrapper manually
```

#### train_full.py CLI Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `--stage` | `nutfah` | Curriculum stage: `nutfah`, `alaqah`, `mudghah`, `khalq_akhar` |
| `--all-stages` | false | Run all 4 stages in sequence (auto-resume between stages) |
| `--samples` | `100000` | Total samples to stream from HuggingFace |
| `--device` | `auto` | Device: `cpu`, `cuda`, `mps`, or `auto` |
| `--data-dir` | None | Train from pre-materialized JSONL instead of streaming |
| `--prepare-only` | false | Download + save to JSONL only (no training) |
| `--output-dir` | `ruh_model/data/real` | Output directory for `--prepare-only` |
| `--resume-from` | None | Checkpoint directory to resume from |
| `--checkpoint-dir` | `ruh_model/checkpoints` | Where to save checkpoints |
| `--quran-weight` | 0.30 | Quran data proportion |
| `--hadith-weight` | 0.20 | Hadith data proportion |
| `--wiki-weight` | 0.25 | Arabic Wikipedia proportion |
| `--opus-weight` | 0.15 | OPUS parallel corpus proportion |
| `--morpho-weight` | 0.10 | Tashkeela morphology proportion |
| `--weight-decay` | 0.01 | AdamW weight decay |
| `--max-grad-norm` | 1.0 | Gradient clipping norm |
| `--warmup-fraction` | 0.1 | LR warmup fraction |
| `--log-every` | 50 | Log loss every N steps |
| `--verbose` | false | Debug-level logging |

### Prepare Data to Disk

For offline training or repeated experiments, materialize HuggingFace data to JSONL first:

```bash
# Download 500K samples, split by domain+language
python -m ruh_model.train_full --prepare-only --samples 500000 --output-dir data/real

# Creates files like:
#   data/real/quran_ar.jsonl     (Quran Arabic)
#   data/real/quran_en.jsonl     (Quran English translations)
#   data/real/hadith_ar.jsonl    (Hadith)
#   data/real/general_ar.jsonl   (Wikipedia)
#   data/real/parallel_ar.jsonl  (OPUS Arabic side)
#   data/real/parallel_en.jsonl  (OPUS English side)
#   data/real/morphology_ar.jsonl (Tashkeela)

# Then train from disk (much faster re-runs, no network needed)
python -m ruh_model.train_full --stage nutfah --data-dir data/real
python -m ruh_model.train_full --stage alaqah --data-dir data/real \
    --resume-from ruh_model/checkpoints/nutfah_final
```

### Real Data Pipeline (Programmatic)

For custom training scripts, use `RealDataPipeline` directly:

```python
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.data.pipeline import RealDataPipeline

tokenizer = BayanTokenizer()
pipeline = RealDataPipeline(
    tokenizer=tokenizer,
    max_seq_len=512,
    mixing_ratios={
        "quran": 0.3,
        "hadith": 0.2,
        "arabic_wiki": 0.25,
        "opus": 0.15,
        "morphology": 0.1,
    },
)

# Stream raw samples
for sample in pipeline.stream(max_samples=1000):
    print(sample["text"][:80], sample["lang"], sample["domain"])

# Get tensor batches directly
for batch in pipeline.get_dataloader(max_samples=5000, batch_size=8):
    print(batch["root_ids"].shape)  # (B, S)
    break
```

Or use the `StreamingRuhDataset` for PyTorch `DataLoader` integration:

```python
from ruh_model.data.streaming_dataset import StreamingRuhDataset
from ruh_model.data.collator import RuhCollator
from torch.utils.data import DataLoader

dataset = StreamingRuhDataset(
    tokenizer=tokenizer,
    max_seq_len=512,
    max_samples=100000,
)
loader = DataLoader(dataset, batch_size=8, collate_fn=RuhCollator(pad_id=0))

for batch in loader:
    print(batch["root_ids"].shape)
    break
```

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
# [(1, 0), (42, 3), (0, 10), (0, 10), (87, 3), (0, 10), (0, 10), (65, 3), (2, 0)]
#  BOS      knowledge  is(stop)  the(stop)  light     of(stop)  the(stop) soul      EOS

# Decode back to approximate text
text = tok.decode(tokens)
print(text)
# "knowledge light soul"  (stopwords dropped, best-effort reconstruction)

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
print(output.shape)  # (1, 54) — original 4 + 50 generated

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
#   my_model/v1/config.json   (all RuhConfig fields)
#   my_model/v1/model.pt      (PyTorch state dict)

# Load from directory
loaded = RuhModel.from_pretrained("my_model/v1")
print(loaded.count_parameters())
```

**Checkpoint format:**

```
my_model/v1/
├── config.json    # {"d_model": 512, "n_heads": 8, ...}
└── model.pt       # torch state_dict
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

**Compression ratio:** Standard embedding for 4,000 roots at d_model=512 requires 2,048,000 parameters. ISM uses `4000×64 + 200×32 = 262,400` embedding params — a **146× reduction** with the factored representation.

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
- **Basar** (بصر, "Sight"): Bidirectional attention — processes structural patterns like reading written text. Uses QalbAttention without masking.
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

The confidence output feeds into the Mizan loss calibration and hisbah terms.

### Adaptive Depth

Per-layer gate that enables early computation exit using ACT (Adaptive Computation Time):

```python
# Each layer computes a halting probability
halt_prob = sigmoid(gate(hidden))  # (B, 1)
# When cumulative halt > threshold, skip remaining layers
```

Includes regularization loss that encourages the model to use fewer layers when the input is simple.

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
| `test_ism.py` | ISMEmbedding forward/backward, output projection weight tying, shape validation, gradient flow |
| `conftest.py` | Shared fixtures: `tiny_config` (small RuhConfig for fast tests), `tokenizer`, `sample_text` |

---

## Project Structure

```
ruh_model/
├── __init__.py              # Package entry: exports RuhConfig, RuhModel (v0.1.0)
├── config.py                # RuhConfig dataclass (all hyperparameters)
├── model.py                 # RuhModel: full transformer assembly
├── train.py                 # CLI: seed-data training (python -m ruh_model.train)
├── train_full.py            # CLI: real-data training (python -m ruh_model.train_full)
│
├── attention/
│   ├── __init__.py
│   ├── qalb.py              # QalbAttention: cardiac-oscillation MHA + RoPE
│   └── sam_basar.py         # SamBasarDual: causal + bidirectional fusion
│
├── embedding/
│   ├── __init__.py
│   ├── ism.py               # ISMEmbedding: factored root+pattern (146× compression)
│   └── rope.py              # RotaryPositionEncoding + RMSNorm
│
├── layers/
│   ├── __init__.py
│   ├── transformer_block.py # RuhBlock: pre-norm residual (attn + FFN)
│   ├── ism_ffn.py           # ISMFFN: SwiGLU feed-forward
│   ├── shura_moe.py         # ShuraMoE: 4 domain experts, top-2 routing
│   ├── lubb.py              # LubbMetacognition: confidence/yaqin/quality heads
│   └── adaptive_depth.py    # AdaptiveDepthGate: early exit
│
├── loss/
│   ├── __init__.py
│   └── mizan_loss.py        # MizanLoss: 5-component composite objective
│
├── tokenizer/
│   ├── __init__.py
│   ├── bayan.py             # BayanTokenizer: text → (root_id, pattern_id)
│   ├── morphology.py        # ArabicMorphAnalyzer: suffix stripping + root extraction
│   ├── english_bridge.py    # EnglishRootBridge: concept-map + stemmer fallback
│   ├── q28_articulatory.py  # Q28: 28 Arabic letters as phonetic basis (6D vectors)
│   ├── root_vocab.py        # RootVocab: root↔ID and pattern↔ID mappings
│   └── tasrif_ops.py        # TasrifEngine: 15 morphophonemic operators
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
│   ├── streaming_dataset.py # StreamingRuhDataset: HuggingFace → tokenized (no RAM)
│   ├── collator.py          # RuhCollator: right-padding for batches
│   ├── generator.py         # SeedDataGenerator: template-based data synthesis
│   ├── pipeline.py          # RealDataPipeline: multi-loader weighted streaming
│   └── loaders/
│       ├── __init__.py
│       ├── quran_loader.py      # HuggingFace / local Quran text loader
│       ├── hadith_loader.py     # Hadith collection loader
│       ├── arabic_wiki_loader.py # Arabic Wikipedia loader
│       ├── opus_loader.py       # OPUS parallel corpora loader
│       └── morpho_loader.py     # Tashkeela morphological data loader
│
├── configs/
│   ├── nutfah.yaml          # Stage 1 training config
│   ├── alaqah.yaml          # Stage 2 training config
│   ├── mudghah.yaml         # Stage 3 training config
│   ├── khalq_akhar.yaml     # Stage 4 training config
│   └── full_real.yaml       # Reference config for large-scale real-data runs
│
├── tests/
│   ├── conftest.py          # Shared test fixtures
│   ├── test_bayan.py        # Tokenizer tests
│   └── test_ism.py          # Embedding tests
│
└── benchmarks/
    └── __init__.py          # Placeholder for future benchmarks
```

---

## API Integration

Ruh is integrated into the Mizan backend. The frontend can interact with the model via REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ruh/status` | GET | Model status (enabled, device, loaded) |
| `/api/ruh/{agent_id}` | GET | Agent-specific Ruh model info |

**Backend code path:** `backend/api/main.py` → `backend/core/ruh_engine.py`

When properly configured with a trained model path:

```bash
# In .env
RUH_MODEL_PATH=ruh_model/checkpoints/epoch_4
RUH_DEVICE=cpu  # or cuda
```

The model loads on startup and provides root-space inference for the cognitive architecture.

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
| **Basar** | بصر | Sight | Bidirectional/structural attention path |
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

Part of the [Mizan](https://github.com/jubershaikh/mizan) project. See the root `LICENSE` file.
