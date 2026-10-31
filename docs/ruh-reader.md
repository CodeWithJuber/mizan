# Ruh reader: MIZAN's own language model, as a second opinion on the language

"And of His signs is the creation of the heavens and the earth and the diversity of your languages and your colors" ([30:22](https://quran.com/30:22)); "And We did not send any messenger except [speaking] in the language of his people to state clearly for them" ([14:4](https://quran.com/14:4)); "if there comes to you a disobedient one with information, investigate" ([49:6](https://quran.com/49:6), Saheeh International).

Lughah (`tadbir/lughah.py`, [Fahm](fahm.md)) decides which language a message is written in by counting letter n-grams with naive Bayes. The Ruh reader (`backend/tadbir/ruh_reader/`) is the first slice of MIZAN's own small transformer: a byte-level language model that learns how each language goes on from one letter to the next, and gives a second reading of the same words. Its word is taken only once it has been measured against Lughah on messages neither has seen. Two tests refused it; the third, on 31 Oct 2026, passed for both seeds. The same day the owner decided it must not learn from text a language model wrote, and **v2**, retrained without it, passed its own first test for both seeds and beat v1 on the same messages (see **Measured**). It still runs in shadow, computed and logged, never changing the decision, until the owner decides to turn it on.

A larger model of the same family, the **Ruh speaker** (about 125M parameters, trained on a GPU), is prepared as a pre-registered pilot and has not been run: [ruh-speaker.md](ruh-speaker.md).

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
| FineWeb-2 `hin_Latn`, `urd_Latn` (web pages; since v2) | ODC-By 1.0 + Common Crawl terms | commit + SHA-256 | training (four documents in five); held-out documents: v2's slices |
| Abhishekcr448/Hinglish-Everyday-Conversations-1M (synthetic, written by GPT-4o-mini per its card) | MIT | commit + SHA-256 | v1: training. **Since v2 never trained on**: measured only (held-out rows) |
| CLINC150 (clinc/oos-eval; crowd-written requests, Larson et al. 2019) | CC BY 3.0 | commit + SHA-256 | never trained on: test 3's English gate rows |
| BANKING77 (PolyAI; customer-service queries) | CC BY 4.0 | commit + SHA-256 | never trained on: v2's English rows |
| PHINC (code-mixed tweets), Dakshina 1.0 (romanized Wikipedia sentences) | CC BY 4.0 (card), CC BY-SA 4.0 | commit + SHA-256; file SHA-256 | measured only: v2's Roman Hindi/Urdu rows |

A line is kept for training only when (in this order, each counted in the manifest): more than half of its letters are in its language's script (MASSIVE's ar-SA has utterances written in English only); it has 3 letters or more and at most 192 bytes of words; it is not a seed by its Tatoeba id; its words as read (`group_of`) are no seed's in any split, so nothing in Lughah's held-out or development groups is trained on; it is not a held-out short message; it is the first of its group; and it is not scripture, with Iqtibas's texts in memory (the build refuses to write a corpus without them). Since v2 also: it is no model-written source's (`corpus.MODEL_WRITTEN`); its words are not those of any message ever measured, nor near them (`--old`, v1's corpus folder, gives the old slices); with `--hadith`, it holds no run of 8 words of the six books (the speaker's rule); and a FineWeb-2 line's document holds no scripture or hadith anywhere. Lines are taken in an order fixed by SHA-256 of their source id (a FineWeb-2 line: its document's, then its place in it), round robin over a language's sources, until the language holds 900,000 bytes of words: the training time, not the data, is the bound, so each language gets the same share. `build` checks the corpus again (dev and held-out seed groups, held-out short messages, the first two scripture checks) and records its SHA-256 and sources in the reader's manifest.

**The held-out short messages** are a slice neither model has seen: MASSIVE test utterances of 3 to 8 words in en, hi, ur and ar (real request style, written for a voice assistant and localised by translators; one MASSIVE id is one group in the paired test, since its translations are one request), and 2,000 Roman Hindi/Urdu utterances of 3 to 8 words whose group the seeds' rule holds out (`part(group) == "held_out"`), none a seed's words. The Roman part is synthetic: it tests the style of that dataset, not what people type. Since v2 Hinglish-1M is downloaded only for this part (and v1.1's and test 3's slices): v2's `short.tsv` is v1's, byte for byte. The slice is read and reported beside the seeds' held-out groups, with Lughah as it ships (fitted on every seed) as a further arm; **the gate stays the seeds' held-out groups.**

## Measured

