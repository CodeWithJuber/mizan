# Three of MIZAN's algorithms: their mathematics and their Quran and hadith grounding

How MIZAN remembers, what it accepts as knowledge, and when it trusts its own improvements. Each section gives the principle from the Quran or an authentic hadith, the mathematics that carries it out, and where it lives in the code.

- **Quran translations** are Saheeh International, as given by quran.com.
- **Hadith** are from Sahih al-Bukhari, quoted from the English hadith-api edition.
- **Tafsir** of al-Tabari is a model translation; Ibn Kathir is the abridged English edition.

The mathematics is borrowed from established, peer-reviewed methods. The Quran and Sunnah set what each algorithm must do; the mathematics is how it does it measurably.

Throughout, the rule is the one from MIZAN's research report: the world is learned from evidence, and only the price of an error is declared (a false-promotion rate α, a budget). That is what "no hardcoded rules" means here.

## 1. Tadhkir: memory held by being remembered (`memory/tadhkir.py`)

**Principle.**
- "The example of the person who knows the Qur'an by heart is like the owner of tied camels. If he keeps them tied, he will control them, but if he releases them, they will run away" (Bukhari 5031).
- "Keep on reciting the Qur'an because it escapes from the hearts of men faster than camel do" (Bukhari 5032).
- He ﷺ "used to repeat it thrice so that the people could understand it properly from him" (Bukhari 95).
- He took care "in preaching by selecting a suitable time, so that we might not get bored" (Bukhari 68).
- And: "As for the foam, it vanishes, [being] cast off; but as for that which benefits the people, it remains on the earth" (13:17).

So a memory is not held by being written once. It is held by being remembered; it slips away when left; repetition fixes it; and spacing the repetitions matters.

**Mathematics.** FSRS-6, the model of human recall fitted on hundreds of millions of reviews (the `fsrs` package, MIT). Each memory has:
- a stability S, the days until the chance of recalling it falls to 90%;
- a difficulty D.

The chance of recall t days after its last review is

$$R(t) = \left(1 + f\,\frac{t}{S}\right)^{-w_{20}},\qquad f = 0.9^{-1/w_{20}} - 1 .$$

Each remembrance is a review that updates S and D by FSRS's equations. A review strengthens S more when R had fallen further (the spacing effect).

| Event | Grade | Effect |
|---|---|---|
| First written | Hard / Good / Easy by the third of importance it falls in | initial S: 1.3 / 2.3 / 8.3 days |
| Recalled to answer | Good | S grows: 2.3 → 7.3 days after a 1-day gap, → 25 after a 10-day gap; nothing the same hour |
| Said again by the user | Good on the memory already held | repeated, not copied (Bukhari 95) |
| Needed but missing | Again | relearned from a lower S (`tadhkir.review` supports it and the tests check it; no part of MIZAN grades a lapse yet) |

**Where it is used.**
- **Ranking.** Recall order is relevance × R × importance.
- **Older memories.** Memories kept before Tadhkir have no FSRS state yet; they use ACT-R base-level activation, `B = ln(n/(1−d)) − d·ln L`.
- **Pruning.** Consolidation keeps pruning by ACT-R activation × importance. FSRS's power-law curve is heavy-tailed, so recall probability alone never says that a memory is foam; disuse over time does.

## 2. Isnad: two witnesses before a fact becomes knowledge (`tadbir/ahl_dhikr.py`)

**Principle.**
- "O you who have believed, if there comes to you a disobedient one with information, investigate, lest you harm a people out of ignorance" (49:6). From this, Ibn Kathir notes, the scholars of hadith refuse narrators whose reliability is unknown.
- "And bring to witness two witnesses ... so that if one of them errs, then the other can remind her" (2:282).
- "It is enough of a lie for a man to narrate everything he hears" (Muslim, Introduction 5).

**What MIZAN does.**
- **One source.** When a single source settles a claim, the claim is shown under the answer with that source (graded hasan). It is not yet given to Lisan as knowledge.
- **Two sources.** It becomes knowledge (**sahih**, given to Lisan as "SETTLED BY MIZAN FROM SOURCES") only when a second, independent site agrees and none disagrees.
- **Disagreement.** If sources disagree, the claim is **mudtarib** (inconsistent) and is never given as knowledge.
- **Seeking the second witness.** When MIZAN's ilm holds a claim from one site only, MIZAN keeps asking its outside sources within the same 20-second budget until another site speaks to it. A site is never its own second witness, so the same site is not asked again.
- **One site, one witness.** Copies of one site count once; a witness is a host, not a page.

**Mathematics.**
- **Reliability of each site.** It is a Beta posterior, starting at Beta(2, 1). It is updated with the agreement truth-discovery uses: credited when an independent site agrees with it on the same claim, debited when one disagrees. This is the jarh wa ta'dil of narrators, in numbers.
- **Weighing the sources together.** They are combined in log-odds:

$$\operatorname{logit} P(\text{true}) = \sum_h s_h\, p_h\, \operatorname{logit}(\bar t_h)$$

with:
- $s_h = +1$ if site $h$ supports the claim, $-1$ if it contradicts it;
- $p_h$ the NLI probability of that reading;
- $\bar t_h$ the site's posterior mean reliability.

A trusted, certain source therefore outweighs an untrusted, unsure one. The result is reported as `p_true` with each claim's grade (`ahl_dhikr.witnesses`).

## 3. Tajdid: improvement accepted only on evidence safe to read at any time (`tadbir/tajdid.py`, `core/adaptive.paired_e_value`)

**Principle.** 49:6 again: investigate before acting on a report. Al-Tabari reads both of its readings, *fa-tathabbatu* and *fa-tabayyanu*, as "give it respite until you know its soundness; do not hasten to accept it".

A new version of an instruction is a claim that it is better. Accepting it the moment a posterior first crosses 0.95, after looking again and again, is hastening. Such a rule promotes a version that is no better far more often than 5% of the time.

**Mathematics.**
- **Pairing.** The incumbent's and the challenger's results are paired in the order they arrive, without looking at the outcomes.
- **Why pairs.** Where a pair disagrees and neither version is better, the challenger wins with probability exactly ½, whatever their common success rate.
- **The e-value.** Over those disagreements (w challenger wins, l losses), MIZAN keeps the mixture likelihood ratio

$$E = 2^{\,w+l}\cdot 2\cdot\frac{B(w+1,\,l+1)}{B(1,1)}\cdot P\!\left(q>\tfrac12 \,\middle|\, w,l\right).$$

  This is a test supermartingale under "the challenger is not better". By Ville's inequality, $P(\sup_n E_n \ge 1/\alpha) \le \alpha$: it may be read after every result.
- **Many challengers.** The k-th challenger needs $1/\alpha_k$ with $\alpha_k = \alpha\,2^{-k}$, so across all challengers ever tried the chance of a single false promotion stays below α = 0.05.
- **Example.** The first challenger needs E ≥ 40: eight straight wins (E = 56.8).
- **Retirement.** A challenger is retired when the evidence for the incumbent reaches the same bound, or after a declared budget of 80 disagreements.
- **Checked.** In simulation, with 300 looks per run at α = 0.05, false promotions came to 3.5%.

## Tests

- **Tadhkir:** `tests/test_tadhkir.py`. Forgetting, spacing, repetition, lapse, ranking, and "said again" being repeated rather than copied.
- **Isnad:** `tests/test_ahl_dhikr.py`. One witness is not knowledge, a second site makes it sahih, a dispute is weighed by trust, a site counts once.
- **Tajdid:** `tests/test_research_learning.py`. Promotion only at the e-value bound, α spending, and the gate's error rate under repeated looks.
