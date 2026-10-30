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
| Recalled in a run, and the answer used it | Good | S grows: 2.3 → 7.3 days after a 1-day gap, → 25 after a 10-day gap; nothing the same hour |
| Recalled in a run, not used | none | nothing changes: being near the top of a search is not remembering |
| Recalled outside a run (the memory API) | Good | the person asked for it, so it is used |
| Said again while held (R ≥ 0.9) | Good | repeated, not copied (Bukhari 95) |
| Said again after its hold fell below 0.9 | Again | it had lapsed: relearned from a lower S |

A memory is "used" when the answer holds more than half of the memory's distinctive information: the same relevance test Ahl al-Dhikr applies to a source sentence (`ahl_dhikr.about`). An agent's run holds its recalls (`dhikr.defer_reviews`) and reviews them when its answer is known (`dhikr.settle_reviews`); a delegated run's recalls are settled by the outer run. Before this, every recalled memory got a Good review whether the answer used it or not. So the few memories that ranked high for common words kept growing stronger and ranking higher: rich got richer.

**Where it is used.**
- **Ranking.** Recall order is relevance × R × importance.
- **Older memories.** Memories kept before Tadhkir have no FSRS state yet; they use ACT-R base-level activation, `B = ln(n/(1−d)) − d·ln L`.
- **Pruning.** Consolidation keeps pruning by ACT-R activation × importance. FSRS's power-law curve is heavy-tailed, so recall probability alone never says that a memory is foam; disuse over time does.

### Fitted on MIZAN's own log (`tadhkir.rest`, run by Nawm)

FSRS's default parameters were fitted on flashcard reviews. Memory differs by person and by material, so MIZAN fits FSRS on its own reviews and keeps the defaults until the fit has earned its place. For now a fit that passes its test is reported, not used: `MIZAN_TADHKIR_FIT` is `shadow` by default, and `apply` adopts it (see **Limits** below for why).

**The log.**
- **What is written.** Every review a memory gets is appended to `memory_reviews` in the memory's own database. Each row holds the memory id, agent id, grade, kind and time. The kind is `learn` (first writing), `use` (recalled and used) or `repeat` (said again). No words are written.
- **When nothing is written.** In a stateless run or under `learning: off`, as for every learned state.
- **Erasure.** A memory's rows go with it wherever it is deleted (an SQLite trigger on `memories`). Mahw counts them in its receipt as "memory reviews". If a fit in use was adopted after the erased reviews were logged, Mahw puts back FSRS's defaults ("memory strength fit"), and the next night fits again on what is kept.
- **Whose parameters.** Each memory database has its own: each user's private memory, and the shared memory of administrators and shared agents. Talaqqi's lessons are not memories and keep the defaults.

