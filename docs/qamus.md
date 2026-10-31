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
reading only when it is decisive. With a prototype of the channel (fewer
iterations), the cut-off that maximised F1 on Dakshina's dev sentences was
0.44 for Hindi and 0.50 for Urdu, close to ½. That was a check, not a fit: no
number is taken from Dakshina.

A spelling is never read when it is an English word: a word of MASSIVE's
English utterances outside their slots, or of Lughah's English corpus ("main",
"the", "door", "bus"). Slot values are left out because they hold names and
Indian words in Latin letters ("rajdhani express", "biryani"). An English
spelling is still read when the lexicon gives that very spelling as a
translation of the word: English writes "rajdhani" for राजधानी. For Urdu only
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
  as Hinglish (`ahl_dhikr.roman`) in that form. The claim, its finding and
  everything shown keep the words the teacher wrote. An English claim, and a
  code-mixed claim that Lughah reads as English, are read as written.
- A contradiction already had to hold both ways (premise against claim, and
  claim against premise). A Roman claim must also be contradicted however it
  is written: in Devanagari and as the teacher wrote it, both ways, four
  readings in all. A contradiction is shown under the answer as "the source
  says otherwise", so it must not depend on the script the model was given.
- `MIZAN_QAMUS=off` turns all of it off.

### Measured (30 October 2026)

**The channel, on Aksharantar's test split** (recorded in the file; Dakshina's
rows are part of this split and are only read). The share of test pairs whose
spelling is among the native word's k most probable spellings, and, for the
pairs whose word is in the vocabulary, how often the most probable reading of
the spelling (before the P > ½ cut and the English filter) is that word:

| | EM iterations | spelling in top 1 / 5 / 10 / 30 | read as its word | readings shipped |
|---|---|---|---|---|
| Hindi | 23 (held-out likelihood stopped rising) | 0.278 / 0.575 / 0.673 / 0.779 of 10,112 | 596 / 718 = 0.830 | 149,200 |
| Urdu | 30 (the bound; still rising slowly) | 0.071 / 0.214 / 0.299 / 0.420 of 14,878 | 743 / 1,633 = 0.455 | 87,647 |

**Running text: Dakshina's romanized Wikipedia sentences**
(`scripts/qamus_roman_eval.py`, test split; the dev split is within 0.01).
A token is read right when it is read as the word the sentence wrote. Recall
counts the tokens whose word the reading can give at all. Content tokens carry
more information than an average running word:

| | tokens | precision [95% Wilson] | same English | recall |
|---|---|---|---|---|
| Hindi, all | 87,367 | 0.872 [0.869, 0.874] | 0.874 | 0.773 |
| Hindi, content | 59,492 | 0.830 [0.825, 0.833] | 0.832 | 0.853 |
| Urdu, all | 85,027 | 0.835 [0.832, 0.839] | 0.865 | 0.615 |
| Urdu, content | 55,855 | 0.796 [0.790, 0.801] | 0.797 | 0.687 |

Most wrong readings are spelling variants of one word (की and कि, है and हैं,
लिए and लिये) or two words written alike ("ki"). Some are not: "mahal" is read
in Urdu as ماحول (environment) instead of محل (palace).

**Teacher answers.** The production teacher (`deepseek/deepseek-v4.1-flash-1017`
via OpenRouter) was asked the 30 questions of `scripts/ahl_coverage.py`'s set
twice: in Hindi-leaning Hinglish ("Taj Mahal kisne banwaya tha aur kab?") and
in Roman Urdu ("Taj Mahal kis ne tameer karwaya tha?"), with "answer in one
paragraph of a few sentences, in the language of the question". 27 of the 60
answers came back in Latin letters; the other 33 (in Devanagari or Urdu
script) were asked again with production's own reply instruction for Hinglish
("Hindi/Urdu in Latin letters, as the user writes"), and all came back in Latin
letters. The answers gave 158 claims (78 and 80). Each claim was judged by
`judge()` with the real NLI model against the question's Simple English
Wikipedia articles, and, as a control, against another question's articles.
The 20 false claims of the English false set were also written in Hinglish by
hand. The arms add one change at a time:

- **main**: Qāmūs as before (Roman words matched only as they are);
- **gate**: the Roman reading in `translate`, so in `about()` and the search;
  the NLI model reads the claim as written;
- **Devanagari**: and the NLI model reads a Roman claim in Devanagari;
- **adopted**: and a contradiction must hold however the claim is written.

| Roman claims | supported, Hindi-leaning (78) | supported, Urdu-leaning (80) | supported, all 158 [95% Wilson] | contradicted (all true claims) | control: supported, contradicted |
|---|---|---|---|---|---|
| Qāmūs off | 6 | 1 | 7 [2.2, 8.9%] | 1 | 0, 0 |
| main | 6 | 1 | 7 [2.2, 8.9%] | 1 | 0, 0 |
| gate | 8 | 7 | 15 [5.8, 15.1%] | 5 | 0, 0 |
| Devanagari | 18 | 10 | 28 [12.6, 24.4%] | 1 | 0, 0 |
| **adopted** | **18** [15.1, 33.6%] | **10** [6.9, 21.5%] | **28** [12.6, 24.4%] | **0** [0, 2.4%] | 0, 0 |

