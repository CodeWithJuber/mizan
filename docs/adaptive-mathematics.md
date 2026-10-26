# Adaptive mathematics (Mizan — weighing the evidence)

> "And the heaven He raised and imposed the balance, that you not transgress
> within the balance." — Quran 55:7-8

Fixed thresholds and keyword rules were replaced by estimators that learn from
observed outcomes. All of them live in `backend/core/adaptive.py`, are pure
Python, and persist their state in the `adaptive_state` table of the agent's
memory database when they need to survive a restart.

| Site | Before | Now |
|---|---|---|
| Nafs promotion (`core/developmental_stages.py`, `core/architecture.py`) | raw success ratio ≥ stage rate; Hikmah capped at 20 so L4+ was unreachable; level not restored after restart | Beta posterior of the success rate: promote when P(rate ≥ stage rate) ≥ `MIZAN_NAFS_CONFIDENCE` (default 0.7) with the stage's minimum evidence; demote when that probability falls below 1 − confidence. Hikmah counted in full; level and successes restored from the profile |
| Task complexity (`core/ruh_engine.py`) | substring keywords ("hi" matched "this") | continuous effort score from word-boundary action words, length (log) and structure (steps, code) bucketed into the same five classes; works for any language |
| Fuad confidence (`core/fuad.py`) | fixed "+35% of the gap" / "×0.7" steps; failure found by substring | Beta-Bernoulli posterior mean; failure read from the receipt's structure |
| Yaqin certainty of tool results (`agents/base.py`) | fixed 0.8 success / 0.2 failure | each tool's own posterior success rate (with forgetting, persisted) |
| Proven patterns (`qca/yaqin_engine.py`) | 0.9 + n/1000 | Wilson lower bound of n verified successes |
| Memory ranking (`memory/dhikr.py`, `memory/memory_pyramid.py`) | stored importance × fixed 24 h half-life; SQL `LIKE` order | BM25 relevance × ACT-R activation (ln(n/(1−d)) − d·ln L: repetition keeps memories strong) × importance; certainty is a posterior mean over recalls |
| Native-sense gate (4 copies) | duplicated 0.8 / 0.2 constants | one `nlp/gate.py` (same measured defaults, `MIZAN_NLP_MIN_SENSE_*` overrides) |
| Lawwama checkpoints (`core/self_healing.py`) | 4 / 2 / 1 turn buckets | interval round(4·H²) plus an immediate checkpoint on a sudden health drop (EW z-score < −1 against the agent's own baseline) |
| Task queue (`task_queue/task_queue.py`) | strict priority order (starvation possible) | effective priority = priority − ln(1 + wait/τ), τ = `MIZAN_QUEUE_AGING_SECONDS` (300) |
| Agent choice for queued/scheduled tasks (`api/main.py`, `core/shukr.py`) | always the first agent | Thompson sampling over each agent's per-category Beta posterior |
| Nafs triad (`core/nafs_triad.py`) | substring voices, unit-temperature softmax (always ~0.35) | word-boundary voices, temperature equal to the bids' spread |

These are heuristics with honest statistics, not proofs: a "success" is still
a delivered response unless a task is independently verified, and the
estimators only weigh the evidence the system actually observes.