**The challenger.** A review is scored when it comes at least a whole day after the memory's previous review (FSRS's convention). The earlier half of the scored reviews, in time, fits a challenger:
- **FSRS's own optimizer**, which fits all 21 parameters by gradient descent. It is used when `fsrs[optimizer]` (torch, pandas, tqdm) is installed and the earlier half holds its mini-batch of 512 scored reviews. The base install does not include it, and neither does the production image (torch, but no pandas or tqdm).
- **Otherwise, a light maximum-likelihood fit** of six parameters, by compass search: w1–w3 (the first stability after a Hard, Good or Easy first writing), w8 (growth per use), w11 (stability after a lapse) and w20 (the curve's shape). The other parameters keep FSRS's values.

**The test.** The later half tests the challenger against the parameters in use. Its likelihood ratio

$$E = \prod_{\text{later reviews}} \frac{p_{\text{challenger}}(y)}{p_{\text{in use}}(y)} = \exp\!\big(n\,(\bar\ell_{\text{in use}} - \bar\ell_{\text{challenger}})\big)$$

has expectation at most 1 when the parameters in use are right, because the challenger saw none of these reviews. This is the split likelihood-ratio test of universal inference (Wasserman, Ramdas & Balakrishnan, PNAS 2020). So log E is the number of reviews tested times the drop in held-out log-loss.

**The bar.**
- The k-th test on a log must reach E ≥ k(k+1)/α. These spend α/(k(k+1)), which sums to α = 0.05 over every test ever made.
- The first test needs 40. After a year of nightly tests the bar is about 2.7 million (log 14.8). It is still reachable, because log E grows with the number of reviews tested.
- Tajdid halves α for each challenger instead. Here a test is made each night the log has grown, and halving would raise the bar by ln 2 every night.

**In use.**
- **Shadow by default.** Under `MIZAN_TADHKIR_FIT=shadow` (the default) a fit that reaches the bar is recorded as the night's test with `would_adopt: true` and `adopted: false`; the parameters in use do not change, and Nawm counts it as `shadow`. Under `apply` it is adopted as below. The simulations in **Measured** fit logs that the parameters in use did not grade, so they adopt either way.
- Adopted parameters are kept in `tadhkir_parameters` with their evaluation: the held-out log-loss under the parameters in use, the defaults and the fit, the number of reviews fitted on and tested on, the e-value, the bar and the date.
- From then on, every review, R(t) and ranking in that database uses them. A memory's stored S and D stay as they are, and later reviews start from them.
- Nawm (`nawm.night`) fits once a night, while no request runs and within the night's time. It fits only when the log has changed since the last test. The optimizer cannot be stopped once started, so it starts only when the pace it showed on this log says it will finish in time. The light fit stops at the deadline.
- `GET /api/memory/tadhkir` (administrators) shows the parameters in use, whether they were fitted, the test that earned them, the latest night's test and the `mode` (`shadow` or `apply`).

**Measured.** No real log exists yet, so logs were simulated (`cd backend && python -m memory.tadhkir [--light] [seeds]`). Each simulated log has:
- 400 memories over 360 days, written at uniform times and graded by a uniform importance;
- reuse after gaps drawn log-uniformly from an hour to 90 days;
- each reuse recalled with probability R(t): Good if so, else Again;
- 3,636–3,866 scored reviews, half fitted on and half tested on (1,818–1,933 tested).

"A different person" changes nine parameters from the defaults (w1–w4, w8–w11, w20): shorter first holds, less growth per use and a steeper curve. Three of these (w4, w9, w10) are outside what the light fit moves. Five seeds each; the log-loss is the mean over seeds, with the true parameters' own held-out log-loss in brackets:

| Log drawn from | Fit | Held-out log-loss: defaults → fitted (truth) | E (bar: 40) | Adopted |
|---|---|---|---|---|
| a different person | light fit | 0.2549 → 0.2425 (0.2418): 95% of the gap closed | 1.0·10⁸ – 1.2·10¹² | 5 of 5 |
| a different person | FSRS's optimizer | 0.2549 → 0.2442 (0.2418): 82% of the gap closed | 3.8·10⁶ – 1.3·10¹⁰ | 5 of 5 |
| FSRS's defaults | light fit | 0.1615 → 0.1622 (0.1615) | 0.034 – 1.7 | 0 of 5 |
| FSRS's defaults | FSRS's optimizer | 0.1615 → 0.1632 (0.1615) | 0.0075 – 0.66 | 0 of 5 |

Over 25 logs drawn from the defaults (seeds 0–24, light fit), no fit was adopted; the largest E was 2.1.

The light fit came closer to the truth than the optimizer on these logs. It moves the parameters MIZAN's grades depend on and runs until no move helps; the optimizer takes five epochs from the defaults over 21 parameters.

**Limits.**
- **The outcomes are not recall tests.** A use is always Good: a memory MIZAN failed to bring up is never observed as a failure. A repeat is graded Again only when R under the parameters in use had fallen below 0.9.
- **What a fit therefore learns.** It learns partly when MIZAN uses memories and how it grades repeats, not only how people forget. The held-out test is graded the same way, so it cannot tell these apart. This is why fits are shadow by default: a fit adopted on such a log would partly confirm its own threshold. A grade read independently of the parameters (for example, whether a memory that a later request needed was brought up at all) would make the test about forgetting, and then `apply` can be the default.
- **What is kept for later.** The `kind` column keeps first writings, uses and repeats apart, so this can be revisited.
- **Not per material.** Parameters are fitted per memory database, not per kind of material.

### Statements in time: what is said later stands above, what was said stays

"Allah eliminates what He wills or confirms, and with Him is the Mother of the Book" ([13:39](https://quran.com/13:39), Saheeh International). A person's memories change: "my city is Delhi" becomes "my city is Mumbai". An earlier statement can also still be true beside a later one: "my son is Yusuf", "my son is Ahmad". So MIZAN never deletes or hides the earlier statement. It orders the two in time.

- **One thing** (`dhikr.same_frame`). Two statements are of one thing when anti-unification over their words leaves a shared frame and one differing span in each. The frame must be at least two words, and must include a word carrying more information than an average word of general language (Lughah's corpora): "my *city* is …" counts, "I like …" does not. No span may be longer than the frame.
- **Recall** (`dhikr.in_time`). When a recalled memory has a later statement of the same thing, the later one is brought in beside it even if it ranked lower. The statements of one thing are listed latest first, each with the date it was said, and the earlier one stays. The prompt shows them as "(said 2026-10-30) My city is Mumbai.", then the earlier one.
- **Why not replace it.** A frame test cannot tell "my city" (one value) from "my son" (several). Hiding an earlier statement would lose a true one in the second case. Dating both loses nothing in either case.

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

- **Tadhkir:** `tests/test_tadhkir.py`. Forgetting, spacing, repetition, lapse, ranking, "said again" being repeated rather than copied, a run strengthening only the memory its answer used, and a lapsed memory said again being relearned.
- **Tadhkir fitted:** `tests/test_tadhkir_fit.py`. Reviews logged without words and only for the used memory, none in a stateless run or under `learning: off`, rows erased with their memory (Daftar, Mahw) and a fit made from them dropped, the α spending, a different person's log fitted and adopted, a log from the defaults not adopted, the optimizer when installed and the light fit otherwise, adopted parameters used for later reviews, a passing fit reported but not used by default (shadow), Nawm fitting within the person's choice, and the administrator-only endpoint.
- **Isnad:** `tests/test_ahl_dhikr.py`. One witness is not knowledge, a second site makes it sahih, a dispute is weighed by trust, a site counts once.
- **Tajdid:** `tests/test_research_learning.py`. Promotion only at the e-value bound, α spending, and the gate's error rate under repeated looks.
