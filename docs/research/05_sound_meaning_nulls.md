# 05 — Does Sound Carry Meaning? Two Honest Nulls

A recurring and deeply-held intuition is that the **sound** of Arabic roots — their letters and
articulation points (makhārij) — itself carries meaning. This is the *phonosemantics* /
sound-symbolism hypothesis. It is a real, testable claim, and it deserved the fairest possible
test rather than either dismissal or cheerleading. We tested it **two independent ways**. Both
came back **null**. That convergence is itself a strong, well-tested result.

---

## 5.1 What "null" does and does not mean

`[Inference]` A null result here means: *at the resolution our data and methods can see, sound
does not predict decodable lexical meaning.* It does **not** prove the intuition false in every
possible sense, and it says nothing about other channels of sound — prosody, rhythm, emphasis,
emotional affect, the mnemonic and aesthetic structure of recitation. Those are real and
arguably central to the Quran, but they are a **different channel** from lexical semantics, and
they were **not** tested here. So the honest statement is narrow and exact: *sound → lexical
meaning is null*.

---

## 5.2 Global test — Mantel (sound-distance vs meaning-distance)

**Pre-registration.** If sound carries meaning, roots that *sound* alike should *mean* alike.
Test the correlation between a sound-feature distance and a meaning distance across many root
pairs; significance by Mantel permutation.

**Method.** Sound distance from the 15-feature letter vectors; meaning distance from
co-occurrence embeddings (PPMI → SVD, k = 50), over N = 500 roots = 124 750 pairs.

**Result** `[Established]`:

| Test | Statistic | p | Verdict |
|---|---|---|---|
| Mantel (sound vs meaning, all pairs) | r = **+0.010** | 0.512 | null |
| Shared-biliteral pairs (roots sharing first two radicals) | mean dist +0.250 vs random +0.244 (Δ +0.006) | 0.146 | null |

Even roots sharing their first two radicals are **not** measurably closer in meaning than
random pairs. There is **no global sound → meaning law**.

![Letter math and Mantel null](letter_math.png)

---

## 5.3 Local test — the pocket-hunt (with strict correction)

A global null could still hide **local pockets** — maybe one specific letter concentrates in
one specific meaning field even if no global law exists. This is the fairest version of the
intuition, and also the most dangerous to test, because searching many (letter × field) cells
will always throw up apparent hits by chance. So the search was corrected at the family-wise
level.

**Pre-registration.** Cluster roots into K = 25 semantic fields (KMeans on meaning vectors).
For each of 36 features (28 letters + 8 makhraj/ṣifāt classes) × 25 fields, test
over-representation by a standardised hypergeometric z. Correct the **entire 900-cell search**
by **Westfall-Young maxT permutation** (B = 1000, fixed seed), FWER 0.05.

**Result** `[Established]`:

| Quantity | Value |
|---|---|
| Roots tested (freq ≥ 5) | 835 |
| Cells searched | 900 |
| Strongest single association | ث in one field, 19% vs 4% baseline, z = 4.23 |
| Its corrected p (maxT) | **0.247** |
| Null max-z (chance ceiling for 900 cells) | mean 3.91, 95th pct 5.14 |
| **Survivors at FWER 0.05** | **0** |

The strongest "pocket" you can find is exactly what 900 random cells would produce. **Nothing
survives correction.**

![Pocket hunt heatmap](pocket_hunt.png)

The heatmap is the lesson made visible: a sea of red and blue cells, several individually
striking (dark red), and **not one black box** (none beats the chance ceiling). This is a
textbook illustration of the **garden of forking paths** — individual cells dazzle;
correct for the search and they are noise.

---

## 5.4 Why two nulls are good news, not bad

`[Inference]`

1. The intuition was given the **fairest** possible hearing — global *and* local, with proper
   nulls and correction — and the result is now a **well-tested** conclusion, not a hand-wave.
2. It **converges with mainstream linguistics**: the arbitrariness of the linguistic sign
   (Saussure). The Quran's Arabic behaves like a natural language here. That is the expected,
   unsurprising outcome — and getting the expected outcome by honest method is what makes the
   project's *positive* findings trustworthy.
3. It **vindicates the Mīzān principle** the whole project runs on: do not let a surface
   pattern legislate meaning. Two nulls are the data agreeing with that discipline.
4. It tells the builder where **not** to dig. The signal does not live in phonetics. It lives
   in root + pattern + context — which is precisely Phase 2 (`06_compositional_meaning.md`).
