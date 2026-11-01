# Code audit (29 Oct 2026, read-only): the Ruh model as it actually is

Produced by a read-only code exploration of the repository at commit d400589, with measurements taken in the development sandbox (torch 2.14.1+cpu, 4 vCPU). Paths are relative to the repository root.

**Bottom line:** Ruh is a working 46M-parameter custom PyTorch transformer. Its training, provenance and evaluation tooling is careful. But no checkpoint exists that can hold a conversation.
- The published epoch-19 checkpoint is a 62-ID root generator.
- The only sentence-level (Bayan v2) run produced incoherent text and failed all 3 yes/no negation probes.
- No Urdu or Hinglish data exists anywhere in the pipeline.
- The repo's own CI-enforced data policy forbids training on hosted-model outputs.
- No online or real-time weight learning exists anywhere.

---

## 1. Architecture as implemented

**Tokenizer (Bayan)**
- **v1:** text becomes `(root_id, pattern_id)` per word (`ruh_model/tokenizer/bayan.py:222-278`).
  - The frozen vocabulary `ruh_model/tokenizer/legacy-v1.json` has **62 root IDs** (4 specials + 58 roots) and **17 patterns**. The source tables `backend/qca/roots.py` have 55 `ARABIC_ROOTS` and 117 `CONCEPT_MAP` entries (union 58 roots).
  - Stopwords map to `(PAD, STOPWORD)` (`bayan.py:251-252`). The stopword lists include not/no/nor and لا/لم/لن/ما/ليس (`bayan.py:83-85, 154-160`), so **negation is erased**.
  - Any root outside the 58 becomes UNK (`root_vocab.py:114-116`). Measured:
    - "ذهب الولد إلى المدرسة ليتعلم الكتابة": only كتب is known; 4 words become UNK; المدرسة is rooted as مدر and ليتعلم as تعل.
    - "The computer is not working today", "Bhai kya haal hai…" and Urdu "آپ کیسے ہیں؟" all decode to `<UNK>…`.
    - "العلم نور" decodes as "عِلْم نَارَ" (fire).
  - **The Q28 fallback is dead code.** `_ROOT_IPA_SIGNATURES` (`q28_articulatory.py:278`) uses hyphenated keys such as `س-ل-م`; 0 of 28 match the vocabulary, so `bayan.py:270-285` always yields UNK. Even if the keys matched, "computer" would map to س-ل-م and "working" to ر-ح-م, which is phonetically arbitrary.
- **v2:** BOS + raw UTF-8 bytes + EOS (`bayan.py:205-212, 227-234`). 256 byte IDs are appended after the 62, giving **318 IDs**. The pattern is always 0, so the root/pattern factorisation does nothing in v2. **v2 Ruh is a byte-level LM.** Lossless round-trip is verified (`train_sequence.py:351-354`).
- **Vendored package:** `packages/bayan` is `bayan-tokenizer` 0.2.0, stdlib-only, with the same 814-line roots table.

**Model** (`ruh_model/model.py`, defaults in `config.py:17-50`: d_model 512, 8 layers, 8 heads, n_roots 4000, n_patterns 200, SwiGLU d_ffn 1365)
- **ISM embedding** (`embedding/ism.py:57-102`): root(4000×64) and pattern(200×32) embeddings feed 4 projections, combined as root + pattern + interact·σ(gate), then RMSNorm and ×√d.
  - Output is weight-tied as `root_emb @ root_proj.T`, a rank-64 output layer (`ism.py:122`).
  - Measured ISM size is 361,216 params, so the real compression is 2,048,000/361,216 = **5.7×, not the 7.8×** claimed (`README.md:5,717`).
  - For v2's 318 live classes, a plain 318×512 table (162,816) would be **2.2× smaller** than ISM.
- **Qalb attention** (`attention/qalb.py:146-231`): standard multi-head attention with RoPE. The scale is multiplied by ψ = 1 + α·sin(2π·layer/T), where α and T are learned and T is modulated by a causal prefix-mean "complexity" term.
  - The `root_ids` argument is unused (`qalb.py:181-182`); `build_root_group_mask` (`:33`) is never called.
