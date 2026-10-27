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
  - MIZAN does not give fatwa. The answer shows its sources and ends with:
    *"This asks for a religious ruling. MIZAN does not give fatwa; ask a
    qualified scholar (ahl al-ilm) who can weigh your situation."*
  - Scholarly bodies agree that AI may help with research but may not act as
    a mufti: the OIC Islamic Fiqh Academy (Resolution 258, 2025), Al-Azhar,
    Dar al-Ifta and the Muslim World League.

## Whom it asks

MIZAN asks its sources in this order:
1. **What it settled before** for this user (its `ilm`). These are sentences
   a source confirmed or contradicted earlier, each kept with its title, link
   and date.
2. **Outside sources:**
   - **Wikipedia**, in the answer's language (English for Roman Hindi and
     Urdu), then English. It uses MediaWiki's own search, then the article's
     plain text.
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

MIZAN identifies itself as Wikimedia's policy asks: by name, version and how
to reach its operator (`MIZAN_CONTACT`, Settings → System settings). If a site
refuses MIZAN, that source is skipped; nothing is done to get around the
refusal.

## How a claim is judged

1. The source's sentences are ranked by **BM25** against the claim. A
   sentence is kept only if it is **about what the claim is about**:
   - the claim's distinctive words are those whose information (inverse
     document frequency over MIZAN's own corpora in seven languages) is above
     the claim's mean;
   - the sentence must contain more than half of that information.

   So a page that shares only common words with the claim ("the", "largest")
   is never read against it, however the NLI model would read the pair. The
   best three kept sentences go on.
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
   - **contradicted**: the source's sentence is shown right after the claim,
     with its link, and the claim stays da'if with "*title* says otherwise".
     The model's sentence is never silently rewritten;
   - **neither**: the claim stays unknown.

If no claim could be settled, the answer ends with: *"MIZAN asked its sources
and found none that confirms these claims; they are the language model's
words, not established facts. Allahu a'lam."*

Without the NLI model, every claim stays unknown and nothing is guessed.

## It learns

- **Kept for this user.** What an outside source settled is kept in the user's
  `ilm` (in MIZAN's adaptive store, most recently used first, up to 300
  sentences). Each entry holds the claim, the source's sentence, title, link,
  date and the words of the question that asked it.
- **Asked once.** The same claim is settled from memory next time, without
  asking again.
- **Shown to Lisan.** Before Lisan writes an answer, the settled sentences
  that bear on the question are given to it as **"SETTLED BY MIZAN FROM
  SOURCES"**, so the answer starts from evidence rather than from the model's
  memory.
- **Private.** Each user's `ilm` is their own.
- **Erased with the chat.** Deleting a chat (Mahw) drops what that chat's
  requests taught.

## In the chat

Under each answer, **📚 Sources asked** lists every confirmed and
contradicted claim with its source and link. The report travels as
`result["ahl"]` → `usage.ahl`; the Isnad ledger shows the new grades.

## Setting

`MIZAN_AHL_DHIKR`: `on` (default) or `off`, in Settings → System settings.
