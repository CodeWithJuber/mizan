# Automatic learning

MIZAN learns from its own verified work, automatically and per user. No chat transcript becomes training data for any model.

How often answers still need the hosted model, per kind of request and language, is measured in [teacher-calls.md](teacher-calls.md).

| Part | What it learns | From | Used for |
|---|---|---|---|
| **Majlis** (`tadbir/majlis.py`) | Which agent does each kind of work best | Every result MIZAN verifies, or fails to verify (Beta posterior per agent and kind of work) | Giving each part of a request to the agent most likely to get it right (Thompson sampling) |
| **Ta'allum** (`tadbir/taallum.py`) | Your wording for its actions | Lisan's mappings that MIZAN then verified | Understanding the same wording later with no model call |
| **Hifz** (`tadbir/hifz.py`) | Programs it verified for you | Write-and-run results that ran cleanly and, when they print numbers, that an independent program agreed with (Tathabbut) | Re-running the same request (same words, same numbers) with no model call; a request of the same form with other numbers through a template made from two or more of them |
| **Muhasaba** (`tadbir/muhasaba.py`) | Where the model's own words were wrong | A daily re-check of the answers MIZAN did not verify | Posting a correction in that chat |
| **Tajriba** (`tadbir/tajriba.py`) | Which change fixed which kind of error | Sandbox failures that a repair then verified | Showing Lisan the most relevant verified lessons when it writes or repairs similar code |
| **Tajdid** (`tadbir/tajdid.py`) | Better wording of Lisan's code instructions | Every verified or failed result of code work | Replacing an instruction only when the new version proves better |
| **Wazn** (`tadbir/wazn.py`) | Which model is ready for which kind of work | The same verified outcomes, per model | Sending code work to the cheapest ready model, and a stronger one after a failure |

## Hifz: programs kept and re-checked

When a program Lisan wrote runs cleanly in the sandbox, and an independent check agrees with it (Tathabbut, below), MIZAN keeps it with its output, for you only. A later request is matched by:

- the same code language
- content words that overlap the kept request's by at least 80% (shared words over all words of the two)
- exactly the same numbers ("10 Fibonacci numbers" is not "20")
- no question words that change the request

A matching request re-runs the kept program. Every reuse is a regression check: the output must match what was verified.

- **Output differs:** the program loses reliability (Beta posterior) and Lisan writes a new one, which replaces it once MIZAN verifies it. A program whose reliability falls below one half (two failed reuses in a row) is forgotten.
- **Time- or randomness-dependent programs:** their output differs on reuse, so the check fails and a new program is written; such a program never answers from memory.
- **Bounded:** at most 100 programs per user, the most recently used first.

You can see and forget your kept programs in **Agents → Majlis → Learning** (`GET/DELETE /api/tadbir/programs`).

### Templates: one form, any numbers or words

Two verified programs for "the first 10 Fibonacci numbers" and "the first 20 Fibonacci numbers" usually differ only where the requests' numbers differ. Two verified programs for "print a greeting for Ali" and "print a greeting for Bilal" usually differ only where the requests' words differ (`print("Assalamu alaikum, Ali")` and `print("Assalamu alaikum, Bilal")`). When no kept program fits a request exactly, MIZAN makes one from the kept programs of its form (`hifz.template`), with no model call. It tries a form that differs only in numbers first, then a form that also differs in words.

**Numbers.**

1. **Instances.** Python programs this user kept for requests with the same words apart from their numbers (80% overlap), the same question words and as many numbers. Each must be reliable, and a program that printed numbers must have been confirmed by an independent program (Tathabbut). At least two instances with different numbers are needed.
2. **Anti-unification.** MIZAN reads their syntax trees and keeps what they share. Each difference becomes a slot bound to the j-th number of the request. This includes numbers inside strings ("F10 =" and "F20 ="). This is Plotkin's least general generalisation.
   - A slot may be that number plus a whole-number offset (`range(1, 11)` and `range(1, 21)` for "1 to 10" and "1 to 20"), when every instance gives the same offset. The offset is one parameter measured once per instance, so their agreement tests it. An exact match is preferred.
   - If the programs differ anywhere the requests' numbers do not explain (say `print(55)` and `print(210)`), there is no template.
3. **Test-guided acceptance.** Putting each instance's numbers back into the template must give that instance's program exactly.
4. **General only where it was seen to vary.** Suppose every instance had the same number at some position ("2 to the power 10", "2 to the power 20"). Then a request that changes it ("3 to the power 5") gets no template, since the program may hold that number as a literal. A number must also keep its kind: an integer slot does not take 2.5.
5. **Run.** The new program runs in the sandbox. If it fails, Lisan writes a program as usual.

