# Episodic memory: what MIZAN remembers without being asked

**Status: pre-registered 31 Oct 2026, before any measurement.** The owner's decision of 31 Oct: "Haan, test karke". Encode episodes from ordinary conversation, test first, then shadow.

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
