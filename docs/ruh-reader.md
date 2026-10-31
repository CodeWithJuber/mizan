# Ruh reader: MIZAN's own language model, as a second opinion on the language

"And of His signs is the creation of the heavens and the earth and the diversity of your languages and your colors" ([30:22](https://quran.com/30:22)); "And We did not send any messenger except [speaking] in the language of his people to state clearly for them" ([14:4](https://quran.com/14:4)); "if there comes to you a disobedient one with information, investigate" ([49:6](https://quran.com/49:6), Saheeh International).

Lughah (`tadbir/lughah.py`, [Fahm](fahm.md)) decides which language a message is written in by counting letter n-grams with naive Bayes. The Ruh reader (`backend/tadbir/ruh_reader/`) is the first slice of MIZAN's own small transformer: a byte-level language model that learns how each language goes on from one letter to the next, and gives a second reading of the same words. Its word is taken only once it has been measured against Lughah on messages neither has seen, and so far it has not earned that (see **Measured**): it runs in shadow, computed and logged, and never changes the decision.

## The model

`tadbir/ruh_reader/net.py` (torch; imported only to train or score, so nothing at MIZAN's import time needs torch):

- **Tokens:** the 256 byte values, an end-of-message token, and 16 language tokens (the five shipped languages and room for languages Ta'lim adds).
- **Architecture:** pre-norm blocks with RMSNorm, rotary positions (RoPE) on queries and keys, SwiGLU feed-forward, causal attention, output layer tied to the token embedding. Default size: d = 256, 4 layers, 4 heads, feed-forward 768, context 192 bytes, **3,480,064 parameters**.
- **Input:** the message's own words as Lughah reads them: letters and marks, lower case, with names and quoted Quran set aside (`lughah.own_words`). The language token comes first.
- **Score:** `log P(x | l) = Σ_t log p(x_t | l, x_<t)` over the message's bytes, for every language, as rows of one batched forward pass. The model is trained to end a line, but the end is not scored: a message may be cut short, and where a training sentence ends says more about the corpus than about the language.
- **Decoding:** each layer's keys and values are kept (KV cache), so a further byte costs one position (`net.generate`; checked equal to a full forward pass in the tests).
- **int8:** `torch.ao.quantization.quantize_dynamic` on every linear layer (`net.quantized`).

## The mathematics

**The reader's posterior.** Bayes with a uniform prior would be P(l | x) ∝ P(x | l). A language model's likelihoods are not calibrated: their differences grow with the length of the message and with how sure an overfitted model is. As Tamyiz does for naive Bayes, the evidence is scaled and divided by a power of the length:

```
P_R(l | x) ∝ exp( min(1, κ · (n / ñ)^(−γ)) · log P(x | l) )
```

n is the message's length in bytes and ñ the training lines' median. γ = 0, κ = 1 is plain Bayes; γ = 1 weighs every message as one median line's worth. κ ∈ (0, 1] and γ ∈ [0, 1] minimise the log-loss on the development groups (coordinate descent with golden-section searches, the ends of each range candidates too, as `core/tamyiz.py` fits its weights). The exponent is never above 1. On messages the reader never gets wrong, the log-loss keeps falling as the exponent grows, and a first fit without the cap chose κ = 50 and then lost 4.87 nats per held-out message on the three it got wrong.

**Product of experts.** Lughah's posterior and the reader's are multiplied, the reader's raised to one weight:

```
P(l | x) ∝ P_L(l | x) · P_R(l | x)^b,     0 ≤ b ≤ 1
```

b is fitted on the development groups by golden-section search, as Iqtibas fits its factor. b = 0 when the reader does not lower the development log-loss, and b = 0 is a factor of 1 for every language. b = 1 would count the reader as evidence independent of Lughah's; both read the same words, so it is worth at most that.

**Held out, never trained on.** Each seed's group is the SHA-256 of its words as read (so "Hello, World!" and "hello world" are one group). One group in five, by that hash, is held out for good. One in eight of the rest is the development set, which picks the checkpoint and fits κ, γ and b. The reader trains on what is left. For the comparison Lughah is refitted (α, weights and γ by its own leave-one-out) on the training groups and the neutral classes only, so both models are judged on words neither has seen. Seeds after the split: 3,310 training, 452 development, 954 held out.

**Short messages.** Whole seed sentences are easy: Lughah, held out, reads all 954 right. People write a few words. Each development and held-out message is therefore also read as its first 2 and first 3 words (when it is longer), in the same group, so the fit and the gate see the lengths people send: 2,756 held-out readings in 954 groups.

**The gate.** The reader's factor is used only when, on the held-out groups, the product beats Lughah alone on both counts:

- **Log-loss:** a paired bootstrap that resamples whole groups (2,000 resamples) gives P(mean difference ≥ 0) below α = 0.05.
- **Accuracy:** a group is a win when the product is right on more of its readings than Lughah, a loss when on fewer. The paired e-value over wins and losses (`core.adaptive.paired_e_value`) must reach k(k+1)/α for the k-th test of this reader: 40 for the first. Every test ever run then spends at most α together (Ville's inequality).

A reader that fails the gate, is missing, was trained on another corpus (the seeds' SHA-256 differs, for example after a Ta'lim batch), or does not know one of Lughah's languages changes nothing.

## Scripture is never a training target

A line is not trained on when any of these holds (`ruh_reader.scripture`):

- Lughah reads a piece of it as quoted Quran (its `quote` class, the vowelled Uthmani text);
- it shares 4 consecutive words (Muhasaba's `LEAST_SHARED`) with the Uthmani sample in Lughah's seeds, folded as the Truth Gate reads Arabic across scripts;
- once Iqtibas has the Quran's texts in memory: the mushaf holds a run of 4 of its words, or a span of at least 4 words is more likely a quote than ordinary speech (Iqtibas's evidence above 0).

Of the 4,716 seeds in the five languages, 5 were set aside: "اذْكُر رَّبَّكَ إِذَا نَسِيتَ" (18:24) and four other fully vowelled Arabic sentences that Lughah reads as Uthmani. That is a cautious mistake, not a leak. The test `test_no_quranic_span_reaches_the_loss` records every target byte that reaches the loss while training with three Quranic lines in the training split, and checks that no run of three of the ayah's words is among them. A night's text goes through the same check.

`build` now reads the Quran's texts before it filters, when Iqtibas is on and Fihris's editions are on disk (`$MIZAN_DATA_DIR/quran`), so the third check applies to the seeds too. It is much more cautious: 46 of the 3,310 training seeds are set aside, most of them ordinary sentences whose four-word span a translation also says ("I have come to the village.", "وہ اس ملک میں آتی جاتی رہتی ہے۔"). The manifest records which check ran (`scripture_mushaf`).

## Its own corpus

Lughah's seeds stay Lughah's. The reader may also learn from text that is not theirs (`tadbir/ruh_reader/corpus.py`; sources, licences and notices in `backend/tadbir/ruh_reader/LICENSES.md`), built at train time into `$MIZAN_DATA_DIR/corpora/ruh_reader/` and never committed:

| Source | Licence | Pinned | Used for |
|---|---|---|---|
| Tatoeba per-language exports (eng, hin, urd, ara); every sentence id the seeds use left out | CC BY 2.0 FR | no (weekly exports; SHA-256 recorded) | training |
| MASSIVE 1.1 (Amazon; localised from SLURP), en-US, hi-IN, ur-PK, ar-SA | CC BY 4.0 | SHA-256 | `train` partition: training; `test` partition, 3–8 words: held out |
| Abhishekcr448/Hinglish-Everyday-Conversations-1M (synthetic, written by GPT-4o-mini per its card) | MIT | commit + SHA-256 | training; held-out rows: held out |

A line is kept for training only when (in this order, each counted in the manifest): more than half of its letters are in its language's script (MASSIVE's ar-SA has utterances written in English only); it has 3 letters or more and at most 192 bytes of words; it is not a seed by its Tatoeba id; its words as read (`group_of`) are no seed's in any split, so nothing in Lughah's held-out or development groups is trained on; it is not a held-out short message; it is the first of its group; and it is not scripture, with Iqtibas's texts in memory (the build refuses to write a corpus without them). Lines are taken in an order fixed by SHA-256 of their source id, round robin over a language's sources, until the language holds 900,000 bytes of words: the training time, not the data, is the bound, so each language gets the same share. `build` checks the corpus again (dev and held-out seed groups, held-out short messages, the first two scripture checks) and records its SHA-256 and sources in the reader's manifest.

**The held-out short messages** are a slice neither model has seen: MASSIVE test utterances of 3 to 8 words in en, hi, ur and ar (real request style, written for a voice assistant and localised by translators; one MASSIVE id is one group in the paired test, since its translations are one request), and 2,000 Roman Hindi/Urdu utterances of 3 to 8 words whose group the seeds' rule holds out (`part(group) == "held_out"`), none a seed's words. The Roman part is synthetic: it tests the style of that dataset, not what people type. The slice is read and reported beside the seeds' held-out groups, with Lughah as it ships (fitted on every seed) as a further arm; **the gate stays the seeds' held-out groups.**

## Measured

Two versions were measured on 30 Oct 2026: **v0**, trained on Lughah's seeds only (this section), and **v1**, trained on its own corpus as well ([v1](#v1-its-own-corpus) below). Both were refused by the gate and run in shadow.

### v0: the seeds only

Run on 30 Oct 2026 in the development sandbox: Intel Xeon 2.8 GHz, 4 vCPU shared with other jobs (load average 2–6), torch 2.14.1+cpu. Each seed trained on 2 torch threads, the two seeds at the same time. `python ../scripts/ruh_reader_eval.py --seeds N`, default size and plan: 3,480,064 parameters, 12 passes over the training lines (1,248 steps of 32 lines, 2,267,412 tokens), **851 s and 847 s of training**, about 16 minutes each with Lughah's refit and the evaluation. The development bits per byte were still falling at the last pass (1.829 and 1.819), so the run was bounded by its budget, not by overfitting.

**Held-out bits per byte**, whole messages, seed 0 / seed 1: Hindi 1.151 / 1.161 · Urdu 1.723 / 1.728 · Arabic 1.979 / 1.981 · Roman Hindi/Urdu 2.121 / 2.098 · English 2.539 / 2.524. The pilot's byte model had 12M tokens of web text and reached 1.21 / 1.61 / 1.70 / 2.01 / 2.41 on its own held-out text.

**Language identification on held-out groups.** Each cell is accuracy in % [95% Wilson interval] · mean log-loss in nats. Lughah alone is its held-out refit; it does not depend on the reader's seed.

| Slice | n | Lughah alone | Reader alone, seed 0 | seed 1 | Product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| all readings | 2,756 | 99.38 [99.01, 99.61] · 0.0237 | 98.69 [98.20, 99.05] · 0.0445 | 98.91 [98.45, 99.24] · 0.0394 | 99.20 [98.79, 99.47] · 0.0200 | 99.42 [99.06, 99.64] · 0.0165 |
| whole messages | 954 | 100.00 [99.60, 100.00] · 0.0062 | 99.58 [98.93, 99.84] · 0.0151 | 99.90 [99.41, 99.98] · 0.0078 | 99.79 [99.24, 99.94] · 0.0036 | 100.00 [99.60, 100.00] · 0.0007 |
| first 3 words | 864 | 99.31 [98.49, 99.68] · 0.0231 | 98.73 [97.73, 99.29] · 0.0433 | 98.96 [98.03, 99.45] · 0.0431 | 99.31 [98.49, 99.68] · 0.0180 | 99.65 [98.98, 99.88] · 0.0138 |
| first 2 words | 938 | 98.83 [97.91, 99.34] · 0.0420 | 97.76 [96.60, 98.53] · 0.0756 | 97.87 [96.73, 98.62] · 0.0682 | 98.51 [97.51, 99.11] · 0.0386 | 98.61 [97.64, 99.19] · 0.0350 |
| < 40 bytes | 2,060 | 99.17 [98.68, 99.48] · 0.0308 | 98.35 [97.70, 98.82] · 0.0560 | 98.59 [97.99, 99.02] · 0.0500 | 98.98 [98.45, 99.33] · 0.0261 | 99.22 [98.74, 99.52] · 0.0218 |
| Latin script (en, hi-latn) | 1,151 | 98.78 [97.97, 99.27] · 0.0481 | 97.48 [96.40, 98.24] · 0.0771 | 98.00 [97.02, 98.66] · 0.0709 | 98.35 [97.44, 98.94] · 0.0424 | 98.87 [98.08, 99.34] · 0.0316 |
| Roman Hindi/Urdu | 584 | 98.12 [96.66, 98.95] · 0.0548 | 98.46 [97.10, 99.19] · 0.0434 | 99.14 [98.01, 99.63] · 0.0208 | 98.12 [96.66, 98.95] · 0.0378 | 98.63 [97.32, 99.30] · 0.0245 |
| Roman Hindi/Urdu < 40 bytes | 425 | 97.41 [95.43, 98.55] · 0.0747 | 97.88 [96.02, 98.88] · 0.0596 | 98.82 [97.28, 99.50] · 0.0284 | 97.41 [95.43, 98.55] · 0.0520 | 98.12 [96.33, 99.04] · 0.0337 |
| Arabic script (ar, ur) | 1,110 | 99.82 [99.35, 99.95] · 0.0067 | 99.64 [99.08, 99.86] · 0.0139 | 99.64 [99.08, 99.86] · 0.0104 | 99.82 [99.35, 99.95] · 0.0046 | 99.91 [99.49, 99.98] · 0.0037 |
| Urdu | 622 | 99.84 [99.09, 99.97] · 0.0061 | 99.52 [98.59, 99.84] · 0.0194 | 99.52 [98.59, 99.84] · 0.0124 | 99.84 [99.09, 99.97] · 0.0032 | 100.00 [99.39, 100.00] · 0.0017 |

**Fit** (on the development groups): seed 0 κ = 0.703, γ = 0.958, b = 0.552; seed 1 κ = 0.711, γ = 0.873, b = 0.440. ñ = 51 bytes.

**The gate refused both seeds:**

| Seed | log-loss, Lughah → product | P(not better) | wins / losses (groups) | e-value (needed) | accuracy, Lughah → product | adopted |
|---|---|---|---|---|---|---|
| 0 | 0.0237 → 0.0200 | 0.141 | 3 / 4 | 0.33 (40) | 99.38% → 99.20% | no |
| 1 | 0.0237 → 0.0165 | 0.018 | 4 / 3 | 0.58 (40) | 99.38% → 99.42% | no |

**Latency** of reading one 100-byte message under all five languages (one batched pass, 2 threads, median of 30–60 runs on the shared machine): fp32 38–50 ms, int8 34–47 ms. The int8 model makes the same decision on 99.67% / 99.82% of held-out readings, with product accuracy 99.27% / 99.46%. At this size int8 buys no reliable speed, as the pilot found at 5M parameters: the cost is per operation, not per weight. MIZAN therefore reads with the fp32 weights. Loaded in a server-like process, the reader took 1.8 s to load (torch import and weights) and raised the peak resident memory from 136 MB to 272 MB. Reading ordinary chat messages of 7–30 bytes in shadow took 12–26 ms each.

**Exploration before the final runs** (one seed each, the end token scored, which the final runs do not): 1,823,616 parameters, product 99.27% · 0.0298 (worse than Lughah's 0.0237; wins 4, losses 6); 3,480,064 parameters, product 99.31% · 0.0193 (P(not better) 0.0055; wins 1, losses 2). A first run with κ and b uncapped fitted κ = 50 and b = 4 and lost 4.87 nats per held-out reading; that is why both are capped (see the mathematics).

**What this says.**
- The reader alone is a weaker language identifier than Lughah's naive Bayes overall (98.7–98.9% against 99.38%). It is stronger only on Roman Hindi/Urdu (98.5–99.1% against 98.1%; on short Roman messages 97.9–98.8% against 97.4%). More than half of its mistakes are on English (96.5% and 96.8% of English readings right).
- The product's probabilities are better calibrated than Lughah's in both seeds: held-out log-loss falls 15% and 30%. Only seed 1's fall is beyond chance (P(not better) 0.018), and its decisions are not better: 3–4 groups won and 3–4 lost, far from the e-value of 40 the gate needs. Lughah is wrong on only 17 of the 2,756 readings, so a gain the gate can see would need most of them fixed and almost none broken.
- So the reader ships in **shadow**: it is computed and logged beside Lughah, and Lughah's decision stands. Turning it `on` changes nothing until a version passes the gate.
- The next levers are data and length, not architecture. Roman Hindi/Urdu is where it already helps, and more licence-clean Hinglish (the MIT dataset the seeds sample has 1M rows) and Tatoeba sentences would let it train past 12 passes over 200 KB. A held-out set of real short messages would test it where Lughah is weakest.

### v1: its own corpus

Same model and gate, trained on the seeds and its own corpus (82,577 lines: 3,264 seed lines, 46 seeds set aside as scripture, and 79,313 corpus lines; 4,391,270 bytes; ar 19,869, en 24,869, hi 11,361, hi-latn 10,445, ur 12,769 lines). One pass (2,581 steps of 32 lines, 4,656,299 tokens) in 1,540 s and 1,547 s on 2 threads per seed, the two seeds at once beside two other jobs. Development bits per byte 1.715 and 1.709, against v0's 1.829 and 1.819; they were still falling at the end of the pass. The weights of each seed are kept the moment training ends (`build(trained=…)`, `keep_trained`), so a restart repeats only the reading.

**Held-out bits per byte**, seeds' held-out groups / real short messages, seed 0: Hindi 1.136 / 1.142 · Urdu 1.732 / 1.447 · Arabic 1.832 / 1.639 · Roman Hindi/Urdu 1.984 / 2.237 · English 2.226 / 2.005 (v0 on the short messages: 1.413 · 1.978 · 2.150 · 2.366 · 2.965).

**The seeds' held-out groups** (the gate's set; Lughah alone is its held-out refit):

| Slice | n | Lughah alone | Reader alone, seed 0 | seed 1 | Product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| all readings | 2,756 | 99.38 [99.01, 99.61] · 0.0237 | 99.35 [98.97, 99.59] · 0.0269 | 99.27 [98.88, 99.53] · 0.0269 | 99.53 [99.19, 99.72] · 0.0203 | 99.49 [99.15, 99.70] · 0.0184 |
| whole messages | 954 | 100.00 [99.60, 100.00] · 0.0062 | 99.90 [99.41, 99.98] · 0.0082 | 99.79 [99.24, 99.94] · 0.0090 | 99.90 [99.41, 99.98] · 0.0049 | 99.90 [99.41, 99.98] · 0.0028 |
| first 2 words | 938 | 98.83 [97.91, 99.34] · 0.0420 | 98.72 [97.78, 99.27] · 0.0498 | 98.83 [97.91, 99.34] · 0.0420 | 99.04 [98.19, 99.49] · 0.0361 | 98.93 [98.05, 99.42] · 0.0330 |
| < 40 bytes | 2,060 | 99.17 [98.68, 99.48] · 0.0308 | 99.13 [98.62, 99.45] · 0.0360 | 99.03 [98.51, 99.37] · 0.0360 | 99.37 [98.92, 99.63] · 0.0271 | 99.32 [98.86, 99.59] · 0.0246 |
| English | 567 | 99.47 [98.46, 99.82] · 0.0412 | 99.12 [97.95, 99.62] · 0.0283 | 97.88 [96.34, 98.79] · 0.0582 | 99.47 [98.46, 99.82] · 0.0197 | 99.29 [98.20, 99.73] · 0.0273 |
| Roman Hindi/Urdu | 584 | 98.12 [96.66, 98.95] · 0.0548 | 98.29 [96.88, 99.07] · 0.0777 | 98.80 [97.55, 99.42] · 0.0586 | 98.46 [97.10, 99.19] · 0.0669 | 98.46 [97.10, 99.19] · 0.0506 |
| Arabic script (ar, ur) | 1,110 | 99.82 [99.35, 99.95] · 0.0067 | 99.73 [99.21, 99.91] · 0.0115 | 99.91 [99.49, 99.98] · 0.0063 | 99.91 [99.49, 99.98] · 0.0051 | 99.91 [99.49, 99.98] · 0.0046 |

**The gate refused both seeds again**, now with the product ahead in accuracy but too few groups changed to reach the bar:

| Seed | log-loss, Lughah → product | P(not better) | wins / losses (groups) | e-value (needed) | accuracy, Lughah → product | adopted |
|---|---|---|---|---|---|---|
| 0 | 0.0237 → 0.0203 | 0.270 | 5 / 2 | 1.30 (40) | 99.38% → 99.53% | no |
| 1 | 0.0237 → 0.0184 | 0.155 | 6 / 3 | 1.01 (40) | 99.38% → 99.49% | no |

**The real short messages** (9,808 held-out MASSIVE test requests of 3–8 words and Roman Hindi/Urdu rows; reported only, the gate stays the seeds' groups):

| Slice | n | Lughah alone | Reader alone, seed 0 | seed 1 | Product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| all short messages | 9,808 | 98.54 [98.29, 98.76] · 0.0549 | 98.94 [98.72, 99.12] · 0.1215 | 98.95 [98.73, 99.13] · 0.1070 | 98.93 [98.71, 99.11] · 0.1175 | 98.92 [98.69, 99.11] · 0.0937 |
| MASSIVE (en, hi, ur, ar) | 7,808 | 99.42 [99.23, 99.57] · 0.0259 | 99.81 [99.68, 99.88] · 0.0064 | 99.72 [99.57, 99.81] · 0.0101 | 99.83 [99.72, 99.90] · 0.0058 | 99.76 [99.62, 99.84] · 0.0071 |
| English | 2,090 | 97.89 [97.19, 98.43] · 0.0921 | 99.33 [98.88, 99.60] · 0.0181 | 99.14 [98.64, 99.45] · 0.0314 | 99.43 [99.00, 99.67] · 0.0160 | 99.14 [98.64, 99.45] · 0.0224 |
| Roman Hindi/Urdu | 2,000 | 95.10 [94.06, 95.96] · 0.1682 | 95.55 [94.56, 96.37] · 0.5710 | 95.95 [94.99, 96.73] · 0.4854 | 95.40 [94.39, 96.23] · 0.5535 | 95.65 [94.67, 96.46] · 0.4321 |
| Hindi / Urdu / Arabic | 5,718 | 100.00 / 99.94 / 100.00 | 100.00 / 99.94 / 100.00 | 100.00 / 99.89 / 99.91 | 100.00 / 99.94 / 100.00 | 100.00 / 99.94 / 100.00 |

On these messages the gate's own paired test on accuracy gives e-values of 6.3·10⁵ and 2.0·10⁵ (wins 46 / losses 8 and 46 / 9 over 4,616 groups), far past 40; against Lughah as shipped, 2.8·10⁴ and 3.0·10⁴. The log-loss, however, is worse (0.055 → 0.118 and 0.094): when the product is wrong it is confidently wrong, nearly all of it on Roman Hindi/Urdu read as English (89–92 of the ~105 mistakes). The v0 reader, trained on the seeds only, lost on the same messages (wins 29–30, losses 34–45). Mistakes on the short messages, seed 0: Lughah 98 Roman read as English and 44 English read as Roman; the product 92 and 12.

**Cost.** fp32 reading of one message under all five languages, 2 threads: 20–22 ms (100 bytes), 6.7 ms (24 bytes); int8 14–15 ms with 99.85% / 99.93% of decisions the same. The evaluation process peaked at 2.1 GB resident (it holds every slice's readings); serving loads only the weights.

**What v1 says.**
- More of the right data helped where it was missing: English on real requests 97.9% (Lughah) → 99.1–99.3% (reader), and the product is ahead of Lughah on the seeds' held-out groups too. Part of the English gain is that MASSIVE's train partition is the same kind of text as its test partition; Lughah has seen no MASSIVE text.
- The gate still refuses: on the seeds' held-out groups Lughah is wrong only 17 times in 2,756, so too few groups can change, and on the real short messages the reader's confidence on Roman Hindi/Urdu is badly calibrated (κ and b are fitted on the seeds' development groups, not on such messages).
- The gate was not moved to the short messages after seeing them. The next test, decided before it is run: fit κ and b on MASSIVE's **validation** partition and held-out Roman Hindi/Urdu development rows, and gate on short messages the reader has never been measured on (MASSIVE validation rows not used for the fit, and fresh Roman rows), with the same two conditions.
- The reader stays in **shadow**.

### v1.1: calibrated on real short messages

The test v1 wrote down, run on v1's weights (no new training). The protocol below was fixed on 31 Oct 2026 before any of its numbers were computed.

**Slices.** MASSIVE 1.1's `dev` partition (its validation set; the corpus build never trains on it) in en-US, hi-IN, ur-PK and ar-SA: utterances of 3–8 words, more than half of their letters in their language's script, whose words as read are no line of Lughah's corpus, no line the reader trained on and no message of v1's short slice, once per language and words. One MASSIVE id is one group, and lies in one half: the **calibration** half when the SHA-256 of `ruh-reader-v1.1:massive:<id>` is even, else the **gate** half. Roman Hindi/Urdu: Hinglish-1M utterances v1's build never read (outside the quarter it read, in its order), 3–8 words, Latin script, a group the seeds' rule holds out, words no seed's, no training line's and no v1 short message's; a conversation's two utterances lie in one half (`ruh-reader-v1.1:hinglish-1m:<row>`), and each half takes as many as the mean per-language count of its MASSIVE rows, so Roman Hindi/Urdu weighs as one language of five, as in v1's slice. The Roman rows are synthetic, as v1's were. `corpus.build_validation` writes them to `validation.tsv` with their SHA-256 in `validation.json`.

**Calibration** (the calibration half only). γ stays at each seed's development fit and ñ at 49 bytes. κ ∈ (0, 1] is `fit_reader`'s κ step with γ held, on the reader's own log-loss; then b ∈ [0, 1] by `fit_b` unchanged, on the product's log-loss with the held-out Lughah. Nothing else is fitted.

**The gate** (the gate half only, MASSIVE and Roman together): `ruh_reader.gate` as it is, both conditions (grouped paired bootstrap on log-loss, P(not better) < 0.05; paired e-value on accuracy), as the **second** test of these weights: v1's gate was the first, so the e-value needed is k(k+1)/α = 2·3/0.05 = **120**. Each seed is judged on its own. A pass does not change the default (`shadow`); the owner decides.

**Reported, never deciding:** the gate half by part and per language with every arm (Lughah as shipped too), the calibration half (in sample), the gate half under v1's development fit, the seeds' held-out groups and v1's 9,808 short messages under the new fit, latency and peak memory.

*Results: not yet computed.*

## Learning while MIZAN rests

Nawm (`tadbir/nawm.py`, [automatic learning](automatic-learning.md#nawm-what-was-learned-is-replayed-while-mizan-rests)) calls `ruh_reader.rest` for each person once a day, while no request runs:

1. **Consent.** Nothing happens unless the reader is not `off`, its weights exist, and the person's choices bound for the night say `learning` is on and `training: on` (`stateless.learns()` and `stateless.trains()`; never in an evaluation or a WhatsApp run, `barred_from_training()`). See [Consent](consent.md).
2. **Verified words only.** The person's messages captured as training candidates (only under `training: on`) that a named reviewer accepted, with the review hash still matching the content (`reviewed_words`, the learner store). A message holding the Quran's words is never learned, nor one already learned.
3. **Labels.** A message is learned under the language Lughah and the reader both read it in. Where they disagree it is not learned, because a label the two contest is not verified.
4. **Training.** The current weights continue training within the night's time (about 60% of what is left), 3 passes at most at a learning rate of 5·10⁻⁴. A quarter of every batch is replayed from the seeds' training groups: in the pilot (`research_notes`, 3.8M parameters, three sequential languages), 25% replay held the earlier languages with no forgetting, where EWC alone did not.
5. **Promotion.** The new version replaces the current one only when, on the held-out seeds, its log-loss is not higher and Ta'lim's paired bootstrap does not find it less accurate (P(worse) < 0.95, `no_worse`). The current one is kept as `previous` for `rollback()`. The gate is then run again as the next test (needing k(k+1)/α), and decides whether `on` may use the new version.
6. **Forgetting.** Each version records the SHA-256 of every message it learned, and no words. Erasing a chat (Mahw) drops every version that learned from its messages, and the newest version that did not becomes current. The seed-only `base` version is never dropped.

## Settings and files

- `MIZAN_RUH_READER` (Settings → Developer → System settings, Model group):
  - `shadow` (default): the reader is computed beside Lughah, disagreements are logged (`mizan.ruh_reader`), counts are kept in `ruh_reader.status()["shadow"]`, and the decision is Lughah's.
  - `on`: the product is used once the gate passed.
  - `off`: the reader is never loaded.
- **Weights:** `$MIZAN_DATA_DIR/models/ruh_reader/`. `current`, `previous` and `base`, each `.pt` (fp32 weights), `.json` (corpus SHA-256, config, fit, gate, learned digests) and `.reads.json` (the development and held-out messages as held-out Lughah read them, so a night re-scores only the reader).
- **Corpus:** `cd backend && python -m tadbir.ruh_reader --corpus [--bytes-per-language 900000] [--workers 3]` downloads the sources (about 250 MB, kept in `$MIZAN_DATA_DIR/corpora/ruh_reader/sources/`), fetches the Quran's texts if they are not on disk, and writes `train.tsv`, `short.tsv` and `manifest.json` (4 minutes with 4 workers on the development sandbox). A corpus whose files changed, or that was built against other seeds, is not used.
- **Train and install:** `cd backend && python -m tadbir.ruh_reader --train [--seed N] [--threads 2] [--seeds-only]`. It trains on the corpus when one is built (`--seeds-only` ignores it). Without `--train` it prints the status.
- **Measure:** `cd backend && python ../scripts/ruh_reader_eval.py --seeds 0 1 [--corpus] --json out.json [--install 0] [--save DIR]`; `--evaluate DIR` reads an installed reader (`current.pt`, `current.json`) on the same slices without training.

Without weights nothing is loaded and torch is never imported: the default deployment is unchanged until an operator trains a reader. Once weights exist, shadow mode loads torch into the server process (a few hundred MB of resident memory on the 2 GB production machine) in a background thread. The message in hand is read without the reader until it is loaded.

## Limits

- **Small data.** v0 learned from about 200 KB of seed text (3,305 lines); v1 adds 4.4 MB of its own corpus and is still one pass from its budget. The pilot's byte model had 12M tokens of web text and reached 1.2–2.4 bits per byte. Here the held-out bits per byte are higher (see the table), and Roman Hindi/Urdu (982 seeds) and English are the weakest.
- **Easy test, hard ceiling.** On whole held-out sentences Lughah is already 100% right, so only shorter readings can show a gain. The short readings are cut from whole sentences, which is not the same as messages people actually send.
- **Labels at night come from the models themselves.** A message is learned under the language both read it in. The night can adapt the reader to how people write, but cannot teach it a language Lughah misreads.
- **Memory.** Weights cannot have one message subtracted. Forgetting falls back to an earlier version, which also loses what later nights learned from other messages.
- **Shadow cost.** Reading every message costs CPU (see latency) and torch's memory, for no change in the decision until the gate passes.
