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
  "When did the Ottoman Empire end?" is not about the deen. Until 31 Oct 2026 it
  read 72% of everyday Hindi and 61% of everyday Urdu requests as about the deen
  by their script alone, so their claims were never asked of Wikipedia; its
  seeds were rebuilt with the deen's recall first ([fahm.md](fahm.md#the-deen-facet-31-oct-2026));
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

   **A claim that does not name what it speaks of.** "यह उनका एक प्रसिद्ध
   उपन्यास है।" ("It is a famous novel of hers") holds the words of any
   sentence on any famous novel. MIZAN reads it with its subject, found in the
   answer's own words and the question's, with no model call (`contexts`):
   - the answer's subject is the distinctive words of its first sentence
     that the question or a later sentence also holds, and the question's
     content words (or their Qāmūs translations into the answer's script)
     that a sentence holds. With none shared, it is the first sentence's
     distinctive words;
   - a sentence holding more than half of the subject's information names it
     and stands alone;
   - any other sentence is read with the words of the first sentence and of
     the subject that it lacks, taken only from the question and the
     sentences before it: the things it may refer to;
   - its source sentences are searched by its words and these, and a source
     sentence is about it only when it also names one of them, as it is or
     translated. A word MIZAN cannot see in the source's script (no Qāmūs
     translation into it) is no evidence either way;
   - the NLI model reads the claim's own words.

   Only claims that stand alone are kept, in the `ilm` and by Talaqqi. Apart
   from its answer, "It is a famous novel of hers" says nothing, and kept it
   would later be read as about any novel.

   A claim in Hindi, Urdu, Arabic or Tamil against an English page: BM25 also
   searches by the claim's translations in MIZAN's own lexicon, and a
   distinctive word counts as present when an above-average-information
   translation of it is in the sentence ([Qāmūs](qamus.md)). On the production
   teacher's Hindi and Urdu answers this supported 5 of 119 and 2 of 120 claims
   (from none), with none read against another question's articles.

   A claim Lughah reads as Hindi or Urdu in Latin letters ("Taj Mahal Shah
   Jahan ne banwaya tha"): Qāmūs reads each of its words as the Hindi or Urdu
   word that most probably wrote it, so its translations count the same way.
   The NLI model reads it in Devanagari (the words Qāmūs reads, the premise's
   own words kept), and it is contradicted only when it is contradicted
   however it is written, both ways. On 60 Roman answers of the production
   teacher (158 claims), each claim read with its subject, 26 claims were
   supported where 8 were (22 right, 2 part, 2 wrong on audit), none was
   contradicted, and none was read against another question's articles
   ([Qāmūs](qamus.md#roman-hindi-and-urdu)).

   A model's sentence often joins what a source says in several: "commissioned
   by Shah Jahan in memory of Mumtaz Mahal" against "It was built by Shah
   Jahan…" and "…for his wife, Mumtaz Mahal". No single sentence holds most of
   its information, so none could be read against it. So each claim also gets
   one **joined premise**:
   - the page whose best three sentences match the claim most (summed BM25)
     gives them, in the page's own order;
   - the joined text must be about the claim, by the same rule as above;
   - it may support the claim but never contradicts it. "Says otherwise" is
     shown with the source's sentence, so it must be one sentence that
     contradicts the claim both ways (step 3). The NLI model reads a join of
     sentences on several things as disagreeing with a claim on one of them:
     "Japan's army … took their capital, Beijing", joined with a sentence on
     Australia, against "ऑस्ट्रेलिया की राजधानी कैनबरा है।" (Canberra), on
     another question's page.

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

**Since 30 October** (claims that do not name their subject, below), a joined
premise no longer contradicts a claim. With the same script on the same sets (75 claims now: Isnad splits a
Hindi answer at the danda), from articles: 6/75 → **17/75** supported, 0
contradicted, Talaqqi keeps 12/30; false set 0/20 supported, **8/20**
contradicted (10 before: "signed on September 2, 1939" and "founded by Steve
Jobs … in 1985" were contradicted only by a joined premise). From snippets:
16/75 → 18/75 supported, Talaqqi keeps 11/30; false set 0/20 supported, 10/20
contradicted.

### Measured: claims that do not name their subject (30 October 2026)

The production teacher answered 30 questions in Hindi (119 claims) and 30 in
Urdu (120 claims). Each answer was judged offline with the real NLI model
against:
- **its own language's Wikipedia:** the Hindi or Urdu articles whose titles
  the answer holds (`wikimedia/wikipedia`, 1 Nov 2023 dumps);
- **a control:** another question's articles (question j against j + 7).
  Every finding there is wrong;
- **cross-script:** the questions' Simple English Wikipedia articles, and the
  same control;
- the **English** sets above (true set: 75 claims; false set: 20).

Every supported or contradicted claim was read against the source sentence
shown with it and labelled right, part (only some of the claim is in the
sentence) or wrong. Before, 12 of the 17 wrong findings in Hindi and Urdu
(own pages and controls) were claims that do not name their subject, as the
rule above finds them, read against a sentence on another subject: "यह उनका
एक प्रसिद्ध उपन्यास है।" against a sentence on another writer's novel.

Supported and contradicted claims, as right / part / wrong:

| Set | Claims | Supported before | Contradicted before | Supported now | Contradicted now |
|---|---|---|---|---|---|
| Hindi, Hindi Wikipedia | 119 | 22 (14/1/7) | 2 (0/0/2) | 20 (16/2/2) | 0 |
| Urdu, Urdu Wikipedia | 120 | 21 (12/5/4) | 2 (1/0/1) | 18 (13/5/0) | 0 |
| Hindi, another question's pages | 119 | 1 (0/0/1) | 1 (0/0/1) | **0** | **0** |
| Urdu, another question's pages | 120 | 1 (0/0/1) | 0 | **0** | 0 |
| Hindi, Simple English Wikipedia | 119 | 5 (3/0/2) | 0 | 4 (3/1/0) | 0 |
| Urdu, Simple English Wikipedia | 120 | 2 (2/0/0) | 0 | 0 | 0 |
| Both, another question's English pages | 239 | 0 | 0 | 0 | 0 |
| English true set, Simple English Wikipedia | 75 | 19 (18/1/0) | 0 | 17 (17/0/0) | 0 |
| English true set, web snippets | 75 | 18 (18/0/0) | 1 (0/0/1) | 18 (18/0/0) | 1 (0/0/1) |
| English false set, Simple English Wikipedia | 20 | 0 | 10 (10/0/0) | 0 | 8 (8/0/0) |
| English false set, web snippets | 20 | 0 | 10 (10/0/0) | 0 | 10 (10/0/0) |

- **Over all sets:** wrong findings 20 → **3**, right 88 → 85, part 7 → 8.
  No false English claim is supported, before or now.
- **The three still wrong** were not read with a subject:
  - "मंगल ग्रह को लाल ग्रह कहा जाता है।" ("Mars is called the Red Planet")
    and "इसी विशेषता के कारण इसे लाल ग्रह के नाम से जाना जाता है।" are
    supported by a sentence that says why Mars is red, not what it is called;
  - the snippet contradiction listed above (a one-sentence misreading, both
    ways).
- **What was lost:**
  - Simple English Wikipedia's own sentences often lean on a pronoun too: "He
    is best known for developing the theory of relativity…" and "30 जनवरी
    1948 को उनकी हत्या कर दी गई थी।" are no longer supported (right before),
    nor the Nile's "It flows north…" (part);
  - two right cross-script supports in Urdu, and the one right Urdu
    contradiction (the Taj Mahal's building years, against "یہ تقریباً 1648ء
    میں مکمل تعمیر کیا گیا۔", "It was completed around 1648", which does not
    name the Taj Mahal either);
  - two right English contradictions that only a joined premise gave (above).
    From snippets, "Pride and Prejudice was written by Charlotte Bronte" is no
    longer contradicted and "306 bones" now is, by one sentence.
- **Measured on the sets the design was chosen on.** About twenty variants
  were measured on these same sets and no held-out set was kept, so the
  numbers above flatter it. With joined premises still contradicting, the
  variants that ask the sentence to name one of the subject words gave 4–9
  wrong findings in Hindi and Urdu together (this rule alone: 5), and at
  least one against another question's page.

**Not adopted:**
- **Lisan rewrites each claim to stand alone** (comparison only, never
  shipped). The teacher rewrote the claims of all 110 answers in one call each,
  replacing pronouns by the words they stand for (334 claims, 216 changed;
  $0.017 in all). A rewrite was kept only when every content word it added is
  in the question or the answer (11 claims failed this check), and the
  rewritten claim was read with the joined-premise rule now in use:
  - more supported: English true sets 40 (38/2/0) against 35 (35/0/0); Hindi
    21 (17/2/2); Urdu 24 (14/7/3);
  - more wrong: 7 against 3 over all sets, including one against another
    question's page: Titan's "इसका व्यास लगभग 5,150 किलोमीटर है और यह बुध से
    भी बड़ा है…", rewritten with "टाइटन", supported by the Mars page ("Mars is
    larger than Mercury");
  - one model call per answer. MIZAN's own rule asks no model.
- **The subject as one more distinctive word** (the sentence must hold more
  than half of the claim's and the subject's information together), or each
  subject word counted as the claim's own: 7–10 wrong findings in Hindi and
  Urdu.
- **A page's title naming the subject** of its sentences: two more wrong Urdu
  supports ("یہ ملک کے جنوب مشرقی حصے میں واقع ہے۔" on the Australia page,
  "یہ شمال کی طرف بہتا ہوا بحیرہ روم میں گرتا ہے۔" on the Africa page).
- **The NLI model reading the claim after its subject words:** the same wrong
  findings, two more right supports in Hindi and Urdu and two fewer in
  English.
- **A joined premise's contradiction shown with the one of its sentences that
  contradicts the claim both ways:** the sentence the model picked was wrong
  in 4 of 6 ("Gates stepped down from his CEO position…" against "founded by
  Steve Jobs").

**Not measured: asking Wikipedia in the claims' own language.** These
questions are in English or Roman Hindi/Urdu, so Wikipedia is asked in English,
while the teacher answered in Hindi or Urdu. Asking the claims' own edition
(`hi`, `ur`, `ar`), searched by the claims, could not be measured live: on 30
October Wikimedia refused MIZAN's client from the development sandbox (403,
"Please respect our robot policy"), and nothing was done to get around it.
Offline, the Hindi and Urdu articles whose titles the answers hold supported 20
(16/2/2) and 18 (13/5/0) claims, against 4 (3/1/0) and 0 from the questions'
English articles, with none against another question's pages. Those articles
were picked by title, not found by Wikipedia's search, so this is not a
measurement of asking by the claims, and it is not wired.

### Held-out (31 October 2026)

Three designs were chosen on the 30 questions above, with about twenty
variants measured on them: claims read across scripts through
[Qāmūs](qamus.md), each claim read with its subject, and Roman Hindi and Urdu
read through Qāmūs ([Roman Hindi and Urdu](qamus.md#roman-hindi-and-urdu)). So
they were measured again on a new set, with no change to the code and nothing
tuned on it.

**The set.**
- 30 new fact questions, none of the 30 above and on none of their articles:
  science 6, geography 5, history 5, people 4, inventions 4, sport 3, nature 3
  (Marie Curie, the Sahara, the Titanic, Nelson Mandela, the World Wide Web,
  the first modern Olympics, the cheetah, …). None is about the deen. Each has
  1–3 articles in the same Simple English Wikipedia dump.
- Five wordings of each, written by hand: English, Hindi in Devanagari, Urdu in
  Urdu script, Hindi-leaning Roman ("Polio ka pehla teeka kisne banaya tha?")
  and Roman Urdu ("Polio ki pehli vaccine kis ne banai thi?"). The questions
  were frozen (SHA-256 recorded) before the teacher was asked.
- The production teacher answered all 150 with the call and instruction used
  above ("one paragraph of a few sentences, in the language of the
  question"). The 27 Roman questions answered in Devanagari or Urdu script (16
  Hindi-leaning, 11 Urdu-leaning) were asked once more with production's reply
  instruction for Hinglish, and all 60 then were in Latin letters. 177 calls,
  10,970 prompt and 40,668 completion tokens, $0.0092 as OpenRouter reported
  it.
- 20 false claims written by hand, 4 in each form, each one sentence with one
  fact changed (a year, a place, a number or a name), with the article sentence
  that contradicts it. They were frozen before any measurement was read.
- Judged offline by the real NLI model as above: English with
  `scripts/ahl_coverage.py`, the others by the same `judge()` with the same
  contexts. Each set was read against its own articles and, as a control,
  against another question's (j against j + 7). The Hindi and Urdu answers
  were also read against the Hindi and Urdu articles whose titles they hold,
  as above. Those are often a general page (मनुष्य "human", मीटर "metre").
- Every supported or contradicted claim was read against its source sentence
  and labelled right, part or wrong.

The current code, with 95% Wilson intervals, and the audit as right/part/wrong:

| Set | Claims | Supported | Audit | Contradicted | Audit | Control: supported, contradicted |
|---|---|---|---|---|---|---|
| English, Simple English Wikipedia | 72 | 17 = 23.6% [15.3, 34.6] | 12/4/1 | 0 [0, 5.1] | | 0, 0 |
| Hindi, Simple English Wikipedia | 80 | 2 = 2.5% [0.7, 8.7] | 2/0/0 | 0 [0, 4.6] | | 0, 0 |
| Urdu, Simple English Wikipedia | 72 | 1 = 1.4% [0.2, 7.5] | 0/1/0 | 0 [0, 5.1] | | 0, 0 |
| Roman, Hindi-leaning | 85 | 9 = 10.6% [5.7, 18.9] | 5/3/1 | 1 [0.2, 6.4] | 0/0/1 | 0, 0 |
| Roman Urdu | 75 | 9 = 12.0% [6.4, 21.3] | 5/3/1 | 0 [0, 4.9] | | 0, 0 |
| Hindi, Hindi Wikipedia | 80 | 8 = 10.0% [5.2, 18.5] | 5/3/0 | 0 [0, 4.6] | | 0, 0 |
| Urdu, Urdu Wikipedia | 72 | 8 = 11.1% [5.7, 20.4] | 6/2/0 | 1 [0.2, 7.5] | 0/0/1 | 0, 0 |
| False claims, English | 4 | 0 | | 2 | 2/0/0 | 0, 0 |
| False claims, Hindi and Urdu script | 8 | 0 | | 0 | | 0, 0 |
| False claims, Roman | 8 | 1 | 0/0/1 | 2 | 2/0/0 | 0, 0 |

- **Controls:** no claim of 556 was read against another question's articles
  (404 against Simple English pages, 152 against Hindi and Urdu ones; 0
  [0, 0.7%]).
- **No false English claim was supported.** Talaqqi would keep 14 of the 30
  English answers.
- **Part** (11 of 44 findings against Simple English pages): a claim with one
  detail its source does not hold ("licensed in 1955", "dormant volcano",
  "Unhe 27 saal jail mein rakhna pada…").
- **Wrong** (5 of 44 against Simple English pages, 1 of 17 against Hindi and
  Urdu ones):
  - a **false Roman Urdu claim supported**: "Marie Curie 7 November 1867 ko
    Berlin mein paida hui thin." against "Skłodowska-Curie was born on 7
    November 1867 in Warsaw, Poland." joined with two other sentences of the
    page (entailment 0.61). It is read in Devanagari as "Marie Curie 7 November
    1867 को Berlin में पैदा हुई तीन." "Berlin" has no reading and stays in Latin
    letters. "thin" (Urdu تھیں, "were") is read as Hindi तीन ("three"), which
    also puts "three" into the search and brings "The three found radium in
    1898" into the joined premise. Written "…paida hui thi.", the claim is still
    supported, by the one sentence (0.77), while "Marie Curie was born on 7
    November 1867 in Berlin." is contradicted (0.98). A Roman claim is
    contradicted only when every writing of it is, but supported when its
    Devanagari writing is. By Talaqqi's rule the answer would be kept;
  - a **true Roman claim contradicted**: "Duniya ka pehla controlled, powered
    aur sustained hawai jahaz Orville aur Wilbur Wright (Wright Brothers) ne
    udaya tha." against the Wright brothers article's first sentence (0.74,
    both ways). Lughah reads the claim as English, so the NLI model reads it as
    written, and the agreement of writings does not apply;
  - a **true Urdu claim contradicted by Urdu Wikipedia**: "ماچو پیچو پیرو کے
    جنوبی امریکی ملک میں، اینڈیز پہاڑوں کے سلسلے میں واقع ہے۔" against "ماچو پیچو
    جنوبی امریکا میں پیرو کے کاسکو علاقے میں واقع ہے۔", the NLI model misreading
    a pair both ways;
  - **true claims supported by joined premises that do not say them**: "The
    biggest animal alive today is the blue whale." against three sentences on
    the blue whale, none of them saying it is the biggest animal (the dump
    drops the lengths: "The biggest blue whale found was  and measured
    long."), and "World Wide Web ko Tim Berners-Lee ne banaya tha." (in both
    Roman sets) against three sentences on the World Wide Web Consortium and
    his birth.

**Each design on and off**, against Simple English Wikipedia unless named
(supported, contradicted; wrong findings in the audit). "Without subjects" is
the code with every claim's context empty; a joined premise still never
contradicts:

| Set | Current code | Without subjects | Roman reading off | Qāmūs off |
|---|---|---|---|---|
| English (72) | 17, 0 (1 wrong) | 17, 0 (1 wrong) | 17, 0 (1 wrong) | 17, 0 (1 wrong) |
| Hindi (80) | 2, 0 | 2, 0 | 2, 0 | 1, 0 |
| Urdu (72) | 1, 0 | 2, 0 (1 wrong) | 1, 0 | 0, 0 |
| Roman (160) | 18, 1 (3 wrong) | 17, 1 (3 wrong) | 5, 2 (2 wrong) | 5, 2 (2 wrong) |
| False claims (20) | 1, 4 (1 wrong) | 1, 4 (1 wrong) | 0, 4 | 0, 4 |
| Hindi and Urdu, own Wikipedia (152) | 16, 1 (1 wrong) | 20, 1 (2 wrong) | | |
| Controls | 0, 0 | 0, 0 | 0, 0 | 0, 0 |

The claim each subject check took away is one that does not name its
subject, read against a sentence on something else: "یہ ان کی سب سے مشہور تصاویر
میں شمار ہوتی ہے۔" (The Starry Night) against The Potato Eaters, and
"इसे प्राचीन मिस्र के शासकों द्वारा कराए गए विशाल निर्माणों में सबसे प्रसिद्ध माना
जाता है।" (the Great Pyramid) against a sentence on the Badari culture. With
the Roman reading off, "Unhone 1789 se 1797 tak United States ke pehle
President ke roop mein kaam kiya." is contradicted by "On January 7, 1789,
Washington was elected president…"; with it on, it is supported (right).

**Against the design set**, the current code on both:

| | Design set (30 October) | Held-out (31 October) |
|---|---|---|
| English supported | 18/75 = 24.0% [15.8, 34.8] | 17/72 = 23.6% [15.3, 34.6] |
| English answers Talaqqi keeps | 14/30 | 14/30 |
| Hindi and Urdu supported by Simple English pages | 4/239 = 1.7% [0.7, 4.2] | 3/152 = 2.0% [0.7, 5.6] |
| Hindi and Urdu supported by their own Wikipedia | 38/239 = 15.9% [11.8, 21.1] | 16/152 = 10.5% [6.6, 16.4] |
| Roman supported | 26/158 = 16.5% [11.5, 23.0] | 18/160 = 11.2% [7.2, 17.1] |
| Roman supported with the Roman reading off | 8/158 | 5/160 |
| True claims contradicted (Simple English; own Wikipedia) | 0/472; 0/239 | 1/384; 1/152, both wrong |
| False claims supported | 0/40 | 1/20 (Roman Urdu) |
| False claims contradicted | English 8/20, Roman 3/20 | English 2/4, Roman 2/8, Hindi and Urdu script 0/8 |
| Findings against Simple English pages: right/part/wrong | 54/3/2 of 59 | 28/11/5 of 44 |
| Findings against another question's articles | 0 | 0 of 556 |

- **English held.** The same share of claims was supported, none was
  contradicted, and Talaqqi would keep as many answers. One support in 17 is
  wrong, against none in 18.
- **Roman fell**, from 16.5% to 11.2% supported (the intervals overlap). The
  Roman reading still gives most of it (5 → 18 claims here, 8 → 26 there), but
  here it also gave the first false claim supported in any set, and one true
  Roman claim is read as contradicted.
- **Reading a claim with its subject changed little here.** It took away one
  wrong support against Simple English pages and one against Hindi and Urdu
  ones. Against Hindi and Urdu pages it also took away three right or part
  supports (20 → 16); against Simple English pages as many claims are
  supported with it as without (39), a few of them others. On the design set,
  12 of 17 wrong findings in Hindi and Urdu were claims that do not name their
  subject; here 2 of the 8 distinct wrong findings over all arms are.
- **Across scripts** (Hindi and Urdu answers against English pages) as few
  claims were supported as on the design set, about 2%.
- **No finding against another question's articles,** in any arm, as on the
  design set.
- **Wrong findings were more common**: 5 of 44 [5.0, 24.0%] against 2 of 59
  [0.9, 11.5%]. The audit was made by a different hand from the design set's
  and marked part more often (11 of 44 against 3 of 59).
- The Hindi and Urdu answers here answer questions written in Hindi and Urdu;
  on the design set they answered English or Roman questions. Answers here hold
  fewer claims (2.4 to 2.8 each, against 4 in Hindi and Urdu there).

#### What changed after the held-out set

The set was read once, to measure; three of its findings then changed the
code, and two rules were measured and not adopted. From here on it is no
longer untouched: the next comparison needs a set of its own. Each change was
measured on the design sets and on this one; nothing else changed.

- **A code-mixed claim is contradicted only however it is written**
  (`writings`). "Duniya ka pehla controlled, powered aur sustained hawai jahaz
  Orville aur Wilbur Wright (Wright Brothers) ne udaya tha." is read by Lughah
  as English, so the rule that a Roman claim must be contradicted as written
  and in Devanagari, both ways, never applied: it was contradicted as written.
  Now every disputed claim is checked as written, as the NLI model read it, and
  in Devanagari wherever Qāmūs reads its words as Roman Hindi or Urdu; a
  capitalised word of a claim read as English is a name and stays as written
  ("Rhea" is the moon, not रिया). Held-out Roman: 1 true claim contradicted → 0.
  On the design sets and the other held-out sets no finding changed (English
  false claims contradicted: 8/20 and 2/4, as before).
- **An abbreviation ends no sentence** when the next word goes on in lower
  case (Isnad): "…at about 11:40 p.m. ship's time, and sank…" was two claims,
  the second a fragment. Held-out English: 72 claims → 71, the fragment's
  support gone and the whole claim supported; no other set changed.
- **Not adopted: a Roman claim supported only when its writings agree.** The
  false claim "Marie Curie 7 November 1867 ko Berlin mein paida hui thin." is
  supported because its Devanagari writing alone is read as entailed: Qāmūs
  reads "thin" (Urdu "were") as तीन (three) and "Marie" as मेरी, the search then
  finds "The three found radium in 1898", and with "thi" the sentence on her
  birth in Warsaw is read as entailing it. Two symmetric rules were measured:

  | Supported (true Roman claims) | Current | Not contradicted as written | Entailed as written too |
  |---|---|---|---|
  | Design set, 158 claims | 26 | 21 | 11 |
  | Held-out, 160 claims | 18 | 13 | 8 |
  | The false Marie Curie claim | supported | supported | not supported |

  The first removes wrong and right supports alike (of the design set's five,
  one wrong, one part, three right) and keeps the false claim; the second
  removes it at the cost of more than half of all Roman supports. Read as
  written, the NLI model misreads Roman Hindi (the reason it reads Devanagari
  at all), so neither writing is a witness on its own. The false claim stays a
  known failure: a Roman claim can be kept (`ilm`, Talaqqi) on one misread
  writing. What would address it is a reading that does not misspell ("thin"
  is not Hindi) and a check that a claim's names are its source's (Berlin is
  not Warsaw), both to be measured on a set not yet seen. The second was
  measured on a new set and not adopted ([Names](#names-31-october-2026)).

### Names (31 October 2026)

**Not adopted.** A check that a supporting sentence names what the claim names
removed wrong supports on the design sets, but on a fresh held-out set it
removed none, so it did not meet its bar. The code was reverted; the measured
version is commit `9b3df51`.

**The failure it was for.** "Marie Curie 7 November 1867 ko Berlin mein paida
hui thin." was supported by "Skłodowska-Curie was born on 7 November 1867 in
Warsaw, Poland." The NLI model can read a sentence about another place or
person as agreeing with a claim.

**The rule.** A source sentence or joined premise may **support** a claim only
when it holds each of the claim's names. When the most decisive premise is an
entailment that does not hold them, the claim is left unknown, as a one-way
contradiction is. No other premise takes its place, so the rule cannot make a
claim contradicted, and contradiction is not affected.

- **A claim's names, in Latin letters** (English, Roman Hindi and Urdu): runs
  of capitalised words standing apart only by spaces ("Marie Curie",
  "Skłodowska-Curie", "Doosri Jang-e-Azeem"). The first word of every sentence
  is capitalised, so a lone first word ("The", "Yeh", "Paris") is not taken
  for a name. A run that goes on past it ("Marie Curie 7 November…") is one.
- **In Devanagari or Urdu script**: the words written in Latin letters only.
  Words in the claim's own script carry no case.
- **A name in parentheses** is another writing of the name right before it
  ("Doosri Jang-e-Azeem (World War II)", "ورلڈ وائڈ ویب (WWW)"). Either
  writing is enough, and the gloss is not asked for on its own.
- **When a name is held.** A name of several words is held when the sentence
  holds any one of its words that carries more than an average word's
  information ("Curie" names Marie Curie; "The" of "The Taj Mahal" is no
  evidence). A word is held by a sentence word that also carries more than
  average information, when that word is:
  - the same word, or the same with its accents dropped ("Röntgen", "Rontgen");
  - a word with the same consonant skeleton, the one Qāmūs compares names by
    ("Mumtaz", "Mumtaaz");
  - a word that begins it or that it begins ("Olympic", "Olympics";
    "Japan", "Japanese");
  - in another script, a Qāmūs translation of it.

  A Latin-letter name is never held through a Roman reading of it into English:
  "Marie" is not मेरी ("my").
- **No runtime romaniser.** anyascii, which the Qāmūs builder romanises names
  with, is not a runtime dependency (not in `pyproject.toml`). The check used
  only Unicode decomposition and Qāmūs's shipped data.

**The bar, set before measuring.** On the design sets, with the rule against
without it:
- wrong supports fall;
- right supports fall by at most 10% of the right supports;
- no finding against another question's articles;
- no claim newly contradicted;
- no false English claim supported.

If these held, a fresh held-out set (v2) decided: false claims supported must
not rise and wrong supports must fall.

**Two versions.** The first version also counted a Devanagari or Urdu word as
a name when Qāmūs translated it into an English word that its Roman reading
reads back as the word ("जापान" → "japan"). It had no gloss rule and no
endings. It met the bar on the design sets: wrong supports 5 → 2, right 90 →
89. On the earlier held-out set (31 October, above) it removed 5 of 34 right
supports, which would fail the bar (14.7%):
- the read-back test took cognates and homographs for names: नाम ("name"),
  बार ("times", read back from "bar"), ڈرامہ ("drama", which the source spells
  ڈراما);
- glosses were asked for on their own: "(WWW)", "(IPV)";
- "Olympic" was not found in "Olympics".

That set had already been used to change code (above), and no result of v2
existed yet, so the rule was revised to the version above before v2 was
measured. On the design sets the revised rule met the bar again. On the
earlier held-out set it refused the false Marie Curie claim (false supports
1 → 0) and one part support ("…HTML-based system…"), with no right support
lost (right/part/wrong 34/16/4 → 34/15/3).

**Design sets** (the sets above; each against its own sources and, as the
control, against question j + 7's). Supported claims as right / part / wrong:

| Set | Claims | Supported, without the rule | With it | Talaqqi keeps |
|---|---|---|---|---|
| English, Simple English Wikipedia | 75 | 18 (18/0/0) | 18 (18/0/0) | 14 → 14 |
| English, web snippets | 75 | 19 (18/0/1) | 18 (18/0/0) | 14 → 13 |
| Roman, Hindi-leaning | 78 | 17 (14/1/2) | 16 (14/1/1) | 13 → 12 |
| Roman Urdu | 80 | 9 (8/1/0) | 9 (8/1/0) | 5 → 5 |
| Hindi, Simple English Wikipedia | 119 | 4 (3/1/0) | 4 (3/1/0) | |
| Urdu, Simple English Wikipedia | 120 | 0 | 0 | |
| Hindi, Hindi Wikipedia | 119 | 20 (16/2/2) | 20 (16/2/2) | |
| Urdu, Urdu Wikipedia | 120 | 18 (13/5/0) | 18 (13/5/0) | |
| False claims (English ×2 sources, Roman) | 60 | 0 | 0 | |

- **Supported:** 105 → 103 of 846 claims. Right/part/wrong went from 90/10/5
  to 90/10/3. The wrong share of supports went from 4.8% [2.1, 10.7] to 2.9%
  [1.0, 8.2].
- **Contradictions:** the same 21 claims in both arms (false sets 8, 9 and 3;
  one English true claim from snippets).
- **Controls:** no finding in either arm.
- **The two supports removed were both wrong:**
  - "Agar "bada" ka matlab kshetrafal (area) hai to duniya ka sabse bada desh
    Russia hai." against a Hindi web snippet that only asks the question;
  - "Mona Lisa ki painting Leonardo da Vinci ne banayi thi." against
    "Leonardo's full name was…".

**Held-out set v2.** It was built as the earlier held-out set was:
- 30 new questions, on none of the articles of the design sets or the
  earlier held-out set: science 6, geography 5, history 5, people 4,
  inventions 4, sport 3, nature 3 (the electron, Galileo, Tokyo, the Dead
  Sea, Napoleon, World War I, Tolstoy, dynamite, Usain Bolt, the giraffe, …);
- five wordings each, by hand;
- the production teacher's answers, with the same call and instructions.
  There were 179 calls: 150 first answers, then 22 Hindi-leaning and 7 Urdu
  Roman questions answered in Devanagari or Urdu script, asked again with
  production's Hinglish instruction. All 60 Roman answers were then in Latin
  letters. Prompt tokens: 10,770; completion tokens: 83,470. OpenRouter
  reported a cost of $0.0176;
- 20 false claims written by hand, 4 per form. 13 of them have a wrong name
  (Galileo born in Venice, dynamite invented by Thomas Edison, Beethoven born
  in Salzburg, Marconi Spanish, Genghis Khan died in Japan, …);
- the questions, the false claims and the answers were each frozen by SHA-256
  before any result was read.

Supported claims as right / part / wrong, without and with the rule (95%
Wilson intervals):

| Set | Claims | Supported, without the rule | With it | Talaqqi keeps |
|---|---|---|---|---|
| English, Simple English Wikipedia | 84 | 13 = 15.5% [9.3, 24.7] (12/1/0) | 13 (12/1/0) | 11 → 11 |
| Roman, Hindi-leaning | 86 | 11 = 12.8% [7.3, 21.5] (7/4/0) | 9 = 10.5% [5.6, 18.7] (6/3/0) | 8 → 6 |
| Roman Urdu | 92 | 10 = 10.9% [6.0, 18.9] (8/2/0) | 10 (8/2/0) | 6 → 6 |
| Hindi, Simple English Wikipedia | 86 | 3 (2/0/1) | 3 (2/0/1) | |
| Urdu, Simple English Wikipedia | 77 | 0 | 0 | |
| Hindi, Hindi Wikipedia | 86 | 8 (5/1/2) | 8 (5/1/2) | |
| Urdu, Urdu Wikipedia | 77 | 12 (10/2/0) | 12 (10/2/0) | |
| False claims, all forms | 20 | 2 = 10.0% [2.8, 30.1] | 2 | |

- **Supported:** 59 → 57. Right/part/wrong went from 44/10/5 to 43/9/5.
- **Contradictions:** the same 8 claims in both arms (7 false claims, and one
  claim of an Urdu answer against Urdu Wikipedia).
- **Controls:** no finding in either arm (0 of 608).
- **The two supports removed:**
  - "Pehla Vishwa Yuddh 28 July 1914 ko shuru hua tha, jab Austria-Hungary ne
    Serbia ke khilaf yuddh ka elaan kiya." is **right**. "Pehla Vishwa Yuddh"
    is World War I in Roman Hindi, and no English sentence writes it. The
    Roman Urdu answer that wrote "Pehli Jang-e-Azeem (World War I)" kept its
    support through the gloss;
  - "Colosseum Rome, Italy mein hai — … Piazza del Colosseo ke paas located
    hai." is **part**: the source does not name the piazza.

**Against the bar.**
- False claims supported must not rise: 2 → 2. Met.
- Wrong supports must fall: 5 → 5. **Not met.**

None of the 13 false claims with a wrong name was supported even without the
rule, so on this set the rule had nothing to catch. The five wrong supports
had no name the rule could check:
- a false direction, "Koala western Australia ke eucalyptus jungle mein rehta
  hai." against "…eastern Australia.";
- a false number, "Usain Bolt ne 100 metres 10.58 seconds mein daude hain."
  against "…9.58 seconds…";
- three Hindi claims in Devanagari, whose names are in Devanagari: "इसका
  आधिकारिक नाम बीजिंग 2008 ओलंपिक था।" (twice, against sentences that say only
  where the games were held), and "ये क्वींसलैंड, न्यू साउथ वेल्स, विक्टोरिया और
  दक्षिण ऑस्ट्रेलिया के कुछ क्षेत्रों में पाए जाते हैं।" (koalas) against a sentence
  on the borders of New South Wales.

**What it shows.**
- Over the three sets, the rule removed 3 wrong supports, 1 right and 2 part.
  All 3 wrong ones were in Latin letters (two on the design sets, the false
  Marie Curie claim on the earlier held-out set).
- A wrong name is the error that check can see, and it was rare among
  supports: no false claim with a wrong name was supported on v2.
- Roman Hindi and Urdu names of things ("Pehla Vishwa Yuddh") are not the
  source's words, so the check refuses true claims written that way.
- In Devanagari and Urdu script, Qāmūs holds too few names to say which words
  are names: भारत, पेरू and ब्राज़ील have no reading back.

Two other things were seen while measuring. Isnad cuts a claim at an initial
or an abbreviation ("Genghis Khan (born Temüjin, c.", "Electron ki khoj
J.J."), and the fragments are judged as claims.

### Word information per language: measured, not adopted (30 October 2026)

This was measured before claims were made to stand alone and before Roman
claims were read (the sections above): its "next step" below is the one
that was then built. `WORDS = "gharib"` has not been measured again since;
`ahl_dhikr.WORDS` stays `"lughah"`.

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