- **Sam-Basar** (`attention/sam_basar.py:85-182`): block 0 only. Both branches are now causal Qalb attentions with identical masks, fused by a sigmoid gate. Both run at t_step 0, so ψ = 1 and the oscillation is inactive in this block.
- **Shura MoE** (`layers/shura_moe.py`): 4 SwiGLU experts, top-2 routing, Switch-style auxiliary loss, in blocks 2, 4 and 6 (`model.py:52-62`). The "theology/ethics/language/general" labels (`:8`) are names only; nothing supervises them.
- **Lubb:** `LubbMetacognition` (`layers/lubb.py:71`) is never instantiated. With `use_lubb=True` the model adds a 2-layer sigmoid confidence head over mean-pooled hidden states (`model.py:64-73, 121-126`). The confidence is never surfaced at inference.
- **Adaptive depth:** `AdaptiveDepthGate` (`layers/adaptive_depth.py:16`) is unused, and `adaptive_depth_threshold` is never read.
- **Mizan loss** (`loss/mizan_loss.py:66-215`): CE + 0.1·calibration + 0.05·consistency + 0.01·fitrah + 0.02·hisbah.
  - Calibration and hisbah use argmax accuracy (`:223-246`), so they only train the confidence head.
  - Consistency is a KL divergence between pooled logits of paraphrase pairs (`training/trainer.py:261-276`).
  - Fitrah pulls entropy toward 0.3·ln(4000) = 2.49 nats, which is above the 1.7 nats CE already reached. **It works against a well-trained byte LM.**
  - `train_sequence.py:32-38`, used for every v2 run, **uses plain CE + MoE auxiliary loss only, with no Mizan terms.**
- **Generation** (`model.py:147-261`): temperature sampling with **no KV cache**; every new token re-runs the full forward pass.

**Parameter counts (measured by instantiating each config)**

| Config | Params |
|---|---|
| Default `RuhConfig` | **45,985,563** |
| `train.py` / `train_full.py` (v2 + Lubb) | **46,051,356** |
| `nutfah` / `alaqah` / `mudghah` / `khalq_akhar` | Same as above. They change only seq len, LR, epochs and batch (`training/curriculum.py:43-73`); RoPE is a non-persistent buffer. |
| `full_real.yaml` | Not read by any CLI (`README.md:886`; `train_full.py` has no `--config`) |
| `train_sequence` pilot (256-wide, 4 layers, no MoE) | 3,578,959 |
| Active per token (top-2 of 4 experts) | ≈ 33.4M |

- Per block: block 0 is 4.72M, dense blocks 3.15M, MoE blocks 9.44M.
- `config.estimated_param_count` (`config.py:67-95`) returns **27,537,664**, which is stale. The same 28M figure appears in `README.md:651` and `export/onnx.py:3`.

## 2. Training

**Data sources**
- **Defaults** (`data/pipeline.py:22-36`): Quran from Tanzil Uthmani Hafs via the pinned GitHub repo `risan/quran-json`, SHA-256-checked (`data/quranic.py:139-181`; CC BY 3.0 verbatim; KFGQPC cross-check differs at exactly 4 verses), plus `wikimedia/wikipedia` 20231101.ar at a pinned revision (CC-BY-SA/GFDL).
- **Mixing:** 0.30 Quran / 0.70 Arabic Wikipedia. Hadith, OPUS and morphology are weighted 0 (`train_full.py:53-59`).
- Custom Quran or Hadith sources require licence, attribution, revision and `training_permission: true`, and only work with v2 (`pipeline.py:70-102`).
- **Chat data** (`data/chat_sources.py:8-23`): OpenAssistant/oasst1 and CohereForAI/aya_dataset, both Apache-2.0 at pinned revisions. Filters are `('ar','en')` (`:26`) and Aya `arb`/`eng` only (`:98`). **No Urdu, Hindi or Hinglish anywhere.**
- `full_real.yaml` and `/api/ruh/data-stats` (`backend/api/main.py:7306-7312`) still list fake dataset IDs ("quran_corpus", "tashkeela", "opus-100/ar-en") with old weights.
- **Seed generator** (`data/generator.py:22-39`): 8 Arabic and 5 English templates such as "{w} نور" and "seek {w}". That gives 55 roots × 10 samples + 117 concept lines ≈ **667 lines**.