**Words.** A slot may also be a span of the user's own words.

1. **Requests of one form.** MIZAN anti-unifies the request's words with each kept request's words, as `memory.dhikr.same_frame` does for memories. A number matches any number here; its value is a number slot's.
   - The words the two share, in order, are the form. Each run of other words is a span, and the g-th span is the g-th slot's value.
   - Every span must be filled on both sides. A word that is only added or only left out, or a number that moved, makes another form.
   - Words are compared without case. A span is taken as the user wrote it: from its first word to its last, with whatever stands between them.
   - When kept requests share the request's form in different ways, the most specific form that two or more of them share is tried first.
2. **The form says what the requests are about.** As in `same_frame`: the form has at least two words, one of them carries more information than an average word of general language (Lughah's corpora), and no request's spans together are longer than the form.
3. **Instances.** Python programs this user kept for requests of this form, with the same question words and as many numbers. They are trusted as for numbers: reliable, and confirmed by Tathabbut if they printed numbers. At least two instances with different spans are needed.
4. **Anti-unification of the programs.** As for numbers, plus one rule. A string constant, or a part of one (including a literal part of an f-string), that holds each instance's g-th span at the same place becomes a slot bound to the request's g-th span.
   - Spans are looked for as whole words first, then anywhere in the string.
   - Numbers in the same string still become number slots. So "the first 3 letters of the word banana" and "the first 4 letters of the word mango" give `print('coconut'[:5])` for "the first 5 letters of the word coconut".
5. **Test-guided acceptance.** Putting each instance's numbers and spans back into the template must give that instance's program exactly.
6. **General only where it was seen to vary.** A span that was the same in every instance gets no slot, and a request that changes it gets no template. So "count the vowels in banana" and "count the vowels in mango" answer "count the vowels in coconut", but not "count the consonants in coconut".
   - A slot also keeps its length in words. If every instance's span there was one word, a request with two words there ("a greeting for Omar twice") gets no template.
   - Numbers follow the rules above.
7. **The user's words are data.** A span's value is only ever placed in an `ast.Constant`: a string, or a literal part of an f-string.
   - The template becomes source with `ast.unparse`, and that source must parse back to exactly the same tree, or there is no template. A span such as `"); import os; ("` is printed as text, and braces in a span never open an f-string expression.
   - Words the programs use as names (`total = 5` against `count = 5`) never become slots, since names are code.

The user's words keep their case: "a greeting for omar" prints "omar". If Lisan's programs changed the case of the user's words ("ali" in the request, "Ali" in the program), there is no template.

**A word the request does not say.** Suppose a kept program holds, in its strings, a word that every request it was verified for says and the new request does not. Then it was written for that word.
- Such a program is not reused (`hifz.recall`, where requests that differ in one word can still overlap 80%).
- A template that holds such a word is not used, whether it was made from numbers or words.
- Without this rule, "count the vowels in the word banana and print the count" re-ran its program for "mango" and printed 3 again. Likewise, two programs for "the first 10 (11) letters of the word pomegranate" gave `print('pomegranate'[:12])` for "the first 12 letters of the word watermelon".

The answer says what happened. MIZAN wrote no new code: it put the request's numbers or words into a program it verified for N requests of this form. The result for this request was not checked by an independent program, so the answer is reported as observed (`evidence_observed`), not verified. The kept programs remain the authority; a template is computed from them each time and is never stored. Each kept program now also stores its request's words, so the order of its numbers and its spans are known; programs kept before this change take part once they are kept again.

**Measured** (`test_measured_word_templates` in `tests/test_learning_auto.py`): 29 cases, each with two verified programs, a new request and the output its template must print.
- **13 correct templates:** a greeting, the user's lower case kept, vowels, reversed, capitals, `repr`, an f-string, numbers and words together, two spans, Hinglish, Arabic script, two-word names, and numbers only.
- **14 correct refusals:** another verb (four cases), another preposition, "first" against "last", extra words (two cases), one instance, a word that never varied, a word used as a name, programs that differ beyond the span, number output that Tathabbut did not confirm, and the very request kept.
- **2 refusals where a template would have been right:** the program changed the case of the user's word, and a span longer than any instance's.
- **0 wrong templates.**

### Cases: what Lisan sees when it must still write

When neither a kept program nor a template answers, Lisan writes the program.
- **What it is shown:** this user's four verified programs nearest the request (`hifz.cases`, BM25 over the requests' words; each program up to 2,000 characters), with an instruction to write a request of the same form the same way. Four is where Memento's case memory stopped gaining (DeepResearcher F1 59.9 → 64.5 at K = 4).
- **Why:** programs of one form then share their shape, so the next request of that form can be answered by a template with no model call.
- **What it is not shown to:** Tathabbut's independent program, so the two derivations stay independent.

