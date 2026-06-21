# Quran Computational Linguistics — Project Documentation

A complete, honest record of a computational study of the Quranic Arabic text: what was
measured, how, what it found, and — equally important — what it did **not** find.

This documentation is governed by one rule throughout (the **Mīzān** principle):

> A pattern that a model notices can **describe** the structure of the text. It can never
> **legislate** the meaning of the text. Meaning is fixed by transmission (lexica + tafsīr),
> not by an embedding, a correlation, or an R². Every claim below is labelled so you always
> know which kind of statement you are reading.

**Epistemic labels used in every document:**

| Label | Meaning |
|---|---|
| `[Established]` | Directly measured, with a null/baseline and (where relevant) multiple-comparison correction. Reproducible. |
| `[Inference]` | A reasoned interpretation of measured results. Defensible, not proven. |
| `[Conjecture]` | A hypothesis or belief that the math neither proves nor disproves. |
| `[Open]` | An unanswered question / a measurement not yet run. |

---

## The arc of the project, in one paragraph

We built a reproducible pipeline over the full Quranic morphology corpus (114 sūras, 6 236
āyāt, 77 429 words, 1 651 roots), turned every word into a 44-column feature row, and ran a
battery of pre-registered tests. The text behaves like a **normal natural language** on
standard statistical laws. Its **vocabulary** carries a strong, real signal that separates
Meccan from Medinan sūras. Its **roots** form a generative algebra with patterns (awzān) that
carry measurable meaning. But its **sound** does **not** carry decodable lexical meaning — we
tested that two independent ways and both came back null. The payoff: meaning in this text is
**largely compositional from root + pattern**, only partly from context, and never reducible
to phonetics.

---

## Headline findings (all held-out / corrected)

| # | Finding | Number | Label |
|---|---|---|---|
| 1 | Meccan vs Medinan predictable from vocabulary | AUC 0.816 (perm p=0.002); 0.967 after dropping 6 disputed sūras | `[Established]` |
| 2 | Root predicts a word's translated meaning | held-out R² = 0.38 | `[Established]` |
| 3 | Pattern (wazn) adds meaning beyond the root | ΔR² = +0.047 | `[Established]` |
| 4 | Sound → lexical meaning, global test | Mantel r = +0.010, p = 0.512 → **null** | `[Established]` |
| 5 | Sound → lexical meaning, local test | pocket-hunt: 0 survivors at FWER 0.05 | `[Established]` |
| 6 | Same-verse neighbour-root context (this operationalisation) adds meaning | ΔR² = −0.008 → **null** | `[Established]` |
| 7 | Root × wazn is a sparse but real generative grid | 1 456 roots × 565 patterns, 0.45% filled, top-20 patterns = 47% of derived words | `[Established]` |
| 8 | Context disambiguates a *specific* polysemous word (dīn) | wajh-detector 96% on famous occurrences; 98:5 resolved by tafsīr al-Qurʾān bi'l-Qurʾān | `[Established]` (rule-based, hand-validated) |

---

## How to read this set

| File | Contents |
|---|---|
| `01_data_methods.md` | Corpus, normalisation, the 44-column word table, statistical discipline. |
| `02_structural_findings.md` | Linguistic-law battery, Meccan/Medinan classifier, sūra-order Mantel. |
| `03_semantics_and_wujuh.md` | Root embeddings, polysemy, classical *wujūh wa-naẓāʾir*, the wajh-detector, the 98:5 resolution. |
| `04_generative_algebra.md` | Phase 1: root × wazn algebra, forward word-generation, the 28-letter feature space. |
| `05_sound_meaning_nulls.md` | The two honest nulls on "sound carries meaning", and the garden-of-forking-paths lesson. |
| `06_compositional_meaning.md` | Phase 2: how much of meaning = f(root, pattern, context). |
| `07_synthesis_mizan_roadmap.md` | Every claim labelled, the boundary, what is and isn't shown, and what comes next. |

Figures referenced in the text are PNG files in this same folder.

---

## What this project is, and is not

**It is** an empirical, reproducible description of structure in a fixed Arabic text, run with
genuine statistical discipline (pre-registration, permutation nulls, multiple-comparison
correction, held-out evaluation), and reported with its negatives intact.

**It is not** a claim about the text's origin, truth, inimitability, or theological meaning.
Those questions live in a different domain (`07_synthesis_mizan_roadmap.md` states the boundary
precisely). The honesty of the negatives is the proof that the positives were not manufactured.
