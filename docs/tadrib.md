# Tadrib: MIZAN's own model learns while it works

"It is God who brought you out of your mothers' wombs knowing nothing, and gave you hearing and sight and minds, so that you might be thankful" ([16:78](https://quran.com/16:78)). "They said, 'May You be glorified! We have knowledge only of what You have taught us'" ([2:32](https://quran.com/2:32)). "He created man and taught him to communicate" ([55:3-4](https://quran.com/55:3-4)). (Translations: Abdel Haleem, quoted through quran.ai. Reading these ayat as a design for learning is the author's own reflection, not tafsir.)

Tadrib (تدريب, training) is how MIZAN's own models change their weights while MIZAN works, not only in a training run. Each verified piece of work becomes a **lesson** that the model learns from within seconds. The night (Nawm) consolidates the day's lessons into the version that has passed its gate. Every lesson is listed, and any lesson can be taken back: the model is then rebuilt without it.

The owner asked for this on 31 Oct 2026: MIZAN should train and learn from its teacher in real time, with no separate offline training run. That day the owner decided:

- **A check by MIZAN stands in for a person's review.** A lesson is used as soon as MIZAN's own check passes; no person reviews each one first. Lessons come only from people who switched `training: on`, and never from evaluations or WhatsApp, never from Quran, hadith or questions of deen, and never from Anthropic or OpenAI output. Every lesson is listed, and a rejected lesson is forgotten.
- **An own model takes over a task once its record shows it is ready.** On a Lisan task in a language where an anytime-valid test shows the own model to be as good as the teacher, the own model answers first. MIZAN still checks every answer, and the teacher answers when the check fails.

## Phases

1. **The reader (this page, built).** The Ruh reader ([ruh-reader.md](ruh-reader.md)) learns each consented message's language as soon as the message arrives. Before, it learned only at night, and only from messages a person had reviewed.
2. **Teacher to student (measured 31 Oct: the `plan_steps` student was not proven in any language).** Lisan's verified outputs train a small student of the same family, starting with `plan_steps` (mapping a message to MIZAN's actions; [below](#phase-2-teacher-to-student-plan_steps-pre-registered-31-oct-2026)). Per task and language, it answers once its test passes.
3. **The speaker on a GPU.** The same loop runs on the 125M speaker ([ruh-speaker.md](ruh-speaker.md)) once RunPod access exists.

## The design: two speeds, as in the brain

This follows complementary learning systems (McClelland, McNaughton & O'Reilly 1995). One store learns quickly from single experiences, and a slower one integrates them by interleaved replay during sleep, so the old is not overwritten:

- **Fast weights.** A copy of the gated version (the **slow** weights) learns each lesson at once: k steps of AdamW (k = 1) on a batch of 16 made of the lesson, 8 lines replayed from the reader's seeds, and the rest recent lessons drawn by reservoir sampling. The learning rate is constant, and an elastic anchor pulls toward the slow weights:

  ```
  L(θ) = CE(batch; θ) + (λ/2) · Σ_i F_i · (θ_i − θ_slow,i)²
  ```

  With F = 1 for every parameter this is a plain L2 pull toward θ_slow (L2-SP); a diagonal Fisher (EWC, Kirkpatrick et al. 2017) is supported by `online.fisher` but not used, because on this reader's family 25% replay held the old languages where EWC did not ([ruh-reader.md](ruh-reader.md)). The fast copy serves at once: its weights are swapped into the loaded reader under the reader's lock, with no reload from disk.
- **Slow weights.** At night (Nawm) the day's lessons are replayed, interleaved with older lessons and the seeds, into a challenger trained from the slow weights. The challenger replaces them only if it is not worse on the held-out seeds (`no_worse`, the same rule as before). Then the fast copy starts again from the new slow weights. Online steps never count as tests of the gate. Only a night does.
- **Prequential check.** Every incoming message is scored by both copies before it is learned (Dawid 1984: predict, then learn). One lesson in five, chosen by SHA-256, is never learned and is kept as test. On those, the paired sign test `paired_e_value(slow better, fast better)` watches the fast copy. When the e-value reaches 1/α = 20, the fast copy is reset to the slow weights. Ville's inequality bounds by α the chance that this ever happens to a fast copy that is not worse.

## A lesson for the reader

A lesson is the person's own words from a chat turn (`lughah.own_words` after `amanah.clean_message`). It is kept only when all of these hold:

- `learns()` and `trains()` are true (`training: on`, [consent.md](consent.md)), the run is not barred from training (`barred_from_training()`: evaluations, WhatsApp), and the run is not stateless.
- Amanah finds no instruction aimed at an AI in the message.
- It is not scripture (`ruh_reader.scripture`) and not text a language model wrote: the reader never learns teacher output.
- Lughah and the reader read it as the same language (`ruh_reader.agreed_language`), and no third witness says otherwise: a line both read as English is not a lesson when Qāmūs reads two Hindi or Urdu words in it written in Latin letters (`ruh_reader.contradicted`, added after the second test). That agreement is MIZAN's check for this lesson, and the agreed language is its label.

Lessons are stored per person in `private/<sha256(owner)>/tadrib.sqlite3`: the digest, chat, kind, language, words, check, time and status (`learned`, `held_out`, `rejected`). Erasing a chat (Mahw) deletes its lessons. Rejecting a lesson (`DELETE /api/tadrib/lessons/{digest}`) deletes it too.

**Forgetting.** Each version records the digests of the lessons it learned. One lock covers learning, saving and forgetting, so an erased lesson can never be promoted again by a night already running. When an erased lesson is in the fast copy, the reader serves the slow weights at once, and the fast copy is rebuilt from them with the remaining lessons. When it is in the slow weights, the newest kept nightly version without it is served, and the next night re-learns the remaining lessons. The seed-only `base` holds no person's words.

## Pre-registered measurement (fixed 31 Oct 2026, before any number is computed)

`scripts/tadrib_eval.py --reader` replays a stream of messages into the online reader and into the same reader frozen, scoring each message with both before the online copy may learn it.

**Readers.** Ruh reader v2, seed 0, is the judged one. Seed 1 is reported as a replication. Each starts as installed after its gate: its weights and its development fit (κ, γ, ref, b). The fit is held fixed during the stream, as it is during a day.

**Streams.** Messages people wrote that no reader has trained, been developed or been gated on, and that are not near (`corpus.Near`) any seed, training line or slice. Roman rows are kept only where Qāmūs reads two Hindi or Urdu words (`corpus.roman_words(…, least=2)`). No model-written source is used (`corpus.MODEL_WRITTEN`). Each message goes to the dev or the test stream by SHA-256, and each stream is ordered by SHA-256.

- **Dev stream** (only for choosing the settings): MASSIVE 1.1 `dev` rows from the calibration half (v1.1's κ and b were fitted there; never a gate's), and the dev half of Roman lines from FineWeb-2 hin_Latn/urd_Latn documents no build has read. At most 300 messages per language.
- **Test stream** (read once): MASSIVE 1.1 `test` utterances of more than 8 words (the gates' short slice took only 3 to 8), BANKING77 and CLINC150 queries of more than 8 words (their 3-to-8-word queries were gated on), and the test half of the never-read FineWeb-2 Roman lines. At most 800 messages per language (en, hi, ur, ar, hi-latn).

**Learning, exactly as in production.** A message is learned only when Lughah and the online reader agree on its language, using that language. One in five, chosen by SHA-256, is held out. The dataset's label is used only to score.

**Settings, chosen on the dev stream.** The grid is k ∈ {1, 2} steps per lesson, learning rate ∈ {1e-4, 3e-4, 1e-3} and anchor λ ∈ {0, 1}, with F = 1 (no night runs during a stream). Batch 16: the lesson, 4 seed lines, 11 recent lessons (seed lines while fewer exist); 1 torch thread. The chosen setting has the lowest mean prequential log-loss on the dev stream among the settings for which the reader's **dev** reads (`current.reads.json` `dev`) at the end of the stream are `no_worse` than the frozen reader's and whose 95th percentile of seconds per lesson on the dev stream is at most 2.0. If none qualifies, the test stream is not run and Tadrib for the reader is not adopted.

*Amended 31 Oct 2026, before any learning number was read.* A smoke run of the code on the first 40 dev messages (k = 3, learning rate 1e-3, λ = 1) took 2.46 s per lesson (median), 3.05 s at the 95th percentile, on 1 thread. It also showed that the memory counter had included Lughah and the scripture check loading for the first time. Only the timing, the exactness check (bit for bit: true) and the count of reads were looked at. So three things changed. The grid's k ∈ {1, 3} became {1, 2}, because a setting that cannot meet bar 3 cannot be adopted. The choice now also requires the speed of bar 3. And the memory is now counted after Lughah, the scripture check and one scoring pass are warm. Nothing else changed.

**Bars on the test stream (seed 0, chosen setting).** All four must hold:

1. **It learns.** The reader's own posterior (P_R, as in the gate) has a lower mean log-loss against the label online than frozen, over every message in the stream, each scored before it is learned. The grouped paired bootstrap (2,000 resamples; a MASSIVE id is one group, any other message its own) gives P(not better) < 0.05.
2. **It does not forget.** On the reader's held-out reads (`current.reads.json` `held_out`), the online reader at the end of the stream is `no_worse` than the frozen one: P(worse) < 0.95 and a log-loss that is not higher.
3. **It is fast enough.** The 95th percentile of the seconds per lesson (scoring by both copies, the k steps, and the swap) is at most 2.0 on 1 torch thread in this sandbox. Memory added by the fast copy, its optimiser and the slow copy is at most 150 MB.
4. **Forgetting is exact.** A fixed tenth of the learned lessons, chosen by SHA-256, is erased, and the fast copy is rebuilt. The rebuilt weights equal, bit for bit, those of a run over the stream without those messages under the same seeds. The gap in mean per-byte loss between erased and never-learned lines is reported before and after the erasure.

The prequential log-loss and accuracy of the product P_L · P_R^b are reported, and so are the 1-in-5 held-out messages on their own and the safety check's e-values (whether it would have reset the fast copy). None of these decides. Whatever the outcome, `MIZAN_RUH_READER` stays `shadow`: the reader's online copy changes what is logged, not what Lughah decides, until the owner turns the reader on.

## First test (v1): refused at the dev stage (31 Oct 2026)

All 12 settings were run on the dev stream (1,500 messages, about 1,200 lessons each; reader v2 seed 0). None qualified, so, as fixed above, the test stream was not run and Tadrib for the reader was not adopted. `MIZAN_TADRIB` stays `off`.

| k | lr | λ | Prequential log-loss, frozen → online | P(not better) | Held-out lessons | Seeds' dev reads, log-loss | p95 s |
|---|---|---|---|---|---|---|---|
| 1 | 1e-4 | 0 | 0.2335 → 0.1655 | 0.006 | 0.180 → 0.165 | 0.0045 → 0.0052 | 1.08 |
| 2 | 1e-4 | 0 | 0.2335 → 0.1555 | 0.007 | 0.180 → 0.185 | 0.0045 → 0.0139 | 2.01 |
| 1 | 3e-4 | 0 | 0.2335 → 0.1776 | 0.051 | 0.180 → 0.189 | 0.0045 → 0.0119 | 1.10 |
| 1 | 3e-4 | 1 | 0.2335 → 0.2280 | 0.013 | 0.180 → 0.177 | 0.0045 → 0.0045 (higher in the 5th digit) | 1.17 |
| 2 | 1e-4 | 1 | 0.2335 → 0.2302 | 0.002 | 0.180 → 0.180 | 0.0045 → 0.0045 (higher in the 5th digit) | 2.13 |
| 1 | 1e-3 | 0 | 0.2335 → 0.2909 | 0.943 | 0.180 → 0.309 | 0.0045 → 0.0048 | 1.12 |
| 2 | 1e-3 | 0 | 0.2335 → 0.5358 | 1.000 | 0.180 → 0.353 | 0.0045 → 0.0137 | 2.07 |

(Five other settings lie between these.) What it showed:
- **The reader learns from the stream.** With no anchor and a small learning rate, the prequential log-loss fell by 29%, and on the one-in-five lessons it never learned by 8%. The product's accuracy rose from 98.53% to 98.80% (k = 2: 99.00%).
- **The labels it learns are right.** Where Lughah and the reader agreed, they matched the dataset's label 98.7 to 99.3% of the time.
- **Without an anchor it forgets a little; with λ = 1 it hardly forgets and hardly learns.** The rule "log-loss not higher at all" failed every setting, the anchored ones by a change in the fifth decimal place.
- **Memory was over the bar** (+400 to +750 MB). The cause was found: one forward pass of 16 rows held about 260 MB of activations, and glibc kept the high-water mark. The online learner now accumulates the same gradient over micro-batches of 4 rows and returns freed memory after each lesson (`malloc_trim`): +121 MB with the reader loaded (60 lessons). The tests check that the micro-batched step equals the whole batch's.
- **Speed:** one step per lesson took 1.1 to 1.2 s at the 95th percentile; two steps, 2.0 to 2.2 s.

## Second test (v2), fixed 31 Oct 2026 after v1's dev results, before the test stream is read

The test stream (3,514 messages) has still not been read. What changes, and why:

- **The forgetting rule** becomes *no evidence of being worse* on the seeds' reads: Ta'lim's paired bootstrap for accuracy (P(worse) < 0.95, as in `no_worse`) and a grouped paired bootstrap for the log-loss (P(mean rise > 0) < 0.95). The nightly promotion keeps the strict `no_worse`: a fast copy is reset to the slow weights each night, and the live sign test resets it sooner if held-out lessons read worse.
- **The grid** keeps one step per lesson (two cannot meet the speed bar) and looks between λ = 0 and λ = 1: learning rate ∈ {1e-4, 3e-4}, λ ∈ {0.03, 0.1, 0.3, 1}, seed lines per batch ∈ {4, 8} (the rest of the 16 recent lessons), micro-batches of 4.
- **The choice** is the lowest dev prequential log-loss among the settings with no evidence of forgetting on the seeds' **dev** reads, a p95 of at most 2.0 s and at most 150 MB added. If none qualifies, the test stream is still not run.
- **The bars on the test stream** (seed 0; seed 1 reported): 1 and 4 as in v1; 2 is the rule above on the seeds' **held-out** reads; 3 as in v1.

`scripts/tadrib_eval.py --grid-v2 WORK`, then `--test-v2 WORK`.

## Second test (v2): refused at the test stage (31 Oct 2026)

On the dev stream, 7 of the 16 settings qualified. The choice was one step per lesson, learning rate 1e-4, λ = 0.03 and 8 seed lines per batch. Its dev results:
- prequential log-loss 0.2335 → 0.2103 (P(not better) 0.018);
- seeds' dev reads 0.00446 → 0.00445;
- 0.82 s per lesson at the 95th percentile;
- +147 MB.

The test stream was then read once. Bar 1 failed for both readers, so Tadrib for the reader was not adopted and `MIZAN_TADRIB` stays `off`.

| Bar | Seed 0 (judged) | Seed 1 (replication) |
|---|---|---|
| 1 it learns: prequential log-loss, frozen → online | 0.2643 → 0.2711, P(not better) 0.893: **fails** | 0.1867 → 0.2238, P(not better) 1.000 |
| 2 no evidence worse on the seeds' held-out reads | 0.0632 → 0.0542 (P(worse) 0.035, P(loss higher) 0.003): holds | 0.0612 → 0.0591: holds |
| 3 speed and memory | p95 1.13 s, +144 MB: holds | p95 1.11 s, +144 MB |
| 4 erasure exact | 285 of 2,780 lessons erased, rebuilt bit for bit: holds | — |

By language (seed 0), the loss fell on English (0.00003 → 0.000003) and Urdu, and rose on Roman Hindi/Urdu (1.160 → 1.189; seed 1: 0.820 → 0.983). Roman Hindi/Urdu carries almost all of the stream's loss. The held-out lessons read worse as well (0.246 → 0.250). The product's accuracy hardly moved (98.72% → 98.78%).

**Why (looked at after the verdict, so it decides nothing).** We read the test stream again with the frozen readers. Of its 800 Roman Hindi/Urdu lines, Lughah and the reader **both** read 33 to 40 as English. The dev stream had 14 to 15 of 300. Each such line became a lesson labelled English, so the reader learned to read Roman Hindi as English. Its few hard lines dominate the mean, and they got harder. A check made of two readers that make the same mistake agrees on that mistake: agreement alone is not enough. The lesson labels were right 98.9 to 99.0% of the time, and the 1% that were wrong were enough to undo the learning.

## Third test (v3), fixed 31 Oct 2026 after v2's verdict, before any reader reads its stream

What changes, and why:

- **A third witness.** A line that Lughah and the reader both read as English is not a lesson when Qāmūs reads two Hindi or Urdu words in it written in Latin letters (`ruh_reader.contradicted`; two is the count the Roman slices already use, `corpus.V2_LEAST`, not tuned here). A word English writes the same way is no witness for either side: Qāmūs reads "meeting" and "alarm" as मीटिंग and अलार्म, and plain English requests would otherwise be turned down (the tests showed it before any stream was read). On v2's already-read streams this witness turns down 22 of 800 English lines (mostly names such as "el paso" and "carlos") and none of the dev stream's 300: at that cost they are left unlearned, never mislabelled. A lesson is kept only when no witness says otherwise. This holds in production too: in `ruh_reader.agreed_language` (and so at night) and in Tadrib's trainer. "Leave what makes you in doubt for what does not make you in doubt" (Jami' at-Tirmidhi 2518, graded sahih): a line the witnesses disagree on is left unlearned.
- **No new choice.** The setting is v2's: one step, learning rate 1e-4, λ = 0.03, 8 seed lines (now `online.Setting`'s defaults). No dev stream and no grid are run.
- **A fresh test stream whose labels are not Qāmūs's.** v2's Roman lines were kept only where Qāmūs read two Hindi or Urdu words, so on them the new witness would remove the wrong lessons by construction. The third stream (`--stream-v3`) is therefore built from text that no build, gate or earlier Tadrib stream read and that is not near any of it (`corpus.Near`). Each line is labelled by its dataset:
  - English, Hindi, Urdu and Arabic: Tatoeba sentences of at least 3 words that no reader has trained or been measured on (CC BY 2.0 FR).
  - Roman Hindi/Urdu: half Dakshina's romanized Wikipedia sentences (CC BY-SA 4.0) and half PHINC's code-mixed tweets (CC BY 4.0), with no Qāmūs filter.
  - At most 800 lines per language, ordered by SHA-256. Built: 3,262 lines (SHA-256 `d36381a5…`): English, Hindi and Arabic 800 each, Roman Hindi/Urdu 400 + 400, and Urdu only 62, because Tatoeba holds few Urdu sentences no reader has seen.
- **Bars** (seed 0 judged, seed 1 reported; both read the stream at the same time): as in v2, except that bar 1 needs P(not better) < 0.025. This is the second test stream to ask "does it learn", so α = 0.05 is split between the two attempts (Bonferroni).

If all four bars hold, `MIZAN_TADRIB` defaults to `on`. If not, it stays `off`.

`scripts/tadrib_eval.py --stream-v3 WORK`, then `--test-v3 WORK`.

## Third test (v3): refused at the test stage (31 Oct 2026)

The stream was read once, by both readers at the same time. Bars 1 and 3 failed, so Tadrib for the reader was not adopted and `MIZAN_TADRIB` stays `off`.

| Bar | Seed 0 (judged) | Seed 1 (replication) |
|---|---|---|
| 1 it learns: prequential log-loss, frozen → online | 0.2677 → 0.2977, P(not better) 1.000: **fails** | 0.1845 → 0.2169, P(not better) 1.000 |
| 2 no evidence worse on the seeds' held-out reads | 0.0632 → 0.0620 (P(worse) 0.46): holds | 0.0612 → 0.0642 (P(worse) 0.55, P(loss higher) 0.91): no evidence worse |
| 3 speed and memory | p95 0.81 s, but +188 MB: **fails** | p95 0.82 s, +187 MB |
| 4 erasure exact | 244 of 2,552 lessons erased, rebuilt bit for bit: holds | — |

- **The third witness worked as meant.** Of the 800 Roman Hindi/Urdu lines, 22 were still learned as English. In v2 the number was 33 to 40, out of a stream that held more such lines.
- **Accuracy did not move.** The product was 98.87% → 98.87%, and the lesson labels matched the dataset 99.2% of the time.
- **Memory rose because the lines are longer.** Tatoeba's Arabic sentences and Dakshina's Wikipedia sentences run longer than v2's stream, and a longer line holds more activations in one micro-batch.

**What the loss was made of (looked at after the verdict, so it decides nothing).** The frozen reader read 35 Roman lines as English with 5 to 55 nats of loss each. Those 35 lines hold 864 of the stream's 871 nats of Roman loss. All of them are PHINC tweets, and reading them shows they are written in English with no Hindi word: "who else is excited to see the boys on startalk tomorrow ? ? ?". PHINC labels every tweet as code-mixed. On these lines the online reader grew surer of the right answer, English, and the dataset's label scored that as worse.

Without PHINC (2,860 lines), the change is within noise either way:

| Seed | All lines without PHINC | Dakshina alone |
|---|---|---|
| 0 | 0.00251 → 0.00234 | 0.0137 → 0.0115 |
| 1 | 0.00169 → 0.00197 | 0.0017 → 0.0029 |

**What the three tests show.**
- **Clean text leaves almost nothing to learn.** Where labels are clean, the reader's loss was already about 0.002 nats a line.
- **Agreement can only confirm what the reader already reads.** It cannot see the lines both readers get wrong, and when they agree on a mistake it teaches that mistake.
- **A learner needs a teacher for what it does not know** ("We have knowledge only of what You have taught us", [2:32](https://quran.com/2:32)). Learning by its own agreement gives the reader no measurable gain. So the reader's online learning stops here: the code stays, and `MIZAN_TADRIB` stays `off`.
- **What does carry a teacher's signal is phase 2.** There, verified Lisan outputs teach a student. For the reader, the same idea means learning only the lines its witnesses disagree on, labelled by someone who knows: the person, or a hand-labelled set.
- **A fourth test would need two things first.** Roman test lines must be labelled by hand (as v2's gate was), not by a dataset that labels English tweets as code-mixed. And the memory bound must hold for long lines.

## Phase 2: teacher to student, `plan_steps` (pre-registered 31 Oct 2026)

The owner chose this after the reader's third test. What the reader showed is that agreement with itself is no teacher. Here the teacher is the language model MIZAN already asks, and only what MIZAN's own checks pass is learned.

**The task.** `Lisan.plan_steps` maps a message to MIZAN's actions as one JSON object, `{"steps": [...]}`. It is asked when Fahm cannot build the request by itself. The teacher's answer is a **lesson** (`tadrib.plans.target`) only when every step passes `fahm.validate_parsed`, or when it is a lone `converse`. The lesson is the plan in a fixed form: each action with only the fields its schema has, and the words it covers only when there are several actions.

Three kinds of plan are never lessons:
- a plan with a Quran or hadith step;
- a plan for a message Qasd reads as about the deen or a ruling (`plans.about_the_deen`);
- a plan that mixes `converse` with actions.

**The teacher.** `deepseek/deepseek-chat-v3-0324`, the model production uses. It is MIT-licensed (its card was read 31 Oct 2026, `tadrib.licence`). Anthropic and OpenAI output never teaches (`licence.forbidden`), and the licence table is the one `mizan_reply.data` enforces. It is asked exactly as Tadbir asks it (`Lisan.plan_steps`, with no earlier messages), through OpenRouter, with spending capped at $3. Each answer is kept with its model id (`Lisan.exchange`).

**The messages.** MASSIVE 1.1 `train` utterances (CC BY 4.0, written by people) in English, Hindi and Urdu: at most 1,700 per language, in SHA-256 order. Messages Qasd reads as about the deen are skipped before the teacher is asked, since no lesson can come from them. That facet reads 63–71% of these everyday Hindi/Urdu requests as about the deen; this is a separate bug, recorded and not fixed here.

**The teacher against itself.** The first 200 lessons are asked a second time. For each language, `p0` is the share of second answers that `agree` with the first. A student that reaches `p0` agrees with the teacher as often as the teacher agrees with itself.

**The student** (`tadrib.student.Student`): the reader's network (`ruh_reader.net.Reader`, 3.48M parameters), with a context of 544 positions, started from Ruh reader v2 seed 0.
- A lesson is `[TASK] message [SEP] answer [END]`, and only the answer and its end are learned.
- Each lesson takes 2 AdamW steps (learning rate 1e-3) on the lesson plus 7 recent lessons replayed (reservoir sampling), in micro-batches of 4, on 2 torch threads.
- Everything is seeded by the lesson's digest.
- This setting is fixed now. A smoke run on the first 11 lessons checked only the mechanics and the speed (learning 0.5 s, answering 0.1 s). There is no dev stream and no grid.

**Agreement** (`plans.agree`).
- *Agree:* the student's answer parses, every step passes MIZAN's checks, and it has the teacher's actions in the teacher's order with the same structured values: the arithmetic's value, the link, the schedule, the project kind, the code language.
- *Same word for word:* free-text fields (a tool `need`, a search `query`) are compared too (`plans.same`). This is reported, not judged.

**The stream.** Lessons go in SHA-256 order. For each lesson:
1. The student answers first (greedy), before it has seen the lesson.
2. The answer is scored by `agree`.
3. The language's betting e-process (`core.adaptive.BettingEProcess(p0)`) is updated. Its stakes follow aGRAPA, computed from exponentially weighted estimates with a half-life of 50 outcomes, so that a student who improves is bet on soon, and they are capped at 0.5/p0.
4. The student learns the lesson.

Under "the student agrees with the teacher at most p0 of the time", the e-process is a nonnegative supermartingale. By Ville's inequality, the chance it ever reaches 20 is at most 5%, however often it is read.

**Bars, per language** (the owner's rule: per task and language):
1. **Proven.** The language's e-process reaches 20 within the stream.
2. **Fast enough.** On 2 threads, answering takes at most 1.0 s at the 95th percentile, and learning a lesson at most 2.0 s.
3. **Forgetting is exact.** Over the first 300 lessons, a student that learned them all and then forgot one in ten (rebuilt without them) equals, bit for bit, one that never learned those.

Also reported, deciding nothing:
- agreement in the first and last thirds;
- where each language's e-process crossed 20;
- answers that pass MIZAN's checks but differ from the teacher (these would be served wrongly);
- word-for-word agreement;
- the cost.

**What follows.** For a language where all three bars hold, phase 2b is built: the student answers `plan_steps` first in production, behind a setting, shadow first. MIZAN checks every answer, and the teacher answers when the check fails; that answer becomes a lesson. The student's words in free-text fields are used only where they are copied from the message. For a language where the bars do not hold, the student is not used.

`scripts/tadrib_lisan.py --lessons WORK`, `--again WORK`, then `--run WORK --weights reader-seed0.pt --erase`.

### Phase 2 result (31 Oct 2026): not proven in any language

**The teacher.** It was asked 5,100 times and 4,485 of its plans were lessons: English 1,455, Hindi 1,481, Urdu 1,549. All of them were served by `deepseek/deepseek-chat-v3-0324`, at $1.35 including the second asking. Its agreement with itself (`p0`) was English 0.877, Hindi 0.783 and Urdu 0.800, each on about 65 messages. Its plans were mostly `converse` (2,367) and `use_tool` (1,708), then `watch` (198), `web_search` (138), `compute` (41) and `build_and_run` (22).

| Bar | English | Hindi | Urdu |
|---|---|---|---|
| 1 proven (e-process reaches 20) | e = 1.0: **no** | e = 1.0: **no** | e = 1.0: **no** |
| Agreement in the last third | 0.581 (p0 0.877) | 0.546 (p0 0.783) | 0.636 (p0 0.800) |
| 2 speed (2 threads) | answer p95 0.22 s, learn p95 0.72 s: holds | same | same |
| 3 exact forgetting | 19 of 300 forgotten, bit for bit: holds | same | same |

No language was proven, so phase 2b is not built and the teacher still answers `plan_steps`.

**What the stream showed** (read after the verdict, so it decides nothing):
- **The form is learned at once, the decision is not.** Answers passing MIZAN's checks rose from 78% to 99% within 1,000 lessons. Agreement rose from 40% to about 58–61% by lesson 2,500 and then stayed there.
- **Different but valid.** About 40% of the student's answers were valid plans that differed from the teacher's. Served, they would have been the wrong actions.
- **Agreement by kind of plan** (last third): `converse` 0.78 and `use_tool` 0.47. Every `watch`, `web_search`, `compute` and `build_and_run` lesson disagreed (62, 44, 17 and 9 of them). The student learned the common choice and not the rare ones.
- **Answering only when sure would not have helped.** Its most confident 10% of answers agreed 80% of the time, which is still below English's p0.

**What it says.** A 3.48M-parameter byte model learns the shape of a plan from a few hundred lessons. Within 4,500 lessons it does not learn the teacher's choice of action, and that choice is a judgement about meaning that the teacher itself repeats only 78–88% of the time. Learning from a teacher works where the student can hold the knowledge: the learning, forgetting and speed machinery all held. Two roads remain:
- a larger student (phase 3, the 125M speaker on a GPU);
- splitting the task, so that the choice of action is learned as a classification from the teacher's verified labels (as Qasd already learns from verified requests) and only the copying of the user's words is generated.


## Settings, routes and files

- `MIZAN_TADRIB` (`on` | `off`; Settings → Developer → System settings): whether lessons are kept and learned. With `off`, nothing is kept, and the reader learns at night from reviewed messages as before. The default is `off`: three pre-registered tests refused it (above).
- `GET /api/tadrib` (admins): status, lessons per day, prequential log-loss of both copies, the safety check, and the last night.
- `GET /api/tadrib/lessons` (the person's own, paged) and `DELETE /api/tadrib/lessons/{digest}` (reject, which forgets it).
- Files in the reader's folder (`$MIZAN_DATA_DIR/models/ruh_reader/`): `fast.pt` and `fast.json` (the fast copy and the digests it learned, written atomically every few lessons so a restart keeps the day), and `nights/` (the last 7 replaced versions with their digests).
