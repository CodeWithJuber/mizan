# Ruh speaker: a pre-registered GPU pilot

"The Most Merciful, taught the Qur'an, created man, [and] taught him eloquence" ([55:1–4](https://quran.com/55:1-4), Saheeh International).

The [Ruh reader](ruh-reader.md) is MIZAN's own 3.48M-parameter byte-level model; it tells languages apart and runs in shadow. The **Ruh speaker** is the same family grown to about 125M parameters and trained to continue text, so that it can later take over some of the language work MIZAN now hands the base model (Lisan). This page is the plan, written on 31 October 2026, **before any training**. Nothing has been launched, nothing has been spent, and nothing here turns the speaker on: it would ship `off`, and any adoption is the owner's decision.

- Code: `backend/tadbir/ruh_reader/speaker.py` (what the pilot is, the data rules, shards; no torch), `backend/tadbir/ruh_reader/speaker_net.py` (the network, training, evaluation; torch), `scripts/runpod_speaker.py` (the launcher), `tests/test_ruh_speaker.py`.
- Licences: `backend/tadbir/ruh_reader/LICENSES.md`, section "Speaker (planned)".

## 1. The model

The reader's block, unchanged (`net.Block`: pre-norm RMSNorm, rotary positions, SwiGLU, causal attention), the output layer tied to the token embedding, a KV cache for decoding, and the reader's language tokens: every document is `[language] tokens… [end]`, so the speaker gives log P(x | language) exactly as the reader does.

| | Pilot (`CONFIGS["pilot"]`) | Test (`CONFIGS["tiny"]`) |
|---|---|---|
| Tokens | byte-level BPE, 32,768 (17 special: end + 16 language slots) | the reader's bytes, 273 |
| d_model / layers / heads | 768 / 14 / 12 (head 64) | 32 / 2 / 2 |
| SwiGLU width | 2,048 | 64 |
| Context | 1,024 tokens | 64 |
| Dropout | 0 (one pass over fresh data) | 0 |
| Parameters | **124,278,528** (25,165,824 tied embedding; 14 × 7,079,424 per block; 768 final norm), checked by `test_the_pilot_has_about_125m_parameters` | 29,376 |

### Bytes or a byte-level BPE

The reader reads bytes. For the speaker the choice is decided by what a fixed amount of compute buys, measured on MIZAN's own text where it could be measured, and by what the published comparisons found where it could not.

**Text per FLOP.** Training costs about 6N FLOPs per position whatever a position holds (plus attention, 6·L·T·d). A byte model's position is one byte; a BPE's is a token of several bytes. MIZAN's languages make this worse for bytes than English alone suggests: a Devanagari letter is 3 UTF-8 bytes, an Arabic letter 2. Measured on 31 Oct 2026 in the development sandbox: a byte-level BPE trained with Hugging Face `tokenizers` 0.23.3 on the reader's own corpus (`train.tsv` of v1, 6.3 MB, equal bytes per language), read on the 16,212 held-out short messages of v1 and v1.1 (`short.tsv`, `validation.tsv`; lossless on 200 lines per language):

| UTF-8 bytes per token | en | hi | hi-latn | ur | ar |
|---|---|---|---|---|---|
| bytes (the reader) | 1 | 1 | 1 | 1 | 1 |
| BPE 32,768, GPT-2 split | 4.73 | **3.85** | 3.95 | 7.47 | 8.07 |
| BPE 32,768, whitespace split (chosen) | 4.73 | **10.71** | 4.62 | 7.36 | 7.83 |

The usual GPT-2 pre-tokeniser splits a word at every non-letter, and Devanagari vowel signs are marks, not letters, so Hindi words are cut at every matra; splitting on whitespace alone lifts Hindi from 3.85 to 10.71 bytes per token. These are short requests, in the domain the tokenizer was trained on: web text will give fewer bytes per token, and the pilot's manifest reports the real ratio per language (`held_out.*.bytes_per_token`).

So at the pilot's compute (2.03·10¹⁸ FLOPs, §3), a 125M byte model would read about 2.5 GB of text in all; the BPE model reads 4.6–10.7 times as much, about 15 GB.

**Bits per byte at fixed compute** was not measured here (no GPU). The published FLOP-controlled studies point the same way: SpaceByte ([arXiv:2404.14408](https://arxiv.org/abs/2404.14408)) "closes the performance gap between byte-level and subword autoregressive language modeling" only with its byte patching, and the Byte Latent Transformer ([arXiv:2412.09871](https://arxiv.org/abs/2412.09871)) ran "the first FLOP controlled scaling study of byte-level models up to 8B parameters" to show that patches, not plain bytes, scale as well as tokens. A plain byte transformer, the reader's design, is the baseline both improve on.

**Speaking costs steps.** A speaker writes one position at a time. A 300-byte Hindi reply is 300 decoding steps as bytes and about 28 as tokens; on MIZAN's 2 GB CPU server that is the difference between seconds and a fraction of one.

**What bytes keep, and BPE keeps too.** Every string has a token sequence (the 256 bytes are the BPE's alphabet, so it falls back to bytes by construction), decoding is exact, and bits per byte stay comparable: nats over the text's UTF-8 bytes. The one loss: the speaker's log P(x) is that of the text's own tokenisation, a lower bound on the probability summed over all tokenisations; the reader's is exact. The gate (§5, E2) measures whatever that costs.

**Decision:** byte-level BPE, whitespace pre-tokenisation, 32,768 tokens, learned from 100 MB of the selected training text, equal bytes per language (`speaker.train_bpe`).

## 2. The data

### Sources, each checked on its card or paper (31 Oct 2026)

Accepted (pinned in `speaker.SOURCES`: dataset commit and every file's SHA-256):

| Source | Language | Licence (where checked) | Pinned | Budget (training bytes) |
|---|---|---|---|---|
| [HuggingFaceFW/fineweb-edu](https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu) `sample/10BT` files 000, 001 | en | ODC-By 1.0, "also subject to CommonCrawl's Terms of Use" (card, Licensing Information) | commit `87f09149`, LFS SHA-256 | 4.5 GB |
| [HuggingFaceFW/fineweb-2](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2) `hin_Deva` file 000 | hi | ODC-By 1.0 + Common Crawl terms (card) | commit `af9c1333`, LFS SHA-256 | 4.0 GB |
| FineWeb-2 `urd_Arab` file 000 | ur | same | same | 3.0 GB |
| FineWeb-2 `arb_Arab` file 000 (Standard Arabic) | ar | same | same | 3.0 GB |
| FineWeb-2 `hin_Latn` and `urd_Latn` (0.198 and 0.129 GB of parquet) | hi-latn | same | same | all they give |
| Tatoeba per-language exports (eng, hin, urd, ara) | en, hi, ur, ar | CC BY 2.0 FR (as the reader) | SHA-256 recorded, weekly exports | all |
| MASSIVE 1.1, **train partition only** | en, hi, ur, ar | CC BY 4.0 (as the reader) | SHA-256 | all |

**Roman Hindi/Urdu exists licence-clean**: FineWeb-2's `hin_Latn` and `urd_Latn` are web text under ODC-By with a URL and crawl per document and an opt-out form. Their language labels are a classifier's (the card's pipeline), so some rows will be English or mixed; nothing was downloaded to look. Lughah reads Roman Hindi and Roman Urdu as one language (`hi-latn`), and so does the speaker.

**A caution on FineWeb-Edu.** Its text is Common Crawl web text, but its selection was made by a classifier trained on Llama-3-70B-Instruct's scores of 500k pages (card, "Annotation"). The speaker trains on the web text, never on Llama's outputs; the Llama 3 licence's naming clause concerns "outputs or results" used to train a model, and whether a filter's choice counts was not settled here. FineWeb (`HuggingFaceFW/fineweb`, ODC-By 1.0, commit `9bb295dd`, no model in its selection) is the drop-in replacement if the owner prefers; one line of `SOURCES` changes.

Rejected (`speaker.REJECTED`):

| Source | Why |
|---|---|
| Abhishekcr448/Hinglish-Everyday-Conversations-1M | MIT, but written by GPT-4o-mini (its card). OpenAI's terms forbid using output to build competing models; MIZAN's rule is that Anthropic and OpenAI output is for lookup only ([consent.md](consent.md)). **The reader v1 trained on it**; the owner decided on 31 Oct 2026 that the reader is retrained without it ([v2](ruh-reader.md#v2-without-model-written-text)) |
| ai4bharat/sangraha | Card CC BY 4.0, but "Synthetic" is English Wikipedia (CC BY-SA) machine-translated, i.e. share-alike re-licensed, and "Verified" holds OCR'd PDFs and transcribed "videos, podcasts, movies" with no source per row |
| ai4bharat/IndicCorpV2 | "Released under a CC-0 license" (card): packaging of crawled news AI4Bharat does not own, plain text with no source per line, so no removal request could ever be honoured |
| statmt/cc100 (has `hi_rom`, `ur_rom`) | Licence "unknown" on its card; "no claims of intellectual property", Common Crawl terms only; no source per paragraph |
| ai4bharat/samanantar, ai4bharat/BPCC | Qamus's earlier verdicts ([qamus.md](qamus.md)): NC with Quran translations inside; share-alike re-licensed |
| LingoIITGN/PHINC | CC BY 4.0 on a card over tweets its authors do not own: evaluation only, as Qamus used it |
| Dakshina | CC BY-SA 4.0: evaluation only, as Qamus used it |
| Wikipedia | CC BY-SA 4.0: share-alike, and whether trained weights are an adaptation is unsettled; not in the first run, the owner's call |

### What reaches the loss (`speaker.Judge`, in order)

1. **Its own script**: more than half the letters of its first 2,048 characters are in its language's script (`corpus.own_script`).
2. **Not a seed's**: its words as read (`ruh_reader.group_of`) are no line of Lughah's corpus in any split.
3. **Never scripture**: `ruh_reader.scripture` on every piece (each line, cut into runs of at most 64 words as Iqtibas counts them, each run starting half-way through the one before, because Iqtibas reads only a message's first 64 words; every span of up to 32 words lies whole inside a piece), with Iqtibas's Quran texts in memory. `prepare` refuses without them, as the reader's corpus build does. One flagged piece drops the whole document.
4. **Never hadith**: no run of 8 words in a row (`HADITH_RUN`) is a run of the six books' text, Arabic folded as the Truth Gate reads it and English as Iqtibas reads words, from the hadith-api editions MIZAN quotes from. The reader's filter is about the Quran only; this is the speaker's addition. 8 is twice the Quran's run, because the six books are ten times the mushaf's length and narrate in ordinary words: a rule written down, not fitted. The manifest counts what it drops.
5. **Once**: one document per group.
6. **Held out**: one group in 200, by the SHA-256 of `ruh-speaker-1:<group>`, is held out for good and never trained on; the first 4 MB of each language's held-out documents are read for bits per byte.

MASSIVE's dev and test partitions, the reader's measured slices, are never read; Lughah's seeds, the reader's held-out groups, are never trained on (rule 2).

**Making rule 3 affordable.** On the reader's corpus `scripture` reads 4–24 kB a second on one core; 15 GB would take hundreds of core-hours. `speaker.Sieve` asks it only of pieces it could flag at all, by exact necessary conditions read from the same texts: its Uthmani and mushaf conditions need Arabic words and a 4-word run of the sample or the mushaf (set lookups); its Iqtibas condition needs the span's first 4 words held, in order, inside one line of a translation, or their letters inside the transliteration (set lookups, then the text itself). Lughah's quote class is the vowelled Uthmani text, so a piece without Arabic letters is not read for it; on the reader's own corpus Lughah read none of 46,675 lines without Arabic letters as a quote. `test_the_sieve_never_lets_past_what_scripture_flags` checks that no piece `scripture` flags is skipped. Measured on one core, on documents of four ten-line paragraphs of the reader's corpus (60 per language; the same decisions with and without the sieve on the 15 compared per language):

| kB per second, one core | ar | en | hi | hi-latn | ur |
|---|---|---|---|---|---|
| `scripture` on every piece | 17.4 | 4.3 | 17.7 | 5.4 | 7.9 |
| with the sieve | 177.6 | 84.9 | 843.0 | 336.6 | 71.8 |
| documents dropped as scripture | 0 | 3 | 0 | 0 | 1 |

English and Urdu stay slowest: many of their ordinary 4-word runs are also in Saheeh's and Jalandhry's translations, so those pieces are read in full. At these rates the pilot's budgets take about 119,000 core-seconds (33 core-hours: en 53,000, ur 41,800, ar 16,900, hi 4,700, hi-latn 2,700): about 2.1 hours on 16 vCPUs. Web documents are longer and more varied than these, so this is an estimate; preparing is capped at 30% of the pod's life (§3), the languages are interleaved by their budgets so a cut stays balanced, and the manifest records what was reached.

**Records.** `shards.json` holds every source with its commit and file SHA-256s, the rules, what was kept and dropped by source and rule, the tokenizer's SHA-256, and every shard's file, tokens, bytes, documents and SHA-256. The kept documents' ids stay in `text/*.jsonl` beside them, so a removal request can be honoured by id.

## 3. Compute and cost

| | |
|---|---|
| Tokens | 2.5·10⁹ (20 per parameter), batches of 32 × 8 × 1,024 = 262,144 tokens, 9,537 steps |
| FLOPs | 6·N·D = 6 × 124,278,528 × 2.5·10⁹ = 1.864·10¹⁸, plus attention 6·L·T·d·D = 0.165·10¹⁸: **2.03·10¹⁸** |
| A100 (312 TFLOP/s dense bf16) | at 35% of peak, 5.2 h (4.0 h at 45%, 7.2 h at 25%) |
| H100 SXM (989 TFLOP/s dense bf16) | at 30%, 1.9 h |
| Data in hand | about 2.3·10⁹ tokens at the measured bytes per token (en 0.95, hi 0.37, ur 0.41, ar 0.38, Roman ≤ 0.2 billion): about one pass |

The share of peak was not measured (no GPU here). For scale: llm.c reported GPT-2 124M trained on 10B tokens in 90 minutes on 8 A100 SXM ([karpathy/llm.c#481](https://github.com/karpathy/llm.c/discussions/481)), which is about 59% of peak by the same count; plain PyTorch with `torch.compile` and fused attention is planned at 35%.

**Cost** (RunPod Secure Cloud on-demand, [runpod.io/pricing](https://www.runpod.io/pricing), "Updated October 8, 2026"): A100 80GB PCIe or SXM $1.79/h, H100 PCIe $2.89/h, H100 SXM $3.99/h; container disk $0.10/GB/month (200 GB: $0.027/h); network volume $0.07/GB/month. Billed by the second.

| On one A100 80GB PCIe | Hours | USD |
|---|---|---|
| Install, downloads (≈19.5 GB of pinned files), SHA-256 checks | ≈ 0.2 | 0.36 |
| Preparing (§2; capped at 30% of the life) | 1–2.1 expected, 4.0 at most | 1.8–3.8 (7.3) |
| Training at 35% of peak | 5.2 | 9.3 |
| Final evaluation, weights | ≈ 0.1 | 0.2 |
| **Expected** | **6.5–7.6** | **≈ 12–14** |
| **Hard cap** | 13.5 (48,530 s) | **25.00** (worst case 24.50 + any network volume's storage) |

The A100 is the default: preparing is CPU-bound, and on an H100 the same hours cost twice as much (the H100's lifetime under $25 is 6.1 h). If training is slower than planned, it stops at the time it has, with its learning rate annealed (the cosine follows whichever ends first, the steps or the clock), and reports how far it got.

### The cap, enforced (`scripts/runpod_speaker.py`)

- `--confirm-budget USD` is required, and refused above $25 for this first run (above $1 for the smoke launch).
- The pod's life is `(budget − max($0.25, 2%)) / (GPU hourly + disk hourly)` seconds, counted from before the pod is created: 48,530 s at $25 on the A100. Below 2 hours the launch is refused.
- The GPU's price is read from the catalog (`GET /v2/catalog/gpus`, `price.secure`) and the created pod's own `cost` is checked against it; a pod that costs more is deleted at once.
- Three things end the pod by the deadline: the launcher deletes it at the deadline, or as soon as it has exited, failed, or the launcher is interrupted, and checks it is gone; a watchdog inside the pod deletes it at the same deadline with the pod-scoped key RunPod gives every pod (the owner's key never enters the pod); training stops 20 minutes before it to write the final weights.
- RunPod documents the in-pod key only as "Pod-scoped API key". So `--smoke` first runs a 10-minute RTX 4090 pod (about $0.15; no volume, no token, no placement filters) whose only work is to delete itself after 90 s, and `--launch` refuses until a smoke record (`~/.mizan/ruh-speaker-smoke.json`) says it could.
- `RUNPOD_API_KEY` (and `HF_TOKEN`) are read from the environment and never printed, logged or written; error bodies are not shown, since they may echo what was sent.
- The default is a dry run. Its output for `--confirm-budget 25 --return volume` (the bootstrap shortened here):

```json
{
 "dry_run": true,
 "budget": {"usd": 25.0, "gpu": "NVIDIA A100 80GB PCIe", "gpu_hourly_usd": 1.79,
            "disk_hourly_usd": 0.0274, "safety_usd": 0.5, "lifetime_seconds": 48530,
            "worst_case_usd": 24.5, "prepare_seconds_at_most": 14559,
            "train_seconds_about": 32771, "network_volume": "billed apart: $0.07/GB/month"},
 "requests": [
  {"method": "GET", "url": "https://api.runpod.io/v2/catalog/gpus", "headers": {"Authorization": "Bearer <redacted>"}},
  {"method": "POST", "url": "https://api.runpod.io/v2/pods", "headers": {"Authorization": "Bearer <redacted>"},
   "body": {"name": "ruh-speaker-pilot-…", "cloud": "SECURE",
            "gpu": {"id": "NVIDIA A100 80GB PCIe", "count": 1, "minCudaVersion": "12.6",
                    "minVcpuCountPerGpu": 16, "minRamPerGpu": 64},
            "image": "pytorch/pytorch@sha256:1262abc856a428933c0477b4be87079173a0b087b7691c47fcb396b7b5775c56",
            "entrypoint": ["python", "-c", "<bootstrap>"], "disk": 200, "ports": [],
            "env": {"RUH_REVISION": "<commit>", "RUH_SOURCE_SHA256": "<SHA-256 of the archive, at launch>",
                    "RUH_DEADLINE_EPOCH": "<now + lifetime_seconds, at launch>", "RUH_RETURN": "volume",
                    "RUH_PLAN": "pilot", "RUH_WORK": "/workspace/ruh-speaker"},
            "mounts": {"network": [{"volumeId": "<volume>", "path": "/workspace"}]},
            "dataCenterIds": ["<the volume's data center>"]}},
  {"method": "GET", "url": "https://api.runpod.io/v2/pods/<id>"},
  {"method": "DELETE", "url": "https://api.runpod.io/v2/pods/<id>"}
 ]
}
```

**The API.** RunPod's REST API v1 is deprecated and retired on 15 November 2026 ([overview](https://docs.runpod.io/api-reference/overview)), so the launcher uses v2 ([create](https://docs.runpod.io/api-reference-v2/pods/create-a-pod), [get](https://docs.runpod.io/api-reference-v2/pods/get-a-pod), [terminate](https://docs.runpod.io/api-reference-v2/pods/terminate-a-pod), [action](https://docs.runpod.io/api-reference-v2/pods/trigger-a-pod-state-transition), [GPU catalog](https://docs.runpod.io/api-reference-v2/catalog/list-gpu-types); OpenAPI 2.0.0 at `https://api.runpod.io/v2/openapi.json`), read on 31 Oct 2026. It has not been called: field names come from the published schema only. The older `scripts/launch_runpod_training.py` (the root-space model's continuation) uses v1 GraphQL and will need the same move.

**Inside the pod.** The image is `pytorch/pytorch:2.14.1-cuda12.6-cudnn9-runtime` by digest (pushed 30 Sep 2026; torch 2.14.1 is pyproject's pin). The bootstrap fetches the reviewed commit's source archive from GitHub, checks the SHA-256 the launcher computed, and hands over to `runpod_speaker.py pod`: `pip install -e .[ml]` with `tokenizers==0.23.3`, `huggingface_hub==2.3.0`, `pyarrow==25.0.1`; `speaker prepare --plan pilot` (skipped when its shards verify); `speaker train` (resumes from its last whole checkpoint); the weights returned (§6); the pod deleted. On any failure it deletes its own pod rather than exit, since an exited container may be restarted.

## 4. Training (`speaker_net.train`)

AdamW (β 0.9, 0.95; weight decay 0.1, none on the embedding and norms), peak learning rate 10⁻³ after 200 warm-up steps, a cosine to a tenth of it, gradients clipped to 1, bfloat16 autocast, `torch.compile`. Each step's windows are drawn uniformly over every training token by a generator seeded with (seed, step, micro-batch), so the data a step sees depends on the step alone: a run resumed from a checkpoint continues exactly where it stopped (`test_training_resumed_from_a_checkpoint_matches_one_run`: 2 + 2 steps give the same weights as 4, bit for bit). Checkpoints every 20 minutes: weights, optimizer and state with a SHA-256 manifest, written to a temporary folder and renamed whole, `latest.json` replaced last; resuming takes the newest checkpoint whose files match their SHA-256 and whose run key (configuration, plan, the shards' SHA-256) is this run's, so a damaged checkpoint falls back to the one before and another run's is never continued. `final/` holds the weights, the tokenizer, the report (held-out bits per byte, steps, tokens, FLOPs, seconds, the history every 1,000 steps) and their SHA-256 manifest; `speaker_net.load_final` refuses files that do not match.

## 5. Evaluation, fixed before training

Default: **off**. Nothing below changes what MIZAN does; each result is reported, and a passed bar only makes the speaker eligible for the owner's decision.

**E1. Held-out bits per byte, per language.** On the held-out documents of §2 rule 6: nats of the text tokens (not the language and end tokens) over the text's UTF-8 bytes, per language, at the end and every 1,000 steps. Reported, not gated. A healthy run's final bits per byte are below its first evaluation's in every language; one that is not is reported as a failed run. Bits per byte are not compared with the reader's: the reader reads lower-cased letters only, the speaker text as written.

**E2. The reader's gate, with the speaker in the reader's place** (`speaker_net.gate_on_validation`), on v1.1's validation slices (`validation.tsv`, built beside the reader's corpus; MASSIVE `dev` and never-read Roman rows, none trained on by the speaker). Each message's own words as written (`lughah.own_words` with the held-out Lughah) are scored under each language token; n is their UTF-8 bytes and ñ the calibration half's median. κ, γ (`fit_reader`) and b (`fit_b`) are fitted on the calibration half only; `ruh_reader.gate` is run on the gate half unchanged, as the speaker's **first** test: log-loss P(not better) < 0.05 by the grouped paired bootstrap, and the paired e-value on accuracy ≥ k(k+1)/α = **40**. To be reported beside it (the eval script's slices, as for v1.1): the speaker alone (accuracy, log-loss), per language and part, and reader v1.1 on the same half. Known limit, from v1.1: Hinglish-1M labels English rows as Roman Hindi/Urdu, which caps every arm's Roman accuracy there.

**E3. One Lisan task: putting MIZAN's verified results into words.** `Lisan.express(request, facts, language)` (called from `tadbir/engine.py`) turns the result of a recipe MIZAN computed and verified into a reply in the user's language. The first task offered to the speaker is that, for three recipes: **compute** (arithmetic), **date** (Gregorian and Hijri) and **Quran counts** (`quran_count`: surahs, ayahs). A pretrained model cannot do it as is: this needs a second, supervised stage (a separate run, a separate approval), trained only on MIZAN's own wording (its phrase tables in `express.py`, and Ta'allum's verified wordings of people who chose `training: on`, reviewed), never on a teacher's output.

- **Items**: the AGI test's items whose Fahm family is one of the three, plus 1,000 generated from the same recipes by a fixed-seed generator (seed 0; 200 per language: en, hi, ur, ar, Roman Hindi/Urdu; the three recipes in equal shares), all run through Muqabala (`POST /api/debug/compare`), stateless. The teacher arm is Lisan as it runs today (Wazn's model); the speaker arm is the same pipeline with the speaker as Lisan for `express` only.
- **Shown or not**: the speaker writes first; MIZAN shows its reply only when (a) Muqabala finds no unsupported number and every number of the verified result is in it, (b) Lughah reads it in the request's language, (c) it quotes no Quran or hadith (Sidq, Iqtibas), (d) it claims no action (Muqabala). Otherwise the teacher writes, as now.
- **Faithful**: (a)–(d), and (e) the multilingual NLI model Ahl al-Dhikr uses reads the reply as entailing MIZAN's own statement of the result and that statement as entailing the reply (both ways: nothing missing, nothing added).
- **A loss** is an item whose speaker reply was shown and is not faithful by (e) while the teacher's reply is faithful.
- **The bar**: H₀ "speaker-first adds an error on at least δ = 1% of requests" is rejected when the e-process E = Π (1 + λ(δ − Xᵢ)), Xᵢ = 1 for a loss, λ = 1/(2(1 − δ)), reaches 1/α = 20 over the 1,000 items (valid at any stopping time by Ville's inequality). With no loss E reaches 154; each loss halves it, so two losses still pass and three do not.
- **Reported**: the share of replies shown without a teacher call (Wilson interval), per recipe and language; latency on MIZAN's CPU; the teacher calls and their cost (Iqtisad).

## 6. How the weights come back

Two ways; the launcher needs one named (`--return`) and has no default. The owner chooses.

**A. A private Hugging Face repository under the owner's account** (`--return hf --hf-repo <owner>/<name>`). The pod uploads `final/` (fp32 weights, 497 MB; tokenizer; report; manifest; the shards' manifest) and refuses if the repository is not private. It needs the owner's OK to give the pod an `HF_TOKEN`: best a fine-grained token that can write to that one repository. The token sits in the pod's environment in RunPod's records while the pod lives (the v2 pod object returns `env`); the launcher never prints it, and inside the pod only the upload reads it (installing, preparing and training run without it). A container restart loses the run's checkpoints (container disk), so a restarted pod starts training again.

**B. A RunPod network volume** (`--return volume --network-volume <id> --data-center <its data center>`). The owner creates a volume (about 60 GB: 19.5 GB of sources, ≈15 GB of selected text, ≈5 GB of shards, checkpoints; $4.20 a month at $0.07/GB/month, billed apart from the $25) in a data center with A100 stock; the pod works in `/workspace/ruh-speaker` on it, so a restarted container resumes from its checkpoint, and nothing leaves RunPod. Afterwards the weights are fetched without a GPU: the volume's S3-compatible API, or a small CPU pod with the volume attached and `runpodctl send` (RunPod's network-volume docs). Then the volume is deleted, or its `sources/` and `text/`.

Either way, `speaker_net.load_final` checks every file's SHA-256 before the weights are read.

## 7. Running it

```bash
export RUNPOD_API_KEY=…          # never typed into a command line or a file in the repo
python scripts/runpod_speaker.py --revision <commit> --confirm-budget 25 --return volume \
    --network-volume <id> --data-center <id>                 # dry run: prints the requests
python scripts/runpod_speaker.py --revision <commit> --confirm-budget 1 \
    --smoke --launch                                         # ≈ $0.15: can the pod end itself?
python scripts/runpod_speaker.py --revision <commit> --confirm-budget 25 --return volume \
    --network-volume <id> --data-center <id> --launch        # the pilot
```

The launcher writes `ruh-speaker-launch/pod-recovery.json` (pod id, deadline, budget; no secrets) before it polls, so a pod can be found and deleted by hand if this machine dies; the watchdog inside the pod ends it at the deadline regardless.

Locally, without a GPU: `cd backend && python -m tadbir.ruh_reader.speaker prepare --plan tiny --tsv docs.tsv --out /tmp/s` and `… train --shards /tmp/s --out /tmp/r`.

**On a Mac with Apple silicon** (the owner's M5 Max, 64 GB), training runs on its GPU through Metal (`--device mps`; chosen by default when there is no CUDA). It runs in fp32, without autocast, and `torch.compile` is used only on CUDA. The plan's 32 windows of 1,024 tokens do not fit in one pass there: on 6 Nov one pass held 73 GB and filled 53 of 54 GB of swap, a step took 2,258 s, and the first call was killed (exit 137). `--rows 8` runs each micro-batch as four passes of 8 windows: the same windows, the same gradient up to the order of float sums and the same run key, so the Mac's checkpoints and a GPU pod's continue each other (`test_fewer_rows_per_pass_train_the_same_run`). Leave `--seconds` out on the Mac: the cosine ends at the last step or at the end of `--seconds`, whichever comes first, so every call of `--seconds 28800` would bring the learning rate down to `min_lr` and the next would raise it again. A checkpoint is written every 20 minutes; when the Mac is needed, stop the process and later run the same command, which resumes from the newest whole checkpoint (at most 20 minutes lost):

```bash
pip install -e ".[ml]"                                    # torch with Metal (MPS) on macOS
cd backend
python -c "import torch; print(torch.backends.mps.is_available())"   # must print True
python -m tadbir.ruh_reader.speaker prepare --plan pilot --out ~/ruh/shards   # downloads the pinned sources
python -m tadbir.ruh_reader.speaker train --shards ~/ruh/shards --out ~/ruh/run --device mps --rows 8
```

The pilot's numbers in §3 are for an A100 or H100 (about 2·10¹⁸ FLOPs, ≈ 19.5 GB of downloads); on the Mac with `--rows 8` (8 Nov, a 25 GB process; Ollama held another 25 GB of the GPU's memory for part of it) steps 2–15 took 1,282 s, about 92 s a step or 2,900 tokens a second, so the pilot's 9,537 steps need about ten days of running. Read the pace from `state.json` in each checkpoint (`step`, `elapsed`).

## 8. Limits

- Not measured here: the GPU's share of peak, the real bytes per token of web text, how long preparing takes on web documents, how many documents each rule drops, and the quality of FineWeb-2's Roman subsets. All are in the run's report.
- The hadith rule (8 words in a row) is written down, not fitted; it may drop ordinary narrative Arabic and English, and its count is reported.
- Rule 3 drops a document for one flagged piece; the reader's filter is cautious (46 of its 3,310 training seeds), so a share of ordinary Islamic and religious text is dropped too: a cautious mistake, not a leak.
- The RunPod v2 calls are written from the published schema and have not been sent; the smoke launch is their first test.
- The speaker as Lisan (E3) needs a second stage that is only described here.