Two versions were measured on 30 Oct 2026: **v0**, trained on Lughah's seeds only (this section), and **v1**, trained on its own corpus as well ([v1](#v1-its-own-corpus) below). Both were refused by the gate and run in shadow. On 31 Oct, **v1.1** recalibrated v1's weights on real short messages and gated them on others ([v1.1](#v11-calibrated-on-real-short-messages)). It was refused too. **Test 3** recalibrated them once more with the Roman rows Qāmūs reads Hindi or Urdu in, and gated them on fresh CLINC150 English requests and never-read Roman rows ([test 3](#test-3-roman-labels-checked-by-qāmūs-gated-on-fresh-messages)): both seeds passed. **v2** is a new reader trained without Hinglish-1M (written by GPT-4o-mini) and with Roman Hindi/Urdu web text people wrote; gated on fresh messages people wrote, it passed for both seeds ([v2](#v2-without-model-written-text)). The default stays shadow; the owner decides.

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

**The slices** (`validation.tsv`, SHA-256 `ac9423b0…5f29`, fixed and checked before anything was scored: no group in both halves, no message's words a seed's, a training line's or a v1 short message's):

| Half | messages | groups | en | hi | ur | ar | Roman Hindi/Urdu |
|---|---|---|---|---|---|---|---|
| calibration | 3,220 | 1,525 | 699 | 598 | 561 | 718 | 644 |
| gate | 3,184 | 1,513 | 709 | 600 | 562 | 676 | 637 |

Both seeds' kept weights matched their key, so nothing was retrained: these are v1's readers.

**Calibration.** Both seeds' development fits had γ = 0, so κ acts as a temperature on the reader's likelihoods.

| Seed | κ, development → calibrated | b, development → calibrated |
|---|---|---|
| 0 | 0.945 → 0.229 | 0.723 → 0.082 |
| 1 | 1.000 → 0.332 | 0.604 → 0.074 |

**The gate refused both seeds.** The log-loss condition held; the accuracy condition did not.

| Seed | log-loss, Lughah → product | P(not better) | wins / losses (groups) | e-value (needed) | accuracy, Lughah → product | adopted |
|---|---|---|---|---|---|---|
| 0 | 0.0545 → 0.0527 | 0.004 | 2 / 0 | 2.33 (120) | 98.59% → 98.65% | no |
| 1 | 0.0545 → 0.0525 | 0.0035 | 2 / 0 | 2.33 (120) | 98.59% → 98.65% | no |

With no losses, 10 won groups would have reached 120. Calibrated, the product changes too few decisions to get there.

**The gate half** (accuracy in % [95% Wilson interval] · mean log-loss; Lughah alone is the held-out refit):

| Slice | n | Lughah alone | Reader alone, seed 0 | seed 1 | Product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| gate half | 3,184 | 98.59 [98.11, 98.94] · 0.0545 | 98.96 [98.55, 99.26] · 0.0527 | 98.87 [98.44, 99.18] · 0.0574 | 98.65 [98.19, 99.00] · 0.0527 | 98.65 [98.19, 99.00] · 0.0525 |
| MASSIVE (en, hi, ur, ar) | 2,547 | 99.45 [99.08, 99.67] · 0.0240 | 99.76 [99.49, 99.89] · 0.0244 | 99.69 [99.38, 99.84] · 0.0252 | 99.53 [99.18, 99.73] · 0.0199 | 99.53 [99.18, 99.73] · 0.0195 |
| English | 709 | 98.03 [96.71, 98.82] · 0.0835 | 99.29 [98.36, 99.70] · 0.0792 | 99.01 [97.98, 99.52] · 0.0497 | 98.31 [97.07, 99.03] · 0.0697 | 98.31 [97.07, 99.03] · 0.0683 |
| Roman Hindi/Urdu | 637 | 95.13 [93.18, 96.55] · 0.1764 | 95.76 [93.90, 97.07] · 0.1657 | 95.60 [93.72, 96.94] · 0.1862 | 95.13 [93.18, 96.55] · 0.1841 | 95.13 [93.18, 96.55] · 0.1846 |
| Hindi / Urdu / Arabic | 600 / 562 / 676 | 100 / 100 / 100 | 100 / 99.82 / 100 | 99.83 / 100 / 100 | 100 / 100 / 100 | 100 / 100 / 100 |

Lughah as shipped reads the gate half 98.81% [98.37, 99.13] · 0.0496, and shipped × reader 98.87% · 0.0483 / 0.0484 (wins 2, losses 0 for both seeds). Bits per byte on the gate half, seed 0 / seed 1: Hindi 1.154 / 1.158 · Urdu 1.463 / 1.485 · Arabic 1.643 / 1.678 · English 2.015 / 1.994 · Roman Hindi/Urdu 2.227 / 2.216. Mistakes: Lughah reads 31 Roman messages as English and 14 English as Roman; the calibrated product 31 and 12 (both seeds).

**What the calibration changed** (the gate half again, reported only). Under v1's development fit the product is right on 98.99% (wins 13, losses 0, e-value 1,170), but its log-loss is 0.120 / 0.099 (P(not better) 1.0 / 0.9995). Calibrated, the log-loss falls below Lughah's and the decisions barely move. One weight on the reader cannot give both: each condition holds under one fit and fails under the other.

**Other slices under the calibrated fit (reported, never deciding):**
- The seeds' held-out groups (v1's gate set): the product's decisions are Lughah's (99.38%, no group won or lost), log-loss 0.0237 → 0.0220 / 0.0217.
- v1's 9,808 short messages: 98.66% / 98.64% against Lughah's 98.54%, log-loss 0.0549 → 0.0530 / 0.0525; wins / losses 13 / 1 and 12 / 2 (e-values 156 and 23.9), against Lughah as shipped 12 / 1 and 11 / 0 (90 and 341). This is not a gate and was not one: these messages were measured in v1, and their numbers are why this test was chosen.

**Cost.** One 100-byte message under all five languages, fp32 on 2 threads, the reader alone in its process (beside one other single-threaded job on the machine): 24.8 / 27.8 ms median (p90 34–36 ms); 24 bytes 6.4–7.0 ms; int8 22.9–24.2 ms. Loading took 1.2–1.4 s and 263 MB resident (306 MB after reading). Within the evaluations, run two at once: 30.6 / 20.8 ms. The evaluation process peaked at 1,044 / 1,064 MB (v1's: 2.1 GB, before the reading passes were bounded).

**Looked at after the test (exploratory, not part of it).** Of the 31 gate-half Roman messages Lughah reads as English, 24 are written entirely in English ("what are you doing tonight?", "are you going to the party?", "i have a question about inheritance law."; one more holds only "chai"), and 7 mix in Hindi words ("chalo, i'm up for it.", "neighbour se mang le!"); read by hand. Hinglish-1M labels every utterance Roman Hindi/Urdu, so much of the reader's "confident mistake" on Roman rows is the reader reading English as English, and that is the loss that pulls κ and b down. The reader's gain is the other way: of the 14 English requests Lughah reads as Roman ("book me a plane ticket", "activate robot vacuum"), the reader under v1's fit reads 12 right. Lughah's own 900 Roman seeds come from the same dataset; whether they hold such rows was not checked here.

**Verdict.** Refused for both seeds, as the second test of v1's weights. The reader stays in **shadow**.

**The next test, written down before it is run:**
1. **Labels checked by a rule neither model uses.** A Hinglish-1M row counts as Roman Hindi/Urdu only when at least one of its words reads as a Hindi or Urdu word in Qamus's Roman reading (`qamus.read_roman`: P > ½, not an English word); rows with none are left out, not relabelled. The rule's agreement with a hand-labelled sample of 200 never-read rows is reported before it is used.
2. **Calibration** as here (κ and b, γ held), on this test's calibration half with its Roman rows filtered by that rule. That half was only ever used to fit.
3. **The gate on messages never measured**: fresh Hinglish-1M rows (never read, passing the rule) and real English short requests not drawn from MASSIVE, where Lughah errs most. MASSIVE's en, hi, ur and ar partitions are all spent now (train trained on, test measured in v1, dev here). CLINC150's queries (CC BY 3.0) are one candidate, once their licence and overlap with MASSIVE are checked.
4. **The same gate** as the third test of these weights: e-value 3·4/0.05 = 240.

### Test 3: Roman labels checked by Qāmūs, gated on fresh messages

The test v1.1 wrote down, run on v1's weights again. The protocol below was fixed on 31 Oct 2026 (04:39 UTC) before any of its numbers were computed.

**Readers.** v1's kept weights, seed 0 and seed 1, loaded only when their training key matches (else that seed is retrained with v1's settings, and it is said). Lughah alone is the held-out refit, as before; Lughah as shipped is reported only.

**1. The rule, and how far it agrees with a reader.** A Hinglish-1M row counts as Roman Hindi/Urdu only when at least one of its words (`qamus.tokens`) has a reading in `qamus.read_roman` (a Hindi or Urdu word with P > ½ that is not an English word); rows with none are left out, never relabelled (`corpus.roman_words`). Before the rule is used, its agreement is measured on 200 never-read rows of the gate's Roman pool (every condition below but the rule; the first 200 by SHA-256 of `ruh-reader-test3:label:<source>`), labelled by hand, text only, before the rule is computed on them. A row is *Roman Hindi/Urdu* when at least one word is Hindi or Urdu used as such (code-mixed rows too), *English* when every word is English, names and loanwords English dictionaries hold ("chai", "yoga", "namaste") aside. Reported: the confusion table, precision and recall with Wilson intervals, Cohen's κ. The rule is used as written whatever the agreement; the 200 rows are not in the gate.

**2. Calibration.** v1.1's calibration half (only ever used to fit): its MASSIVE rows as they are, its Roman rows only where the rule holds. γ and ñ held at the development fit; κ, then b, as in v1.1 (`fit_on(…, gamma=…)`).

**3. The gate slice** (fixed, its SHA-256 recorded, before anything is scored). *Seen* texts are every line of Lughah's corpus, every training line of the reader, v1's short slice, both halves of v1.1's slices, and every MASSIVE 1.1 utterance in en-US, hi-IN, ur-PK and ar-SA (all partitions). A message is left out when its words as read are a seen text's, or *near-exact* to one: within 2 character edits, or the same words with one word more or one fewer (`corpus.Near`).
- **English**: [CLINC150](https://github.com/clinc/oos-eval) (Larson et al., EMNLP 2019; crowd-written requests to a task assistant, 23,700 queries in six splits, all used), commit `828f8093932c8fe6ca7936c3d2e52903b1c523de`, `data/data_full.json` SHA-256 `36923c37…56e0`, licence read in that commit's LICENSE: Creative Commons Attribution 3.0 Unported. Every query of 3–8 words, mostly Latin letters, not seen or near-exact, once per words. It is set aside for another source if its licence were not CC BY 3.0, more than 10% of its 3–8-word queries were exact MASSIVE utterances, or fewer than 1,000 queries remained.
- **Roman Hindi/Urdu**: Hinglish-1M utterances v1's build never read, in v1's order: 3–8 words, Latin script, a group the seeds' rule holds out, not seen or near-exact, in a conversation none of whose utterances is a seed, a v1 short message or a v1.1 row, not one of the 200 labelled; then the rule. Rows the rule holds go to the gate until it holds as many Roman rows as English ones; rows it does not are kept aside and reported. Synthetic, as before.
- One message is one group. `corpus.build_fresh` writes `fresh.tsv` and `fresh.json`.

**4. The gate** (the fresh slice only): `ruh_reader.gate` unchanged, both conditions, as the **third** test of these weights: e-value k(k+1)/α = 3·4/0.05 = **240**. Each seed on its own. A pass does not change the default (`shadow`); the owner decides.

**Reported, never deciding:** the gate slice by part and language with every arm; the Roman rows the rule left out; the gate slice under v1's development fit and under v1.1's calibration (no rule); the calibration half (in sample), v1.1's gate half, the seeds' held-out groups and v1's short messages under the new fit; latency and memory.

**The rule against a reader** (measured 04:49 UTC, before the rule was used; the 200 labels were written, and their SHA-256 recorded, before the rule was computed on any of them):

| 200 never-read rows | rule: Roman Hindi/Urdu | rule: not |
|---|---|---|
| by hand: Roman Hindi/Urdu (198) | 198 | 0 |
| by hand: English (2) | 1 | 1 |

Agreement 199/200 = 99.5% [97.2, 99.9]; precision 198/199 = 99.5% [97.2, 99.9]; recall 198/198 = 100% [98.1, 100]; specificity 1/2 [9.5, 90.6]; Cohen's κ 0.66. The one disagreement is "yes, i agree, they're growing as an artist.", where Qāmūs reads "artist" as the Urdu آرٹسٹ. Only 2 of 200 random rows are English (1.0% [0.3, 3.6]), so the sample says little about how the rule treats English rows (see below).

**The slices** (`fresh.tsv`, SHA-256 `0dfd50b8…bf79`, fixed and checked before anything was scored: no repeated group, no group a seen text's or a labelled row's, every Roman row never read, in a held-out group and in an unmeasured conversation, the rule holding on every gate Roman row and on no row it left out; a brute-force check of 300 gate rows found none near-exact to a seen text). The seeds' Hinglish ids number another file, so a conversation holding a seed was found by its words.

| Part | messages | of which | left out before |
|---|---|---|---|
| gate | 17,580 (17,580 groups) | en (CLINC150) 12,534 · Roman Hindi/Urdu 5,046 | CLINC150: not 3–8 words 10,447, seen words 209, near-exact 422, repeated 88; Roman: not a held-out group 35,949, seen words 2,972, near-exact 351, conversation measured or a seed's 317, repeated 210, labelled by hand 200, script 4 |
| left out by the rule (reported) | 157 | Roman Hindi/Urdu | |

CLINC150 passed its checks: CC BY 3.0 on the official repository, 185 of its 13,253 queries of 3–8 words (1.4%) are exact MASSIVE utterances, 12,534 remain. The never-read Roman pool ran out at 5,046 rows (the protocol's "or the pool ends"): few Hinglish-1M utterances have 3–8 words, one in five is a held-out group, and many repeat seen words. So English weighs 71% of the gate. Of v1.1's 644 calibration Roman rows the rule left out 25.

Both seeds' kept weights matched their key, so nothing was retrained: these are v1's readers.

**Calibration** (γ = 0 for both, so κ is a temperature):

| Seed | κ: development → v1.1 → test 3 | b: development → v1.1 → test 3 |
|---|---|---|
| 0 | 0.945 → 0.229 → 0.283 | 0.723 → 0.082 → 0.269 |
| 1 | 1.000 → 0.332 → 0.401 | 0.604 → 0.074 → 0.233 |

**The gate passed for both seeds.** Both conditions held.

| Seed | log-loss, Lughah → product | P(not better) | wins / losses (groups) | e-value (needed) | accuracy, Lughah → product | adopted |
|---|---|---|---|---|---|---|
| 0 | 0.0672 → 0.0525 | < 0.0005 (0 of 2,000) | 54 / 8 | 4.3·10⁷ (240) | 98.61% → 98.87% | **yes** |
| 1 | 0.0672 → 0.0505 | < 0.0005 (0 of 2,000) | 61 / 9 | 5.1·10⁸ (240) | 98.61% → 98.90% | **yes** |

**The default stays `shadow`.** A pass is reported; the owner decides whether `on` may use it.

**The gate slice** (accuracy in % [95% Wilson interval] · mean log-loss; Lughah alone is the held-out refit):

| Slice | n | Lughah alone | Reader alone, seed 0 | seed 1 | Product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| gate slice | 17,580 | 98.61 [98.42, 98.77] · 0.0672 | 98.52 [98.33, 98.69] · 0.0677 | 98.62 [98.44, 98.79] · 0.0579 | 98.87 [98.70, 99.01] · 0.0525 | 98.90 [98.74, 99.05] · 0.0505 |
| English (CLINC150) | 12,534 | 99.15 [98.98, 99.30] · 0.0553 | 98.89 [98.69, 99.06] · 0.0538 | 98.88 [98.67, 99.05] · 0.0393 | 99.43 [99.28, 99.54] · 0.0298 | 99.43 [99.28, 99.54] · 0.0283 |
| Roman Hindi/Urdu | 5,046 | 97.25 [96.76, 97.66] · 0.0966 | 97.60 [97.14, 97.99] · 0.1022 | 98.00 [97.57, 98.35] · 0.1042 | 97.48 [97.01, 97.88] · 0.1088 | 97.60 [97.14, 97.99] · 0.1057 |

- **By part** (reported; the gate is the whole slice): on English the product wins 40 / 6 and 42 / 8 groups (e 3.2·10⁵ and 8.2·10⁴) and halves the log-loss. On Roman Hindi/Urdu it wins 14 / 2 and 19 / 1 (e 64 and 5.0·10³), but its log-loss is **worse** (0.097 → 0.109 and 0.106, P(not better) 1.0): there it is more often right and, when wrong, more sure.
- **Mistakes**, held-out Lughah → product, seed 0 / seed 1: Roman read as English 134 → 123 / 117, English read as Roman 106 → 72 / 72, Roman read as Hindi 5 → 4 / 4.
- **Against Lughah as shipped** (what MIZAN runs; it never saw these messages): shipped 98.82% · 0.0595, shipped × reader 98.92% · 0.0498 and 98.96% · 0.0481; wins / losses 25 / 7 (e 77) and 36 / 10 (e 735), P(not better) < 0.0005 for both. Seed 0 would not reach 240 against it; seed 1 would. Reported only: the gate is against the held-out refit, as in every test.
- **What the rule changed.** Under v1.1's calibration (the same half without the rule; b 0.08 / 0.07) the product on this slice: 98.69% / 98.73% · 0.0611 / 0.0597, wins / losses 18 / 3 and 26 / 4 (e 143 and 2,528). Under v1's development fit: 98.90% / 98.96% but log-loss 0.095 / 0.076 (P(not better) 1.0 / 0.95). Leaving out the 25 calibration rows the rule left out (all 25 written in English, read after the test) let b rise to about a quarter, and one weight now holds both conditions.
- **Bits per byte** on the gate slice, seed 0 / seed 1: English 2.294 / 2.257 · Roman Hindi/Urdu 2.239 / 2.219.

**Other slices under the test-3 fit (reported, never deciding):**
- The 157 Roman rows the rule left out: every arm reads about 94% of them as English (Lughah right on 5.7%, the product on 5.1%): they are English rows under Hinglish-1M's label, as the rule says.
- v1.1's gate half: 98.59% → 98.78% / 98.81%, log-loss 0.0545 → 0.0526 / 0.0527, wins / losses 6 / 0 and 7 / 0 (P(not better) 0.18 / 0.20).
- The seeds' held-out groups: 99.38% → 99.38% / 99.46%, log-loss 0.0237 → 0.0188 / 0.0183 (wins / losses 0 / 0 and 2 / 0).
- v1's 9,808 short messages (measured in v1): 98.54% → 98.77% (both), log-loss 0.0549 → 0.0523 / 0.0516, wins / losses 25 / 3 (e 5,651) for both.
- The calibration half (in sample): 98.97% → 99.06% (both), log-loss 0.0465 → 0.0409 / 0.0406.

**Cost.** One 100-byte message under all five languages, fp32 on 2 threads, the reader alone in its process: 27.0 / 28.1 ms median (p90 31.9 / 36.1 ms); 24 bytes 6.1 / 6.3 ms; int8 22.5 / 24.3 ms. Loading took 1.2 s and 263 MB resident (307 MB after reading). Within the evaluations, run two at once: 18.6 / 20.1 ms. The int8 model makes the same decision on 99.85% / 99.93% of the seeds' held-out readings. Each evaluation (25,000 messages read under five languages besides v1.1's slices) took 741 / 755 s and peaked at 1,111 / 1,214 MB.

**Looked at after the test (exploratory, not part of it).** Of the 141 gate Roman rows that held-out Lughah or the seed-0 product misreads, 75 are written entirely in English by hand ("i need to buy a new power bank!", "did you watch the match?", "my internet is down!"). The rule keeps them because Qāmūs reads an English word that MASSIVE's translators wrote in Devanagari or Urdu letters as Roman Hindi: "bank" → बैंक, "team" → टीम, "match" → میچ, "dinner" → डिनर, "artist" → آرٹسٹ. The 200-row sample, with 2 English rows, could not show this. So the Roman part's measured accuracy, and its worse log-loss, are still in part the labels'. The English mistakes are terse commands ("credit limit change", "check my bank balance", "schedule a mechanic"): of Lughah's 106, the seed-0 product fixed 40 and made 6 new ones.

**Verdict.** The gate passed for both seeds as the third test of v1's weights (e ≥ 240; the e-values and the log-loss bootstrap far past it). The gain is on English requests; on Roman Hindi/Urdu the product is more often right but worse calibrated. The reader stays in **shadow** until the owner decides. Using it `on` would also need a version installed with this fit and verdict: `install` writes the development fit and the seeds' gate, which refused it.

### v2: without model-written text

On 31 Oct 2026 the owner decided that the reader must be retrained without Hinglish-Everyday-Conversations-1M: its card says GPT-4o-mini wrote it, and MIZAN never trains on OpenAI's or Anthropic's output ([consent.md](consent.md)). v1 learned from it twice: its 10,445 corpus lines (all of v1's Roman Hindi/Urdu corpus) and the 900 of Lughah's 982 Roman seeds that are Hinglish-1M rows. v2 is a new reader, trained without either. The protocol below was fixed on 31 Oct 2026 (05:47 UTC) before any of its numbers were computed.

**What v2 learns from.**
- *No text a language model wrote* (`corpus.MODEL_WRITTEN`). Hinglish-1M is a measurement source only (`corpus.HINGLISH_1M`): it still gives the Roman part of `short.tsv` (v1's short slice, so v1 and v2 are reported on the same messages) and v1.1's and test 3's slices. Lughah's Hinglish-1M seeds (`ruh_reader.written_by_a_model`) are left out of the reader's training lines, of its development lines (which pick the checkpoint and give γ), and of the night's 25% replay; they stay in the seeds' held-out groups, which are reported only. Lughah itself still counts them: that is Lughah's corpus, not changed here.
- *Roman Hindi/Urdu people wrote*: [FineWeb-2](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2) `hin_Latn` and `urd_Latn` (ODC-By 1.0 and Common Crawl's terms, read on the card at commit `af9c1333`, the speaker's pins: `data/hin_Latn/train/000_00000.parquet` SHA-256 `e26effec…97ea`, `data/urd_Latn/train/000_00000.parquet` `82937843…73bd`). One document in five (SHA-256 of `ruh-reader-v2:held:<source>:<id>`) is held out for good. Of the others, those whose rank falls in a thirty-second are read in rank order, each cut into short lines (`corpus.lines_of`: line breaks and sentence ends; a piece over 192 bytes of words cut into the fewest equal runs) and giving its first 32, round robin over the two subsets, until 900,000 bytes of words: v1's Roman share.
- *Every rule v1's lines passed*, and two more: no line is the words of, or near (`Near`), any message ever measured (v1's short slice, v1.1's and test 3's slices and labels, v2's slices and labels); the speaker's hadith rule (8 words in a row of the six books, Arabic and English); and a FineWeb-2 document with scripture or hadith anywhere in its whole text (`speaker.pieces`, `speaker.Sieve` in front of `ruh_reader.scripture`) gives no line at all.
- The rest as v1: the same model and plan (3,480,064 parameters; one pass, 1,800 s at most, 6 development checks), Tatoeba and MASSIVE's train partition from v1's downloads, two seeds trained one at a time on 2 threads, weights kept the moment training ends.

**The slices** (`corpus.build_v2`; fixed, and their SHA-256 recorded, before anything is scored). *Seen* texts are never measured: every line of Lughah's corpus and of v1's corpus (its Hinglish rows too), v1's short slice, v1.1's and test 3's slices and labels, every MASSIVE 1.1 utterance and every CLINC150 query; a message near one (2 character edits, or one word more or fewer) is left out too. A message has 3–8 words, its language's script, and words no earlier message has.
- **English**: [BANKING77](https://github.com/PolyAI-LDN/task-specific-datasets) (PolyAI; Casanueva et al. 2020, [arXiv:2003.04807](https://arxiv.org/abs/2003.04807); 13,083 customer-service queries written by people, the card says "expert-generated"), commit `57ec275d`, LICENSE CC BY 4.0, `banking_data/train.csv` `b06e26ac…664b` and `test.csv` `d12d6e3b…474d`. CLINC150 has no unread 3–8-word query left: test 3 used all 12,534.
- **Roman Hindi/Urdu**, people's writing from three sources, each giving each half at most a third of that half's English count (rounded up), in SHA-256 order: [Dakshina](https://github.com/google-research-datasets/dakshina) 1.0's romanized Hindi and Urdu Wikipedia sentences (CC BY-SA 4.0, measured only; romanized by native speakers, so Hindi or Urdu by construction); [PHINC](https://huggingface.co/datasets/LingoIITGN/PHINC)'s code-mixed tweets (CC BY 4.0 on the card at `44b5471d`, measured only; mentions, hashtags and links set aside); and lines of FineWeb-2's held-out documents (a quarter of them read, at most 3 lines a document). A PHINC or FineWeb-2 row counts only where Qāmūs reads **two** distinct Hindi or Urdu words in it (`roman_words(…, least=2)`; test 3's rule asked one, and kept English rows with one loanword such as "bank"); the others are kept apart and reported.
- **Groups and halves.** A query, tweet or sentence is one group; a FineWeb-2 document is one group (its lines count together). Each group lies in the calibration half or the gate half by SHA-256 of `ruh-reader-v2:<group>`.
- **The rule against a reader.** Before the rule is used, the first 200 PHINC and FineWeb-2 rows (one per group) in a SHA-256 order of their own, passing every condition but the rule, are labelled by hand (text only; Roman Hindi/Urdu when a word is Hindi or Urdu used as such, English when every word is English, names and dictionary loanwords aside, *other* when neither), the labels' SHA-256 recorded before the rule is computed on them. Reported: the rule's confusion table, precision and recall (Wilson), Cohen's κ, and test 3's one-word rule beside it. The rule is used as written whatever the agreement; the 200 rows' groups are left out of the slices.

**Calibration** on the calibration half (its counted rows): γ and ñ held at each seed's development fit; κ, then b (`fit_on(…, gamma=…)`).

**The gate** on the gate half (English and Roman together): `ruh_reader.gate` unchanged, both conditions, as the **first** test of these weights: e-value 1·2/0.05 = **40**. Each seed on its own. A pass does not change the default (`shadow`); the owner decides.

**Reported, never deciding:** the gate half by part (English; Roman by source) with every arm, Lughah as shipped too; the rows the rule left out; the gate half under the development fit; the calibration half in sample; under v2's fit, the seeds' held-out groups, v1's short slice, v1.1's gate half and test 3's fresh slice (their Hinglish-1M rows for comparison only); **v1 on the same slices** (its kept weights, calibrated the same way on v2's calibration half, read on v2's gate half; not a test of v1), and v2's product against v1's; latency and memory.

**The rule against a reader** (05:49 UTC: the 200 rows were drawn at 05:48 without the rule; their labels, read by hand row by row, were written and their SHA-256 recorded before the rule was computed on any of them). 79 PHINC rows and 121 FineWeb-2 lines; 161 Roman Hindi/Urdu, 33 English, 6 other (two Roman Gujarati rows, four of names or a citation only).

| 200 rows | two words (used) | one word (test 3's; reported) |
|---|---|---|
| Roman Hindi/Urdu (161): counted / not | 153 / 8 | 160 / 1 |
| English (33): counted / not | 4 / 29 | 21 / 12 |
| other (6): counted / not | 2 / 4 | 4 / 2 |
| precision | 96.2% [92.0, 98.3] | 86.5% [80.8, 90.7] |
| recall | 95.0% [90.5, 97.5] | 99.4% [96.6, 99.9] |
| specificity | 84.6% [70.3, 92.8] | 35.9% [22.7, 51.6] |
| Cohen's κ | 0.78 | 0.46 |

The two-word rule still counts three FineWeb-2 headers of a news site ("Breaking » Monday, April 22, 2013"), one English line and the two Gujarati rows; the one-word rule would have counted 21 of the 33 English rows. Reading the rows by hand also showed that FineWeb-2's Latin subsets hold sexually explicit pages: they are web text people wrote, and the reader learns which language a line is in, not what it says.

**The slices** (`v2.tsv`, SHA-256 `356948c3…84e7`, fixed and checked before anything was scored: each group in one half, no words repeated, none a seen text's, none of a hand-labelled row's group, every FineWeb-2 row from a held-out document, the rule holding on every counted web or tweet row and on no row kept apart; a brute-force check of 300 rows found none near a seen text):

| Half | English (BANKING77) | Dakshina | PHINC | FineWeb-2 (hin / urd) | messages (groups) | kept apart by the rule (PHINC / FineWeb-2) |
|---|---|---|---|---|---|---|
| calibration | 2,524 | 842 | 842 | 842 (525 / 317) | 5,050 (4,607) | 157 / 842 |
| gate | 2,440 | 814 | 814 | 814 (505 / 309) | 4,882 (4,458) | 180 / 814 |

**The corpus** (`train.tsv` SHA-256 `b5698b93…f96a`, 77,101 lines; built after the slices): Roman Hindi/Urdu 8,989 FineWeb-2 lines (hin 4,756, urd 4,233), 893,812 bytes of words (0.7% under the budget: 1,336 lines of the window fell with documents that hold scripture or hadith, 854 of them Roman Urdu); no line from Hinglish-1M. The rule against measured messages also took 1,892 MASSIVE training utterances that are near a test or dev utterance (MASSIVE's requests share templates), so English, Hindi, Urdu and Arabic take a little more Tatoeba than in v1. `short.tsv` is v1's byte for byte (`aa47199e…`). A brute-force check of 3,000 training lines found none near a measured message. The reader then trains on 79,729 lines: 2,628 seed lines (636 Hinglish-1M seeds left out) and the corpus; its development set is 366 seeds (86 Hinglish-1M seeds left out).

**Training.** One seed at a time, alone on the machine (2 threads; the evaluation of seed 0 ran beside seed 1's training): both finished the pass, 2,492 steps of 32 lines (4,584,428 tokens), in 936 s and 929 s. Development bits per byte 1.688 and 1.645 (v1: 1.715 and 1.709), still falling at the last check. Each seed's weights were kept the moment training ended, and its evaluation found them by their key. Before that, a smoke run of the evaluation with a tiny untrained model (b = 0) printed Lughah's own numbers on the gate half; the protocol was already committed, and nothing in it changed.

**Calibration** (γ = 0 for both, so κ is a temperature; ñ = 47 bytes):

| Seed | κ: development → calibrated | b: development → calibrated |
|---|---|---|
| 0 | 1.000 → 0.405 | 1.000 → 0.672 |
| 1 | 0.802 → 0.481 | 0.592 → 0.696 |

**The gate passed for both seeds.** Both conditions held, far past the bar.

| Seed | log-loss, Lughah → product | P(not better) | wins / losses (groups) | e-value (needed) | accuracy, Lughah → product | adopted |
|---|---|---|---|---|---|---|
| 0 | 0.1187 → 0.0708 | < 0.0005 (0 of 2,000) | 96 / 3 | 8.1·10²² (40) | 95.92% → 97.87% | **yes** |
| 1 | 0.1187 → 0.0641 | < 0.0005 (0 of 2,000) | 110 / 3 | 7.8·10²⁶ (40) | 95.92% → 98.16% | **yes** |

**The default stays `shadow`.** A pass is reported; the owner decides. Using it `on` would also need v2 installed with this fit and this verdict: `install` writes the development fit and the seeds' gate (which, under the development fit, it does not pass: see below).

**The gate half** (accuracy in % [95% Wilson interval] · mean log-loss; Lughah alone is the held-out refit):

| Slice | n | Lughah alone | Reader, seed 0 | seed 1 | Product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| gate half | 4,882 | 95.92 [95.33, 96.44] · 0.1187 | 98.53 [98.15, 98.83] · 0.0487 | 98.65 [98.28, 98.94] · 0.0459 | 97.87 [97.43, 98.24] · 0.0708 | 98.16 [97.74, 98.50] · 0.0641 |
| English (BANKING77) | 2,440 | 99.71 [99.41, 99.86] · 0.0376 | 99.88 [99.64, 99.96] · 0.0099 | 99.51 [99.14, 99.72] · 0.0171 | 99.92 [99.70, 99.98] · 0.0035 | 99.88 [99.64, 99.96] · 0.0051 |
| Roman Hindi/Urdu | 2,442 | 92.14 [91.00, 93.14] · 0.1996 | 97.17 [96.44, 97.76] · 0.0874 | 97.79 [97.13, 98.30] · 0.0747 | 95.82 [94.95, 96.55] · 0.1380 | 96.44 [95.63, 97.10] · 0.1231 |
| Dakshina | 814 | 86.98 [84.49, 89.12] · 0.2810 | 95.70 [94.08, 96.89] · 0.1117 | 96.93 [95.51, 97.91] · 0.0795 | 94.10 [92.27, 95.52] · 0.1561 | 95.45 [93.80, 96.68] · 0.1208 |
| PHINC | 814 | 98.16 [96.98, 98.88] · 0.0631 | 99.26 [98.40, 99.66] · 0.0316 | 99.39 [98.57, 99.74] · 0.0237 | 98.89 [97.91, 99.42] · 0.0426 | 98.89 [97.91, 99.42] · 0.0341 |
| FineWeb-2 (held-out pages) | 814 | 91.28 [89.14, 93.03] · 0.2546 | 96.56 [95.07, 97.61] · 0.1188 | 97.05 [95.65, 98.01] · 0.1209 | 94.47 [92.68, 95.84] · 0.2153 | 94.96 [93.24, 96.27] · 0.2145 |

- **By part** (reported; the gate is the whole half), wins / losses, seed 0 · seed 1: English 6 / 1 · 6 / 2 (log-loss 0.038 → 0.004 · 0.005); Dakshina 60 / 2 · 70 / 1; PHINC 6 / 0 · 6 / 0; FineWeb-2 24 / 0 · 28 / 0. The log-loss falls on every part, Roman Hindi/Urdu included (0.200 → 0.138 · 0.123): unlike test 3, the product is not worse calibrated on Roman rows. Most of the gain is on sources the reader never learned from: Dakshina's and PHINC's rows are not FineWeb-2's style, and Dakshina alone holds 60 of seed 0's 96 groups won and 70 of seed 1's 110.
- **Mistakes**, held-out Lughah → product, seed 0 / seed 1: Roman read as English 192 → 101 / 85; English read as Roman 7 → 2 / 3.
- **Against Lughah as shipped** (what MIZAN runs; it never saw these messages): 96.42% · 0.1138 → 97.87% · 0.0749 and 98.20% · 0.0684; wins / losses 76 / 6 and 90 / 4.
- **Under the development fit** (κ, b fitted on the 366 development seeds): more decisions change (98.28% / 98.32%, wins 120 / 8 and 118 / 3), but seed 0's log-loss gain is not beyond chance there (0.119 → 0.107, P(not better) 0.19); seed 1's is (0.119 → 0.066, P(not better) < 0.0005). Calibrating on real short messages is what makes both conditions hold, as in test 3.
- **The rows the rule left out** (994: 180 PHINC, 814 FineWeb-2; reported): every arm reads most of them as English, which most are (Lughah right on 38%, the product on 46% / 47%), and the product's log-loss on them is worse (1.82 → 2.56 / 2.57): it is surer than Lughah that English lines are English.
- **Bits per byte** on the gate half, seed 0 / seed 1 (v1's in brackets): BANKING77 2.47 / 2.48 (2.39 / 2.35), Dakshina 3.26 / 3.26 (3.83 / 3.86), PHINC 3.03 / 3.02 (3.18 / 3.18), FineWeb-2 3.04 / 3.01 (3.42 / 3.42).

**v1 on the same slices** (its kept weights, calibrated the same way on v2's calibration half: κ 0.366 / 0.374, b 0.404 / 0.430; reported, not a test of v1):

| Slice | n | Lughah alone | v1 product, seed 0 | seed 1 | v2 product, seed 0 | seed 1 |
|---|---|---|---|---|---|---|
| gate half | 4,882 | 95.92 · 0.1187 | 96.80 · 0.0976 | 96.95 · 0.0940 | 97.87 · 0.0708 | 98.16 · 0.0641 |
| English (BANKING77) | 2,440 | 99.71 · 0.0376 | 99.71 · 0.0104 | 99.84 · 0.0101 | 99.92 · 0.0035 | 99.88 · 0.0051 |
| Roman Hindi/Urdu | 2,442 | 92.14 · 0.1996 | 93.90 · 0.1847 | 94.06 · 0.1778 | 95.82 · 0.1380 | 96.44 · 0.1231 |
| Dakshina | 814 | 86.98 · 0.2810 | 90.91 · 0.2160 | 91.15 · 0.2068 | 94.10 · 0.1561 | 95.45 · 0.1208 |
| PHINC | 814 | 98.16 · 0.0631 | 98.03 · 0.0555 | 98.28 · 0.0462 | 98.89 · 0.0426 | 98.89 · 0.0341 |
| FineWeb-2 | 814 | 91.28 · 0.2546 | 92.75 · 0.2826 | 92.75 · 0.2804 | 94.47 · 0.2153 | 94.96 · 0.2145 |

v1 against Lughah on this half: wins / losses 48 / 6 and 55 / 6. v2's product against v1's, the same seed, on the same messages: wins / losses 57 / 5 and 65 / 7, log-loss 0.098 → 0.071 and 0.094 → 0.064 (P(not better) < 0.0005 for both). Without a line a model wrote, the reader is better on people's Roman Hindi/Urdu than v1 was, and no worse on English requests.

**The old slices under v2's calibrated fit** (reported, never deciding), Lughah alone → product, seed 0 / seed 1:
- The seeds' held-out groups (their Hinglish-1M seeds too): 99.38% → 99.38% / 99.49%, log-loss 0.0237 → 0.0196 / 0.0191 (wins / losses 4 / 4 and 5 / 3). v1 under the same calibration: 99.46% / 99.49%.
- v1's short slice, MASSIVE (en, hi, ur, ar; 7,808): 99.42% → 99.86% (both), log-loss 0.026 → 0.005 / 0.006. Its 2,000 Hinglish-1M rows (comparison only): 95.10% → 94.95% / 95.20%, log-loss 0.168 → 0.346 / 0.353 (v1's seed 0 under the same calibration: 95.25% · 0.239).
- v1.1's gate half: 98.59% → 98.93% (both), log-loss 0.0545 → 0.078 / 0.081, wins / losses 11 / 0 (both).
- Test 3's gate slice: CLINC150 English (12,534) 99.15% → 99.71% / 99.59%, log-loss 0.055 → 0.011 / 0.013, wins / losses 77 / 7 and 74 / 20; its Hinglish-1M rows (5,046, comparison only) 97.25% → 97.46% / 97.30%, log-loss 0.097 → 0.174 / 0.182.
- On Hinglish-1M's own rows v2 is worse calibrated than v1 (its log-loss there about doubles, as v1's did not): those rows are a language model's style, and many are English under a Roman label (test 3); v2 never saw that style.

**Cost.** One 100-byte message under all five languages, fp32 on 2 threads, the reader alone in its process: 27.5 / 32.0 ms median (p90 31.3 / 36.6); 24 bytes 6.8 / 7.5 ms; int8 25.0 / 26.9 ms. Loading took 1.4–1.5 s and 263 MB resident (303–308 MB after reading), as v1. The int8 model makes the same decision on 99.56% / 99.64% of the seeds' held-out readings. Each evaluation (the v2 reader and v1 on about 47,000 messages under five languages) took 1,244 / 1,300 s and peaked at 1,158 / 1,092 MB.

**Looked at after the test (exploratory, not part of it).** Of the gate rows the seed-0 product still misreads, most are not Roman Hindi/Urdu in any sense a reader could find: Dakshina's romanized Wikipedia sentences include place names and English titles ("Fairmount Township, Butler County, Kansas", "Lake Wood, Washington", "Catholic encyclopedia: Cana"), and the FineWeb-2 lines the two-word rule kept include page furniture ("Breaking » Friday, April 19, 2019", "Submitted by Kumar on 19 Aug 2013", "WhatsApp Dark Mode"). The product loses 3 groups per seed (seed 0: "Visa or Mastercard?" read as Roman Hindi/Urdu, and two Dakshina rows).

**Verdict.** Reader v2, trained without any text a language model wrote, passed its first gate for both seeds (e ≥ 40; the e-values and the log-loss bootstrap far past it), and is better than v1 on the same messages. The gain is on Roman Hindi/Urdu people wrote, sources it never trained on included; English requests improve a little. On Hinglish-1M's synthetic rows it is worse calibrated than v1. The reader stays in **shadow** until the owner decides.

## Learning while MIZAN works (Tadrib)

Since 31 Oct 2026 the reader does not wait for the night ([tadrib.md](tadrib.md)). Each message of a person who switched `training: on` becomes a **lesson** as soon as it is answered: their own words (pasted text set aside), when Amanah finds no instruction aimed at an AI and no scripture is in it. A background trainer:

1. scores the lesson with the fast copy and with the current (slow) version, before learning anything;
2. keeps it only where Lughah and the serving reader read the same language (the owner's decision: this check by MIZAN stands in for a person's review);
3. holds one lesson in five out as test, and learns the rest in a few steps (replay of seeds and recent lessons, an L2 pull toward the slow weights);
4. swaps the fast weights into the loaded reader, and keeps them on disk (`fast.pt`, `fast.json`) every few lessons.

On the held-out lessons a paired sign test watches the fast copy: once the slow version reads them better with e-value ≥ 20, the fast copy starts again from it. Lessons are listed per person (`GET /api/tadrib/lessons`) and can be taken back (`DELETE /api/tadrib/lessons/{digest}`).

## Learning while MIZAN rests

Nawm (`tadbir/nawm.py`, [automatic learning](automatic-learning.md#nawm-what-was-learned-is-replayed-while-mizan-rests)) calls `ruh_reader.rest` for each person once a day, while no request runs:

1. **Consent.** Nothing happens unless the reader is not `off`, its weights exist, and the person's choices bound for the night say `learning` is on and `training: on` (`stateless.learns()` and `stateless.trains()`; never in an evaluation or a WhatsApp run, `barred_from_training()`). See [Consent](consent.md).
2. **Verified words only.** The day's lessons (Tadrib), each under the language MIZAN checked when it was given, and the person's messages captured as training candidates (only under `training: on`) that a named reviewer accepted, with the review hash still matching the content (`reviewed_words`, the learner store). A message holding the Quran's words is never learned, nor one already learned.
3. **Labels.** A message is learned under the language Lughah and the reader both read it in. Where they disagree it is not learned, because a label the two contest is not verified.
4. **Training.** The current weights continue training within the night's time (about 60% of what is left), 3 passes at most at a learning rate of 5·10⁻⁴. A quarter of every batch is replayed from the seeds' training groups (never a model-written seed: `ruh_reader.trainable`): in the pilot (`research_notes`, 3.8M parameters, three sequential languages), 25% replay held the earlier languages with no forgetting, where EWC alone did not.
5. **Promotion.** The new version replaces the current one only when, on the held-out seeds, its log-loss is not higher and Ta'lim's paired bootstrap does not find it less accurate (P(worse) < 0.95, `no_worse`), and none of what it learned was erased while it trained (checked under the lock just before). The current one is kept as `previous` for `rollback()` and in `nights/` (the last 7). The lessons it learned are marked consolidated, and the fast copy starts again from it. The gate is then run again as the next test (needing k(k+1)/α), and decides whether `on` may use the new version.
6. **Forgetting.** Each version records the SHA-256 of every message it learned, and no words; so does the fast copy. Erasing a chat (Mahw) or rejecting a lesson drops every version that learned it, the fast copy and the kept nights included, and the newest version that did not becomes current; the fast copy is rebuilt from it with the lessons that remain. The seed-only `base` version is never dropped. One lock (`disk_lock`, an `flock` beside the weights) covers learning, saving and forgetting.

## Settings and files

- `MIZAN_RUH_READER` (Settings → Developer → System settings, Model group):
  - `shadow` (default): the reader is computed beside Lughah, disagreements are logged (`mizan.ruh_reader`), counts are kept in `ruh_reader.status()["shadow"]`, and the decision is Lughah's.
  - `on`: the product is used once the gate passed.
  - `off`: the reader is never loaded.
- **Weights:** `$MIZAN_DATA_DIR/models/ruh_reader/`. `current`, `previous` and `base`, each `.pt` (fp32 weights), `.json` (corpus SHA-256, config, fit, gate, learned digests) and `.reads.json` (the development and held-out messages as held-out Lughah read them, so a night re-scores only the reader).
- **Corpus:** `cd backend && python -m tadbir.ruh_reader --corpus [--old V1_CORPUS] [--hadith] [--bytes-per-language 900000] [--workers 3]` downloads the sources (about 580 MB with FineWeb-2's two Latin files, kept in `$MIZAN_DATA_DIR/corpora/ruh_reader/sources/`; FineWeb-2 is read with `pyarrow`), fetches the Quran's texts if they are not on disk (and the six books' with `--hadith`), and writes `train.tsv`, `short.tsv` and `manifest.json` (v2: 2 minutes with 3 workers on the development sandbox). A corpus whose files changed, or that was built against other seeds, is not used.
- **v2's slices** (before its corpus): `cd backend && python -m tadbir.ruh_reader --v2-labels --old V1_CORPUS --dakshina DIR` writes `v2_labels.tsv` (the rows to label by hand, drawn without the rule); `--v2` downloads BANKING77 and PHINC (pinned) and writes `v2.tsv` and `v2.json` beside the corpus; DIR holds Dakshina's four romanized files (pinned by SHA-256). `python ../scripts/ruh_reader_eval.py --corpus … --v2 V1_CORPUS --test 1 [--compare V1_WEIGHTS --compare-fit V1_JSON] …` calibrates on v2's calibration half and gates on its gate half.
- **Train and install:** `cd backend && python -m tadbir.ruh_reader --train [--seed N] [--threads 2] [--seeds-only]`. It trains on the corpus when one is built (`--seeds-only` ignores it). Without `--train` it prints the status.
- **Measure:** `cd backend && python ../scripts/ruh_reader_eval.py --seeds 0 1 [--corpus] --json out.json [--install 0] [--save DIR]`; `--evaluate DIR` reads an installed reader (`current.pt`, `current.json`) on the same slices without training.
- **v1.1's validation slices:** `cd backend && python -m tadbir.ruh_reader --validation` writes `validation.tsv` and `validation.json` beside the corpus, from its own downloads (pins checked). `python ../scripts/ruh_reader_eval.py --corpus --validation [--test K] …` calibrates κ and b on the calibration half (γ held, `fit_on(…, gamma=…)`) and runs the gate on the gate half as the K-th test (by default the reader's tests + 1).
- **Test 3's fresh slices:** `cd backend && python -m tadbir.ruh_reader --fresh-labels` writes `labels.tsv` (the rows to label by hand, drawn without the rule); `--fresh` downloads CLINC150 into `sources/clinc150/` (pinned) and writes `fresh.tsv` and `fresh.json` beside the validation slices. `python ../scripts/ruh_reader_eval.py --corpus --validation --fresh --test 3 …` calibrates with the Roman rule and gates on the fresh slice.

Without weights nothing is loaded and torch is never imported: the default deployment is unchanged until an operator trains a reader. Once weights exist, shadow mode loads torch into the server process (a few hundred MB of resident memory on the 2 GB production machine) in a background thread. The message in hand is read without the reader until it is loaded.

## Limits

- **Small data.** v0 learned from about 200 KB of seed text (3,305 lines); v1 adds 4.4 MB of its own corpus and is still one pass from its budget. The pilot's byte model had 12M tokens of web text and reached 1.2–2.4 bits per byte. Here the held-out bits per byte are higher (see the table), and Roman Hindi/Urdu (982 seeds) and English are the weakest.
- **Easy test, hard ceiling.** On whole held-out sentences Lughah is already 100% right, so only shorter readings can show a gain. The short readings are cut from whole sentences, which is not the same as messages people actually send.
- **Model-written text.** v1 was trained on Hinglish-1M, which GPT-4o-mini wrote; v2 is not. Lughah's own 900 Hinglish-1M seeds still shape Lughah's counts, and so the product of experts through Lughah's factor; changing Lughah's corpus is a separate decision.
- **Synthetic Roman labels.** Hinglish-1M labels every utterance Roman Hindi/Urdu, including many written entirely in English (24 of the 31 that v1.1's gate half has Lughah read as English). Measured accuracy on those rows is a floor set by the labels, and their log-loss weighs most in the calibration. Test 3's rule (a word Qāmūs reads as Hindi or Urdu) leaves out some of them, but keeps English rows holding a loanword MASSIVE writes in Devanagari or Urdu ("bank", "team", "match"): 75 of the 141 Roman rows misread in test 3 are English.
- **Where test 3's gain is.** It is on English requests (CLINC150, 71% of its gate). On Roman Hindi/Urdu the product was more often right but its log-loss worse than Lughah's.
- **Labels at night come from the models themselves.** A message is learned under the language both read it in. The night can adapt the reader to how people write, but cannot teach it a language Lughah misreads.
- **Memory.** Weights cannot have one message subtracted. Forgetting falls back to an earlier version, which also loses what later nights learned from other messages.
- **Shadow cost.** Reading every message costs CPU (see latency) and torch's memory, for no change in the decision until the gate passes.
