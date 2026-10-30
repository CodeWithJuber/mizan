# Tadqiq: a blinded audit of the answers MIZAN gives without the teacher

MIZAN answers more and more requests with no language-model call: a program it verified before and re-runs (Hifz), an answer the teacher taught once and sources confirmed (Talaqqi), wording it learned (Ta'allum), its own recipes for arithmetic, dates and code. `usage.lisan.zero_call` marks these answers ([teacher-calls.md](teacher-calls.md)). As that share grows, fewer answers pass in front of an independent opinion, so a slow decline in their quality could go unseen. Tadqiq (تدقيق, close checking) samples them and asks the teacher, blinded, and watches each family of requests for a rise in disagreement. The owner approved it on 30 Oct 2026 ([consent.md](consent.md)).

Code: `backend/tadbir/tadqiq.py`. The hook is one call at the end of `BaseAgent._execute_run` (`agents/base.py`), after the answer's `usage` is built.

## What is audited

An answer is drawn for an audit only when all of these hold:

- its `usage.lisan.zero_call` is true: no hosted-model call made it;
- it is the answer to the person's request, not a run one agent delegated to another;
- the run is not an evaluation (`stateless`: the AGI test, a debug comparison, a chat sent with `stateless: true`);
- the person has learning on (`stateless.learns()`; `learning: off` is never audited);
- Amanah found no pasted instruction aimed at the AI in the request;
- the run's provider is a hosted model (not `mizan-owned`).

It is then drawn with probability `MIZAN_AUDIT_RATE`, from the operating system's random generator (`random.SystemRandom`), so the sample is unbiased. The probability is kept with each result: every audit stands for 1/p answers, and the report's `answers_represented` is the Horvitz-Thompson count Σ 1/pᵢ, which stays right if an administrator changes the rate.

A drawn answer whose question is about the deen is never sent: `ahl_dhikr.religious` (Qasd's `deen` and `ruling` facets, or an answer citing a Quran or hadith reference) is checked first. The teacher's word is not a check on scripture; MIZAN quotes the Quran and hadith from their own sources.

## How it is audited

After the answer has been delivered, a background task (held in a module-level set so it is not garbage-collected) asks the teacher. The teacher is the run's own provider and model, through Lisan, with the Lisan task name `audit`. It is given the request alone, with the date, and asked to answer directly; it never sees MIZAN's answer, its code or its notes. Lisan uses the run's model here, not a cheaper one Wazn would pick, because the audit is of the teacher's opinion. The call is recorded on a stand-in agent, so it never enters the answer's own `usage`.

The two answers are then compared:

| MIZAN's answer | Compared by | Agree | Disagree |
|---|---|---|---|
| A program's printed output (a plain-text fence), or numbers with no sentence (`17*25 = 425`) | The numbers each answer gives beyond those in the request, with `tathabbut.agree` | One answer's numbers appear, in order, among the other's | Neither does |
| Words | The NLI model of Ahl al-Dhikr (`ahl_dhikr.judge`), MIZAN's sentences against the teacher's and the teacher's against MIZAN's; each pair must first pass `ahl_dhikr.about` | Some claim is supported and none contradicted | A claim is contradicted (judge requires the contradiction to read both ways) |

Everything else is `unsettled`: the teacher gave no number, no sentence of one answer is about the other's, or the NLI model is not available. MIZAN's own notes under an answer (lines in italics) and code are set aside before comparing. A sentence needs three words besides numbers to carry a claim, the unit Ahl al-Dhikr holds claims to.

Two more outcomes are recorded and never compared: `refused` (Iqtisad refused the call) and `unavailable` (the provider failed).

## Spending

The audit call goes through Iqtisad like every paid call: admitted before it is sent against the remaining daily and monthly budget, refused when the budget is spent, settled with what it cost. It is charged to the person whose answer it audits, under the Lisan task `audit`, so it shows in their Settings → Spending. A refused audit sends nothing and costs nothing. The reply is limited to 800 tokens. The report's `spend_usd` is each call's cost as `api.usage` estimates it from the reported usage (provider-reported cost first, then `api.prices`); Iqtisad's ledger holds the charge itself.

## What is kept

One row per audit in `$MIZAN_DATA_DIR/tadqiq.db`: time, family, language, kind (`numbers`/`text`), outcome, sampling probability, estimated cost and number of calls. No request text, no answer text, no person or chat identifier. Each family's monitor state is kept beside it: the last window of settled outcomes as 0/1, the baseline counts and the statistic.

## Consent and privacy

- The audit is the owner's decision of 30 Oct 2026: 2 to 5 % of answers, about $0.17 a week.
- It runs only for a person with learning on. An audit learns nothing about that person and keeps nothing of theirs; it measures MIZAN's own answers. Evaluations are never audited, so a benchmark is never sent to the model twice by it.
- What leaves the server is the request (and any image attached to that turn) to the same provider that would have answered it had MIZAN asked the teacher. Nothing else from the chat is sent.
- Tadqiq's results cannot be tied back to a person or a chat, so erasing a chat (Mahw) has nothing of Tadqiq's to erase. The alarm note is written outside any chat for the same reason. The call's cost is in the person's Iqtisad ledger (owner, request id, task `audit`, tokens, cost), as every paid call is; it holds no text.
- Questions about the deen are never audited.

## The disagreement monitor

Each family (`usage.lisan.family`) has an e-CUSUM over its settled outcomes (x = 1 for a disagreement). Unsettled, refused and unavailable outcomes do not enter it.

### The target

The owner's target is to find a 10-point drop in agreement within about two weeks at 200 requests a day. With the default rate r = 0.03, that is

  T = r × 200 × 14 = 84 audits (6 a day),

and the rise to find is δ = 0.10 in the disagreement rate. T follows the configured rate: 56 audits at 0.02, 140 at 0.05.

### The statistic

With the family's baseline disagreement rate p₀ and p₁ = p₀ + δ, each settled audit adds its log-likelihood ratio

  ℓ = x · ln(p₁/p₀) + (1 − x) · ln((1 − p₁)/(1 − p₀)),

and the statistic is log Mₙ = max(log Mₙ₋₁, 0) + ℓₙ. The alarm is raised when log Mₙ ≥ h.

This is Page's CUSUM, and it is also an e-detector (Shin, Ramdas and Rinaldo, "E-detectors: a nonparametric framework for sequential change detection"): while the true rate p is at most p₀, E_p[e^ℓ] = p·p₁/p₀ + (1 − p)(1 − p₁)/(1 − p₀) ≤ 1 (it is linear in p and equals 1 at p₀). Then Mₙ is bounded by the Shiryaev-Roberts e-process, whose value minus n is a supermartingale, and the expected number of audits before a false alarm is at least e^h (Lorden 1971), however often the statistic is read. For a known change CUSUM is optimal: no rule finds a rise of δ faster on average for the same false-alarm run length (Moustakides 1986).

### The threshold, from the target

After the rise every audit adds on average I = KL(p₁‖p₀) = p₁ ln(p₁/p₀) + (1 − p₁) ln((1 − p₁)/(1 − p₀)). Siegmund's approximation gives the CUSUM's expected delay from its floor as (H − 1 + e^−H)/I, where H is the threshold plus the expected overshoot when it is crossed. A crossing comes on a disagreement, whose step is ln(p₁/p₀); half of it is taken as the overshoot. Setting the delay to T:

  H − 1 + e^−H = T · I,  h = H − ½ ln(p₁/p₀),  and h ≥ ln(1/α) with α = 0.05.

The floor means an alarm never rests on less evidence than Tajdid needs to replace an instruction (an e-value of 20). It binds only when the baseline is high (from about 0.22 at T = 84).

Worked at p₀ = 0.10: p₁ = 0.20, I = 0.2 ln 2 + 0.8 ln(8/9) = 0.0444 nats, T·I = 3.73, H = 4.72, h = 4.72 − 0.35 = 4.37, so the alarm needs an e-value of e^4.37 ≈ 79.

| Baseline p₀ | h | e^h (guaranteed audits before a false alarm, at least) |
|---|---|---|
| 0.02 | 10.21 | 27,146 |
| 0.05 | 6.35 | 573 |
| 0.10 | 4.37 | 79 |
| 0.15 | 3.57 | 35 |
| 0.20 | 3.13 | 23 |
| 0.30 | 3.00 (floor) | 20 |

The guarantee e^h is a floor; the real run length is longer by a factor of about 1/KL(p₀‖p₁).

### The baseline

The baseline is the family's own disagreement rate, so a family where the teacher often disagrees for its own reasons (it cannot know today's Hijri date as MIZAN computes it) does not alarm for that; only a change does. It is learned from the family's settled audits older than the last T (the guard), with Jeffreys' estimate (d + ½)/(n + 1). A rise is found within about T audits, before it can enter its own baseline. Watching starts once the baseline holds T audits, that is after 2T settled audits (four weeks at the design traffic). The threshold is recomputed from the current baseline at each audit.

### What it does in simulation

The shipped `observe` was run on simulated families (1000 runs each, 84-audit window, 6 audits a day). "False alarm" is the share of steady families that alarm in their first year of watching; "found" is the delay of a 10-point rise that starts after two weeks of watching (`tests/test_tadqiq.py` checks the same at a 2 % baseline).

| Baseline | False alarm in the first year | Rise found: mean | median | within 2 weeks |
|---|---|---|---|---|
| 0.02 | 0.8 % | 14.1 days | 12.5 days | 60 % |
| 0.05 | 15.7 % | 14.0 days | 11.3 days | 64 % |
| 0.10 | 56.6 % | 14.8 days | 10.8 days | 64 % |
| 0.20 | 94.5 % | 15.9 days | 10.3 days | 64 % |

With the baseline known exactly, the mean delay is 83 to 86 audits (14.0 days) for every baseline up to 0.20, and the mean run to a false alarm is about 17,400 audits (8 years) at 0.05, 2,770 (15 months) at 0.10 and 930 (5 months) at 0.20. The learned baseline adds false alarms early on, while it rests on few audits.

The trade-off is set by the target itself: 84 audits carry T·I nats of evidence about the rise, and the false-alarm run length grows like e^h. At 3 %, a steady family with a 10 % baseline raises a false alarm in its first year of watching about half the time, and one with a 20 % baseline almost always does. At 5 % (T = 140) the same two-week target leaves much more room, so an administrator who sees false alarms in families with high baselines can raise the rate to 0.05 within the approved range:

| Baseline | False alarm in the first year at 5 % | Rise found: mean |
|---|---|---|
| 0.02 | 0.0 % | 13.9 days |
| 0.05 | 0.6 % | 14.0 days |
| 0.10 | 15.3 % | 15.3 days |
| 0.20 | 57.2 % | 15.3 days |

The derivation assumes a family receives the design traffic of 200 zero-call answers a day. A family with less traffic is audited less often, so the same rise is found in proportionally more days; the statistic and its guarantee per audit are unchanged.

### An alarm

When the statistic first crosses the threshold, the alarm is logged (`mizan.tadqiq`, warning) and noted in Sijill under the administrators' shared record (`sijill.ADMINS`), which every administrator's **Learning now** feed (`/api/tadbir/learning/live`) includes. The family's monitor reports `alarm: true` while the statistic stays above the threshold and counts its `alarms`. The statistic keeps running; a lasting rise keeps it high.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `MIZAN_TADQIQ` | `on` | `off` stops new audits (tests run with `off`) |
| `MIZAN_AUDIT_RATE` | `0.03` | The sampling probability. A value from the server's environment is held to the approved 0.02 to 0.05; a value an administrator saves in Settings → Developer → System settings may be anything from 0 to 1 |

Both apply live, from the next answer.

## Endpoint

`GET /api/tadbir/audit?days=90` (administrators only; `days` 1 to 3650 bounds the counts, the monitors are cumulative) returns:

- `rate`, `rate_set_by_admin`, `approved_rate`, `enabled`, and `design` (`shift`, `requests_per_day`, `days`, `window_audits`, `alpha`);
- `total` and, per family, `audited`, each outcome's count (`agree`, `disagree`, `unsettled`, `refused`, `unavailable`), `settled`, `disagreements`, `disagreement_rate` with its Wilson 95 % `interval`, `answers_represented`, `spend_usd`, `unpriced` (calls with no known price) and `languages` (audits per language);
- per family, `monitor`: `status` (`learning the baseline` or `watching`), `baseline_audits` and `needed`, then the `baseline` rate, the `alternative` p₁, the `statistic` (e-value Mₙ), the `threshold` (e^h), `alarm`, `alarms`, `alarmed_at` and `expected_delay_audits`.

Counts only; no content.
