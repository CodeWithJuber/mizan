# Automatic learning

MIZAN learns from its own verified work, automatically and per user. No chat transcript becomes training data for any model.

| Part | What it learns | From | Used for |
|---|---|---|---|
| **Majlis** (`tadbir/majlis.py`) | Which agent does each kind of work best | Every result MIZAN verifies, or fails to verify (Beta posterior per agent and kind of work) | Giving each part of a request to the agent most likely to get it right (Thompson sampling) |
| **Ta'allum** (`tadbir/taallum.py`) | Your wording for its actions | Lisan's mappings that MIZAN then verified | Understanding the same wording later with no model call |
| **Hifz** (`tadbir/hifz.py`) | Programs it verified for you | Write-and-run results that ran cleanly | Re-running the same request (same words, same numbers) with no model call |
| **Muhasaba** (`tadbir/muhasaba.py`) | Where the model's own words were wrong | A daily re-check of the answers MIZAN did not verify | Posting a correction in that chat |

## Hifz: programs kept and re-checked

When a program Lisan wrote runs cleanly in the sandbox, MIZAN keeps it with its output, for you only. A later request is matched by:

- 80% of its content words
- exactly the same numbers ("10 Fibonacci numbers" is not "20")
- no question words that change the request

A matching request re-runs the kept program. Every reuse is a regression check: the output must match what was verified.

- **Output differs:** the program loses reliability (Beta posterior) and Lisan writes a new one. A program whose reliability falls below one half is forgotten.
- **Time- or randomness-dependent programs:** they retire themselves the first time their output differs.

You can see and forget your kept programs in **Majlis → Learning** (`GET/DELETE /api/tadbir/programs`).

## Muhasaba: self-review and correction (Tawbah)

Once a day (`MIZAN_MUHASABA_SECONDS`, default 86,400; first run 10 minutes after start), MIZAN re-reads the answers from the last day that the language model gave in words. Answers MIZAN verified are skipped. It checks what it can check by itself:

- **Arithmetic** written as `expression = value`, recomputed exactly.
- **Quran and hadith text** quoted with a reference, compared with the text MIZAN reads from its source.

When it can prove a mistake, it posts a correction in that chat. The correction gives the exact value or the source text and is marked as MIZAN's review.

- **Each answer is reviewed once.**
- **Admin switch:** Settings → System settings → Self-review (`MIZAN_MUHASABA=on|off`).
- **User opt-out:** a user stops the corrections with the chat preference `muhasaba: off`.
- **Run it now (admin):** `POST /api/tadbir/muhasaba?hours=24`.

## Every user has their own Majlis

Each signed-in user gets a private instance of every agent: private memory, and learning that stays private. Those instances share one registry, so Majlis gives each part of a user's request to that user's specialist agents, not only the coordinator. **Majlis → Learning** shows each user what their own agents learned.

## The own model (Ruh / mizan_reply)

Weight training of MIZAN's own model stays deliberately gated, and the gate is enforced in CI (`tests/test_mizan_owned_research.py`):

- Only human-written examples count; machine-authored targets are rejected.
- Each example needs a named reviewer who is not its author.
- Each bundle needs an approval bound to the bundle's digest.

Once an approved bundle is in place, the autorun watcher trains, evaluates, and activates or rolls back automatically (`docs/own-learning-cycle.md`).

**Hardware:** the 2 GB production backend cannot train. Train on a larger host.

Nothing in Majlis, Ta'allum, Hifz or Muhasaba becomes training data. What they learn is MIZAN's own understanding.