| 20 false Roman claims | supported | contradicted | control: supported, contradicted |
|---|---|---|---|
| main | 0 | 6 [14.5, 51.9%] | 0, 0 |
| gate | 0 | 4 | 0, 0 |
| Devanagari | 0 | 5 | 0, 0 |
| **adopted** | **0** [0, 16.1%] | **5** [11.2, 46.9%] | 0, 0 |

No other set changed:

| Set | main | adopted |
|---|---|---|
| Hindi (Devanagari) answers, 119 claims | 5 supported, 0 contradicted | 5, 0 |
| Urdu answers, 120 claims | 2, 0 | 2, 0 |
| Their control (another question's articles) | 0, 0 | 0, 0 |
| English set of `scripts/ahl_coverage.py`, 75 claims (5 of its questions in Hinglish) | 19 supported, 0 contradicted | 20, 0: the same 19, and the Roman claim "…duniya ka sabse bada desh Russia hai" (right) |
| English false claims, 20 | 0 supported, 10 contradicted | 0, 10 |

**Hand audit of every finding** (right: the sentence says it; part: it says
part of it; wrong):

| Claim (adopted arm) | Source sentence, shortened | Audit |
|---|---|---|
| Saturn ka sabse bada chand Titan hai. | The largest moon is Titan. | right |
| Berlin ki deewar 9 November 1989 ko giri thi. | The Berlin Wall was taken down on November 9, 1989. | right |
| Australia ki rajdhani Canberra hai. | Canberra is the capital city of Australia. | right |
| Ye New South Wales mein located hai. (Canberra) | …an area… was given to the country by New South Wales to build Canberra in. | wrong: Canberra is in the ACT; also supported on main |
| Pride and Prejudice Jane Austen ne likhi thi, aur yeh novel 1813 mein publish hui thi. | Pride and Prejudice is a book by Jane Austen. It was published in 1813. | right |
| Mona Lisa ki painting Leonardo da Vinci ne banayi thi. | Leonardo's full name was "Leonardo di ser Piero da Vinci"… | wrong: true claim, the sentence does not say it |
| Yeh ek famous portrait hai jo 16th century ke shuru mein banaya gaya tha aur ab Paris ke Louvre Museum mein rakha hai. | …is a 16th-century portrait. It is on permanent display in Paris at the Louvre museum. | right |
| Penicillin ki khoj Alexander Fleming ne ki thi. | Penicillin was discovered by… Sir Alexander Fleming in 1928… | right |
| Iske liye unhe 1945 mein Nobel Prize bhi mila (Howard Florey aur Ernst Chain ke saath). | He shared Nobel Prize… in 1945… with Howard Walter Florey and Ernst Boris Chain. | right |
| Sone (gold) ka chemical symbol Au hai. | Its chemical symbol is Au. | right |
| Yeh symbol Latin shabd "Aurum" se liya gaya hai, jiska matlab sona hota hai. | Its symbol is Au, from the Latin word for gold, aurum. | right |
| Telephone ka avishkar mukhy roop se Alexander Graham Bell se joda jata hai, jinhone 1876 mein iska patent liya. | Alexander Graham Bell was the first person to patent the telephone, in 1876. | right |
| Photosynthesis wo process hai jisme plants, algae aur kuch bacteria… glucose… oxygen… | Photosynthesis is how plants… make carbohydrates… carbon dioxide + water + light energy → glucose + oxygen | right |
| Isaac Newton ek English physicist, mathematician aur astronomer the, jinka janm 1643 mein hua tha. | Sir Isaac Newton (25 December 1643 –…) was an English physicist, mathematician and astronomer. | right |
| Microsoft ki sthapna Bill Gates aur Paul Allen ne ki thi. | Gates started Microsoft in 1975 with Paul Allen… | right |
| Iska nirmaan 1887 se 1889 ke beech Paris mein hua tha aur ise 1889 ki Exposition Universelle ke liye banaya gaya tha. | It was built between 1887 and 1889 for the Exposition Universelle… | right |
| Bharat ki rajdhani New Delhi hai. | New Delhi is the capital of India. | right |
| Agar "bada" ka matlab kshetrafal (area) hai, to duniya ka sabse bada desh Russia hai. | Russia is the largest country in the world. | right |
| Ye Saturn ke chaandron mein sab se bada hai aur poore solar system ka doosra sab se bada moon hai (Ganymede ke baad). | Titan is the largest moon of Saturn and the second largest in the Solar System… after Ganymede | right |
| Ye New South Wales aur Australian Capital Territory mein waqe hai aur ise 1913 mein capital ke taur par banaya gaya tha. | …it is in the Australian Capital Territory (ACT). Canberra was started in 1913… | part: not in New South Wales |
| Mona Lisa ki tasveer Leonardo da Vinci ne banai thi. | …Leonardo's most famous oil painting, the Mona Lisa. | right |
| Woh ek Italian artist, engineer aur inventor the, aur yeh painting 16th century ke shuru mein bani thi. | He was also a scientist, mathematician, engineer, inventor… | part: the date is not in it |
| Ye 20 July 1969 ko Apollo 11 mission ke dauran hua. | On July 20, 1969, Armstrong and Aldrin became the first humans to land on the moon… | right |
| Sonay (gold) ka kimiyai alamat Au hai, jo Latin ke aurum se aaya hai. | Its symbol is Au, from the Latin word for gold, aurum. | right |
| Iska atomic number 79 hota hai aur ye ek transition metal hai. | Its atomic number is 79… a transition metal in Group 11. | right |
| Photosynthesis woh process hai jisme paudhe (aur kuch algae/bacteria)… | (as above) | right |
| Isaac Newton ek mashhoor English physicist, mathematician aur astronomer thay (1643–1727). | (as above) | right |
| Doosri Jang-e-Azeem (World War II) Europe mein 8 May 1945 ko khatam hui, jab Germany ne surrender kiya. | Germany surrendered on May 8, 1945… | right (main read it as contradicted) |
| *False:* Canberra New Zealand ki rajdhani hai. | Canberra is the capital city of Australia. | right (contradicted) |
| *False:* Mona Lisa 21 August 1950 ko chori hui thi. | On August 21, 1911, the Mona Lisa was stolen. | right (contradicted) |
| *False:* Alexander Graham Bell ko telephone ka pehla patent 1901 mein mila tha. | …the first person to patent the telephone, in 1876. | right (contradicted) |
| *False:* Japan ka formal surrender 2 September 1939 ko USS Arizona par sign hua tha. | Japan formally surrendered on September 2, 1945… on board the USS Missouri | right (contradicted) |
| *False:* Microsoft ki sthapna Steve Jobs aur Paul Allen ne 1985 mein ki thi. | Gates started Microsoft in 1975 with Paul Allen… | right (contradicted) |

So 28 true claims are supported where main supported 7: 24 right, 2 part, 2
wrong (one of them, New South Wales, main supported too). Main's 8 findings
had 2 wrong: the same New South Wales claim, and the Second World War claim
read as contradicted. No claim was read against another question's articles.
Of the false claims, main contradicted 6 and the adopted reading 5: it no
longer contradicts "Germany ne May 1944 mein surrender kiya aur Japan ne
August 1946 mein…" (right on main) or "Pacific Ocean duniya ka sabse chhota
mahasagar hai" (main's sentence only said plate tectonics make the Pacific
smaller), and newly contradicts "Canberra New Zealand ki rajdhani hai". The
search by translations moved the page's best sentences away from the joined
premise main found. One true claim main supported is no longer supported:
"Africa ki sabse lambi nadi Nile hai, jo lagbhag 6,650 km lambi hai…".

