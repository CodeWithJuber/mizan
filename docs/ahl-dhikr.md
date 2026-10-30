# Ahl al-Dhikr: when MIZAN does not know, it asks those who know

> "Ask the people of knowledge if you do not know." Quran 16:43 ([An-Nahl 16:43](https://quran.com/16:43))

When MIZAN does not recognise a request, the language model answers in its own
words. Isnad grades each claim of such an answer **da'if**, because nothing
MIZAN holds supports it, and Sidq corrects only what it can prove: arithmetic,
quoted Quran and hadith, claimed actions and links. Ahl al-Dhikr goes further.
When the question asks about the world, MIZAN asks its sources about each
da'if claim **before the answer is shown**, and keeps what they settle.

## When it runs

- **The answer is the model's own words.** MIZAN's own recipes (calculations,
  Quran, hadith, dates, code it ran) are already established.
- **The question asks about the world.** This is decided by Qasd's `fact`
  facet, a yes/no model learned from seeds in five languages
  (`tadbir/data/qasd/facets.tsv`). It contains no word list. "Who built the
  Taj Mahal?" is a fact question; "Write me a poem" is not.
- **Or the question asks for a religious ruling.** This is decided by the
  `ruling` facet, for questions such as "Is it halal to invest in crypto?" or
  "Gusse mein di gayi talaq hoti hai?".
  - MIZAN does not give fatwa. Under the answer, with its sources, it shows:
    *"This asks for a religious ruling. MIZAN does not give fatwa; ask a
    qualified scholar (ahl al-ilm) who can weigh your situation."*
    (`usage.ahl.referral`, never inside the answer's text; a Telegram,
    WhatsApp or email reply, which has no notes view, prints it on its own
    line).
  - Scholarly bodies agree that AI may help with research but may not act as
    a mufti: the OIC Islamic Fiqh Academy (Resolution 258, 2025), Al-Azhar,
    Dar al-Ifta and the Muslim World League.

## Whom it asks

MIZAN asks its sources in this order:
1. **What it settled before** for this user (its `ilm`). These are sentences
   a source confirmed or contradicted earlier, each kept with its title, link
   and date.
2. **Outside sources:**
   - **Wikipedia**, in the question's language (English for Roman
     Hindi/Urdu), then English. It uses MediaWiki's own search (the top two
     articles), then the article's plain text. When the Action API does not
     give an article's text, its lead section comes from the REST API's
     summary instead (a separate, cached service).
   - **A web search**, whose snippets are untrusted data: Amanah removes any
     instruction aimed at the AI.

A question about the deen is **never** asked of the outside sources. MIZAN
quotes the Quran and hadith from their own sources, and a ruling is a
scholar's. A question counts as being about the deen when any of these holds:
- Qasd's `deen` facet says so (the Quran, a hadith, belief, worship, a word of
  the Quran). This is a yes/no model learned from seeds in five languages;
  "When did the Ottoman Empire end?" is not about the deen;
- the `ruling` facet says so;
- the answer cites a Quran or hadith reference (`2:153`, `Sahih al-Bukhari 1`).

The order of the outside sources is learned. Each source has a Beta posterior
of settling a claim when asked, and each answer asks them in the order of a
Thompson sample. MIZAN stops when every claim is settled or a 20-second budget
is spent.

MIZAN follows Wikimedia's [robot policy](https://wikitech.wikimedia.org/wiki/Robot_policy):
- It identifies itself by name, version and how to reach its operator. Set
  `MIZAN_CONTACT` to an email address in Settings → Developer → System settings,
  so Wikimedia can reach the operator instead of blocking the server.
- It asks one request at a time, as the Action API asks of a client that does
  not log in.
- On 429 or 503 it waits as long as `Retry-After` says and asks once more, but
  only if that wait is at most half the time left. The other half is for the
  retried request and the other sources.
