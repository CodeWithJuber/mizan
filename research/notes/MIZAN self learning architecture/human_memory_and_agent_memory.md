# Human memory science and AI agent memory: a mathematically specified basis for MIZAN's per-user and global memory and learning (as of October 2026)

Scope note for the report writer: MIZAN today stores chat messages in SQLite and recalls a user's earlier statements by IDF-weighted word overlap: a statement is recalled when it holds more than half of the request's distinctive information. It also keeps Daftar notes with provenance, does true forgetting (Mahw), and stores per-user learned items: Hifz programs, Ta'allum wordings and Tajriba repair lessons. Its code already has the needed primitives in `backend/core/adaptive.py`: `actr_activation(ages, decay=0.5)`, `activation_weight(threshold=-6.0, noise=0.5)`, Beta posteriors, EW stats, BM25, Thompson sampling and Wilson bounds. `backend/memory/dhikr.py` (line ~205) still uses a fixed half-life rule, `half_life_hours = importance * 720` (at most 30 days), and `0.5 ** (hours / half_life)`. Throughout these notes, "Inferences" maps the science onto those pieces. Claims recalled from well-known primary papers are linked to the paper (DOI or arXiv). Items not re-checked in this session are marked "(not re-verified this session)".

## 1. Human memory models and their mathematics

### Takeaway
Human memory is several cooperating systems, and most of their behaviour has compact equations MIZAN can run on CPU:
- **Limited working memory**: about 4 chunks.
- **Fast hippocampal episodic store**: one-shot, pattern-separated.
- **Slow semantic store**: neocortical, interleaved learning.
- **Consolidation by replay**: prioritised by surprise, reward and need.
- **Retrieval as a rewrite opportunity**: reconsolidation.
- **Power-law forgetting**: equivalently, a mixture of exponentials.
- **Rational need-probability retrieval**: ACT-R base-level activation plus cue association.
- **Spacing-dependent stability growth**: SM-2 and FSRS.
- **Drifting temporal context**: TCM.

### Cited Findings