**Three training paths**
- `train.py`: seed or JSONL data, MizanLoss, now v2 + Lubb (`train.py:48`).
- `train_full.py`: streaming parquet, v2 + Lubb (`:583-585`).
- `train_sequence.py`: bounded, evaluated v2 byte windows; trains only on assistant bytes for dialogue (`data/sequence.py:65-108`). Groups are split leak-free across shared prompts (`:22-62`). It writes `evaluation.json` and refuses legacy resumes (`train_sequence.py:163-167`).

**Recorded runs and checkpoints (none are in the repo; `ruh_model/checkpoints/` does not exist)**
- **Epoch 19 (2026-09-29, Kaggle T4×2, ~50 min):** 4-stage curriculum on regenerated seed templates for all 50 epochs. Training loss went from 5.2660 to 1.0827 (`docs/TRAINING.md:103-123`). Training loss only.
  - It is Bayan v1 with a 128-token context (`docs/ruh-training-repair.md:3-9`; `ruh_model/README.md:7`).
  - **What it can do:** emit sequences drawn from the 58 roots, decoded as best-guess Arabic derivatives. Most prompts become UNK, and negation and function words are invisible. It cannot chat in any language.
- **v2 pilot** (3.58M params, 1,000 steps): held-out CE 6.92 → 2.10; samples repeated one phrase (`docs/ruh-training-repair.md:93-102`).
- **v2 full-size** (45,985,563 params, 8,437 steps / 1,350 s, 4,475,738 supervised bytes, mix 55% Arabic dialogue / 25% English dialogue / 20% Arabic text):
  - Held-out CE 8.35 → **1.73** (Arabic 1.14, English 1.71), over the first 16 eval batches only.
  - Outputs were **incoherent**, repeated 4-gram fractions 0.39 / 0.26, and **0/3 yes/no negation probes** passed.
  - It stays private and unapproved; model SHA `fcbd2dac…` (`:149-165`).
- A RunPod A100 continuation ($5 cap) is scripted (`:167-202`). No result is recorded. The Kaggle notebooks in `notebooks/kaggle/*` contain 0 saved outputs.

## 3. Evaluation

From `ruh_model/benchmarks/results/RESULTS.md` and the JSON files beside it:
- **Morphology:** root accuracy of the rule-based analyzer (not Ruh) is **0.4709 (81/172 types)** on a gold set drawn from the Q-CSMP v2 test split. It was 0.3488 before the U+0671 fix. Pattern accuracy is not scored. The CAMeL comparison was not run.
- **Q-CSMP v2 in-sample majority baseline:** acc 0.7831, macro-F1 0.4762 (n=3,135, 48 lemmas, 88 senses; 40 senses have zero recall). The pilot headline is negative for root features: Δ_Q = −0.0555 (`eval/qcsmp_eval.py:1-20`).
- **Dialect (NADI/MADAR):** could not be verified; no licensed data.
- **No trained Ruh checkpoint is wired into any eval.**
- `benchmarks/qcsmp_adjudicated.py` (28,841 records, 115 senses) only computes κ against the ≥0.61 target. No adjudication has been done.
- `data/quranic_evaluation.py` is a mechanical scorer for exact text, diacritics, negation and citations. It has no recorded results.

**"mizan.nlp sense-disambiguation trained on Q-CSMP v2"** refers to root `nlp/`, not `ruh_model/sense`.
- It is 48 per-lemma sklearn LogisticRegression models on character 2–4-gram surface features (`nlp/artifacts/default/manifest.json`, v1.2.1).
- **acc 0.8150, macro-F1 0.6380**, whole-surah holdout n=627.
- The manifest admits the gain over v1.2.0 comes entirely from merging senses (predictions are bit-identical). The earlier v1.0.0 scored 0.7592.
- `ruh_model/sense/disambiguate.py:1-25` is a keyword-overlap disambiguator with no model and **no measured accuracy**.

## 4. Integration

