# 07 — Synthesis, the Mīzān Boundary, and Roadmap

## 7.1 Every claim, labelled

**`[Established]` — measured, with null/baseline/correction, reproducible**

- The Quran is in the normal range of a natural language on the linguistic-law battery
  (2 of 6 laws rejected, reported honestly).
- Frequency exponents are register- and unit-dependent (not a standalone fingerprint).
- Meccan vs Medinan is predictable from vocabulary: AUC 0.816, permutation p = 0.002; AUC 0.967
  after dropping the 6 traditionally-disputed sūras.
- Sūra ordering has a mild positive content-structure: Mantel r ≈ +0.30 (both muṣḥaf and
  chronological).
- Root embeddings recover semantic fields; نور/نار collapse at root level and separate at lemma
  level.
- Root × wazn is a real, sparse generative grid: 1 456 roots × 565 patterns, 0.45% filled,
  top-20 patterns = 47% of derived lemmas; ~65% of running text is root-based.
- Forward generation works for strong roots, fails for weak roots without special rules.
- **Sound does not carry decodable lexical meaning:** global Mantel r = +0.010 (p = 0.512) and
  local pocket-hunt 0 survivors at FWER 0.05.
- A word's translated meaning is **~38%** predictable from its root, **~43%** from root + wazn,
  held-out; same-verse neighbour-root context adds nothing in this setup (−0.008).
- A rule-based wajh-detector recovers classical sense-faces of *dīn* (96% on famous
  occurrences) and *ummah* (100%), and 98:5 is resolved by the naẓāʾir family.

**`[Inference]` — defensible interpretation, not proof**

- The model's difficulty on the 6 disputed sūras mirrors real scholarly uncertainty (without
  claiming the model should re-label them).
- Representation level (root vs lemma vs token) sets what the geometry can resolve.
- The context negative in Phase 2 reflects tool–question mismatch (aggregate regression vs
  targeted disambiguation), not the irrelevance of context.
- Meaning lives in root + pattern + context, not in phonetics.

**`[Conjecture]` — belief the mathematics neither proves nor disproves**

- That all human languages descend from a single primordial Arabic. This is a metaphysical /
  faith claim. Its one *testable* projection — that the sound of letters carries intrinsic
  meaning — was tested twice and came back null, so the project does **not** build on it. The
  broader origin claim is outside what these methods can decide, and the project does not stake
  itself on it either way.

**`[Open]` — not yet measured**

- Whether a *richer* context model (neighbour gloss-meaning vectors, or a sequence model) would
  add predictive meaning where the coarse root-bag did not.
- Whether the roots **span** a concept space (the rigorous version of "can it express
  everything") — Phase 3, not yet run.
- The weak-root generation rules (hollow / defective / hamzated / assimilated).
- Which awzān shift meaning the most (a per-pattern semantic-shift analysis).

---

## 7.2 The boundary, stated once, precisely

This project measures **structure**. Structure can be described, predicted, and quantified.
**Meaning** — what a Quranic word actually means, which face it carries, what a verse teaches —
is fixed by **transmission**: the lexica (al-Rāghib's *Mufradāt* and the dictionaries), the
tafsīr tradition, and the established interpretive principles (e.g. *tafsīr al-Qurʾān
bi'l-Qurʾān*). No correlation, embedding, cluster, or R² in this project carries the authority
to *set* meaning. A model that predicts meaning 43% of the time is describing a regularity, not
issuing a ruling.

This is not a limitation bolted on for caution. It is the **design principle** (Mīzān) that
made the work trustworthy: because structure was never allowed to legislate meaning, the
negatives (two sound-nulls, a context-null, 2 rejected laws) could be reported honestly — and
the positives (Meccan/Medinan, root+wazn meaning, the generative grid) stand on the same honest
footing.

---

## 7.3 What is genuinely new here

`[Inference]`

- An end-to-end, reproducible, **honestly-corrected** pipeline over the full corpus, where
  every claim ships with its null and its label.
- A **measured decomposition of meaning** into root / pattern / context contributions on real
  held-out data (root ~38%, +wazn +4.7 pts, +coarse-context ~0).
- The **two-front falsification** of sound-symbolism for this text (global + corrected local),
  which is rarely done with this rigour.
- A **rule-based bridge** from a polysemous word's grammatical governor to its classical wujūh
  face, validated against scholar-agreed occurrences, plus a worked *tafsīr al-Qurʾān
  bi'l-Qurʾān* resolution of a hard case (98:5).

None of these is a claim about the text's origin or inimitability. They are claims about
**measurable structure**, kept deliberately on that side of the line.

---

## 7.4 Roadmap (recommended order)

1. **Phase 3 — coverage / basis test** *(recommended next).* Do the roots **span** a concept
   space? This is the rigorous, honest form of the "it can express everything" intuition:
   measure how completely the root inventory covers a semantic space, and where the gaps are.
2. **Richer context model.** Replace the coarse same-verse root-bag with neighbour
   **gloss-meaning** vectors (or a small sequence model) and re-test, fairly, whether context
   then adds to meaning prediction. Resolves the `[Open]` question behind the Phase-2 context
   null.
3. **Weak-root generation engine.** Implement the hollow / defective / hamzated / assimilated
   rules so forward generation produces *qāʾil*, not *qāwil*, lifting generation coverage above
   the current 80%.
4. **Per-wazn semantic-shift analysis.** Quantify which patterns move meaning the most relative
   to their root — turning the clean +0.047 wazn signal into a per-pattern map.

---

## 7.5 Files and artifacts

Scripts `partA … partN` (each with a `*.json` of results and a `*.png` figure), the master word
table `quran_words.csv` (77 429 × 44), `roots_summary.csv`, `summary.json`, and this
documentation set. Seeds fixed; numbers reproducible by re-running the scripts.

> The honesty of the negatives is the warrant for the positives. That is the whole method.
