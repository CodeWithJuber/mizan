# 06 — Compositional Meaning (Phase 2)

The central quantitative question of the whole project: **how much of a word's meaning is
predictable from its structure** — its root, its pattern (wazn), and its context — and how is
that predictability divided among the three?

---

## 6.1 Design

**Pre-registration.** Predict each token's translated-meaning vector from increasing feature
sets; measure the held-out R² gained at each layer; anchor with a shuffle null; check whether
context helps polysemous roots more.

- **Target Y (meaning).** Each token's English gloss → content words (stopwords stripped) →
  bag-of-words → TruncatedSVD(50) → L2-normalised. This is a **separate space** from the Arabic
  features, so predicting it is not circular. (Glosses are human translation, i.e. an external
  meaning signal.)
- **Features, nested.**
  1. **root** — one-hot identity (1 649 roots seen in content tokens).
  2. **+ wazn** — one-hot pattern (566 categories, including an `IRREG` class for weak forms).
  3. **+ context** — bag of the **other tokens' roots in the same verse**
     (nnz = 463 658), i.e. "what roots surround this word".
- **Model.** Multi-output ridge (α = 10), one fit per feature set.
- **Evaluation.** 80/20 token split, seed 20260614, variance-weighted held-out R².
- **Controls.** A shuffle null (permute Y) must give R² ≈ 0. A polysemy split (roots with ≥ 8
  tokens, by sense-spread median) tests whether context helps the ambiguous words more.
- **Scale.** N = 48 098 tokens (those with a root and a content gloss); gloss vocab = 4 739.

---

## 6.2 Results `[Established]`

| Model | Held-out R² | Increment |
|---|---|---|
| Shuffle null | **−0.033** | (sanity: ≈ 0 ✓) |
| Root only | **+0.383** | — |
| Root + wazn | **+0.430** | Δ wazn = **+0.047** |
| Root + wazn + context | **+0.422** | Δ context = **−0.008** |

Polysemy split (context gain):

| Subset | Δ context | n (test) |
|---|---|---|
| High-polysemy roots | −0.005 | 5 699 |
| Low-polysemy roots | −0.013 | 3 413 |

![Compositional meaning](compositional.png)

---

## 6.3 Reading the numbers

**1. Structure genuinely predicts meaning.** `[Established]` The root alone explains **~38%**
of the variance in a word's translated meaning, held-out, versus ~0 for the shuffle null. After
two sound-nulls, this is the project's positive payoff: meaning in this text is **largely
lexical / root-driven**, and that is now a measured fact, not an assumption.

**2. The pattern carries real meaning.** `[Established]` Adding the wazn lifts R² by a clean
**+0.047** (about five percentage points). The derivational template — active vs passive
participle, instrument noun, verbal noun, intensive — adds measurable meaning **beyond** the
root. The intuition that "the pattern also means something" is **supported** here.

**3. This context signal did not add.** `[Established]` Same-verse neighbour-root context
changed R² by **−0.008** (slightly negative), and did not help even the high-polysemy roots.
This is reported as a clean negative.

**4. Why the context negative does NOT contradict the wujūh result.** `[Inference]` In
`03_semantics_and_wujuh.md`, context **clearly** disambiguated a *specific* polysemous word
(*dīn*, including the 98:5 resolution). Here the target is the **aggregate** gloss-meaning over
all 48 098 tokens. The vast majority of words are not polysemous, so their meaning is already
pinned by root + wazn; the slice where context *could* help is small. On top of that, a
**coarse, sparse bag of same-verse roots** is a weak disambiguation signal, and ridge cannot
extract the small sense-residual from it — so it adds variance (noise) rather than signal, net
slightly negative. The lesson is about **tool–question fit**: aggregate gloss-regression is the
wrong instrument for sense disambiguation; targeted sense-classification (as done by hand for
*dīn*) is the right one. "Context does not help **in this setup**" ≠ "context is meaningless".

---

## 6.4 The Mīzān reading of Phase 2

`[Established]` measured: structure predicts **~43%** of meaning (root + wazn).

`[Inference]`/principle: prediction is **not** authority. The remaining ~57% (idiom, grammar,
genuine context, translation variance) and the very fact that a model *predicts* rather than
*defines* mean the model **describes** meaning, it does not **legislate** it. The meaning of a
word is still fixed by the lexica and the tafsīr — by transmission — not by any R². The ~57%
residual is, in effect, a built-in humility marker.

This whole phase is structural description. It says nothing about the text's truth, origin, or
theological content.
