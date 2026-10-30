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

### Templates: one form, any numbers

Two verified programs for "the first 10 Fibonacci numbers" and "the first 20 Fibonacci numbers" usually differ only where the requests' numbers differ. When no kept program fits a request exactly, MIZAN makes one from the kept programs of its form (`hifz.template`), with no model call:

1. **Instances.** Python programs this user kept for requests with the same words apart from their numbers (80% overlap), the same question words and as many numbers. Each must be reliable, and a program that printed numbers must have been confirmed by an independent program (Tathabbut). At least two instances with different numbers are needed.
2. **Anti-unification.** MIZAN reads their syntax trees and keeps what they share. Each difference becomes a slot bound to the j-th number of the request. This includes numbers inside strings ("F10 =" and "F20 ="). This is Plotkin's least general generalisation.
   - A slot may be that number plus a whole-number offset (`range(1, 11)` and `range(1, 21)` for "1 to 10" and "1 to 20"), when every instance gives the same offset. The offset is one parameter measured once per instance, so their agreement tests it. An exact match is preferred.
   - If the programs differ anywhere the requests' numbers do not explain (say `print(55)` and `print(210)`), there is no template.
3. **Test-guided acceptance.** Putting each instance's numbers back into the template must give that instance's program exactly.
4. **General only where it was seen to vary.** Suppose every instance had the same number at some position ("2 to the power 10", "2 to the power 20"). Then a request that changes it ("3 to the power 5") gets no template, since the program may hold that number as a literal. A number must also keep its kind: an integer slot does not take 2.5.
5. **Run.** The new program runs in the sandbox. If it fails, Lisan writes a program as usual.

The answer says what happened. MIZAN wrote no new code: it put the request's numbers into a program it verified for N requests of this form. The result for these numbers was not checked by an independent program, so the answer is reported as observed (`evidence_observed`), not verified. The kept programs remain the authority; a template is computed from them each time and is never stored. Each kept program now also stores its request's words, so the order of its numbers is known; programs kept before this change take part once they are kept again.

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

