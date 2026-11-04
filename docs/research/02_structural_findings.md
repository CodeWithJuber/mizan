# 02 — Structural Findings

Three results about the text as a statistical object: it obeys the normal laws of language, its
vocabulary cleanly separates the two revelation periods, and its sūra ordering is mildly
structured.

---

## 2.1 The linguistic-law battery

**Question.** Does the Quran behave like a natural language on the standard quantitative laws,
or is it an outlier?

**Method.** A six-law battery (Zipf's rank–frequency law, Heaps' vocabulary-growth law, and
four related regularities), fit on the corpus and compared against natural-language
expectations. See `zipf.png`, `analysis_laws.png`, `laws_results.json`.

**Result** `[Established]`. The text sits in the **normal range** of a natural language. Of the
six laws, **two were rejected** for the Quran — and that rejection was reported honestly rather
than smoothed over. The headline is not "the Quran is magically lawful"; it is "the Quran is a
linguistically ordinary corpus on these measures," which is the correct, unsurprising baseline
a believer and a sceptic can both accept.

**Why the honesty matters.** Many popular "miracle" analyses only ever report the laws that
fit. Reporting 2/6 rejections is the discipline that makes the *other* findings in this project
credible.

![Linguistic law battery](analysis_laws.png)

---

## 2.2 Register / baseline comparisons

**Question.** Are the Quran's frequency exponents intrinsic, or an artefact of length and
register?

**Method.** Compare the Quran against hadith, poetry, and tafsīr samples, including
**size-matched** comparisons. See `baseline_compare.png`, `baseline_sizematched.png`,
`baselines_multi.png`.

**Result** `[Established]`. The fitted exponents are **register- and unit-dependent**: they
shift with corpus and with how you slice the text. So a bare "the Quran's Zipf exponent is X"
is not a meaningful fingerprint on its own. `[Inference]` This is a caution, not a deficiency —
it tells us to compare like-with-like and to distrust single-number "signatures".

---

## 2.3 Meccan vs Medinan from vocabulary — the strongest finding

**Question.** Tradition labels each sūra Meccan or Medinan. Is that distinction *visible in the
words themselves*, beyond trivial cues like length?

**Pre-registration.** Predict the Meccan/Medinan label of a sūra from its top-root frequency
profile; baseline against length alone; significance by label permutation; report AUC.

**Method.** Per-sūra features = frequencies of the top-200 roots. Classifier evaluated by ROC
AUC. Permutation null shuffles the labels (B = 500). The Medinan set used:

```
{2,3,4,5,8,9,13,22,24,33,47,48,49,55,57,58,59,60,61,62,63,64,65,66,76,98,99,110}
```

**Results** `[Established]`:

| Model | AUC |
|---|---|
| Length only | 0.616 |
| Vocabulary (top-200 roots) | **0.816** |
| Permutation null | p = 0.002 (B = 500) |
| Vocabulary, after dropping the 6 traditionally-disputed sūras {13, 22, 55, 76, 98, 99} | **0.967** |

**Reading.** `[Established]` The revelation period leaves a strong, statistically real
fingerprint in *which roots a sūra uses* — far above what length alone explains. `[Inference]`
That the six sūras whose classification scholars themselves dispute are exactly the ones the
model finds hardest (dropping them lifts AUC from 0.82 to 0.97) is striking convergence between
a blind statistical model and centuries of human scholarly uncertainty. It does **not** mean
the model should *re-label* those sūras — it means the difficulty is real and shared.

![Meccan vs Medinan](meccan_medinan.png)

**On AUC itself.** ROC/AUC was developed for WWII radar detection (Peterson, Birdsall & Fox,
1954); AUC = the probability the model ranks a random positive above a random negative. See
`auc_explainer.png`.

---

## 2.4 Sūra-order structure (Mantel test)

**Question.** Is the *ordering* of sūras (in the muṣḥaf, and chronologically) related to their
content similarity?

**Method.** Mantel test between an order-distance matrix and a content-distance matrix over
sūras. See `surah_order.png`.

**Result** `[Established]`:

| Ordering | Mantel r |
|---|---|
| Muṣḥaf order | +0.308 |
| Chronological order | +0.303 |

`[Inference]` Both orderings carry a mild but positive association with content — neighbouring
sūras are somewhat more alike than distant ones — and the two orderings are about equally
structured. This is a weak effect, honestly a weak effect, and is reported as such.

![Surah order](surah_order.png)
