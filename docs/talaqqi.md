# Talaqqi: the teacher teaches once

"Then Adam received from his Lord [some] words" ([2:37](https://quran.com/2:37), Saheeh International). "Who taught by the pen, taught man that which he knew not" ([96:4-5](https://quran.com/96:4-5)). What is received is written down and kept, so it need not be asked for again.

Talaqqi (تلقّي, receiving) is the loop that lets a question MIZAN once sent to the language model be answered later without it. The model is the teacher. MIZAN keeps only what its own sources confirmed, and checks it again before every reuse.

## How an answer is kept

When the language model answers a question about the world (Qasd's `fact` facet), Ahl al-Dhikr asks MIZAN's sources about each claim (`docs/ahl-dhikr.md`). The answer is kept for that user when all of these hold:

- every claim Ahl al-Dhikr checked was **supported** by a source, and none was contradicted or left unknown;
- the Truth Gate corrected or removed nothing, and no claim is graded mawdu';
- the question **opened its chat**. A question that leans on earlier messages, such as "who founded it?", could name another topic in the same words;
- the question is not about the deen. A ruling, or an answer citing the Quran or hadith, is never kept: deen answers come from the Quran, hadith and scholars, never from a model's words.

The kept answer carries its sanad: the question's words, the teacher model, how it was received (`sama`, heard from the teacher), and for each claim the sentence, title, link and date of the source that confirmed it.

## How it is given again

A later question that opens a chat, in the same language, with the same content words, numbers and asking words, is answered from the kept answer. The content words may differ by a fifth at most, the same closeness Hifz asks of a kept program. Every reuse is checked first.

Each kept answer has an FSRS-6 strength (`memory/tadhkir.py`), as a memory does.

- **Not due.** While its retrievability R(t) is at least 0.9, FSRS's own target, the claims stand on the sentences that confirmed them.
- **Due.** Once R(t) falls below 0.9, the claims are asked of the outside sources again: Wikipedia and the web, read by the NLI model. No language model is asked.
  - Every claim supported: the answer is given, and the check counts as an FSRS Good review. Stability grows, so the next outside check comes later.
  - Any claim contradicted: the answer is dropped and the teacher is asked again.
  - Otherwise, for example a source unreachable: the teacher answers this time, and a new answer the sources confirm replaces the kept one.

The reused answer ends with a line saying when MIZAN learned it and which sources confirmed it. Each claim is graded hasan with its source in the Isnad ledger. `usage.lisan.calls` is 0, `usage.lisan.source` is `mizan`, and `usage.talaqqi` records when it was kept, the teacher, how often it was given, and whether the sources were asked again. The zero-call share (`docs/teacher-calls.md`) counts these answers.

## Privacy and control

- Kept per user, in the user's own adaptive store, never shared with another user.
- `learning: off` keeps nothing (`docs/consent.md`). A stateless run, such as an evaluation or a debug comparison, neither keeps nor reuses.
- Deleting a chat (Mahw) drops the answers it taught: each kept answer names its chat, and is also found by its question's words.
- The Daftar ledger counts them under "Learned". Agents → Majlis → Learning lists them, with their sources, how often each was given and when its next check is due. "Forget these answers" there, or `DELETE /api/tadbir/answers`, forgets them all.
- Nothing here trains a model. These are MIZAN's own kept answers.

## Where it lives

- `backend/tadbir/talaqqi.py`: keep, recall, re-check, reuse and forget.
- `Tadbir._talaqqi` in `backend/tadbir/engine.py`: the reuse, tried before an unrecognised request goes to the language model.
- `BaseAgent._talaqqi_keep` in `backend/agents/base.py`: the keep, after Ahl al-Dhikr.
- `tests/test_talaqqi.py`.
