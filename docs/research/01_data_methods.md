# 01 — Data, Pipeline, and Statistical Discipline

## 1.1 Corpus

| Property | Value |
|---|---|
| Source | Quranic Arabic Corpus (QAC) morphological data |
| Reading | Ḥafṣ ʿan ʿĀṣim (Kufan) |
| Sūras | 114 |
| Āyāt | 6 236 |
| Word tokens | 77 429 |
| Distinct roots | 1 651 |
| Distinct lemmas | 4 764 (4 629 carry a root) |

Word-by-word English glosses are joined from a parallel gloss resource; an Amiri Arabic font
file is bundled for figures.

Auxiliary comparison corpora (cached, normalised identically) used in the register/baseline
experiments:

| Corpus | Tokens |
|---|---|
| Hadith | 1 372 284 |
| Classical poetry | 800 000 |
| Tafsīr (al-Ṭabarī sample) | 314 701 |

None of these corpora is in the repository: the analyzer downloads the QAC morphology from its
pinned source, the hadith pool is rebuilt from its source, and the poetry and Tafsīr samples,
whose source was not recorded, were removed (`backend/research/datasets/LICENSES.md`).

## 1.2 Normalisation (applied to every corpus)

Arabic orthography is folded to a stable consonantal skeleton before any counting:

- Strip all diacritics (ḥarakāt, shadda, sukūn, dagger alif, taṭwīl).
- Seat-fold: `ٱ أ إ آ → ا`, `ى → ي`, `ؤ → و`, `ئ → ي`, `ة → ه`; hamza (`ء`) removed.
- Keep only `U+0621–U+064A`.

This matters because Unicode stores the "same" letter several ways; without folding, two
spellings of one word look like two words.

**Collision traps that were handled explicitly** `[Established]`:

- `ummah / amah / umm` all fold to `امه`.
- `dīn / dayn` both fold to `دين`.
- Therefore target words are selected by **gloss / lemma**, never by a literal normalised
  string, so that inflected forms are captured and homographs are not merged by accident.

## 1.3 The word table — `quran_words.csv`

The pipeline emits one row per token (77 429 rows × 44 columns). This single artifact is the
substrate for every downstream experiment. Selected columns:

| Group | Columns | Notes |
|---|---|---|
| Identity | `gidx` (0..77428 linear order), `loc`, `sura`, `aya`, `word`, `form`, `translit` | Sort by `gidx` for reading order; two tokens are in the same verse iff `sura` and `aya` match. |
| Lexical | `word_en`, `root` (joined Arabic, e.g. `حمد`), `root_translit`, `root_en`, `root_en_here`, `lemma`, `pos` | `pos` ∈ {N=39 019, V=19 353, P=13 189, PN=3 911, ADJ=1 957}. |
| Morphology | `skeleton`, `norm`, `n_seg`, `n_letters` | |
| Counts | `freq_*`, `energy_info_*`, `abjad_*` | Frequency, information-content, and abjad-numeral features. |
| Neighbours | `prev_*`, `next_*`, `crosses_verse_*` | Local context fields. |
| Graph | `collocate_roots`, `collocate_en`, `root_degree`, `root_wdegree`, `root_clustering`, `root_eigcent`, `root_pagerank` | Co-occurrence-network statistics per root. |

Coverage: 50 268 rows carry a non-null root; the remaining ~27 k are particles, pronouns, and
some proper nouns that have no triliteral root.

Companion outputs: `roots_summary.csv`, `summary.json`.

## 1.4 Statistical discipline (the rules every experiment followed)

These rules exist to defeat the single biggest danger in this kind of work — the **garden of
forking paths**, where enough flexible analyses will always surface a "pattern" by chance.

1. **Pre-registration.** The hypothesis, statistic, null, and threshold were written down
   *before* computing. Each experiment file states its pre-registration.
2. **Explicit null model.** Permutation / shuffle nulls, never an eyeballed "looks
   significant". Monte-Carlo p-values use `p = (count + 1)/(n + 1)` with a fixed seed.
3. **Effect size + uncertainty**, not just a p-value.
4. **Multiple-comparison correction** whenever a search ranges over many cells — by
   Westfall-Young maxT permutation (family-wise error) where a single strongest hit is the
   question.
5. **Held-out evaluation** for any predictive claim (train/test split, fixed seed).
6. **Try to kill the claim.** Negatives are reported as first-class results, not buried.
7. **Meaning stays separate from structure.** A structural measurement is never silently
   upgraded into a claim about what the text *means*.

## 1.5 Reproducibility

Every figure and number in this documentation is produced by a script in the project (`partA`
… `partN`, plus helpers), each writing a `*.json` of its results next to its `*.png`. Seeds are
fixed (`20260614` for the main split). Re-running a script reproduces its numbers.
