# Qāmūs: MIZAN's own cross-lingual lexicon

Qāmūs (قاموس, "lexicon") lets MIZAN match a word written in one language
against text in another, using the words it translates to. MIZAN learns the
lexicon itself from parallel sentences; no word list is written by hand.
Version 1 pairs English with Hindi (Devanagari), Urdu, Arabic and Tamil.

It was built for one gap. Ahl al-Dhikr (`docs/ahl-dhikr.md`) checks a claim
against a source sentence only when the sentence is *about* the claim:
`ahl_dhikr.about(claim, sentence)` asks that the sentence hold most of the
claim's distinctive words. When the teacher model answers in Devanagari Hindi
or in Urdu ("भारत की राजधानी नई दिल्ली है।") and the source is English
Wikipedia ("New Delhi is the capital of India."), no word is shared, so no
claim could be checked.

Module: `backend/tadbir/qamus.py`. Data: `backend/tadbir/data/qamus/<x>-en.json.gz`.
Builder: `scripts/build_qamus.py`. Measurement: `scripts/qamus_eval.py`.

## Data and licence

The lexicon is learned from **MASSIVE 1.1** (Amazon; FitzGerald et al., 2022;
CC BY 4.0). MASSIVE holds the same voice-assistant utterances in 52
languages, aligned by id. Its train, validation and test splits are 11,514,
2,033 and 2,974 utterances per language. The builder reads the Hugging Face
parquet conversion of `AmazonScience/massive` at a pinned commit, for the
locales `en-US`, `hi-IN`, `ur-PK`, `ar-SA` and `ta-IN`. The SHA-256 of every
file it reads is recorded in each lexicon. The shipped files hold words and
probabilities, never an utterance. The attribution and citation are in
`backend/tadbir/data/qamus/LICENSES.md`.

No Quran or hadith text is used, for training or for measuring.

The measurement also reads **FLORES-101 devtest** (CC BY-SA 4.0). Nothing is
learned from it, and it is not shipped.

## Method

### Words

A word is `core.adaptive.tokenize` of the NFC form of the text. Before Qāmūs,
`tokenize` matched `\w+`, which matches no combining mark, so Devanagari and
Tamil vowel signs and viramas, and Arabic harakat, cut words into pieces
("राजधानी" was read as "र", "जध", "न"). A word now keeps the combining marks
written on it (Unicode category M), as Unicode's word boundaries do
(UAX #29). This applies to every caller of `tokenize`.

Learned items that were stored under the old pieces (Ta'allum, Hifz, Ahl
al-Dhikr and Talaqqi keep the content words of the request that taught them)
can still be erased. Mahw matches both readings: `tokenize(text, marks=False)`
gives the old pieces. Such items are no longer found for reuse: a request in
Devanagari, Tamil or vowelled Arabic that Hifz or Ta'allum kept before is
verified once more and kept under its whole words.

### Pairs

Each utterance id gives one pair: the English words and the other language's
words. MASSIVE marks how each slot was written. A slot the translator
*localised* is not a translation: "the time in London" became "the time in
Delhi". The values of such slots are left out on both sides.

Measured on Hindi before and after this step: "भारत" had been aligned with
india 0.32, japan 0.21 and nigeria 0.08, and after it with india 0.94.

### IBM Model 1 by EM, in both directions

For source sentence E and target sentence F, IBM Model 1 says each target word
f was produced by one of the source words or by a NULL word. NULL is there for
the particles and case endings that no source word produced:

    P(F | E) = Π_{f in F} (1 / (|E| + 1)) Σ_{e in E ∪ NULL} t(f | e)

EM estimates t from the pairs alone. It starts uniform over the word pairs
that co-occur, then repeats two steps:

    E step:  c(f, e) += t(f | e) / Σ_{e' in E ∪ NULL} t(f | e')     for each f in F, e in E ∪ NULL
    M step:  t(f | e) = c(f, e) / Σ_f' c(f', e)

EM stops at the iteration with the highest log-likelihood of the **validation
split**. That was 2 or 3 iterations for every model. On Hindi, the validation
dictionary's F1 (below) was flat from 2 to 20 iterations (0.69 to 0.70), so
the stopping rule changes little.

