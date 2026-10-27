# Fahm (فهم): understanding by evidence

Fahm is how MIZAN understands a request before it plans anything. It answers
two questions:

1. **Which language** does the user write in? (`tadbir/lughah.py`)
2. **What is the request for**: which of MIZAN's recipes, or plain
   conversation? (`tadbir/qasd.py`)

Both answers are posteriors computed by one engine, **Tamyiz** (تمييز,
discernment; `core/tamyiz.py`). No word list, cue regex or length threshold
decides either answer: the model weighs the evidence, and the most probable
reading wins.

## The engine: weighted naive Bayes, fitted by leave-one-out

For each class `c` (a language, or an intent):

```
score(c) = w_prior · log P(c)
         + w_text     · Σ_text-features     n_f · log P(f | c)
         + w_evidence · Σ_evidence-features n_f · log P(f | c)

P(c)     = (N_c + 1) / (N + K)                 Laplace
P(f | c) = (n_cf + α) / (n_c + α · V)          Dirichlet smoothing
P(c | x) = softmax(score)
```

- **Features** are character n-grams (2–4 for intents, 1–5 for languages)
  and whole words, hashed into 2¹⁸ buckets (CRC-32), so memory stays fixed
  however much is learned. Spelling variants and code-mixed Hinglish share
  n-grams, so "bnao", "banao" and "banaao" reinforce one another.
- **Two groups of evidence.** A message gives hundreds of overlapping
  n-grams, which plain naive Bayes would count as independent. What a parser
  found (`e:qref` a valid Quran reference, `e:expr` an exact calculation,
  `e:url` a link the user wrote, …) or the context (`c:project`, a coding
  project is selected) is a single token. Each group has its own weight
  (weighted naive Bayes): `w_text` corrects the over-counting and
  `w_evidence` says how much a parser finding is worth.
- **Fitted, not chosen.** `α` and the three weights are fitted by exact
  leave-one-out log-loss. Every example is scored by the model trained on all
  the others, and the values that predict the held-out examples best are
  kept (α from a grid, weights by coordinate descent with golden-section
  search). An example counted in two contexts is held out with its copy
  (grouped leave-one-out), so the estimate is honest.
- **Decision** is MAP: the most probable class, which minimises the expected
  number of mistakes. "Answer in words" (`converse`) is a class with its own
  examples, so no cut-off decides when to act.
- **Learning** is immediate: a verified example is added to the counts.
  Each user's learned examples live in their own `Overlay`, added to the
  shared model for that user only.

Fits are cached with the SHA-256 of the corpus they came from
(`core/data/tamyiz.json` ships with the code; `$MIZAN_DATA_DIR/tamyiz.json`
holds a refit made at run time). A changed corpus is refitted and a stale
value is never used. After editing the seeds:

```bash
cd backend && python -m core.tamyiz_cache
```

## Lughah: the user's language

Classes: English, Roman Hindi/Urdu (`hi-latn`), Arabic, Urdu, Hindi, plus two
neutral classes that say nothing about the asker:

- `quote`: the vowelled Uthmani text of the Quran
- `name`: surah, collection and narrator names in Latin letters, from
  MIZAN's own indexes

A message is read in two steps, as is standard for code-mixed text:

1. Each word is classified on its own. A word whose most probable class is
   `name` or `quote` is material, not the asker's language, and is set aside.
2. The remaining words, in runs of one script, are classified as wholes, so a
   run of Hinglish keeps its English words.

The prior is a Dirichlet over the languages:

- one pseudo-count each
- the user's earlier messages in this chat
- one more, shared by the languages the material is written in. Quoted Quran
  is Arabic; a name is in no language.

So "Bukhari 1" is answered in the language of the chat, a bare ayah in
Arabic, and "Latest news about Gaza search karo" in Hinglish. A first message
of names alone ties, and the first language listed (English, the app's
default) is taken.

Corpus: 900 sentences per language and 600–900 per neutral class, drawn with
a fixed seed (`scripts/build_lughah_corpus.py`):

- Tatoeba (CC BY 2.0 FR)
- Hinglish-Everyday-Conversations-1M (MIT)
- the Quran's Uthmani text (Tanzil)
- MIZAN's indexes, plus lines written for MIZAN

