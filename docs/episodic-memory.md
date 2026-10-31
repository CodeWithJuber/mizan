# Episodic memory: what MIZAN remembers without being asked

**Status (31 Oct 2026): test 1 refused, test 2 passed; kept in production in shadow** (below). The tests were pre-registered before any measurement. The owner's decision of 31 Oct: "Haan, test karke". Encode episodes from ordinary conversation, test first, then shadow.

## Why

A memory enters `memories`, and so Tadhkir's FSRS loop, only when a person asks: "remember this", Daftar, or the memory API. Production's review log was therefore empty (`docs/handoff.md`). People do not remember that way. An experience is encoded as it happens, and the hippocampus encodes what is new more strongly than what was already known (prediction error). Sleep then replays it and keeps it or lets it go (complementary learning systems: McClelland, McNaughton & O'Reilly 1995).

MIZAN has the second half: Nawm and FSRS strength in `memory/tadhkir.py`. This adds the first half, in `memory/episodic.py`.

## The policies (fixed now)

A **statement** is one turn of a person's own words.

| Policy | Keeps a statement when |
|---|---|
| `all` | always: every non-empty statement |
| `informative` | it carries a word more informative than an average running word of conversation. The conversation background (`episodic.Background`) counts how many turns of other conversations each word appears in. So "ok", "thanks" and "haan", which conversation is full of, are never kept. |
| `novel` | it is informative, **and** most of its distinctive information is not already in what was kept of this person (`ahl_dhikr.about` against the kept statements). A thing said again strengthens the old memory, as Tadhkir's repeat review does, instead of being written twice. |

There are no word lists and no thresholds. "Informative" means above the background's average word. "New" means more than half of the statement's own information.

**Why a conversation background.** General language (Lughah's corpora, which `ahl_dhikr.information` reads) rarely says "ok" or "thanks", so those words look informative there. This was found by the unit test, before any measurement. In the test the background is every turn of MSC's `train` split (sessions 2 and 3), which no measured conversation is part of. In production it would be other people's chats.

## The test

**Data.** Multi-Session Chat (MSC; Xu, Szlam & Weston 2021, "Beyond Goldfish Memory"):
- Conversations people wrote across sessions days apart.
- After each session, crowdworkers wrote what each speaker said that is worth remembering (`personas`).
- The release is `parl.ai/downloads/msc/msc_v0.1.tar.gz`, pinned by SHA-256 `e640e37cf4317cd09fc02a4cd57ef130a185f23635f4003b0cee341ffcb45e60`, the same pin as ParlAI's `build.py`.
- The release states no licence. It is used **for measurement only**: never trained on, never shipped, never quoted in the repository.

**Unit.** One speaker of one conversation in `session_4`. The statements are that speaker's turns in sessions 1–3, in order. They alternate, starting with Speaker 1, whose facts are `personas[0]`.

**Labels.** Both are computed with `ahl_dhikr.about`, the relevance test MIZAN already uses.
- **Worth remembering (S):** some fact the crowdworkers wrote for that speaker after that session holds most of its information in the statement (`about(fact, statement)`).
- **Needed later (N):** some turn of session 4, by either speaker, holds most of the statement's distinctive information (`about(statement, turn)`).

**Choosing on dev.** MSC's `valid` split, 500 conversations, is the development set. Of `informative` and `novel`, the one with the higher F1 for S is chosen. `all` is reported as the baseline.

**Judging on test.** MSC's `test` split, 501 conversations, is read once, with the chosen policy. Three bars:
1. **It keeps what is needed later better than chance.** Precision for N must exceed the share of N among all statements, which is what keeping at random at the same rate would give. The difference is resampled over conversations (10,000 bootstrap resamples, seed 0) and must have P(not better) < 0.05.
2. **It keeps most of what people thought worth remembering.** Recall for S must be at least 0.8.
3. **It keeps less than everything.** At most 60% of statements may be kept.

**Reported, deciding nothing:**
- every policy on both splits;
- precision, recall and F1 for S and N;
- the keep rate;
- seconds per statement.

**Known weakness.** The labels and the `novel` policy both use `ahl_dhikr.about`. A policy that only mirrors that function could score well without remembering well. The S labels come from people's summaries, which no policy sees, so S is the check that does not lean on MIZAN's own reading.

**What follows.**
- **If all three bars hold:** a separate change keeps the chosen policy's memories in production in shadow. That means only for `learning: on`; never pasted text, Amanah findings, scripture or stateless runs; erased by Mahw with their chat; shown in Daftar; not yet used in recall. Their need is then measured on real use with `tadhkir.need_test` before recall uses them.
- **If a bar fails:** nothing is built, and the failure is written here.

`python scripts/episodic_eval.py --msc msc_v0.1.tar.gz --split valid` (dev), then `--split test --policy <chosen>`.

## Result (31 Oct 2026): not proven

**Dev (`valid`, 500 conversations, 19,555 statements).** The conversation background holds 93,679 turns of MSC's `train` split.

| Policy | Keeps | S precision / recall / F1 | N precision (chance) / recall |
|---|---|---|---|
| `all` | 100% | 0.437 / 1.000 / 0.608 | 0.024 (0.024) / 1.000 |
| `informative` | 99.6% | 0.438 / 1.000 / **0.610** | 0.023 (0.024) / 0.930 |
| `novel` | 93.8% | 0.440 / 0.946 / 0.601 | 0.020 (0.024) / 0.773 |

So `informative` was chosen (S-F1), as registered.

**Test (`test`, 501 conversations, 18,435 statements), read once:**

| Bar | `informative` |
|---|---|
| 1 N precision above chance | 0.0200 vs 0.0215, P(not better) = 1.0: **fails** |
| 2 S recall ≥ 0.8 | 0.9999: holds |
| 3 keeps ≤ 60% | 99.5%: **fails** |

Nothing is built for production.

**What the data showed** (read on dev after the verdict, so it decides nothing):
- **People's turns in MSC nearly all carry a word that is rare in conversation.** So "informative" separates almost nothing.
- **What was needed later was mostly what had already been said.** Statements `novel` turned down, nearly all repeats of something already kept, were needed in session 4 at **8.9%** (107 of 1,208). New statements were needed at **2.0%** (365 of 18,347).
- **This is Anderson & Schooler's (1991) finding about memory and the environment.** How often a thing has come up predicts whether it is needed again. Its newness does not.
- **The idea to test next.** Every informative statement goes into a weak episodic trace at low stability. Saying it again, a repeat that Tadhkir already grades, strengthens it into long-term memory. Nawm lets the traces that were never repeated fade. The selection happens at consolidation, by repetition, not at encoding by novelty.
- **Testing it needs data no test has read.** MSC's `session_5` split has four earlier sessions and has not been read.

## Test 2: what came up again (pre-registered 31 Oct 2026, before any reading of session 5)

**The rule** (`episodic.came_up_again`). Every statement of a person stays at first a weak trace. It becomes a lasting memory when it **came up again**: some later turn MIZAN heard, by either speaker, holds most of its distinctive information (`ahl_dhikr.about`). In production this would be a Good review that raises the trace's FSRS stability, as Tadhkir's repeat review already does for a note said again. A trace that never came up again is left to fade by Nawm. There is one rule, fixed now, with nothing chosen on data.

**Data.** MSC's `session_5` (`valid` 500 and `test` 501 conversations), which no test has read. The statements are a speaker's turns in sessions 1–4. "Came up again" looks only at turns of sessions 1–4. **Needed (N)** is as in test 1: some turn of session 5 holds most of the statement's distinctive information.

**Bars, on each split** (`test` judges, `valid` is reported beside it):
1. **It keeps what is needed later better than chance.** Precision for N exceeds N's share of all statements; bootstrap over conversations, P(not better) < 0.05.
2. **It keeps less than everything.** At most 60% of statements become lasting memories.

**Reported, deciding nothing:**
- recall for N, which is what a fading trace could lose;
- precision and recall for S;
- N precision over N's prevalence (the lift).

**What follows if both bars hold on `test`:** the production change described above, in shadow, under the owner's decision. Otherwise nothing is built.

`python scripts/episodic_eval.py --msc msc_v0.1.tar.gz --session 5 --split test` (and `--split valid`).

### Test 2 result (31 Oct 2026): passed

| `session_5` | Lasting memories | N precision (chance), lift | N recall | S precision / recall |
|---|---|---|---|---|
| **`test`** (judges; 501 conversations, 24,375 statements) | **5.6%** | **0.152 (0.019), 8.1×**; P(not better) 0.0 | 0.457 | 0.398 / 0.053 |
| `valid` (reported; 500 conversations, 25,459 statements) | 6.5% | 0.128 (0.018), 7.0×; P(not better) 0.0 | 0.448 | 0.436 / 0.066 |

Both bars hold on both splits. What came up again in a conversation was needed in the next session about **eight times** as often as a statement chosen at random, and only about one statement in seventeen came up again. The first run of the script stopped before the rule was read: a `KeyError`, because the change giving each statement what was heard after it had not been applied. It was fixed and rerun. Only the `all` baseline had printed, and nothing was changed after it.

**What it means:**
- **Repetition, not newness, marks what lasts.** This holds for these people's conversations, as it does for the environment Anderson & Schooler (1991) measured.
- **Repetition alone keeps only about half of what will be needed** (N recall 0.46). That is why every statement starts as a weak trace rather than nothing: a weak trace can still be recalled while it lasts.
- **Strengthening is not people's notion of "important".** S recall is 0.05: the summaries crowdworkers wrote are mostly things said once.

**What follows** (the owner's decision: shadow first):
- Under `learning: on`, a person's statements are kept as weak episodic traces. They are never pasted text, Amanah findings, scripture or stateless runs, and Mahw erases them with their chat.
- A statement that comes up again is strengthened, by a Good review in Tadhkir.
- Nawm lets unrepeated traces fade.
- In shadow they are kept and counted but **not yet used in recall**. Real use is then measured by `tadhkir.need_test` before recall uses them.

## In production: shadow (built 31 Oct 2026)

`memory/episodic.py` keeps the traces; nothing reads them in an answer yet.

**What is kept.** After each chat turn (`BaseAgent.execute`, beside Tadrib's lesson), the person's own words of the turn become one **episode** in their own store, `private/<sha256(owner)>/episodes.sqlite3` (`hear`). The words are what `tadrib.lesson_text` leaves: pasted text is set aside. Nothing is kept when any of these holds (`gate`, the verdict in `usage.memory.episode`):

| Verdict | When |
|---|---|
| `off` | `MIZAN_EPISODIC=off` (tests set it) |
| `no consent` | a stateless run, or `learning: off` |
| `replayed` | an unattended run that replays a task the person wrote earlier: a schedule, a trigger, the queue or a watcher. Saying the same task each day is not the person speaking, and would count as coming up again. A message on Telegram, email or WhatsApp is the person speaking and is kept |
| `injection` | Amanah finds an instruction in pasted text (`amanah.scan_message`; the person's own words are never flagged) |
| `no words` | only pasted text |
| `scripture` | the words are the Quran's (`ruh_reader.scripture`) |

**Coming up again.** Before the new episode is written, it is read against the person's 500 most recent episodes. Each earlier episode whose distinctive information the new words mostly hold (`ahl_dhikr.about`, the rule test 2 measured) gets a **repeat** row, naming the chat that brought it up. An episode with a repeat is a *lasting* memory; the others stay weak traces. One difference from test 2: there either speaker's later turn counted, while here only the person's own later words do. MIZAN's reply often restates the message it answers, so counting it would make nearly every episode lasting. Whether this person-only rule still marks what is needed is what the need test on real use reads. Reading 500 episodes takes about 40 ms (measured on the cloud container, in a worker thread).

**Erasing.** Deleting a chat (Mahw) deletes its episodes and every repeat it gave an episode of another chat, so that episode is weak again. Mahw's trace search also looks in the episode store (`episodes` in the receipt).

**Seen by the person.** Daftar lists "Things you said that MIZAN keeps as episodes: N, of which M came up again (not yet used in answers)".

**Not built yet** (they matter only once recall uses the traces):
- an FSRS stability per episode, raised by a repeat as Tadhkir's Good review does;
- Nawm letting weak traces fade;
- recall from episodes. Before it, real use must show that strength says which episode is needed ("Before recall" below). The tests above first named `tadhkir.need_test` for this; simulated, it cannot tell, so a ranking test replaces it.

`MIZAN_EPISODIC` = `shadow` (default) | `off`, in Settings → Developer → System settings.

## Test 3: the production rule (pre-registered 31 Oct 2026, before `session_4/train` is read)

**Why.** Production counts a repeat only when the person's *own* later words hold most of an episode's information. Test 2 counted either speaker's later turn. The shadow store was built on the production rule, which no test has measured. Recall must not be built on it unless it holds.

**Data.** MSC's `session_4/train`: 1,001 conversations. Their session-4 turns, the N labels, have never been read. Their earlier sessions are in MSC's `session_3/train`, which test 1 read only as the background's word counts: no labels, and this rule does not use the background.

**Unit.** One speaker of one conversation. The statements are that speaker's turns in sessions 1–3, as in test 1.

**The rule** (fixed now, production's): `came_up_again(statements, own)`, where `own[i]` holds only the **same speaker's** turns after statement `i`, before session 4. Needed (N) is as in tests 1 and 2: some session-4 turn, by either speaker, holds most of the statement's distinctive information.

**Bars** (read once, on this split):
1. **Better than chance.** Precision for N exceeds N's share of all statements. The difference is bootstrapped over conversations (10,000 resamples, seed 0) and must have P(not better) < 0.05.
2. **Keeps less than everything.** At most 60% of statements come up again.

**Reported, deciding nothing:**
- N recall and the lift;
- S precision and recall;
- test 2's both-speaker rule on the same split.

**What follows.**
- **If both bars hold:** the shadow store's rule stays.
- **If a bar fails:** the failure is written here. Recall from episodes is not built on this rule; the shadow store keeps counting, which changes no answer.

`python scripts/episodic_eval.py --msc msc_v0.1.tar.gz --session 4 --split train`

### Test 3 result (31 Oct 2026): passed

`session_4/train`, 1,001 conversations, 38,504 statements, read once:

| Rule | Comes up again | N precision (chance), lift | P(not better) | N recall | S precision / recall |
|---|---|---|---|---|---|
| **production's: own later words** (judges) | **3.7%** | **0.171 (0.023), 7.4×** | 0.0 | 0.27 | 0.434 / 0.037 |
| test 2's: either speaker (reported) | 6.7% | 0.143 (0.023), 6.2× | 0.0 | 0.42 | 0.414 / 0.065 |

Both bars hold, so the shadow store's rule stays.

**What it means:**
- **The production rule is more precise and catches less.** What a person says again themselves is needed later about seven times as often as chance. But it marks only about a quarter of what will be needed, against two fifths when the other speaker's words also count.
- **Weak traces carry most of the need.** This is why every statement is kept as a weak trace rather than dropped. Whether recall should read weak traces, and how long Nawm should let them last, is what the need test on real use must answer.
- **A person's later words are only part of the picture.** In MSC the other speaker is a person. In MIZAN it is MIZAN, whose reply was left out on purpose (see "In production: shadow"). What MIZAN says back could be counted only when it is the person's own fact echoed, which no test has measured.

`python scripts/episodic_eval.py --msc msc_v0.1.tar.gz --session 4 --split train`

## Before recall: does strength say which episode is needed? (pre-registered 31 Oct 2026, before any real use is read)

Recall from episodes would rank them by FSRS retrievability R(t), counting each time an episode came up again as a Good review (Tadhkir's repeat review). Tests 2 and 3 showed on MSC that repetition marks what is needed. This rule decides whether real use in MIZAN shows the same, before recall may use it.

**Why not Tadhkir's `need_test`.** That test asks whether the need *rate* follows λ·R(u). Simulated, it cannot tell a world that does from one with a flat rate: after a few Good reviews FSRS stabilities are long, R stays near 1, and the two models predict nearly the same rate. Its log e-value was 0.3–1.1 with about 8,000 needs, where it needs 3.0. What recall needs is a *ranking*, so this rule tests the ranking.

**The rule** (`episodic.strength`, `strength_report`). Each moment some of a person's episodes come up again (a **need**) is read as a draw from that person's episodes alive then: the 500 latest, as `hear_now` reads them. The draw is compared under three laws:

| Law | P(episode k is the one needed) |
|---|---|
| strength | R_k / Σ R, R with every earlier repeat as a Good review, first written Hard (a weak trace) |
| recency (null 1) | R0_k / Σ R0, R0 as written, never strengthened |
| uniform (null 2) | 1 / n |

- **The e-value.** The product over needs of P_strength(k) / P_null(k) is a test martingale under that null: given the past, its expected factor is Σ_k P_null(k) · P_strength(k) / P_null(k) = 1. So it may be read at any time, and Ville's inequality bounds by α the chance that it ever reaches 1/α under the null.
- **Several episodes at one moment.** When one message brings up more than one episode, their ratios are averaged; an average of e-values is an e-value.
- **Pooling.** People are pooled by multiplying their e-processes.
- **Which e-value decides.** Strength must beat both nulls, so the smaller of the two e-values decides. It is valid against either null.

**Simulated before any real data** (`episodic.simulate`; 300 episodes, 360 days, λ = 0.3 a day, seeds 0 and 1):

| World the needs came from | log e vs recency | log e vs uniform | Decides (needs log e ≥ 3.0) |
|---|---|---|---|
| strength | 243, 209 | 10.4, 8.5 | yes |
| recency | −107, −140 | −30, −32 | no |
| uniform | **175, 182** | −7.4, −4.5 | no |

The uniform row is why both nulls are needed. A world where every episode is equally likely makes recency look wrong (log e 175) without strength being right.

**Decision rule** (fixed now, before real use is read). Recall from episodes is **proposed to the owner** only when the pooled e-value, the smaller of the two, reaches **1/α = 20** (α = 0.05). Until then episodes stay in shadow. The report never turns recall on by itself.

**How to read it.** `GET /api/memory/tadhkir` (admins) under `episodes`. It holds people, episodes, needs, both e-values, `e` and `strength_says_need`, and never any words. With production's traffic of 2 to 17 messages a day, expect weeks before a verdict. On 200 simulated episodes it took about 1,500 needs to decide.