The production claim of the gap is still not read against "It was built in
the 17th century by Emperor Shah Jahan in memory of his wife, Mumtaz Mahal.":
of its 8 distinctive words, the sentence holds 3 (shah, mumtaz, mahal), and
"badshah", "begum" and "banwaya" have no translation (Limits). The teacher's
other wordings of the same fact are read: "Taj Mahal Shah Jahan ne apni biwi
Mumtaz Mahal ki yaad mein banwaya tha" is about it through "biwi" → wife
(`tests/test_qamus.py`). Neither Taj Mahal claim of the 60 answers was
supported: the Simple English page's sentences on its builder were read as
neutral.

#### With each claim read with its subject

The numbers above were measured on main, before `judge()` read each claim
with the subject it speaks of (`contexts`, [Ahl al-Dhikr](ahl-dhikr.md)).
With both in the code, the same sets were measured again: the claims of each
answer get the contexts `consult` gives them, and the arm before is the same
code with the Roman reading off (the code as it was without this change):

| Set | Roman reading off | Roman reading on |
|---|---|---|
| Roman true claims, Hindi-leaning (78), supported | 6 | 17 [14.1, 32.2%] |
| Roman true claims, Urdu-leaning (80), supported | 2 | 9 [6.0, 20.0%] |
| All 158: supported [95% Wilson] | 8 [2.6, 9.7%] | **26** [11.5, 23.0%] |
| True claims contradicted | 0 | 0 [0, 2.4%] |
| 20 false Roman claims: supported, contradicted | 0, 2 | 0, 3 |
| Control (another question's articles) | 0, 0 | 0, 0 |
| Hindi (Devanagari) answers, 119 claims | 4, 0 | 4, 0 |
| Urdu answers, 120 claims | 0, 0 | 0, 0 |
| English set, 75 claims | 17, 0 | 18, 0: the Roman claim "…duniya ka sabse bada desh Russia hai" (right) |
| English false claims, 20 | 0, 8 | 0, 8 |

Hand audit: of the 26, 22 are right, 2 part, 2 wrong (the New South Wales
claim and "Mona Lisa ki painting Leonardo da Vinci ne banayi thi" against
Leonardo's full name, both as above). Of the 8 with the Roman reading off, 7
are right and 1 wrong (New South Wales). The 3 false claims contradicted are
right (Canberra in New Zealand, Mona Lisa stolen in 1950, the telephone patent
in 1901).

Against the measurement on main (28: 24 right, 2 part, 2 wrong), reading
each claim with its subject lost two right findings and one part:
- "Iska nirmaan 1887 se 1889 ke beech Paris mein hua tha…" (the Eiffel
  Tower): "It was built between 1887 and 1889 for the Exposition
  Universelle" names none of the subject's words, so it is not about it.
- "Yeh ek famous portrait hai jo 16th century ke shuru mein banaya gaya tha
  aur ab Paris ke Louvre Museum mein rakha hai." was supported on main by the
  joined premise; searched with its subject, the page's best sentences are
  others.
- "Woh ek Italian artist, engineer aur inventor the…" (part).

It gained one part: "Unhe 1921 ka Nobel Prize photoelectric effect par mila,
aur E=mc² wala formula unki pehchan hai." against "He received the Nobel
Prize in Physics in 1921 for theoretical physics. In 1922, he received the
Nobel prize for Physics for his explanation of the photoelectric effect…"
(the formula is not in it). The false claims main contradicted by a joined
premise (Japan's surrender in 1939, Microsoft in 1985 by Steve Jobs) are no
longer contradicted: a joined premise never contradicts.

A Roman claim's subject can hold Roman function words ("thi", "banayi",
"ismein"): their information is counted over corpora where Roman Hindi is
rare, so they look distinctive. They widen the search. They cannot let an
unrelated sentence through the subject check: a sentence passes it by naming
a subject word as written, or through a translation carrying more than
average information, never through "was" or "in". Measured, not changed:
these sets chose the design, and a further change would be fitted to them
too.

### Not adopted

- **A direct Roman→English lexicon from PHINC.** IBM Model 1 in both
  directions on PHINC's 13,738 tweet pairs (EM stopped after 3 iterations by
  held-out likelihood) learned frequent words well: duniya → world (0.99),
  biwi → wife (0.97), saal → years, likha → written. Encyclopedic words never
  occur in it (tameer, mashhoor, rajdhani, haddiyan). In a prototype run with
  the claims read as written, it added one supported claim to what reading
  through Devanagari and Urdu gave (Hindi 8 → 9, by "bharat" → india) and
  none for Urdu. PHINC has no annotation a cut-off could be fitted on, so a
  second source and a second method were not taken for one claim.
- **Opening the gate alone.** With the claims read by the NLI model as
  written, 5 true claims were read as contradicted (the gate arm above).
- **Reading in Devanagari without the agreement of writings.** One true claim
  was read as contradicted (the Devanagari arm): "Taj Mahal ko Mughal badshah
  Shah Jahan ne apni biwi Mumtaz Mahal ki yaad mein tameer karwaya tha"
  against "The Taj Mahal was built for Shah Jahan's third wife, Mumtaz Mahal",
  which the claim as written is not.
- **Searching by the translations of distinctive words only**, the ones
  `about()` counts, instead of every word's ("ne" → has, "mein" → in). It
  found fewer true Roman claims supported (24 of 158 against 28), more false
  Roman claims contradicted (7 against 5, both new ones right) and more
  Devanagari and Urdu claims supported (5 → 8 of 119 and 2 → 3 of 120, all
  right). But on the English set of `scripts/ahl_coverage.py` it read a true
  Hindi claim, "उनका जन्म 2 अक्टूबर 1869 को पोरबंदर, गुजरात में हुआ था और उन्हें
  राष्ट्रपिता कहा जाता है।", as contradicted by a joined premise that holds "He
  was first called this in 1914 in South Africa". A false contradiction on a
  set that had none, so the search is as before.
- **Context for Urdu.** For Urdu, the next letter as the context was compared
  with Hindi's (the word's end, a bare letter or a marked letter) on
  Dakshina's test tokens: precision 0.846 against 0.859, recall 0.755 against
  0.713. The next letter is used. Neither reads Urdu as well as Hindi is read
  (Limits).

