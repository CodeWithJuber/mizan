# MIZAN's own model: how a self-hosted agent can train on its own traffic and need OpenRouter less over time (as of 28 Oct 2026)

Retrieval date for every web source below: 28 October 2026. Quotes from terms pages come from page fetches made that day. Some fetch tools return summaries with short quoted fragments, so the exact wording should be re-checked before it is used in a legal decision. None of this is legal advice. Repo facts come from files in this repository.

MIZAN today: `backend/learner/ruh_learner.py` stores each captured interaction with `provider`, `model`, `quality_score`, `review_status`, `reviewer_id`, `review_evidence` and `reviewed_content_hash`. Its docstring says "Store unreviewed captures; explicit review permits candidate export only". Capture is gated by `stateless.trains()`. `backend/tadbir/wazn.py` already picks the cheapest ready model from `MIZAN_LISAN_MODELS` and moves one step stronger for each failed attempt ([repo: backend/learner/ruh_learner.py, backend/tadbir/wazn.py](/backend/learner/ruh_learner.py)). The Ruh model works over `(root_id, pattern_id)` tokens, not BPE ([repo: CLAUDE.md](/CLAUDE.md)).

---

## 1. Legal and terms: may outputs from models served through OpenRouter be used to train another model? Which open-weight bases are licensed for it?

### Takeaway
Training on outputs is clearly allowed for **DeepSeek** (its terms explicitly permit "model distillation") and for **open-weight Apache-2.0 / MIT models** (Qwen3/3.5, Gemma 4, Mistral Small, Phi-4, SmolLM3, the DeepSeek-R1 distills, DeepSeek V4 Flash). **Mistral's** API terms restrict only image outputs. Three cases come with strings attached. **Llama** outputs are allowed, but a model trained on them that is distributed or made available must have a name starting with "Llama" and must show "Built with Llama". **Gemma ≤3** outputs make the trained model a "Model Derivative", which carries Gemma's use-policy flow-down. **Anthropic (Claude)** and **OpenAI (GPT)** outputs must not be used: both forbid training competing models. OpenRouter adds no restriction of its own on training. It says the terms of each underlying model govern, so MIZAN's export must filter by the `provider`/`model` it already records.

### Cited Findings