**`RuhModelProvider`** (`backend/providers_ruh.py`)
- Implements `create` and `stream` on `BaseLLMProvider`, with `supports_tools=False` and `max_output_tokens=1024` (`:14-16`).
- `stream` is a single-chunk wrapper (`:102-204`).
- **Bug:** the prompt budget is `max(64, max_seq_len − min(max_tokens,1024))` (`:60-73`). For a 384-context v2 checkpoint with max_tokens ≥ 320, prompts are clipped to the **last 64 bytes**, which drops the system prompt.

**Routing**
- A chat reaches Ruh when the agent or model is `ruh`/`ruh-local`. It needs `RUH_ENABLED` plus `RUH_MODEL_PATH` or `ruh_model/checkpoints/latest` (`backend/providers.py:1356-1368, 1486-1511`).
- `ruh-remote` goes to a RunPod endpoint (`providers_ruh_remote.py`). Its worker is not in the repo.
- `router/intelligent_router.py` is only used by tests.

**`/api/ruh/*` endpoints**
- `status`, `generate` (`main.py:6687-6757`).
- `tokenize` always uses v1 (`:6766`).
- `checkpoints`, `data-stats` (stale), `architecture` (`:7336-7421`). The architecture endpoint lists Lubb and AdaptiveDepth as active and Basar as bidirectional; all three are false.

**`/api/training/*`** (admin prefix, `main.py:573`)
- `start` spawns `python -m ruh_model.train` on a JSONL directory or seed data (`training_manager.py`).
- **It never trains from captured interactions.** Status always reports `automatic_weight_training: False`.

**Learner** (`backend/learner/ruh_learner.py`)
- Each capture stores prompt, response, provider, model and metadata (`session_id` or `client_id`) in SQLite at `$MIZAN_DATA_DIR/private/<sha256(owner)>/learner.sqlite3` (`:13-25, 69-78`).
  - `KhalifahAgent` instead uses a shared `data/mizan.db` (`agents/khalifah.py:94`).
- Capture is skipped for stateless runs or channels marked no-training, such as WhatsApp (`:108-111`; `memory/stateless.py:26-41`). It only runs when `capture_eligible` (`agents/base.py:3164-3189`).
- No other consent switch was found.
- Review (`/api/learner/review/{id}`) binds a SHA-256 content hash (`review_contract.py:15-19`).
- Export (`data_export.py`) is NDJSON `reviewed_model_interaction` with accepted rows and quality ≥ 0.8 only, excluding `mizan-owned`/`mizan-support`. **It deliberately has no `text`/`messages` field**, so it cannot feed the trainers (`:19-25, 77-101`).

## 5. Gaps to Ruh serving as Lisan

**Role mismatch.** Lisan writes programs, maps wording onto action schemas, and words answers (`docs/architecture.md:7`). Ruh has no tool or JSON decoding, no code data, and no instruction data in Urdu or Hinglish.

**Root space vs multilingual text**
- v1 cannot represent English, Urdu, Hinglish, most Arabic roots, or negation.
- v2 is lossless but byte-level: Arabic/Urdu script costs about 2 bytes per character, so sequences run several times longer than with BPE.
- The root factorisation is not used in v2.

