# Ruh pilot: the root/pattern channel at matched compute, and the feasibility numbers the design assumes (29–30 Oct 2026)

Measurements made in the development sandbox on 30 Oct 2026: **Intel(R) Xeon(R) Processor @ 2.80 GHz** (4 vCPU visible, 16 GB RAM, no GPU), `torch 2.14.1+cpu`, Python 3.13. Every timing that stands for production was taken with `torch.set_num_threads(2)` on an otherwise idle machine; the three training arms were run concurrently with one torch thread each (4 cores shared with a sibling researcher's job), and their 2-thread throughput was measured separately. Peak RSS of every process was kept under the stated limit except where noted (the training processes' `ru_maxrss` includes memory-mapped data pages; anonymous memory stayed ≈1.2 GB).

Scripts (all in the session scratchpad (working files of the session, not kept)): `fetch_fineweb.py` (row-group range reads from FineWeb2/FineWeb-Edu parquet), `data_prep.py` (corpus, Quranic Arabic Corpus lexicon, Quran-span masking, splits, per-byte factor ids), `factor_ids.py`, `ruhpilot.py` (byte GPT with additive root/pattern/concept channels, RoPE, KV cache, matched-parameter configs), `train_arms.py` (plan / train / bpb / feats), `probe_massive.py` (linear probe, Tamyiz baseline, Wilson, paired e-value, McNemar), `larkey.py` (precision test on BM25, Fihris editions, `memory.dhikr.about`), `kv_bench.py`, `continual.py`, `knn_lm.py`, `after_arms.sh`. Results as JSON in `../results/`.

Tags: **[measured]** = run here; **[estimated]** = arithmetic from measured or published numbers; **[inference]** = my reading. Literature numbers carry the primary source and date.

What this note does **not** repeat: E1 (CPU throughput of the Ruh architecture) and E2 (root coverage of Lughah seeds) in `experiments_cpu_and_root_coverage.md`; the code audit in `audit_ruh_model_state.md`; `tiny_language_model_on_cpu.md` KQ1–KQ5; the Qāmūs design and A/B/C plan in `root_space_interlingua.md` KQ4–KQ5; the kNN/SDMLP/EWC material in `neuroscience_memory_and_cpu_models.md` Q2–Q4; Larkey 2002 and the sample-size formulas in `failure_modes_honest_ceilings_measurement.md` KQ3–KQ4.

---

## Data used by every experiment (licence-clean; the Quran and hadith were never training text)

### Takeaway
≈85 MB of web text in four languages plus MASSIVE 1.1 train utterances and MIZAN's Lughah seeds; Quranic passages were removed by exact word-shingle match against the five Fihris editions; the Quranic Arabic Corpus table gives a root to 8.3 % of Urdu and 25 % of Arabic word tokens in this web text (lower than E2's Tatoeba sentences, as expected for MSA web prose).