- On 403 (a refusal under the policy) it stops asking Wikipedia for that
  answer, so the web search keeps its time. Nothing is done to get around a
  refusal. Shared cloud addresses are often refused; on 30 October every
  Wikipedia endpoint answered 403 to the development sandbox.

## How a claim is judged

1. The source's sentences are ranked by **BM25** against the claim. A
   sentence is kept only if it is **about what the claim is about**:
   - the claim's distinctive words are those whose information (inverse
     document frequency over Lughah's corpora in five languages) is above
     the claim's mean;
   - the sentence must contain more than half of that information.

   So a page that shares only common words with the claim ("the", "largest")
   is never read against it, however the NLI model would read the pair. The
   best three kept sentences go on.

   A claim in Hindi, Urdu, Arabic or Tamil against an English page: BM25 also
   searches by the claim's translations in MIZAN's own lexicon, and a
   distinctive word counts as present when an above-average-information
   translation of it is in the sentence ([Qāmūs](qamus.md)). On the production
   teacher's Hindi and Urdu answers this supported 5 of 119 and 2 of 120 claims
   (from none), with none read against another question's articles.

   A model's sentence often joins what a source says in several: "commissioned
   by Shah Jahan in memory of Mumtaz Mahal" against "It was built by Shah
   Jahan…" and "…for his wife, Mumtaz Mahal". No single sentence holds most of
   its information, so none could be read against it. So each claim also gets
   one **joined premise**:
   - the page whose best three sentences match the claim most (summed BM25)
     gives them, in the page's own order;
   - the joined text must be about the claim, by the same rule as above;
   - it is read like any sentence, and its contradiction must also hold both
     ways (step 3).

   Only propositions are judged: a claim needs at least three words, the same
   unit a source sentence needs, and a lead-in ending in ":" ("Thodi
   detail:") is not a claim at all (Isnad skips it).
2. A multilingual **NLI model** reads each kept sentence against the claim.
   - Model: `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`, MIT licence,
     covering English, Arabic, Hindi, Urdu and more.
   - It runs with ONNX Runtime on the CPU at about 5 ms per pair, at a pinned
     revision.
   - It is downloaded once (428 MB) into `$MIZAN_DATA_DIR/models/nli` and let
     go after ten idle minutes.
3. The **verdict** is the most probable label of the most decisive sentence
   (entailment or contradiction, whichever is strongest). There is no
   threshold:
   - **supported**: the claim becomes **hasan** in the Isnad ledger, with
     "*title* (*source*) says so";
   - **contradicted**: only when the contradiction holds both ways. The NLI
     model also reads the claim against the source's sentence, and
     contradiction is symmetric, so a one-way reading is a misread and settles
     nothing (on 27 October an agreeing page was shown as "says otherwise").
     The claim stays da'if with "*title* says otherwise", and the source's
     sentence and link are listed **under the answer**. The model's sentence
     is never silently rewritten;
   - **neither**: the claim stays unknown.

   Nothing the sources say is ever written into the answer itself. Notes inside
   the text landed in table rows, formulas, verses, refusals and after a last
   word the user required (27 October benchmark: 258 notes in 51 answers).
   An equation ("9.11 = 9 + 0.11", "60 × 60 = 3600") is never asked of a
   source either: computing it settles it ([Sidq](sidq.md)).

Claims no source settled are reported under the answer ("Sources asked: 2 not
found — the model's own words, Allahu a'lam"), not added to its text. A note
inside the text broke answers asked for in an exact shape (one sentence,
JSON), as the live benchmark of 27 October found.

Without the NLI model, every claim stays unknown and nothing is guessed.

### Measured (30 October 2026)

`scripts/ahl_coverage.py` judges a fixed set of teacher answers offline with
the real NLI model, against two kinds of source:
- the questions' articles in Simple English Wikipedia (the `wikimedia/wikipedia`
  dump of 1 Nov 2023);
- web search results (DuckDuckGo snippets), captured once.

Two sets of claims:
- **True set:** 30 questions, 66 claims. Answers came from the production
  teacher model, one paragraph each.
- **False set:** 20 claims with one fact changed (a name, number or date).

95% Wilson intervals in brackets:

| Source | Premises | Supported (true set) | Contradicted (true set) | Talaqqi keeps | Supported (false set) | Contradicted (false set) |
|---|---|---|---|---|---|---|
| Wikipedia articles | One sentence each (before) | 5/66 = 7.6% [3.3, 16.5] | 1/66 | 5/30 | 0/20 | 8/20 |
| Wikipedia articles | Plus the joined premise (now) | **17/66 = 25.8% [16.7, 37.4]** | **0/66** | **12/30** | 0/20 | **10/20** |
| Web snippets | One sentence each (before) | 13/66 = 19.7% [11.9, 30.8] | 1/66 | 9/30 | 0/20 | 10/20 |
| Web snippets | Plus the joined premise (now) | **15/66 = 22.7% [14.3, 34.2]** | 1/66 | **10/30** | 0/20 | 10/20 |

- **Audit:** every claim the joined premise newly supported (12 from articles,
  2 from snippets) was checked against its source by hand. All 14 are right;
  one is right only in part (the Nile "drains … Egypt" claim's premise does
  not name Egypt).
- **Contradictions:** with the joined premise, 20 of 21 were right. The wrong
  one is the NLI model misreading a pair both ways: "commissioned by Shah
  Jahan in memory of his wife Mumtaz Mahal" against a snippet saying "built
  by Emperor Shah Jahan to house the tomb [of] his wife". The one
  contradiction from articles before was a misreading of the same claim; the
  joined premise supports it.
- **Not adopted:**
  - **Two-sentence windows** (articles: 11/66 supported, 7/30 kept) add
    nothing beyond the joined premise.
  - **A larger NLI model,** `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`
    (MIT, int8 ONNX, 339 MB), was measured the same way (`--nli`). On the
    false set it supported 2 of 20 and contradicted none. For example, it
    read "stolen on August 21, 1950" as supported by "On August 21, 1911,
    the Mona Lisa was stolen".

**Not covered yet:** an answer written in a script its source does not use. On
the five Hinglish questions the teacher answered in Devanagari, so no claim
could be matched against English sentences. Their Wikipedia edition (`hi`) was
not in this offline set.

### Word information per language: measured, not adopted (30 October 2026)

`about()` weighs a word by its inverse document frequency over Lughah's five
corpora pooled (about 900 short sentences each). Every word those sentences do
not hold weighs the same as a name, so ordinary Hindi and Urdu words such as
"प्रसिद्ध" (famous) or "سب سے" (most) can look distinctive. A better estimated
measure was built and measured: **Gharib** (`backend/tadbir/gharib.py`).

- **Information.** A word's Shannon self-information in the language of the
  text it is read in, `information(w | L) = −log P(w | L)`. A text's language
  is the one under which its words are most probable,
  `argmax_L Σ_w log P(w | L)` (no Lughah call, no script table).
- **Frequencies.** wordfreq 3.1.1's "small" lists (data CC BY-SA 4.0) for
  English, Arabic, Hindi, Urdu and Tamil: every word written at least once per
  million running words. Each entry is cut into words as MIZAN cuts text,
  each digit written 0, and the pieces' frequencies renormalised with the
  share of running words the list leaves out. A number is its shape times
  10^−digits (every number of a shape equally likely). A word no list holds
  carries −log 10^−6 = 13.8 nats in every language.
- **Roman Hindi/Urdu** has no wordfreq list. It is a mixture,
  `P(w | hi-latn) = λ · P_roman(w) + (1 − λ) · P(w | en)`, fitted by EM on
  Lughah's 982 Roman Hindi sentences, each occurrence left out of its own
  word's estimate (a word seen once is no evidence of Roman Hindi): λ = 0.907.
  This uses data MIZAN already ships; a larger Roman Hindi corpus was not
  added.
- **Floor.** A word is informative when it carries more than the average
  running word of its language, the entropy `Σ_w P(w | L) · information(w | L)`:
  English 7.51, Hindi 7.40, Urdu 7.28, Arabic 9.06, Tamil 9.76, Roman Hindi
  6.13 nats.
- **Data.** `backend/tadbir/data/gharib/words.json.gz`: 958 KB gzip, 203,547
  words (English 28,211; Arabic 56,529; Hindi 26,376; Urdu 23,134; Tamil
  68,239; Roman Hindi 1,058). Built and checked byte for byte by
  `python -I scripts/build_gharib.py --wheel wordfreq-3.1.1-py3-none-any.whl
  [--check]`, which reads the pinned wheel as a zip and runs none of its code.
  Licences and attribution: `backend/tadbir/data/gharib/LICENSES.md`.

It was measured by setting `ahl_dhikr.WORDS = "gharib"`
(`scripts/ahl_coverage.py --information gharib`), with the real NLI model, on
the same sets. Three readings of "distinctive" were tried: above the claim's
mean (as now), above the language's floor, and both.

**Hindi and Urdu answers against Hindi and Urdu Wikipedia** (`wikimedia/wikipedia`
20231101; the articles whose titles the answer contains, longest first). The
control reads each answer against another question's articles. Every settled
claim was audited by hand against its premise: *part* means the premise says
some of the claim (e.g. Peru and Brazil but not Colombia); *wrong* includes
two Mars claims whose premise gives the cause of the planet's colour, not its
name "the red planet".

| Words weighed by | Hindi supported (right / part / wrong) | Hindi contradicted (wrong) | Urdu supported (right / part / wrong) | Urdu contradicted (right / wrong) | Control: Hindi | Control: Urdu |
|---|---|---|---|---|---|---|
| Lughah IDF (in use) | 22 (14 / 1 / 7) | 2 (2) | 21 (12 / 5 / 4) | 2 (1 / 1) | 1 supported, 1 contradicted | 1 supported |
| Gharib, above the claim's mean | 23 (14 / 2 / 7) | 1 (1) | 21 (11 / 6 / 4) | 2 (1 / 1) | 1 contradicted | 1 supported |
| Gharib, above the floor | 22 (15 / 1 / 6) | 1 (1) | 20 (12 / 5 / 3) | 2 (1 / 1) | 1 contradicted | none |
| Gharib, both | 22 (14 / 2 / 6) | 1 (1) | 20 (11 / 6 / 3) | 2 (1 / 1) | 1 contradicted | none |

**English** (`scripts/ahl_coverage.py --arms joint`; Isnad now cuts the four
answers written in Devanagari at the danda, 13 claims instead of 4, so the 30
true answers give 75 claims and the counts differ from the table above):

| Words weighed by | True set, Wikipedia | True set, web | False set, Wikipedia | False set, web |
|---|---|---|---|---|
| Lughah IDF (in use) | 19/75 supported, 0 contradicted | 18/75, 1 | **0/20 supported, 10 contradicted** | **0/20, 10** |
| Gharib, above the claim's mean | 19/75, 1 | 19/75, 1 | 1/20, 7 | 0/20, 8 |
| Gharib, above the floor | 19/75, 0 | 20/75, 1 | 1/20, 7 | 0/20, 8 |
| Gharib, both | 19/75, 1 | 19/75, 1 | 1/20, 7 | 0/20, 8 |

**Hindi and Urdu answers against Simple English Wikipedia with Qāmūs**
(supported; no arm contradicted any claim):

| Words weighed by | Hindi | Urdu | Control: Hindi | Control: Urdu |
|---|---|---|---|---|
| Lughah IDF (in use) | 5/119 | 2/120 | 0 | 0 |
| Gharib, above the claim's mean | 5/119 | 2/120 | 0 | **1** |
| Gharib, above the floor | 4/119 | 3/120 | 0 | **1** |
| Gharib, both | 5/119 | 2/120 | 0 | **1** |

Not adopted, for three reasons:

1. **Precision did not improve.** Every arm still supports 6 or 7 Hindi and 3
   or 4 Urdu claims wrongly, and still contradicts claims wrongly.
2. **English contradictions were lost.** Self-information weighs a name or a
   year far above the claim's other words, and a false claim differs from its
   source exactly there ("Buzz Aldrin … in 1972"), so the source sentence no
   longer holds most of the claim's information and is not read: 10 → 7 and
   10 → 8 contradicted, and one false claim supported ("Buzz Aldrin was the
   first person to walk on the Moon in 1972", by a joined premise naming
   Aldrin and the Moon).
3. **A cross-script control finding appeared:** "اسے انگریزی میں مارس کہا جاتا
   ہے۔" ("it is called Mars in English") was read against Newton's article,
   because Qāmūs reads "مارس" as Arabic "March" and Newton died in March.

**What the wrong findings are.** With the weights in use, 13 of the 17 wrong
Hindi and Urdu findings (supports, contradictions and control findings) are
claims that open with a pronoun and do not name what they are about: "यह उनका एक प्रसिद्ध उपन्यास है।"
("this is her famous novel") against a sentence about Robinson Crusoe, "یہ
شمال کی طرف بہتا ہوا بحیرہ روم میں گرتا ہے۔" ("it flows north into the
Mediterranean") against Africa's article. Their words are on the other page
too; what is missing is the subject, which no weighing of the claim's own
words can supply. Of the claims that name their subject, 16 settled right, 3
in part and 4 wrong. So Wikipedia in the claims' own language is not asked
yet. The next step is to make each claim stand alone before it is judged
(the subject put back, from the answer itself), then measure again.

## It learns

- **Kept for this user.** What an outside source settled is kept in the user's
  `ilm` (in MIZAN's adaptive store, most recently used first, up to 300
  sentences). Each entry holds the claim, the source's sentence, title, link,
  date and the words of the question that asked it.
- **Asked once.** The same claim is settled from memory next time. The same
  site is not asked again, since a site is never its own second witness.
- **Shown to Lisan, once two sources agree.** Before Lisan writes an answer,
  the settled sentences that bear on the question are given to it as
  **"SETTLED BY MIZAN FROM SOURCES"**, so the answer starts from evidence rather
  than from the model's memory. A sentence counts only when two independent
  sites agree and none disagrees ("two witnesses", 2:282; "investigate", 49:6).
  - **One site:** the claim is shown under the answer but is not given as
    knowledge.
  - **Ilm with one site:** MIZAN asks its outside sources again to find a
    second witness.
  - **Weighing.** Each site's reliability is a Beta posterior, raised when an
    independent site agrees and lowered when one disagrees. The sites are
    combined in log-odds (`witnesses`, `p_true`). See
    [Quranic algorithms](quranic-algorithms.md#2-isnad-two-witnesses-before-a-fact-becomes-knowledge-tadbirahl_dhikrpy).
- **Only what is about its claim.** A kept entry whose sentence is not about
  its own claim (kept before the relevance gate existed) is not used and is
  dropped from the store when it is next written. Lisan is given a settled
  sentence only when it is about the question too. On 27 October a Saturn
  answer showed an old entry about a tafsir page as "the source says
  otherwise"; that cannot happen again.
- **Private.** Each user's `ilm` is their own.
- **Erased with the chat.** Deleting a chat (Mahw) drops what that chat's
  requests taught.

While MIZAN rests (Nawm, `docs/automatic-learning.md`), the claims one site settled are asked of Wikipedia again, so a second witness can make them knowledge before anyone asks.

## In the chat

Under each answer, **📚 Sources asked** lists every confirmed and
contradicted claim with its source and link. The report travels as
`result["ahl"]` → `usage.ahl`; the Isnad ledger shows the new grades.

## Setting

`MIZAN_AHL_DHIKR`: `on` (default) or `off`, in Settings → Developer → System settings.
