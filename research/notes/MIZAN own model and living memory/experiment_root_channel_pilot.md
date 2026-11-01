# Experiment E4 (30 Oct 2026): does a Quranic-root channel help a tiny byte-level model at MIZAN's scale?

This answers the critic's gap 1 empirically rather than from literature. Script: `root_channel_pilot.py` (session scratchpad). Development sandbox CPU, 3 torch threads.

## Setup

- **Data:** MIZAN's Lughah seed corpora (Tatoeba-derived everyday sentences in Urdu, Arabic, Hindi, English, Roman Urdu). 256,551 training bytes, 25,646 held-out bytes (split by sentence hash). 30.3% of training bytes are Arabic-script; 15.9% of training bytes sit inside a word for which the Sarf analyzer (Quranic Arabic Corpus, 1,651 roots) returns a root. The Quran and hadith are not training text.
- **Model:** a 4-layer, 128-wide GPT over UTF-8 bytes (≈0.86M parameters without the channel), context 256, batch 16, AdamW, one-cycle LR, same seed and batch order for every variant.
- **Channel:** an embedding (2,048 ids × 128) added to the byte embedding at every byte, keyed by the id of the word the byte sits in (0 outside Arabic-script words and for words without a root).
- **Metric:** held-out bits per byte (bpb), overall and on Arabic-script bytes.

## Run 1 (800 steps = 3.28M tokens, ≈3 min per variant)

| Variant | Params | Held-out bpb, all | Arabic-script bytes | Other bytes |
|---|---|---|---|---|
| bytes only | 0.86M | 2.773 | 2.439 | 2.921 |
| bytes + **real root ids** | 1.12M | 2.746 | **2.322** | 2.934 |
| bytes + root ids under a fixed random **permutation** | 1.12M | 2.743 | 2.309 | 2.935 |

Reading of run 1:
- A per-word channel lowers Arabic-script bpb by about 0.12 bits (≈5%) at this scale; the cost on other bytes is nil.
- The "permutation" control was **uninformative by construction**: a learned embedding is invariant to a consistent relabeling of ids, so the permuted variant still groups exactly the words that share a root. Its equality with the real-root variant says nothing about meaning. The control that does test meaning is a channel keyed by **word form** (a consistent id per distinct word, no grouping of forms that share a root) — run 2.
- Throughput: ≈18k tokens/s training on 3 threads for this 1M-parameter model (the 2-thread production figure for a 1M Ruh config was 4k tokens/s; the plain GPT here is leaner than Ruh's MoE blocks).

## Run 2 (1,000 steps, corrected control)

Variants: bytes only · bytes + real root ids · bytes + a random id per word form (same id range and parameters, no root grouping). An extra metric: bpb on held-out bytes inside **word forms never seen in training** — the case where a root shared with seen forms could inform the model and a per-form id cannot (its embedding is untrained).

Results (`root_channel_pilot_v2.json`; 1,000 steps = 4.1M tokens; held-out bytes inside unseen word forms: 3,328):

| Variant | Params | Held-out bpb, all | Arabic-script bytes | Other bytes | **Bytes in word forms unseen in training** |
|---|---|---|---|---|---|
| bytes only | 0.86M | 2.789 | 2.426 | 2.934 | 2.588 |
| bytes + **real root ids** | 1.12M | 2.757 | 2.285 | 2.945 | **2.553** |
| bytes + random id per **word form** (control) | 1.12M | 2.718 | **2.175** | 2.934 | 2.716 |

Reading of run 2:
- On word forms the model has seen, a per-form identity channel beats the root channel (2.175 vs 2.285 bpb): an id that names the exact form is more specific than one shared by all forms of a root. That is memorisation of forms.
- On word forms **never seen in training** the order flips: real roots 2.553 < bytes only 2.588 < per-form ids 2.716. The root channel carries information that transfers from seen forms to unseen ones (they share a root the model has learned about), while the per-form channel hands the model an untrained embedding and makes it *worse than having no channel*. This is the signature of structure that generalises, which is what "the root carries meaning" has to mean operationally.
- The size of the effect is modest at this scale (−0.035 bit/byte against bytes only, −0.16 against the word-id control, on 3,328 bytes, one seed); run 3 adds a second seed and a variant with both channels (root + word form) to see whether roots add on top of identity.
- Learning-curve shape: the root variant's unseen-form bpb still improves at step 1,000 (2.6036 → 2.5529 → 2.5528) while the word-id control's plateaus from step 600 (2.728 → 2.721 → 2.716).

## Run 3 (seed 1, data order changed with the seed; 1,000 steps)

Bytes and roots ran first (`root_channel_pilot_v3_seed1_bytes_roots.json`); the word-form control and the two-channel variant were rerun on 30 Oct after the CPU freed (`root_channel_pilot_v3_seed1.json`, log `pilot_seed1_rest.log`).

| Variant | Held-out bpb, all | Arabic-script bytes | Other bytes | Bytes in unseen word forms |
|---|---|---|---|---|
| bytes only | 2.776 | 2.423 | 2.917 | 2.583 |
| bytes + real root ids | 2.762 | 2.274 | 2.956 | **2.543** |
| bytes + random id per word form (control) | 2.724 | 2.186 | 2.939 | 2.704 |
| bytes + root ids + word-form ids (both) | **2.700** | **2.063** | 2.953 | 2.653 |

Across the two seeds the pattern replicates exactly: on seen forms a per-form identity channel beats roots (Arabic-script 2.175/2.186 vs 2.285/2.274), on unseen forms roots beat bytes (−0.035/−0.040) and the identity channel is worse than no channel (+0.128/+0.121). The two-channel variant is best on seen Arabic-script bytes (2.063: roots add 0.12 bit on top of identity) but on unseen forms it sits between (2.653), so an untrained per-form embedding still drags where generalisation is needed. A production design that wants both would have to zero the identity channel for forms it has not seen often enough, which is what an embedding with a count threshold (or a hashed-n-gram fallback) does.

## Run 4: matched-parameter arms at 3.79M parameters and 12M tokens

The decisive version of this question ran in the Ruh pilot note (KQ-B1, corrected features, 30 Oct). At a fixed parameter budget root/pattern tables cost more feed-forward width than they repay (pooled +0.004 bpb vs bytes only); the gain is confined to Urdu rooted bytes (−0.040) and is nil on Arabic rooted bytes, whose letters already spell the root. A proxy concept table of strings shared by the Urdu and Arabic text gave the only effect beyond the Hindi negative control (Urdu −0.013 bpb). See `ruh_pilot_root_channel_and_feasibility.md`.

## What this bounds (so far)

- At ≈1M parameters and ≈4M training tokens on CPU, a word-level side channel over Arabic script is worth ≈0.1–0.25 bit/byte on seen forms, and the **root grouping is the part that generalises to unseen forms** (run 2). The root channel is cheap (0.26M parameters, no latency to speak of), does not hurt, and shows a small, directionally consistent transfer benefit; at matched parameters and 12M tokens (run 4) the tables do not repay the width they take, so the effect is real but too local to justify slots in Ruh's LM at this scale.
- Design consequence either way: roots should be a **side channel** added to a byte/character model (as the Ruh audit also recommends), never the vocabulary; the universal meaning space has to be learned (lexicon induction with the teacher once, plus cross-lingual alignment), with roots as one of its features.
