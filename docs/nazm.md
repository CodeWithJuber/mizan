# Nazm (نظم): answers in the form that was asked

"Exactly three sentences", "under 50 words", "no commas", "as JSON with the keys name and age", "in Urdu script": these are demands a reader checks by counting. MIZAN checks them the same way, instead of trusting the model's wording. `tadbir/nazm.py` holds the checks. The Imtihan's generation block and MIZAN's own answers both use them.

## The checks

| Kind | Holds when |
|---|---|
| `sentences`, `words`, `lines`, `paragraphs`, `bullets`, `numbered` | The count is `exact`, or at least `min` / at most `max` |
| `include`, `exclude` | Each of `words` appears / does not appear as a whole word |
| `no_char` | None of `chars` appears |
| `lowercase`, `uppercase` | The whole answer is in that case |
| `starts_with`, `ends_with` | The answer starts / ends with `text` (case aside) |
| `json` | The answer (or its fenced block) is a JSON object holding `keys` |
| `script` | Most letters are in the script `name` (arabic, devanagari, latin, tamil) |

Sentences end at `. ! ? ؟ । ۔`; words are runs of letters and digits in any script.

## In MIZAN's answers

1. **Does the request ask for a form?** Qasd's `form` facet answers this. It is a naive Bayes model like the other facets, learned from seed examples in `tadbir/data/qasd/facets.tsv` in English, Hinglish, Urdu, Hindi and Arabic: no word list, no rule. An administrator can teach it more examples (Ta'lim, model `qasd.form`).
2. **The answer is written as usual**, but not streamed: it is sent once it is final, so what streamed is what was kept.
3. **Which checks?** For an answer in words (not one of MIZAN's own recipes, whose form is its renderer's, and where "as bullet points" may describe a file), Lisan reads the checks out of the request as typed checks, each citing the request's words it rests on (`Lisan.form_checks`). MIZAN keeps only checks of a known kind whose cited words are in the request (`nazm.grounded`): a check never rests on words nobody wrote.
4. **MIZAN counts.** If a check fails, Lisan rewrites the answer once with the failures named (`Lisan.conform`). MIZAN keeps the rewrite only if:
   - more checks hold than before;
   - it brings no number that neither the answer nor the request had, so a fact is never changed to fit a form;
   - the answer quotes no Quran or hadith, since scripture is never reworded.
5. **The outcome is reported** as `result["nazm"]` → `usage.nazm`: `checks`, `held`, `failed`, `rewritten`. A rewrite is noted under Agents → Majlis → Learning (Sijill).

A request with no form costs nothing beyond the facet's posterior: no Lisan call and no held stream. In `MIZAN_ORCHESTRATION=llm` the model decides everything, Nazm included, so MIZAN does not check.
