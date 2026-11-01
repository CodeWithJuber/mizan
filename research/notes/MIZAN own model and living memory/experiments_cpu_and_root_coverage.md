# Grounding experiments (29 Oct 2026, run in the development sandbox; scripts in the session scratchpad)

These are measurements, not literature. They bound what the designs may assume.

## E1. CPU training and inference throughput of the Ruh architecture (production-like: 2 torch threads)

Script `ruh_cpu_bench.py`; batch 8 × 128 tokens, AdamW, cross-entropy; `torch 2.14.1+cpu`.

| Config | Params | Train tok/s (fwd+bwd+step) | Tokens/day at 25% duty | Days to 20×params tokens at 25% duty | Forward, 64-token context | One more token at ctx 64 (no KV cache) |
|---|---|---|---|---|---|---|
| tiny 128-d × 4 layers | 1.03M | 3,954 | 85M | 0.2 | 7.0 ms | 8.6 ms |
| small 256-d × 6 layers | 5.43M | 1,809 | 39M | 2.8 | 16.4 ms | 16.8 ms |
| mid 384-d × 8 layers | 15.39M | 1,034 | 22M | 13.8 | 35.8 ms | 31.1 ms |
| default 512-d × 8 layers + MoE | 45.99M | 574 | 12M | 74.2 | 86.3 ms | 81.7 ms |

Reading:
- A 5–15M-parameter model can be trained to a Chinchilla-style 20 tokens/parameter budget on the production CPU in days to two weeks of 25%-duty background training. The 46M default needs about 2.5 months; a 100M+ model is out of reach on this hardware.
- Incremental ("real-time") weight updates are affordable at these sizes: one gradient step on 1,024 tokens costs 0.26 s (tiny), 0.57 s (small), 1.0 s (mid), 1.8 s (default).
- Generation without a KV cache costs tens of milliseconds per token even for small models and grows with context; a KV cache is a prerequisite for any interactive use, and byte-level sequences (2 bytes per Arabic/Urdu character) multiply the cost.
- The 2 GB RAM limit is not the binding constraint for ≤50M parameters (≤200 MB for weights + Adam state); compute is.

## E2. Quranic-root coverage of everyday Urdu and Arabic text

Script `root_coverage.py`; the Quranic Arabic Corpus morphology (v0.4, as pinned by `backend/tadbir/sarf.py`) has **1,651 roots** and **14,835 distinct surface forms**. Seed sentences are MIZAN's Lughah corpora (`backend/tadbir/data/lughah/ur.tsv`: 6,882 Urdu tokens / 1,871 types; `ar.tsv`: 4,427 Arabic tokens / 2,462 types; Tatoeba-derived everyday sentences).

| Text | Tokens with a letter Arabic lacks (پ چ ٹ ڈ ڑ ژ گ ں ھ ۓ) → not a Quranic root | Exact Quranic surface form after Urdu→Arabic letter mapping and folding | Rest (needs morphological inference; may or may not be Arabic-origin) |
|---|---|---|---|
| Urdu (ur.tsv) | **36.6%** | **10.5%** | 52.8% |
| Modern Arabic (ar.tsv) | 0% | **43.0%** | 57.0% |

Reading:
- Even in modern Arabic, fewer than half of everyday word tokens are forms the Quran attests; a Quranic-root vocabulary is a proper subset of the language.
- In Urdu, more than a third of tokens are provably outside Arabic (Indo-Aryan/Persian letters), and at most the remaining ~63% could carry an Arabic root; literature estimates for Arabic/Persian-origin vocabulary in Urdu (by type) must be checked against this by the research on root-space interlingua. Roman Urdu / Hinglish was not measured (needs transliteration).
- Consequence for design: a root channel can cover a meaningful minority of Urdu content words and a large share of the religious/abstract vocabulary (ilm, kitab, waqt, hukm, sabr …), but the universal meaning space cannot be the Quranic root inventory itself. Roots are one feature channel; the interlingua must be learned concepts over all languages, with bytes/characters carrying what roots cannot.

## E3. Production baseline of "answers with zero hosted-model calls" — not obtained

Script `zero_model_share.py` would compute, from the owner's own chats via the API and as aggregates only, the share of assistant messages whose `usage.orchestrator == "mizan"` with no `usage.calls`. The saved production credentials no longer authenticate (401 on login), so the number was not measured. The code audit (`audit_base_model_dependence.md` §3) shows nothing in MIZAN records this share today; it is the first metric the roadmap must add (`usage.lisan` field, persisted `orchestration.language_model_calls`, a daily series).