## Wider Hindi: PMIndia

Measured on 31 October 2026 and **not adopted**: the shipped Hindi lexicon and
Roman reading are still learned from MASSIVE alone. PMIndia widened them a
great deal (FLORES Hindi claims read 29 → 247 of 1,012), and on a fresh
held-out set more claims were supported with no new wrong finding, but on the
existing sets a true Hindi claim was newly contradicted and three findings
were newly wrong, which the bar set beforehand does not allow.

### The gap

A production Roman claim, "Taj Mahal ko Mughal badshah Shah Jahan ne apni
begum Mumtaz Mahal ki yaad mein banwaya tha", is not read against "It was
built in the 17th century by Emperor Shah Jahan in memory of his wife, Mumtaz
Mahal.": "badshah", "begum" and "banwaya" have no translation. Devanagari
Hindi claims are supported 4 or 5 of 119 against English pages for the same
reason. MASSIVE is a voice assistant's vocabulary.

### Data and licence

Read and checked one by one; only PMIndia is used.

| Source | Licence | Decision |
|---|---|---|
| [PMIndia](https://data.statmt.org/pmindia/) v1 (Haddow and Kirefu, 2020), `pmindia.v1.hi-en.tsv`, 56,831 sentence pairs from the news updates of the Prime Minister of India's website, SHA-256 `bfa9fe6c…2029f` (Last-Modified 27 January 2020) | CC BY 4.0 (its README and paper); one provider, which made the content available for re-distribution | Used to build the measured lexicon, as extra Hindi–English training pairs; nothing of it is shipped |
| [Samanantar](https://huggingface.co/datasets/ai4bharat/samanantar) (AI4Bharat), at commit `ead34c5b` | The Hugging Face card says CC BY-NC 4.0, against the CC0 given for its mined part elsewhere. It collates existing corpora with their own terms: Tanzil (translations of the Quran), JW300, the Bible, OpenSubtitles, IITB (CC BY-NC 4.0) | Rejected: non-commercial on its card, and Quran text inside. Its rows carry no source (the files hold only `idx`, `src`, `tgt`), so no part can be left out |
| [BPCC](https://huggingface.co/datasets/ai4bharat/BPCC) (AI4Bharat, IndicTrans2), at commit `5bde3093` | BPCC-H-Wiki CC BY 4.0, but it is English Wikipedia sentences (CC BY-SA) and their translations; the mined parts are CC0 "packaging" of text AI4Bharat does not own, from Wikipedia dumps, the Internet Archive and religious and CC BY-SA sites, with no source per row | Rejected: share-alike re-licensed, and sub-sources that cannot be left out. Gated besides. BPCC-H-Daily (CC BY 4.0) is app requests, MASSIVE's domain |

Urdu has no such source here: PMIndia also has an English–Urdu file
(3.5 MB), which was not used (Limits).

### Method

The builder and its rules are unchanged; PMIndia's pairs are added to
MASSIVE's train pairs for Hindi only:

- the subset, fixed before any result was seen: every pair whose two sides
  have words, at most 40 words a side (IndicTrans2's mining cut-off), exact
  duplicates dropped, in the file's order: 53,656 pairs, all of PMIndia that
  fits (one EM iteration on 5,000 of them takes 2 seconds);
- EM stops by MASSIVE's validation log-likelihood, τ is fitted by F1 on the
  same validation slot dictionary, precision@1 is measured on the same test
  dictionary, names are judged on MASSIVE's slots, as before;
- pieces are judged over all the training text, and the Wilson bound counts
  every training sentence that holds a word;
- the Urdu, Arabic and Tamil files are rebuilt byte for byte.

The Roman reading is rebuilt with the same channel (same pairs, seed and
stopping rule), over a vocabulary of MASSIVE's Hindi words and PMIndia's
Devanagari words, their counts summed. The English filter is unchanged
(PMIndia's English is not added: it holds Indian words in Latin letters).
Every Hindi word's readings are kept, as before: the files then take 4.0 MB
in all, under the 5 MB the tests allow (a fallback, decided on size alone, was
not needed).

`build_qamus.py --extra` and `build_qamus_roman.py --extra` build this variant
(Rebuild and measure); without `--extra` both rebuild the shipped files byte
for byte.

### Pre-registered bar

Written before the new lexicon was measured. It is adopted only if all hold:

1. On a fresh held-out set of teacher answers, pooled non-English supported
   claims (Hindi, Urdu, Roman Hindi, Roman Urdu) rise.
2. Its control (another question's articles) stays at 0 supported and 0
   contradicted.
3. No true claim is newly contradicted.
4. On the existing sets (Hindi and Urdu answers, Roman answers, Roman false
   claims, the English true and false sets), wrong findings do not rise and
   the controls stay at 0.

### Measured (31 October 2026)

**The lexicon.** EM stopped after 3 iterations in both directions, as before.
On MASSIVE's test dictionary (its own domain), more words are held and the
first translation is right less often:

| Direction | precision@1 [95% Wilson] | right / held | coverage | words | shipped (MASSIVE alone) |
|---|---|---|---|---|---|
| hi→en | 0.750 [0.682, 0.808] | 135 / 180 | 0.73 of 248 | 11,662 | 0.812 [0.743, 0.866], 125 / 154, 0.62, 2,480 |
| en→hi | 0.625 [0.552, 0.693] | 110 / 176 | 0.78 of 226 | 20,902 | 0.700 [0.625, 0.766], 112 / 160, 0.71, 3,064 |

Words MASSIVE never held are now translated: "हालांकि" → however, "राज्य" →
state, "सम्राट" → emperor, "स्वतंत्रता" → independence, "वैज्ञानिक" →
scientist; "कारण" only as "due". Some translations are noise from PMIndia's
own phrasing: "सरकार" → govt, and "ने", the particle of "प्रधानमंत्री ने" (the
Prime Minister has), also → prime, minister. Names are still not swapped:
none of the 20 swaps of `tests/test_qamus.py` came back, and "भारत" is still
not read as india (nor "india" as anything Hindi).

**`about()` across scripts** (`scripts/qamus_eval.py`, Hindi):

| | shipped | with PMIndia |
|---|---|---|
| FLORES claims accepted | 29 / 1012 (2.9% [2.0, 4.1]) | 247 / 1012 (24.4% [21.9, 27.1]) |
| FLORES, through `judge()` | 18 | 76 |
| FLORES false accepts, random / hard | 0 / 20240, 0 / 3036 | 0 / 20240, 0 / 3036 |
| MASSIVE claims accepted | 64.3% of 2249 | 65.4% |
| MASSIVE false accepts, hard (English claim) | 13.1% (11.7%) | 12.4% (10.5%) |

**The Roman reading.** The Hindi vocabulary grew from 5,747 to 30,053 words
and its readings from 149,200 to 746,766. On Dakshina's test sentences,
Hindi content tokens: 45,776 read against 33,727, precision 0.870
[0.867, 0.873] against 0.830, recall 0.838 against 0.853. On Aksharantar's test
split, a spelling is read as its word 1,862 of 2,484 times (0.750), against
596 of 718 (0.830): far more of its words are now in the vocabulary. Urdu is
unchanged.

**The Taj Mahal claim is still not read.** Of its 8 distinctive words, the
sentence holds 3 (shah, mumtaz, mahal) as before. PMIndia never writes
"बादशाह" or "बेगम", and "बनवाया" once, so none of the three is translated.
The teacher's other wording, "Taj Mahal Shah Jahan ne apni biwi Mumtaz Mahal
ki yaad mein banwaya tha", is now *supported* by that sentence (below).

**Teacher answers, the existing sets**, each claim read with its subject,
against the question's Simple English Wikipedia articles and, as a control,
another question's:

| Set | shipped: supported, contradicted | with PMIndia | changed findings: newly wrong, wrong no longer found |
|---|---|---|---|
| Roman true claims, 158 | 26 [11.5, 23.0%], 0 | 33 [15.3, 27.9%], 0 | 0, 0 |
| Roman false claims, 20 | 0, 3 | 1, 3 | 1, 0 |
| Hindi (Devanagari) answers, 119 | 4, 0 | 6, 1 | 2, 0 |
| Urdu answers, 120 | 0, 0 | 0, 0 | 0, 0 |
| English set, 75 | 18, 0 | 19, 0 | 0, 0 |
| English false claims, 20 | 0, 8 | 0, 8 | 0, 0 |
| Controls of the non-English sets | 0, 0 | 0, 0 | |

**The fresh held-out set**: 30 other questions on other articles, the
teacher's answers in English, Hindi, Urdu, Roman Hindi and Roman Urdu, and 20
false claims, written and frozen before either lexicon was measured on them:

| Set | shipped: supported, contradicted | with PMIndia |
|---|---|---|
| Hindi, 80 claims | 2, 0 | 4, 0 |
| Urdu, 72 | 1, 0 | 1, 0 |
| Roman Hindi, 85 | 9, 1 | 11, 1 (the same claim) |
| Roman Urdu, 75 | 9, 0 | 11, 0 |
| **Pooled, 312** | **21** [4.4, 10.1%], 1 | **27** [6.0, 12.3%], 1 |
| English, 72 | 17, 0 | 17, 0 |
| False claims, 16 non-English and 4 English | 1, 2 and 0, 2 | 1, 2 and 0, 3 |
| Every control | 0, 0 | 0, 0 |

**Hand audit of every changed finding** (right: the sentence says it; part:
it says part of it; wrong). On the existing sets:

| Claim | Source sentence, shortened | Audit |
|---|---|---|
| + क्षेत्रफल की दृष्टि से दुनिया का सबसे बड़ा देश रूस है, जो यूरोप और एशिया दोनों महाद्वीपों में फैला है। | Russia has land borders… in both Europe and Asia. …Russia is the largest country in the world. | right |
| + जनसंख्या की दृष्टि से अब भारत दुनिया का सबसे बड़ा देश है। | …Russia is also the world's eighth most populous nation… It is the largest country in the world. | **wrong**: Russia's page; "भारत" has no translation (Limits), and population, world, most and largest carry more than half of the claim |
| + स्वर्ण का रासायनिक प्रतीक Au है। | Its chemical symbol is Au. | right |
| + *contradicted:* यह सौरमंडल का दूसरा सबसे बड़ा चंद्रमा है। (Titan) | Titan is the largest moon of Saturn and the second largest in the Solar System. | **wrong**: a true claim; the NLI model read it as contradicted both ways |
| − यह पुनर्जागरण काल का एक प्रसिद्ध चित्र है। | Salai was the owner of Leonardo's most famous oil painting, the Mona Lisa. | part (no longer found) |
| + Albert Einstein ek mashhoor German-born theoretical physicist the, jinhon ne relativity ke theory (special aur general) di… | …a German-born American scientist. …Einstein's general theory of relativity… | part |
| + Chand par sabse pehle insaan Neil Armstrong ne qadam rakha tha — 20 July 1969 ko Apollo 11 mission ke dauran. | On July 20, 1969, Armstrong and Aldrin became the first humans to land on the moon… | right |
| + DNA (Deoxyribonucleic Acid) ek molecule hai jo hamare cells ke andar genetic information store karta hai… (both Roman sets) | DNA… is the molecule that contains the genetic code of organisms. …DNA carries genetic information. | right, twice |
| + Iska nirmaan 1887 se 1889 ke beech Paris mein hua tha aur ise 1889 ki Exposition Universelle ke liye banaya gaya tha. | It was built between 1887 and 1889 for the Exposition Universelle… | right |
| + Unhe laws of motion aur universal gravitation ke liye jaana jaata hai, aur unki book Principia ne physics ki neev rakhi. | He is well known for his work on the laws of motion, optics, gravity… In 1687, Newton published… Principia… | right |
| + Taj Mahal Shah Jahan ne apni biwi Mumtaz Mahal ki yaad mein banwaya tha. | It was built in the 17th century by Emperor Shah Jahan in memory of his wife, Mumtaz Mahal. | right |
| + Taj Mahal ko Mughal badshah Shah Jahan ne apni biwi Mumtaz Mahal ki yaad mein tameer karwaya tha. | The Taj Mahal was built for Shah Jahan's third wife, Mumtaz Mahal… | part: not "in her memory" |
| + Darya-e-Amazon South America mein hai — yeh Andes pahadon se nikal kar Peru, Colombia aur Brazil se guzarta hua Atlantic Ocean mein girta hai. | Its headwaters are in the Andes Mountains in Peru… flows eastward into the Atlantic Ocean… across Brazil | part: not Colombia |
| + Microsoft ki bunyad Bill Gates aur Paul Allen ne rakhi thi. | Gates started Microsoft in 1975 with Paul Allen… | right |
| − Unhe 1921 ka Nobel Prize photoelectric effect par mila, aur E=mc² wala formula unki pehchan hai. | (as before) | part (no longer found) |
| − Saturn ka sabse bada chand Titan hai. | The largest moon is Titan. | right (no longer found) |
| − Iska atomic number 79 hota hai aur ye ek transition metal hai. | Its atomic number is 79… | right (no longer found) |
| + *False, supported:* Mona Lisa ki painting Michelangelo ne Rome mein banayi thi. | Michelangelo did not finish his painting either, because the Pope called him to Rome. Mona Lisa's eyes… Leonardo's most famous oil painting, the Mona Lisa. (joined) | **wrong**: a false claim supported by a joined premise |
| + *False, contradicted:* Sone ka chemical symbol Ag hai, jo Latin shabd argentum se aaya hai. | Its symbol is Au, from the Latin word for gold, aurum. | right |
| − *False, contradicted:* Alexander Graham Bell ko telephone ka pehla patent 1901 mein mila tha. | …the first person to patent the telephone, in 1876. | right (no longer found) |
| + 30 जनवरी 1948 को उनकी हत्या कर दी गई थी। (English set) | On 30 January 1948, he was shot to death by… Nathuram Godse… | right |

Eight more findings kept their verdict with another sentence of the same
page, right as before (Microsoft, the Nobel Prize of 1945, Photosynthesis
twice, Pride and Prejudice, the telephone, the Mona Lisa, Titan in Urdu).
The two wrong findings of the shipped lexicon (the New South Wales claim, and
"Mona Lisa ki painting Leonardo da Vinci ne banayi thi" against Leonardo's
full name) are unchanged.

On the held-out set:

| Claim | Source sentence, shortened | Audit |
|---|---|---|
| + पहले आधुनिक ओलंपिक खेल 1896 में ग्रीस की राजधानी एथेंस में हुए थे। | The first "modern" Olympics took place in 1896 in Athens, Greece. | right |
| + फ्रांसीसी क्रांति 1789 में शुरू हुई थी। | It began with the Estates General of 1789… | right |
| + Unhe America ke founding fathers mein se ek maana jata hai. | …one of the Founding Fathers of the United States. | right |
| + America ke pehle sadr George Washington thay. | George Washington… was the first president of the United States… | right |
| + Yeh chaar chambers mil kar khoon ko poore jism mein pump karne ka kaam karte hain. | It pumps blood throughout the body. In humans, the four chambers are… | right |
| + Us samay 14 deshon ke lagbhag 241 athletes ne hissa liya tha. | These Games brought 14 nations and 241 athletes… | right |
| + Pehli dafa kamyab powered hawai jahaz (airplane) Orville Wright ne 17 December 1903 ko Kitty Hawk, North Carolina mein uraya tha… | …flew the first controlled, powered, heavier-than-air airplane on December 17, 1903… first test flight was in Kitty Hawk, North Carolina. | right |
| + Agar sirf zameen (land) par sabse gehra sthan poocha jaye to woh alag hota hai, lekin "Earth ka sabse gehra point" aam taur par Challenger Deep ko hi kaha jata hai. | It is also the deepest known location on Earth itself. The deepest part of the trench is known as the Challenger Deep. | part |
| + Zameen ka sab se gehra maqam Challenger Deep hai, jo Mariana Trench ke andar Pacific Ocean mein, Guam ke qareeb hai. | It is also the deepest known location on Earth itself. The western end of the trench is near Guam. | part: does not name it |
| − Unhe 27 saal jail mein rakhna pada, aur baad mein 1994 mein South Africa ke pehle Black president bane. (both Roman sets) | …the first black President of his country, South Africa. | part, twice (no longer found) |
| − Inhe first Modern Olympic Games kaha jata hai, aur yeh International Olympic Committee ke dwara organize kiye gaye the. | It was the first international Olympic Games held in the Modern era. The International Olympic Committee (IOC) was also instituted… | part (no longer found) |
| + *False, contradicted:* The first modern Olympic Games were held in Paris, France, in 1896. | The 1896 Summer Olympics… were held at Athens in Greece. | right |

Seven more kept their verdict with another sentence: Kilimanjaro, Brazil,
the Titanic twice and the Athens Olympics, right as before, and "World Wide
Web ko Tim Berners-Lee ne banaya tha" twice, wrong as before (now "Berners-Lee
now leads the World Wide Web Consortium."). The false claim "Marie Curie 7
November 1867 ko Berlin mein paida hui thin" is supported in both arms
(wrong), and the one true claim contradicted is the same in both (the Wright
brothers, read as English).

**The bar.** On the held-out set, items 1 to 3 hold: pooled supported claims
rise from 21 to 27 of 312, the control stays at 0 and 0, and no true claim is
newly contradicted. On the existing sets, items 3 and 4 fail: the Hindi Titan
claim is newly contradicted, and three findings are newly wrong while none
that was wrong is gone. **Not adopted.**

All three new wrong findings come from sentences the shipped lexicon never
let through, not from wrong translations:

- the NLI model reads a true Hindi claim against the sentence that says it as
  a contradiction, both ways ("दूसरा सबसे बड़ा", second largest, against "the
  largest moon of Saturn and the second largest in the Solar System");
- a claim's name is not translated ("भारत", India, Limits), so its other
  words carry more than half of its information on a page about another
  country;
- searched by more translations, a page's best sentences changed, and three
  of them joined name Michelangelo, Rome and the Mona Lisa for a false claim
  `about()` already accepted.

A wider lexicon brings more such sentences to the NLI model; these three
checks would need to hold before it is shipped.

## Limits

- **The vocabulary is a voice assistant's.** MASSIVE is alarms, music, weather,
  lists and short factual questions. On encyclopedic text, half of a claim's
  distinctive information is in words MASSIVE never holds ("हालाँकि" however,
  "कारण" reason, "राज्य" state). Another third is in a form or synonym the
  sentence does not use: "use" against "used", "multiple" against "many".
  PMIndia (CC BY 4.0) widens Hindi a great deal and was not adopted, for the
  wrong findings it let through (Wider Hindi: PMIndia); Samanantar and BPCC
  are not licence-clean. Tatoeba (CC BY 2.0 FR, already the Lughah source) is
  untried. PMIndia's English–Urdu file was not tried, so Urdu has no wider
  source.
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
- **Roman Hindi and Urdu are read through MASSIVE's words.** Only a word of
  MASSIVE's Hindi or Urdu vocabulary (5,747 and 5,496 words) is read, and it
  helps only when the lexicon translates it. "banwaya" (बनवाया) and "begum"
  are not in MASSIVE; "badshah" (बादशाह) and "deewar" (दीवार) are read but have
  no translation. PMIndia would not change this for the Taj Mahal claim: it
  never writes "बादशाह" or "बेगम", and "बनवाया" once. A word is read only as one of the 30 spellings the channel
  finds most probable for it.
- **Urdu is read less well than Hindi.** Its short vowels are not written, so
  one Urdu word has many spellings, and most of Aksharantar's Urdu pairs are
  words run together from web text ("ہوگادوسرے", hoga dosray).
- **A Roman word spelled like an English word is never read** ("door" for दूर,
  "main" for मैं), nor a name that MASSIVE's English utterances use outside a
  slot.
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

The Roman reading:

    python -I scripts/build_qamus_roman.py --data /tmp/qamus_roman_data          # writes hi-latn.json.gz
    python -I scripts/build_qamus_roman.py --data /tmp/qamus_roman_data --check  # fails if a rebuild differs
    python -I scripts/qamus_roman_eval.py --dakshina /tmp/dakshina_dataset_v1.0

The build reads Aksharantar's Hindi and Urdu archives (33 MB and 18 MB) and
MASSIVE's train splits, and takes about 10 minutes on one CPU. The
measurement needs Dakshina v1.0 unpacked (`dakshina_dataset_v1.0.tar` from
Google's storage, 2 GB; only `hi/romanized` and `ur/romanized` are read).

The measured variant with PMIndia (not adopted), in place of the shipped Hindi
files (`git checkout` restores them):

    python -I scripts/build_qamus.py --data /tmp/qamus_data --extra --languages hi   # hi-en.json.gz, content SHA-256 488fe6eb13db9834…
    python -I scripts/build_qamus_roman.py --data /tmp/qamus_roman_data --extra      # hi-latn.json.gz, content SHA-256 4faea1ed98d3e110…

Each downloads PMIndia's `pmindia.v1.hi-en.tsv` (23 MB) into its data folder
once and refuses it if its SHA-256 is not the pinned one. The lexicon build
then takes about 3 minutes, the Roman reading about 10.
