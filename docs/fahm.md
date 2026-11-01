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
         + w_text     · (m / m̃)^(−γ) · Σ_text-features n_f · log P(f | c)
         + w_evidence · Σ_evidence-features n_f · log P(f | c)

P(c)     = (N_c + 1) / (N + K)                 Laplace
P(f | c) = (n_cf + α) / (n_c + α · V)          Dirichlet smoothing
P(c | x) = softmax(score)
```

- **Features** are character n-grams (2–4 for intents, 1–5 for languages)
  and, for intents, whole words, hashed into 2¹⁸ buckets (CRC-32), so memory
  stays fixed however much is learned. Spelling variants and code-mixed Hinglish share
  n-grams, so "bnao", "banao" and "banaao" reinforce one another.
- **Two groups of evidence.** A message gives hundreds of overlapping
  n-grams, which plain naive Bayes would count as independent. What a parser
  found (`e:qref` a valid Quran reference, `e:expr` an exact calculation,
  `e:url` a link the user wrote, …) or the context (`c:project`, a coding
  project is selected) is a single token. Each group has its own weight
  (weighted naive Bayes): `w_text` corrects the over-counting and
  `w_evidence` says how much a parser finding is worth.
- **Length.** A long message has far more n-grams than any example, and
  plain naive Bayes would read each one as fresh evidence: a pasted list of
  2,000 words came out as a web search with P = 1.0 (production faculty run,
  28 Oct 2026). The text term is divided by `(m / m̃)^γ`, where `m` is the
  message's count of known text features and `m̃` the examples' median.
  `γ = 0` is plain naive Bayes, `γ = 1` weighs every message's letters as one
  example's worth (document length normalisation, Rennie et al., ICML 2003);
  `γ` is fitted like the weights (Qasd: 0.29).
- **Repetition (Qasd).** A letter pattern said again is bursty, not fresh
  evidence each time (Church & Gale 1995): 160 records repeat "parcel …
  weighs … kg" 160 times. Qasd counts each pattern `log(1 + n)`.
- **Fitted, not chosen.** `α`, the three weights and `γ` are fitted by exact
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

Classes: English, Roman Hindi/Urdu (`hi-latn`), Arabic, Urdu, Hindi (and any
language an administrator teaches, [Ta'lim](talim.md)), plus two neutral
classes that say nothing about the asker:

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

MIZAN's own byte-level language model, the [Ruh reader](ruh-reader.md), reads
the same words as a second opinion: P(language | words) from
log P(words | language), multiplied into Lughah's posterior with a fitted
weight. On held-out seeds and their first 2–3 words it made the probabilities
better calibrated but not the decisions (99.20% and 99.42% against Lughah's
99.38%, two seeds). Its third test (31 Oct 2026, fresh CLINC150 English
requests and never-read Roman rows) passed for both seeds, the gain on
English; it still runs in shadow (`MIZAN_RUH_READER`) and never changes the
decision until the owner turns it on.

## Qasd: what the request is for

Qasd reads four kinds of evidence:

- the request's own words, as n-grams and words
- what MIZAN's parsers find in it (`e:` tokens)
- the context (`c:` tokens)
- the chat so far, as the prior (below)

It returns a posterior over 32 recipes, `converse` and `salam_returned` (a returned salam, recognised and answered as conversation) (among them `quran_count`: how many surahs or ayahs, answered from the surah index, never by a search). `use_tool` is the
request for one of the user's connected tools (GitHub, calendar, email, Drive):
it has no recipe of its own, so it goes to Lisan, which picks among the tools
the user actually has, and MIZAN checks the arguments against the tool's schema. The seeds are in
`backend/tadbir/data/qasd/intents.tsv` (CC0): 1229 requests in five languages
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
3. A family is acted on only when it is **decisive**: more probable than
   every other reading together (P > ½). Below that, MIZAN does not guess an
   action from the likeliest crumb; the family's mass counts as "an action
   MIZAN could not build", and so does the mass of a family whose recipe could
   not be built from these words. Once that mass outweighs the next family, or
   conversation comes next, the request goes on as conversation. On the seed
   requests held out one at a time, this turns away 87 wrong actions and
   leaves 62 right but undecided ones to Lisan (step 5). "Tum pagal ho?" was
   once given the tool list at P = 0.28, and "Garbage area 👇 कुलडी 😁" was
   built as a website at P = 0.25.
4. A family is acted on only if the words made it more probable than it was
   before reading them: its posterior must exceed its prior (the posterior of
   a message with no evidence at all). A message with no evidence of its own
   can never start a recipe; a bare "?" once ran a Quran search on the text
   "?". (A "?" is now read as `again_follow`, below, which only takes up a
   request that went unanswered.)
5. If the action families that each outranked conversation, with more
   evidence than before (step 4), could not be built and together outweigh
   conversation, Lisan may map the wording into MIZAN's action schema. Many
   small readings spread over unrelated actions are uncertainty, not a
   request, and are never mapped. Lisan sees the user's last three messages
   as context, so a word taught in a dialect lesson reads as part of the
   lesson. A fixed answer (`capabilities`, `salam`) is never mapped. MIZAN validates
   every step and runs it itself. A Quran surah must be the user's own, as a
   hadith number must be. If Lisan names a surah the user did not write (53:14
   from memory for "Sidratul muntaha kya hai"), the step is refused. Its
   `quran_search` action searches the user's own words with Fihris instead,
   and Fihris chooses the ayah.

**The chat is the prior.** As Lughah does for the language, Qasd reads the
user's earlier messages in the chat (up to 12) as a Dirichlet prior: each
class starts with one pseudo-count, spread by the model's own prior, and every
earlier message adds its posterior. The model's prior is divided out of the
message's posterior and the chat's multiplied in. In a chat that has been
conversation for a while, a short message that reads only a little like a
request stays conversation; a clear request ("Surah Ikhlas sunao", "2**100
kitna hai") still wins on its own words. Replaying the owner's chat of
27 October (35 messages teaching words of their dialect) took 9 actions
before; now nothing is built or searched: the two lines that quote "kya time
hua" are still answered with the time, and two are read by Lisan with the
chat as context.

**Follow-ups** are intents whose words name something said earlier in the
chat, and Tadbir takes it from there: `silsila_follow` ("karo koshish", the
sequence asked before), `search_bare` ("dhundo pahle", the topic asked before)
`run_follow` ("run this code", "isko chalao": the longest runnable block in
the most recent message that shows one) and `again_follow` ("?", "jawab nahi
aaya": the user's last request when no answer followed it, because the reply
failed or came back empty, is taken up again). With nothing earlier to take,
the request goes on as conversation.

A problem that carries its own definition is not a follow-up even when it
mentions a sequence: "A sequence is defined by x₀ = 1 and x(n+1) = x(n) +
1/x(n) … find the limit" was once read as `silsila_follow` (P = 0.76) and
answered with an earlier sequence. Proof, limit and convergence questions in
five languages are now conversation seeds.

**A term missing inside a sequence** ("13, 26, 64, 118, 274, ?, 628, 778,
1126") is read with every known term at its position, and the rule must
reproduce all of them, the terms after the gap included; the answer is the
missing term (376 here, from 2p² + 3p − 1 over the n-th prime). A `?` at the
end asks for the next term.

**Facets** are separate yes/no models on their own seeds (`facets.tsv`):

- `current`: the answer depends on something current or outside MIZAN; this
  gates a web search that Lisan proposes
- `harder`: the user asks for more effort on what came before
- `explain`: the user asks for the working of a calculation, not only the result
- `fact`: the question asks about the world, so the claims of an answer in the
  model's own words are asked of MIZAN's sources (Ahl al-Dhikr, `docs/ahl-dhikr.md`)
- `ruling`: the question asks for a religious ruling, which a scholar gives
- `deen`: the question is about the Quran, a hadith, belief or worship, so
  Ahl al-Dhikr asks only the user's own `ilm`, never Wikipedia or the web
  (and Tadqiq, Talaqqi and Tadrib leave it alone). Its seeds are [below](#the-deen-facet-31-oct-2026)
- `sarf`: the user asks for the root, wazn or part of speech of an Arabic word
  ([Sarf](sarf.md)); asked only when no request was decisive
- `form`: the request asks for a form of answer MIZAN can count
  ([Nazm](nazm.md))

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

## Iqtibas: words the Quran holds

"light upon light" and "سدرة المنتهى" carry no word that asks for an ayah. What
makes them a Quran request is that they are the Quran's own words, which
Qasd's letters cannot see; seeds of such bare phrases taught Qasd to read any
short odd message as a Quran search. `tadbir/iqtibas.py` looks instead:

1. **The span.** The longest run of the message's words that one of the
   editions Fihris downloads holds word for word. Arabic and Urdu are read
   by words after Fihris's folding, the transliteration by its letters (a
   repeated letter counts once), and English and Hindi by words.
2. **The evidence.** log P(span | drawn from the Quran) − log P(span |
   ordinary speech), a likelihood ratio.
   - The first term is the times the edition holds the span over the places
     a span could start.
   - The second comes from a Witten–Bell bigram model of the ordinary speech
     that ships with MIZAN: the Lughah corpora, without the Uthmani quotes or
     the names, and Qasd's conversation and salam seeds, where everyday salam and dhikr
     live. A phrase people say ("Alhamdulillah") is cheap; "light upon light"
     is not said in passing.
   - The evidence is multiplied by the share of the message the span is, so
     "May Allah have mercy on him", which only holds "have mercy", weighs
     little.
3. **The factor.** The Quran family's posterior is multiplied by exp(b ·
   evidence) and renormalised.
   - b is fitted the way Tamyiz fits its own weights: the value that
     minimises the log-loss, leave-one-out over Qasd's seeds and out of
     sample over `data/iqtibas/calibration.tsv`.
   - That file holds 26 bare quotes sent as requests and 26 Quranic formulas
     said in conversation. Qasd never trains on it.
   - The fit is stored in `core/data/iqtibas.json`, with the SHA-256 of the
     seeds, the calibration file and the editions.
   - After changing either file, refit with `cd backend && python -m
     tadbir.iqtibas --fit`. It needs the editions and fetches them if they are
     missing.

With no span, before the editions are on disk, or with `MIZAN_IQTIBAS=off`
(Settings → Developer → System settings; off in tests), the factor is 1. The editions are
fetched and read at startup, and while they load the message is read without
them. What was found (words, edition, ayah, evidence, factor) is in the trace
and in a conversation result's entities.

Measured on 2026-10-28 (b = 0.041):

| | Without the factor | With it |
|---|---|---|
| Log-loss | 1.0066 | 0.9946 |
| Seeds right (leave-one-out) | 0.7036 | 0.7048 |
| Calibration rows right | 0.56 | 0.69 |

The paired bootstrap's P(seeds worse) is 0.19.

Effect on the held-out requests:

| Request | P(Quran) | Route |
|---|---|---|
| "light upon light" | 0.51 | `quran_search` |
| "سدرة المنتهى" | 0.48 | Lisan maps the wording |
| "Who created the heavens and the earth?" (39:38) | 0.99 | `quran_search` |

Dhikr, "In the name of Allah, let's begin" and the other guard phrases stay
conversation; a salam alone ("peace be upon you") is MIZAN's own `salam` recipe,
never a Quran search. A paraphrase ("Allah does not
burden a soul beyond its capacity") is not a quote and is not helped.
Finding the span takes about 1–17 ms per message.

## How well it does (held-out)

Grouped leave-one-out on the shipped seeds: every seed is judged by a model
that never saw it.

| Model | Classes | Examples | Held-out accuracy |
|---|---|---|---|
| Lughah | 7 | 6246 (1500 sampled for the fit) | 99.2% |
| Qasd, exact intent | 32 | 2382 (1229 seeds, two contexts) | 70.0% |
| Qasd, family (what MIZAN acts on) | 19 | same | 75.0% |
| Qasd, act vs answer in words (P(`converse`) > ½) | 2 | same | 81.5% |
| Facet `current` | 2 | 130 | 83.8% |
| Facet `harder` | 2 | 57 | 77.2% |
| Facet `explain` | 2 | 40 | 90.0% |
| Facet `fact` | 2 | 98 | 87.8% |
| Facet `ruling` | 2 | 179 | 87.2% |
| Facet `deen` | 2 | 794 | 91.8% |
| Facet `sarf` | 2 | 54 | 88.9% |
| Facet `form` | 2 | 159 | 86.8% |

At run time the parsers add precision on top: a recipe is built only when its
parser finds what the recipe needs.

The 26 conversation seeds addressed to MIZAN but not about its tools ("Are you
crazy?", "Can you predict the future?", "Do you have feelings?") cost 0.7
points on the earlier seeds (594 of 778 against 599). The trade is deliberate:
the lost cases are capability questions now answered by Lisan in words, and
the gained ones are questions that used to get the fixed tool list. With the
`run_follow` and `quran_search` seeds too, the earlier seeds score 593 of 778.

## The deen facet (31 Oct 2026)

**What was wrong.** The facet had 110 seeds, and most of its few Devanagari and Arabic-script seeds were about the deen, so the script itself became evidence. Measured with `scripts/facet_eval.py` on MASSIVE 1.1 everyday requests (300 per language, never seeds):
- **Everyday requests read as about the deen:** Hindi 72%, Urdu 61%. "क्या अभी बारिश हो रही है" ("is it raining now") was one of them, and such questions were never asked of Wikipedia.
- **Quran and hadith requests missed:** only 63% of Qasd's own Roman and English ones were read as about the deen.
- **Worship and belief questions missed:** 32% Roman, 80% Devanagari, 25% Urdu/Arabic.

**What was added** (`scripts/facet_eval.py --write 40`; 683 rows):
- **About the deen (yes):** half of Qasd's own Quran and hadith request seeds (by SHA-256; the other half is held out).
- **Not about the deen (no):** half of Qasd's seeds for MIZAN's own actions (computing, programs, searches, pages, in every script, Roman Hindi/Urdu included).
- **Not about the deen (no):** 40 everyday requests per language from MASSIVE 1.1 train (en, hi, ur; CC BY 4.0, written by people).
- **About the deen (yes):** 143 questions about worship and belief in five scripts (`scripts/data/facet_deen_written.tsv`). Questions only, no Quran text. Since the seeds held almost none, they were **written by a language model at the owner's request** and are marked as such. Their held-out counterparts (`scripts/data/facet_deen_heldout.tsv`) were written first and are never seeds.

**The owner's decision: deen safety first.** Reading a question about the deen as worldly would send it to Wikipedia. Reading an everyday question as about the deen only keeps it to the person's `ilm`. Where the two pulled apart, recall on the deen came first.

| Read as about the deen (held out) | Before | After |
|---|---|---|
| Everyday commands, MASSIVE test: en / hi / ur | 0.3% / 72% / 61% | 0.7% / 2.3% / 3.7% |
| Everyday questions, MASSIVE test (qa, cooking, recommendations): en / hi / ur | 2.3% / 76% / 62% | 2.7% / 7.7% / 19% |
| Qasd's held-out action requests: Latin / Devanagari / Arabic script | 8% / 44% / 45% | 0.4% / 11% / 25% |
| Held-out everyday questions written for the test: Latin / Devanagari / Arabic script | 6% / 83% / 12.5% (16 / 6 / 8) | 25% / 17% / 50% |
| **Recall**, held-out Quran/hadith requests: Latin / Devanagari / Arabic script | 63% / 100% / 88% (71 / 8 / 17) | 99% / 87.5% / 100% |
| **Recall**, held-out worship and belief questions: Latin / Devanagari / Arabic script | 32% / 80% / 25% (19 / 10 / 16) | 79% / 80% / 94% |

- **Ta'lim's check** on the facet's own earlier seeds kept the batch: "yes" 0.83 → 0.90, "no" 0.91 → 0.82.
- **Measured and not chosen:**
  - Everyday "no" rows alone removed every false positive, but Hindi recall fell 100% → 0%.
  - Adding MASSIVE's everyday questions as well lowered Urdu false positives (19% → 2%), but Devanagari worship recall fell to 40–50%.
- **What is left.** Everyday "how do I…" questions in Roman Hindi and Urdu ("Chai banane ka tareeqa kya hai?") still read as about the deen 25–50% of the time on small sets. The `ruling` facet is unchanged: every "no" count tried lowered its recall.

## Salam (4:86): pre-registered 1 Nov 2026

**Why.** On production, every conversation answer still came from the teacher model: since 29 Oct, 0 of 26 answers needed no model call. The smallest piece of conversation MIZAN can own is the greeting, which the Quran commands answering with a better greeting or at least the same (4:86).

**What is built** (the owner's decision of 1 Nov):
- A message that is a salam and nothing else ("Assalamualaikum", "AoA bhai", "السلام علیکم ورحمۃ اللہ", "अस्सलामु अलैकुम") is a new Qasd intent, `salam`, with a fixed answer like `capabilities`.
- MIZAN answers it with no model call: "Wa alaikum assalam wa rahmatullahi wa barakatuh" in the message's script, then one line offering help in the message's language.
- A salam with a request or question, a returned salam, other greetings and questions about the salam stay as they are.
- It is turned on directly if it passes, with no shadow, because the reply is fixed words.

**Measured** by `scripts/salam_eval.py` through `fahm.understand`, as production runs it (MIZAN orchestration, Iqtibas on with the Quran's editions):
- **Held-out sets** in `scripts/data/salam/`: `dev.tsv` (51 salam / 64 not) to choose the seeds, and `test.tsv` (48 / 61), read once. Both cover Latin, Arabic and Devanagari script, and neither shares a row with the seeds or the other. They were written by MIZAN's coding assistant (a language model) before any seed, and are marked as such.
- **Bars, on test, all must pass:**
  1. at least **90%** of salam-only messages read as `salam` (Wilson interval reported);
  2. **no** other message read as `salam` (Wilson upper bound reported);
  3. Qasd's earlier seeds no worse by exact leave-one-out against main at 7be4f47, with relabelled rows left out: refused at P(worse) ≥ 0.95, Ta'lim's gate.
- **Reported with no bar:** MASSIVE 1.1's `general_greet` and `general_quirky` test rows (en, hi, ur, ar) read as a salam, listed for a look by hand, since a translator may have written a salam for "hello".
- **If a bar fails**, the result is written as it came and the recipe stays off. The seeds may then be revised against dev only, with a fresh test set.

## What is still written by hand, and why

- **Grammars: exact readers whose findings are evidence.** Quran and hadith
  references, calculations, dates and clock times, links, fenced code, file
  names, Hugging Face links, grid puzzles, runs of numbers, schedules and
  prayer names are parsed exactly. A grammar either finds a
  valid reference or it does not, and what it finds is checked against
  MIZAN's indexes. The model decides how much a finding counts.
- **Clause boundaries** (`and`, `aur`, `phir`, `اور`, `और`). These only
  propose a split; the probabilities decide whether to keep it.
- **Safety guards.** Hudud (what a program may touch) and Amanah's guards
  (hidden characters, links that carry data out, instruction patterns in
  outside text) are rules on purpose; Amanah's evidence model only adds to its
  patterns. A guard must hold for inputs no example covered.
- **Scope of the project blueprints.** Stacks MIZAN does not build itself
  (React, Django, databases, logins, …) are not built by a recipe; the agent
  loop takes them in `hybrid` mode. This is a list of what the blueprints
  cannot do, not a reading of intent.
- **Ta'allum's question words**, which keep a learned request from being
  reused for a question about it. These are the next to move to a facet.