### Cited Findings
- **[measured]** Sources: FineWeb2 `urd_Arab`, `arb_Arab`, `hin_Deva` (first 2–4 row groups of shard `000_00000`, 19.1 / 32.0 / 19.9 MB of text; ODC-By 1.0 — [HF dataset](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2)); FineWeb-Edu `sample/10BT` (14.5 MB; ODC-By 1.0 — [HF dataset](https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu)); MASSIVE 1.1 `ur-PK`, `ar-SA`, `hi-IN`, `en-US` (11,514 train / 2,033 dev / 2,974 test utterances per locale, 60 intents; CC BY 4.0 — [amazon-massive-dataset-1.1.tar.gz](https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz), [FitzGerald et al. 2022](https://arxiv.org/abs/2204.08582)); MIZAN Lughah seeds `ur/ar/hi/en/hi-latn.tsv` (Tatoeba CC BY 2.0 FR, Hinglish-1M MIT, authored CC0; `quote.tsv` and `name.tsv` excluded — `backend/tadbir/data/lughah/LICENSES.md`). Arabic WordNet 4.0 / IndoWordNet were not fetched (see Gaps); CAMeL Tools is not installed and its r13 database is a separate download, so the root table is the Quranic Arabic Corpus alone.
- **[measured]** Quranic Arabic Corpus morphology v0.4 as pinned by `backend/tadbir/sarf.py` (SHA-256 `742bfac5…`, GPL, downloaded once): 14,835 surface forms, 14,215 with a root, **1,647 distinct roots** (E2 reported 1,651 before Sarf's fold merged four), **1,508 distinct vowelled patterns (wazn)**.
- **[measured]** Quran masking: Arabic lines holding any 4-word shingle of `quran-simple-clean`, or any 6-word shingle of the Saheeh / Jalandhry / Hindi / transliteration editions, with at least two words outside the edition's 300 most frequent, were dropped. Removed: ur 247,650 B (99 of 4,941 web documents touched), ar 1,355,635 B (210 of 5,209), hi 16,082 B (17), en 2,777 B (6). A first pass with 3/4-word shingles and no frequency rule removed **53 % of the Urdu sample**, almost all false positives (e.g. "نے کہا ہے کہ", "at the time of"), which is why the rule above was adopted.
- **[measured]** Root coverage after the Urdu→Arabic letter mapping (ہ→ه ھ→ه ی→ي ے→ي ک→ك ۃ→ة ں→ن) and Sarf's fold, exact Quranic form with a small clitic cascade (و/ف proclitic, ال/وال/لل): **Urdu 8.3 % of Arabic-script word tokens (6.7 % of bytes)**, **Arabic 25.1 % of tokens (18.7 % of bytes)**; Hindi, English, Roman Urdu 0 by construction.
- **[measured]** Proxy concept ids (arm C): 4,745 Arabic-script strings occur ≥3 times in both the Urdu and the Arabic training text (3,500 kept) and 532 Latin strings occur in both English and Roman-Urdu/Hinglish seeds (500 kept): they cover 24.7 % of Urdu bytes, 14.5 % of Arabic, 8.9 % of English, 28.2 % of Hinglish bytes.
- **[measured]** Splits: held-out ≈450 KB per language (ur 121 documents, ar 90, hi 114, en 125), Roman Urdu 5.6 KB (76 lines); training streams ur 19.0 MB, ar 30.9 MB, hi 20.6 MB, en 14.5 MB, hi-latn 71 KB. Mixture for training: 24 % each of ur/ar/hi/en and 4 % hi-latn by tokens.

### Inferences
- **[inference]** The web-text root coverage (8 % Urdu, 25 % Arabic) is the realistic figure for a chat assistant's input, below E2's 10.5 % / 43 % on short Tatoeba sentences; whatever the channel does, it acts on a minority of bytes.
- **[inference]** Exact shingle matching against the Fihris editions is a sufficient "no Quran as training target" filter for web text once function-word shingles are excluded; `iqtibas.py` would add fuzzy spans but needs the editions loaded in-process and was not required here.

### Gaps
- No Roman Urdu / Hinglish corpus beyond the 982 Lughah lines (the MIT Hinglish-1M set was not downloaded in this session); the hi-latn BPB numbers rest on 5.6 KB.
- Arabic WordNet 4.0 and IndoWordNet ids were not fetched; the concept channel is the documented proxy (shared spelling), which is a loan-word detector, not a sense inventory.

---

## KQ-A. Literature: root/pattern factors inside a language model (what the factored-LM line actually measured)

### Takeaway
Every published number comes from the 2003–2013 factored-LM line on ~170K-word CallHome Egyptian Arabic and a few larger MSA/Iraqi sets: the whole bundle of factors (stem + morph class + root + pattern) with genetically-optimised backoff bought 2–6 % perplexity over an optimised word trigram and 0.6–1.8 points absolute WER (≈1–3 % relative), with the FLM alone sometimes *worse* than the baseline; the root stream by itself moved WER by 0.1 point; neural factored LMs gained 8–12 % perplexity at 170K words only when interpolated with the n-gram; root-enriched embeddings in 2019 matched FastText's character n-grams to within 0.4 % perplexity. Gains were largest where data were sparsest and shrank or reversed where n-gram coverage was good (eval03 bigram). No paper isolates the root/pattern factor at matched parameters in a neural LM.

### Cited Findings
- **Bilmes & Kirchhoff, HLT-NAACL 2003 (short paper).** Factors "can be anything, including morphological classes, stems, roots"; CallHome ECA words carry deterministically derived morphological class (M), stem (S), root (R) and pattern (P); training = official LDC CallHome ECA training portions + the ECA supplement (100 conversations), test = 1996 evaluation set. Table 1 (perplexity): word 3-gram **173**; FLM 3-gram (w₁,w₂,m₁,s₁) **178**; GPB-FLM 3-gram **166** (−4.0 %); word 2-gram **175**; FLM 2-gram (w₁,m₁) 173; FLM 2-gram (w₁,m₁,s₁) 179; GPB-FLM 2-gram **167** (−4.6 %). "The FLM alone might increase perplexity, but the GPB-FLM decreases it"; "it is possible to obtain a 2-gram with lower perplexity than the optimized baseline 3-gram." The reported Arabic models use morphs and stems; root and pattern are defined but not in Table 1. WSJ (Penn Treebank): 3-gram 258, 2-gram 320, GPB-FLM 2-grams 266–276. — [aclanthology.org/N03-2002](https://aclanthology.org/N03-2002.pdf) [measured by the authors]
- **Vergyri, Kirchhoff, Duh & Stolcke, Interspeech 2004.** LDC CallHome ECA, 120 conversations (≈180K words); dev 32K, eval97 18K, eval03 11K words; 18K-word recognition dictionary; stem and morph class from the CallHome lexicon, "a morphological analyzer [Darwish] to further decompose the stem into a root … and a pattern". Table 1 (dev perplexity): word bigram **229.9**, trigram **227.1**; FLM by manual search 229.6 / 223.2; random 229.9 / 230.3; genetic search **226.1 / 212.6** ("3 % (bigram) and 6 % (trigram) relative reductions"). Table 2 (eval03 trigram): word 123 → FLM **89**, but bigram 132 → **136** (worse). Table 3 WER: dev 53.9 → 52.6 (morph LMs for N-best rescoring) → **52.1** (FLM in all passes; −1.8 absolute); eval97 57.6 → 56.6 → 56.1 (−1.5); eval03 40.2 → 39.4 → 39.6. The RT-03 system's class-based and stream LMs over root, stem and morph class gave "word error rate reductions on the eval03 set of 0.8 % and 1.5 % (absolute)". — [isca-archive.org vergyri04_interspeech](https://www.isca-archive.org/interspeech_2004/vergyri04_interspeech.pdf) [measured by the authors]
- **Duh & Kirchhoff, COLING 2004 (automatic FLM structure learning by genetic algorithms).** Arabic CallHome ECA ≈170K / 32K / 18K words (train/dev/eval); factors Word, Stem, Root, Pattern, Morph ("the Arabic models made use of all conditioning variables"). Table 3 (OOVs scored as unknown): dev bigram word **236.0** → GA-FLM **193.3** (−18 % vs word, −1.1 % vs the best manual/random FLM); dev trigram **237.0 → 188.1** (−21 % vs word, −5.5 % vs best other FLM); eval bigram 235.2 → 233.4; eval trigram **253.9 → 212.2** (−16 % vs word, −3.1 % vs best other). Turkish (400K train words): dev trigram 534.9 → 444.5 (−17 %), eval 545.4 → 452.7. — [aclanthology.org/C04-1022](https://aclanthology.org/C04-1022.pdf) [measured by the authors]
- **Kirchhoff, Vergyri, Bilmes, Duh & Stolcke, Computer Speech & Language 20(4):589–608, 2006** (preprint at SRI). Data (Table 3): train 80 conversations, **146,298 words, 14 h**; dev 32,148; eval97 17,670; eval03 11,015; OOV ≈5 %. Table 8 (CallHome lexicon types / stream trigram perplexity): words 54,545 / 179; stems 37,325 / 125.3; morph classes 1,360 / 50.0; **roots 7,294 / 76.8; patterns 4,724 / 52.8** (streams not comparable to word perplexity). Root and pattern came from an MSA analyser, so "both the root and the pattern information are noisy" for ECA; "Arabic has approximately 5000 roots, several hundred patterns". Table 9 WER on dev by N-best rescoring: baseline **56.1**; + FLM **56.6** (worse); + morph stream 55.8; + stem stream 56.0; **+ root stream 56.0; + root class 56.0**; best combination (root + stem + morph streams + morph class) **55.6**; worst (morph class + stem class + root class) 57.2. Table 11 (GA FLM vs word): dev 2-gram 230.3 → 223.9 (−2.0 %), 3-gram 227.1 → 212.6 (−6.3 %); eval97 227.9 → 222.4 (−1.7 %), 222.3 → 208.4 (−6.3 %). Table 13: final WER 53.9 → 52.1 (dev), 57.6 → 56.1 (eval97), 40.2 → 39.6 (eval03); overall "1.8 % (dev), 1.5 % (eval97) and 0.6 % (eval03)" absolute; conclusion: "significant word error rate reductions on one evaluation set and … non-significant but consistent improvements on the other". — [SRI preprint PDF](https://sri.com/wp-content/uploads/2021/12/morphology-based_language_modeling_for.pdf); journal listing [sri.com](https://www.sri.com/publication/speech-natural-language-pubs/morphology-based-language-modeling-for-conversational-arabic-speech-recognition/) [measured by the authors]
- **Alexandrescu & Kirchhoff, HLT-NAACL 2006, "Factored Neural Language Models".** ECA 170K training words (|V| = 16,026), 32K dev, 17K eval97, OOV 8.5 % / 7.7 %; factors = stems and morphological tags from the LDC lexicon (Turkish: root, POS, case, …); d = 32–64, 45–64 hidden units, 362–1,024 output classes. Table 2 perplexity (no-unk / with-unk), ECA eval: baseline 3-gram **183 / 172**; word NLM 204 / 192; **factored NLM 190 / 175** (alone, no better than the n-gram); n-gram + word NLM 173 / 160; **n-gram + factored NLM 168 / 155** (−8 % / −10 %); n-gram + GA-FLM + FNLM **165 / 154**. Turkish (400K words): FNLM alone 1,249 / 832 vs n-gram 855 / 586 (much worse), interpolated 744 / 500 (−13 % / −15 %). Abstract: "significantly reduces perplexity on sparse-data tasks". — [aclanthology.org/N06-2001](https://aclanthology.org/N06-2001.pdf) [measured by the authors]
- **El-Desoky Mousa, Shaik, Schlüter & Ney, NAACL 2010 (hybrid decomposed FLMs, MSA LVCSR).** 206 million running words of LM text; 70k full-word vocabulary; MADA features: morph class M, lemma L, "P (Pattern): word after subtracting root" and a root feature. Table 1 perplexity: full-word baseline **302.6 → 290.9** (best FLM, −3.9 %); partially decomposed 284.1 → 279.1; fully decomposed 82.7 → 79.8. Table 2 WER (70k full words, FLM rescoring): **20.4 → 19.9**. Tables 3–4: 4-gram lattice rescoring 16.3 → N-best FLM 15.7 (dev07; −3.7 % rel); decomposed system 14.5 → 14.3. Abstract: "from 3.5 % to 7.0 % relative reduction in WER with respect to a traditional full-words system, and from 1.0 % to 2.0 % relative … with respect to a non-factored decomposed system". — [aclanthology.org/N10-1104](https://aclanthology.org/N10-1104.pdf) [measured by the authors]
- **El-Desoky Mousa et al., ICASSP 2012 (morpheme-level FLM vs stream/class LMs) and ICASSP 2013 (DNN morpheme-based feature-rich LM, Egyptian Arabic, "significant WER reductions … compared to the traditional word-based LMs").** Only abstracts were reachable; the tables are behind IEEE — numbers not obtained (Gap). — [ICASSP 2013 listing](https://researchr.org/publication/MousaKMS13/bibtex); [RWTH i6 publication 854](https://www-i6.informatik.rwth-aachen.de/publications/singlebibtex.php?id=854)
- **Sarikaya, Afify, Deng, Erdogan & Gao, IEEE TASLP 16(7):1330–1339, 2008 (JMLLM).** Iraqi Arabic, ≈200 h acoustic data; the units are morphological *segments* (prefix/stem/suffix by blind segmentation checked against Buckwalter), **not roots**; maximum-entropy joint model. Table II WER, complete corpus (460K sentences): word trigram **32.2**, morpheme trigram 31.3, JMLLM-leaf 30.5, JMLLM-tree 29.9, JMLLM-tree + word trigram **29.2** (−3.0 absolute, −9.3 % relative); half corpus (230K sentences): **38.7** → 37.7 → 35.9 (JMLLM-tree + morph) / 36.1 (+ word) — the absolute gain is the same or larger at half the data. MT (DevSet BLEU): morph trigram 29.74 → JMLLM-tree + word trigram 31.28. — [sarikaya08jml.pdf](https://research.sabanciuniv.edu/id/eprint/10259/1/sarikaya08jml.pdf) [measured by the authors]
- **El-Kishky, Fu, Addawood, Sobh, Voss & Han, WANLP 2019 (root extraction to enrich embeddings).** Arabic Wikipedia, 274K articles / 62.5M tokens for embeddings; LM = 3-layer LSTM, 600 units, dropout 0.2; LM-1 3.3M tokens (260K vocabulary), LM-2 7.6M tokens. Table 6 perplexity (LM-1 / LM-2): SkipGram **1757 / 1075**; **FastText 1720 / 1069**; root-enriched (CS2S-RootVec) **1726 / 1071**; root + template (CS2S-TemplaticVec) **1716 / 1065**. So root ids alone: −1.8 % vs SkipGram, **+0.3 % vs FastText's character n-grams**; root + template: −0.2 % / −0.4 % vs FastText. Authors: "morphemic decomposition is necessary to handle data-sparsity and OOV words when little training data is present". — [aclanthology.org/W19-4610](https://aclanthology.org/W19-4610.pdf) [measured by the authors]
- **Shah, Tarunesh & Jyothi, EMNLP 2019 (SEG-LM, factored *output* for Hindi/Tamil — the nearest Indic evidence; stems/suffixes, not roots).** Hindi 666,446 training tokens (vocab 50,384, OOV 5.3 %), Tamil 507,226 (vocab 106,403, OOV 15.2 %). Table 2 test perplexity: Hindi Char-CNN-LSTM 366.2, unsegmented NoSeg(2) **268.6**, Seg(2) 249.6, Seg(2)+BCE 248.4, Seg(3)+BCE+Embed **228.7** (−15 %); Tamil 1871.9 / **1197.8** / 952.4 / **815.7** (−32 %) / 921.8 / 894.0. — [EMNLP 2019 PDF](https://ys1998.github.io/research/emnlp2019.pdf) [measured by the authors]
- **Hatch & Richardson, ArabicNLP 2025 (Semitic Root Encoding tokenisation for NMT).** Root + template-stem + BPE tokens; "improves results by an average of 1.15 BLEU over the baseline" and avoids root–template combinations absent from the language; data and model sizes not in the abstract. — [aclanthology.org/2025.arabicnlp-main.3](https://aclanthology.org/2025.arabicnlp-main.3/)
- 2019–2026 neural Arabic/Urdu LMs with root or pattern *input factors* and a perplexity ablation: none found beyond El-Kishky 2019 (searches on root/pattern embeddings, templatic factors, Urdu morphology LMs; UrduLM 2026 is a 100M BPE model with no root factor — [arXiv 2601.17664](https://arxiv.org/html/2601.17664)). The tokeniser-level results (MorphBPE 2025, Morphemes Without Borders 2026) are in `tiny_language_model_on_cpu.md` KQ3 and are not repeated.

### Inferences
- **[inference] What the line proves and does not.** (i) At 150–170K words, morphology factors as a *bundle* with learned backoff are worth 2–6 % perplexity against an optimised word trigram and ~1–3 % relative WER; (ii) the FLM without parallel backoff, or with a bad structure, is *worse* than the baseline (Bilmes Table 1; Kirchhoff Table 9 "+FLM 56.6"); (iii) the only root-isolating number is Kirchhoff 2006 Table 9: root stream or root class alone, 56.1 → 56.0 WER (−0.1 absolute), i.e. indistinguishable from noise; (iv) the neural factored LM at 170K words beats a word NLM by ~3 % perplexity interpolated and is no better alone; (v) at millions of tokens, root features add nothing over character n-grams (El-Kishky Table 6). The honest expectation for Ruh's root/pattern slots is therefore **a few percent of perplexity at most, concentrated on the rooted words, in the data-sparse regime, and no gain against a byte/character model once data are enough** — exactly the shape the matched-compute arms below test.
- **[inference] Why the small-data gain is structural.** A root or pattern id shares statistics across all surface forms of a lexeme; this is a prior that helps when a form is rare and hurts (or is neutral) when the form itself is frequent enough to be estimated. Byte- and character-level models already share statistics across spellings, which is why El-Kishky's FastText baseline absorbed the root gain; Ruh v2 is byte-level, so the same absorption is expected.

### Gaps
- El-Desoky 2012/2013 tables (the only DNN morphological Arabic LM in the line) were not obtained.
- No study trains the same root-factored LM at several data sizes with a controlled ablation; "gains vanish with more data" is read off cross-study differences (ECA 170K vs MSA 206M vs El-Kishky 3–8M tokens with a character baseline), not from one curve.
- Kirchhoff 2006 Table 10 (first-pass FLM approximation) and the 2003 WSJ factor definitions were not extracted.

---

## KQ-B1. Matched-compute arms: bits per byte per language

### Takeaway
**Measured (30 Oct, corrected features, one seed).** At matched parameters (3.79M) and identical 12.0M tokens, **root/pattern tables do not pay for the feed-forward width they take**: arm B is 0.004 bpb *worse* than bytes-only pooled over the five languages, and worse than the run-to-run control on Urdu, Arabic and English. The gain they carry is real but local: on Urdu bytes inside a word with a root, B is 0.040 bpb better than A (1.562 vs 1.601) and C 0.091 better (1.510), while Arabic rooted bytes gain nothing in B (1.716 vs 1.706), because an Arabic word's letters already spell its root and the channel is redundant there; in Urdu it is a bridge from Arabic. Arm C (root/pattern + a *proxy* concept table of strings shared by the Urdu and Arabic, or English and Roman-Urdu, training text) is 0.0145 bpb better than A pooled, and the only gain that survives Hindi as a negative control (Hindi bytes carry no ids in any arm) is **Urdu, −0.013 bpb (≈0.8 %)**. Decision for KQ-B5: no root/pattern slots in Ruh's LM at this scale; a *verified* cross-lingual concept slot (Qāmūs) is the one channel worth a properly seeded test, and roots stay in Sarf, Fihris and the lexicon.

### Cited Findings
- **[measured]** Matched configurations by exact count: A `d_ff=1271` 3,794,396; B `d_ff=1157` + root (1,647+1)×64 + wazn (1,509+1)×64 + two 64→256 projections, 3,795,348; C `d_ff=1024` + the same + concept (4,000+1)×64, 3,794,880. Factor ids are looked up per word and added to every byte of the word (id 0 is the exact zero vector); arm A never reads the factor arrays.
- **[measured]** Throughput on an idle machine, 2 threads, batch 32 × 256: **6,185 tok/s** (arm C, 4 layers), **3,897 tok/s** (6 layers, 5.37M params); RSS 1.33–1.37 GB with all data in memory, ≈1.2 GB anonymous with memory-mapped data. At 2 threads the 12M-token budget is **32 min of CPU** per arm (16M would be 43 min); tokens/parameter = 3.2 (12M) — far below Chinchilla's 20, which E1 showed needs days of background training at this size.
- **[measured]** Under contention (three arms, one thread each, sharing 4 cores with a sibling 4-thread job) each arm ran at 1,600–2,700 tok/s.
- **[measured]** Held-out bits per byte, 1,000-resample document bootstrap 95 % intervals (`results/bpb_A.json`, `bpb_B_regen.json`, `bpb_C_regen.json`; arm A re-scored as `bpb_A_regen.json` with identical totals):

| Arm | params | ur | ar | hi | en | hi-latn | mean |
|---|---|---|---|---|---|---|---|
| A bytes | 3,794,396 | 1.609 [1.584, 1.632] | 1.703 [1.671, 1.739] | 1.209 [1.193, 1.227] | 2.410 [2.343, 2.477] | 2.010 [1.931, 2.090] | 1.788 |
| B + root/pattern | 3,795,348 | 1.611 [1.585, 1.634] | 1.715 [1.684, 1.751] | 1.204 [1.187, 1.221] | 2.417 [2.350, 2.484] | 2.025 [1.948, 2.096] | 1.794 |
| C + root/pattern/concept | 3,794,880 | 1.581 [1.554, 1.604] | 1.694 [1.662, 1.730] | 1.195 [1.178, 1.212] | 2.403 [2.336, 2.469] | 2.019 [1.937, 2.101] | 1.778 |

- **[measured]** Paired per-document differences (same held-out documents, 5,000 resamples; negative = better than the first arm): B − A: ur +0.002 [−0.001, +0.005], ar **+0.012** [+0.010, +0.014], hi −0.006 [−0.008, −0.004], en +0.007 [+0.004, +0.011], hi-latn +0.015 [−0.007, +0.038]; pooled **+0.0039** [+0.0023, +0.0055]. C − A: ur **−0.028** [−0.031, −0.025], ar −0.008 [−0.011, −0.006], hi −0.015 [−0.017, −0.013], en −0.007 [−0.011, −0.004], hi-latn +0.009 [−0.017, +0.035]; pooled **−0.0145** [−0.0162, −0.0128]. C − B pooled −0.0184 [−0.0201, −0.0167].
- **[measured]** Hindi as negative control: Devanagari bytes carry no factor id in any arm, so the Hindi difference measures what changes between runs for reasons other than the channel (different d_ff, different optimisation path). Difference-in-differences (arm − A on language L minus arm − A on Hindi): B: ur +0.0076 [+0.0039, +0.0114], ar +0.0183 [+0.0155, +0.0210], en +0.0129 [+0.0090, +0.0169]; C: ur **−0.0133** [−0.0172, −0.0095], ar +0.0062 [+0.0026, +0.0098], en +0.0073 [+0.0030, +0.0113].
- **[measured]** Bytes inside a word with a root vs without (point estimates; per-document rooted totals were not saved, so no interval): Urdu rooted A 1.601 / B **1.562** / C **1.510**, Urdu unrooted 1.610 / 1.615 / 1.588; Arabic rooted 1.706 / 1.716 / 1.690, Arabic unrooted 1.701 / 1.715 / 1.695.
- **[measured]** Training: both reruns 1,465 steps from scratch on corrected factor ids (the character→byte offset bug fixed in `data_prep.py`), 2 threads each, 09:05–10:10 UTC (≈65 min wall under contention with a canary job).

### Inferences
- **[inference]** The root channel's information is real but small and local: it lowers Urdu rooted-byte cost by 2.5–5.7 % and leaves Arabic (where the root is already in the letters) unchanged. Spread over all bytes it cannot repay the 9–19 % of feed-forward width the tables displace at a fixed parameter budget; this is the factored-LM literature's result (the root stream alone moved WER by 0.1 point; root-enriched embeddings within 0.4 % of character n-grams) reproduced at MIZAN's scale.
- **[inference]** The concept proxy helps Urdu beyond the Hindi control (−0.013 bpb) but not Arabic or English: a shared-string id lets Urdu borrow what the model learned about the same loan word in Arabic text, the "bridge" role the Larkey test (KQ-B4) found for cross-lingual Fihris retrieval. The proxy is a loan-word detector, not a sense inventory; a verified Qāmūs concept id is the version worth testing.
- **[inference]** One seed. The Hindi control moved 0.006–0.015 bpb between arms with no channel at all, so run-to-run variation is of the same order as every effect here except C's Urdu gain; a decision to put any slot into production Ruh needs ≥2 seeds and the e-value gate on a frozen held-out set.

### Gaps
- One seed per arm; per-document rooted/unrooted totals were not saved (point estimates only for that split).
- 12M tokens is 3.2 tokens/parameter; the plan's 16M budget was cut when a sibling job took 1.5 cores. A Chinchilla-scale comparison (76M tokens) would need ~3.4 h per arm at 2 threads and was out of session reach.

---

## KQ-B2. MASSIVE intent probe: full data, ≤100 per intent, cross-lingual transfer, e-value gate

### Takeaway
NOT RUN in this session (the feature export and probe were scheduled after the arms; the container restart at ≈08:20 UTC and the arms' rerun used the session's time). Not needed for the KQ-B5 decision; the protocol below stands for a later run.

### Cited Findings
- Method **[measured, protocol]**: mean-pooled final-layer states (256-d) of each utterance (BOS + UTF-8 bytes + EOS, with each arm's own factor ids), standardised, multinomial logistic regression (scikit-learn, C = 1, lbfgs), trained on the official MASSIVE train split (11,514) or on ≤100 utterances per intent (seeded sample), tested on the official test split (2,974). Transfer: train ur-PK test ar-SA and the reverse, plus hi-IN→ur-PK and en-US→ur-PK. Intervals: Wilson 95 %. Decision rule: MIZAN's `core.adaptive.paired_e_value(wins, losses)` over discordant test items (B right & A wrong vs A right & B wrong), crossing 1/α = 20 at α = 0.05 (anytime-valid by Ville); McNemar exact binomial p as the fixed-n check.
- No table: not run.

### Inferences
- None drawn.

### Gaps
- The whole key question remains open.

---

## KQ-B3. Production baseline on the same splits: Tamyiz hashed char n-gram naive Bayes (closes gap C3)

### Takeaway
NOT RUN in this session (the feature export and probe were scheduled after the arms; the container restart at ≈08:20 UTC and the arms' rerun used the session's time). Not needed for the KQ-B5 decision; the protocol below stands for a later run.

### Cited Findings
- Method **[measured, protocol]**: `backend/core/tamyiz.Tamyiz` with Qasd's featurisation (character 2–4-grams of the letters + `w:` words, log(1+n) counts), `fit(calibrate=True, sample=1500)` (leave-one-out fitted α, weights, γ), trained on exactly the same train / ≤100-per-intent subsets, predicted on the same test utterances, and paired against arm A with the same e-value.
- No table: not run.

### Inferences
- None drawn.

### Gaps
- The whole key question remains open.

---

## KQ-B4. Larkey-style precision test: surface words vs root ids vs root+pattern ids on MIZAN's retrieval paths

### Takeaway
On MIZAN's own paths the Quranic-form table is a *light* conflator (mean class size 1.02–1.09 against Khoja's 262 in Larkey 2002), so Larkey's precision loss does not appear: monolingual MASSIVE retrieval is unchanged to ±0.5 points, cross-lingual Fihris retrieval (Urdu translation → Arabic ayah) **doubles** with root ids (P@10 6.5 → 13.3 %, MRR 0.029 → 0.068) because shared roots are the only bridge, and the Dhikr `about()` recall path returns more statements at equal top-5 precision. Pattern ids restrict the conflation (class 1.59 vs 3.77) and give back half of the cross-lingual gain, so (c) sits between (a) and (b), not above (b).

### Cited Findings
All **[measured]**, `larkey.py`, `results/larkey.json`; BM25 is `core.adaptive.bm25_scores` (k₁ = 1.5, b = 0.75, the constants Fihris uses); words are `tadbir.fihris.words`; root/pattern keys from the same Quranic-form lookup as the arms; 400 random test queries per set, seed 3.
- **MASSIVE ur-PK** (documents = 11,514 train utterances, relevant = same intent): surface MAP 0.1995, P@5 0.612, interpolated precision at recall 0.05/0.10/0.25 = 0.525/0.429/0.289; **root** 0.1999, 0.613, 0.526/0.431/0.290; **root+pattern** 0.1994, 0.612, 0.525/0.429/0.289. Class size (distinct surface forms per index term): surface 1.00 (5,440 terms); root 1.015 (max 6; 1.0 % of terms conflate, mean 2.5 forms each); root+pattern 1.004 (max 3).
- **MASSIVE ar-SA**: surface MAP 0.1719, P@5 0.565, P@R 0.499/0.400/0.249; **root** 0.1733, 0.570, 0.502/0.397/0.255; **root+pattern** 0.1734, 0.565, 0.501/0.400/0.254. Class size: root 1.088 (max 22; 2.9 % of terms conflate, mean 4.1 forms); root+pattern 1.041 (max 8).
- **Fihris cross-lingual** (query = Jalandhry Urdu translation of an ayah, documents = 6,236 `quran-simple-clean` ayahs, relevant = that ayah): surface **MRR 0.029, P@1 1.5 %, P@10 6.5 %**; **root MRR 0.068, P@1 3.75 %, P@10 13.3 %**; root+pattern MRR 0.046, P@1 2.75 %, P@10 9.3 %. Class sizes over the Arabic ayah vocabulary: surface 14,650 terms; root **3,887 terms, mean 3.77 forms per term, max 106, 27 % of terms conflate (mean 11.1 forms)**; root+pattern 9,210 terms, mean 1.59, max 40.
- **Dhikr `memory.dhikr.about`** (stored statements = train utterances, query = test utterance, relevant = same intent; 300 queries): ur-PK surface P@5 0.518, recall of same-intent statements 0.055, 59.8 statements returned, 11.7 % of queries recall nothing; **root-mapped text P@5 0.526, recall 0.065, 73.4 returned, 7.7 % nothing**. ar-SA surface P@5 0.465, recall 0.029, 18.2 returned, 28.3 % nothing; **root P@5 0.488, recall 0.056, 67.6 returned, 16.0 % nothing**.
- Reference point (not re-fetched): Larkey, Ballesteros & Connell 2002 found Khoja root classes of 262 forms on average (max 929) against 22 for light8-s and average precision .341 vs .389 — in `failure_modes_honest_ceilings_measurement.md` KQ3.

### Inferences
- **[inference]** Larkey's prediction (b) < (a) assumed an aggressive root stemmer. A Quranic-form table with a clitic cascade conflates 1–3 % of chat terms and 27 % of the Quranic vocabulary; the precision cost is therefore invisible in chat retrieval and real but tolerable in Quran retrieval, where it is outweighed by the recall it creates across languages. The pattern slot behaves as the "light" disambiguator Larkey found useful: it halves the class size and gives up half the cross-lingual recall.
- **[inference]** The absolute cross-lingual numbers (P@10 13 %) say what a root bridge can and cannot do: with ~9 % of Urdu tokens rooted, roots alone cannot find the ayah from its translation; they are a recall expander for Fihris's existing views (which already search the Urdu edition directly), not a replacement.
- **[inference]** For Dhikr, root mapping is a safe recall expansion (more statements, equal top-5 precision, fewer empty recalls), consistent with the design rule "roots expand, surface decides".

### Gaps
- Fihris's own `Index` (standardised, mixed BM25 across five views with topic weights) was not modified; the test used the same scorer and word normaliser outside the index. A run through `fihris.Index.search` with a root view added is the production-faithful follow-up.
- Only Quranic-form roots were tested; a CAMeL r13 root analyser (≈4× the coverage) would conflate more and could show Larkey's loss.

---

## KQ-B5. Decision: root/pattern slots in Ruh, or roots confined to Sarf/Fihris/Qāmūs alignment? Which representation where?

### Takeaway
**Roots stay out of Ruh's language model at this scale; they serve Sarf, Fihris, Dhikr recall and the Qāmūs lexicon. A verified concept slot is the one channel worth a seeded test.** Matched-parameter arm B (root/pattern tables) was 0.004 bpb worse than bytes only pooled and worse than the Hindi control on Urdu, Arabic and English (KQ-B1); its gain is confined to Urdu rooted bytes (−0.040). Arm C's shared-string concept proxy gave the only effect that survives the control (Urdu −0.013 bpb). Retrieval needs roots as an *expander* (cross-lingual Fihris P@10 6.5 % → 13.3 %, KQ-B4), not as the meaning space. The MASSIVE probe (KQ-B2) and the Tamyiz baseline on the same splits (KQ-B3) were not run in this session and are not needed for this decision.

### Cited Findings
- **[measured]** KQ-B1 tables above (pooled B − A +0.0039 [+0.0023, +0.0055]; C − A −0.0145 [−0.0162, −0.0128]; Urdu C − A minus Hindi C − A −0.0133 [−0.0172, −0.0095]).
- **[measured]** KQ-B4: monolingual MASSIVE MAP unchanged by roots (ur-PK 0.1995 → 0.1999); cross-lingual Fihris P@10 doubled; Dhikr empty recalls 28.3 % → 16.0 % on ar-SA.
- **[measured]** Coordinator's pilot (0.86M, Lughah seeds, two seeds): root channel −0.035/−0.040 bpb on word forms unseen in training where a per-form id channel was worse than none — the channel's value is transfer to unseen forms, again local.

### Inferences
- **[inference, provisional]** On representation: the two sibling notes propose different objects because they serve different operations. Binary HD/VSA binding (`neuroscience_memory_and_cpu_models.md` Q2–Q4) is the right object for **memory keys**: XOR-bind root⊗pattern per word, bundle a sentence, compare by Hamming — writes are µs, reads are a single pass, composition is exact and the key is independent of any trained weights (so Mahw can erase it and Tadhkir can age it). Dense additive embeddings (`root_space_interlingua.md` KQ4 §9) are the right object **inside the LM**: the model must differentiate through them, they are 13 MB of tables, and the arms here are exactly that design. The final report should therefore say: *one lexicon (Qāmūs ids), two encodings* — HD binding for the episodic/kNN keys, dense additive slots for Ruh's input — and should not ask the LM to read HD vectors or the memory to read dense weights.

### Gaps
- Single seed; the falsifier stated in the report (arm C must beat A on ur→ar transfer with a sahih lexicon covering ≥20 % of tokens) needs a real Qāmūs and ≥2 seeds.

---

## KQ-C1. Decode speed with a KV cache (2 threads, fp32 and int8, contexts 128/384/1024, Arabic/Urdu bytes)

### Takeaway
With a KV cache a 5M-parameter byte model decodes at 4–8 ms per byte on 2 threads, a 15M one at 7–11 ms, and a 46M-parameter dense model at 13–19 ms (fp32) or 9–15 ms (int8 dynamic quantisation): a 300-byte Urdu reply at a 384-byte context takes **1.3–1.5 s (5M), 2.4–2.7 s (15M), 4.8 s fp32 / 3.2 s int8 (46M)**, against the audit's ≈90 s without a cache; int8 pays only at 46M (×1.5), not at 5–15M.

### Cited Findings
All **[measured]**, `kv_bench.py`, `results/kv_bench.json`, idle machine, `torch.set_num_threads(2)`, greedy decoding of 48 new bytes after the prompt, 5 repeats for the no-cache forward; shapes: 5M = 256-d × 6 layers (4,865,024 params), 15M = 384-d × 8 (14,382,336), 46M = 512-d × 8 dense with d_ff widened to 45,992,504 params (the Ruh default is 45,985,563 with MoE blocks; this is its dense equal-parameter stand-in, so its FLOPs per token are ≈1.4× Ruh's top-2-of-4 active 33.4M). Values below are the mean of the Urdu and Arabic streams (they differ by <10 %).

| params | precision | ctx | prefill ms | cached ms/byte | no-cache ms/byte at ctx+48 | 300-byte reply s (prefill + 300 steps) |
|---|---|---|---|---|---|---|
| 4.87M | fp32 | 128 / 384 / 1024 | 18 / 82 / 133 | 6.1 / 4.4 / 6.4 | 28 / 49 / 130 | 1.8 / 1.4 / 2.1 |
| 4.87M | int8 | 128 / 384 / 1024 | 32 / 59 / 110 | 3.8 / 4.4 / 6.3 | 19 / 49 / 108 | 1.2 / 1.4 / 2.0 |
| 14.4M | fp32 | 128 / 384 / 1024 | 40 / 98 / 246 | 7.8 / 8.4 / 10.7 | 50 / 107 / 268 | 2.4 / 2.6 / 3.5 |
| 14.4M | int8 | 128 / 384 / 1024 | 28 / 61 / 191 | 6.3 / 7.2 / 12.3 | 30 / 84 / 199 | 1.9 / 2.2 / 3.9 |
| 46.0M | fp32 | 128 / 384 / 1024 | 87 / 230 / 574 | 13.6 / 15.2 / 19.0 | 112 / 259 / 710 | 4.2 / 4.8 / 6.3 |
| 46.0M | int8 | 128 / 384 / 1024 | 53 / 129 / 367 | 9.2 / 10.1 / 14.8 | 74 / 167 / 500 | 2.8 / 3.2 / 4.8 |

- Peak RSS: 405 MB (5M), 452 MB (15M), 757 MB (46M incl. the int8 copy).
- Comparison with E1 (no cache, ctx 64, 2 threads): 5.43M 16.8 ms per extra byte, 46M 81.7 ms; with E1's forward numbers scaling ∝ context, the audit's "≈90 s for a 300-byte reply at full context" becomes **4.8 s** (46M fp32, ctx 384) here — the cache turns per-byte cost from O(context) into near-constant (13.6 → 19.0 ms from 128 to 1024 bytes of context at 46M).
- Comparison with `tiny_language_model_on_cpu.md` KQ2's estimate ("≥150 tok/s at ≤30M with a ggml-style runtime, 40–60 tok/s at 125M"): measured here in plain PyTorch, **160–230 bytes/s at 5M, 90–130 at 15M, 53–74 at 46M fp32 (68–110 int8)**; the estimate holds for 5M and is ~2× optimistic for 15M in PyTorch (a ggml/ONNX runtime remains the untested lever).

### Inferences
- **[estimated]** Bytes per character: 2 for Arabic/Urdu script, so a 300-byte reply is ≈150 characters ≈ 25–30 Urdu words; a 600-byte (two-sentence) reply doubles the step term: 2.6 s (5M), 5 s (15M), 9.3 s (46M fp32). Interactive use on the production CPU is therefore realistic for ≤15M parameters and marginal for 46M without int8 or a faster runtime.
- **[inference]** Dynamic int8 quantises only `nn.Linear`; at 5M the per-step cost is dominated by framework overhead (≈4 ms regardless of precision), so quantisation buys nothing — the lever there is fewer Python-level ops (ONNX/ggml export), not smaller weights.
- **[inference]** Prefill grows linearly (5M: 18 → 133 ms from 128 to 1024 bytes), so re-reading a long chat history each turn costs more than the reply; the KV cache should persist across turns of one chat (the state-as-memory point in the neuroscience note).

### Gaps
- Ruh's actual Qalb attention (ψ-modulated scale with a causal prefix-mean complexity term) and the MoE blocks were not ported to a cached implementation; the 46M figure is a dense stand-in. ONNX Runtime and ggml paths were not measured.
- Timings at 5M vary ±30 % between runs (sub-10-ms steps on a shared VM); the 15M and 46M numbers are stable to ±10 %.

---

## KQ-C2. Nightly continual learning at this size: forgetting under (a) nothing, (b) replay 5 % / 25 %, (c) EWC, (d) replay + EWC

### Takeaway
**25 % replay gives zero forgetting on CPU; EWC alone does not.** Measured results are in the coordinator's addendum at the end of this note (read from `results/cl_*.json`): naive ACC 7.91 bpb / BWT +8.68 (Urdu 2.36 → 11.82, worse than random initialisation at 8.16); EWC λ = 2,000 ACC 6.59 / BWT +6.72; replay 5 % ACC 2.23 / BWT +0.19; **replay 25 % ACC 2.09 / BWT −0.005**; replay 5 % + EWC ACC 2.23 / BWT +0.18; one night ≈215–230 CPU-s.

### Cited Findings
- Method **[measured, protocol]**: arm A's architecture (3.79M) trained from random initialisation on three "weeks" in sequence — week 1 Urdu, week 2 Arabic, week 3 Hindi web text — 0.66M tokens per week (80 steps × 32 × 256; the budget the session allowed), lr 1e-3 cosine per week, probes = the first 120 KB of each language's held-out set. Replay = reservoir sample (Vitter, capacity 2,000 windows) of past weeks mixed into each batch at 5 % or 25 %; EWC = diagonal Fisher from 8 batches of the finished week, penalty ½·λ·Σ F_i(θ_i − θ*_i)² with λ = 2,000, one anchor per finished week. Metrics in BPB (lower is better): R_ij = BPB on probe j after week i; ACC = mean of the last row; BWT = mean_j<T (R_Tj − R_jj) (> 0 is forgetting); FWT = mean_j>1 (R_{j−1,j} − b_j) with b_j the random-init BPB (< 0 is positive transfer); Chaudhry forgetting f_j = R_Tj − min_{l≤T−1} R_lj. Definitions follow GEM (Lopez-Paz & Ranzato, NeurIPS 2017, [arXiv 1706.08840](https://arxiv.org/abs/1706.08840)) and Riemannian Walk (Chaudhry et al., ECCV 2018, [arXiv 1801.10112](https://arxiv.org/abs/1801.10112)) with accuracy replaced by −BPB.
- R matrices: `results/cl_{naive,ewc,replay05,replay25,replay05_ewc}.json`; summarised in the coordinator's addendum.

### Inferences
- See the coordinator's addendum: the fast store must feed the slow store by interleaved replay; a weight-change penalty is not a substitute.

### Gaps
- One seed per regime; three weeks only; Hindi in week 3 means its own forgetting is not measured.

---

## KQ-C3. kNN datastore over arm A's hidden states: does a small datastore help at all?

### Takeaway
NOT MEASURED beyond the smoke test below (the full datastore run was scheduled after the arms and did not run). The smoke test is a function check, not a result.

### Cited Findings
- Method **[measured, protocol]**: one (fp16 256-d key, next-byte value) per held-in training byte (equal share per language), brute-force exact k = 64 search on 2 threads (torch matmul, no FAISS), per-query temperature = mean kNN distance, p = λ·p_kNN + (1−λ)·p_LM, λ ∈ {0, 0.1, 0.25, 0.5}, evaluated on 60 KB of held-out text per language (second half of 256-byte windows).
- Smoke test on an under-trained checkpoint (41 steps, 40K-token store): BPB ur 3.40 → 2.84 at λ = 0.5, read 0.55 ms/query, 21 MB — only a function check; the real numbers were not obtained.

### Inferences
- None drawn beyond feasibility (read 0.55 ms/query, 21 MB for 40K tokens).

### Gaps
- Whether a datastore over verified text helps a trained 3.8M model is open.

---

## Every number in one table (tagged)

See KQ-B1 (arms table and paired differences), KQ-B4 (Larkey), KQ-C1 (KV cache) and the coordinator's addendum (continual learning). KQ-B2, KQ-B3 and KQ-C3 were not run.

## What the final report may and may not claim about Ruh

May claim (measured, one seed unless stated): at 3.79M parameters and 12M tokens, root/pattern slots do not improve bits per byte at matched parameters (pooled +0.004) and help only Urdu rooted bytes; a shared-string concept proxy helps Urdu by 0.013 bpb beyond the Hindi control; 25 % replay prevents forgetting where EWC alone fails; a KV cache makes 5–15M models interactive (1.4–2.6 s per 300-byte reply). May not claim: that roots or a concept channel improve intent understanding (KQ-B2 not run), that Ruh beats Tamyiz (KQ-B3 not run), that a kNN datastore helps (KQ-C3 not run), or any result at Chinchilla scale.


---

## Coordinator's addendum (30 Oct 2026, 07:30 UTC): what the arm runs delivered before the workflow was stopped

The researcher agent that wrote this note kept running experiments after saving it; the coordinator stopped the workflow at 07:13 UTC. These are the results found on disk, read directly from `results/*.json` and `results/*.log`, with the researcher's own last actions taken into account.

### KQ-B1 outcome: first-pass B/C numbers are **quarantined** (data leak), rerun in progress

- Arm **A** (bytes only, 3,794,396 params, 12,001,280 tokens, 1,465 steps, 97 min on one contended thread at ≈2,050 tok/s) finished and was scored on the held-out documents (`results/bpb_A.json`, 1,000-resample document bootstrap 95 % CI): **ur 1.609 [1.584, 1.632] · ar 1.703 [1.671, 1.739] · hi 1.209 [1.193, 1.227] · en 2.410 [2.343, 2.477] · hi-latn 2.010 [1.931, 2.090]** bits per byte. Within Urdu, bytes inside words with a Quranic-form root score 1.695 and other bytes 1.602; within Arabic 1.588 vs 1.728.
- Arms **B** (root/pattern channel) and **C** (root/pattern/concept channel) also finished, but at 07:00 UTC the researcher found a bug in `scripts/data_prep.py`'s character→byte offset bookkeeping for the per-byte factor ids of Urdu and Arabic, fixed it, regenerated `data/processed`, **moved the B/C models and scores to `results/leaky/`** and relaunched both arms on the corrected features (`scripts/launch_bc.sh`, 07:03). Those reruns had reached step ≈100 of 1,465 when the workflow was stopped. The quarantined first-pass scores (B: ur 1.49, ar 1.47; C: ur 1.26, ar 1.36, hi-latn 1.73) are therefore **not evidence**: a misaligned factor id can carry information about the following bytes. They are recorded here only so nobody mistakes them for results later.
- Arm A does not read the factor arrays, so its scores stand; its `bpb_A_regen` rescoring differs only in the rooted/unrooted split.
- The coordinator's independent 1M-parameter pilot (`experiment_root_channel_pilot.md`), which computes factor ids per character and then expands to bytes, found a consistent but small effect in the same direction (Arabic-script −0.14/−0.15 bpb, unseen word forms −0.035/−0.040, two seeds). The matched-parameter B/C rerun is what should decide the question; it is being relaunched by the coordinator.

### KQ-C2 outcome: nightly continual learning — replay is what works

Arm A's architecture (3.79M), trained from random initialisation on three sequential "weeks" (Urdu → Arabic → Hindi web text, 0.66M tokens each, 80 steps × 32 × 256, lr 1e-3 cosine per week), probes = the first 120 KB of each language's held-out set; `results/cl_*.json`. R[i][j] = bpb on probe j after week i; the table shows the final row (after week 3), the mean final bpb over the three probes (ACC), backward transfer (BWT; negative = no forgetting), forward transfer to the not-yet-seen language (FWT) and the CPU cost of one night.

| Variant | Final bpb ur / ar / hi | ACC (mean) | BWT | FWT | CPU-s per night |
|---|---|---|---|---|---|
| nothing | 11.82 / 10.11 / 1.79 | 7.91 | +8.68 | 1.78 | 217 |
| EWC λ=2000 | 9.47 / 8.53 / 1.76 | 6.59 | +6.72 | 1.69 | 221 |
| replay 5 % | 2.51 / 2.43 / 1.74 | 2.23 | +0.19 | 1.82 | 217 |
| replay 25 % | 2.29 / 2.28 / 1.71 | 2.09 | -0.00 | 1.75 | 219 |
| replay 5 % + EWC | 2.50 / 2.41 / 1.78 | 2.23 | +0.18 | 1.99 | 224 |

Reading:
- With nothing, each new week **destroys** the previous languages (Urdu 2.36 → 11.8 bpb after two more weeks; random-init is 8.1): catastrophic forgetting is total at this size.
- **EWC alone does not hold it** (λ = 2000: Urdu still 9.5 bpb).
- **Replay does**: a reservoir sample of past weeks mixed at 5 % of each batch keeps Urdu at 2.51 and Arabic at 2.43 after the Hindi week (forgetting 0.14 / 0.24 bpb); at **25 % replay there is no forgetting at all** (BWT −0.005, Urdu 2.29 after week 3 against 2.36 right after its own week) and the mean is the best of all variants (2.09). Adding EWC on top of replay changes nothing (2.23 vs 2.23).
- Cost: one "night" of 0.66M tokens is **≈215–230 CPU-seconds** (≈4 min of one core) at 3.8M parameters, so a nightly consolidation of a day's text with 25 % replay from the archive is well inside the production budget.
- This is the complementary-learning-systems result at MIZAN's scale: the fast store (the archive the reservoir samples from) must feed the slow store (the weights) by interleaved replay; a penalty on weight change (EWC) is not a substitute. "Nothing omitted" (18:49) is what makes replay possible: the episodic record must be kept so that it can be re-read.

### KQ-C1 (KV cache) and KQ-B4 (Larkey test) are unaffected by the leak

Their inputs are word-level lookups and timing, not the per-byte factor arrays; their sections above stand.
