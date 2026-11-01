# Datasets and languages for MIZAN's self-learning: Hugging Face seeding, new languages (Tamil), and a safe admin seeding flow (as of 28 October 2026)

Scope: which open datasets can seed MIZAN's own weighted naive Bayes readers (Qasd intent, yes/no facets, Lughah language ID) and a later small LM; what their licences allow; how a new language is learned; how an admin seeding flow should value, check and undo data. Hub metadata (licence tag, last update, language tags, gating) was read live from the Hugging Face Hub on 2026-10-28 through the Hub API; "Updated" dates below are the Hub's.

---

## 1. Labelled intent/task datasets in many languages (repo id, size, languages, licence, mapping to MIZAN intents)

### Takeaway
MASSIVE (CC BY 4.0, 51 locales including ta-IN, ur-PK, hi-IN, ar-SA, bn-BD, ms-MY, id-ID, tr-TR, all parallel by utterance id) is still the only large, human-localized, openly licensed intent corpus that covers all eight target languages. The other multilingual intent sets (MTOP, MInDS-14, Multi3NLU++, MultiATIS++) cover few or none of them. Aya, xP3 and IndicAlign are task/instruction collections, not intent-labelled, but they are large multilingual sources of *requests* whose task metadata can serve as weak labels. CLINC150 and Banking77 are English-only, but CLINC150 is the standard source of out-of-scope ("converse"/none) examples.

### Cited Findings

**Coverage of the 8 target languages (from Hub language tags, read 2026-10-28)**

