# Real-time learning from sources when the agent does not know: asking, verifying, keeping with provenance, reusing (state of the art, October 2026)

Scope: methods and the mathematics behind them for MIZAN's "Ahl al-Dhikr" (Quran 16:43) path, buildable on CPU with small models plus a hosted LLM used only for wording. Current MIZAN behaviour (from `docs/ahl-dhikr.md`, read 2026-10-28): when Qasd's facet is `fact` and an answer is the model's own words, each da'if claim is asked of (1) the user's `ilm` (up to 300 settled sentences, most recently used first, no expiry), then (2) Wikipedia and a web search in a Thompson-sampled order (a Beta posterior per source of "settling a claim when asked"), within 20 s. BM25 picks sentences, a relevance gate keeps a sentence only if it holds more than half of the claim's above-mean IDF information, the multilingual MiniLMv2 NLI model gives a MAP verdict (contradiction only if it holds both ways), and one decisive sentence settles the claim. Deen questions are only checked against the user's own `ilm`. The gaps this research points to are flagged under "Inferences" in each section.

## 1. Knowing when you do not know (calibration, selective prediction, conformal prediction, semantic entropy, self-consistency), so the agent decides to ask

### Takeaway
Semantic entropy (Nature, June 2024), the best-studied black-box signal, clusters sampled answers by bidirectional entailment and takes the entropy over meanings. It reached a mean AUROC of 0.790 against 0.69 for naive entropy and P(True), but it needs 5 to 10 samples. Conformal factuality (ICML 2024) turns any claim score into a guarantee of the form "at least 1−α correct" by dropping the least-certain sub-claims, using only a small labelled calibration set. A 2025 study of 35 adaptive-retrieval methods found that cheap uncertainty estimators match complex "should I retrieve?" pipelines. MIZAN already runs a CPU NLI model, so it can compute discrete semantic entropy and conformal thresholds itself. The hosted LLM is needed only to produce the samples.

