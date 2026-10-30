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

The builder romanises names with **anyascii 0.3.2** (ISC licence; pinned, and
checked before a build). It is needed only to build, and nothing it writes is
shipped.

## Method

### Words

A word is `core.adaptive.tokenize` of the NFC form of the text. Before Qāmūs,
`tokenize` matched `\w+`, which matches no combining mark, so Devanagari and
Tamil vowel signs and viramas, and Arabic harakat, cut words into pieces
("राजधानी" was read as "र", "जध", "न"). A word now keeps the combining marks
written on it (Unicode category M), as Unicode's word boundaries do
(UAX #29). This applies to every caller of `tokenize`.

Qāmūs also drops invisible format characters (Unicode category Cf: direction
marks, joiners) before it reads a text, in training and in lookups. Unicode's
word boundaries ignore them inside a word, but `\w` stops at them. One Urdu
sentence had a left-to-right mark inside "جاۓ", which was read as "جا" and
"ۓ", and "ۓ" was learned as "hubby".

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
india 0.32, japan 0.21 and nigeria 0.08, and after it with india 0.94. (The
name check below later removes that pair, because "भारत" does not sound like
"india".)

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

### Names are written, not translated

Translators did not only localise marked slots. They also put other names in
place of names outside them, and marked some swapped slots as translated:
"नेहा" for "claire", "अहमदाबाद" for "manchester", "پاکستان" for
"switzerland". The first lexicon had learned such pairs: "pakistan" →
"بھارت", "india" → "پاکستان", "mumbai" → "गोवा", "london" → "गाड़ी". With
them, `about()` could read a claim about India against a sentence about
Pakistan, and Ahl al-Dhikr could then show a source as saying otherwise. A pair
involving a name is therefore kept only when one word is written as the other,
by its sounds.

**Which words are names.** Each word is judged by data, with no list:

- A word is a **name** when more than half of its occurrences lie inside a
  slot that a translator did not translate (localised it, or copied it
  unchanged). Each English slot was handled by four translators, one per
  locale, so an English word counts as inside such a slot when any of them did
  not translate it. A word of the other language is judged by its own locale.
  "pakistan" (1 of 1), "london" (22 of 24) and "mumbai" (12 of 12) are names.
  "friday" (22 of 94), "airport" (2 of 12) and "accept" (0 of 1) are not.
- A word is an **entity** when more than half of its occurrences lie inside an
  annotated slot of any kind. "الهند" (India) is one: Arabic translators
  translated it.

**Which pairs are kept.** A pair with a name on either side is kept only when
both words are entities and they sound alike. "गाड़ी" (a car) is no entity, so
it is no translation of "london"; "أجد" ("I find") is none for "japan".

**Sounding alike.** The other script's word is romanised with anyascii
("پاکستان" → "pkstn", "जॉन" → "jon"). Each word is reduced to its consonant
skeleton: the letters a–z, without the vowels a e i o u, each run of one
consonant written once ("john" → "jhn"). The score is

    sounds_alike(x, e) = 1 − edit_distance(skeleton(x), skeleton(e)) / max(|skeleton(x)|, |skeleton(e)|)

A pair sounds alike when its score is at least σ.

**The cut-off σ, by Youden's J.** σ is fitted per language on the validation
split's name slots, using single-word values of the **name types** that are
marked as translated. A name type is a slot type the translators did not
translate in more than half of its slots, over the four locales: person
(0.90 not translated), place_name (0.75), business_name, artist_name,
currency_name, app_name, food_type, music_genre, and the song, movie, game,
podcast and playlist names. Each language has 50 to 86 such pairs. The
negatives are the same names shuffled within their slot type.

F1 cannot be used here. Many "translated" name slots in truth hold another
name, as the examples above show, and real translations sit in name types too
("आलू" for "potato"). With those positives, F1 is highest when everything is
kept: σ = 0 for Hindi, Arabic and Tamil.

Youden's J = TPR − FPR does not have that problem. If a share 1 − π of the
positives are unrelated pairs, distributed like the negatives, then
TPR = π·T + (1 − π)·FPR and J = π·(T − FPR). The σ that maximises J does not
move with π.

With 50 to 86 pairs, J is flat near its best: for Arabic, J lies between 0.23
and 0.33 for any σ from 0.1 to 0.5. So σ is the highest value whose J is
within one standard error of the best J (the one-standard-error rule). That is
the strictest cut-off the data cannot tell from the best, chosen because
keeping an unrelated name costs more than losing a name.

Two alternatives were measured and not adopted:

- **Soundex consonant classes** tied with plain skeletons on mean validation J
  (0.363 each), but the cut-off varied more between languages. Plain
  skeletons were kept as the simpler choice.
- **Sharing P again after filtering** (renormalising) promoted what was left of
  a name's candidates: "بھارت" → about, "پاکستان" → post. P is therefore not
  renormalised.

### Pieces of a word written apart

The Urdu text of MASSIVE writes "Pakistan" as "پا کستا ن" in places, so "ن"
and "کستا" had been learned as translations of "japan". Other words are cut by
punctuation: "what's", "e-mail", "a.m.". A token is a **piece** when the corpus
holds the whole word it is most often part of more often than it holds the
token standing alone. A run of adjacent tokens counts as part of a whole word
when, written together, it is a token the corpus holds. "کستا" never stands
alone. "कौन" (who) stands alone more often than "कौनसा" is written closed, so
it is not a piece. Pieces are dropped as keys and as translations (31 to 157
per direction).

Combining marks no longer cut any word. The one-letter words that remain are
written as one letter in the source:

- abbreviation letters ("ب. م. ث." for BMW, Tamil "ப.");
- colloquial clitics written apart (Arabic "ع" for على, Tamil "ல");
- real one-letter words (Hindi "न", Urdu and Arabic "و", "آ");
- English letters from "I'm" and "a.m.".

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
`[date : शुक्रवार]`. Slots of the name types are left out, because a name
slot marked as translated often holds another name. Names are measured by the
name filter's own test (above). The validation split's dictionary chooses τ,
after names and pieces are filtered. The test split's dictionary measures
precision@1.

The Wilson score was adopted over the plain P because validation F1 was
higher in all eight directions. This was measured before names were checked:

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
- how many entries the name and piece checks removed;
- the name types, σ and the name filter's test;
- the test measurements.

The four files take 313 KB in all. `python -I scripts/build_qamus.py --data
<folder> --check` rebuilds them and compares the SHA-256 of their content.

## Using it

- `qamus.translations(word, source_lang, target_lang)` gives
  `[(translation, P), …]`.
- `qamus.translate(word, target_lang)` gives a word's translations from every
  language written in the word's script. An Arabic-script word may be Arabic
  or Urdu. A pair counts when either direction's lexicon holds it: "दिल्ली" is
  read as "delhi" because the English lexicon gives "delhi" → "दिल्ली", though
  the Hindi one, cut where its own dictionary put it, does not. Both
  directions come from one score and passed the same checks. A number written
  in another script's digits ("१९४७") is given in ASCII digits.
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
the lexicon holds. The dictionary is of the slot types translators translate
(names left out). The "before" column is the first lexicon, before names and
pieces were checked, on the same dictionary.

| Direction | precision@1 [95% Wilson] | right / held | coverage | before: precision@1, coverage |
|---|---|---|---|---|
| hi→en | 0.812 [0.743, 0.866] | 125 / 154 | 0.62 of 248 | 0.839, 0.73 |
| en→hi | 0.700 [0.625, 0.766] | 112 / 160 | 0.71 of 226 | 0.710, 0.81 |
| ur→en | 0.775 [0.708, 0.830] | 138 / 178 | 0.71 of 252 | 0.805, 0.77 |
| en→ur | 0.735 [0.664, 0.796] | 125 / 170 | 0.73 of 233 | 0.726, 0.85 |
| ar→en | 0.644 [0.579, 0.704] | 143 / 222 | 0.69 of 324 | 0.664, 0.78 |
| en→ar | 0.562 [0.485, 0.637] | 90 / 160 | 0.72 of 221 | 0.569, 0.85 |
| ta→en | 0.769 [0.706, 0.822] | 153 / 199 | 0.56 of 357 | 0.761, 0.67 |
| en→ta | 0.571 [0.497, 0.641] | 101 / 177 | 0.70 of 254 | 0.566, 0.83 |

Checking names leaves precision on ordinary words within 0.03 of the first
lexicon. It costs 0.06 to 0.14 of coverage.

### The name filter

These are the test split's translated name slots, against the same names
shuffled. Recall is measured against "translated" pairs, which include swaps
and translations, so the true recall is higher.

| Language | σ | validation J | passes shuffled names | precision | recall |
|---|---|---|---|---|---|
| Hindi | 0.667 | 0.280 | 2 / 45 (4.4%) | 0.875 | 0.246 |
| Urdu | 0.500 | 0.396 | 1 / 59 (1.7%) | 0.971 | 0.485 |
| Arabic | 0.333 | 0.262 | 5 / 63 (7.9%) | 0.865 | 0.444 |
| Tamil | 0.500 | 0.276 | 4 / 88 (4.5%) | 0.897 | 0.324 |

Entries the first lexicon held that involve a name, and how many of them are
removed now. The total is the direction's entries in the first lexicon:

| Direction | entries with a name | removed | of entries |
|---|---|---|---|
| hi→en | 657 | 498 | 3014 |
| en→hi | 777 | 604 | 3317 |
| ur→en | 720 | 499 | 3513 |
| en→ur | 964 | 720 | 4743 |
| ar→en | 1190 | 1006 | 6846 |
| en→ar | 991 | 801 | 4709 |
| ta→en | 1241 | 941 | 6230 |
| en→ta | 790 | 559 | 3475 |

Removed entries include swaps (abdul → مشرف, columbia → لاہور, paul →
प्रकाश, steffi → فهد, "صقر" → rahman). They also include real translations of
words translators sometimes swapped (english → अंग्रेज़ी, south → جنوب), and
transliterations that score below σ (chicken → चिकन, "ஃபெராரி" → ferrari).
All 20 swaps found in the first lexicon ("pakistan" → "بھارت", "mumbai" →
"गोवा", "york" → "سيناء", …) are gone (`tests/test_qamus.py`). The new
lexicons keep 181 to 288 pairs with a name per direction.

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

FLORES-101 (Wikipedia-style). In brackets, the first lexicon, before names
were checked:

| Claims in | accepted with Qāmūs | without | through `judge()` | false, random | false, hard | English claim, hard |
|---|---|---|---|---|---|---|
| Hindi | 29 / 1012 (2.9% [2.0, 4.1]) (25) | 1 | 18 (16) | 0 / 20240 | 0 / 3036 | 1 / 3036 |
| Urdu | 13 / 1012 (1.3% [0.7, 2.2]) (10) | 0 | 8 (7) | 0 / 20240 | 0 / 3036 | 0 / 3036 |
| Arabic | 2 / 1012 (0.2%) (2) | 0 | 1 (1) | 0 / 20240 | 0 / 3007 | 0 / 3007 |
| Tamil | 3 / 1012 (0.3%) (4) | 0 | 3 (4) | 0 / 20240 | 0 / 2991 | 1 / 2991 |

MASSIVE test split (in the lexicon's domain). In brackets, the first lexicon:

| Claims in | accepted with Qāmūs | without | through `judge()` | false, random (English claim) | false, hard (English claim) |
|---|---|---|---|---|---|
| Hindi | 64.2% [62.3, 66.2] of 2249 (60.7%) | 1.1% | 6.0% | 0.19% (0.19%) | 13.2% (11.5%) |
| Urdu | 62.7% [60.7, 64.7] of 2254 (62.3%) | 0.3% | 3.2% | 0.18% (0.18%) | 12.5% (10.9%) |
| Arabic | 41.9% [39.9, 43.9] of 2282 (44.1%) | 5.2% | 7.8% | 0.11% (0.17%) | 10.5% (10.0%) |
| Tamil | 34.6% [32.7, 36.5] of 2288 (37.2%) | 0.0% | 0.6% | 0.03% (0.21%) | 5.2% (12.2%) |

The hard neighbours are chosen by the claim's bridge, so they change with the
lexicon, and the English reference changes with them.

On Wikipedia-style text, no unrelated sentence was accepted, in any language.
In MASSIVE's domain, the cross-lingual path accepts unrelated sentences at
about the rate the existing same-script rule does for the same claims in
English:

- random sentences: 0.03 to 0.19%, against 0.17 to 0.21%;
- hard neighbours: 5.2 to 13.2%, against 10.0 to 12.2%. Hindi is 1.7 points
  above its reference and Urdu 1.6.

The change to `about()` is therefore adopted. The hard-neighbour rate is high
for both rules because a MASSIVE request is three to six words long: "set an
alarm for seven" and "remove the alarm for seven" share most of their
distinctive words.

Checking names lowered acceptance only in Arabic and Tamil (by 2.2 and 2.6
points on MASSIVE). Reading a pair from either direction's lexicon raised it
in Hindi and Urdu, and raised FLORES Hindi from 25 to 29 claims.

#### What each condition in `about()` changed, measured

The two conditions in `about()` were measured on the first lexicon (cut-off on
P), in MASSIVE's domain, added one at a time:

| `about()` | hard neighbours (hi / ur / ar / ta) | English claim |
|---|---|---|
| neither condition | 15.5 / 20.0 / 15.3 / 15.6% | 13.2 / 13.0 / 11.7 / 14.0% |
| translations must carry information | 13.9 / 17.7 / 11.1 / 6.1% | same |
| and one word stands for one | 13.4 / 14.6 / 10.7 / 5.1% | same |

The Wilson cut-off was also measured against the cut-off on P, before names
were checked. It holds fewer rare words. On FLORES it accepted fewer claims:
Hindi 25 against 34, Urdu 10 against 14, both with no false accept. On MASSIVE
it accepted more: Hindi 60.7% against 58.5%, Arabic 44.1% against 38.0%. The
Wilson cut-off was chosen by the held-out dictionary's F1, decided before
FLORES was read, and is kept.

#### The gate before `about()`: searched by the claim's translations too

`judge()` and `joint_premise()` read only the source sentences whose BM25
score against the claim is above 0. Across scripts, only a shared digit or a
name in Latin letters gives such a score from the claim's own words. The
correct English sentence was reached this way for:

- 19.7% of FLORES Hindi claims;
- 7.8% of MASSIVE Hindi claims.

With the claim's Qāmūs bridge added to the BM25 query (`ahl_dhikr.searched`:
`claim + " " + " ".join(qamus.bridge(claim, "en"))`), the correct sentence
scores above 0 for 100% of FLORES Hindi claims and 98.2% of MASSIVE Hindi
claims (Urdu 100% and 98.4%). Whether a found sentence is about the claim is
still `about()`'s decision, on the claim itself.

**Measured on teacher answers before adopting it** (30 Oct 2026). The production
teacher answered the 30 questions of `scripts/ahl_coverage.py`'s set once in
Hindi (Devanagari) and once in Urdu, and each claim was judged by the real NLI
model against the question's Simple English Wikipedia articles. As a control,
each answer was also judged against another question's articles.

| Claims | Qāmūs off | Qāmūs in `about()` | and in the search | Control: another question's articles |
|---|---|---|---|---|
| Hindi, 119 | 0 supported | 2 | 5 [1.8%, 9.5%] | 0 supported, 0 contradicted in every arm |
| Urdu, 120 | 0 | 1 | 2 [0.5%, 5.9%] | 0 supported, 0 contradicted in every arm |

All seven supported claims were checked by hand and are right ("भारत की राजधानी
नई दिल्ली है।", "बर्लिन की दीवार 9 नवंबर 1989 को गिरी थी।", "یہ کمپنی 1975 میں قائم
ہوئی۔", …). No claim was contradicted. The gain is small because of the
lexicon's coverage (below), not the search, so the search is adopted.

The same measurement found that Isnad split sentences only at `. ! ? ۔ ؟`:
each Hindi answer was one claim (30 claims, none checkable). Isnad now also
splits at `।` and `॥`, which gave the 119.

## Roman Hindi and Urdu

### The gap

Most of MIZAN's users write Hindi and Urdu in Latin letters, and the teacher
answers them so. On 30 October 2026 production asked "Taj Mahal kisne banwaya
tha aur kab?" and the teacher answered "Taj Mahal ko Mughal badshah Shah Jahan
ne banwaya tha — apni begum Mumtaz Mahal ki yaad mein…". Ahl al-Dhikr asked
its three sources, and none of 8 claims was supported. Roman words such as
"banwaya", "badshah", "begum" and "yaad" carry most of each claim's
distinctive information, and no English sentence holds them. Qāmūs read only
Devanagari, Urdu, Arabic and Tamil script.

Two things were missing, and both were measured:

1. **The gate.** `about()` found no English sentence about a Roman claim
   unless the names in Latin letters alone carried more than half of its
   information.
2. **The reading.** When the gate was opened, the NLI model misread Roman
   claims. It called true claims contradicted by sentences that do not
   contradict them: "Mona Lisa ki painting Leonardo da Vinci ne banayi thi"
   against Leonardo's full name, "Zuhal ka sab se bara chand Titan hai"
   against "Titan is Saturn's moon". The model learned Hindi from XNLI, in
   Devanagari.

### Data and licences

Read and checked one by one; only the first two are used to build.

| Source | Licence | Used |
|---|---|---|
| [Aksharantar](https://huggingface.co/datasets/ai4bharat/Aksharantar) (AI4Bharat), Hindi 1.30M and Urdu 0.70M train pairs of a native word and its spelling in Latin letters, at commit `e418c1fc` | Manually collected pairs CC BY 4.0; pairs mined from Samanantar and IndicCorp, and existing sources, CC0 | How letters are written in Latin letters. Its rows that came from Dakshina (24,727 Hindi, 73,666 Urdu) are left out: Dakshina is CC BY-SA 4.0 |
| MASSIVE 1.1 (above) | CC BY 4.0 | Which Hindi and Urdu words there are, and how common (the prior); which words are English |
| [Dakshina](https://github.com/google-research-datasets/dakshina) v1.0 (Google), Hindi and Urdu Wikipedia sentences romanized by native speakers, word-aligned | CC BY-SA 4.0 | Measurement only: nothing is learned from it or shipped |
| [PHINC](https://huggingface.co/datasets/LingoIITGN/PHINC) (IIT Gandhinagar), 13,738 Hinglish tweets with human English translations | CC BY 4.0 | Measured as a direct Roman→English lexicon, not adopted (below) |
| `findnitai/english-to-hinglish` | Card says Apache-2.0 | Rejected: it re-licenses share-alike sources (Hinglish-TOP, CMU Hinglish DoG) and holds synthetic rows of unstated origin |
| LinCE | Each part under its own terms | Rejected: an aggregate with no single clear licence |
| CMU Hinglish DoG | CC BY-SA 3.0 / GFDL | Not needed: PHINC covers the same use under CC BY |
| Lughah's `hi-latn.tsv` (Hinglish-Everyday-Conversations-1M, MIT) | MIT, synthetic | Not used: it has no other side to learn a reading from |

### Method

**A noisy channel.** A native word d is a sequence of units: each letter with
the combining marks written on it ("बनवाया" = ब, न, वा, या). Each unit, in its
context, writes 0 to 4 Roman letters, in order:

    P(r | d) = Σ over alignments Π_i t(chunk_i | unit_i, context_i)

The context is what follows the unit. In Devanagari it is the word's end, a
bare letter or a letter with marks: a consonant's own vowel is not spoken at
the end of a word ("kamal") and often not before a bare consonant. In Urdu,
whose short vowels are not written, it is the next letter itself. A context
never seen in training falls back to the unit's chunks over all its contexts.

t is learned by EM with the forward-backward algorithm. With α[i][j] the
probability that the first i units write the first j letters, and β the same
from the end:

    E step:  c(r[j-l:j] | u_i) += α[i-1][j-l] · t(r[j-l:j] | u_i) · β[i][j] / P(r | d)
    M step:  t(chunk | u) = c(chunk | u) / Σ c(· | u)

The first E step counts every alignment once. Chunks with less than 10⁻⁴ of a
unit's mass are dropped. 100,000 training pairs per language are drawn with a
fixed seed. EM stops when the log-likelihood of Aksharantar's validation pairs
(without Dakshina's rows) no longer rises.

**Reading a spelling.** The vocabulary is the native words of MASSIVE's train
split (5,747 Hindi, 5,496 Urdu) with their counts n_d. Each word's 30 most
probable spellings are taken from a beam search over the channel. Each
spelling r is read as the word that most probably wrote it, by Bayes' rule:

    P(d | r) = P(r | d) · P(d) / Σ_d' P(r | d') · P(d'),    P(d) = (n_d + 1) / (N + |V|)

A reading is kept only when it is decisive, P(d | r) > ½, as Fahm takes a
reading only when it is decisive. On Dakshina's dev sentences the cut-off
that maximised F1 was 0.44 for Hindi and 0.50 for Urdu, close to ½. It was
measured, not fitted: no number is taken from Dakshina.

A spelling is never read when it is an English word: a word of MASSIVE's
English utterances outside their slots, or of Lughah's English corpus ("main",
"the", "door", "bus"). Slot values are left out because they hold names and
Indian words in Latin letters ("rajdhani express", "biryani"). For Urdu only
the words the lexicon translates are kept. For Hindi every word is kept,
because a Roman claim is read by the NLI model in Devanagari (below).

**What is stored.** `backend/tadbir/data/qamus/hi-latn.json.gz` holds each
spelling with the Devanagari and Urdu words it is read as, how EM ran, and the
held-out measurements. `scripts/build_qamus_roman.py --check` rebuilds it and
compares the SHA-256 of its content.

### Using it

- `qamus.read_roman("duniya")` gives `{"hi": "दुनिया", "ur": "دنیا"}`.
- `qamus.translate(word, target)`: a Latin-letter word that is read gives the
  native word for its own language and the native word's translations for any
  other: "duniya" → world, "biwi" → wife. An English word gives none, as
  before. So `bridge()`, `found_in()`, `about()` and `ahl_dhikr.searched()`
  read Roman claims with no change to their rules.
- `qamus.devanagari(claim, keep=premise)` writes a Roman claim's words in
  Devanagari, except the premise's own words, which stay as they are. A
  premise's word is a name or a symbol the source writes so: "Au" would
  otherwise be read as "और" (and).
- `ahl_dhikr.judge` gives the NLI model a claim that Lughah's own model reads
  as Hinglish (`ahl_dhikr.roman`) in that form, in both directions of the
  contradiction check. The claim, its finding and everything shown keep the
  words the teacher wrote. An English claim, and a code-mixed claim that
  Lughah reads as English, are read as written.
- `MIZAN_QAMUS=off` turns all of it off.

### Measured (30 October 2026)

ROMAN_MEASURED

### Not adopted

ROMAN_NOT_ADOPTED

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
- **A name that is not a transliteration is lost.** "भारत" and "بھارت" (India),
  "مصر" (Egypt) do not sound like their English names, so they are not
  translated. The same goes for a name whose real translation shared its
  probability with the names put in its place ("پاکستان" → pakistan,
  "لندن" → london in Urdu).
- **A few swaps pass by chance.** Short consonant skeletons can match by
  chance. On the test split, the name filter lets 4.4% of shuffled Hindi
  name pairs through, 1.7% for Urdu, 7.9% for Arabic and 4.5% for Tamil. Kept
  pairs include Arabic "احمد" → mike and "هند" → anna, and Urdu "رمضان" →
  rowan.
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
refuse a folder inside it. Both scripts need `pyarrow` and `huggingface_hub`,
and the builder needs `anyascii==0.3.2`. The build takes about 40 seconds and
the measurement about 5 minutes on one CPU.