### Tathabbut: an independent derivation must agree

Running cleanly says a program works, not that it read the request right: in the 27 October API benchmark, "the 30th Fibonacci number, F1 = F2 = 1" printed F29 (514229), exited 0 and was kept as verified. So when a program prints numbers (`backend/tadbir/tathabbut.py`):

1. Lisan writes a second program for the same request by a different method, **without seeing the first** (`Lisan.cross_check`), and MIZAN runs it.
2. **Agreement:** every number the second prints appears, in order, in the first's output, each compared at the precision the less precise of the two was printed with. The answer says a second program printed the same result.
3. **Disagreement:** the first program is repaired once, told what the independent program printed. If the repair agrees, it is the answer. If not, the answer is **not verified**, says what the second program printed, and nothing is kept.
4. **No check:** if the independent program could not run or printed no number, a result that prints numbers is not verified either, and the answer says it was not checked.

A program kept before this check is checked once on its next reuse: if an independent program disagrees, it is forgotten and Lisan writes a new one (`hifz.drop`); if it agrees, it is marked `checked`. Two derivations that share no code rarely share a misreading; this is N-version programming, with the cost of one more Lisan call and one more sandbox run per program that prints a number.

## Talaqqi: answers the sources confirmed, given again without the model

A language-model answer to a question about the world, whose every claim Ahl al-Dhikr found supported by a source, is kept for that user with its sources. The same question, opening a chat, is then answered with no model call. Its claims are checked against the sources again on an FSRS schedule that lengthens each time they hold; an answer a source contradicts is dropped. Questions about the deen are never kept. See `docs/talaqqi.md`.

## Nawm: what was learned is replayed while MIZAN rests

