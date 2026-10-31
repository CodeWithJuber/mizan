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