### Cited Findings
- **Semantic entropy (SE).** Farquhar, Kossen, Kuhn and Gal, *Nature*, published 19 June 2024. SE detects "confabulations" (arbitrary, incorrect generations) by computing entropy "at the level of meaning rather than specific sequences of words". Sampled answers are grouped when they are semantically equivalent, judged by entailment. — [Nature](https://www.nature.com/articles/s41586-024-07421-0)
- SE results. Averaged over 30 task×model combinations, SE reaches AUROC 0.790, against naive entropy 0.691, P(True) 0.698 and embedding regression 0.687. It stays between 0.78 and 0.81 across LLaMA, Falcon and Mistral at 7B to 70B, using ten generations per question. The paper also reports AURAC (area under the "rejection accuracy" curve), which measures the accuracy gained by refusing the highest-entropy questions. — [Nature](https://www.nature.com/articles/s41586-024-07421-0)
- SE limits. It targets arbitrary errors, not "consistent errors learned from the training data". For paragraph-length GPT-4 biographies, the discrete SE variant beats P(True) until about 20% of questions are rejected, after which P(True) "has a narrow edge". — [Nature](https://www.nature.com/articles/s41586-024-07421-0)
- Entailment model ablation (Supplementary Table 3, 8 generations, LLaMA-2-70B answers). Average AUROC is 0.78 with a purpose-built DeBERTa NLI model, 0.83 with GPT-3.5 as the entailment judge, 0.80 with GPT-4 and 0.71 with LLaMA-2-70B. A small NLI model is therefore only about 0.05 AUROC below a prompted LLM judge. For short phrases, over 60 combinations: SE 0.792, discrete SE 0.790, naive entropy 0.760. — [Oxford ORA supplementary](https://ora.ox.ac.uk/objects/uuid:0653d09e-9368-4eb1-98bb-50d9dda7d3e5/files/r0g354g31t)
- **Semantic entropy probes (SEPs).** Kossen et al., June 2024. SE costs 5 to 10 times the compute of one answer. SEPs approximate SE "from the hidden states of a single generation", bring the overhead to "almost zero", and generalise out of distribution better than probes that predict accuracy directly. They need white-box hidden states. — [arXiv 2406.15927](https://arxiv.org/abs/2406.15927)
- **Conformal factuality.** Mohri and Hashimoto, ICML 2024, arXiv Feb 2024. The "uncertainty set" of an output is the set of statements that entail it, so conformal prediction becomes a back-off algorithm: drop sub-claims whose score is below a threshold t. The threshold q̂_α is the ⌈(n+1)(1−α)⌉/n quantile of the calibration scores, which gives P(output correct) ≥ 1−α under exchangeability (Theorem 4.1), with an upper bound of 1−α+1/(n+1) under nesting. On GPT-4 outputs, correctness rose from 30% to 80% on FActScore, 78% to 93% on NaturalQuestions and 75% to 95% on MATH, while most sub-claims were kept. It "requires very few human-annotated samples". — [arXiv 2402.10978](https://arxiv.org/html/2402.10978); [PMLR](https://proceedings.mlr.press/v235/mohri24a.html)
- Conformal factuality limits: the guarantee is marginal, not conditional. It holds on average over inputs, so a single user or domain can differ. It is also marginal over the draw of the calibration set and breaks under distribution shift. — [arXiv 2402.10978](https://arxiv.org/html/2402.10978)
- **Adaptive retrieval (deciding when to ask).** Moskvoretskii et al., ACL 2025, compared 35 methods (8 adaptive-retrieval pipelines and 27 uncertainty estimators) on 6 datasets with 10 metrics. "Uncertainty estimation techniques often outperform complex pipelines in terms of efficiency and self-knowledge, while maintaining comparable QA performance." Other findings:
  - DRAGIN leads on downstream QA but has near-random self-knowledge.
  - SeaKR (internal states) is good on single-hop questions; AdaptiveRAG is better on multi-hop.
  - Consistency-based estimators are best for QA; logit-based estimators are best for self-knowledge.
  - A hybrid of all estimators ranks first for efficiency but costs more compute.

  — [arXiv 2501.12835](https://arxiv.org/html/2501.12835v2); [ACL Anthology](https://aclanthology.org/2025.acl-long.319.pdf)
- **LLM-independent adaptive RAG.** Marina et al., EMNLP 2025, tested 27 features in 7 groups, computed from external information rather than from the LLM. These features "match the performance of complex LLM-based methods while achieving significant efficiency gains". — [ACL Anthology](https://doi.org/10.18653/v1/2025.emnlp-main.439)
- **Uncertainty-triggered retrieval.** arXiv Jan 2025. On a small set, retrieving when "Eccentricity" uncertainty U > 2 gave F1 0.605 against 0.552 for always-retrieve, with half the searches. On a larger 75-example set, always-retrieve did better but needed about twice the calls. The authors conclude "always retrieving may be preferable in RAG applications where lightweight retrieval methods like BM25 suffice." — [arXiv 2501.09292](https://arxiv.org/html/2501.09292v3)
- **Why models guess.** Kalai, Nachum, Vempala and Zhang (OpenAI), Sept 2025. Hallucination persists because accuracy-only grading rewards guessing. They propose explicit confidence targets: "Answer only if you are > t confident, since mistakes are penalized t/(1−t) points", for example t=0.5 (penalty 1), t=0.75 (penalty 2), t=0.9 (penalty 9). — [arXiv 2509.04664](https://arxiv.org/html/2509.04664v1)
- SimpleQA example from OpenAI:

  | Model | Abstained | Accurate | Wrong |
  |---|---|---|---|
  | gpt-5-thinking-mini | 52% | 22% | 26% |
  | o4-mini | 1% | 24% | 75% |

  Guessing raises accuracy slightly but triples errors. — [OpenAI blog, 5 Sept 2025](https://openai.com/index/why-language-models-hallucinate/)
- **Verbalised confidence.** For RLHF models, asking for a stated confidence is often better calibrated than token probabilities; the paper reports expected calibration error falling by about a relative 50%. — [Tian et al. 2023, arXiv 2305.14975](https://arxiv.org/abs/2305.14975)
- **P(True)/P(IK).** Models can be trained or prompted to estimate whether they know an answer. — [Kadavath et al. 2022, arXiv 2207.05221](https://arxiv.org/abs/2207.05221)
- **Self-consistency.** Sample several reasoning paths and take a majority vote. Reported gains: GSM8K +17.9%, SVAMP +11.0%, AQuA +12.2%, StrategyQA +6.4%, ARC-c +3.9%. — [Wang et al. 2022, arXiv 2203.11171](https://arxiv.org/abs/2203.11171)
- **Selective prediction.** Selective classification chooses a confidence threshold that guarantees a target risk at maximum coverage (risk-coverage trade-off). — [Geifman & El-Yaniv 2017, arXiv 1705.08500](https://arxiv.org/abs/1705.08500)
- Related conformal work: conformal abstention for LLMs — [Yadkori et al. 2024, arXiv 2405.01563](https://arxiv.org/abs/2405.01563); conditional and level-adaptive conformal factuality — [Cherian, Gibbs & Candès 2024, arXiv 2406.09714](https://arxiv.org/abs/2406.09714); conformal language modeling — [Quach et al. 2023, arXiv 2306.10193](https://arxiv.org/abs/2306.10193); tutorial — [Angelopoulos & Bates, arXiv 2107.07511](https://arxiv.org/abs/2107.07511)
- An evaluation of LLM memory systems (Oct 2025) reports that "episodic memory can help LLMs recognise the limits of their own knowledge." — [arXiv 2510.23730](https://arxiv.org/html/2510.23730v1)

### Inferences
- **Decision rule for "ask or answer" (expected-utility form of Kalai's target).** Let p be the estimated probability that a claim is right, C_err the cost of showing a wrong claim and C_ask the cost of asking (latency, money, privacy). Asking is worth it when (1−p)·C_err > C_ask, that is when p < 1 − C_ask/C_err. Kalai's t/(1−t) penalty is the same rule with C_ask = 0 and answering versus abstaining. For a deen question the error cost is effectively unbounded, so p must be near 1 before the model's own words stand; MIZAN already never lets the model quote scripture. This replaces the current rule ("facet = fact, so ask about every da'if claim") with one that also orders claims inside the 20-second budget: ask the lowest-p claims first.
- **Discrete semantic entropy on CPU.** Ask Lisan for k = 5 to 10 short answers (or re-sample only the uncertain sentence). Cluster them with MIZAN's existing multilingual NLI model: answers i and j are in the same cluster iff i ⇒ j and j ⇒ i. Then compute SE = −Σ_c p̂(c) log p̂(c) with p̂(c) = |c|/k. The ablation above suggests a small NLI model loses about 0.05 AUROC against an LLM judge. The cost is the extra hosted-LLM samples, which Iqtisad would need to budget. SEPs are not usable because the hosted model exposes no hidden states. The in-house Ruh model, if ever used, could carry a probe.
- **Cheaper ask-signals that need no extra LLM call** (all CPU-friendly, after the EMNLP 2025 "LLM-independent" result):
  - Qasd's facet posterior and fast-change cues: dates, "current", "latest", superlatives.
  - Entity rarity: low BM25/IDF of named entities in MIZAN's corpora, a proxy for popularity. PopQA-type questions about rare entities are where retrieval helps most; CRAG's no-retrieval LLaMA2-7B scores only 14.7 on PopQA versus 38.2 with retrieval, see section 2.
  - Prior settlement history in `ilm`.

  These can feed one Tamyiz-style naive-Bayes "needs a source" model fitted by leave-one-out, which is consistent with MIZAN's "no thresholds" approach.
- **Conformal calibration of Ahl al-Dhikr verdicts.** The Isnad ledger plus owner-reported errors (the Ibrah tasks) form a labelled calibration set. Score each claim by its NLI entailment probability, compute q̂_α from that set, and present a claim as "hasan, supported" only above q̂_α. That makes the advertised "supported" rate a guarantee rather than a MAP label. Calibrate per language or per source family where n allows, because the guarantee is only marginal. The Wilson intervals Imtihan already reports can show the guarantee's own uncertainty.

### Gaps
- No published head-to-head was found of semantic entropy computed with a *multilingual MiniLM-class* NLI model on Arabic, Urdu or Hindi answers. The DeBERTa ablation is English.
- No source quantified the latency and cost of semantic entropy with hosted frontier models in October 2026. Only the relative 5 to 10× multiplier is documented.

## 2. Retrieval and verification: self-ask, ReAct, FActScore, SAFE, FacTool, RARR, Chain-of-Verification, Self-RAG, CRAG and 2025–2026 work. Which give measurable gains, at what cost?

### Takeaway
The decompose → retrieve → verify pattern (FActScore, SAFE, FacTool, VeriScore) is mature. SAFE agrees with crowd raters on 72% of facts, wins 76% of disagreements and costs $0.19 per response. Its cost scales with the number of claims, though: up to about 13 LLM/search calls per claim, about 107 searches per response. The 2025–2026 frontier groups claims, reuses evidence and searches only uncertain groups: EAVer needs about 3 searches per response, and FaStFact reads document-level evidence instead of SERP snippets. Small trained checkers verify claims against fixed evidence at GPT-4 level for about 1/400 of the cost (MiniCheck, 770M parameters). Corrective retrieval (CRAG: grade the retrieved documents, fall back to web search when they are bad) gives large gains and is plug-and-play. Self-RAG needs its own fine-tuned model, so it does not fit a hosted-LLM design.

### Cited Findings
- **SAFE.** Google DeepMind; arXiv March 2024; NeurIPS 2024.
  - The LLM splits a response into individual facts, makes each self-contained and judges relevance, then runs multi-step Google searches per fact.
  - Metric: F1@K, which balances precision (supported facts) against recall relative to a preferred number of facts K.
  - On 16,011 facts from 496 responses, SAFE agreed with humans on 72.0%. On 100 disagreements re-annotated as ground truth, SAFE was right 76% and humans 19%.
  - Cost: $96.31 in total (GPT-3.5-Turbo $64.57 plus Serper $31.74), $0.19 per response against $4 for crowdworkers, more than 20× cheaper.

  — [arXiv 2403.18802](https://arxiv.org/html/2403.18802v4); [DeepMind](https://deepmind.google/research/publications/85420/); [NeurIPS PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/937ae0e83eb08d2cb8627fe1def8c751-Paper-Conference.pdf)
- **FActScore.** Min et al., EMNLP 2023. Splits generations into atomic facts and scores the fraction supported by a knowledge source (Wikipedia). ChatGPT scored only 58% on biographies; an automated estimator had less than 2% error rate. — [arXiv 2305.14251](https://arxiv.org/abs/2305.14251)
- **Earlier methods:**
  - VeriScore (2024) verifies only *verifiable* claims. — [arXiv 2406.19276](https://arxiv.org/abs/2406.19276)
  - FacTool (2023) is tool-augmented checking across domains: knowledge QA, code, math, citations. — [arXiv 2307.13528](https://arxiv.org/abs/2307.13528)
  - RARR (2022/ACL 2023) researches an existing output, then revises it while preserving the original. — [arXiv 2210.08726](https://arxiv.org/abs/2210.08726)
  - Chain-of-Verification (2023) drafts an answer, plans verification questions, answers them independently, then revises. — [arXiv 2309.11495](https://arxiv.org/abs/2309.11495). CRAG's table lists CoVe on LLaMA-65B at 71.2 FactScore on biographies. — [CRAG arXiv 2401.15884](https://arxiv.org/html/2401.15884v3)
  - Self-Ask (2022) has the model ask explicit follow-up sub-questions, which can be routed to a search engine; it targets the "compositionality gap". — [arXiv 2210.03350](https://arxiv.org/abs/2210.03350)
  - ReAct (2022) interleaves reasoning traces with actions; it beat imitation and RL methods by an absolute 34% (ALFWorld) and 10% (WebShop) success rate. — [arXiv 2210.03629](https://arxiv.org/abs/2210.03629)
- **CRAG** (Yan et al., arXiv Jan 2024). A lightweight retrieval evaluator grades the retrieved documents and triggers one of three actions (Correct, Incorrect, Ambiguous). Incorrect triggers web search; knowledge is refined by decompose-then-recompose. Gains:
  - On SelfRAG-LLaMA2-7b, CRAG beats plain RAG by +7.0 accuracy on PopQA, +14.9 FactScore on Biography, +36.6 on PubHealth and +15.4 on ARC-Challenge.
  - On LLaMA2-hf-7b the gains are +4.4 PopQA, +2.8 Bio and +10.3 ARC.
  - Self-CRAG beats Self-RAG by +20.0 PopQA and +36.9 Bio (LLaMA2-hf-7b).

  The same table shows retrieval matters most for long-tail questions: LLaMA2-7B scores 14.7 on PopQA without retrieval and 38.2 with it. — [arXiv 2401.15884](https://arxiv.org/html/2401.15884v3)
- **Self-RAG** (Asai et al., ICLR 2024) trains one LM to emit "reflection tokens" (retrieve or not; is the passage relevant, supported, useful). It beats ChatGPT and retrieval-augmented Llama2-chat on open-domain QA, reasoning, fact verification and citation accuracy. — [ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/25f7be9694d7b32d5cc670927b8091e1-Abstract-Conference.html). When CRAG's authors ran the Self-RAG procedure on an *untrained* LLaMA2-hf-7b, it scored only 29.0 PopQA and 0.7 PubHealth, against 54.9 and 72.4 with the trained Self-RAG model. The method depends on its fine-tuned critic. — [CRAG Table 1](https://arxiv.org/html/2401.15884v3)
- **MiniCheck** (Tang, Laban, Durrett, EMNLP 2024). Small checkers trained on GPT-4-synthesised hard examples.
  - MiniCheck-FT5 (Flan-T5-Large, 770M) "reaches GPT-4 accuracy" on the 13K-example LLM-AggreFact benchmark at more than 400× lower cost, and beats earlier specialised checkers by 4 to 10 points absolute.
  - The 355M DeBERTa and RoBERTa variants cost $0.20 for the whole test set at $0.8/GPU-hour.
  - It needs no separate claim-decomposition step.

  — [arXiv 2404.10774](https://arxiv.org/html/2404.10774); [ACL Anthology](https://aclanthology.org/2024.emnlp-main.499/)
- **FreshPrompt** (Vu et al., Findings ACL 2024). Feeding dated search evidence, ordered oldest to newest, plus few-shot reasoning over it improved GPT-4 on FreshQA by +47% (Strict) and +31.4% (Relaxed) accuracy. It beat Self-Ask and Perplexity.AI. Both the number and the order of evidence items matter, and concise answers reduce hallucination. — [arXiv 2310.03214](https://arxiv.org/abs/2310.03214)
- **2025–2026: cost-efficient verification**
  - EAVer (arXiv 2609.22223, Sept 2026 preprint):
    - Per-claim pipelines issue 35.9 to 103.7 searches per sample with 23.5% to 66.5% repeated links; SAFE averaged 106.90 searches per sample and VeriFastScore 15.62.
    - SAFE "can require up to 13 calls for a single relevant claim".
    - EAVer (Qwen3-8B) groups related claims, verifies confident groups directly, searches only uncertain groups and keeps compact evidence memos for reuse. It averaged 3.14 searches per sample, reached 73.43 Macro-F1 on VeriFastScore (against 70.55) and 74.05 on the human-annotated FaStFact-Bench.

    — [arXiv 2609.22223](https://arxiv.org/abs/2609.22223)
  - FaStFact (Findings EMNLP 2025) does chunk-level claim extraction with confidence-based pre-verification and gathers document-level evidence from crawled pages, because one-line SERP snippets proved insufficient. It reports the highest alignment with human evaluation among baselines. — [ACL Anthology](https://aclanthology.org/2025.findings-emnlp.1295/)
  - DeepFact (ACL 2026), on deep-research-report claims:
    - Unassisted PhD experts reached only 60.8% accuracy on hidden known-answer claims, rising to 90.9% after three "Audit-then-Score" rounds.
    - DeepFact-Eval reached 83.4%, against 58.5% for the best traditional pipeline and 69.1% for the best prior deep-research verifier.
    - VeriScore reached 52.5%: snippet-based checkers transfer poorly to complex claims.

    — [ACL Anthology](https://aclanthology.org/2026.acl-long.1586.pdf)
  - FactSearch (ACL 2026 demo) estimates about $0.018 per response with 5 claims on OpenAI pricing, and offers a local variant. — [ACL Anthology](https://aclanthology.org/2026.acl-demo.36.pdf)
  - Evergreen (arXiv 2604.26180, Apr 2026) uses early stopping, relevance sorting and *confidence sequences* to stop verification once enough evidence is in. It kept F1 0.94 at 3.1× lower cost. — [arXiv 2604.26180](https://arxiv.org/html/2604.26180)

### Inferences
- **What to add to MIZAN, ranked by gain per cost on CPU.**
  1. **Corrective retrieval gate (CRAG pattern).** MIZAN already has the evaluator: the relevance gate plus NLI. Formalise three outcomes per claim:
     - *Correct*: a kept sentence entails the claim.
     - *Incorrect*: no kept sentence passes the information gate, so try the next source or reformulate the query.
     - *Ambiguous*: kept sentences are neutral, so read the full page (document-level evidence, as FaStFact found necessary) rather than snippets.
  2. **Claim grouping and evidence reuse (EAVer pattern).** Before asking sources, cluster an answer's claims by shared distinctive entities, using the same IDF information gate. Issue one search per cluster, cache the fetched page per request, and run every claim in the cluster against it. This cuts search calls, privacy exposure and the 20-second budget pressure. No training is needed; EAVer's learned policy can be approximated by the information-gate clustering.
  3. **A second, grounding-specialised checker.** MiniLMv2-mnli-xnli is a generic MNLI/XNLI model. MiniCheck-style checkers are trained specifically for "is this LLM claim supported by this document". Use MiniCheck (English, 355M to 770M) for English claims; NLI agreement between the two (product-of-experts or Dawid-Skene, section 3) gives a better-calibrated verdict.
  4. **Sequential stopping instead of a fixed budget.** Update the claim's support posterior as each sentence or source arrives, and stop once a confidence-sequence bound clears the decision boundary (the Evergreen idea). This replaces "stop at 20 s".
- **Not recommended for MIZAN.** Self-RAG needs its own fine-tuned generator, and MIZAN's Lisan is a hosted model. RL-trained search agents (Search-R1 family, EAVer's DPO policy) need GPU training. Full SAFE is too call-hungry for per-chat use; it is better kept as the Imtihan offline judge.
- **Evidence presentation to Lisan (FreshPrompt).** When `ilm` sentences are shown to Lisan as "SETTLED BY MIZAN FROM SOURCES", include the source date and order them oldest to newest, so the newest comes last as in FreshPrompt.

### Gaps
- No 2026 benchmark measured these pipelines in Arabic, Urdu or Hindi; all cited results are English.
- No published CPU latency for MiniCheck-FT5 was found; the cost figures assume a GPU at $0.8/hour.
- EAVer is a September 2026 preprint and has not been peer-reviewed.

## 3. Source trust and provenance: weighing sources (reliability models, TruthFinder, Bayesian truth inference, Dawid-Skene), keeping provenance (W3C PROV, nanopublications), and mapping isnad and grading onto both

### Takeaway
Truth-discovery algorithms all rest on one fixed point: a source is reliable if it states true things, and a claim is true if reliable sources state it. The solutions range from iterative heuristics (TruthFinder, Investment) through EM latent-class models (Dawid-Skene) to Bayesian two-sided models (Latent Truth Model) and web-scale Knowledge-Based Trust. Hadith science added two elements most truth-discovery methods lack: independence of chains, so that copies of one route do not count twice, and grading by a named critic. A 2025 ICML paper formalises exactly this as a graph model. W3C PROV (2013) and nanopublications give a standard data model: assertion plus provenance plus publication info, with Quotation and PrimarySource relations and trusty-URI hashes. MIZAN's Sakk receipts already provide the hashing half.

### Cited Findings
- **The principle.** "If a source provides trustworthy information frequently, it will be assigned a high reliability; meanwhile, if one piece of information is supported by sources with high reliabilities, it will have big chance to be selected as truth." Iterative methods alternate truth computation and source-weight estimation until they converge. — [Li et al., A Survey on Truth Discovery, SIGKDD Explorations 2015, arXiv 1505.02463](https://arxiv.org/html/1505.02463v2)
- **Investment algorithm** (as given in the survey). Each value receives vote(v) = (Σ_{s∈S_v} w_s/|V_s|)^1.2. Each source collects credit back: w_s = Σ_{v∈V_s} vote(v)·(w_s/|V_s|) / Σ_{s'∈S_v} (w_{s'}/|V_{s'}|). — [arXiv 1505.02463](https://arxiv.org/html/1505.02463v2)
- **TruthFinder** (Yin, Han, Yu, KDD 2007 / TKDE 2008) defines the "Veracity" problem: "a website is trustworthy if it provides many pieces of true information, and a piece of information is likely to be true if it is provided by many trustworthy websites". Both are inferred iteratively, and similar facts support each other ("implication"). — [TKDE abstract](https://ui.adsabs.harvard.edu/abs/2008ITKDE..20..796Y/abstract). The update equations are:
  - fact confidence s(f) = 1 − Π_{w∈W(f)} (1 − t(w)), computed in log space with τ(w) = −ln(1 − t(w));
  - an implication-adjusted score σ*(f) = σ(f) + ρ·Σ_{f'} σ(f')·imp(f'→f);
  - a sigmoid dampening s(f) = 1/(1 + e^{−γσ*(f)});
  - website trust t(w) = the mean of s(f) over the facts w provides.

  Same paper.
- **Fact-finder critique.** Majority voting "implicitly (and implausibly) assumes that all sources are equally trustworthy". Example: a Google search for "water runs downhill" returned 17.5K documents, against 116K for "water runs uphill". — [Pasternack & Roth, fact-finders chapter (UPenn CogComp)](https://cogcomp.seas.upenn.edu/papers/fact_finder_chapter_clean.pdf)
- **Dawid-Skene** (1979). Each item has one latent true class; each annotator has a confusion matrix π^{(j)}_{kl} = P(reports l | true k). EM alternates:
  - E-step: T_{ik} ∝ p_k Π_j Π_l (π^{(j)}_{kl})^{n^{(j)}_{il}};
  - M-step: π^{(j)}_{kl} ∝ Σ_i T_{ik} n^{(j)}_{il}, and p_k = mean_i T_{ik}.

  — [Dawid & Skene, JRSS C 28(1) 1979](https://doi.org/10.2307/2346806). Its assumptions are conditional independence of annotators given the truth (shared bias or consultation violates it), error rates constant across items, and exhaustive, mutually exclusive classes. A practical use is adjudicating "supports / contradicts / does not address" judgments. — [Reliable Context glossary (secondary source of unknown authority)](https://reliablecontext.com/glossary/dawid-skene-model)
- **Recent surveys.** A 2024 IEEE TBDATA survey classifies truth discovery by single versus multi-valued observations, independent versus dependent sources, static versus dynamic sources, and supervised versus unsupervised methods. — [Wang et al. 2024](https://doi.org/10.1109/tbdata.2024.3423677)
- **Further models:**
  - The Latent Truth Model gives each source two-sided quality (a false-positive rate and a sensitivity) in a Bayesian model. — [Zhao et al., VLDB 2012, arXiv 1203.0058](https://arxiv.org/abs/1203.0058)
  - Knowledge-Based Trust scores web pages by the correctness of the facts they state rather than by links, and separates extraction errors from source errors. It was applied to 2.8B extracted facts to estimate the trustworthiness of 119M web pages. — [Dong et al., VLDB 2015, arXiv 1502.03519](https://arxiv.org/abs/1502.03519)
  - Source *dependence* (copying) detection is needed so that copied values are not counted as independent votes. — [Dong, Berti-Equille & Srivastava, VLDB 2009](https://www.vldb.org/pvldb/vol2/vldb09-110.pdf)
- **Hadith science as a graph model** ("Crowdsourced Information Authentication: A Graph-based Model from the Science of Hadith", ICML 2025, OpenReview June 2025). Narrators are nodes, transmissions are directed edges, and an isnad is a path. The model jointly learns "the authenticity score for each transmission and the reliability score for each narrator". It accounts for chain structure, narrator reliability, content consistency and "corroboration ... through multiple independent transmission paths, including a mechanism to discount overlapping paths", using an iterative co-update algorithm with a convergence analysis. — [OpenReview](https://openreview.net/forum?id=F7CgAEPvAv); [ICML slides](https://icml.cc/media/icml-2025/Slides/50547.pdf)
- **Computational isnad work:**
  - A 2025 review of more than 50 studies on sanad analysis covers authenticity classification, narrator networks, NER, datasets and ontologies. Narrator2Vec reached 94% top-10 narrator-prediction accuracy. Centrality analyses of Bukhari and Muslim identify hubs such as Abu Hurayra, Anas bin Malik and az-Zuhri. — [TELKOMNIKA review](https://telkomnika.uad.ac.id/index.php/TELKOMNIKA/article/download/27447/12280)
  - Narrator linking reached 94.6% on AR-Sanad 280K. — [Neural Computing & Applications 2024](https://dlnext.acm.org/doi/10.1007/s00521-024-10194-2)
  - EviLink-NA (ACM TALLIP, July 2026) fuses five evidence channels (textual, temporal, geospatial, path-consistency, reliability priors) by *Dirichlet evidential fusion* with an explicit uncertainty mass. It gives calibrated probabilities (ECE, Brier, NLL) and a principled "abstain" for low evidence. — [ACM TALLIP](https://dl.acm.org/doi/full/10.1145/3811820)
  - A community library, "ISNAD" (Apache-2.0, `pip install isnad`), grades each claim's chain of transmitters with a "weakest-link" cap, a living "rijal" registry of transmitters, separate content criticism, and a SHA-256 audit record. It is unreviewed and positions itself as a compliance tool. — [GitHub alizahidraja/isnad](https://github.com/alizahidraja/isnad)
- **W3C PROV-DM** (Recommendation, 30 April 2013). Its core types are Entity, Activity and Agent. Derivation (wasDerivedFrom) has three subtypes:
  - **Revision**: a revised version of an original.
  - **Quotation** (wasQuotedFrom): "the repeat of (some or all of) an entity ... by someone who may or may not be its original author".
  - **Primary Source** (hadPrimarySource): "something produced by some agent with direct experience and knowledge about the topic, at the time ... without benefit from hindsight". It is "important for secondary sources to reference those primary sources ... so that their reliability can be investigated."

  — [PROV-DM](https://www.w3.org/TR/prov-dm/); [PROV namespace](https://www.w3.org/ns/prov/); [PROV-O](https://www.w3.org/TR/prov-o/) (wasInfluencedBy is the superproperty)
- **Nanopublications** (guidelines working draft dated 30 Sept 2026). A nanopublication consists of an assertion graph, a provenance graph (which must link to the assertion, for example prov:wasDerivedFrom and prov:wasAttributedTo) and a publication-info graph (creator and timestamp), tied together by a head graph. Trusty URIs give an integrity key that enforces immutability. — [nanopub.net guidelines](https://nanopub.net/guidelines/working_draft/)

### Inferences
- **Isnad ↔ PROV ↔ truth discovery mapping** (proposed for MIZAN's ledger):

  | Hadith science | PROV / nanopub | Truth-discovery quantity | MIZAN today |
  |---|---|---|---|
  | rawi (narrator) | prov:Agent | source reliability t(w), or a Dawid-Skene confusion matrix | a source name only |
  | sama'/riwaya (an act of transmission) | prov:Activity (fetch, extract, translate) | an edge in the source graph | fetch receipt in Sakk |
  | riwaya bil-lafz (verbatim) vs bil-ma'na (by meaning) | wasQuotedFrom vs wasDerivedFrom | lossless vs lossy extraction (KBT's extraction-error term) | quotes vs model wording |
  | the Companion's eyewitness report | hadPrimarySource | primary vs secondary source | not distinguished |
  | ittisal al-sanad (continuity) | an unbroken derivation chain back to a primary source | — | the link is kept |
  | 'adalah (integrity) | an Agent attribute | a prior against fabrication (Amanah taint, sites known to inject) | Amanah |
  | dabt (precision) | quotation fidelity | per-source accuracy (sensitivity/specificity, as in LTM) | — |
  | shudhudh (a reliable narrator contradicting more reliable ones) | conflicting entities | the contradiction outcome weighted by source trust | "contradicted" from one source |
  | 'illah (hidden defect) | e.g. a source copied from another | source dependence (copy detection, Dong 2009) | — |
  | hasan li-ghayrihi (weak routes strengthening each other) | several independent derivations | corroboration counted only over independent paths | — |
  | grade by a named muhaddith | pubinfo: wasAttributedTo(grader) | an annotator in Dawid-Skene | Isnad grade by MIZAN |
  | mawdu' (fabricated) | — | known-false | Sidq removes it |

- **Source reliability done properly.** MIZAN's Beta posterior currently models "does this source *settle* a claim", which is about coverage, not truth. Add a second posterior per source and per domain or topic, Beta(α_s, β_s), for "was this source's verdict right". It is updated only from verified outcomes: an owner correction, agreement with an independent source, a Muhasaba re-check, or Imtihan. Use it as t(w) in a TruthFinder or Dawid-Skene aggregate when more than one source speaks: log-odds(claim true) = Σ_s z_s · log(t_s/(1 − t_s)), with z_s = ±1 for support or contradiction and the NLI probability as a soft z_s. This is the naive-Bayes form, consistent with Tamyiz. Sources found to be copies (same sentence text, or a page citing the other page) must be collapsed into one vote before summing, which is the hadith "independent chains" rule and Dong's copy detection.
- **Grade by the chain, not only by "a source agreed".** "hasan" from one Wikipedia sentence is, in hadith terms, an ahad report through a secondary source. A finer, PROV-based Isnad grade for outside facts:
  - **sahih-like**: two or more *independent* sources agree, at least one primary (for example a government statistic or a dated official page), no reliable contradiction;
  - **hasan**: one reliable source, or several weaker independent ones (hasan li-ghayrihi);
  - **da'if**: none, or only sources of low reliability;
  - **shadhdh / contradicted**: contradicted by sources whose aggregate trust is higher.
- **Storage format.** Keep each settled entry as a nanopublication-shaped record: assertion (the claim text and its language), provenance (source URL, page revision id or fetch time, quoted sentence, quotation versus paraphrase, NLI probabilities, model versions), and pubinfo (the user, the MIZAN version, the Sakk receipt hash as a trusty-URI-like integrity key). This also makes the Mahw (erase) receipts and the Daftar export precise.

### Gaps
- No source evaluated truth-discovery algorithms when the "sources" are an NLI model reading a few web pages. Published evaluations use structured attribute values (books, flights, stocks).
- I did not find the full equations of the 2025 hadith graph model (only the abstract and slides) or a public implementation.
- The copy-detection paper URL is given from memory of the VLDB 2009 proceedings and was not fetched in this session.

## 4. Keeping and reusing what was learned: online knowledge bases, knowledge editing (ROME, MEMIT and their failures), retrieval memory versus weight updates, time decay and re-verification, conflict resolution

### Takeaway
Weight editing is not a viable store for an agent that learns continuously. Gupta et al. (Findings ACL 2024) found ROME and MEMIT fail gradually and then catastrophically under sequential edits (MEMIT collapsed after about 1,400 edits on GPT-J). They also fail multi-hop "ripple" consequences. RAG beats unsupervised fine-tuning for injecting both old and new knowledge. MIZAN's hosted LLM has no editable weights anyway, so an external, provenance-keyed memory is the right design. The 2026 evidence says retrieval quality matters far more than how memories are written (a 20-point spread across retrieval methods, 3 to 8 points across write strategies). Facts change at different rates (FreshQA's never, slow and fast-changing classes), so each kept fact needs a validity model and scheduled re-verification. MIZAN's current `ilm` has none: "asked once" holds forever, capped at 300 entries.

### Cited Findings
- **Sequential editing collapse.** "As a model is edited sequentially with multiple facts, it continually becomes less editable, forgets previously edited facts and loses the ability to perform downstream tasks". Forgetting comes in two phases, gradual and then catastrophic, and ROME has single "disabling edits". For MEMIT on GPT-J, catastrophic forgetting began after about 1,400 edits; edits "bleed into other facts". — [Gupta et al., Findings ACL 2024](https://aclanthology.org/2024.findings-acl.902.pdf)
- r-ROME shows the disabling edits come from implementation irregularities and fixes ROME's collapse. — [Gupta et al., EMNLP 2024](https://doi.org/10.18653/v1/2024.emnlp-main.1210)
- Lifelong editing degrades severely after "dozens or hundreds" of edits; the interference is tied to knowledge superposition. — [Hu et al., AAAI 2025](https://doi.org/10.1609/aaai.v39i22.34583)
- "All parameter modifying ME methods systematically damage all fundamental capabilities of LLMs after a few sequential edits". — [Navigating the Dual Facets, arXiv 2402.11122](https://arxiv.org/pdf/2402.11122v1.pdf)
- All editing methods perform poorly on reasoning over edited facts, and locate-and-edit methods "severely deteriorate the models' language modeling capabilities". — [ReCoE, Findings ACL 2024](https://aclanthology.org/2024.findings-acl.743.pdf)
- **Ripple effects.** Editors recall the edited fact but "fail catastrophically" on multi-hop questions that follow from it. MeLLo, which "stores all edited facts externally" and prompts iteratively, "outperforms previous model editors by a large margin". — [MQuAKE, EMNLP 2023, arXiv 2305.14795](https://arxiv.org/abs/2305.14795). See also RippleEdits — [Cohen et al., TACL 2024, arXiv 2307.12976](https://arxiv.org/abs/2307.12976)
- **Outdated knowledge.** Outdatedness is critical across 24 LLMs, answers are inconsistent under paraphrase, and four editing methods "can not reduce the cases of outdatedness". Evaluation is against Wikidata as the up-to-date graph. — [DyKnow, arXiv 2404.08700](https://arxiv.org/html/2404.08700v2)
- **Retrieval versus fine-tuning.** "RAG consistently outperforms [unsupervised fine-tuning], both for existing knowledge encountered during training and entirely new knowledge", and "LLMs struggle to learn new factual information through unsupervised fine-tuning". — [Ovadia et al. (Microsoft), arXiv 2312.05934](https://arxiv.org/abs/2312.05934)
- **Agent memory systems:**
  - Mem0 (Apr 2025) dynamically extracts, consolidates and retrieves memories. On LOCOMO it reports a 26% relative gain in LLM-as-judge score over OpenAI's memory, 91% lower p95 latency and more than 90% token savings against full context. — [arXiv 2504.19413](https://arxiv.org/html/2504.19413)
  - Vendor report, Oct 2026 (not independent): "independent benchmark results can differ by a wide margin". The hardest open problems are "temporal reasoning, memory staleness, cross-session identity, privacy, deletion". — [mem0.ai blog](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Retrieval dominates memory quality** (arXiv 2603.02473, Mar 2026). A 3×3 study on LoCoMo crossed write strategies (raw chunks, Mem0-style facts, MemGPT-style summaries) with retrieval methods (cosine, BM25, hybrid plus rerank).
  - Accuracy spans 20 points across retrieval methods (57.1% to 77.2%) but only 3 to 8 points across write strategies.
  - Raw chunks with zero LLM write calls "match or outperform" the lossy alternatives.
  - For raw chunks, BM25 gave 59.2% and hybrid gave 81.1%; the retrieval-failure rate fell from 35.3% to 11.4%.
  - The hybrid pools the top-2k candidates from cosine and BM25 and adds one LLM rerank call.

  — [alphaXiv 2603.02473](https://www.alphaxiv.org/abs/2603.02473)
- **Temporal classes.** FreshQA has 600 questions split into never-changing, slow-changing (changes over years), fast-changing (within a year) and false-premise. "All models (regardless of model size) struggle on questions that involve fast-changing knowledge and false premises", and a question's category can itself change over time. — [FreshLLMs, arXiv 2310.03214](https://arxiv.org/abs/2310.03214)
- **Recency decay in agent memory.** Generative Agents score a memory by recency × importance × relevance, with recency an exponential decay over game hours since last access (decay factor 0.995). — [Park et al. 2023, arXiv 2304.03442](https://arxiv.org/abs/2304.03442)
- **Knowledge conflicts.** LLMs are highly receptive to coherent, convincing external evidence even when it conflicts with their parametric memory. They also show confirmation bias when evidence mixes supporting and conflicting content. — [Xie et al., "Adaptive Chameleon or Stubborn Sloth", arXiv 2305.13300](https://arxiv.org/abs/2305.13300). Survey: [Xu et al., Knowledge Conflicts for LLMs, arXiv 2403.08319](https://arxiv.org/abs/2403.08319)
- **Weight-side editors that avoid in-place damage** (for completeness): GRACE, a discrete codebook adaptor — [arXiv 2211.11031](https://arxiv.org/abs/2211.11031); WISE, a side memory — [arXiv 2405.14768](https://arxiv.org/abs/2405.14768); AlphaEdit, null-space projection, ICLR 2025 — [arXiv 2410.02355](https://arxiv.org/abs/2410.02355). These are relevant only to the in-house Ruh model.

### Inferences
- **Keep MIZAN's memory external.** Never "learn" world facts into Ruh weights. For Ruh, if ever, edit only through a side memory such as GRACE or WISE, behind the same provenance ledger.
- **Upgrade `ilm` retrieval before anything else.** MIZAN's `ilm` and Dhikr recall are BM25-only. The 2026 study shows BM25 at 59% against 81% for hybrid on the same store. Add a small multilingual embedding model on CPU (an e5-small-class model, about 100 MB) and fuse ranks by reciprocal rank fusion, RRF(d) = Σ_r 1/(k + rank_r(d)) with k ≈ 60, before any LLM rerank. Keep raw evidence sentences, which MIZAN already does. Do not summarise them.
- **Replace the 300-entry LRU with a validity model.** Each settled entry gets:
  1. a volatility class c ∈ {never, slow, fast}, predicted by a Tamyiz naive-Bayes model from the claim text (dates, "current", office-holders, prices, populations, records), seeded from FreshQA's labelled categories and refined by observed changes;
  2. a survival probability S(Δt) = exp(−λ_c Δt), where λ_c has a conjugate Gamma(a_c, b_c) prior updated at each re-check (a_c ← a_c + changes found, b_c ← b_c + exposure time). MIZAN thereby learns how fast each kind of fact goes stale;
  3. reuse rule: use the entry directly while S(Δt)·P(correct when settled) clears the ask threshold from section 1; otherwise re-ask the source. Muhasaba already runs daily re-checks, so it could take a ranked queue by (1 − S)·(usage frequency).
- **Reuse score.** score = relevance × base-level activation, with the ACT-R term B = ln Σ_j t_j^{−d} (MIZAN's `core/adaptive.py` already has ACT-R) multiplied by validity S(Δt). Recency of *use* and recency of *verification* are kept separate: a much-used fact verified long ago is exactly the one to re-verify.
- **Conflict resolution order** (combining the hadith rule and truth discovery):
  1. A newer reliable source wins on fast-changing classes. Compare by date (page revision, Wikidata point-in-time or start/end qualifiers, as DyKnow does), then by source trust.
  2. On never-changing classes, the higher-trust aggregate wins (log-odds sum over *independent* sources); a lone contradiction against a stronger consensus is shadhdh.
  3. Keep both, with provenance, when unresolved, and show "sources differ" rather than picking one.

  Because LLMs accept coherent conflicting evidence easily (Xie et al.), conflict resolution must happen in MIZAN's code before Lisan sees the evidence.

### Gaps
- No published dataset of observed change rates for web facts was found that could seed the λ_c priors directly. FreshQA provides categories, not rates.
- The 2026 memory study used GPT-5-mini and LoCoMo (English); the size of the BM25-to-hybrid gain for Arabic, Urdu and Hindi is unmeasured.

## 5. Learning answers to new kinds of questions, not only facts: skill libraries (Voyager), tool creation, program caches with verification

### Takeaway
New kinds of questions are learned as *verified programs or workflows*, not as facts. Three patterns recur, each with measured gains:
- Voyager (2023) keeps only self-verified code in a retrievable skill library (3.3× more unique items, tech-tree milestones up to 15.3× faster).
- LATM (ICLR 2024) has a strong model make a tool once and a cheap model use it, a "functional cache" that matches GPT-4 performance at lower cost.
- Agent Workflow Memory (ICML 2025) induces reusable workflows online (+24.6% and +51.1% relative success on Mind2Web and WebArena).

MIZAN already has the verification parts (Hifz program cache, Tathabbut cross-checks, Qiyas example-checking, Tajdid's sequential acceptance at P(better) ≥ 0.95). What it lacks is the step that *induces a new recipe or tool* when an unrecognised kind of question recurs.

### Cited Findings
- **Voyager** (May 2023). Three parts: an automatic curriculum; "an ever-growing skill library of executable code"; and iterative prompting with environment feedback, execution errors and *self-verification*. Skills are indexed by an embedding of their description, and the top 5 are retrieved for a new task. Only verified programs are added, and complex skills compose simpler ones. Results: 3.3× more unique items (63 in 160 iterations), 2.3× longer distances, and tech-tree milestones up to 15.3× faster (wooden 15.3×, stone 8.5×, iron 6.4×; only Voyager reached diamond). It reuses the library in a new world. — [arXiv 2305.16291](https://arxiv.org/abs/2305.16291); [project page](https://voyager.minedojo.org/); [paper PDF](https://voyager.minedojo.org/assets/documents/voyager.pdf)
- **LATM** (ICLR 2024). A strong "tool maker" writes a Python utility function for a class of tasks; a lightweight "tool user" applies it. A dispatcher keeps a repository of tools: "if no suitable tool is available, the dispatcher identifies this as a novel task", solves it with a strong model, then caches instances "until a sufficient number are amassed to craft a new tool". With GPT-4 as maker and GPT-3.5 as user, performance equals GPT-4 in both roles at significantly lower cost. The cache "stores the functionality of a class of requests instead of the natural language responses". — [ICLR 2024 PDF](https://proceedings.iclr.cc/paper_files/paper/2024/file/ed91353f700d113e5d848c7e04a858b0-Paper-Conference.pdf)
- **Agent Workflow Memory** (ICML 2025) induces "commonly reused routines" from past experience, offline or online. It gave +24.6% and +51.1% relative success on Mind2Web and WebArena with fewer steps, and online AWM beat baselines by 8.9 to 14.0 points as train-test gaps widened. — [PMLR v267](https://proceedings.mlr.press/v267/wang25bx.html)
- **Memento** (Aug 2025) does memory-based online RL with no LLM fine-tuning: a case bank plus a learned case-selection policy. It reached 87.88% Pass@3 on GAIA validation and 79.40% on test; case-based memory added 4.7 to 9.6 points on out-of-distribution tasks. — [arXiv 2508.16153](https://arxiv.org/html/2508.16153v2)
- **Other tool-creation work:** CREATOR — [arXiv 2305.14318](https://arxiv.org/abs/2305.14318); CRAFT — [arXiv 2309.17428](https://arxiv.org/abs/2309.17428)

### Inferences
- **"Recipe induction" for MIZAN, mirroring LATM's dispatcher:**
  1. When Fahm keeps sending a cluster of requests to `converse` or `use_tool`, and the answers keep being repaired or flagged (Tajriba lessons, Muhasaba corrections, owner Ibrah reports), treat the cluster as a *novel task class*. Cluster with Qasd's own features, which are already a naive-Bayes space.
  2. Once n examples have verified answers, ask Lisan to write a program, the "tool". Admit it only if it reproduces every verified example in the sandbox (Qiyas), passes an independent cross-check (Tathabbut), and beats the incumbent path at P(better) ≥ 0.95 (Tajdid's sequential test).
  3. Then register it as a Hifz/Tadbir recipe with its own Qasd seed examples (Ta'allum or Ta'lim), so Fahm routes the next such question to it with no model call.
- **The stopping rule for "enough examples"** can reuse the Beta-Binomial machinery. With s successes in n held-out runs, admit when P(θ > θ_incumbent | s, n) ≥ 0.95 under a Beta(1 + s, 1 + n − s) posterior. That is the same 0.95 Tajdid uses, so no new threshold is introduced.
- **Retrieval of skills.** Voyager uses embeddings of the description and retrieves the top 5. MIZAN should use the same hybrid retrieval recommended for `ilm` (section 4) over recipe descriptions plus their seed phrasings.

### Gaps
- No 2025–2026 source measured skill-library learning for *question answering* in a personal assistant (as opposed to Minecraft or web navigation).
- No source evaluated the safety of auto-induced tools beyond sandboxing. Hudud and Amanah cover MIZAN's side.

## 6. Religious knowledge: what authentic Islamic sources say about verifying reports (49:6, 16:43, 17:36; hadith-science criteria), and which open, authoritative sources can be consulted programmatically, on what terms

### Takeaway
The Quran commands investigation of reports from an unreliable bearer (49:6), asking those who know when one does not know (16:43), and not pursuing what one has no knowledge of (17:36). Sahih Muslim's introduction makes passing on everything one hears a form of lying (Muslim 5). It also ranks narrators in tiers of precision and defines munkar as divergence from the precise memorisers. Classical hadith science (Ibn al-Salah) defines sahih by five conditions: continuity, integrity, precision, no anomaly, no hidden defect. Hasan is a lighter tier, and mildly weak routes can strengthen each other but severely weak ones cannot. This is a complete source-reliability and corroboration theory. Four programmatic sources have usable terms:
- **Quran Foundation API**: OAuth2. QF content must not be cached more than 1 week except through Content Sync, the Quran text must not be modified, and models must not be trained on it without consent. RAG is allowed.
- **sunnah.com API**: an API key requested by GitHub issue; grades carry `graded_by`.
- **dorar.net's new API**: a Bearer token after manual review. It returns the muhaddith, the source book and the grade summary.
- **fawazahmed0 hadith-api**: Unlicense, no rate limits, multiple grades.

### Cited Findings
- **Quran 49:6** (Saheeh International, via the AlQuran Cloud API editions quran-uthmani and en.sahih): "يَٰٓأَيُّهَا ٱلَّذِينَ ءَامَنُوٓا۟ إِن جَآءَكُمْ فَاسِقٌۢ بِنَبَإٍۢ فَتَبَيَّنُوٓا۟ ..." — "O you who have believed, if there comes to you a disobedient one with information, investigate, ..." The ayah continues with a warning against harming a people out of ignorance and then regretting it. — [AlQuran Cloud 49:6](https://api.alquran.cloud/v1/ayah/49:6/editions/quran-uthmani,en.sahih)
- **Quran 16:43**: "وَمَآ أَرْسَلْنَا مِن قَبْلِكَ إِلَّا رِجَالًۭا نُّوحِىٓ إِلَيْهِمْ ۚ فَسْـَٔلُوٓا۟ أَهْلَ ٱلذِّكْرِ إِن كُنتُمْ لَا تَعْلَمُونَ" — "And We sent not before you except men to whom We revealed [Our message]. So ask the people of the message if you do not know." — [AlQuran Cloud 16:43](https://api.alquran.cloud/v1/ayah/16:43/editions/quran-uthmani,en.sahih)
- **Quran 17:36**: "وَلَا تَقْفُ مَا لَيْسَ لَكَ بِهِۦ عِلْمٌ ..." — "And do not pursue that of which you have no knowledge." The ayah continues that the hearing, the sight and the heart will all be questioned. — [AlQuran Cloud 17:36](https://api.alquran.cloud/v1/ayah/17:36/editions/quran-uthmani,en.sahih)
- **Sahih Muslim 5** (Introduction, chapter "The Prohibition of Narrating Everything One Hears"), Shu'bah ← Khubayb ← Hafs bin 'Asim ← Abu Hurayrah: "It is enough of a lie for a man to narrate everything he hears" (كَفَى بِالْمَرْءِ كَذِبًا أَنْ يُحَدِّثَ بِكُلِّ مَا سَمِعَ). — [sunnah.com/muslim:5](https://sunnah.com/muslim:5). The same words are reported from 'Umar (Introduction 9). — [sunnah.com](https://sunnah.com/muslim/introduction/8)
- **Imam Muslim's introduction:**
  - Narrators fall into tiers: those of "integrity ... and certitude"; those "not described with memorization and precision" yet covered by "protection [from ill-repute] and truthfulness" (examples given: 'Ata' bin al-Sa'ib, Yazid bin Abi Ziyad, Layth bin Abi Sulaym); and those accused of fabrication or dominated by munkar, whom he did not use.
  - "An indication of Munkar in the narration of a Muhaddith is when his transmission differs with the transmission of a Muhaddith from the people of memorization and acceptance".
  - An addition from a narrator who "is predominantly in agreement with" the trustworthy is accepted.
  - "Focusing on the few authentic narrations is worthier for them than seeking an abundance of weak narrations."

  — [sunnah.com Muslim Introduction](https://sunnah.com/muslim/introduction) (translation by Fernando Rodriguez; the page notes the introduction's narrations "may not all meet the strict standards" of the Sahih itself)
- **'Abdullah ibn al-Mubarak** (d. 181 AH): "The isnad is part of the religion: had it not been for the isnad, whoever wished to would have said whatever he liked." **Ibn Sirin** (d. 110 AH): "They would not ask about the isnad. But when the fitnah happened, they said: Name to us your men..." Both are cited to Sahih Muslim's introduction, 1:15 ('Abd al-Baqi edition). — [Suhaib Hasan, An Introduction to the Science of Hadith (SunnahOnline)](https://sunnahonline.com/library/fiqh-and-sunnah/277-introduction-to-the-sciences-of-hadith) (secondary; the primary Arabic is in Muslim's introduction)
- **Definitions.** Ibn al-Salah: sahih is the hadith with "a continuous isnad, made up of reporters of trustworthy preservers from similar authorities, and which is found to be clear from shudhudh and any defects". Hasan, per Ibn al-Salah, has two kinds:
  1. a narrator who is mastur but not careless, *provided a similar text comes through another isnad*;
  2. a truthful narrator "a degree less in his preservation".

  "A number of weak ahadith on a particular issue can be raised to the degree of hasan if the weakness found in their reporters is of a mild nature. However, in case the weakness is severe (i.e., the reporter is a liar or the hadith is itself shadhdh), such weak ahadith will not support each other". The four verdict classes are sahih, hasan, da'if and mawdu'. — [Mahmood al-Tahhan / Suhaib Hasan, "Rules Governing the Criticism of Hadeeth" (IslamHouse PDF)](https://d1.islamhouse.com/data/en/ih_books/single/en_Rules_Hadeeth.pdf)
- al-Jurjani's manual (d. 816 AH) gives the same five conditions. It defines shudhudh as "when a trustworthy narrator narrates a report which is in stark contradiction to the reports of all others" and 'illah as defects "due to factors that are obscure ... and hard to detect". — [Risalah fi 'Ilm Usul al-Hadith, trans. Abu Hasan](https://www.ridawipress.org/wp-content/uploads/risalah-sharif.pdf). The Arabic of Ibn al-Salah's Muqaddimah is also online — [hdith.com](https://hdith.com/encyclopedia/book/b-70/h/746330); [archive.org English translation](https://archive.org/stream/IbnAsSalaahSIntroductionToTheScienceOfHadeeth/Ibn-as-Salaah-s-Introduction-to-the-Science-of-Hadeeth_djvu.txt)
- **Quran Foundation (quran.com) Content APIs.**
  - Access: OAuth2 client credentials with `scope=content`; tokens last 3600 s; the headers `x-auth-token` and `x-client-id` are required; the secret is kept on the backend only. The pre-live environment holds only surahs 1 and 2; production needs approved permissions.
  - "Integrity of Translations": disable automatic browser translation, and mark Quranic text containers with `translate="no"`.

  — [QF quickstart](https://api-docs.quran.foundation/docs/quickstart/); [Content APIs v4](https://api-docs.quran.foundation/docs/content_apis_versioned/4.0.0/content-apis/)
- **QF Developer Terms** (last updated 11 Oct 2026):
  - "The text of the Quran is not modified in any way"; no selling, sublicensing or redistribution; snippets must preserve "original context and meaning".
  - Developers must not "cache or store QF Content longer than 1 week unless it is obtained and maintained through the Content Sync APIs" (a resync is required at least every 7 days).
  - No use of QF content "to build ... machine-learning models without written consent".
  - "Retrieval-augmented generation (RAG) within the Application is distinct from using QF Content ... to build a machine-learning model", but content-derived embeddings "that reproduce or permit reconstruction" stay under the storage and use restrictions.
  - Derived Materials, which include "AI-generated responses", are subject to the same restrictions if they reproduce content.
  - A public privacy policy is required; breaches must be reported within 24 hours; governing law is New York.

  — [QF Developer Terms](https://api-docs.quran.foundation/legal/developer-terms/)
- A Quran.com MCP server (origin `https://mcp.quran.ai`) was connected in this research environment. It exposes fetch, search, tafsir, translation and morphology tools with mandatory "grounding rules" for Quran claims. This was observed in the tool configuration, not in published documentation.
- **sunnah.com API.** Data is "a portion of our data", added "as we complete manual checks". An API key is requested by opening a GitHub issue; an "offline dump" is "not available yet". The OpenAPI spec uses the base URL `https://api.sunnah.com/v1/` and the header `X-API-Key`. Endpoints cover collections, books, chapters, hadiths, `/hadiths/refs?refs=bukhari:1,...` and lookup by URN; page size is at most 100. Each hadith's `grades` array carries `graded_by` and `grade`. — [sunnah.com/developers](https://sunnah.com/developers); [spec.v1.yml](https://github.com/sunnah-com/api/blob/master/spec.v1.yml). Requesters on GitHub have offered limits such as "2 requests/second, 1,000 requests/day" in their key requests; these are requester proposals, not published limits. — [issue #2849](https://github.com/sunnah-com/api/issues/2849)
- **dorar.net (الموسوعة الحديثية) API.**
  - Endpoint: `GET https://dorar.net/api/v1/hadith/search`, authorised with `Authorization: Bearer <token>`.
  - Access: request a token with a form stating who you are, your contact, the purpose and the beneficiary, and agree to "إتاحة وصول لمراجعة العمل قبل نشره" (give access to review the work before it is published). Requests are reviewed by hand.
  - Parameters: `q` (2 to 200 characters); `limit` (1 to 20, default 15); `degree` filter, where 1 = graded sahih by the muhaddithun, 2 = isnad graded sahih, 3 = graded da'if, 4 = isnad graded da'if; `match` = any | all | phrase.
  - Each result returns text, narrator, `muhaddith` (the grader), source book, page or number, `grade` (for example "[صحيح]") and links to sharh, similar narrations and usul.

  — [dorar.net API page](https://dorar.net/index.php/api-services/hadith). The older JSONP endpoint (`dorar_api.json?skey=`) returned HTML and had no documentation, which led to community wrappers. — [AhmedElTabarani/dorar-hadith-api](https://github.com/AhmedElTabarani/dorar-hadith-api/)
- **fawazahmed0/hadith-api.** "Free Hadith API Service with Multiple Languages and Multiple Grades". Licence: The Unlicense. "No Rate limits"; served from the jsDelivr CDN (`/editions`, `/editions/{edition}/{n}`, `/info` with grades and references); README warns to include a fallback mechanism. — [GitHub](https://github.com/fawazahmed0/hadith-api)

### Inferences
- **The verses as a design specification:**
  - 49:6 conditions verification on the *bearer's* reliability: a report from a fasiq is investigated, not rejected outright. This is exactly a per-source reliability prior that sets how much evidence is needed.
  - 16:43 names *whom* to ask: those who know, which for the deen means MIZAN's own scholarly sources and qualified scholars, never the open web. MIZAN already enforces this.
  - 17:36 is the abstention rule: when no source settles a claim, say so. "Allahu a'lam" under the answer is the right behaviour.
  - Muslim 5 forbids the "pass everything on" failure, which is what an LLM's ungrounded answer is.
- **Grades are themselves provenance.** A dorar.net or sunnah.com grade is a *named muhaddith's* judgement (`muhaddith`, `graded_by`). MIZAN should store the grade as an attributed annotation (who graded, in which book). Where graders differ, show the disagreement with names rather than collapsing it into one label. This is the Dawid-Skene "annotator" view, but MIZAN must *not* "infer" a grade statistically over scholars' judgements: in the deen the scholars' verdicts are reported, not re-estimated.
- **MIZAN's Isnad tiers versus classical terms.** MIZAN uses sahih, hasan, da'if and mawdu' as *its own* evidence grades for model claims. To avoid confusion with real hadith grades, the UI should label them as MIZAN's grading of an answer, not a hadith verdict. A hadith quoted from a collection should show the collection's or grader's grade separately.
- **Terms compliance check needed.** Fihris downloads the Quran once into `$MIZAN_DATA_DIR/quran`. If any of that text, translation or index comes from QF APIs, keeping it longer than 7 days without Content Sync, or keeping reconstructable embeddings or indexes, would breach the QF terms. If it comes from sources with other licences (for example Tanzil), it must follow those. Verify which source each view uses. The QF "no ML training without written consent" clause also bars using QF content as Ruh training data.
- **Programmatic deen sources by trust level** (inference):
  1. local pinned copies with licences (Quran text; hadith-api editions);
  2. sunnah.com (manually checked, with graders);
  3. dorar.net (largest graded corpus, Arabic, reviewed access);
  4. QF APIs for translations and tafsir under their caching terms.

  The web is never on this list.

### Gaps
- I did not fetch a primary Arabic source for the variant reading of 49:6 (فتثبتوا in some qira'at, which matches MIZAN's "Tathabbut" naming). It is commonly cited but unverified here.
- sunnah.com's actual rate limits and its licence for reuse of API data are not published on the developer page.
- dorar.net's API page lists no explicit licence, caching rule or rate limit beyond `limit ≤ 20` and the review requirement.
- No primary source was retrieved on how classical scholars applied 16:43 beyond the ayah's context; tafsir was out of scope.

## 7. Safety: prompt injection and poisoning through retrieved pages (and defences), and privacy of what is asked of outside services

### Takeaway
Retrieved pages are an attack surface. Five injected texts make a RAG system give an attacker's answer 90% to 97% of the time. Adaptive attackers broke 12 published defences at over 90% success, and human red-teamers succeeded in 100% of scenarios. Only *architectural* separation holds up: CaMeL-style control/data-flow separation with capabilities, plan-then-execute, and quarantined reading. CaMeL solved 77% of AgentDojo tasks with provable security, against 84% undefended. Privacy leaks through the *queries themselves*: an adversary who sees only a deep-research agent's web queries or network metadata can recover over 73% of a prompt's functional content. Ahl al-Dhikr's design (the model never controls tools, outside text is data, nothing a source says is written into the answer) matches the strong patterns. Its remaining exposures are what gets *kept* in `ilm` (memory poisoning) and what claims are sent to search engines.

### Cited Findings
- **PoisonedRAG** (USENIX Security 2025). Injecting 5 malicious texts per target question into a database of millions gave a 90% attack success rate; on NQ (2,681,468 clean texts), black-box, it reached 97%. The defences evaluated "are insufficient". Attackers can poison by "maliciously editing Wikipedia pages" or hosting web pages. — [USENIX PDF](https://www.usenix.org/system/files/usenixsecurity25-zou-poisonedrag.pdf); [arXiv 2402.07867](https://arxiv.org/html/2402.07867v3)
- **The Attacker Moves Second** (Nasr, Carlini, Tramèr et al., arXiv Oct 2025; USENIX Security 2026). Gradient, RL, random-search and human attacks "bypass 12 recent defenses ... with attack success rate above 90% for most", most of which "originally reported near-zero attack success rates". Human red-teaming succeeded in 100% of scenarios against 69% for automated search. Lessons: "small static evals can be misleading", and "model-based auto-raters can be unreliable". — [arXiv 2510.09023](https://arxiv.org/abs/2510.09023); [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/nasr)
- **CaMeL** (Google DeepMind, arXiv Mar 2025). It extracts control and data flow from the trusted query so that "the untrusted data retrieved by the LLM can never impact the program flow". Capabilities, metadata tracking the sources and allowed recipients of each value, enforce policies at tool calls. It builds on the Dual-LLM pattern, in which a privileged LLM sees only the user query and a quarantined LLM with no tools reads the untrusted data. Result: 77% of AgentDojo tasks solved "with provable security" against 84% undefended. — [arXiv 2503.18813](https://arxiv.org/html/2503.18813v2)
- **Design patterns** (2025). "Once an LLM agent has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions". Outputs must not exfiltrate (for example "via embedded links") or manipulate "future agent behavior". Plan-then-execute gives control-flow integrity, but injected data can still alter the *content* of planned actions. — [arXiv 2506.08837](https://arxiv.org/html/2506.08837v3)
- **RTBAS** (Feb 2025) applies information-flow control to tool agents. It prevented all targeted attacks on AgentDojo with only a 2% utility loss and asks the user only when integrity or confidentiality cannot be ensured. — [arXiv 2502.08966](https://doi.org/10.48550/arxiv.2502.08966)
- **Memory poisoning through web content.** Attackers can get agents to write attacker content into persistent memory (e.g. `MEMORY.md`). "Completion-style" attacks, which frame the memory write as necessary to finish the task, succeeded against six models in at least one setting. — [ACM, "Poisoning LLM Agent Memory via Web Content"](https://dl.acm.org/doi/pdf/10.1145/3833142.3833192) (details limited to the abstract excerpt)
- **Multi-agent composition.** A 2026 preprint studies whether CaMeL's guarantees compose across agents and proposes a protocol that "preserves provenance across agent" boundaries. — [arXiv 2610.05640](https://arxiv.org/html/2610.05640)
- A 2026 layered RAG defence (TriShieldRAG: ingest guard, trust-aware re-ranking, a third layer) reports "one blind spot" in layered defences. — [arXiv 2607.23838](https://arxiv.org/html/2607.23838v2) (abstract only seen)
- **LLMs readily adopt coherent external evidence over their own knowledge**, which amplifies poisoning. — [Xie et al., arXiv 2305.13300](https://arxiv.org/abs/2305.13300)
- **Query privacy:**
  - MosaicLeaks treats an agent's web queries as the leakage channel. An adversary seeing only cumulative queries tries to infer intent and private answers, and individually harmless fragments become revealing together (the "mosaic effect"). — [MosaicLeaks](https://alexgurung.me/mosaicleaks/)
  - Passive network observers (DNS resolvers, ISPs, proxies) watching web and research agents, which visit 70 to 140 domains per request, recovered "over 73% of the functional and domain knowledge of user prompts" and up to 19 of 32 latent traits across sessions. Constraining domain diversity or obfuscating traces cut attack effectiveness by an average of 29% at negligible utility cost. — [arXiv 2508.20282](https://arxiv.org/html/2508.20282v3)
  - Tool-orchestration leakage: an agent combines innocuous fragments from several tools into a sensitive inference. Six LLMs averaged a 62.11% overall leakage rate; the best mitigation reached an H-Score of 79.20%. — [arXiv 2512.16310](https://arxiv.org/html/2512.16310v2)
  - AgentDAM (NeurIPS 2025 Datasets & Benchmarks) found web agents on GPT-4, Llama-3 and Claude "prone to inadvertent use of unnecessary sensitive information", against the principle of data minimisation. — [NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/file/c9826b9ea5e1b49b256329934a578d83-Paper-Datasets_and_Benchmarks_Track.pdf)
- **Wikimedia rules for an agent that asks Wikipedia.**
  - An informative User-Agent with contact information is required, or "you may be IP-blocked without notice"; requests should be made in series.
  - REST API, unauthenticated: concurrency ≤ 3 and < 5 requests/s; authenticated: 10 requests/s.
  - Action API, unauthenticated: concurrency 1 and < 5 requests/s.
  - Prefer dumps; high-volume external users should use Wikimedia Enterprise.
  - Operators must "follow the requirements of the content licenses when republishing downloaded or cached data" and must not spread requests over multiple user agents.

  — [MediaWiki API:Etiquette](https://www.mediawiki.org/wiki/API:Etiquette); [Wikitech Robot policy, 16 Mar 2026](https://wikitech.wikimedia.org/wiki/Robot_policy); [WMF API Usage Guidelines](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines/en)

### Inferences
- **Where Ahl al-Dhikr already matches the strong patterns:**
  - The model never chooses tools (CaMeL and plan-then-execute).
  - Outside text is fenced as data (Amanah).
  - Verdicts come from MIZAN's NLI, not from the LLM reading the page (quarantined reading).
  - Nothing from a source is written into the answer text, which is shown under the answer.
  - Deen questions never touch the web.
- **Gap 1: poisoned facts kept in `ilm`.** One web page settles a claim and is then reused for that user "asked once" forever, and shown to Lisan as "SETTLED BY MIZAN". That is the PoisonedRAG and memory-poisoning path. Mitigations, all CPU-only:
  1. require independent corroboration (two or more non-copied sources, section 3) before an entry is *kept*, while showing single-source results under the answer only;
  2. give web-search snippets a lower reliability prior than encyclopedic pages, and learn per-domain reliability from verified outcomes;
  3. expire or re-verify entries by the validity model (section 4);
  4. run Amanah on stored sentences at write time *and* at read time, since detection models improve;
  5. record the page revision or ETag so a later edit can be detected.
- **Gap 2: what claims reveal to search engines.** Each da'if claim, sent as a query, can carry the user's private context (names, health, money, location). Mitigations:
  - **Data minimisation**: send only the claim's distinctive entity words (the same IDF information gate), never the user's message.
  - **No personal entities**: strip anything Daftar knows to be personal (the user's own notes and names) before sending.
  - **Fewer, grouped queries**: send them through one egress (the EAVer pattern also reduces the mosaic).
  - **Prefer local corpora first**: keep a local Wikipedia dump or index for the user's languages, which Wikimedia itself recommends over live requests.
  - **Disclose**: list in "Sources asked" exactly which outside services saw which query, as part of Sakk receipts.
- **Evaluation.** Do not trust static injection benchmarks alone (Nasr et al.). Imtihan's agentic block should include adaptive, human-written poisoning pages aimed at Ahl al-Dhikr: pages crafted to pass the information gate and be read as entailment. The pass criterion is that the user's `ilm` stays unpoisoned.

### Gaps
- No source measured poisoning against a pipeline like MIZAN's, where an NLI model rather than an LLM reads the page and nothing is executed. The NLI step may be easier to fool with crafted entailing sentences, but no study was found.
- The ACM memory-poisoning paper's full results (models, rates) were not available beyond the abstract excerpt.
- No source quantified query-privacy leakage for *single-claim* verification queries; MosaicLeaks and the network study concern multi-step deep-research agents.