"And made your sleep [a means for] rest" ([78:9](https://quran.com/78:9)); "And of His signs is your sleep by night and day and your seeking of His bounty" ([30:23](https://quran.com/30:23), Saheeh International).

In sleep the brain replays what it lived, by priority. Mattar and Daw (Nature Neuroscience 21, 2018) explained the order of hippocampal replay as Need × Gain:
- **Need:** how likely a memory is to be used soon.
- **Gain:** how much revisiting it would change what is done with it.

Once a day, while no request is running, MIZAN replays the answers a teacher taught once (Talaqqi) that way (`backend/tadbir/nawm.py`, `nawm_night` in `api/main.py`).

- **Need** is the lesson's ACT-R base-level activation from how often it was given: n uses over its lifetime L, B = ln(n/(1−d)) − d·ln L.
- **Gain** is 1 − R(t), the chance its sources no longer bear it out, from its FSRS retrievability. Only lessons whose R(t) fell below 0.9 are replayed; one above it is given on its sources anyway.
- **Recheck:** the lessons with the highest Need × Gain have their claims asked of Wikipedia again and read by the NLI model, as a reuse would.
  - All supported: the lesson is held more firmly (a Good review), so the next person to ask is answered at once. It is not counted as given.
  - A claim contradicted: the lesson is dropped before anyone is given it.
  - Otherwise: it is left as it was, and checked again when asked.
- **Second witnesses** ([2:282](https://quran.com/2:282): "And bring to witness two witnesses"). The same night takes the person's `ilm` claims that only one site settled, most recently used first. Such a claim is shown under an answer but is not given to Lisan as knowledge, and Wikipedia is asked about it again (`nawm.witness`, through `ahl_dhikr.consult`).
  - An independent host agrees: the claim becomes sahih and is given to Lisan from then on.
  - A site is never its own second witness, so a claim Wikipedia settled is not asked of Wikipedia.
  - A question about the deen is never asked outside.
  - The web search is not used at night, since it is a tool each person's permissions govern.
- **The language reader** (`ruh_reader.rest`, [Ruh reader](ruh-reader.md)): when MIZAN's own reader has been trained, a person who switched `training: on` has their messages that a named reviewer accepted learned by it, a quarter of every batch replayed from the seeds. The new version replaces the current one only when it is no worse on the held-out seeds; the previous one is kept, and erasing a chat drops every version that learned from it. It is skipped under `MIZAN_RUH_READER=off`, without weights, and without that consent.
- **Budget:** five lessons and five claims per person, and five minutes per night in all. The night stops as soon as a request starts.
- **Who:** each person whose agents the server holds in memory, each administrator, and each other enabled person whose learning is on disk (`$MIZAN_DATA_DIR/private/<SHA-256 of their id>/memory.db`), so a person who has not chatted since the server restarted still gets their night. Their file is read as it is; no agent is built for it. Each person's own choices are bound: under `learning: off` nothing is changed.
- **Learning now:** each replay is noted under the Learning page's **Learning now** as "Replayed while resting". The note names no request, since it is made outside any chat and erasing a chat could not find it.
- **Settings:** `MIZAN_NAWM` (`on` by default, or `off`); `MIZAN_NAWM_SECONDS` (default 86400, at least 600). The first night starts 15 minutes after the server starts.

## Muhasaba: self-review and correction (Tawbah)

Once a day (`MIZAN_MUHASABA_SECONDS`, default 86,400; first run 10 minutes after start), MIZAN re-reads the answers from the last day that the language model gave in words. Answers MIZAN verified are skipped. It checks what it can check by itself:

- **Arithmetic** written as `expression = value`, recomputed exactly.
- **Quran and hadith text** quoted with a reference, compared with the text MIZAN reads from its source.

When it can prove a mistake, it posts a correction in that chat. The correction gives the exact value or the source text and is marked as MIZAN's review.

- **Each answer is reviewed once.**
- **Admin switch:** Settings → Developer → System settings → Self-review (`MIZAN_MUHASABA=on|off`).
- **User opt-out:** a user stops the corrections with the chat preference `muhasaba: off`.
- **Run it now (admin):** `POST /api/tadbir/muhasaba?hours=24`.

## Tajriba: lessons from verified repairs

Terminal-RSI (arXiv:2610.22192) improves a model by rewriting failed attempts into verified ones and learning from them. HERD (arXiv:2610.31401) keeps the cases a skill misses in a bounded memory. MIZAN does both without changing any weights.

When a program fails in the sandbox and a repair then verifies, MIZAN keeps a lesson for that user:

- **the error signature:** the exception and its message, with names, paths and numbers replaced by `<name>` and `<n>`
- **the change that fixed it:** the lines the verified repair changed, at most 30

The next time Lisan writes code, MIZAN finds the most relevant lessons (BM25 over the signature and the request) and shows up to three. A repair is shown the lessons that match its error signature.

Each lesson keeps a Beta posterior of how often the work it was shown for then verified:

- Lessons whose usefulness falls below one half are dropped.
- At most 60 are kept, the most recently used first.

You can see and forget your lessons in **Agents → Majlis → Learning** (`GET/DELETE /api/tadbir/lessons`).

## Tajdid: instructions renewed, kept only when proven better

Lisan's instruction for each kind of code work is MIZAN's harness for the model: writing code, repairing it, and proposing or revising a grid or sequence rule. Following HERD and sequential incumbent replacement, the harness evolves under MIZAN's checks:

1. **Credit.** The current instruction (the incumbent) keeps a Beta posterior of how often its work verified. MIZAN's own checks are the critic:
   - the sandbox exit code
   - every grid example reproduced
   - every sequence term checked
2. **Challenge.** After five failures, MIZAN asks Lisan to rewrite the instruction from the recorded error signatures. The rewrite becomes a challenger only if it:
   - keeps the output contract, such as "fenced code block" or `transform(grid)`
   - keeps the same `{placeholders}`
   - stays within twice the original length (or 600 characters, whichever is more)
3. **Trial.** The incumbent and the challenger share the work by Thompson sampling.
4. **Decision.** Results of the two versions are paired as they arrive, and over the pairs that disagree MIZAN keeps an e-value that may be read after every result (`core.adaptive.paired_e_value`). The full derivation is in [Quranic algorithms](quranic-algorithms.md#3-tajdid-improvement-accepted-only-on-evidence-safe-to-read-at-any-time-tadbirtajdidpy-coreadaptivepaired_e_value).
   - **Evidence the challenger is better ≥ 1/α_k:** it becomes the incumbent. α = 0.05; the k-th challenger has α_k = α·2^-k, so the first needs 40.
   - **Evidence the incumbent is better ≥ 1/α_k, or 80 disagreements without a decision:** the challenger is retired.
   - The old "P(better) ≥ 0.95" rule, checked after every result, promoted no-better versions far more often than 5% of the time. By Ville's inequality the e-value cannot.

**What never changes:** Lisan's base prompt, MIZAN's verification and every safety gate. Only the wording of the task instruction evolves.

**Scope:** the state is shared by all users and stored in `$MIZAN_DATA_DIR/harness.db`. It holds instruction text and error signatures, never user text.

**Admins:**
- See every version, its success rate, the challenger's evidence against its threshold and the promotion history in **Agents → Majlis → Learning**.
- Reset a kind of work to the built-in instruction there (`GET /api/tadbir/harness`, `DELETE /api/tadbir/harness/{task}`).
- Switch renewal off with `MIZAN_HARNESS_EVOLUTION=off`.

## Wazn: the cheapest ready model

An admin may list candidate models for Lisan's code work, cheapest first, in `MIZAN_LISAN_MODELS`. MIZAN keeps a Beta posterior per kind of work and model, fed by the same verified outcomes.

- **First call:** goes to the cheapest model whose sampled success reaches the readiness level (`MIZAN_LISAN_READINESS`, default 0.7).
- **Each failed attempt at the same work:** moves one step to a stronger model instead of asking the same one again.
- **No list:** Lisan uses the agent's model. At most six models are read from the list.
- **An image in the turn (Basar):** only listed models that read images (as far as the provider's catalog says) are candidates.

## Safety omission (Furqan)

A tool's result can carry a warning or an error, such as skipped files, a deprecation, a truncated result or a rate limit, even when the call succeeded. Furqan checks Lisan's wording of a tool result: if the wording drops such a warning, MIZAN uses its own wording, which shows the result in full.

## Every user has their own Majlis

Each signed-in user who is not an administrator gets a private instance of every agent (`_private_agent` in `api/main.py`): private memory, and learning that stays private. Those instances share one registry, so Majlis gives each part of a user's request to that user's specialist agents, not only the coordinator. Administrators use the shared agents. **Agents → Majlis → Learning** shows each user what their own agents learned.

## The own model (Ruh / mizan_reply)

Weight training of MIZAN's own model stays deliberately gated, and the gate is enforced in CI (`tests/test_mizan_owned_research.py`):

- Human-written examples count. A machine-authored target counts only as a `licensed_teacher` record: MIZAN verified it, the teacher's licence allows training on its output (never Anthropic or OpenAI), and none of its sources is Quran or hadith (`docs/consent.md`).
- Each example needs a named reviewer who is not its author.
- Each bundle needs an approval bound to the bundle's digest.

Once an approved bundle is in place, the autorun watcher trains, evaluates, and activates or rolls back automatically (`docs/own-learning-cycle.md`).

**Hardware:** the 2 GB production backend cannot train. Train on a larger host.

Nothing in Majlis, Ta'allum, Hifz, Muhasaba, Tajriba, Tajdid or Wazn becomes training data. What they learn is MIZAN's own understanding.

Two research directions are deliberately not used for the own model:

- **Distilling the model's own outputs into its weights** (teacher-free self-distillation).
- **Training on machine-generated tasks** (Athanor-style curricula).

Both would put unverified machine-authored targets into training, which the CI-enforced data policy above forbids.

A person's own chats become training candidates only if they switch training on (`docs/consent.md`); learning for them is on unless they switch it off.

## Learning now (Sijill)

Every learning step above is also noted, the moment it happens, in a live record for the user whose work it came from (`backend/tadbir/sijill.py`): wording learned or reused (Ta'allum), a request's wording learned by Qasd, a program kept or re-run (Hifz), a repair lesson (Tajriba), an instruction scored (Tajdid), routing evidence (Majlis), a note kept (Daftar), a game level remembered (Mustakshif), a claim corrected before it was shown (Sidq), claims settled by sources (Ahl al-Dhikr), an answer rewritten to the form asked for (Nazm). The **Learning** page shows it at the top as **Learning now**, polling `GET /api/tadbir/learning/live?after=<seq>` every few seconds. The last 200 notes per user are kept in memory.

## Own-model training

`MIZAN_OWNED_LEARNING_AUTORUN` is on by default and read live: the watcher starts whenever an own-learning directory is configured and trains only when a bundle is ready, which requires human-written examples with named reviewers and a digest-bound approval (see [own-learning-cycle.md](own-learning-cycle.md)). Turning it off in System settings takes effect without a restart.