**Data**
- Have: about 4.5M supervised bytes (≈ 5K Arabic + 1.5K English Aya, ≤3K OASST, about 1K Wikipedia articles).
- A compute-optimal budget for 46M params (~20 tokens/param) is about 0.9B tokens, so current data is about **0.5%** of that.
- Multilingual instruction following realistically needs a 0.3–1B parameter model and roughly 10B+ tokens. (Auditor's estimate, not a repo figure.)
- For comparison, the repo already has two larger own-model paths:
  - MiniMind `mizan-full-sft`: 64M params, 1,325,484 SFT rows (`docs/data-contracts-2026-10-25.md:10-11`).
  - Hybrid base model default: Qwen3-4B (`docker-compose.prod.yml:104-106`).

**Policy**
- Only human-written, independently reviewed examples may train the own model. Self-distillation and machine-generated tasks are forbidden and CI-enforced (`docs/automatic-learning.md:119-131`).
- So "base model for knowledge, Ruh learns from it" is **blocked by the repo's own rules** unless the owner changes the policy.
- No LoRA, DPO or online-update code exists for Ruh (`data-contracts:69`).

**Compute**
- Production backend: 2 CPU / 2 GiB, CPU-only torch (`docker-compose.prod.yml:126-130`; `Dockerfile.backend.prod:23-27`). "The 2 GB production backend cannot train." Runners: 2 GiB / 2 CPU.
- GPUs: Kaggle T4×2 at about 30 h/week (`ruh-training-repair.md:85-88`), plus RunPod on demand.
- Auditor's estimate: 500M params × 10B tokens ≈ 3e19 FLOPs, which is roughly 70 A100-hours or more than 500 T4-hours (about 18 weeks of Kaggle quota).

**CPU latency** (measured, 46.05M v2 config)

| Context | Forward, 4 threads | Forward, 2 threads |
|---|---|---|
| 128 bytes | 68 ms | 92 ms |
| 384 bytes | 225 ms | 305 ms |

- A measured generation of 64 bytes from a 64-byte prompt ran at **13.4 bytes/s**.
- With no KV cache, a 300-byte reply at full context takes about **90 s on the production 2-CPU limit**.

## 6. Novel ideas worth keeping

| Idea | Where | Tested? | Assessment |
|---|---|---|---|
| Root/pattern factorisation | `embedding/ism.py`; analyzer in `tokenizer/morphology.py` | `test_ism.py` (16 tests); analyzer measured at 47.1% | Keep as an *auxiliary* root/pattern channel added to a byte or BPE embedding, not as the vocabulary |
| Q28 articulatory basis | `tokenizer/q28_articulatory.py` | No unit tests in `ruh_model/tests` | A hand-coded 28×6 table, not trained; the tokenizer fallback is broken. Keep only for phonetics/tajwid research |
| Confidence head + calibration/hisbah | `model.py:64-73`; `mizan_loss.py:148-215` | Gradients tested (`test_review_repairs.py:131-141`) | Not exposed at inference. Worth keeping as an abstention signal, matching the fail-closed design in `nlp/` |
| Consistency loss | `trainer.py:261-283` | Tested (`test_review_repairs.py:152-169`) | No paraphrase data exists |
| Shura MoE sparse dispatch, BF16-safe Qalb | as above | `test_training_acceleration.py` | No ablation showing benefit over vanilla attention |
| Tajwid text rules engine | `tajwid/rules.py`, 1,271 lines, Hafs, cited sources | `tests/test_ruh_tajwid.py` (~40 rule tests) | Real deterministic value. The ASR bridge (`tajwid/scaffold.py`) is NotImplemented |
| Dialect normalisation | `dialect/normalize.py` | 17 unit tests | Never run on real dialect text |
| Provenance-pinned Quran data, surah-level splits, exactness scorers | `data/quranic.py`, `quranic_evaluation.py` | 22 tests | Strong; keep |
| Review/abstention gating | `review/`, learner contracts | Tested | Keep |

Overall: 246 test functions in `ruh_model/tests` (265 tests passed per `docs/review-2026-10-25.md:112`). There are no direct tests for MizanLoss fitrah/hisbah, Q28, Tasrif or AdaptiveDepth.

---

## Appendix: CPU training throughput of the Ruh architecture (measured 29 Oct 2026, 2 threads = production's 2 vCPU, batch 8 × seq 128, AdamW, CE loss)

| Config | Params | Train tok/s | Tokens/day at 25% duty | Days to reach 20×params tokens at 25% duty | Forward, 64-token context | Cost of one more token at ctx 64 (no KV cache) |
|---|---|---|---|---|---|---|
| tiny 128-d × 4 layers | 1.03M | 3,954 | 85M | 0.2 | 7.0 ms | 8.6 ms |
| small 256-d × 6 layers | 5.43M | 1,809 | 39M | 2.8 | 16.4 ms | 16.8 ms |
| mid 384-d × 8 layers | 15.39M | 1,034 | 22M | 13.8 | 35.8 ms | 31.1 ms |
| default 512-d × 8 layers + MoE | 45.99M | 574 | 12M | 74.2 | 86.3 ms | 81.7 ms |

Script: `scratchpad/ruh_cpu_bench.py`. Reading: a 5–15M-parameter model can be trained to a compute-optimal token budget on the production CPU within days to two weeks of 25%-duty background training; the 46M default would take about 2.5 months. Generation without a KV cache costs tens of milliseconds per token even for the small models, and grows with context.