**OpenRouter (Terms of Service, "Last Updated: August 31, 2026")**
- No clause expressly permits or forbids using Outputs to train other models. §7 item 4 forbids accessing the Site or Service "for purposes of developing a competing service" — [OpenRouter Terms](https://openrouter.ai/terms)
- §5.1: users must "comply with the applicable terms for each Model". §7 item 1 forbids use "in violation of any applicable Model Terms" — [OpenRouter Terms](https://openrouter.ai/terms)
- §6.1: "Your ownership rights in the Output are set forth in the Model Terms for each Model you use". Users "retain copyright and any other proprietary rights" in their Inputs — [OpenRouter Terms](https://openrouter.ai/terms)
- §6.1: "Where possible, OpenRouter has opted out of model training with the Models it uses" but "Some Models may store or train on your Inputs for improving their own large language models". §6.5: "Unless explicitly opted in to prompt logging, we do not store your Inputs after categorizing them." §6.2: opting into prompt logging grants OpenRouter a licence "for our own commercial and business purposes" — [OpenRouter Terms](https://openrouter.ai/terms)

**DeepSeek (Terms of Use, "Last Update: March 27, 2026")**
- §4.2(3) permits use of outputs for "training other models (such as model distillation), etc., as long as such usage is legal and adhere to these Terms" — [DeepSeek Terms of Use](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html)
- §4.2(2): "We assign any rights, title, and interests—if any—in the Outputs of the Services to you." §4.2(1): users retain rights in Inputs — [DeepSeek Terms of Use](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html)
- §4.3: DeepSeek "may, to a minimal extent, use Inputs and Outputs to provide, maintain, operate, develop or improve the Services". The opt-out is the "Improve the model for everyone" toggle. §3.5(3) forbids "attempting to discover the source code, models, algorithms" — [DeepSeek Terms of Use](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html)
- DeepSeek V4 (preview released 24 Apr 2026): Flash has 284B total / 13B active parameters (MoE), Pro has 1.6T / 49B, both MIT-licensed with 1M context. The DeepSeek API charges Flash at $0.14 input / $0.28 output per M tokens. The full Flash download is 160 GB — [Simon Willison, 24 Apr 2026](https://simonwillison.net/2026/apr/24/deepseek-v4). The Hugging Face card for `deepseek-ai/DeepSeek-V4-Flash` shows `license: mit`, 290.9B parameters and FP8 weights, updated 22 Jun 2026 — [HF: DeepSeek-V4-Flash](https://hf.co/deepseek-ai/DeepSeek-V4-Flash)

**Anthropic (Commercial Terms, "Effective Jun 17, 2025")**
- §D.4: "Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or resell the Services except as expressly approved by Anthropic" — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
- §B: the Customer "owns its Outputs" and Anthropic assigns its rights in Outputs to the Customer. Owning the output does not cancel the D.4 use restriction — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
- Enforcement context: on 23 Feb 2026 Anthropic said DeepSeek, Moonshot and MiniMax ran distillation campaigns of about 16M exchanges through about 24,000 fraudulent accounts. It treated these as terms-of-service violations, while calling distillation a legitimate method in general — [Anthropic: detecting and preventing distillation attacks](https://www.anthropic.com/news/detecting-and-preventing-distillation-attacks); [Bloomberg Law](https://news.bloomberglaw.com/artificial-intelligence/anthropic-says-deepseek-minimax-distilled-ai-models-for-gains); [Computing.co.uk](https://www.computing.co.uk/news/2026/ai/chinese-firms-used-distillation-copy-claude)

**OpenAI (Business Terms, dated "Jan. 1, 2026" in the captured text; the direct fetch of openai.com returned HTTP 403)**
- The Business Terms forbid using Output, "except for a Permitted Exception", "to develop artificial intelligence models that compete with OpenAI's products and services" — [ConductAtlas capture of OpenAI Business Terms](https://conductatlas.com/platform/openai/openai-business-terms/provision/CA-P-059973/prohibition-on-using-output-to-develop-competing-ai-models/) (original: [openai.com/policies/business-terms](https://openai.com/policies/business-terms/))
- The consumer/ROW Terms of Use list "Use Output to develop models that compete with OpenAI" among prohibited uses. ConductAtlas reports the EU terms were last updated 11 May 2026 with the same prohibition — [OpenAI ROW Terms (search snippet)](https://openai.com/policies/row-terms-of-use/); [ConductAtlas EU terms](https://conductatlas.com/platform/openai/openai-eu-terms-of-use/no-use-of-output-to-compete-with-openai/)

**Mistral (Commercial Terms of Service, "Effective: September 25, 2026")**
- §3.3: "Customer may not use image Outputs to develop or train any image generation product that competes with a Mistral AI Product" ("to the extent permitted by applicable law"). There is no equivalent restriction on text outputs — [Mistral Commercial ToS](https://legal.mistral.ai/terms/commercial-terms-of-service)
- §2.2(e) forbids using "the Output or any modified version of the Output to reverse engineer the Mistral AI Products". §3.1: Customer "owns all Output" — [Mistral Commercial ToS](https://legal.mistral.ai/terms/commercial-terms-of-service)
- §4.2: Mistral "will not use Customer Data or Outputs to train its artificial intelligence models except" for Feedback, Order Form terms and Labs/Preview models (§4.3) — [Mistral Commercial ToS](https://legal.mistral.ai/terms/commercial-terms-of-service)

**Google Gemma (Gemma Terms of Use, "Last modified: April 1, 2026")**
- §1.1(e): "Model Derivatives" include models trained by "distillation methods that use intermediate data representations" or by "methods based on the generation of synthetic data Outputs by Gemma for training that model". "For clarity, Outputs are not deemed Model Derivatives." — [Gemma Terms](https://ai.google.dev/gemma/terms)
- §3.1: anyone distributing Gemma or Model Derivatives must include the §3.2 use restrictions "as an enforceable provision in any agreement" and give recipients a copy of the Agreement. §3.3: "Google claims no rights in Outputs you generate using Gemma." The page says Gemma 4 is under a separate Apache 2.0 licence — [Gemma Terms](https://ai.google.dev/gemma/terms)
- Gemma 4 was released on 2 Apr 2026 under Apache 2.0, the first Gemma under that licence. Sizes: E2B, E4B, a 26B MoE (~3.8B active) and a 31B dense model. Sources disagree slightly on the lineup — [The Decoder](https://the-decoder.com/googles-gemma-4-is-now-available-with-apache-2-0-licensing-for-the-first-time/); [Slashdot, 2 Apr 2026](https://tech.slashdot.org/story/26/04/02/1735238/google-announces-gemma-4-open-ai-models-switches-to-apache-20-license). The HF card for `google/gemma-4-E4B-it` shows `license: apache-2.0`, 7,996M parameters in total, any-to-any — [HF: gemma-4-E4B-it](https://hf.co/google/gemma-4-E4B-it)

**Meta Llama 4 (Community License, "Llama 4 Version Effective Date: April 5, 2025")**
- §1.b.i: "If you use the Llama Materials or any outputs or results of the Llama Materials to create, train, fine tune, or otherwise improve an AI model, which is distributed or made available, you shall also include "Llama" at the beginning of any such AI model name." It also requires displaying "Built with Llama". (The fetch summary elided the middle of this sentence. The words "which is distributed or made available" match the published Llama 3.1+/4 licence text, but re-check them.) — [Llama 4 License](https://dev.meta.ai/llama/llama4/license/)
- §2: licensees with "greater than 700 million monthly active users in the preceding calendar month" must request a licence from Meta. §1.b.iv incorporates the Acceptable Use Policy — [Llama 4 License](https://dev.meta.ai/llama/llama4/license/)
- Llama 4 has no small dense model. Scout is 108.6B total (17B active, 16 experts), gated, `license: other` — [HF: Llama-4-Scout](https://hf.co/meta-llama/Llama-4-Scout-17B-16E-Instruct)

**Qwen / Alibaba**
- Open weights: `Qwen/Qwen3.5-9B` (9,653M parameters, multimodal, `license: apache-2.0`, updated 2 Mar 2026) and `Qwen/Qwen3-8B` (8,191M, `apache-2.0`) — [HF: Qwen3.5-9B](https://hf.co/Qwen/Qwen3.5-9B); [HF: Qwen3-8B](https://hf.co/Qwen/Qwen3-8B)
- The Qwen3.5 Small series came out in 0.8B, 2B, 4B and 9B sizes in late Feb to early Mar 2026 under Apache 2.0. These are secondary sources, and their dates disagree — [texxr (VentureBeat reproduction)](https://texxr.com/handle/ollama); [LLM Stats: Qwen3.5-2B](https://llm-stats.com/models/qwen3.5-2b)
- Qwen3 was pre-trained on about 36T tokens covering 119 languages and dialects — [Qwen3 Technical Report, arXiv 2505.09388](https://arxiv.org/abs/2505.09388)
- Alibaba Cloud Model Studio service-specific terms: the only output clause found is that trial content "may only be used to evaluate the model's performance" and not "for any other purpose, including any commercial purpose". No clause on competing models was found, and the page shows no date — [Alibaba Model Studio service terms](https://help.aliyun.com/en/model-studio/bailian-service-notes)

**Other permissively licensed small bases (from HF model cards)**
- `HuggingFaceTB/SmolLM3-3B`: 3,075M parameters, Apache 2.0, languages en/fr/es/it/pt/zh/ar/ru (no Urdu or Hindi tag) — [HF: SmolLM3-3B](https://hf.co/HuggingFaceTB/SmolLM3-3B)
- `microsoft/phi-4`: 14,660M, MIT, tagged English only. `microsoft/Phi-4-mini-instruct`: 3,836M, MIT, multilingual including Arabic (no Urdu or Hindi tag) — [HF: phi-4](https://hf.co/microsoft/phi-4); [HF: Phi-4-mini-instruct](https://hf.co/microsoft/Phi-4-mini-instruct)
- `mistralai/Mistral-Small-3.2-24B-Instruct-2506`: 24,011M, Apache 2.0, languages include ar, hi, bn (no ur tag) — [HF: Mistral-Small-3.2](https://hf.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506)
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`: 7,616M, MIT — [HF: R1-Distill-Qwen-7B](https://hf.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B)

### Inferences
- **Export filter by provenance (actionable).** `ruh_learner` already stores `provider` and `model`. Add a licence-policy table that runs at export:
  - **allow**: `deepseek/*` (ToU §4.2(3) plus MIT weights); open-weight Apache/MIT models (Qwen3/3.5 open checkpoints, Gemma 4, Mistral Small/Magistral open weights, gpt-oss); Mistral API text outputs.
  - **allow with obligations**: `meta-llama/*`. Once MIZAN's model answers users, it is arguably "made available", so its name would have to start with "Llama" and the UI would need "Built with Llama". Simpler to exclude. `google/gemma-2/3*` makes the student a Gemma "Model Derivative" with use-policy flow-down. Exclude it or accept that.
  - **deny**: `anthropic/*`, `openai/gpt-*` (non-open-weight) and anything with unknown terms, such as Qwen API-only models (e.g. Qwen-Max/Plus via Alibaba) whose terms could not be verified.
- **Who serves the model matters.** Through OpenRouter, an open-weight model may be served by a third-party host (DeepInfra, Together, etc.). OpenRouter §6.1 points to the "Model Terms", which for open weights are the licence. Host terms were not checked (see Gaps).
- **MIZAN's own verified parts are its own data.** A program output computed in MIZAN's sandbox, Quran or hadith text quoted from source, and a number checked by Sidq are not model "Output". The model's wording around them is.
- **Is MIZAN a "competing service" to OpenRouter (§7.4)?** Probably not: a self-hosted agent that runs its own model is not a model marketplace or router. Anthropic's D.4 is different. A small model trained to replace Claude for MIZAN's users is plausibly a "competing AI model", so Claude outputs must stay out.
- **Privacy note.** DeepSeek ToU §4.3 lets DeepSeek use inputs and outputs unless that is opted out, and OpenRouter says "some Models may store or train on your Inputs". Moving traffic to a local model therefore also reduces how much user data reaches third parties.

### Gaps
- OpenAI's "Permitted Exception" definition was not retrieved (openai.com returned 403). Its scope is unknown.
- No current Alibaba Cloud International clause on using Qwen *API* outputs to train other models was found.
- The terms of third-party OpenRouter hosts (DeepInfra, Together, Novita, etc.) were not checked.
- gpt-oss-20b/120b being Apache 2.0 comes from prior knowledge ([HF: gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b)) and was not re-checked this session.
- The full Llama Acceptable Use Policy text and any EU/multimodal restriction were not retrieved.

---

## 2. Methods: distillation, SFT on verified outputs, preference learning, RL with verifiable rewards. Which work best for small (1-8B) models on narrow domains?

### Takeaway
For a 1-9B student on MIZAN's narrow, partly verifiable work, the evidence points to an order of steps:
1. **SFT on teacher outputs that passed MIZAN's own checks**: rejection-sampling fine-tuning (RFT), the first round of STaR/ReST-EM, and sequence-level KD in effect.
2. **On-policy distillation** where an open-weight teacher can score the student's tokens. It is the most compute-efficient way to close the remaining gap.
3. **KTO/DPO** from verified-good vs corrected/failed answers.
4. **GRPO with verifiable rewards** only for families that have a programmatic checker (code cross-check, arithmetic, quote fidelity).

Distilling from a strong teacher beats running RL on a small model from scratch. Imitation copies style more easily than capability.

### Cited Findings

**Distillation**
- Classic KD trains the student on the teacher's softened distribution: L = (1−λ)·CE(y, p_s) + λ·T²·KL(p_t^T ‖ p_s^T) — [Hinton et al. 2015, arXiv 1503.02531](https://arxiv.org/abs/1503.02531)
- Sequence-level KD (Kim & Rush 2016) approximates the teacher's sequence distribution by its beam-search mode and trains the student on those sequences with ordinary cross-entropy. The student loses little quality and can decode greedily without beam search — [arXiv 1606.07947](https://arxiv.org/abs/1606.07947). *(SFT on DeepSeek's answers is exactly sequence-level KD with the API's sampled sequence as the "mode".)*
- GKD (Agarwal et al., ICLR 2024) trains on the student's **own** generated sequences, with the teacher giving token-level feedback under any divergence (forward KL, reverse KL, generalised JSD). This fixes the train/inference mismatch of off-policy KD — [arXiv 2306.13649](https://arxiv.org/abs/2306.13649). MiniLLM argues reverse KL KL(p_s‖p_t) keeps the student from overestimating the teacher's low-probability regions — [arXiv 2306.08543](https://arxiv.org/abs/2306.08543)
- On-policy distillation (Thinking Machines, 27 Oct 2025, updated Jun 2026 to Qwen3.5-9B student/teacher): the student samples, the teacher scores each token with per-token reverse KL used as the advantage (discount 0) — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
  - Cost vs off-policy SFT: 9× cheaper when the SFT data already exists, ~18× in GPU hours, ~30× when teacher sampling for a new task is counted.
  - AIME'24: SFT on 400k prompts gave 60%. On-policy distillation from that checkpoint reached 70% in ~150 steps (~77K prompts × 4 samples). Quoting the Qwen3 report: off-policy distillation 55.0%, RL 67.6%, on-policy distillation 74.4%; RL used 17,920 GPU hours vs 1,800 for on-policy distillation.
  - LoRA rank 32 trails full fine-tuning by 13% after SFT but only by 6% after on-policy distillation — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
- DeepSeek-R1: R1-Zero uses pure RL with rule-based accuracy and format rewards. The R1-Distill models were SFT'd on ~800k curated R1 samples, and distilling R1 into small dense models beat running large-scale RL directly on those small models — [DeepSeek-R1, arXiv 2501.12948](https://arxiv.org/abs/2501.12948)
- "False promise of imitation": models fine-tuned on a proprietary model's outputs copy its style and fool crowd raters, but gain little in factuality or capabilities missing from the imitation data. Closing the gap needs a better base LM — [Gudibande et al. 2023, arXiv 2305.15717](https://arxiv.org/abs/2305.15717)
- Quality over quantity: LIMA fine-tuned a 65B LLaMA on 1,000 carefully curated examples and got strong alignment — [arXiv 2305.11206](https://arxiv.org/abs/2305.11206)

**SFT on verified outputs (rejection sampling / self-training)**
- STaR loops: generate rationales, keep those that reach the correct answer, "rationalise" failures given the answer, fine-tune, repeat. GPT-J 6B on CommonsenseQA performed comparably to a ~30× larger fine-tuned model — [arXiv 2203.14465](https://arxiv.org/abs/2203.14465)
- RFT (Yuan et al. 2023): fine-tuning on multiple *distinct* correct reasoning paths found by rejection sampling raised LLaMA-7B on GSM8K from 35.9% (SFT) to 49.3% (with samples pooled from several models) — [arXiv 2308.01825](https://arxiv.org/abs/2308.01825)
- ReST runs Grow (sample from the policy) and Improve (filter by a reward threshold, then fine-tune offline) — [Gulcehre et al. 2023, arXiv 2308.08998](https://arxiv.org/abs/2308.08998). ReST-EM (Singh et al.) uses only binary feedback on MATH and APPS. It scales well with model size and clearly beats fine-tuning on human data alone — [arXiv 2312.06585](https://arxiv.org/abs/2312.06585)

**Preference learning**
- DPO: L = −E log σ(β[log π(y_w|x)/π_ref(y_w|x) − log π(y_l|x)/π_ref(y_l|x)]). It needs pairs and a reference model — [arXiv 2305.18290](https://arxiv.org/abs/2305.18290)
- KTO needs only a **binary** desirable/undesirable label per example, not pairs, through a prospect-theory value function. It matches or exceeds DPO from 1B to 30B — [arXiv 2402.01306](https://arxiv.org/abs/2402.01306)
- ORPO adds an odds-ratio penalty to the NLL loss: one stage, no reference model — [arXiv 2403.07691](https://arxiv.org/abs/2403.07691). SimPO uses the length-normalised log-likelihood as the implicit reward with a target margin γ and no reference model, beating DPO by up to 6.4 points on AlpacaEval 2 and 7.5 on Arena-Hard — [arXiv 2405.14734](https://arxiv.org/abs/2405.14734)

**RL with verifiable rewards**
- GRPO (DeepSeekMath) drops the critic. For G samples per prompt with rewards r_i, the advantage is A_i = (r_i − mean(r))/std(r), with a KL penalty to the reference — [arXiv 2402.03300](https://arxiv.org/abs/2402.03300). Tulu 3 names this "RLVR" (RL with verifiable rewards) and applies it to math and instruction-following checks — [arXiv 2411.15124](https://arxiv.org/abs/2411.15124)
- In policy-gradient RL, LoRA matches full fine-tuning "even with ranks as low as 1", because RL absorbs roughly one bit per episode — [Thinking Machines, LoRA Without Regret](https://thinkingmachines.ai/blog/lora/)

### Inferences
- **Mapping to MIZAN's signals.** Every Lisan answer already carries an outcome:
  - Tathabbut cross-check passed or failed (code with numbers).
  - Furqan/Sidq corrected the answer or not (wording, quotes, arithmetic).
  - Isnad grade: sahih, hasan, da'if or mawdu'.
  - Muhasaba correction posted later.
  - Hifz reuse succeeded.

  These give, with no human labelling:
  - **SFT set**: answers that passed and were not corrected. This is RFT / the first ReST-EM step.
  - **KTO set**: passed = desirable; failed, corrected or mawdu' = undesirable. KTO fits because MIZAN's labels are unpaired and imbalanced.
  - **DPO pairs**: (corrected answer, original answer) wherever Muhasaba or Sidq produced a corrected version for the same prompt.
  - **GRPO reward**: r = 1 if the program's numbers match an independent program (Tathabbut) and Hudud allows it, 0 otherwise. Partial credit can come from a format reward.
- **On-policy distillation needs a teacher that can score arbitrary sequences.** Hosted chat APIs generally return log-probs only for tokens the teacher itself generated, if at all. So true GKD/on-policy KD against DeepSeek through OpenRouter is probably impossible. It needs an open-weight teacher run on rented GPUs. Options: DeepSeek V4 Flash (MIT, ~160 GB FP8) on a multi-GPU node, or a Qwen3.5 27B-class model if one exists. The cheaper route is off-policy SFT now (data is free, it is already in the capture table) and on-policy distillation in short rented bursts later.
- **Small-model recipe that fits the evidence.** Steps 1-3 are cheap:
  1. A base with good multilingual pre-training: Qwen3.5-4B/9B or Gemma 4 E4B (Apache).
  2. LoRA on all layers (MLP included).
  3. SFT on 5k-50k licence-filtered, verified examples per family.
  4. KTO on outcome labels.
  5. GRPO only on code, arithmetic and quote-fidelity families.
  6. On-policy distillation when there is budget.

  Expect clear gains in style, format and MIZAN-specific behaviour (calling conventions, refusing to quote Quran from memory). Expect smaller gains in knowledge and hard reasoning (Gudibande).
- **Zero OpenRouter changes the regime.** Once the API share reaches 0, no new teacher signal comes in. The only remaining learning signal is verifier-filtered self-training (ReST-EM/GRPO). That works for verifiable families but adds no new knowledge or wording quality for open conversation. A small residual escalation budget (or user feedback) is the only source of new language signal there.

### Gaps
- No head-to-head study of KTO vs DPO vs SimPO specifically at 1-4B on code plus multilingual conversation was found this session.
- Whether OpenRouter passes through `logprobs`/`top_logprobs` for DeepSeek V4 Flash, and whether any host offers prompt-logprob scoring (needed for KD on the student's tokens), was not verified.
- TRL's GKD/KTO/GRPO trainers and Axolotl/Unsloth recipe docs were not re-fetched (pointers: [TRL docs](https://huggingface.co/docs/trl/index); TRL has GKD, DPO, KTO, ORPO and GRPO trainers — from prior knowledge).

---

## 3. Continual learning without catastrophic forgetting: adapters, replay, EWC, merging; how to evaluate before promoting a checkpoint

### Takeaway
Use LoRA adapters on a frozen base: one per domain family, optionally a thin one per user. LoRA "learns less and forgets less". Mix in a replay buffer of older verified examples plus general instruction data in every retrain. Retrain from the base on the accumulated data rather than stacking fine-tunes. Combine adapters with TIES/DARE merges if needed. Promote a challenger only through a sequential or paired test on held-out sets, which MIZAN already does for Tajdid (P(better) ≥ 0.95) and Ta'lim (paired bootstrap). A per-user adapter also makes Mahw "true forget" workable: delete the adapter, or retrain it without the erased chat.

### Cited Findings
- LoRA: W = W₀ + (α/r)·B·A with B ∈ ℝ^{d×r}, A ∈ ℝ^{r×k}, so a layer trains r(d+k) parameters instead of dk — [Hu et al. 2021, arXiv 2106.09685](https://arxiv.org/abs/2106.09685). QLoRA freezes a 4-bit NF4 base and trains LoRA on top. It fine-tuned 65B on one 48 GB GPU, and Guanaco reached 99.3% of ChatGPT on the Vicuna benchmark after 24 h on one GPU — [arXiv 2305.14314](https://arxiv.org/abs/2305.14314)
- "LoRA Learns Less and Forgets Less" (Biderman et al., TMLR 2024) studied code and math, with IFT on ~100K pairs and CPT on 20B tokens:
  - "In the standard low-rank settings, LoRA substantially underperforms full finetuning."
  - "LoRA better maintains the base model's performance on tasks outside the target domain", more than weight decay or dropout do.
  - Full fine-tuning learns perturbations of rank "10-100X greater than typical LoRA configurations".
  — [arXiv 2405.09673](https://arxiv.org/abs/2405.09673)
- "LoRA Without Regret" (Schulman et al., 29 Sep 2025):
  - On small-to-medium instruction and reasoning SFT sets, "LoRA performs the same as full fine-tuning", but it underperforms when the data exceeds its capacity.
  - Attention-only LoRA underperforms MLP-only LoRA, so apply it to all layers.
  - The best LoRA learning rate is "consistently 10x" the full-FT learning rate.
  - LoRA is "less tolerant of large batch sizes".
  - It costs "slightly more than ⅔ of the FLOPs" of full FT per pass.
  — [Thinking Machines](https://thinkingmachines.ai/blog/lora/)
- Forgetting and its repair: mid-training Qwen3-8B on internal documents raised internal QA from 18% to 43% but cut IF-eval from 85% to 45%. A 70/30 mix with chat data gave 36% and 79%. Adding on-policy distillation (an earlier Qwen3-8B as teacher on Tulu3 prompts) gave 41% and 83%, "recover[ing] nearly full performance on IF-eval without losing any knowledge". In mid-training, LoRA "learns less knowledge and still forgets" — [Thinking Machines, On-Policy Distillation](https://thinkingmachines.ai/blog/on-policy-distillation/)
- EWC adds a quadratic penalty that keeps parameters important to old tasks near their old values: L(θ) = L_new(θ) + Σ_i (λ/2)·F_i·(θ_i − θ*_i)², where F is the diagonal Fisher information — [Kirkpatrick et al. 2017, arXiv 1612.00796](https://arxiv.org/abs/1612.00796)
- Replay: learning-rate re-warming and re-decaying plus replay of a fraction of earlier data lets continually pre-trained LLMs match retraining from scratch on all data — [Ibrahim et al. 2024, arXiv 2403.08763](https://arxiv.org/abs/2403.08763)
- Merging:
  - Model soups: averaging the weights of fine-tunes from the same initialisation improves accuracy at no inference cost — [arXiv 2203.05482](https://arxiv.org/abs/2203.05482).
  - TIES-Merging: trim small task-vector entries, elect a sign per parameter, then average only agreeing entries — [arXiv 2306.01708](https://arxiv.org/abs/2306.01708).
  - DARE: randomly drop a fraction p of delta parameters (even 90-99%) and rescale the rest by 1/(1−p) before merging — [arXiv 2311.03099](https://arxiv.org/abs/2311.03099)
- Serving many adapters: S-LoRA serves thousands of concurrent LoRA adapters on one base by paging adapter weights — [arXiv 2311.03285](https://arxiv.org/abs/2311.03285)
- Sequential testing: Wald's SPRT stops once the log-likelihood ratio crosses a or b, with a = ln(β/(1−α)) and b = ln((1−β)/α). On average it needs fewer samples than a fixed-n test for the same error rates — [SPRT (Wikipedia)](https://en.wikipedia.org/wiki/Sequential_probability_ratio_test)
- Unlearning: SISA training (sharded, isolated, sliced, aggregated) limits how much must be retrained when a data point must be forgotten — [Bourtoule et al., arXiv 1912.03958](https://arxiv.org/abs/1912.03958)

### Inferences
- **Recommended structure for MIZAN.**
  1. **Base**: frozen and versioned (e.g. Qwen3.5-4B or Gemma 4 E4B).
  2. **Family adapters**: one per Fahm family (code/Tathabbut, conversation-Hinglish/Urdu, Arabic explanation, Quran-adjacent wording, which never quotes, since Fihris quotes) or one shared adapter, retrained from the base on the **accumulated** verified set plus a fixed replay slice (general instruction data, e.g. Tulu-3-style prompts, plus oldest verified examples).
  3. **Optional per-user adapters**: small rank, user style only, trained only with consent.
  4. **Deleting a user's data**: drop or retrain their adapter. For family adapters, rebuild from a dataset with the user's examples removed (SISA-style shards by user or month keep this cheap).
- **Do not stack fine-tunes.** Retrain from the base on the cumulative dataset each cycle, which is cheap at 10k-100k examples. This avoids drift and makes erasure reproducible: dataset hash → adapter hash, which can be recorded as a Sakk receipt.
- **Promotion gate (worked math).** For a pass/fail metric on a held-out set, compare challenger B with incumbent A on the same items. The McNemar sample size is

  n ≈ (z_{α} + z_{β})² · (p₀₁ + p₁₀) / (p₀₁ − p₁₀)²,

  where p₀₁ and p₁₀ are the discordant rates. Example: B fixes 6.5% of items A fails, A fixes 3.5% that B fails (a net +3 points), one-sided α = 0.05 (z = 1.645), power 0.8 (z = 0.84):
  - n ≈ (2.485)² · 0.10 / 0.0009 ≈ **686 items**;
  - two-sided α = 0.05: n ≈ 7.84 · 0.10 / 0.0009 ≈ **871**.

  So each family's held-out set should hold roughly 700-900 items to detect +3-point changes. MIZAN's Bayesian rule (Beta posterior on per-item win rate among discordant items, promote when P(θ > ½) ≥ 0.95) is equivalent in spirit and can stop early.
- **Two gates per promotion**: (a) in-family improvement on the held-out set, and (b) non-regression on general checks (Imtihan blocks, an IFEval-style instruction check, Arabic/Urdu/Hinglish conversation probes), with a margin δ (e.g. no drop > 1 point at P ≥ 0.95). The on-policy-distillation results show forgetting shows up mainly in instruction following.

### Gaps
- No published numbers were found on per-user LoRA adapters for personal assistants (quality vs data needed per user).
- llama.cpp's current multi-adapter hot-swap API (per-request LoRA scale) was not verified this session.

---

## 4. Routing to reduce API use: router or cascade to a local model when its predicted quality is high enough; how the local share grows; speculative decoding

### Takeaway
MIZAN already has the right shape. Wazn is a cascade (cheapest ready model first, one step stronger per failed attempt) and Majlis uses Thompson sampling over Beta posteriors. The local model becomes the first rung. For families with a verifier (code cross-check, arithmetic, quotes), use **local → verify → escalate on failure**: the expected API share is the local failure rate. For unverifiable wording, use a **learned router** (RouteLLM-style) trained on MIZAN's own comparisons. Speculative decoding speeds up **local** generation but does not cut API calls.

### Cited Findings
- RouteLLM (Ong et al., 2024; v4 Feb 2025) learns routers between a strong and a weak LLM from human preference data plus augmentation. It "significantly reduces costs—by over 2 times in certain cases—without compromising the quality of responses", and the routers kept working when the strong and weak models were swapped at test time — [arXiv 2406.18665](https://arxiv.org/abs/2406.18665)
- FrugalGPT uses an LLM cascade with a learned scorer that decides whether to accept an answer or escalate. It matched the best single LLM (GPT-4) "with up to 98% cost reduction", or beat GPT-4 accuracy by 4% at the same cost — [arXiv 2305.05176](https://arxiv.org/abs/2305.05176)
- Cascades by answer consistency: sample the weak model several times (and with mixed thought representations). Escalate only when the answers disagree. This matched the strong LLM at about 40% of its cost on reasoning tasks — [Yue et al. 2023, arXiv 2310.03094](https://arxiv.org/abs/2310.03094). AutoMix uses few-shot self-verification plus a POMDP-based meta-verifier to decide escalation — [arXiv 2310.12963](https://arxiv.org/abs/2310.12963)
- Speculative decoding: a small draft proposes k tokens and the target verifies them in one pass, giving an identical output distribution. Reported 2-3× on T5-XXL ([Leviathan et al., arXiv 2211.17192](https://arxiv.org/abs/2211.17192)) and 2-2.5× on Chinchilla-70B ([Chen et al., arXiv 2302.01318](https://arxiv.org/abs/2302.01318))
- MIZAN's Wazn picks from `MIZAN_LISAN_MODELS` "cheapest first" and steps up after failure — [repo: backend/tadbir/wazn.py](/backend/tadbir/wazn.py)

### Inferences
- **Cost of a verified cascade.** Let c_L be the local cost per request (≈ electricity on an existing server), c_A the API cost, and s_f the local first-try pass rate for family f. Then
  - expected cost per request = c_L + (1 − s_f)·c_A;
  - fraction of API spend saved = s_f − c_L/c_A ≈ s_f;
  - extra latency = (1 − s_f)·t_L, the wasted local attempt.

  Route family f locally only when s_f is high enough that the expected latency penalty (1 − s_f)·t_L is acceptable. With slow CPU decoding this matters (see §5).
- **Posterior gate (fits MIZAN's style).** Keep a Beta(a_f, b_f) per (family, model) on "local answer passed MIZAN's checks". Try local first when P(s_f ≥ τ_f | data) ≥ 0.95, or Thompson-sample local vs API as Majlis does. τ_f is set by the latency budget, e.g. τ = 0.8 when a wasted local attempt costs 10 s.
- **Unverifiable wording (conversation, Hinglish/Urdu, explanations).** There is no checker, so labels must come from comparisons: send a small random fraction ε (e.g. 5%) of local-eligible requests to both, as Muqabala already does, and get a preference from a judge (the API model itself, or user thumbs). Fit P(local ≥ API − δ | x) with a small classifier on MIZAN's features (Qasd family, language posterior from Lughah, length, n-grams), the RouteLLM approach. Use ε-exploration so the router keeps learning.
- **How the local share grows.** Local share S(t) = Σ_f w_f · 1[P(s_f(t) ≥ τ_f) ≥ 0.95], where w_f is family f's traffic share. Expected order:
  1. Requests that need **no model**: Hifz re-runs of verified programs, Ta'allum learned wording, Tadbir-computed answers.
  2. Short, verifiable code and arithmetic.
  3. Fixed-format wording around tool results.
  4. Open conversation in Hinglish/Urdu/Arabic last.
- **Speculative decoding** needs the target's logits in the same process, so it cannot accelerate OpenRouter calls. It helps when MIZAN serves its own larger model with a small same-tokenizer draft (e.g. Qwen3.5-9B target with Qwen3.5-0.8B draft). On a memory-bandwidth-bound CPU, verifying k drafted tokens costs about one target pass, so 1.5-2.5× is plausible but unmeasured.

### Gaps
- No published growth curves were found for "share of traffic moved to a self-trained local model over time". MIZAN would have to measure its own S(t).
- RouteLLM's per-benchmark numbers (MT-Bench/MMLU/GSM8K savings at fixed quality) were not in the abstract fetched. Only the ">2×" headline was confirmed.

---

## 5. Practical costs: GPU hours and money for LoRA on a 3-8B model with 10k-100k examples; CPU (llama.cpp, GGUF) vs small GPU serving; latency; expected quality vs a hosted frontier model on code, Hinglish/Urdu and Arabic

### Takeaway
**Training is cheap: about $2-$35 of rented H100 time per run, or $15-$100 through a fine-tuning API.** The real cost is evaluation, iteration and data curation. **Serving decides everything.** On MIZAN's own server (2-8 GB for the app), only a **3-4B model at Q4** fits next to the app, and on vCPUs it runs at single-digit to ~30 tokens/s. A rented always-on GPU (~$250/month for a 4090) costs **10-25× more than MIZAN's current DeepSeek V4 Flash spend** at plausible volumes. So the case for a local model is independence, privacy and availability, not money. Small models will lag frontier models clearly on hard code and on Urdu-script/Hinglish nuance. They come closest on narrow, verifiable, format-bound work.

### Cited Findings

**API baseline**
- DeepSeek V4 Flash costs $0.14/M input and $0.28/M output on DeepSeek's own API — [Simon Willison](https://simonwillison.net/2026/apr/24/deepseek-v4).
- OpenRouter's `deepseek-v4-flash-latest` page lists ~$0.065/M input, $0.18/M output and $0.02/M cache reads — [OpenRouter (search snippet)](https://openrouter.ai/~deepseek/deepseek-v4-flash-latest).
- Another tracker lists $0.14/$0.28 for OpenRouter's standard rate — [computeprices](https://computeprices.com/providers/openrouter/models/deepseek-v4-flash). The sources disagree; the slugs and dates differ.

**GPU rental**
- RunPod lists the H100 80GB "from $1.99/hr" on demand with per-second billing (page updated July 2026) — [RunPod pricing](https://www.runpod.io/gpu-cloud/pricing).
- Trackers list H100 PCIe at $2.89 (Secure Cloud) and RTX 4090 at ~$0.34/h (Community) to $0.69/h (Secure) — [Hivenet guide](https://www.hivenet.com/post/runpod-pricing-complete-guide-to-gpu-cloud-costs)
- H100 SXM: 1,979 BF16 Tensor TFLOPS *with sparsity*, so ~989 dense — [NVIDIA H100](https://www.nvidia.com/en-us/data-center/h100/)

**Fine-tuning APIs**
- Together AI LoRA SFT is reported at ~$0.48/M training tokens for models ≤16B ($1.20 for full SFT), $1.50 for 17-69B, $2.90 for 70-100B. Billing = epochs × dataset tokens + evaluation tokens. Third-party trackers, May-June 2026 — [CostBench: Together fine-tuning](https://www.costbench.com/software/fine-tuning-apis/together-ai-fine-tuning/); [Together docs](https://docs.together.ai/docs/fine-tuning-pricing.md)

**Unsloth**
- About 2× faster and >70% less VRAM than HF + FlashAttention-2 for Llama 3.1 8B QLoRA (rank 32, all linear layers). 8 GB VRAM fits ~2,972 tokens of context with Unsloth, where HF runs out of memory — [Unsloth benchmarks](https://unsloth.ai/docs/basics/unsloth-benchmarks)
- A guide reports Llama 3.1 8B QLoRA on one RTX 4090 peaking at 6.6 GB reserved VRAM at 2,048-token sequences — [computingforgeeks](https://computingforgeeks.com/fine-tune-llm-unsloth-qlora/)

**CPU inference (llama.cpp / Ollama)**
- llama-bench on a Ryzen 9 7950X with 64 GB DDR5 shows Qwen3-8B Q4_K_M at ~26.4 tok/s generation, CPU only. The author could not confirm the table was measured — [markaicode llama.cpp benchmark](https://markaicode.com/benchmarks/llamacpp-tokens-per-second-benchmark/)
- EPYC 9354 with 12-channel DDR5-4800 ran Llama 3.1 8B Q4_K_M at 14.2 tok/s on 12 threads, 7.1 on 4 threads — [markaicode CPU benchmark](https://markaicode.com/benchmarks/tool-cpu-benchmark/)
- A Ryzen 7 7700X with DDR5-6000 runs an 8B Q4_K_M at ~13 tok/s. Reports of ~35 tok/s for 3B and ~14 for 7B on DDR5 desktops; ordinary laptops run 7-8B at 3-4 tok/s — [bestllmfor](https://bestllmfor.com/guide/llm-local-cpu-sans-gpu/)

**Language quality**
- HELM Arabic (Stanford, Dec 2025): the best open-weights model was Qwen3 (mean 0.786). Open models trained or fine-tuned specifically for Arabic *underperformed* general models — [HELM Arabic](https://crfm.stanford.edu/2025/12/18/helm-arabic.html)
- Evaluating twelve small LMs on Arabic: models with stronger Arabic alignment and more reliable instruction following did better — [arXiv 2606.21460](https://arxiv.org/pdf/2606.21460)
- UrduMMLU (26,389 MCQs, 26 subjects, 30 models): the best open-weight model trails the best proprietary model by ~8-9 points, and models do much worse on Urdu literature/language than on STEM — [arXiv 2606.07167](https://arxiv.org/pdf/2606.07167)
- U-MIRAGE (AbjadNLP 2026, Urdu and Roman Urdu medical QA): quantized small models score near random on low-resource languages, and chain-of-thought helps small models more than large ones. This comes from an index page and needs verification — [ACL Anthology](https://preview.aclanthology.org/credits/2026.abjadnlp-1.55)
- Urdu idiom translation (Gemma 3-1B, Qwen 3-8B, Mistral-7B among others): native-script Urdu input gave more accurate idiomatic translations than Roman Urdu — [arXiv 2510.17460](https://arxiv.org/abs/2510.17460v1)
- Quantization hurts multilingual LLMs most on non-Latin-script languages, and automatic metrics underestimate the damage — [Marchisio et al. 2024, arXiv 2407.03211](https://arxiv.org/abs/2407.03211)
- Qwen3.5-9B is claimed (vendor/press) to rival gpt-oss-120b on some benchmarks — [texxr/VentureBeat](https://texxr.com/handle/ollama)

### Inferences (my arithmetic; formulas shown so they can be redone)

**Training compute.** Full fine-tuning costs ≈ 6·P·T FLOPs. LoRA costs ≈ ⅔ of that, so ≈ 4·P·T (LoRA Without Regret). Assume ~1,000 tokens per example and effective throughput of 1.5-3×10¹⁴ FLOP/s on an H100 (15-30% MFU; QLoRA dequantization lowers MFU).

| Run | Tokens T | 8B FLOPs | H100 hours | Cost at $1.99-2.89/h | Together API at $0.48/M |
|---|---|---|---|---|---|
| 10k examples × 3 epochs | 30M | 9.6×10¹⁷ | 0.9-1.8 h | ~$2-5 | ~$14 |
| 100k examples × 2 epochs | 200M | 6.4×10¹⁸ | 5.9-11.9 h | ~$12-34 | ~$96 |

A 3-4B model costs ~40-50% of these. Multiply by 3-5 for hyperparameter sweeps and failed runs, and add evaluation generation. Realistic budget: **$20-$300 per promoted adapter**. DPO/KTO roughly doubles the compute per example (policy plus reference forward passes; KTO and SimPO/ORPO without a reference are cheaper). Together lists DPO LoRA at ~$3.75/M tokens for mid-size models.

**Training a general LM from scratch (Ruh as Lisan) is out of reach.** At Chinchilla-style ~20 tokens/parameter, a 3B model needs ~60B tokens:
- 6·3×10⁹·6×10¹⁰ ≈ 1.1×10²¹ FLOPs ≈ 1,000-2,000 H100-hours ≈ $2,000-$6,000;
- and it would still be far behind Qwen3, which was pre-trained on ~36T tokens.

Keep Ruh as the morphology specialist (Sarf) and fine-tune a pretrained base for Lisan.

**Memory for CPU serving.**
- Q4_K_M weights ≈ 4.5-5 bits/param, so 8B ≈ 4.5-5 GB, 4B ≈ 2.3-2.5 GB, 3B ≈ 1.7-1.9 GB.
- KV cache at fp16 ≈ 2 · layers · kv_heads · head_dim · 2 bytes per token. For Qwen3-8B (36 layers, 8 KV heads, head_dim 128) that is ≈ 147 KB/token, so ≈ 0.6 GB at 4k context.

With 2-8 GB for the whole app, an 8B model does not fit comfortably, while a 3-4B Q4 (≈ 2-3 GB including KV) does. The 8B model needs the server's RAM raised to ~12-16 GB.

**Decode speed** is memory-bandwidth bound: tok/s ≈ effective bandwidth / model bytes. Dual-channel DDR5-5600 is ~90 GB/s in theory, so an 8B Q4 tops out at ~18 tok/s, consistent with the 13-26 tok/s reports. A shared-vCPU VPS might get 10-30 GB/s effective: ~2-6 tok/s for 8B, ~5-15 tok/s for 3-4B. A 300-token answer then takes ~20-60 s on a VPS, plus CPU prompt processing that is compute bound and slow for 2-3k-token MIZAN prompts. That makes the latency penalty of a failed local attempt material, so τ_f in §4 should be high.

**Break-even vs the API.** Example: 1,000 Lisan calls/day at 3k input + 700 output tokens.
- DeepSeek direct ($0.14/$0.28): 3M·$0.14 + 0.7M·$0.28 ≈ $0.62/day ≈ **$19/month**.
- OpenRouter at $0.065/$0.18: ≈ $0.32/day ≈ **$10/month**.
- Reasoning tokens can multiply output 2-5×, which still stays under ~$50/month.

Compare a rented always-on RTX 4090 at $0.34/h (≈ $248/month) or an H100 (≈ $1,450/month). The 4090 breaks even only near $248 / $0.62 per 1k calls ≈ **400k calls/month (~13k/day)**. **CPU serving on the existing box** has no marginal cost but is slow and weaker. **Conclusion**: rent GPUs for *training bursts*, serve 3-4B locally on CPU (or 8B if RAM is raised), and keep the API as the escalation rung.

**Expected quality vs DeepSeek V4 Flash** (284B/13B-active, which is itself a strong teacher):
- **Code**: a fine-tuned 4-9B model should handle short, testable scripts well when MIZAN runs them and retries (Tathabbut catches errors). Multi-file projects and unfamiliar libraries will escalate often.
- **Hinglish/Roman Urdu conversation**: distillation from MIZAN's own Hinglish traffic should transfer *style* well (Gudibande). Nuance and facts will lag. Avoid aggressive quantization of the model that writes Urdu script (Marchisio), e.g. use Q5/Q6 or Q8 if RAM allows.
- **Arabic**: Qwen-family bases are the strongest open option (HELM Arabic). The highest-stakes risk, Quran and hadith text, is already removed because MIZAN quotes from source and never lets the model write the text.

### Gaps
- No verified tokens/sec figure for Unsloth 8B QLoRA on an H100 was found. The FLOP-based hours above are estimates; a one-hour benchmark run would replace them.
- Memory bandwidth of MIZAN's actual production server, and its CPU prompt-processing speed for 2-3k-token prompts, are unknown. Running `llama-bench -p 2048 -n 256` on it would settle this.
- No Hinglish (Hindi-English code-mixed) benchmark covering small models was found this session.
- DeepSeek V4 Flash's latency on OpenRouter (TTFT, tok/s) was not measured, so local vs API latency cannot be compared quantitatively.
- No sourced head-to-head of a fine-tuned 4-9B model vs a frontier API on code (e.g. SWE-style or LiveCodeBench) was collected.

---

## 6. Data quality: dedupe, PII scrubbing, consent and opt-out, keeping evaluation data out, licences of user-provided content

### Takeaway
Data hygiene matters more than volume. Steps:
1. Licence-filter by provider/model (§1).
2. Keep only verified, uncorrected answers for SFT, with outcome labels for KTO.
3. Exact- and near-dedupe (MinHash).
4. Scrub PII.
5. Keep Imtihan, Muqabala, WhatsApp, `stateless` and opted-out traffic out (MIZAN already does part of this).
6. Run an n-gram contamination check against every held-out set.
7. Accumulate data rather than replace it, so self-training does not collapse.
8. Wire Mahw erasure through to datasets and adapters.

### Cited Findings
- Deduplicating training data (exact plus near-duplicate) produced models that "emit memorized text ten times less frequently". Over 1% of unprompted output from models trained on non-deduplicated data was copied verbatim from training data — [Lee et al. 2021, arXiv 2107.06499](https://arxiv.org/abs/2107.06499)
- Contamination: GPT-3 measured train/benchmark overlap with 13-gram matches and reported clean-subset results — [Brown et al. 2020, arXiv 2005.14165](https://arxiv.org/abs/2005.14165)
- Model collapse: training indiscriminately on model-generated content causes irreversible defects, and the tails of the original distribution disappear — [Shumailov et al., Nature 2024](https://www.nature.com/articles/s41586-024-07566-y). *Accumulating* synthetic data alongside the original real data avoids collapse, while *replacing* data causes it — [Gerstgrasser et al. 2024, arXiv 2404.01413](https://arxiv.org/abs/2404.01413)
- PII detection and anonymisation: Microsoft Presidio (open source, regex plus NER recognisers, pluggable) — [Presidio](https://github.com/microsoft/presidio)
- Users keep copyright in their Inputs under OpenRouter's terms (§6.1) and DeepSeek's (§4.2(1)) — [OpenRouter Terms](https://openrouter.ai/terms); [DeepSeek ToU](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html)
- Erasure: SISA sharding makes forgetting a data point cheaper by retraining only the affected shard — [arXiv 1912.03958](https://arxiv.org/abs/1912.03958)
- MIZAN's existing gates:
  - capture is skipped unless `stateless.trains()`;
  - Imtihan and Muqabala runs are bound stateless;
  - WhatsApp words "never become training data" (`stateless.no_training`);
  - export requires explicit review (`review_status`, `reviewed_content_hash`).
  — [repo: backend/learner/ruh_learner.py](/backend/learner/ruh_learner.py); [repo: CLAUDE.md](/CLAUDE.md)

### Inferences
- **Pipeline order for MIZAN's export** (each step logged with counts, the dataset hash recorded in a Sakk `system` receipt):
  1. **Consent**: include only users who opted in. The default should be opt-in for training a weight model, as distinct from MIZAN's in-context learning, which users can already turn off. Honour a per-user `training: off` like `muhasaba: off`.
  2. **Exclusions**: stateless/Imtihan/Muqabala, WhatsApp, email (third-party text), messages Amanah flagged as injection, pasted documents (fenced `<<untrusted>>` content is third-party text of unknown licence), and images.
  3. **Licence filter**: by `provider`/`model` (§1).
  4. **Outcome filter**: SFT = verified and uncorrected (Isnad sahih/hasan, Tathabbut passed, no Sidq rewrite). KTO-negative = corrected, failed or mawdu'.
  5. **PII scrub**: Presidio plus custom recognisers for Pakistani/Indian phone formats, CNIC/Aadhaar-like numbers, emails, and addresses from Muraqabah places. Replace with typed placeholders.
  6. **Dedupe**: exact hash plus MinHash-LSH near-dupe (e.g. Jaccard ≥ 0.8 on 5-gram shingles), keeping the most recent verified instance. Also cap examples per user (e.g. ≤5% of a family set) so one heavy user does not dominate the adapter.
  7. **Contamination**: drop any training item sharing a 13-gram with Imtihan tasks, `mizan-eval-v1`, Ibrah tasks or family held-out sets. Freeze held-out sets *before* collecting, and add Ibrah items (production failures) to the held-out set, never the training set.
  8. **Balance**: per-family and per-language quotas (Urdu script, Roman Urdu/Hinglish, Arabic, English) so the adapter does not drift to English.
- **Third-party content in "own traffic".**
  - Quran Arabic text is not copyrighted, but translations (e.g. Saheeh International) and hadith English editions may be. Since MIZAN never wants the model to produce these texts anyway, mask or strip quoted source passages from training targets. Train the model to *call* Fihris or the hadith index, not to reproduce text. This also avoids memorising translations.
  - The Quranic Arabic Corpus morphology is GPL. MIZAN deliberately does not ship it, so keep its glosses out of model training data unless the GPL implications for weights are accepted.
- **Collapse guard.** Never train only on the student's own outputs. Each cycle should include teacher-verified examples (while the API share is >0), environment-verified self-samples (ReST-EM/GRPO), and a fixed replay slice of original human/general data. Accumulate; never replace.
- **Mahw integration.** On erase:
  1. Remove the chat's rows from `interactions` and from every exported dataset version.
  2. Mark adapters trained on those rows as "contains erased data".
  3. Retrain affected per-user adapters at once, and family adapters at the next cycle (or within a stated SLA).
  4. Record this in the Mahw receipt.

  Per-user or per-month shards (SISA) keep this cheap.

### Gaps
- Legal requirements for erasing personal data that has entered model *weights* (GDPR Art. 17, Pakistan/India data-protection law) were not researched in this session.
- The licences of the hadith-api English editions and the Quran translations MIZAN downloads were not checked.
- No measured figure for how much PII typically appears in assistant chat logs (to size scrubbing effort) was collected.