The model is trained in both directions: t(e | x), English produced from the
other language, and t(x | e).

### Symmetrising

The two directions are multiplied, so a pair is kept only when each word is
what the other is most often written as:

    P(e | x) = t(e | x) · t(x | e) / Σ_e' t(e' | x) · t(x | e')

P(x | e) is computed the same way. A word copied unchanged into the other side
(a name left in Latin letters in a Hindi sentence) is matched as it is and is
not stored.

### How much evidence: the Wilson lower bound

A pair seen in one sentence can get P near 1 from that sentence alone. Each
translation is therefore scored by the 95% Wilson lower bound of P·n successes
in n trials, where n is the number of training sentences that hold the word.
The bound is the same rule MIZAN uses wherever a decision needs both a good
rate and enough observations (`core.adaptive.wilson_bounds`). Within one word
the order is P's.

### The cut-off, chosen on held-out data

A translation is kept when its score is at least a cut-off τ. τ is chosen per
direction as the value that maximises F1 against a **held-out dictionary**
taken from MASSIVE's own annotations, with no hand labelling. A dictionary
entry comes from a slot type that meets all of these:

- it occurs once in the English utterance and once in the other;
- the translator *translated* it (MASSIVE's `slot_method`);
- each value is a single word in its own script.

Its two values are then a word pair, such as `[date : friday]` and
`[date : शुक्रवार]`. The validation split's dictionary (213 to 379 words per
direction) chooses τ. The test split's dictionary measures precision@1.

The Wilson score was adopted over the plain P because validation F1 was
higher in all eight directions:

| Direction | F1 with P | F1 with Wilson |
|---|---|---|
| hi→en | 0.701 | 0.719 |
| en→hi | 0.623 | 0.636 |
| ur→en | 0.691 | 0.702 |
| en→ur | 0.639 | 0.656 |
| ar→en | 0.581 | 0.583 |
| en→ar | 0.426 | 0.462 |
| ta→en | 0.609 | 0.611 |
| en→ta | 0.445 | 0.473 |

### What is stored

For each direction, each word's kept translations are stored with their P,
most probable first. Each file also records:

- the script of each language, read from the data (each letter's Unicode
  name);
- the EM iterations and the held-out log-likelihood trace;
- τ and the validation F1;
- the test measurements.

The four files take 357 KB in all. `python -I scripts/build_qamus.py --data
<folder> --check` rebuilds them and compares the SHA-256 of their content.

## Using it

- `qamus.translations(word, source_lang, target_lang)` gives
  `[(translation, P), …]`.
- `qamus.translate(word, target_lang)` gives a word's translations from every
  language written in the word's script. An Arabic-script word may be Arabic
  or Urdu. A number written in another script's digits ("१९४७") is given in
  ASCII digits.
- `qamus.bridge(text, target_lang)` gives the target-language words a text's
  words translate to.
- `qamus.found_in(words, text)` gives the words with a translation in the
  text.
- `MIZAN_QAMUS=off` turns it off.

### In `ahl_dhikr.about()`

The rule for same-script text is unchanged. A claim's distinctive words are
those carrying more information than its average word (inverse document
frequency over the Lughah corpora). The sentence is about the claim when it
holds more than half of their information.

A distinctive word that is not in the sentence, and is written in another
script than the sentence, now also counts as present when one of its
translations is a word of the sentence. Two conditions keep this as strict as
the literal match:

- **The translation must itself carry information.** A matched translation
  must carry more than the average running word of general language
  (`average_information()`, the same measure that makes "is" and "the"
  function words). "کریں" translated as "the" proves nothing, since "the" is
  in nearly every English sentence.
- **One word of the sentence stands for one word of the claim.** A literal
  word stands only for itself, so a translation may also be used only once.
  "براہ کرم" are two Urdu words for one "please".

Both conditions were adopted because of the measurement below. Without them,
MASSIVE neighbours of another intent were accepted 15.3 to 20.0% of the time,
against 11.7 to 14.0% for the same claims in English.

## Measured (30 October 2026)

### Bilingual lexicon induction, precision@1 on the test split

This is the share of held-out dictionary words, among those the lexicon holds,
whose first translation is right. Coverage is the share of dictionary words
the lexicon holds.

| Direction | precision@1 [95% Wilson] | right / held | coverage |
|---|---|---|---|
| hi→en | 0.845 [0.790, 0.888] | 175 / 207 | 0.70 of 294 |
| en→hi | 0.689 [0.626, 0.746] | 153 / 222 | 0.80 of 277 |
| ur→en | 0.815 [0.761, 0.859] | 198 / 243 | 0.78 of 313 |
| en→ur | 0.734 [0.675, 0.785] | 179 / 244 | 0.84 of 291 |
| ar→en | 0.669 [0.613, 0.720] | 196 / 293 | 0.76 of 384 |
| en→ar | 0.556 [0.492, 0.619] | 129 / 232 | 0.83 of 279 |
| ta→en | 0.768 [0.716, 0.813] | 222 / 289 | 0.63 of 456 |
| en→ta | 0.556 [0.496, 0.615] | 148 / 266 | 0.79 of 338 |

### `about()` across scripts

`scripts/qamus_eval.py` reads every claim against the English sentence that
says it, and against unrelated English sentences. Neither held-out set was
learned from:

- **FLORES-101 devtest** has 1,012 English sentences from Wikinews,
  Wikijunior and Wikivoyage, with professional translations. Encyclopedic
  sentences are the source; their translations are the claims. Unrelated
  means from another article.
- **MASSIVE's test split** uses only utterances with no localised slot.
  Unrelated means of another intent. MASSIVE holds many near-identical
  requests of one intent, which are about the same thing.

The measures:

- **Random:** 20 unrelated sentences per claim, drawn with a fixed seed.
- **Hard:** the three unrelated sentences closest to the claim and its bridge
  by BM25, which a cross-lingual search would return first.
- **English claim:** the existing same-script rule reading the claim's own
  English sentence against the same sentences. This is the rate the new path
  is held to.
- **Through `judge()`:** the claim is accepted and its sentence scores above 0
  by BM25 against the claim's own words (see below).

Rates are given with 95% Wilson intervals where useful.

FLORES-101 (Wikipedia-style):

| Claims in | accepted with Qāmūs | without | through `judge()` | false, random | false, hard | English claim, hard |
|---|---|---|---|---|---|---|
| Hindi | 25 / 1012 (2.5% [1.7, 3.6]) | 1 | 16 | 0 / 20240 | 0 / 3036 | 0 / 3036 |
| Urdu | 10 / 1012 (1.0% [0.5, 1.8]) | 0 | 7 | 0 / 20240 | 0 / 3036 | 0 / 3036 |
| Arabic | 2 / 1012 (0.2%) | 0 | 1 | 0 / 20240 | 0 / 3015 | 0 / 3015 |
| Tamil | 4 / 1012 (0.4%) | 0 | 4 | 0 / 20240 | 0 / 2999 | 1 / 2999 |

MASSIVE test split (in the lexicon's domain):

| Claims in | accepted with Qāmūs | without | through `judge()` | false, random (English claim) | false, hard (English claim) |
|---|---|---|---|---|---|
| Hindi | 60.7% [58.7, 62.7] of 2249 | 1.1% | 6.0% | 0.16% (0.19%) | 14.3% (13.4%) |
| Urdu | 62.3% [60.3, 64.3] of 2254 | 0.3% | 3.1% | 0.16% (0.18%) | 14.5% (12.7%) |
| Arabic | 44.1% [42.1, 46.2] of 2282 | 5.2% | 7.8% | 0.11% (0.17%) | 11.3% (11.1%) |
| Tamil | 37.2% [35.3, 39.2] of 2288 | 0.0% | 0.5% | 0.03% (0.21%) | 5.3% (13.2%) |

On Wikipedia-style text, no unrelated sentence was accepted, in any language.
In MASSIVE's domain, the cross-lingual path accepts unrelated sentences at the
rate the existing same-script rule does for the same claims in English:

- random sentences: 0.03 to 0.16%, against 0.17 to 0.21%;
- hard neighbours: 5.3 to 14.5%, against 11.1 to 13.4%. Urdu is 1.8 points
  above its reference.

The change to `about()` is therefore adopted. The hard-neighbour rate is high
for both rules because a MASSIVE request is three to six words long: "set an
alarm for seven" and "remove the alarm for seven" share most of their
distinctive words.

#### What each condition changed, measured

The table above is for the shipped lexicon with both conditions. In MASSIVE's
domain, with the first lexicon (cut-off on P), the conditions were added one at
a time:

| `about()` | hard neighbours (hi / ur / ar / ta) | English claim |
|---|---|---|
| neither condition | 15.5 / 20.0 / 15.3 / 15.6% | 13.2 / 13.0 / 11.7 / 14.0% |
| translations must carry information | 13.9 / 17.7 / 11.1 / 6.1% | same |
| and one word stands for one | 13.4 / 14.6 / 10.7 / 5.1% | same |

The Wilson cut-off (shipped) holds fewer rare words than the cut-off on P. On
FLORES it accepts fewer claims: Hindi 25 against 34, Urdu 10 against 14, both
with no false accept. On MASSIVE it accepts more: Hindi 60.7% against 58.5%,
Arabic 44.1% against 38.0%. The Wilson cut-off was chosen by the held-out
dictionary's F1, decided before FLORES was read, and is kept.

#### The gate before `about()`: a recommendation

`judge()` and `joint_premise()` read only the source sentences whose BM25
score against the claim's own words is above 0. Across scripts, only a shared
digit or a name in Latin letters gives such a score. The correct English
sentence is reached this way for:

- 19.7% of FLORES Hindi claims;
- 7.8% of MASSIVE Hindi claims.

So the accepts that reach the NLI model today are the "through `judge()`"
column. With the claim's Qāmūs bridge added to the BM25 query
(`claim + " " + " ".join(qamus.bridge(claim, language))`), the correct
sentence scores above 0 for 99.8% of FLORES Hindi claims and 97.5% of MASSIVE
Hindi claims (Urdu 99.7% and 97.9%). That would be a one-line change in
`judge()`. It is not made here and is left to be measured on teacher answers
(`scripts/ahl_coverage.py`).

## Limits

- **The vocabulary is a voice assistant's.** MASSIVE is alarms, music, weather,
  lists and short factual questions. On encyclopedic text, half of a claim's
  distinctive information is in words MASSIVE never holds ("हालाँकि" however,
  "कारण" reason, "राज्य" state). Another third is in a form or synonym the
  sentence does not use: "use" against "used", "multiple" against "many".
  More licence-clean parallel text is the next step, for example Tatoeba
  (CC BY 2.0 FR, already the Lughah source) or Samanantar (CC0, English–Indic).
- **Names are rarely translated.** A name is transliterated ("एहुड उर" for
  "Ehud Ur"), and only names seen in MASSIVE are known. A transliteration
  model learned from the name pairs would cover the rest.
- **Localisation is not always marked.** Some entities were changed outside a
  marked slot, so a few translations are wrong. The Urdu "بھارت" (India) is
  stored as "pakistan", from its one translated sentence, "india pakistan
  match" against "پاک بھارت میچ".
- **The Arabic is Saudi dialect** (MASSIVE `ar-SA`), not the Modern Standard
  Arabic of Wikipedia. This is why it has the lowest precision and coverage.
- **Roman Hindi/Urdu is not covered.** A Hinglish word is in Latin letters, so
  it is matched as it is, as before. MASSIVE has no Roman Hindi locale.
- **Only English pairs.** Hindi against Urdu, or Urdu against Arabic, is not
  translated (same script, or no pair).
- **Arabic-script spelling variants** (ي and ی, ك and ک) and optional harakat
  are not normalised.

## Rebuild and measure

    python -I scripts/build_qamus.py --data /tmp/qamus_data           # writes the four files
    python -I scripts/build_qamus.py --data /tmp/qamus_data --check   # fails if a rebuild differs
    python -I scripts/qamus_eval.py --data /tmp/qamus_eval --massive /tmp/qamus_data

The data folders must be new folders outside the repository; the scripts
refuse a folder inside it. Both scripts need `pyarrow` and `huggingface_hub`.
The build takes about 30 seconds and the measurement about 5 minutes on one
CPU.
