# Sarf: the root, pattern and meaning of an Arabic word

Sarf (صرف, morphology) reads an Arabic word's root, pattern (wazn), part of
speech and meaning from the **Quranic Arabic Corpus**. It never guesses by rule.
`POST /api/v1/root-analyze` uses it, so the API gives the same answer as the
corpus.

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
   - its vowelled wazn (كَاتِب → فَاعِل, مَكْتُوب → مَفْعُول, يَوْم → فَعْل).
2. **Any other word** is read by a noisy-channel model. Every probability in it
   is counted in the corpus with add-one smoothing. MIZAN considers every split
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
     (مكتبة → ك-ت-ب, مَفْعَلَة, noun).
3. **A root's meaning** is the corpus's own glosses of its most frequent words,
   for example ك-ت-ب: "the book; a book; the scripture".

## The API

`POST /api/v1/root-analyze {"text": "..."}` (public, at most 2000 characters).
It returns:
- `analysis`: one entry per Arabic word, with these fields:
  - `root` and `root_letters` (ك-ت-ب);
  - `pattern` (the wazn), `pos`, `verb_form`, `lemma`;
  - `gloss` (the word's own), `meaning` (the root's);
  - `root_occurrences`, `prefix`, `suffix`;
  - `source`: `quran` or `inferred`;
  - `probability` and `alternatives`;
- `word_count`;
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
  the regression set كتب / كاتب / مكتوب / مكتبة / كتاب, all ك-ت-ب.