| Dataset (repo id) | ta | ur | hi | ar | bn | ms | id | tr | Licence | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| `AmazonScience/massive` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | CC BY 4.0 | [HF](https://huggingface.co/datasets/AmazonScience/massive) |
| `mteb/amazon_massive_intent` (parquet mirror) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Apache-2.0 tag on the mirror (the underlying data stays CC BY 4.0) | [HF](https://huggingface.co/datasets/mteb/amazon_massive_intent) |
| `CohereLabs/aya_dataset` | ✓ | ✓ | ✓ | ✓ (arb + dialects) | ✓ | ✓ | ✓ | ✓ | Apache-2.0 | [HF](https://huggingface.co/datasets/CohereLabs/aya_dataset) |
| `CohereLabs/aya_collection` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Apache-2.0 | [HF](https://huggingface.co/datasets/CohereLabs/aya_collection) |
| `bigscience/xP3` | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | Apache-2.0 | [HF](https://huggingface.co/datasets/bigscience/xP3) |
| `ai4bharat/indic-align` | ✓ | ✓ | ✓ | – | ✓ | – | – | – | CC BY 4.0 | [HF](https://huggingface.co/datasets/ai4bharat/indic-align) |
| `mteb/mtop_intent` (MTOP) | – | – | ✓ | – | – | – | – | – | "unknown" | [HF](https://huggingface.co/datasets/mteb/mtop_intent) |
| `PolyAI/minds14` | – | – | – | – | – | – | – | – | CC BY 4.0 | [HF](https://huggingface.co/datasets/PolyAI/minds14) |
| `clinc/clinc_oos` | en only | | | | | | | | CC BY 3.0 | [HF](https://huggingface.co/datasets/clinc/clinc_oos) |
| `PolyAI/banking77` | en only | | | | | | | | CC BY 4.0 | [HF](https://huggingface.co/datasets/PolyAI/banking77) |

**MASSIVE**
- 1M realistic, parallel, labelled virtual-assistant utterances, 51 languages, 18 domains, 60 intents, 55 slots; built by professional translators localizing the English SLURP set (16,521 utterances) into 50 languages from 29 genera; with English, 587k train, 104k dev, 152k test, 153k held out for MMNLU-22 — [MASSIVE paper, arXiv 2204.08582](https://arxiv.org/abs/2204.08582)
- Quality control: each localized utterance is judged by three MTurk workers for intent match, slot match, grammaticality/naturalness, and more; translators and judges were selected with quizzes — [arXiv 2204.08582](https://arxiv.org/abs/2204.08582)
- Hub card last updated 16 Nov 2022; 627.6K downloads; CC BY 4.0. The `mteb` parquet mirror was updated 24 Feb 2026 and is the one MIZAN's `scripts/build_massive_seeds.py` already reads (pinned by commit) — [AmazonScience/massive](https://huggingface.co/datasets/AmazonScience/massive), [mteb mirror](https://huggingface.co/datasets/mteb/amazon_massive_intent), local `scripts/build_massive_seeds.py`
- Mapping: MASSIVE's 60 intents are voice-assistant intents (alarm, calendar, weather, music, IoT, QA factoid, general quirky, etc.). Only a few line up with MIZAN's intents (e.g., `qa_factoid` ≈ factual/web search, `general_quirky`/`general_greet` ≈ converse, `datetime_query` ≈ dates, `qa_maths` ≈ compute). MIZAN already aligns them automatically: its own Qasd model reads the English utterances, an intent is aligned only if the 95% Wilson lower bound of the majority share exceeds ½, and the label carries over to the same utterance id in every language — local `scripts/build_massive_seeds.py` (docstring)

**Aya**
- Aya Dataset: 204,114 human-annotated prompt–completion pairs (138,844 original, 65,270 re-annotations), 65 languages (28 high-, 12 mid-, 31 low-resource), train 202,364 / test 1,750; fields `inputs`, `targets`, `language`, `language_code`, `annotation_type`, `user_id`; Apache-2.0; card updated 15 Apr 2025 — [aya_dataset card](https://huggingface.co/datasets/CohereLabs/aya_dataset)
- Aya Collection: instruction-style templates from fluent speakers applied to 44 datasets, including translations of 19 instruction datasets into 101 languages, 513M instances; each row has `dataset_name`, `sub_dataset_name`, `task_type`, `template_id`, `language`, `script` — [aya_dataset card (family table)](https://huggingface.co/datasets/CohereLabs/aya_dataset), [aya_collection README](https://huggingface.co/datasets/CohereLabs/aya_collection)
- Aya evaluation suite: 250 culturally grounded prompts in 7 languages, 200 translated prompts in 24 languages; Aya red-teaming: harmful prompts in 8 languages, 9 harm categories with "global"/"local" labels — [aya_dataset card](https://huggingface.co/datasets/CohereLabs/aya_dataset)

**xP3**
- Crosslingual Public Pool of Prompts: prompts and datasets across 46 languages and 16 NLP tasks, used to train BLOOMZ and mT0; Apache-2.0; 100M–1B rows; last updated 30 May 2023 — [bigscience/xP3](https://huggingface.co/datasets/bigscience/xP3) ([arXiv 2211.01786](https://arxiv.org/abs/2211.01786))

**IndicAlign (AI4Bharat)**
- Instruction and toxic-alignment collections for 14 Indic languages (Indic-ShareLlama, Dolly-T, OpenAssistant-T, WikiHow, IndoWordNet, Anudesh, Wiki-Conv, Wiki-Chat; HHRLHF-T, Toxic-Matrix); translated with IndicTrans2; CC BY 4.0 tag; updated 25 Jul 2024 — [ai4bharat/indic-align](https://huggingface.co/datasets/ai4bharat/indic-align) ([arXiv 2403.06350](https://arxiv.org/abs/2403.06350))
- A government (AIKosh) listing shows CC BY 4.0 for the WikiHow subset specifically; translated third-party subsets may carry their own terms — [AIKosh listing](https://aikosh.indiaai.gov.in/home/datasets/details/indic_align_wikihow.html)

**English intent sets**
- Banking77: 13,083 customer-service queries labelled with 77 fine-grained banking intents; 10,003 train / 3,080 test; CC BY 4.0 — [PolyAI/banking77](https://huggingface.co/datasets/PolyAI/banking77), [Casanueva et al. 2020, arXiv 2003.04807](https://arxiv.org/pdf/2003.04807)
- CLINC150: built to test out-of-scope (OOS) detection, "queries that do not fall into any of the system's supported intents"; CC BY 3.0 — [clinc/clinc_oos](https://huggingface.co/datasets/clinc/clinc_oos). Per the paper, 150 intents in 10 domains with an OOS class (from prior knowledge of [Larson et al. 2019, arXiv 1909.02027](https://arxiv.org/abs/1909.02027); per-split counts not re-fetched in this session)

**Other multilingual intent sets (few target languages)**
- MInDS-14: spoken intent detection, 14 e-banking intents, 14 language varieties (en, fr, it, es, pt, de, nl, ru, pl, cs, ko, zh); CC BY 4.0 — [PolyAI/minds14](https://huggingface.co/datasets/PolyAI/minds14)
- Multi3NLU++: 3,080 utterances per language, banking + hotels, 62 intents, multi-label; CC BY 4.0 — [uoe-nlp/multi3-nlu](https://huggingface.co/datasets/uoe-nlp/multi3-nlu) ([arXiv 2212.10455](https://arxiv.org/abs/2212.10455))
- MTOP: 6 languages (de, en, fr, hi, es, th); licence "unknown" on the mteb mirror — [mteb/mtop_intent](https://huggingface.co/datasets/mteb/mtop_intent)
- SLURP (MASSIVE's English source) is mirrored at `marcel-gohsen/slurp` with no licence tag (audio + text) — [marcel-gohsen/slurp](https://huggingface.co/datasets/marcel-gohsen/slurp)
- `FBK-MT/MultiATIS` does not exist on the Hub (lookup returned "not found") — Hub API lookup, 2026-10-28

**Real user requests (not intent-labelled, but realistic)**
- WildChat-1M: 1M ChatGPT conversations from users who opted in for free access, 68 languages detected; public version holds only non-toxic turns; licence changed to ODC-BY in June 2024, applied retroactively — [WildChat paper](https://arxiv.org/pdf/2405.01470), [WildChat-1M README](https://huggingface.co/datasets/allenai/WildChat-1M/blame/7d6490e462285cf85d91eabea0f9a954fbddcd1f/README.md)
- WildChat-4.8M: 3,199,860 non-toxic conversations; ODC-BY; updated 11 Aug 2025 — [allenai/WildChat-4.8M](https://huggingface.co/datasets/allenai/WildChat-4.8M)

### Inferences
- For Qasd, MASSIVE is the language bridge, not the intent source: it gives Tamil/Urdu/Malay wording for the handful of MIZAN intents that overlap (dates, compute, factual questions, conversation). Most MIZAN intents (quran lookup, hadith lookup, build a project, run code, sarf, hf_hub, watch, salah) have no equivalent in any public intent corpus. Their non-English seeds have to come from (a) translation of MIZAN's own English/Urdu seeds, (b) Aya/IndicAlign/WildChat prompts weakly labelled by MIZAN's own model, or (c) admin-typed examples.
- CLINC150's OOS split is useful for calibrating the `converse` class against "requests that look like tasks but match no MIZAN recipe". The licence (CC BY 3.0) allows this with attribution.
- WildChat is the best source for the *prior*: its distribution of what real users type (lots of code, writing and chit-chat; many languages; code-mixed text) is closer to MIZAN's chat than MASSIVE's voice-assistant commands. But its responses are ChatGPT outputs (see §2 for terms), so use only the user turns for the classifiers.
- The parallel structure of MASSIVE (same id in 51 locales) is the strongest device for a new language: once an English id is aligned to a MIZAN intent, 50 human-localized versions come for free. That is exactly how `build_massive_seeds.py` works, and the design is sound.

### Gaps
- Exact per-language row counts of Aya Dataset (e.g., how many Tamil pairs) were not retrieved; the card's language table was truncated.
- SLURP's own licence and MultiATIS++ distribution terms (believed to be LDC-distributed) were not verified.
- No Tamil-specific intent-classification dataset beyond MASSIVE was found on the Hub; a "tamil instruct" Hub search returned only small instruct sets (e.g., `Hemanth-thunder/tamil-open-instruct-v1`, 52 downloads) — [Hub search](https://huggingface.co/datasets?search=tamil%20instruct).

---

## 2. SFT/instruction and preference datasets: licences, restrictive terms, and how to use prompts and responses

### Takeaway
Most popular SFT and preference sets are *permissively tagged* (MIT, Apache-2.0, ODC-BY, CC BY 4.0) but contain *outputs of proprietary or community-licensed models* whose terms travel separately: OpenAI-generated rows (UltraChat, OpenHermes, WildChat responses, Nectar's GPT-4 rankings), Llama-generated rows (Magpie: "Llama" naming + "Built with Llama"), and non-commercial subsets inside mixtures (No Robots, CC BY-NC 4.0, inside Tulu 3). The cleanest for a self-hosted product are human-written or human-rated sets: Aya Dataset (Apache-2.0), HelpSteer2/3 (CC BY 4.0), OASST1 (Apache-2.0). For MIZAN's classifiers, use only the *prompts* (user-written or synthetic instructions) with MIZAN's own weak labels; keep model *responses* for a later small LM and only from sources whose terms allow training a distributed model.

### Cited Findings

**SFT / instruction**

| Repo id | Size | Languages | Licence tag | Restrictions found | Source |
|---|---|---|---|---|---|
| `allenai/tulu-3-sft-mixture` | 939,344 samples (18 subsets) | ~70 incl. tam, urd, hin, arb, ben, msa, ind, tur (via Aya) | ODC-BY-1.0 | "Some portions of the dataset are non-commercial"; includes No Robots (CC-BY-NC-4.0, 9,500 prompts) and WildChat GPT-4 (100,000 prompts); "includes output data generated from third party models that are subject to separate terms"; "intended for research and educational use" | [card](https://huggingface.co/datasets/allenai/tulu-3-sft-mixture) |
| `teknium/OpenHermes-2.5` | ~1M, mostly synthetic | eng | none on card | tagged `GPT-4`, `Distillation`; no licence stated | [card](https://huggingface.co/datasets/teknium/OpenHermes-2.5) |
| `HuggingFaceTB/smoltalk` | ~1M samples (SmolLM2 paper [arXiv 2502.02737](https://arxiv.org/abs/2502.02737)) | en | Apache-2.0 for the new subsets only | the card applies Apache-2.0 to Smol-Magpie-Ultra, Smol-constraints, Smol-rewrite, Smol-summarize; for mixed-in public sets "please refer to the original dataset for the license" | [card](https://huggingface.co/datasets/HuggingFaceTB/smoltalk), [smol-smoltalk README](https://www.huggingface.co/datasets/HuggingFaceTB/smol-smoltalk/blob/main/README.md) |
| `HuggingFaceTB/smoltalk2` | Mid / SFT / Preference subsets (SmolLM3); SFT includes `smoltalk_multilingual8_Qwen3_32B_think` 244,736 rows, `aya_dataset_Qwen3_32B_think` 15,222; Preference includes Tulu-3 8B pref mix 230,501 | multilingual subsets | no licence tag in Hub metadata | responses regenerated by Qwen3-32B | [card](https://huggingface.co/datasets/HuggingFaceTB/smoltalk2) |
| `Magpie-Align/Magpie-Llama-3.3-Pro-1M-v0.1` | ~1M | en | `llama3.3` | Llama licence terms (below) | [card](https://huggingface.co/datasets/Magpie-Align/Magpie-Llama-3.3-Pro-1M-v0.1) |
| `argilla/magpie-ultra-v1.0` | 1M–10M | en | none in Hub metadata | generated with Llama 3.1 405B-Instruct + Llama-Guard-3-8B + Llama-3.1-8B; each row carries `intent`, `knowledge`, `difficulty`, `quality`, `primary_tag`, `other_tags`, `guard`, `embedding` | [card](https://huggingface.co/datasets/argilla/magpie-ultra-v1.0) |
| `HuggingFaceH4/ultrachat_200k` | ~200k (filtered from 1.4M) | en | MIT | dialogues "generated by ChatGPT" | [card](https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k) |
| `CohereLabs/aya_dataset` | 204k | 65 | Apache-2.0 | human-written; annotator demographics included | [card](https://huggingface.co/datasets/CohereLabs/aya_dataset) |
| `ai4bharat/indic-align` | 10M–100M | 14 Indic | CC BY 4.0 | machine-translated with IndicTrans2 | [card](https://huggingface.co/datasets/ai4bharat/indic-align) |

**Preference / RLHF**

| Repo id | Size | Languages | Licence tag | Restrictions found | Source |
|---|---|---|---|---|---|
| `openbmb/UltraFeedback` | ~64k prompts × 4 responses = 256k samples | en | MIT | responses from many LLMs; fine-grained ratings (GPT-4 as annotator per the paper, [arXiv 2310.01377](https://arxiv.org/abs/2310.01377)) | [card](https://huggingface.co/datasets/openbmb/UltraFeedback) |
| `nvidia/HelpSteer2` | 10k–100k | en | CC BY 4.0 | human annotation "in partnership with Scale AI" | [card](https://huggingface.co/datasets/nvidia/HelpSteer2) |
| `nvidia/HelpSteer3` | 10k–100k | en, zh, ko, fr, es, ru, ja, de, it, pt, pl, id, nl, vi | CC BY 4.0 | updated 16 Nov 2025 | [card](https://huggingface.co/datasets/nvidia/HelpSteer3) |
| `Skywork/Skywork-Reward-Preference-80K-v0.2` | 77,016 pairs | (en) | none in Hub metadata | subsampled from HelpSteer2, OffsetBias, WildGuard, Magpie DPO series (Llama outputs); v0.2 removed 4,957 pairs with "significant n-gram overlap" with RewardBench prompts | [card](https://huggingface.co/datasets/Skywork/Skywork-Reward-Preference-80K-v0.2) |
| `allenai/llama-3.1-tulu-3-8b-preference-mixture` | 100k–1M | | ODC-BY | "Some portions of the dataset are non-commercial. We present the mixture as a research artifact." | [card](https://huggingface.co/datasets/allenai/llama-3.1-tulu-3-8b-preference-mixture) |
| `berkeley-nest/Nectar` | 100k–1M, 7-wise rankings | en | Apache-2.0 | "under the condition that the dataset is not used to compete with OpenAI"; rankings generated by GPT-4 | [card](https://huggingface.co/datasets/berkeley-nest/Nectar) |

**Terms that travel with model outputs**
- Llama 3.1 licence s.1.b.i: anyone who uses Llama Materials "or any outputs" to create, train, fine-tune or improve a distributed AI model "shall also include 'Llama' at the beginning of any such AI model name", and must "prominently display 'Built with Llama'"; s.2 requires a separate licence above 700 million monthly active users — [Llama 3.1 Community License](https://dev.meta.ai/llama/llama3_1/license)
- Nectar's card states its Apache-2.0 grant is conditional on not competing with OpenAI — [berkeley-nest/Nectar](https://huggingface.co/datasets/berkeley-nest/Nectar)
- Tulu 3 states its third-party model outputs "are subject to separate terms governing their use" — [tulu-3-sft-mixture](https://huggingface.co/datasets/allenai/tulu-3-sft-mixture)

**Weak-label hooks already present in the data**
- Magpie-Ultra rows carry model-assigned `intent`, `primary_tag`/`other_tags`, `difficulty`, `quality` and a safety `guard` label per instruction — [argilla/magpie-ultra-v1.0 README](https://huggingface.co/datasets/argilla/magpie-ultra-v1.0)
- Aya Collection rows carry `task_type`, `dataset_name` and `template_id`, e.g. `templated_indic_sentiment`, `templated_indic_paraphrase`, `templated_mintaka` (QA), `templated_masakhanews` — [aya_collection README](https://huggingface.co/datasets/CohereLabs/aya_collection)
- Tulu 3 rows carry `source` (e.g., Persona MATH, Persona Python, CoCoNot, WildGuardMix) — [tulu-3-sft-mixture](https://huggingface.co/datasets/allenai/tulu-3-sft-mixture)

### Inferences
- **Prompts → intent/facet seeds (weak supervision).** Treat each source's own metadata as a noisy *labelling function*, not a label. Examples: Tulu `source=Persona MATH/GSM/Algebra` → `compute` candidate; `Persona Python`/`Evol CodeAlpaca` → `run code`/`build a project` candidate; Magpie `primary_tag ∈ {Math}` → compute, `{Coding & Debugging}` → code, `{Information seeking}` → `fact` facet / web search, `{Creative writing, Role playing, Brainstorming, Advice seeking}` → converse; Aya Collection `task_type=translation` → (a translation intent if MIZAN has one, else converse). Then let MIZAN's own posterior decide. Keep a prompt only when (i) the labelling function and Qasd agree and (ii) the cluster-level Wilson lower bound exceeds ½. That is the same rule `build_massive_seeds.py` uses, so it stays "evidence, not word lists".
- **Clustering/label propagation for the long tail.** Embed (or hash-vectorise) prompts, cluster, have the admin label one medoid per cluster in the Ta'lim UI, and propagate to the cluster only where the within-cluster Qasd agreement is decisive. For a naive Bayes reader, propagating labels from parallel translations (MASSIVE ids, Aya translated subsets, IndicAlign/IndicTrans2) is safer than embedding-based propagation, because the label is tied to the *same meaning*.
- **Facets.** Ruling (`ruling`) and deen facets have no public labelled source. Usable negatives come from WildGuard/CoCoNot/HelpSteer prompts (none about fiqh). Positives can be bootstrapped from fatwa question sets (see §3) as *question text only*: the question is the user's wording, the answer is the scholar's, and copyright issues mainly concern the answers.
- **Responses → later small LM.** Rank by licence cleanliness: (1) human-written: Aya Dataset (Apache-2.0), OASST1 (Apache-2.0), HelpSteer2/3 responses with human ratings (CC BY 4.0); (2) open-model synthetic with permissive output terms: SmolTalk's own subsets (Apache-2.0) and Qwen-regenerated SmolTalk2 rows (licence to verify); (3) Llama-generated (Magpie, Skywork's Magpie DPO pairs): usable, but a distributed model must be named "Llama…" and say "Built with Llama"; (4) OpenAI-generated (UltraChat, OpenHermes, WildChat responses, Nectar, UltraFeedback ratings): avoid for a model MIZAN distributes; keep for internal evaluation at most.
- Preference pairs map naturally onto MIZAN's acceptance gate: a chosen/rejected pair is a paired comparison, the same statistical shape as the gate's paired bootstrap. HelpSteer's multi-attribute ratings (helpfulness, correctness, coherence, complexity, verbosity) are the closest open analogue to Furqan/Isnad grades if MIZAN ever trains a reward-like scorer.

### Gaps
- Licence tags were missing from Hub metadata for SmolTalk2, magpie-ultra-v1.0 and Skywork-80K-v0.2; their card bodies were not read to the end, so their licences remain unverified here.
- OpenAI's current (Oct 2026) terms on using outputs to train models were not re-fetched; the "do not compete" restriction is cited only through Nectar's card.
- No 2025–2026 *multilingual preference* dataset covering Tamil/Urdu/Malay was found in this pass (HelpSteer3's 14 languages include only Indonesian from the target set).

---

## 3. Islamic datasets: Quran text and translations, tafsir, hadith, morphology, Islamic QA

### Takeaway
There are now large, actively maintained Hub mirrors (e.g., `quranlab/quran-tafsir`, `quranlab/hadith`, both updated 14 Oct 2026), but their licences are "other"/mixed per config. The authoritative upstream terms are restrictive in ways that matter for MIZAN: Tanzil text is verbatim-only with attribution; QAC is GPL with a research-only note; QRCD (QuranQA) is CC BY-NC-ND; hadith *translations and gradings* belong to their translators and graders even where the code or Arabic text is public-domain. MIZAN's current approach (download once from the source, pin by SHA-256, never ship, quote verbatim) fits these terms best. For classifier seeding, the useful Islamic data is *question wording* (QuranQA, IslamicEval, fatwa questions), not the texts themselves.

### Cited Findings

**Quran text and translations**
- Tanzil Quran text: distributed under CC BY 3.0; verbatim copies allowed, modification prohibited; reusers must credit Tanzil.net and link to it; the notice must accompany copies and derived files holding a substantial portion — [tanzil-downloader README quoting the Tanzil notice (secondary)](https://npmjs.com/package/tanzil-downloader); credits page [tanzil.net/docs credits](https://tanzil.net/docs/_export/raw/credits). MIZAN's Lughah corpus already records the same terms for its every-seventh-ayah sample — local `backend/tadbir/data/lughah/LICENSES.md`
- alquran.cloud credits Tanzil.net for part of the Arabic text it serves — [alquran.cloud terms](https://alquran.cloud/terms-and-conditions)
- The Tanzil translation collection is also redistributed via OPUS — [OPUS Tanzil](https://opus.nlpl.eu/Tanzil/corpus/version/Tanzil)

**Tafsir**
- `quranlab/quran-tafsir`: multilingual commentaries and annotated translations aligned to the canonical 6,236 ayahs; text "reaches you through the work of QuranEnc.com, Tafsir Center for Quranic Studies, Quranic Universal Library…"; licence `other`, `license_name: mixed-per-config-terms`; dozens of classical Arabic tafsir configs (Ibn Kathir, al-Tabari, al-Qurtubi, al-Baghawi, al-Jalalayn, al-Razi, al-Sa'di and many more); 33 languages incl. ta, ur, hi, bn, id, tr, ar; updated 14 Oct 2026 — [quranlab/quran-tafsir](https://huggingface.co/datasets/quranlab/quran-tafsir)
- Smaller tafsir sets: `tafsircenter/tafsir-mcp-data`, `M-AI-C/en-tafsir-ibn-kathir`, `nassimjp/Pashto-Tafsir-Reasoning` — [Hub search "tafsir"](https://huggingface.co/datasets?search=tafsir)

**Hadith**
- `quranlab/hadith`: the Six Books + Muwatta, Musnad Ahmad, al-Darimi and the forty-collections, Arabic plus translations, "grader-attributed gradings", one config per (collection × language); licence `other`; updated 14 Oct 2026 — [quranlab/hadith](https://huggingface.co/datasets/quranlab/hadith)
- fawazahmed0/hadith-api: secondary sources describe the data as released under The Unlicense, and the classical Arabic texts as public domain by age — [CTAN `hadith` package README](https://ctan.org/tex-archive/macros/unicodetex/latex/hadith); contradicted in part by the `quranlab/hadith` maintainers, who read the Unlicense as covering only the repo's code and treat translations and gradings as "© their authors (translators / publishers such as Darussalam; the muḥaddith graders)" — [quranlab/hadith](https://huggingface.co/datasets/quranlab/hadith); repo: [github.com/fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api)
- `meeAtif/hadith_datasets`: six books, English + Arabic + grading + reference links, JSON/CSV, tagged MIT; updated 9 Feb 2026 — [meeAtif/hadith_datasets](https://huggingface.co/datasets/meeAtif/hadith_datasets)
- LK Hadith Corpus (Leeds University & King Saud University): bilingual Arabic–English corpus of the six canonical collections, 10M+ tokens, announced as freely available via the LREC repository — [Altammami et al., LREC 2020](https://aclanthology.org/2020.lrec-1.415); the journal version describes 39,038 annotated hadith — [White Rose eprint 160497](https://eprints.whiterose.ac.uk/id/eprint/160497/); the *paper* is CC BY-NC 4.0, which does not settle the corpus licence — [White Rose eprint 163052](https://eprints.whiterose.ac.uk/id/eprint/163052/). Hub mirror `arbml/LK_Hadith` has no licence tag (updated Oct 2022) — [arbml/LK_Hadith](https://huggingface.co/datasets/arbml/LK_Hadith)

**Morphology**
- Quranic Arabic Corpus: Wikipedia lists the GNU GPL; the project FAQ says data is "for research, not commercial use" under the GNU public license and asks for citation — [Wikipedia](https://en.wikipedia.org/wiki/Quranic_Arabic_Corpus), [corpus.quran.com FAQ](https://Corpus.Quran.com/faq.jsp); a Scribd re-upload carries a CC BY-NC notice instead (conflicting, likely third-party) — [Scribd copy](https://es.scribd.com/document/89539395/083)

**Islamic QA and evaluation**
- Qur'an QA 2023 (QRCD): two tasks, passage retrieval (up to 10 passages for an MSA question; some questions have no answer in the Quran) and reading comprehension; 9 teams/22 runs (retrieval), 6 teams/17 runs (MRC) — [Malhas, Mansour & Elsayed, ArabicNLP 2023](https://aclanthology.org/2023.arabicnlp-1.76); QRCD is CC BY-NC-ND 4.0 and "it is strictly prohibited to make any changes to the QRCD dataset"; it "represents a sample and not all schools of thought" — [Codalab Qur'an QA 2023 Task B](https://codalab.lisn.upsaclay.fr/competitions/14267)
- IslamicEval 2025 (ArabicNLP 2025): first shared task on LLM hallucination in Islamic content; subtask 1 detect and correct hallucinated Quran verses and hadith, subtask 2 answer Quran/hadith questions from grounded sources; 13 teams in the final phase — [Mubarak et al., IslamicEval 2025 overview](https://preview.aclanthology.org/setup/2025.arabicnlp-sharedtasks.67); a 2026 follow-up notes that every system must label every span and none abstains, and proposes an abstention layer — [ICML 2026 abstract](https://icml.cc/virtual/2026/83950)
- Fatwa: `SahmBenchmark/fatwa-qa-evaluation`: 2,000 Arabic Islamic-finance/jurisprudence fatwa QA pairs, Apache-2.0 tag, Dec 2025 — [card](https://huggingface.co/datasets/SahmBenchmark/fatwa-qa-evaluation); other fatwa sets on the Hub are small and of unclear provenance (e.g., `ZenoAbderrahim/binbaz_fatwas_rag`, `androidapps11/assim-fatwas`, `hozifa1/noor-platform-fatwa`) — [Hub search "fatwa"](https://huggingface.co/datasets?search=fatwa)
- Quran audio/alignment (for Sama'): `QUD-Technologies/quranic-universal-ayahs` (CC BY 4.0, ayah audio with word timestamps, updated 27 Oct 2026) — [card](https://huggingface.co/datasets/QUD-Technologies/quranic-universal-ayahs); `Buraaq/quran-md-ayahs` (Quran-MD, multimodal text/linguistic/audio, Muslims in ML @ NeurIPS 2025, [arXiv 2601.17880](https://arxiv.org/abs/2601.17880); no licence tag) — [card](https://huggingface.co/datasets/Buraaq/quran-md-ayahs)

### Inferences
- **Keep texts out of training; keep them as indexed sources.** Tanzil's no-modification term and QRCD's ND term make it unsafe to feed Quran text or QRCD into anything that rewrites it (an LM's training data is a derivative in practice). MIZAN's pattern (quote verbatim from a pinned download; Lughah samples only every seventh ayah, unchanged, with the notice) is consistent with Tanzil's terms.
- **QAC: GPL + "research, not commercial use" is internally inconsistent** (GPL forbids field-of-use restrictions). That is a reason to keep MIZAN's current "download once into `$MIZAN_DATA_DIR`, never ship" practice and to record both statements in provenance.
- **Hadith translations: treat as third-party copyrighted** regardless of a repo's MIT/Unlicense tag (meeAtif's MIT tag over Darussalam-style translations is not credible on its own). The Arabic matn and isnad are safe to index; English quotations should be shown with the source edition's attribution.
- **Seeding Qasd/facets from Islamic QA:** QuranQA and IslamicEval questions are excellent *positive* examples for `quran_search`/`quran_lookup`/`hadith_lookup` and the `deen` facet in MSA. Because QRCD is CC BY-NC-ND, use it only as a held-out evaluation block in Imtihan (unmodified), not as seeds. Fatwa question text (e.g., the Apache-2.0 SahmBenchmark set) can seed the `ruling` facet's positives. The answers should never become Lisan training data.
- IslamicEval's hallucination subtask is close to what Sidq already does (detect and replace altered quotes); its data would make a ready external test for Sidq if its licence allows evaluation use.

### Gaps
- The licence and per-config terms inside `quranlab/quran-tafsir` and `quranlab/hadith` were not read in full (the README is very long); QuranEnc's own terms were not fetched.
- Tanzil's licence page was not fetched directly (only a secondary quotation); the current wording on tanzil.net should be checked.
- The LK Hadith Corpus data licence, the IslamicEval 2025 data licence, and the sunnah.com API terms were not found.
- QRCD's size was not confirmed from a primary source (one secondary 2025 paper says 251 questions).

---

## 4. Language identification data for many languages

### Takeaway
For Lughah's naive Bayes language reader, the best open training sources are Tatoeba (CC BY 2.0 FR, already used), WiLI-2018 (ODbL, 235 languages, balanced), and the per-source corpora behind GlotLID and OpenLID. GlotLID's model is Apache-2.0 (2,102 labels in v3), but both training corpora are gated with per-source licences ("other"). FLORES+ (CC BY-SA 4.0, gated, now maintained by OLDI) should be used only as the *evaluation* set, never as seeds, both to avoid contamination and because of ShareAlike.

### Cited Findings
- GlotLID: v3 supports 2,102 labels (ISO 639-3 + script, e.g. `rus-Cyrl`); the EMNLP 2023 paper's model covered 1,665 languages; model on HF as `cis-lmu/glotlid` under Apache-2.0 — [GlotLID GitHub](https://fr.github.com/cisnlp/GlotLID), [GlotLID paper, arXiv 2310.16248](https://arxiv.org/html/2310.16248v3), [GlotCC paper (v3 > 2,000 labels)](https://arxiv.org/html/2410.23825v2)
- GlotLID corpus: `cis-lmu/glotlid-corpus`, gated (manual approval), licence `other`, sources listed in the repo's `sources.md`, updated 26 Oct 2026 — [cis-lmu/glotlid-corpus](https://huggingface.co/datasets/cis-lmu/glotlid-corpus); a word-list companion `cis-lmu/glotlid-wordlists` is ungated — [Hub search "glotlid"](https://huggingface.co/datasets?search=glotlid)
- OpenLID: 121 million lines of monolingual data, 201 languages; each source "either under an open license for research purposes or described as free to use"; the repo says sources have different licences "but all allow (at minimum) free use for research"; dataset licence tag `other`; the OpenLID *model* is GPL-3.0 — [Burchell et al. 2023, arXiv 2305.13820](https://arxiv.org/abs/2305.13820), [open-lid-dataset GitHub](https://github.com/laurieburchell/open-lid-dataset)
- OpenLID-v2: 200 language varieties, gated (auto), licence `other`, updated 17 Oct 2025 — [laurievb/OpenLID-v2](https://huggingface.co/datasets/laurievb/OpenLID-v2); OpenLID-v3 (HPLT, Feb 2026) targets precision on closely related languages — [arXiv 2602.13139](https://arxiv.org/pdf/2602.13139), [HPLT/OpenLID-v3 card](https://huggingface.co/HPLT/OpenLID-v3/blob/main/README.md)
- FLORES-200 (`facebook/flores`): CC BY-SA 4.0, gated, "no longer being updated"; the newer version is FLORES+ managed by the Open Language Data Initiative — [facebook/flores](https://huggingface.co/datasets/facebook/flores); FLORES+ (`openlanguagedata/flores_plus`) is "an evaluation benchmark dataset for multilingual machine translation", CC BY-SA 4.0, gated, ~220 varieties incl. ta, ur, hi, ar (+dialects), bn, zsm, id, tr, updated 25 Oct 2026 — [openlanguagedata/flores_plus](https://huggingface.co/datasets/openlanguagedata/flores_plus)
- WiLI-2018: 235,000 Wikipedia paragraphs, 235 languages, balanced with a train/test split; ODbL — [MartinThoma/wili_2018](https://huggingface.co/datasets/MartinThoma/wili_2018) ([arXiv 1801.07779](https://arxiv.org/abs/1801.07779))
- `papluca/language-identification`: 90k samples, 20 languages (incl. ar, hi, ur, tr), built from Multilingual Amazon Reviews, XNLI, STSb Multi MT; no licence on the card — [papluca/language-identification](https://huggingface.co/datasets/papluca/language-identification)
- Tatoeba sentences (eng, ara, urd, hin exports) under CC BY 2.0 FR, plus an MIT-licensed Hinglish set, are what Lughah uses today — local `backend/tadbir/data/lughah/LICENSES.md`; [CC BY 2.0 FR](https://creativecommons.org/licenses/by/2.0/fr/)

### Inferences
- **Romanised and code-mixed text is the real gap.** Every LID corpus above is overwhelmingly native-script, edited text. MIZAN's users write "pehli 5 ayat ka urdu tarjuma" (Roman Urdu/Hinglish) and Tanglish/Romanised Tamil. GlotLID's label scheme (language + script) handles this conceptually (`urd-Latn`, `tam-Latn`), but training rows for those labels are scarce. The Hinglish-1M set already in use, plus WildChat user turns (68 languages, real typing), plus admin-taught examples are the most realistic sources.
- **ShareAlike caution:** seeds derived from FLORES+ (CC BY-SA) and shipped inside `tadbir/data/lughah` would arguably need to be shared under CC BY-SA. Using FLORES+ only for held-out evaluation (never stored as a seed) avoids that and keeps the evaluation clean.
- For Tamil, a seed batch can combine MASSIVE ta-IN utterances (short, request-like, CC BY 4.0), Aya Dataset Tamil prompts (Apache-2.0), IndicAlign Tamil (CC BY 4.0, IndicTrans2 output) and WiLI `ta` paragraphs (ODbL). FLORES+ `tam_Taml` devtest serves as the acceptance test.
- Use GlotLID (Apache-2.0) as an *external referee*, not as a source of labels: run it on candidate seeds to flag likely mislabels (e.g., a "Tamil" row that GlotLID reads as `mal-Mlym`), feeding the label-noise step in §6.

### Gaps
- Per-source licence lists for GlotLID (`sources.md`) and OpenLID were not opened, so which subsets permit commercial redistribution is unknown.
- Tatoeba's current per-language sentence counts for Tamil, Malay and Bengali were not retrieved.

---

## 5. How low-resource-language learning works for a classifier and a small LM, and how many examples per class are needed

### Takeaway
Across studies, three things recur. (1) Zero-shot transfer from English loses a lot on low-resource languages: on MASSIVE, XLM-R drops from 83.5% to 68.1% intent accuracy on Tamil and from 83.2% to 65.6% on Urdu. (2) Translating the training data (translate-train) usually beats cross-lingual embeddings alone, but the gain depends on translation quality. (3) Small amounts of in-language labelled data close most of the gap. For a naive Bayes reader with no pretrained encoder, theory says it approaches its (higher) asymptotic error in O(log n) examples (n = number of features), so tens of examples per class give most of the benefit, and more examples help mainly through vocabulary coverage.

### Cited Findings

**MASSIVE: full data vs zero-shot (train on en-US only), intent accuracy %, Base models (~270M params) — Table 8**

| Locale | mT5 T2T full | mT5 Enc full | XLM-R full | mT5 T2T zero | mT5 Enc zero | XLM-R zero |
|---|---|---|---|---|---|---|
| en-US | 87.9 | 89.0 | 88.3 | – | – | – |
| id-ID | 87.0 | 86.8 | 87.1 | 77.0 | 74.1 | 83.1 |
| ms-MY | 86.8 | 86.9 | 86.1 | 69.9 | 66.0 | 76.7 |
| tr-TR | 86.1 | 87.1 | 86.3 | 66.5 | 63.7 | 78.4 |
| hi-IN | 85.6 | 86.2 | 85.8 | 62.4 | 59.3 | 74.8 |
| bn-BD | 84.8 | 85.8 | 84.1 | 56.5 | 52.1 | 66.0 |
| ta-IN | 84.4 | 85.2 | 83.5 | 61.3 | 58.0 | 68.1 |
| ur-PK | 84.3 | 85.1 | 83.2 | 47.2 | 49.0 | 65.6 |
| ar-SA | 81.8 | 82.2 | 80.7 | 59.0 | 58.8 | 62.8 |

— [MASSIVE, arXiv 2204.08582, Table 8](https://arxiv.org/abs/2204.08582)
- Locale averages: full-data intent accuracy 85.3 (mT5 T2T), 86.1 (mT5 Enc), 85.1 (XLM-R); zero-shot 62.9, 61.2, 70.6; lowest zero-shot locale ja-JP (44.8 for XLM-R) — [arXiv 2204.08582, Table 3](https://arxiv.org/abs/2204.08582)
- The highest-to-lowest locale gap in exact match grows from 15 points (full data) to 44 points (zero-shot); XLM-R's per-language pretraining data volume correlates with zero-shot exact match (Pearson 0.54) — [arXiv 2204.08582](https://arxiv.org/abs/2204.08582)

**Cross-lingual transfer methods**
- Multilingual task-oriented dialogue (intent + slots): in the zero-shot setting, translating the training data worked considerably better than the cross-lingual embedding methods tested — [Schuster et al. 2018, arXiv 1810.13327](https://arxiv.org/pdf/1810.13327)
- XeroAlign (aligning sentence embeddings with parallel/translated data) improved XLM-R intent classification by roughly 5–10 points, most on lower-resource languages such as Turkish, Hindi and Thai; on PAWS-X, translate-train (90.1 avg) was barely above target-language training (90.0) — [XeroAlign, arXiv 2105.02472](https://arxiv.org/pdf/2105.02472)
- Self-Translate-Train (the LLM translates its own training data into the target language, then is fine-tuned) beats zero-shot transfer on math, QA and NLI for de/ru/th/zh, with smaller gains where translation quality (BLEU) was lower, e.g. Thai — [Ri, Kiyono & Takase, arXiv 2407.00454](https://arxiv.org/abs/2407.00454v2)
- Self-training with pseudo-labels plus a bilingual task-fitting module has been proposed for zero-shot transfer to low-resource languages without parallel data (abstract only seen) — [arXiv 2310.04726](https://arxiv.org/abs/2310.04726v1)

**How many examples per class**
- Naive Bayes vs logistic regression: the discriminative model has lower asymptotic error, but naive Bayes "may approach its (higher) asymptotic error much faster"; logistic regression needs on the order of n examples (n = features) — [Ng & Jordan, NIPS 2001](https://papers.nips.cc/paper/2001/hash/7b7a53e239400a13bd6be6c91c4f6c4e-Abstract.html); extended to multiclass: naive Bayes needs O(log n) samples to approach its asymptotic error vs O(n) for multiclass logistic regression — [Zheng et al., ICML 2023, arXiv 2302.02334](https://arxiv.org/pdf/2302.02334)
- Few-shot intent detection with pretrained sentence encoders targets ~10 examples per intent (Banking77, 77 intents); dual-encoder detectors beat fine-tuned BERT most in the fewest-shot setting and were robust to hyperparameters — [Casanueva et al. 2020, arXiv 2003.04807](https://arxiv.org/pdf/2003.04807)
- Later 10-shot Banking77 results are in the mid-to-high 80s, e.g., contrastive pre-training + fine-tuning 80.86 (5-shot) and 87.20 (10-shot) — [CPFT, arXiv 2109.06349](https://arxiv.org/pdf/2109.06349)
- SetFit (contrastive fine-tuning of a sentence encoder) reports that with 8 labelled examples per class it is competitive with fine-tuning RoBERTa-large on a 3k-example sentiment set (from prior knowledge of the abstract; not re-fetched) — [Tunstall et al. 2022, arXiv 2209.11055](https://arxiv.org/abs/2209.11055)

### Inferences
- **What MASSIVE implies for MIZAN's Tamil:** the per-locale training set is ~11.5k utterances over 60 intents (587k train ÷ 51 locales), i.e., ~190 per intent, and that buys XLM-R ~83–85% on Tamil. A hashed n-gram naive Bayes reader without pretraining will be below that, but it will improve much faster per example at the start. Plan on 30–100 in-language examples per *MIZAN* intent for decisive posteriors on common intents, and use the acceptance gate to decide when more stop helping. The O(log n) result predicts most of the gain comes early; real text's Zipfian vocabulary means the long tail (rare words, inflected Tamil forms) keeps paying off slowly.
- **Character n-grams are the right inductive bias for Tamil, Malay, Turkish and Urdu:** agglutinative/inflected morphology (Tamil, Turkish) and script variation (Urdu Nastaliq vs Roman Urdu) defeat word features. Hashed character n-grams share evidence across inflected forms, so a few examples generalise further than they would with words.
- **Recommended new-language recipe (classifier):**
  1. *Lughah first:* teach the language with MASSIVE + Aya + WiLI rows (even over intents), and Romanised examples if users write that way. The gate checks that existing languages are not hurt, especially confusable pairs: ta vs ml, ur vs hi in Roman script, ms vs id.
  2. *Translate-train via parallel ids:* carry over aligned MASSIVE intents (existing script). For MIZAN-only intents, have Lisan translate MIZAN's own English seeds into Tamil once (an admin reviews a sample). Tag the rows `source=lisan-translate` so they can be valued and undone separately. Translation quality bounds the gain (Self-Translate-Train), so weight these rows below human-localised ones (e.g., a fitted per-source weight, as Tamyiz already fits feature weights).
  3. *Self-training from verified use:* Tamil requests that MIZAN executes and *verifies* (Tadbir/Hifz already know which runs were verified) become labelled examples via `qasd.learn`. That is self-training with a verifier, which avoids the confirmation-bias problem of plain pseudo-labelling.
  4. *Active learning:* each week, show the admin the Tamil requests with the highest posterior entropy, or where action families nearly tie with `converse` (exactly the `fahm.actionable` boundary), to label in Ta'lim. Uncertainty sampling targets the decision boundary that matters.
- **For a later small LM (Ruh or other):** continued pretraining on in-language text (Aya Collection/IndicAlign Tamil, licence-clean subsets), then SFT on human-written Aya Tamil pairs, then preference data, which is scarce for Tamil (none found). Practical path: generate pairs from MIZAN's own verified vs repaired answers (Tathabbut/Tajriba already produce "first answer failed, repaired answer verified" pairs, effectively on-policy preference data with a programmatic judge).

### Gaps
- No study was found that compares translate-train, zero-shot and self-training *on MASSIVE for Tamil* specifically, or that measures *naive Bayes* learning curves per intent on MASSIVE.
- No 2025–2026 paper was retrieved quantifying examples-per-class for character-n-gram naive Bayes in agglutinative languages; the 30–100 figure above is an inference, to be confirmed with MIZAN's own learning curves (the LOO machinery can produce them directly).

---

## 6. Good practice for an admin data-seeding flow: valuation, contamination/duplicates, licence and provenance, label noise, safe undo

### Takeaway
MIZAN's gate (paired bootstrap over leave-one-out re-reads, refuse at P(worse) ≥ 0.95, undoable) is a sound *batch-level* valuation and matches LOO-style data valuation. Research suggests four additions. (a) Per-row valuation inside a batch: exact LOO is cheap for naive Bayes, and Shapley-style values handle redundancy that LOO misses. (b) A label-noise pass (confident learning) before the gate. (c) Contamination checks against Imtihan, the locked `mizan-eval-v1`, FLORES+ and other held-out sets (n-gram overlap, as Skywork did for RewardBench) plus near-duplicate removal. (d) Machine-readable provenance per row (repo id, commit, licence SPDX, and term flags such as NC/ND/SA/model-output/"Llama naming"), because >70% of popular datasets have missing licence info and >50% have licence errors.

### Cited Findings
- **Data Shapley:** values each training point by its average marginal contribution; uniquely satisfies natural equitable-valuation properties; the authors argue LOO does not satisfy them and that Data Shapley gives more insight than LOO or leverage scores; low-Shapley points "effectively capture outliers and corruptions"; Monte Carlo and gradient estimators make it tractable — [Ghorbani & Zou, ICML 2019](https://proceedings.mlr.press/v97/ghorbani19c.html), [arXiv 1904.02868](https://ar5iv.arxiv.org/html/1904.02868)
- **KNN-Shapley:** exact Shapley values can be computed efficiently for nearest-neighbour models (from prior knowledge; not re-fetched) — [Jia et al. 2019, arXiv 1908.08619](https://arxiv.org/abs/1908.08619)
- **Influence functions:** estimate the effect of removing or up-weighting a training point on a prediction without retraining (from prior knowledge; not re-fetched) — [Koh & Liang 2017, arXiv 1703.04730](https://arxiv.org/abs/1703.04730)
- **Confident learning / cleanlab:** label errors average at least 3.3% across 10 popular benchmark *test* sets (ImageNet validation ≥ 6%); candidates found by confident learning, then checked by crowd workers, with ~51% of flagged candidates confirmed; implemented in the open-source `cleanlab` package — [Northcutt et al., "Pervasive Label Errors in Test Sets", arXiv 2103.14749](https://arxiv.org/abs/2103.14749); method: [Confident Learning, arXiv 1911.00068](https://arxiv.org/abs/1911.00068v4) (listed as under review at JAIR; publication status not confirmed). The thesis version reports 3.4% — [MIT DSpace](https://dspace.mit.edu/handle/1721.1/139321)
- **Licence/provenance:** an audit of 1,800+ text datasets found licence omission rates of 70%+ and error rates of 50%+ on popular hosting sites; the team reduced "Unspecified" licences from 72%+ to 30% and released the Data Provenance Explorer — [Longpre et al., Data Provenance Initiative, arXiv 2310.16787](https://arxiv.org/abs/2310.16787) (Nature Machine Intelligence 2024); follow-up audit of ~4,000 text, speech and video datasets — [arXiv 2412.17847](https://huggingface.co/papers/2412.17847.md)
- **Contamination precedent:** Skywork removed 4,957 preference pairs with significant n-gram overlap with RewardBench prompts and published both the removed set and the method — [Skywork-Reward-Preference-80K-v0.2](https://huggingface.co/datasets/Skywork/Skywork-Reward-Preference-80K-v0.2)
- **Deduplication:** near-duplicate and repeated content is common in LM training sets, and removing it (exact substring + MinHash near-dup) improves models and reduces memorisation (from prior knowledge; not re-fetched) — [Lee et al. 2022, arXiv 2107.06499](https://arxiv.org/abs/2107.06499)
- **Gated/terms-bearing sources need an access record:** FLORES+, GlotLID corpus and OpenLID-v2 are gated on the Hub (access must be requested; the Hub API returned "access denied" for this account) — [flores_plus](https://huggingface.co/datasets/openlanguagedata/flores_plus), [glotlid-corpus](https://huggingface.co/datasets/cis-lmu/glotlid-corpus), [OpenLID-v2](https://huggingface.co/datasets/laurievb/OpenLID-v2)
- MIZAN's existing provenance convention: every seed line starts with `source:id`, and a `LICENSES.md` maps prefixes to licences and notices — local `backend/tadbir/data/lughah/LICENSES.md`

### Inferences
**A seeding pipeline for Ta'lim / HF import (design notes)**
1. **Fetch & pin.** Resolve the HF repo to a commit SHA; record `{repo_id, revision, config, split, row_id, licence_spdx, licence_url, terms_flags[], gated: bool, fetched_at, admin_id}` per row (extend `source:id` to `hf:<repo>@<sha>:<config>/<split>#<row>`). Terms flags: `NC`, `ND`, `SA`, `model_output:{openai|llama|qwen|…}`, `no_compete`, `attribution_text`. Refuse automatically: `ND` sources as seeds (QRCD), `NC` for a product deployment, `model_output:openai` for any LM-training export. Warn on `SA`.
2. **Normalise & dedup.** NFKC + Amanah fold, then exact hash and MinHash/char-shingle near-dup *within the batch* and *against existing seeds*. A near-duplicate of an existing seed adds little evidence but can still pass the gate by inflating counts. Collapse duplicates to one row with a count.
3. **Contamination.** n-gram overlap (e.g., 8–13-gram on words, longer on characters for Tamil/Arabic) against Imtihan tasks, `mizan-eval-v1` (hash-locked), the Ibrah tasks, FLORES+ devtest, MASSIVE *test* split (use only MASSIVE train for seeds) and QRCD. Reject overlaps; log them in the batch report, as Skywork did.
4. **Safety/injection.** Run Amanah on every row (it already skips injected entries for Daftar import); drop rows Amanah reads as injection, since HF datasets are outside text.
5. **Label noise (confident learning, naive-Bayes style).** For each candidate row, compute Qasd's out-of-sample posterior from the *existing* model (or LOO within the batch). Flag rows where the given label's probability falls below that class's per-class threshold (the mean self-confidence of rows of that class, as in confident learning), and cross-check language rows with GlotLID. Show the admin flagged rows first; default to excluding them.
6. **Per-row valuation (cheap for naive Bayes).** Removing one row is just subtracting its counts, so exact LOO of each new row on the gate's metric (log-loss on the existing seeds' LOO re-reads) costs one pass. Rank rows by value; negative-value rows are prime label-noise suspects. LOO underrates redundant rows (two copies each look worthless), so for *groups* (per source, per intent, per translated-vs-human) use a few hundred Monte Carlo permutations (Data Shapley over groups, not rows), which is tractable at that granularity.
7. **Gate (existing).** Paired bootstrap of before/after LOO re-reads; refuse at P(worse) ≥ 0.95. Additions: (a) report the effect *per language and per intent*, so a Tamil batch that slightly hurts Malayalam is visible even when overall P(worse) < 0.95; (b) require a held-out check (FLORES+/MASSIVE test for the new language) to *improve*, not just not regress. Otherwise a batch can be accepted that teaches nothing.
8. **Safe undo.** Store each batch as an append-only, content-addressed record (SHA-256 of normalised rows + provenance). Undo = subtract the batch's counts (exact for naive Bayes) and recompute the `core/data/tamyiz.json` fit cache key. Write a Sakk receipt for accept and undo. Batches build on each other's fitted weights, so undoing an older batch should re-run the gate on the current state (the "after" of later batches may depend on it). Keep a dependency list per batch and warn before undoing a batch later ones were accepted against.
9. **Licence ledger export.** Generate `LICENSES.md` sections automatically from the provenance table (attribution texts for CC BY, Tanzil's notice, MIT notices), so the shipped seed files always carry their notices, as the hand-written file does now.

- Admin-typed examples should carry `source=admin:<id>` and the same valuation. They are often few and high-value, and LOO will show that directly.

### Gaps
- No source was found on data valuation specifically for *naive Bayes* text classifiers or for gating *batches* by paired bootstrap; the per-row LOO-by-count-subtraction method is an inference from the model's additivity.
- Current cleanlab support for streaming or online label-noise detection (2025–2026 versions) was not checked.
- Hub gating terms for FLORES+, GlotLID corpus and OpenLID-v2 (what users agree to on access) could not be read without access.