**Working memory**
- Cowan argues short-term memory capacity is about 4 chunks (range roughly 3–5) once rehearsal and chunking are prevented. This is a revision of Miller's "7±2". — [Cowan 2001, BBS](https://doi.org/10.1017/S0140525X01003922); [Miller 1956](https://doi.org/10.1037/h0043158)
- Baddeley's multicomponent model has three parts: a central executive, a phonological loop and a visuospatial sketchpad. In 2000 he added the **episodic buffer**, a limited-capacity store that binds information from the subsystems and from long-term memory into integrated episodes. — [Baddeley 2000, TICS](https://doi.org/10.1016/S1364-6613(00)01538-2)
- LLM analogue: accuracy is highest when the relevant information sits at the start or end of a long context and drops when it sits in the middle ("lost in the middle"). — [Liu et al. 2023/TACL 2024](https://arxiv.org/abs/2307.03172)

**Episodic vs semantic memory (Tulving)**
- Episodic memory is memory for personally experienced events located in subjective time and place ("what–where–when"), with autonoetic (re-experiencing) awareness. Semantic memory is context-free knowledge of facts. — [Tulving 2002, Annu. Rev. Psychol.](https://doi.org/10.1146/annurev.psych.53.100901.135114)
- The CoALA framework applies the same taxonomy to language agents: working memory, plus episodic, semantic and procedural long-term memory. Actions are split into internal ones (retrieve, reason, learn) and external ones. — [Sumers et al. 2023, CoALA](https://arxiv.org/abs/2309.02427)

**Complementary learning systems (CLS)**
- McClelland, McNaughton & O'Reilly argue that one system cannot do both rapid acquisition and structured generalisation. The hippocampus stores sparse, pattern-separated traces quickly. The neocortex learns slowly through interleaved presentation, which avoids the **catastrophic interference** that focused new learning causes in distributed networks. Hippocampal reinstatement over time trains the neocortex. — [McClelland, McNaughton & O'Reilly 1995, Psych. Rev.](https://doi.org/10.1037/0033-295X.102.3.419); [McCloskey & Cohen 1989](https://doi.org/10.1016/S0079-7421(08)60536-8)
- Kumaran, Hassabis & McClelland (2016) update CLS:
  - Information consistent with an existing schema can enter neocortex rapidly.
  - Hippocampal replay can be weighted toward salient (rewarding or surprising) experiences rather than played uniformly.
  - The theory maps directly onto AI experience replay, for example the DQN replay buffer.
  — [Kumaran, Hassabis & McClelland 2016, TICS](https://doi.org/10.1016/j.tics.2016.05.004)
- Schema effect in rats: when rats already had a spatial schema, they learned new flavour–place pairs in a single trial, and these became hippocampus-independent within about 48 h. Without a schema this took weeks. — [Tse et al. 2007, Science](https://doi.org/10.1126/science.1135935)
- SLIMM model: schema-congruent information is integrated quickly via medial prefrontal cortex. Incongruent, novel information relies on the medial temporal lobe and is consolidated slowly. — [van Kesteren et al. 2012, TINS](https://doi.org/10.1016/j.tins.2012.02.001)

**Systems consolidation, sleep and replay**
- Hippocampal place cells that fired together during exploration showed an increased tendency to fire together during subsequent sleep. This was the first ensemble evidence for replay. — [Wilson & McNaughton 1994, Science](https://doi.org/10.1126/science.8036517)
- Sequence replay during slow-wave sleep is time-compressed, about 20× in rat hippocampus (not re-verified this session). Awake rest also shows **reverse** replay of just-run trajectories. — [Lee & Wilson 2002, Neuron](https://doi.org/10.1016/S0896-6273(02)01096-6); [Foster & Wilson 2006, Nature](https://doi.org/10.1038/nature04587)
- Active systems consolidation during sleep: slow oscillations, spindles and ripples coordinate hippocampal replay with neocortical plasticity. Sleep benefits declarative memories, especially ones expected to be relevant later. — [Rasch & Born 2013, Physiol. Rev.](https://doi.org/10.1152/physrev.00032.2012)
- Synaptic homeostasis hypothesis: sleep globally downscales synapses strengthened during waking. This acts as selective forgetting that improves signal-to-noise. — [Tononi & Cirelli 2014, Neuron](https://doi.org/10.1016/j.neuron.2013.12.025)
- Normative replay prioritisation: an experience's replay value is **gain × need**. Gain is how much the replay would improve the policy. Need is how likely the state is to be visited again (the successor representation). — [Mattar & Daw 2018, Nat. Neurosci.](https://doi.org/10.1038/s41593-018-0232-z)
- AI counterpart, prioritised experience replay:
  - Sampling: `P(i) = p_i^α / Σ_k p_k^α`, with `p_i = |δ_i| + ε` (TD-error magnitude).
  - Bias correction: importance weights `w_i = (N·P(i))^(−β)`.
  — [Schaul et al. 2016](https://arxiv.org/abs/1511.05952)

**Reconsolidation**
- A consolidated auditory fear memory became labile again when it was reactivated. Infusing the protein-synthesis inhibitor anisomycin into the lateral and basal amygdala right after reactivation caused amnesia. Infusion without reactivation did not. So retrieval re-opens a trace for modification. — [Nader, Schafe & LeDoux 2000, Nature](https://doi.org/10.1038/35021052)
- Boundary condition: reactivation destabilises a memory only when the reminder carries a **prediction error**, a mismatch between what was expected and what happened. — Sevenster, Beckers & Kindt 2013, *Science* 339:830 ([PubMed search](https://pubmed.ncbi.nlm.nih.gov/?term=Sevenster+Beckers+Kindt+2013+prediction+error+amnesia)) (not re-verified this session)

**Forgetting curves**
- Ebbinghaus measured savings in relearning nonsense syllables. Savings were about 58% after 20 min, 44% after 1 h, 36% after about 9 h, 34% after 1 day, 28% after 2 days, 25% after 6 days and 21% after 31 days. He fitted `b = 100·k / ((log10 t)^c + k)` with t in minutes, k = 1.84 and c = 1.25. — [Ebbinghaus 1885, trans. 1913 (Classics in the History of Psychology)](https://psychclassics.yorku.ca/Ebbinghaus/index.htm)
- A single-subject replication over about 70 hours of testing reproduced the curve. It showed a bump at 24 h, attributed to sleep. — [Murre & Dros 2015, PLOS ONE](https://doi.org/10.1371/journal.pone.0120644)
- Forgetting is described better by a **power function** `m(t) = a·t^(−b)` (or `a·(1+t)^(−b)`) than by an exponential. Jost's law: of two traces of equal strength, the older one decays more slowly. — [Wixted & Ebbesen 1991, Psych. Sci.](https://doi.org/10.1111/j.1467-9280.1991.tb00175.x); [Wixted 2004, Annu. Rev. Psychol.](https://doi.org/10.1146/annurev.psych.55.090902.141555)
- Rational analysis: across environments (newspaper headlines, child-directed speech, e-mail), the probability that an item is needed again follows power functions of recency and frequency. Memory's forgetting matches the statistics of need. — [Anderson & Schooler 1991, Psych. Sci.](https://doi.org/10.1111/j.1467-9280.1991.tb00174.x)

**ACT-R declarative memory**
- Base-level activation: `B_i = ln( Σ_{j=1..n} t_j^(−d) ) + β_i`. Here t_j is the time since the j-th presentation and d ≈ 0.5 is the default decay.
- Total activation: `A_i = B_i + Σ_j W_j·S_ji + ε`. The associative strength is `S_ji = S − ln(fan_j)` (the fan effect), and ε is logistic noise with scale s.
- Retrieval probability: `P_i = 1 / (1 + e^(−(A_i − τ)/s))`, with retrieval threshold τ.
- Latency: `T_i = F·e^(−A_i)`.
- Optimised-learning approximation for n presentations over lifetime L: `B_i ≈ ln( n/(1−d) ) − d·ln L`.
— [ACT-R 7 Reference Manual](http://act-r.psy.cmu.edu/actr7.x/reference-manual.pdf); [Anderson et al. 2004, Psych. Rev.](https://doi.org/10.1037/0033-295X.111.4.1036)
- Fan effect: the more facts are associated with a concept, the slower and less accurate retrieval of any one of them becomes. — [Anderson 1974, Cogn. Psych.](https://doi.org/10.1016/0010-0285(74)90021-8)
- Pavlik & Anderson's spacing model:
  - Each presentation's decay depends on the activation at the time it occurred: `m_n = ln( Σ_i t_i^(−d_i) )`, with `d_i = c·e^(m_{i−1}) + α`.
  - Practice at high activation (massed practice) therefore decays faster, and the spacing effect falls out of this mechanism.
  — [Pavlik & Anderson 2005, Cognitive Science (record)](https://digitalcommons.memphis.edu/facpubs/8387). The fitted c and α were not verified (see Gaps).

**Spacing effect and optimal review**
- In a large study with retention intervals up to 1 year, the optimal gap between study sessions was about 10–20% of the retention interval for intervals near a week. The optimal ratio fell to about 5–10% for a year. Too short a gap hurt more than too long a gap. — [Cepeda et al. 2008, Psych. Sci. "temporal ridgeline"](https://doi.org/10.1111/j.1467-9280.2008.02209.x); meta-analysis [Cepeda et al. 2006, Psych. Bull.](https://doi.org/10.1037/0033-2909.132.3.354)
- Retrieval practice (testing) produces better long-term retention than restudy. — [Roediger & Karpicke 2006, Psych. Sci.](https://doi.org/10.1111/j.1467-9280.2006.01693.x)
- Pimsleur's graduated-interval recall: 5 s, 25 s, 2 min, 10 min, 1 h, 5 h, 1 day, 5 days, 25 days, 4 months, 2 years. Each interval is about 5× the previous one. — [Pimsleur 1967, Modern Language Journal](https://doi.org/10.1111/j.1540-4781.1967.tb06700.x)
- SuperMemo SM-2 (1987):
  - Intervals: `I(1)=1`, `I(2)=6`, `I(n)=I(n−1)·EF` days.
  - Easiness update: `EF' = EF + (0.1 − (5−q)·(0.08 + (5−q)·0.02))`, floored at 1.3.
  - A quality grade q < 3 restarts repetitions without changing EF.
  — [Woźniak, SM-2 algorithm](https://super-memory.com/english/ol/sm2.htm)
- Half-life regression (Duolingo):
  - Recall probability: `p = 2^(−Δ/h)`, with learned half-life `ĥ = 2^(Θ·x)` (x = features such as counts of correct and incorrect reviews).
  - Loss: `ℓ = (p − p̂)² + α(Δ/log₂p − ĥ)²`, plus a regulariser on Θ.
  — [Settles & Meeder 2016, ACL](https://aclanthology.org/P16-1174/)
- **FSRS** models each card by three variables: **D**ifficulty (1–10), **S**tability (the interval at which R = 90%) and **R**etrievability. Optimal scheduling grew out of the stochastic-shortest-path formulation in [Ye, Su & Cao 2022, KDD (SSP-MMC)](https://doi.org/10.1145/3534678.3539081). Formulas from the [FSRS wiki, "The Algorithm"](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm):
  - **FSRS-6 forgetting curve**: `R(t,S) = (1 + factor·t/S)^(−w20)`, with `factor = 0.9^(−1/w20) − 1`, so that `R(S,S) = 0.9`. The decay w20 is trainable. In FSRS-4.5 the constants were fixed at DECAY = −0.5 and FACTOR = 19/81.
  - **Interval** for desired retention r (FSRS-4.5 form): `I(r,S) = (S/FACTOR)·(r^(1/DECAY) − 1)`. With FSRS-6's curve this becomes `I(r,S) = (S/factor)·(r^(−1/w20) − 1)`, derived by inverting R.
  - **Initial stability**: `S0(G) = w_{G−1}`, where G ∈ {1 Again, 2 Hard, 3 Good, 4 Easy}.
  - **Initial difficulty** (FSRS-5): `D0(G) = w4 − e^(w5·(G−1)) + 1`.
  - **Difficulty update** (FSRS-5): `ΔD = −w6·(G−3)`, then linear damping `D' = D + ΔD·(10−D)/9`, then mean reversion `D'' = w7·D0(4) + (1−w7)·D'`.
  - **Stability after successful recall** (listed in the wiki's v4 section and carried forward): `S'_r = S·( e^(w8)·(11−D)·S^(−w9)·(e^(w10·(1−R)) − 1)·w15[G=2]·w16[G=4] + 1 )`.
  - **Stability after a lapse**: `S'_f = w11·D^(−w12)·((S+1)^(w13) − 1)·e^(w14·(1−R))`.
  - **Same-day review** (FSRS-6): `S' = S·e^(w17·(G−3+w18))·S^(−w19)`. S grows faster when it is small and converges at SInc = 1.
  - **FSRS-6 default parameters** w0..w20 = [0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542].

**Search of Associative Memory (SAM) and Temporal Context Model (TCM)**
- SAM:
  - Sampling: `P_S(I_i | Q) = Π_j S(Q_j,I_i)^(W_j) / Σ_k Π_j S(Q_j,I_k)^(W_j)`. This is a softmax over log-strengths summed across cues.
  - Recovery: `P_R(I_i | Q) = 1 − exp(−Σ_j W_j·S(Q_j,I_i))`.
  - Retrieval fails after K_max unsuccessful samples.
  — [Raaijmakers & Shiffrin 1981, Psych. Rev.](https://doi.org/10.1037/0033-295X.88.2.93)
- TCM:
  - Context drifts as `t_i = ρ_i·t_{i−1} + β·t_i^IN`, where t_i^IN is the input retrieved by the current item.
  - `ρ_i = sqrt(1 + β²[(t_{i−1}·t_i^IN)² − 1]) − β·(t_{i−1}·t_i^IN)` keeps ‖t_i‖ = 1.
  - Items are bound to context by Hebbian outer-product matrices M^{FT} and M^{TF}. Recalling an item retrieves its encoding context, which cues neighbours.
  - This explains recency and the **contiguity effect**: the lag-conditional response probability peaks at ±1, with a forward asymmetry.
  — [Howard & Kahana 2002, J. Math. Psych.](https://doi.org/10.1006/jmps.2001.1388); its extension CMR adds source context and semantic organisation: [Polyn, Norman & Kahana 2009, Psych. Rev.](https://doi.org/10.1037/a0014420)
- Event segmentation theory: people segment experience into events at points where prediction error rises, and boundaries organise later memory. — [Zacks et al. 2007, Psych. Bull.](https://doi.org/10.1037/0033-2909.133.2.273)
- EM-LLM applies this to LLMs. It segments the token stream into episodic events where **Bayesian surprise** (−log P of the token) exceeds a moving threshold of mean + γ·std, refines boundaries with graph modularity, and retrieves by similarity plus **temporal contiguity** (neighbouring events). — [Fountas et al. 2024/ICLR 2025, EM-LLM](https://arxiv.org/abs/2407.09450)

**Schema, prediction error and salience**
- Reward prediction errors (Rescorla–Wagner style `ΔV = αβ(λ − ΣV)`) also enhance **declarative** encoding: events that are surprisingly better or worse are remembered better. — [Ergo, De Loof & Verguts 2020, TICS](https://doi.org/10.1016/j.tics.2020.02.009)
- Emotional arousal enhances consolidation through amygdala and noradrenergic modulation of hippocampal and cortical storage. Arousing events are retained better over long delays. — [McGaugh 2004, Annu. Rev. Neurosci.](https://doi.org/10.1146/annurev.neuro.27.070203.144157)
- Interference: retrieving some items from a category suppresses later recall of related but unpractised items (retrieval-induced forgetting). — [Anderson, Bjork & Bjork 1994, JEP:LMC](https://doi.org/10.1037/0278-7393.20.5.1063)

### Inferences
(These are design inferences for MIZAN drawn from the findings above. They are not claims made by the sources.)

- **Retrieval should be Bayesian need-probability, not a fixed overlap threshold.** ACT-R's `A = B + Σ W·S` is a log-odds of need: base-level (recency × frequency prior) plus cue association (likelihood). Anderson & Schooler (1991) give this its normative reading. Proposed recall score for memory item m and query q:
  `logit P(m needed | q, ctx) = θ0 + θ1·B_m + θ2·ŝ_lex(m,q) + θ3·ŝ_sem(m,q) + θ4·cos(c_now, c_m) + θ5·log(1+salience_m) − θ6·ln(fan_m)`
  - `B_m = ln Σ_j t_j^(−d)` comes from `actr_activation` already in `adaptive.py`. The access times t_j are the times the item was *used* in a verified answer or explicitly confirmed.
  - ŝ_lex is the existing IDF-overlap fraction, or BM25 standardised.
  - ŝ_sem is a cross-lingual embedding cosine. This matters because users write Urdu, Roman Urdu, Arabic and English, where word overlap fails.
  - c is a TCM-style context vector (see below).
  - θ is fitted by logistic regression on implicit labels:
    - Positive: the item was used and the answer verified, or the user did not have to restate.
    - Negative: the item was shown but ignored or contradicted, or the user restated a fact MIZAN failed to recall.
  - Inject an item only when expected utility is positive: `P·U_hit > (1−P)·C_false`. Equivalently, threshold at `P* = C_false/(U_hit + C_false)`, learned per user. This replaces the "> ½ of distinctive information" rule and `activation_weight(threshold=−6.0)`.
- **Few, high-precision items.** Cowan's ~4-chunk limit and the lost-in-the-middle finding both argue for injecting a small number of consolidated chunks: a profile chunk, a current-task chunk, and 2–3 episodic items. Place them at the start of the prompt rather than spreading many fragments through it.
- **Replace Dhikr's `importance*720h` half-life with a DSR (FSRS-style) state per memory item.** Each item carries D, S and last-access time, with `R(t) = (1 + f·t/S)^(−w)`.
  - Map "grades" onto observable events:
    - Again: needed but not retrieved (the user restated it or corrected MIZAN).
    - Hard: retrieved but ranked low or partly wrong.
    - Good: retrieved and used in a verified answer.
    - Easy: retrieved with a large margin.
  - Update S with `S'_r` / `S'_f` and D with damping and mean reversion.
  - FSRS's power curve is exactly a Gamma mixture of exponential decays: `∫ e^(−λt)·Gamma(λ; k, θ) dλ = (1 + θt)^(−k)`. Use it rather than one exponential half-life (Wixted's power law).
  - Fit w per user once enough events exist. Use FSRS defaults or a global DP-estimated prior (Section 4) before then.
- **TCM context vector per user (cheap on CPU).**
  - Keep `c_t = ρ·c_{t−1} + β·e_t`, where e_t is the normalised embedding of the current message. Compute ρ from the TCM formula so ‖c‖ = 1, and store c at encoding time with each item.
  - Retrieving an item boosts its temporal neighbours (contiguity). This gives "what else did we discuss then" recall without graph construction.
  - Open a new episode when surprise exceeds μ + γσ of the user's EW stats. `EWStats` already exists, and this is the same rule EM-LLM uses.
- **Reconsolidation → update-on-retrieval.** When a recalled item is used and the user contradicts or refines it (a prediction error), that moment is the point to rewrite the item, with the old version kept as superseded (Section 2, Zep/StateMem). Recall without a mismatch should only refresh B and S.
- **Salience/importance** should be evidence-based rather than an LLM-rated 1–10 scale. Use: (a) the user explicitly asked to remember it (Daftar note); (b) surprise under Qasd's model, `−log P`; (c) emotional or affective markers; (d) downstream reward, i.e. verification success or failure.

### Gaps
- The fitted constants c and α of Pavlik & Anderson (2005) could not be confirmed from accessible sources. Only the functional form is cited.
- Published FSRS-vs-SM-2 benchmark numbers (log-loss/RMSE from the open-spaced-repetition srs-benchmark) were not retrieved, so no accuracy comparison is given.
- Exact replay compression factors and the prediction-error boundary condition for reconsolidation are cited from memory of the primary papers and should be checked before being quoted numerically.
- No source was found that validates FSRS-style DSR updating for *agent memory items* (as opposed to human flashcards). That mapping is an inference to be tested by the evals in Section 5.

## 2. AI agent memory systems 2023–2026 and their benchmark results

### Takeaway
On long-term conversational memory, five designs measurably help:
- Fine-grained fact keys with time-aware queries.
- Write-time update operations with explicit supersession (bi-temporal or state tracking).
- Hybrid lexical, dense and graph retrieval.
- Agentic search over raw history for hard cases.
- Memories distilled from failures as well as successes.

Vendor scores on the original LongMemEval cluster at 94–96% in 2026, but they are not comparable. The harder 2026 benchmarks (LongMemEval-V2, StateMemBench) show large remaining gaps, especially in tracking current versus superseded state.

### Cited Findings

**Architectures**
- **MemGPT/Letta**:
  - OS-style virtual context management. "Main context" (system instructions, a writable working context and a FIFO message queue) is paged against external **recall storage** (the full message history) and **archival storage** (a vector store) through function calls the LLM issues itself.
  - A queue manager issues a memory-pressure warning as the context fills and evicts messages with recursive summarisation (the paper's warning threshold is ~70%; not re-verified this session).
  — [Packer et al. 2023, MemGPT](https://arxiv.org/abs/2310.08560)
- **Letta sleep-time compute**: a primary agent is paired with a **sleep-time agent** that reorganises memory asynchronously (shipped in Letta 0.7.0). — [Letta blog](https://letta.com/blog/sleep-time-compute)
  - The paper reports that offline "sleep-time" pre-computation over a context cuts the test-time compute needed for the same accuracy by about 5× on Stateful GSM-Symbolic and Stateful AIME. The benefit correlates with how predictable the user's query is. — [Lin et al. 2025, "Sleep-time Compute"](https://arxiv.org/abs/2504.13171)
- **Generative Agents**:
  - Retrieval score = α_rec·recency + α_imp·importance + α_rel·relevance. All α = 1, and each term is min-max normalised to [0,1].
  - Recency is exponential decay with factor 0.995 per sandbox hour since the item was last retrieved. Importance is LLM-rated 1–10. Relevance is the embedding cosine.
  - Reflection (synthesising higher-level insights) triggers when the summed importance of recent events exceeds 150.
  — [Park et al. 2023](https://arxiv.org/abs/2304.03442)
- **MemoryBank**: Ebbinghaus-inspired retention `R = e^(−t/S)`. Strength S starts at 1 and increments by 1 each time the memory is recalled, which also resets t. — [Zhong et al. 2023/AAAI 2024](https://arxiv.org/abs/2305.10250)
- **Reflexion**: verbal reinforcement. After a failure the agent writes a self-reflection into an episodic buffer used on the next attempt. It reached 91% pass@1 on HumanEval versus 80% for GPT-4. — [Shinn et al. 2023](https://arxiv.org/abs/2303.11366)
- **A-MEM**: Zettelkasten-style notes. Each note has content, a timestamp, LLM-generated keywords, tags, a context description, an embedding and links. New notes link to their top-k neighbours, selected by an LLM, and **memory evolution** updates the attributes of existing linked notes. — [Xu et al. 2025](https://arxiv.org/abs/2502.12110)
- **Mem0**:
  - Two phases. *Extraction*: an LLM extracts candidate facts from the latest exchange plus a rolling summary. *Update*: for each fact, the LLM compares it with the top-s similar memories and picks ADD / UPDATE / DELETE / NOOP. Mem0^g adds a graph store.
  - Headline claims: about 26% relative LLM-as-judge (J) improvement over OpenAI's memory, 91% lower p95 latency and more than 90% token savings versus full context.
  — [Chhikara et al. 2025](https://arxiv.org/abs/2504.19413)
  - Per a digest of the paper's LoCoMo table: full context scores J ≈ 72.9 with 17.1 s p95 latency; Mem0 scores J ≈ 66.9 with about 1.76K memory tokens and 1.44 s p95. LangMem's search latency is p50 17.99 s and p95 59.82 s. — [Mem0 paper digest](https://yiwei-chen.github.io/paper-digest/summaries/en/mem0.html)
  - Independent re-runs differ. MemR³ reports A-Mem at 69.06 and Zep at 74.62 overall under its own setup, which contradicts Mem0's claim that A-Mem trails by more than 25 J points. — [MemR³](https://arxiv.org/pdf/2512.20237)
  - Mem0's 2026 marketing page claims LoCoMo 92.5%, LongMemEval 94.4% and BEAM 64.1% (vendor figures; methodology not given on the page). — [mem0.ai benchmarks 2026](https://mem0.ai/library/agent-memory/ai-memory-benchmarks-in-2026)
- **Memory-R1** (ACL 2026): the Memory Manager (ADD/UPDATE/DELETE/NOOP) and the Answer Agent (which filters retrieved memories) are trained with outcome-driven RL (PPO/GRPO). With only 152 training QA pairs it beats Mem0 and generalises across LoCoMo, MSC and LongMemEval at 3B–14B scale. Motivating failure: naive systems DELETE+ADD on "adopted a second dog" when they should UPDATE. — [Yan et al., Memory-R1](https://arxiv.org/abs/2508.19828v4)
- **Zep/Graphiti**: a temporally aware knowledge graph. Zep scores 94.8% on DMR versus 93.4% for MemGPT, and on LongMemEval improves accuracy by up to 18.5% while cutting response latency by 90% versus baselines. — [Rasmussen et al. 2025](https://arxiv.org/abs/2501.13956)
  - From the paper body (not re-verified this session):
    - Edges are bi-temporal: valid-time t_valid/t_invalid and transaction-time created/expired.
    - A new contradicting edge invalidates the old one by setting t_invalid rather than deleting it.
    - The graph has episode, semantic-entity and community subgraphs.
    - Retrieval combines cosine, BM25 and breadth-first graph search, with rerankers (RRF, MMR, mention counts, node distance, cross-encoder).
- **HippoRAG**:
  - Offline: OpenIE triples form a KG ("neocortex"). Online: query entities seed **Personalized PageRank** ("hippocampal index"), with node specificity `s_i = 1/|P_i|` (an IDF analogue over passages).
  - Results: up to 20% better multi-hop QA than state-of-the-art retrieval. Single-step retrieval matches iterative IRCoT while being 10–30× cheaper and 6–13× faster.
  — [Gutiérrez et al. 2024 (NeurIPS)](https://arxiv.org/abs/2405.14831)
- **HippoRAG 2** (ICML 2025): integrates passages as nodes in the PPR graph. An embedding model scores passages and triples to seed PPR, and an LLM "recognition memory" filters the triples. It is framed as **non-parametric continual learning**: new knowledge is added without weight updates. It reports about a 7% gain on associative tasks over the best embedding retriever while staying strong on factual and sense-making tasks. — [Gutiérrez et al. 2025](https://arxiv.org/abs/2502.14802)
- **Procedural/skill memory**:
  - Voyager keeps a library of executable, environment-verified code skills retrieved by embedding. It obtained 3.3× more unique items and unlocked tech-tree milestones up to 15.3× faster than prior agents. — [Wang et al. 2023, Voyager](https://arxiv.org/abs/2305.16291)
  - Agent Workflow Memory induces reusable workflows from trajectories, with +24.6% and +51.1% relative success on Mind2Web and WebArena. — [Wang et al. 2024, AWM](https://arxiv.org/abs/2409.07429)
- **ReasoningBank** (Google, 2025):
  - Distils generalisable strategy "memory items" from the agent's self-judged successes **and failures**.
  - Reported gains: up to +8.3% on WebArena and +4.6% on SWE-Bench-Verified over memory-free agents.
  - Adding failures helped ReasoningBank (46.5 → 49.7 on WebArena-Shopping). It did not help success-only designs: Synapse 40.6 → 41.7, AWM 44.4 → 42.2.
  - Memory-aware test-time scaling raised success from 49.7% (k=1) to 55.1% (k=5).
  — [ReasoningBank, arXiv 2509.25140](https://arxiv.org/abs/2509.25140); [Google Research blog](https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/)

**Benchmarks and scores**
- **LongMemEval** (ICLR 2025):
  - 500 curated questions embedded in freely scalable chat histories, testing five abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates and abstention.
  - Commercial assistants and long-context LLMs show about a 30% accuracy drop on information memorised across sustained interactions.
  - The paper splits memory design into **indexing, retrieval and reading**. Its proposed fixes are **session decomposition** (finer value granularity), **fact-augmented key expansion** and **time-aware query expansion**, which it says greatly improve recall and QA.
  — [Wu et al. 2024](https://arxiv.org/abs/2410.10813)
- **LoCoMo**: very long multi-session dialogues, averaging about 300 turns and 9K tokens over up to 35 sessions, with QA (single-hop, multi-hop, temporal, open-domain, adversarial), event summarisation and multimodal dialogue tasks. — [Maharana et al. 2024 (ACL)](https://arxiv.org/abs/2402.17753)
- **State of the art, October 2026**: no independent leaderboard exists.
  - Self-reported LongMemEval figures: Agent Zero Memory 95.60% (+0.73 over the best prior; LoCoMo 93.60%); a self-published repo claims 96.2%; Mastra is reported at 94.87%. — [Agent Zero Memory, arXiv 2608.29606](https://arxiv.org/abs/2608.29606); [agentmemory repo (self-published)](https://github.com/JordanMcCann/agentmemory)
  - Caveat: answer accuracy and retrieval recall@5 are sometimes conflated, for example MemPalace's 96.6% is R@5. — [search synthesis of mem0.ai page and arXiv 2608.17756](https://arxiv.org/pdf/2608.17756)
  - Agent Zero Memory design:
    - Three parallel stores: an episodic "Memory Events" timeline, an entity–event KG, and a curated "Hierarchical Documentary Memory" of durable facts.
    - Every item is provenanced (origin, timestamp, evidence pointer). Answers may cite only evidence actually opened, and the system abstains otherwise.
    - An intent gate skips retrieval on self-contained turns.
    - Across 8 backbone LLMs, accuracy varied by only 3.4 points while per-query cost varied about 30×.
    — [arXiv 2608.29606](https://arxiv.org/abs/2608.29606)
- **LongMemEval-V2** (May 2026):
  - 451 manually curated questions over histories of up to 500 web-agent trajectories (115M tokens). It tests static state recall, dynamic state tracking, workflow knowledge, environment "gotchas" and premise awareness.
  - Results (abstract): a coding-agent memory that stores trajectories as files and searches them in a sandbox (AgentRunbook-C) reaches 72.5%, an off-the-shelf coding agent 69.3%, and the strongest RAG baseline only 48.5%.
  — [Wu et al. 2026](https://arxiv.org/abs/2605.12493)
  - A search summary of an ICML 2026 listing quotes 74.9% for AgentRunbook-C on a small split, and frontier LLMs at ≤14.1% without trajectory evidence. — [ICML 2026 listing](https://icml.cc/virtual/2026/67423). These numbers differ from the abstract; treat 72.5% as authoritative.
- **StateMemBench** (Aug 2026):
  - 234 multi-session scenarios. Each answer is graded as current state, superseded state or other failure.
  - The main failure of existing memory systems is returning a **superseded** state.
  - An explicit state layer (StateMem) raised current-state accuracy from 0.205 to 0.363 (DeepSeek-V4-Flash) and from 0.149 to 0.233 (Qwen-3.5-9B) over the strongest baselines.
  - As a wrapper over six backends it adds 32–67 points, of which 15–32 survive a length- and cost-matched control.
  — [Fan et al. 2026, "Can Agent Memory Systems Track Evolving State?"](https://arxiv.org/abs/2608.19652)

### Inferences
- **What measurably works, ranked by evidence strength for MIZAN's use case:**
  1. **Explicit supersession with valid-time stamps** (Zep invalidation; StateMem's 1.6–1.8× current-state gain; Memory-R1 UPDATE vs DELETE+ADD). MIZAN's recall currently returns any earlier matching statement, so "I moved to Lahore" and "I live in Karachi" can both be recalled. Each semantic fact needs `t_valid_from`, `t_valid_to`, `superseded_by`, and recall should default to the currently valid version while keeping history for "what did I say before?".
  2. **Fact-level keys and time-aware queries** (LongMemEval). Index atomic facts extracted from the user's own words, each with a back-pointer to the message, in addition to whole messages. Expand queries that contain time phrases ("last month", "pichle hafte") into date ranges before matching. MIZAN's Waqt recipe already parses dates.
  3. **Hybrid retrieval**: BM25 (already present) + a small cross-lingual embedding + one PPR step over an entity graph for multi-hop questions (HippoRAG). Node specificity `1/|P_i|` is the same IDF idea MIZAN already uses.
  4. **Write-time update decisions**: ADD/UPDATE/DELETE/NOOP (Mem0, Memory-R1). In MIZAN, Lisan may *propose* the operation, but MIZAN decides it by evidence: bidirectional NLI entailment means duplicate (NOOP or merge); bidirectional contradiction means supersede; otherwise ADD. This is the same NLI rule Ahl al-Dhikr already uses.
  5. **Agentic search over raw history as an escalation path** (LongMemEval-V2: 69–72% vs 48.5% for RAG). When the posterior recall gate finds nothing decisive but the request is clearly memory-seeking, run a bounded grep/BM25 search over the user's full archive before answering "I don't know".
  6. **Strategy memory from failures** (ReasoningBank, Reflexion, AWM). Tajriba (repair lessons) is MIZAN's version. ReasoningBank's ablation suggests storing *failure-derived* lessons too, not only verified successes.
- **Full context remains a strong baseline**: 72.9 vs 66.9 J on LoCoMo, at roughly an order of magnitude more tokens (the Mem0 paper's ">90% token savings"; the full-context count of ~26K tokens is recalled from the paper and was not re-verified this session). For a light user whose whole history fits the model's context cheaply, the right policy may be "recent window + summary + retrieved facts", with Iqtisad deciding by cost. Memory systems trade a few accuracy points for large cost and latency savings.
- **Provenance-locked answers** (Agent Zero: cite only opened evidence, abstain otherwise) match MIZAN's Isnad/Sidq philosophy. A recalled user fact should be graded *sahih* only when its source message still exists and is unsuperseded.
- Memory backbone quality appears to matter more than the answer model (3.4-point spread across 8 LLMs). This supports MIZAN's stance that MIZAN, not Lisan, should own memory.

### Gaps
- Zep's internal design (bi-temporal fields, rerankers) and MemGPT's 70% threshold are from the papers' bodies and were not re-fetched this session.
- The exact LoCoMo table values per system (Mem0 paper) came only via a secondary digest. Third-party re-runs conflict.
- No independent, judge-controlled 2026 leaderboard for LongMemEval or LoCoMo was found. All 94–96% figures are self-reported.
- BEAM (the benchmark in Mem0's 2026 numbers) was not researched: its size, tasks and scoring are unknown here.
- No benchmark found tests memory for **multilingual / code-switched** users (Urdu, Roman Urdu, Arabic, Hindi mixed with English), which is MIZAN's main population.

## 3. Consolidation in AI ("sleep" jobs), dedupe, summarisation, conflict detection, and stability–plasticity

### Takeaway
Episodic-to-semantic consolidation is still the least mature part of agent memory. Surveys describe it as fragile periodic LLM summarisation that loses provenance. A sound design borrows CLS:
- Keep raw episodes immutable.
- Consolidate offline, with prioritised replay.
- Deduplicate and detect conflicts by evidence (MinHash, then NLI).
- Promote facts to semantic memory only on posterior evidence.
- Keep back-pointers.
- Protect high-evidence knowledge from being overwritten (the EWC/stability side).

### Cited Findings
- 2026 surveys organise agent memory as construction, **update** (consolidate/remove) and query, over episodic, semantic and procedural types. — [LLM Agent Memory survey, Preprints 2026](https://www.preprints.org/manuscript/202603.0359)
- Episodic→semantic consolidation is described as the least mature part. It typically needs explicit developer rules or periodic LLM summarisation, "both of which are fragile and hard to validate", and is "rarely automatic". — [Memory for Autonomous LLM Agents, arXiv 2603.07670](https://arxiv.org/abs/2603.07670)
- Governance risks: index bloat from redundant episodic logs (mitigated by forgetting and pruning) and **procedural drift**, where outdated workflows get reinforced. — [SSGM framework, arXiv 2603.11768](https://arxiv.org/html/2603.11768v1)
- The episodic→semantic move is "precisely the loss of source provenance" that systems must guard against. — [Always-On Agents survey, arXiv 2606.30306](https://arxiv.org/pdf/2606.30306)
- Sleep-time compute (offline re-processing of context) reduces test-time compute about 5× at equal accuracy, and helps most when future queries are predictable from the context. — [arXiv 2504.13171](https://arxiv.org/abs/2504.13171)
- Hierarchical summarisation: RAPTOR recursively clusters chunks (Gaussian mixtures over reduced embeddings) and summarises each cluster into a tree retrieved at several levels. It improved the best QuALITY result by 20% absolute accuracy with GPT-4. — [Sarthi et al. 2024](https://arxiv.org/abs/2401.18059)
- Near-duplicate detection:
  - MinHash estimates Jaccard resemblance: `P[h_min(A) = h_min(B)] = J(A,B)`.
  - LSH banding with b bands of r rows makes a pair a candidate with probability `1 − (1 − s^r)^b`, an S-curve with threshold ≈ `(1/b)^(1/r)`.
  — [Broder 1997](https://doi.org/10.1109/SEQUEN.1997.666900); [Leskovec, Rajaraman & Ullman, MMDS ch. 3](http://www.mmds.org/)
- **Stability–plasticity / catastrophic forgetting**: networks trained sequentially overwrite earlier tasks. — [McCloskey & Cohen 1989](https://doi.org/10.1016/S0079-7421(08)60536-8); [French 1999, TICS](https://doi.org/10.1016/S1364-6613(99)01294-2); [Mermillod et al. 2013](https://doi.org/10.3389/fpsyg.2013.00504)
- **EWC** penalises changing parameters important to old tasks: `L(θ) = L_B(θ) + Σ_i (λ/2)·F_i·(θ_i − θ*_{A,i})²`, where F_i is the diagonal Fisher information. — [Kirkpatrick et al. 2017, PNAS](https://doi.org/10.1073/pnas.1611835114)
- Replay-based continual learning: rehearsing a small buffer of old experiences largely prevents forgetting. Generative replay replaces stored data with a generator. — [Rolnick et al. 2019](https://arxiv.org/abs/1811.11682); [Shin et al. 2017](https://arxiv.org/abs/1705.08690)
- Prioritised replay `P(i) ∝ (|δ_i|+ε)^α` with importance correction `(N·P(i))^(−β)`. — [Schaul et al. 2016](https://arxiv.org/abs/1511.05952). Normative "gain × need" prioritisation. — [Mattar & Daw 2018](https://doi.org/10.1038/s41593-018-0232-z)
- Non-parametric continual learning (adding to an external memory without weight updates) is presented as a practical route around catastrophic forgetting. — [HippoRAG 2](https://arxiv.org/abs/2502.14802)
- Sleep downscaling (synaptic homeostasis) as a model for principled forgetting. — [Tononi & Cirelli 2014](https://doi.org/10.1016/j.neuron.2013.12.025)

### Inferences
- **A concrete nightly "Nawm" (sleep) job for MIZAN, per user, CPU-only.** It should run alongside Muhasaba's daily job and honour `stateless.bind()` and Mahw:
  1. **Segment** the day's messages into episodes using the surprise rule (μ + γσ of EW stats, as EM-LLM does) plus explicit chat boundaries.
  2. **Extract candidate facts** only from the user's own words. Lisan proposes atomic facts, each with a character-span back-pointer. MIZAN keeps a fact only if the span exists verbatim or is NLI-entailed by it, and Amanah reports it clean.
  3. **Deduplicate**: MinHash on character 5-grams (language-agnostic), LSH with, for example, b=20 and r=5, which puts the threshold near 0.55. Then confirm with bidirectional NLI entailment. Merge duplicates by adding their access timestamps, so B and S grow; this is rehearsal.
  4. **Detect conflicts**: bidirectional NLI contradiction between facts about the same entity and slot. The later `t_valid_from` supersedes the earlier one, setting `t_valid_to` and `superseded_by`. Nothing is deleted; deletion belongs to Mahw.
  5. **Promote episodic→semantic by evidence.** Model "fact f holds for this user" as `Beta(a0 + n_support, b0 + n_contra)` over *independent* episodes (different days or chats). Promote to the profile when `P(θ > ½) ≥ 0.95` (the regularised incomplete Beta already exists in `adaptive.py`). An explicit "remember this" note promotes immediately (salience).
  6. **Summarise hierarchically** (RAPTOR-like) into a small profile and topic summaries, every line keeping back-pointers. This prevents the provenance loss the surveys warn about, and lets Isnad grade summary claims.
  7. **Consolidate skills**: Hifz programs and Ta'allum wordings verified at least k times across distinct requests are generalised into templates with slots, as in Voyager and AWM. Lessons come from failures as well as successes (ReasoningBank).
  8. **Prioritised re-verification**: pick items for Muhasaba re-checking with `P(i) ∝ p_i^α`. Here `p_i = need_i × gain_i`, where need = the FSRS retrievability of an upcoming use and gain = (1 − verification confidence), plus a recency of contradiction.
  9. **Forget softly**: items with `R(t) < r_min` and a Beta-posterior usefulness below a learned bound move to an archive tier. They are excluded from automatic recall but remain searchable by agentic escalation. This is the synaptic-homeostasis analogue, separate from Mahw's user-ordered erasure.
- **Stability side, for learned wordings, rules and lessons.** Non-parametric memory avoids weight-level catastrophic forgetting, but its analogue is *procedural drift* and *interference*: a new wording overrides a well-proven old one. Make the replacement bar grow with the incumbent's evidence, an EWC-like penalty where Fisher information ≈ the count of verified uses. The challenger replaces the incumbent only if `P(θ_new > θ_old + m(n_old)) ≥ 0.95`. Tajdid already uses `P(better) ≥ 0.95`; adding the evidence-scaled margin `m(n_old)` is the stability term.
- **Plasticity side**: schema-consistent new facts (CLS update, Tse et al. 2007) can enter semantic memory faster. If a new fact fills an *existing* profile slot with a compatible value, a lower promotion bar is justified. A fact that contradicts a well-supported slot should wait for more evidence or ask the user. Reconsolidation says to ask at the moment of mismatch.

### Gaps
- No controlled study was found that measures how much consolidation (versus raw-episode retrieval) improves LongMemEval-type accuracy in isolation. The surveys say this is under-validated.
- The MinHash LSH parameters above are illustrative, from the S-curve formula, and not tuned on MIZAN data.
- Whether small multilingual NLI models (MIZAN's MiniLM-L6 mnli-xnli) are accurate enough on short, code-switched personal facts for dedupe and conflict detection was not researched.

## 4. Global learning across users with privacy

### Takeaway
MIZAN can learn from all users without exposing any one of them by releasing only user-level differentially private aggregates. There are two cases:
- **Public key set** (recipe ids, intents, tools, models): noisy counts suffice and work even with few users.
- **New strings** (new phrasings or templates): add DP partition selection. This needs on the order of 12–45 distinct users per released item at ε ≈ 1. Small self-hosted deployments therefore learn new strings globally only from seeds, admin Ta'lim and explicit opt-in donation, while numeric priors can be shared with DP noise at any size.

### Cited Findings
**Definitions and mechanisms**
- (ε,δ)-DP: `Pr[M(D) ∈ S] ≤ e^ε·Pr[M(D') ∈ S] + δ` for neighbouring datasets D, D'. For user-level DP, D and D' differ in *all* of one user's data.
  - Laplace mechanism: add `Lap(Δ₁/ε)`.
  - Gaussian mechanism: `σ ≥ Δ₂·sqrt(2 ln(1.25/δ))/ε` for ε < 1.
  - Basic composition sums the ε's. Advanced composition over k mechanisms gives `ε' = ε·sqrt(2k ln(1/δ')) + k·ε·(e^ε − 1)`.
  — [Dwork & Roth 2014, Algorithmic Foundations of DP](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf)
- zCDP: the Gaussian mechanism with L2 sensitivity Δ and noise σ is ρ-zCDP with `ρ = Δ²/(2σ²)`. ρ composes additively, and ρ-zCDP implies `(ρ + 2·sqrt(ρ·ln(1/δ)), δ)`-DP. — [Bun & Steinke 2016](https://arxiv.org/abs/1605.02065)
- Rényi DP: (α, ε)-RDP implies `(ε + ln(1/δ)/(α−1), δ)`-DP. — [Mironov 2017](https://arxiv.org/abs/1702.07476)
- DP-SGD: clip each example's gradient to norm C, add Gaussian noise of std σC to the summed batch gradient, and track privacy with the moments accountant. — [Abadi et al. 2016](https://arxiv.org/abs/1607.00133)
- Randomised response (local DP): report the true bit with probability `p = e^ε/(1+e^ε)`. The unbiased population estimate is `π̂ = (λ̂ − (1−p))/(2p − 1)`. — [Warner 1965, JASA](https://doi.org/10.1080/01621459.1965.10480775)
- RAPPOR (Chrome) runs Bloom-filter randomised response: a permanent memoised response plus an instantaneous one. — [Erlingsson, Pihur & Korolova 2014](https://arxiv.org/abs/1407.6981)

**Federated learning and secure aggregation**
- FedAvg: clients run local SGD and the server averages `w_{t+1} = Σ_k (n_k/n)·w^k_{t+1}`. This needed 10–100× fewer communication rounds than synchronous SGD. — [McMahan et al. 2017](https://arxiv.org/abs/1602.05629)
- User-level DP federated training of LSTM language models (DP-FedAvg): with enough users, accuracy is nearly unchanged. — [McMahan et al. 2018](https://arxiv.org/abs/1710.06963)
- Secure aggregation: pairwise additive masks cancel in the sum, so the server sees only the aggregate, even with dropouts. Communication expansion is 1.73× for 2^10 users with 2^20-dimensional vectors and 1.98× for 2^14 users with 2^24 dimensions. — [Bonawitz et al. 2017, CCS](https://eprint.iacr.org/2017/281)
- Federated learning without robust aggregation is vulnerable to poisoning and backdoors from a few malicious clients. — [Bagdasaryan et al. 2020](https://arxiv.org/abs/1807.00459)

**Production deployments**
- Gboard trains next-word-prediction language models with federated learning and DP-FTRL (no uniform client sampling needed). More than twenty LMs reached ρ-zCDP between 0.2 and 2, two of them also with secure aggregation. The first production deployment (Spanish, Feb 2022) had ρ = 0.81. All Gboard neural-network NWP LMs now carry DP guarantees. — [Xu et al. 2023, ACL Industry](https://arxiv.org/abs/2305.18465); [Private FL in Gboard white paper](https://arxiv.org/abs/2306.14793)
- Apple (local DP) uses a Count Mean Sketch, flipping each bit of a one-hot vector with probability `1/(e^(ε/2)+1)`. Emoji use ε = 4 and web domains ε = 8, **per daily submission**, sent without device identifiers. A 2017 analysis argued the budgets accumulate across days and use cases. — [Apple DP Overview](https://www.apple.com/privacy/docs/Differential_Privacy_Overview.pdf); [Apple ML Research 2017](https://machinelearning.apple.com/research/learning-with-privacy-at-scale); [Tang et al. 2017](https://arxiv.org/abs/1709.02753)

**Thresholds and partition selection (releasing *which* strings exist)**
- k-anonymity requires every released record to be indistinguishable from at least k−1 others on quasi-identifiers. — [Sweeney 2002](https://doi.org/10.1142/S0218488502001648)
  - k-anonymity alone fails under homogeneity and background-knowledge attacks, motivating l-diversity. — [Machanavajjhala et al. 2007](https://doi.org/10.1145/1217299.1217302)
  - It gives no formal guarantee comparable to DP (inference; DP's advantage is composition).
- DP partition selection: count the distinct users in each partition (for example each candidate phrase), add noise, and release only partitions above a threshold.
  - The Laplace version drops a partition if `n + Lap(1/ε) < 1 − ln(2δ)/ε`.
  - The optimal mechanism releases with probability `π(n) = min(e^ε·π(n−1) + δ, 1 − e^(−ε)·(1 − π(n−1) − δ), 1)`, with π(0) = 0. For small n, `π(n) = δ·(e^(nε) − 1)/(e^ε − 1)`.
  - Gains over Laplace are significant only for small ε (below 1).
  — [Desfontaines et al. 2022, PoPETs](https://petsymposium.org/popets/2022/popets-2022-0017.php); [thesis chapter](https://desfontain.es/thesis/PartitionSelection.html)
  - Worked from these formulas (computation, not a sourced figure): at ε = 1 and δ = 10⁻⁵, a phrase needs about **12 distinct users** to have a 50% chance of release, under either mechanism.
- 2026 extension: optimal partition selection under Rényi DP, giving tighter composition, plus L2-bounded weighted selection for users who contribute several partitions. — [Harrison & Manurangsi 2026](https://arxiv.org/abs/2603.09167)
- DP set union: releasing the union of users' item sets (vocabularies, n-grams) with user-level DP. — [Gopi et al. 2020](https://arxiv.org/abs/2002.09745)
- Heavy hitters: TrieHH discovers frequent strings prefix by prefix, keeping a prefix only when enough sampled users vote for it. DP comes from sampling plus thresholding (not re-verified this session). — [Zhu et al. 2020](https://arxiv.org/abs/1902.08534)
- Releasing search-query logs privately also relies on threshold + noise. — [Korolova et al. 2009, WWW](https://doi.org/10.1145/1526709.1526733)

**Memorisation and unlearning risk**
- Large language models memorise and can emit verbatim training data, including PII. The "exposure" metric for inserted canaries is `exposure = log₂|R| − log₂ rank(canary)`. — [Carlini et al. 2021](https://arxiv.org/abs/2012.07805); [Carlini et al. 2019, Secret Sharer](https://arxiv.org/abs/1802.08232)
- SISA training (sharded, isolated, sliced, aggregated) allows exact unlearning by retraining only the affected shard. — [Bourtoule et al. 2021](https://arxiv.org/abs/1912.03817)

### Inferences
(Design for MIZAN, a single trusted server, so this is central DP. The adversary is any user or viewer of global artefacts trying to learn about another user.)

- **Unit of privacy = one user per period** (for example a week). Bound each user's contribution before counting: at most m distinct candidate items per period, each counted once per user. Count distinct users, not events.
- **Case A: the key set is public, so no threshold is needed.**
  - Keys include: recipe/intent ids, tool names, agent names, Lisan model ids (Wazn), Furqan check kinds, and seed phrasing ids.
  - Release noisy sufficient statistics with per-user clipping c: `S̃_k = S_k + N(0, σ²)` and `F̃_k = F_k + N(0, σ²)`.
  - Use them as **hierarchical-Bayes priors** for each user: `Beta(κ·μ̃_k + s_{u,k}, κ·(1−μ̃_k) + f_{u,k})`, with `μ̃_k = S̃_k/(S̃_k + F̃_k)` and κ fitted by empirical Bayes (method of moments across users).
  - This gives Majlis (Thompson sampling), Wazn and Qasd a global prior that a new user benefits from immediately. Noise of a few counts is negligible once totals reach the hundreds, so this works even with 10 users.
  - Budget with zCDP: the Gaussian mechanism with sensitivity Δ = c·√(number of keys a user touches) gives ρ = Δ²/(2σ²) per release.
  - Example: weekly releases at ρ = 0.007 give ρ ≈ 0.365 per year, which is ε ≈ 4.9 at δ = 10⁻⁶ by `ε = ρ + 2·sqrt(ρ·ln(1/δ))`. Daily releases at ρ = 0.01 would give ε ≈ 17.9 per year, so release less often.
  - Gboard's ρ of 0.2–2 per model is a useful anchor.
- **Case B: new strings (phrasings, intent examples, program templates, ayah-search synonyms).**
  1. **Canonicalise first**: replace numbers, dates, names, URLs and rare tokens (IDF above the Lughah corpus mean, or not in the seed vocabulary) with typed slots. Only templates are candidates, never verbatim user text (Carlini's memorisation risk).
  2. Count distinct users per template, and require the template to be *verified* (Furqan/Tathabbut pass) for each counted user.
  3. Release with DP partition selection. With m contributions per user, splitting the budget evenly gives threshold `τ = 1 + (m/ε)·ln(m/(2δ))`. Examples (computed): m=1, ε=1, δ=10⁻⁵ → τ ≈ 11.8; m=1, ε=1, δ=10⁻⁶ → τ ≈ 14.1; m=3, ε=1, δ=10⁻⁶ → τ ≈ 43.7. A Gaussian or weighted variant scales better when m > 1.
  4. Released templates enter global Qasd/Ta'allum seeds only after a Ta'lim-style held-out check (`P(worse) < 0.95`).
- **Implication for small deployments**: with N users ≲ 50, almost no new string clears τ. Global learning of new strings should then come from:
  - (a) public data and seeds (MASSIVE, Hugging Face datasets) and admin Ta'lim;
  - (b) **explicit opt-in donation** of specific examples, reviewed by an admin (consent-based, outside DP);
  - (c) Case-A numeric priors, which do work.
  The report should say so plainly rather than promising DP phrase learning on a 5-user server.
- **Poisoning resistance**: the distinct-user threshold also forces a poisoner to control at least τ accounts. Add Amanah screening of candidates and require independent verification per user. Federated-style poisoning attacks show this is needed.
- **Global memory of public facts** (Ahl al-Dhikr results settled against Wikipedia or web sources, Fihris/hadith lookups) contains no user data *in the fact itself*. The fact that someone asked can be sensitive, though, so share such cache entries globally only after stripping the asking context and, if the query itself is distinctive, only once at least τ distinct users have asked.
- **Mahw interplay**: DP releases bound any single user's influence, so a user's erasure does not require recomputing past global releases. Their counts drop out of the next period. Report this honestly as "bounded influence", not "erased", in the Mahw receipt. Any future global *parametric* model (Ruh) needs SISA-style sharding or DP-SGD to make deletion meaningful.

### Gaps
- No published deployment was found of DP partition selection for **small** user bases (tens of users). The small-N conclusion above is computed from the formulas, not observed.
- The exact threshold for users contributing to several partitions under the optimal mechanism, and the 2026 Rényi-DP results, were not extracted numerically.
- TrieHH's precise DP guarantee was not re-verified.
- No source was found on DP for *program-template* learning specifically (versus text n-grams).

## 5. Measuring memory quality and running memory evals

### Takeaway
Memory should be evaluated as a retrieval system and as a belief-tracking system at the same time. That means measuring:
- recall and precision of what is injected;
- answer accuracy by ability (extraction, multi-session, temporal, update, abstention);
- staleness (superseded-state answers);
- interference (accuracy versus fan);
- retention versus age;
- calibration;
- cost and latency;
- privacy leakage across users.

All of it should run under controlled judges, because vendor scores are not comparable.

### Cited Findings
- LongMemEval's five abilities (information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention), its indexing/retrieval/reading decomposition, and its finding that memory optimisations improve both recall and QA. — [Wu et al. 2024](https://arxiv.org/abs/2410.10813)
- LoCoMo evaluates QA by category (single-hop, multi-hop, temporal, open-domain, adversarial), plus event summarisation over very long dialogues. — [Maharana et al. 2024](https://arxiv.org/abs/2402.17753)
- Mem0's evaluation reports an LLM-as-judge score (J) next to token cost and p50/p95 latency for search and total response. Full context is the accuracy ceiling and memory systems trade a few points for large savings. — [Chhikara et al. 2025](https://arxiv.org/abs/2504.19413); [digest](https://yiwei-chen.github.io/paper-digest/summaries/en/mem0.html)
- StateMemBench grades each answer as current state, superseded state or other. This separates staleness from other errors by construction. — [Fan et al. 2026](https://arxiv.org/abs/2608.19652)
- LongMemEval-V2 adds dynamic state tracking, workflow knowledge, environment gotchas and premise awareness (detecting false premises) for agent experience memory. — [Wu et al. 2026](https://arxiv.org/abs/2605.12493)
- Comparability problems:
  - Vendor LongMemEval scores use different judges, answer models and retrieval setups.
  - Some report recall@5 as if it were accuracy.
  - Some use full-context consolidation with task-tuned prompts.
  — [search synthesis incl. arXiv 2608.17756](https://arxiv.org/pdf/2608.17756); [mem0.ai](https://mem0.ai/library/agent-memory/ai-memory-benchmarks-in-2026)
- The memory backbone moved accuracy far more than the answer LLM did: a 3.4-point spread across 8 backbones, at about 30× cost variation. — [arXiv 2608.29606](https://arxiv.org/abs/2608.29606)
- Canary "exposure" measures unintended memorisation: `exposure = log₂|R| − log₂ rank`. — [Carlini et al. 2019](https://arxiv.org/abs/1802.08232)

### Inferences
- **MIZAN memory eval ("Imtihan: Dhikr block"), stateless and synthetic.** Generate per-user histories in MIZAN's languages (English, Urdu, Roman Urdu, Arabic, Hindi, mixed). Plant needles with known ground truth:
  - facts;
  - updates with valid times;
  - temporal questions ("what did I say last Ramadan");
  - multi-session joins;
  - *absent* facts for abstention;
  - near-duplicate distractors to raise fan;
  - injected "remember this" items from untrusted pasted text (Amanah).
  Score by rule where possible, using Imtihan's `scorers.py`, with a fixed judge otherwise.
- **Metrics with formulas:**
  - Retrieval: Recall@k = |relevant ∩ retrieved_k| / |relevant|. Precision@k likewise. nDCG@k = DCG@k / IDCG@k with `DCG = Σ (2^rel_i − 1)/log₂(i+1)`.
  - **Abstention discrimination**: signal-detection `d' = z(H) − z(FA)`, where H = correct "I don't have that" on absent needles and FA = false recall or invented memory on absent needles. Also report the raw false-recall rate.
  - **Staleness rate** = P(answer reflects a superseded value | an update exists), following StateMemBench.
  - **Interference curve**: accuracy as a function of the number of similar distractor memories (fan). ACT-R predicts a decline of about ln(fan). A flat curve means retrieval is robust to interference.
  - **Retention curve**: accuracy versus needle age (log-spaced: 1 day to 1 year, simulated timestamps). Fit `a·(1 + t/S)^(−w)` and compare with the model's predicted R.
  - **Calibration** of the recall gate's P(needed): ECE and Brier. Imtihan already reports these.
  - **Cost**: injected memory tokens per turn, p50/p95 added latency, and Iqtisad spend, alongside accuracy (Mem0's reporting style).
  - **Cross-user leakage**: plant a unique canary in user A's history. User B's prompts that try to elicit it must give exposure ≈ 0 and zero verbatim hits. Run the same test against every *global* artefact (Case B templates, global priors).
  - **Erasure**: after a Mahw delete, run the canary search and a membership-style probe. Mahw already searches 20-character pieces.
- **Report with uncertainty**: Wilson intervals per ability and paired bootstrap for before/after changes. These are already in Imtihan and Ta'lim.
- **Production signals**, as online metrics without labels:
  - "Restatement rate": the user repeats a fact MIZAN should have recalled, detected by NLI entailment with an existing memory. This is the main *miss* signal.
  - "Correction rate": the user says a recalled fact is wrong or outdated. This is the main *false-recall/staleness* signal.
  These also serve as the Again/Hard grades for the FSRS-style updates in Section 1.

### Gaps
- No standard multilingual or code-switched long-term memory benchmark was found, so MIZAN would need to build its own as described.
- No published "interference curve" methodology for agent memory was found. The fan-based test is an inference from ACT-R.
- Judge-variance figures (how much LLM-as-judge choice moves LongMemEval/LoCoMo scores) were not found as a controlled study, only as caveats.