Sources and licences are in `backend/tadbir/data/lughah/LICENSES.md`. Why a
linear model: on romanised Indic text, a linear classifier trained on
synthetic data raised F1 from 74.7% (a pretrained neural model) to 85.4%
([Benton et al. 2025, "Improving Informally Romanized Language
Identification", arXiv 2504.21540](https://arxiv.org/abs/2504.21540)).

## Qasd: what the request is for

Qasd reads three kinds of evidence:

- the request's own words, as n-grams and words
- what MIZAN's parsers find in it (`e:` tokens)
- the context (`c:` tokens)

It returns a posterior over 24 recipes and `converse`. The seeds are in
`backend/tadbir/data/qasd/intents.tsv` (CC0): 696 requests in five languages
and scripts. A seed whose intent does not depend on the selected project is
counted in both contexts, because P(project | intent) is the same for those
intents.

**From posterior to plan** (`fahm.understand`):

1. The posterior is summed by **family**: kinds of one request, such as
   quran / quran_question / quran_explain, or build / edit / project task.
   A request to make something is one family, whether it builds or edits.
2. Families are tried most probable first. Within a family, the most probable
   recipe whose parser finds what it needs (a reference, an expression, a
   link, a schedule) becomes the plan.
3. A family whose recipe could not be built from these words adds its mass to
   "an action MIZAN could not build". Once that mass outweighs the next
   family, or conversation comes next, the request goes on as conversation.
4. If an action was more probable than conversation (P(converse) < ½), Lisan
   may map the wording into MIZAN's action schema. MIZAN validates every
   step and runs it itself.

**Facets** are separate yes/no models on their own seeds (`facets.tsv`):

- `current`: the answer depends on something current or outside MIZAN; this
  gates a web search that Lisan proposes
- `harder`: the user asks for more effort on what came before

**Several requests in one message.** The message is split at its
conjunctions, and the simpler explanation wins:

- If one plan for the whole message already holds what every part asks
  for, it is one request. "Write a function that … and returns …" is one
  program, because its request is the whole text. "Bukhari 1 aur Bukhari 2"
  is two, because one plan holds only one reference.
- When the parts are different actions, the split is kept only if it
  explains the message better than the whole does: the product of the
  parts' probabilities against the whole's. "Every morning after Fajr send
  an ayah and the Hijri date" is one watcher; "Bukhari 1 aur Surah Ikhlas" is
  two requests. A clause MIZAN cannot place
counts as a separate request only when it is decisively an action of its own
(its family's P > ½).

**Learning.** When Lisan or the conversation had to place a request and MIZAN
then verified the work, Qasd adds that wording to the user's own counts. The
next request like it is understood with no model call. Up to 400 examples
are kept per user, and Ta'allum keeps the full mapping alongside.

## How well it does (held-out)

Grouped leave-one-out on the shipped seeds: every seed is judged by a model
that never saw it.

| Model | Classes | Examples | Held-out accuracy |
|---|---|---|---|
| Lughah | 7 | 6246 (1500 sampled for the fit) | 99.2% |
| Qasd, exact intent | 25 | 1323 (696 seeds, two contexts) | 76.0% |
| Qasd, family (what MIZAN acts on) | 16 | same | 80.1% |
| Qasd, act vs answer in words | 2 | same | 86.8% |
| Facet `current` | 2 | 104 | 86.5% |
| Facet `harder` | 2 | 31 | 90.3% |

At run time the parsers add precision on top: a recipe is built only when its
parser finds what the recipe needs.

## What is still written by hand, and why

- **Grammars: exact readers whose findings are evidence.** Quran and hadith
  references, calculations, dates and clock times, links, fenced code, file
  names and Hugging Face links are parsed exactly. A grammar either finds a
  valid reference or it does not, and what it finds is checked against
  MIZAN's indexes. The model decides how much a finding counts.
- **Clause boundaries** (`and`, `aur`, `phir`, `اور`, `और`). These only
  propose a split; the probabilities decide whether to keep it.
- **Safety guards.** Hudud (what a program may touch) and Amanah (instructions
  hidden in outside text) are rules on purpose. A guard must hold for inputs
  no example covered.
- **Scope of the project blueprints.** Stacks MIZAN does not build itself
  (React, Django, databases, logins, …) go to the agent loop. This is a list
  of what the blueprints cannot do, not a reading of intent.
- **Ta'allum's question words**, which keep a learned request from being
  reused for a question about it. These are the next to move to a facet.
