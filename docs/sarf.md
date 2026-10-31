# Sarf: the root, pattern and meaning of an Arabic word

Sarf (صرف, morphology) reads an Arabic word's root, pattern (wazn), part of
speech and meaning from the **Quranic Arabic Corpus**. It never guesses by rule.
`POST /api/v1/root-analyze` and the chat both use it, so they always give the
same answer.

The live benchmark of 27 October 2026 found the old analyzer, a rule-based
prefix stripper, dropping the first radical: كتب → تب, كاتب → اتب, مكتوب → مكت.
It also called يوم a past-tense verb. Sarf replaces it.

## The data

Sarf downloads two files once into `$MIZAN_DATA_DIR/morphology`, each pinned by
SHA-256. A file that does not match its digest is never used. Both are GPL and
are not shipped with MIZAN:

| File | What it is |
|---|---|
| `quran-morphology.txt` | The Quranic Arabic Corpus morphology v0.4 (Kais Dukes, University of Leeds, [corpus.quran.com](https://corpus.quran.com)), in the mustafa0x fork's corrected Arabic-script edition. Every segment of every word of the Quran, with its root, lemma and tags. |
| `word-by-word.txt` | The corpus's English gloss of each of the 77,429 words, in the same order. |

Every answer names its source: *Quranic Arabic Corpus (corpus.quran.com), GPL*.

## How a word is read

1. **A word of the Quran** (14,835 distinct spellings) gets its own analysis
   from the corpus:
   - the reading it has most often, with the other readings and their shares
     (كتب: kutiba 57%, kataba 35%, kutub 9%);
   - its vowelled wazn (كَاتِب → فَاعِل, يَوْم → فَعْل).
2. **Any other word** is read by a noisy-channel model. Every probability in it
   is counted in the corpus: P(prefix), P(suffix), P(pattern) and P(root)
   with add-one smoothing, P(written letter | root letter) with 0.1 added per
   letter. MIZAN considers every split
   of the word into a prefix, a stem and a suffix the corpus has seen. For each
   split it considers every pattern the corpus has, and every root that can
   fill that pattern. The pattern is the stem with its root letters replaced by
   ف ع ل. The model also counts how the corpus writes each root letter: a weak
   و can be written ا. The score of a reading is

   ```
   log P(prefix) + log P(suffix) + log P(pattern) + log P(root)
     + Σ log P(written letter | root letter)
   ```

   - The most probable reading wins (MAP). Its probability is reported.
   - The part of speech is the one the corpus gives that pattern most often
     (مكتبة → ك-ت-ب, مَفْعِلَة, noun; مكتوب, which the Quran writes only as
     مكتوبا, → ك-ت-ب, مَفْعُول, passive participle).
3. **A root's meaning** is the three glosses the corpus gives its words most
   often, for example ك-ت-ب: "the book; a book; the scripture".

## In the chat

A question about a word's root, wazn or part of speech is answered from the
same analyzer, never from the model. Examples:
- "كاتب ka root kya hai?"
- "ما جذر كلمة يستغفرون؟"
- "What is the wazn of استغفر?"

How MIZAN recognises such a question:
- **The question.** Qasd's yes/no facet `sarf` (seeds in five languages)
  decides it. It is asked only when no other request in the message is
  decisive, so "قل هو الله أحد" stays a Quran quote.
- **The words asked about.** These are the Arabic words that are not part of
  the question's own frame. The frame is ما، جذر، كلمة and the like: the Arabic
  words that appear in more than one of the seeds.

The answer gives, for each word:
- root, wazn and part of speech, with the word's own gloss;
- what the root means in the Quran, and how many of its words there are;
- the other readings the Quran has, with their shares;
- a note when the word is not in the Quran, so the reading is the corpus's
  most probable one.

It ends naming the corpus. Isnad grades it sahih ("read by MIZAN from the
Quranic Arabic Corpus").

### Known false positives (measured 31 Oct 2026)

On production, "پاکستان کا سب سے بڑا شہر کون سا ہے؟" was answered with the root
of "ستان". This predates the deen facet's rebuild.

`scripts/facet_eval.py --sarf` measures the facet on everyday questions and
requests people wrote (MASSIVE 1.1, CC BY 4.0). These rates matter only in
Urdu and Arabic, because only Arabic-script words can become targets.

Read as about roots, held out (`test`, 300 each):

| Language | Questions | Requests |
|---|---|---|
| Urdu | 8.3% | 2.7% |
| Arabic | 2% | 2% |

The facet's own `yes` seeds are recalled 0.875 by leave-one-out.

Adding everyday Urdu and Arabic messages as `no` rows removes the false
positives (0% at every count). It also lowers that recall:

| `no` rows per language and kind | 10 | 20 | 40 | 80 |
|---|---|---|---|---|
| Recall of the `yes` seeds | 0.71 | 0.63 | 0.50 | 0.46 |

Ta'lim's check refuses every count (P(worse) 0.95–0.998). So nothing is
changed yet.

The facet needs more `yes` examples first, as the deen facet did
(`docs/fahm.md`): a held-out set of sarf questions, written before any seed,
then new seeds, then the same grid.

## The API

`POST /api/v1/root-analyze {"text": "..."}` (public, at most 2000 characters;
a longer text answers 413). It returns:
- `analysis`: one entry per Arabic word (the first 200), with these fields:
  - `surface` (the word as written), `root` and `root_letters` (ك-ت-ب);
  - `pattern` (the wazn), `pos`, `verb_form`, `lemma`;
  - `gloss` (the word's own), `meaning` (the root's);
  - `root_occurrences`, `prefix`, `suffix`, `is_stopword`;
  - `source`: `quran`, `inferred`, or `unknown` when no reading fits;
  - `probability` and `alternatives`;
- `word_count` (and `token_count`, the same number, for older clients);
- `source`: the attribution.

If the corpus cannot be read, the route answers 503 and says so.

`POST /api/v1/tokenize` is the Ruh model's tokenizer, which is a different
thing. Its `count` is the text's own units (words, or bytes for the byte-level
tokenizer, as `unit` says). The model's begin and end markers are listed in
`tokens` with their `kind`, and counted only in `count_with_markers`. "كتب" is
1 unit, 3 with the markers.

## Code

- `backend/tadbir/sarf.py`
  - `build` counts the corpus;
  - `analyze_word` reads one word;
  - `corpus()` loads and verifies the data.
- `backend/api/main.py`: `/api/v1/root-analyze`, `/api/v1/tokenize`.
- Tests: `tests/test_sarf.py`. They use a small corpus in the same format, and
  the regression set كتب / كاتب / مكتوب / مكتبة / كتاب / الكتاب, all ك-ت-ب.
