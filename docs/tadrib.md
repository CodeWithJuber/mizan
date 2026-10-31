# Tadrib: MIZAN's own model learns while it works

"It is God who brought you out of your mothers' wombs knowing nothing, and gave you hearing and sight and minds, so that you might be thankful" ([16:78](https://quran.com/16:78)). "They said, 'May You be glorified! We have knowledge only of what You have taught us'" ([2:32](https://quran.com/2:32)). "He created man and taught him to communicate" ([55:3-4](https://quran.com/55:3-4)). (Translations: Abdel Haleem, quoted through quran.ai. Reading these ayat as a design for learning is the author's own reflection, not tafsir.)

Tadrib (تدريب, training) is how MIZAN's own models change their weights while MIZAN works, not only in a training run. Each verified piece of work becomes a **lesson** that the model learns from within seconds. The night (Nawm) consolidates the day's lessons into the version that has passed its gate. Every lesson is listed, and any lesson can be taken back: the model is then rebuilt without it.

The owner asked for this on 31 Oct 2026: MIZAN should train and learn from its teacher in real time, with no separate offline training run. That day the owner decided:

- **A check by MIZAN stands in for a person's review.** A lesson is used as soon as MIZAN's own check passes; no person reviews each one first. Lessons come only from people who switched `training: on`, and never from evaluations or WhatsApp, never from Quran, hadith or questions of deen, and never from Anthropic or OpenAI output. Every lesson is listed, and a rejected lesson is forgotten.
- **An own model takes over a task once its record shows it is ready.** On a Lisan task in a language where an anytime-valid test shows the own model to be as good as the teacher, the own model answers first. MIZAN still checks every answer, and the teacher answers when the check fails.

## Phases

1. **The reader (this page, built).** The Ruh reader ([ruh-reader.md](ruh-reader.md)) learns each consented message's language as soon as the message arrives. Before, it learned only at night, and only from messages a person had reviewed.
2. **Teacher to student (next).** Lisan's verified outputs (the wording Furqan accepted, plans Fahm validated and that then worked) train a small own generator of the same family, `ruh_reader/speaker_net.Speaker`. Per task and language, it answers once its test passes.
3. **The speaker on a GPU.** The same loop runs on the 125M speaker ([ruh-speaker.md](ruh-speaker.md)) once RunPod access exists.

## The design: two speeds, as in the brain

This follows complementary learning systems (McClelland, McNaughton & O'Reilly 1995). One store learns quickly from single experiences, and a slower one integrates them by interleaved replay during sleep, so the old is not overwritten:

- **Fast weights.** A copy of the gated version (the **slow** weights) learns each lesson at once: k steps of AdamW on a small batch made of the lesson, a quarter of lines replayed from the reader's seeds, and the rest recent lessons drawn by reservoir sampling. The learning rate is constant, and an elastic anchor pulls toward the slow weights:

  ```
  L(θ) = CE(batch; θ) + (λ/2) · Σ_i F_i · (θ_i − θ_slow,i)²
  ```

  F is the diagonal Fisher of the slow weights, estimated on the night's replay (EWC, Kirkpatrick et al. 2017). Until a night has estimated it, F = 1 for every parameter, a plain L2 pull toward θ_slow. The fast copy serves at once: its weights are swapped into the loaded reader under the reader's lock, with no reload from disk.
- **Slow weights.** At night (Nawm) the day's lessons are replayed, interleaved with older lessons and the seeds, into a challenger trained from the slow weights. The challenger replaces them only if it is not worse on the held-out seeds (`no_worse`, the same rule as before). Then the fast copy starts again from the new slow weights. Online steps never count as tests of the gate. Only a night does.
- **Prequential check.** Every incoming message is scored by both copies before it is learned (Dawid 1984: predict, then learn). One lesson in five, chosen by SHA-256, is never learned and is kept as test. On those, the paired sign test `paired_e_value(slow better, fast better)` watches the fast copy. When the e-value reaches 1/α = 20, the fast copy is reset to the slow weights. Ville's inequality bounds by α the chance that this ever happens to a fast copy that is not worse.

## A lesson for the reader

A lesson is the person's own words from a chat turn (`lughah.own_words` after `amanah.clean_message`). It is kept only when all of these hold:

- `learns()` and `trains()` are true (`training: on`, [consent.md](consent.md)), the run is not barred from training (`barred_from_training()`: evaluations, WhatsApp), and the run is not stateless.
- Amanah finds no instruction aimed at an AI in the message.
- It is not scripture (`ruh_reader.scripture`) and not text a language model wrote: the reader never learns teacher output.
- Lughah and the reader read it as the same language (`ruh_reader.agreed_language`). That agreement is MIZAN's check for this lesson, and the agreed language is its label.

Lessons are stored per person in `private/<sha256(owner)>/tadrib.sqlite3`: the digest, chat, kind, language, words, check, time and status (`learned`, `held_out`, `rejected`). Erasing a chat (Mahw) deletes its lessons. Rejecting a lesson (`DELETE /api/tadrib/lessons/{digest}`) deletes it too.

**Forgetting.** Each version records the digests of the lessons it learned. One lock covers learning, saving and forgetting, so an erased lesson can never be promoted again by a night already running. When an erased lesson is in the fast copy, the reader serves the slow weights at once, and the fast copy is rebuilt from them with the remaining lessons. When it is in the slow weights, the newest kept nightly version without it is served, and the next night re-learns the remaining lessons. The seed-only `base` holds no person's words.

## Pre-registered measurement (fixed 31 Oct 2026, before any number is computed)

`scripts/tadrib_eval.py --reader` replays a stream of messages into the online reader and into the same reader frozen, scoring each message with both before the online copy may learn it.

**Readers.** Ruh reader v2, seed 0, is the judged one. Seed 1 is reported as a replication. Each starts as installed after its gate: its weights and its development fit (κ, γ, ref, b). The fit is held fixed during the stream, as it is during a day.

**Streams.** Messages people wrote that no reader has trained, been developed or been gated on, and that are not near (`corpus.Near`) any seed, training line or slice. Roman rows are kept only where Qāmūs reads two Hindi or Urdu words (`corpus.roman_words(…, least=2)`). No model-written source is used (`corpus.MODEL_WRITTEN`). Each message goes to the dev or the test stream by SHA-256, and each stream is ordered by SHA-256.

- **Dev stream** (only for choosing the settings): MASSIVE 1.1 `dev` rows from the calibration half (v1.1's κ and b were fitted there; never a gate's), and the dev half of Roman lines from FineWeb-2 hin_Latn/urd_Latn documents no build has read. At most 300 messages per language.
- **Test stream** (read once): MASSIVE 1.1 `test` utterances of more than 8 words (the gates' short slice took only 3 to 8), BANKING77 and CLINC150 queries of more than 8 words (their 3-to-8-word queries were gated on), and the test half of the never-read FineWeb-2 Roman lines. At most 800 messages per language (en, hi, ur, ar, hi-latn).

**Learning, exactly as in production.** A message is learned only when Lughah and the online reader agree on its language, using that language. One in five, chosen by SHA-256, is held out. The dataset's label is used only to score.

**Settings, chosen on the dev stream.** The grid is k ∈ {1, 3} steps per lesson, learning rate ∈ {1e-4, 3e-4, 1e-3} and anchor λ ∈ {0, 1}, with F = 1 (no night runs during a stream). Batch 16: the lesson, 4 seed lines, 11 recent lessons (seed lines while fewer exist); 1 torch thread. The chosen setting has the lowest mean prequential log-loss on the dev stream among the settings for which the reader's **dev** reads (`current.reads.json` `dev`) at the end of the stream are `no_worse` than the frozen reader's. If none qualifies, the test stream is not run and Tadrib for the reader is not adopted.

**Bars on the test stream (seed 0, chosen setting).** All four must hold:

1. **It learns.** The reader's own posterior (P_R, as in the gate) has a lower mean log-loss against the label online than frozen, over every message in the stream, each scored before it is learned. The grouped paired bootstrap (2,000 resamples; a MASSIVE id is one group, any other message its own) gives P(not better) < 0.05.
2. **It does not forget.** On the reader's held-out reads (`current.reads.json` `held_out`), the online reader at the end of the stream is `no_worse` than the frozen one: P(worse) < 0.95 and a log-loss that is not higher.
3. **It is fast enough.** The 95th percentile of the seconds per lesson (scoring by both copies, the k steps, and the swap) is at most 2.0 on 1 torch thread in this sandbox. Memory added by the fast copy, its optimiser and the slow copy is at most 150 MB.
4. **Forgetting is exact.** A fixed tenth of the learned lessons, chosen by SHA-256, is erased, and the fast copy is rebuilt. The rebuilt weights equal, bit for bit, those of a run over the stream without those messages under the same seeds. The gap in mean per-byte loss between erased and never-learned lines is reported before and after the erasure.

The prequential log-loss and accuracy of the product P_L · P_R^b are reported, and so are the 1-in-5 held-out messages on their own and the safety check's e-values (whether it would have reset the fast copy). None of these decides. Whatever the outcome, `MIZAN_RUH_READER` stays `shadow`: the reader's online copy changes what is logged, not what Lughah decides, until the owner turns the reader on.

## Settings, routes and files

- `MIZAN_TADRIB` (`on` | `off`, default `on`; Settings → Developer → System settings): whether lessons are kept and learned. With `off`, nothing is kept, and the reader learns at night from reviewed messages as before.
- `GET /api/tadrib` (admins): status, lessons per day, prequential log-loss of both copies, the safety check, and the last night.
- `GET /api/tadrib/lessons` (the person's own, paged) and `DELETE /api/tadrib/lessons/{digest}` (reject, which forgets it).
- Files in the reader's folder (`$MIZAN_DATA_DIR/models/ruh_reader/`): `fast.pt` and `fast.json` (the fast copy and the digests it learned, written atomically every few lessons so a restart keeps the day), `fisher.pt`, and `nights/` (the last 7 nightly versions with their digests).
