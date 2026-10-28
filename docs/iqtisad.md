# Iqtisad (اقتصاد): hard spending limits

Every paid model call is checked against its user's remaining budget **before it is sent**. Its answer length is capped to what the money left can pay for. A limit is therefore a hard stop that no single call can cross, not a warning after the fact. Spending is held to a measure (al-Furqan 25:67).

The code is in `backend/api/iqtisad.py`. It is called from the paid providers in `backend/providers.py`: Anthropic, OpenAI and OpenRouter, for both normal and streamed calls. Every caller (chat, Lisan, debug mode, the AGI test, summaries, deep research) goes through those providers. Local models (Ollama, Ruh, the owned model) cost nothing and are not metered.

## How a call is admitted

| Part of the call | How MIZAN bounds it |
|---|---|
| Input | **Hard bound:** a byte-level tokenizer makes at most one token per UTF-8 byte of the request, so the byte count is an upper bound.<br>**Learned estimate:** once a model has been seen at least three times, MIZAN uses its learned tokens-per-byte ratio (exponentially weighted mean + 2σ), which is cheaper.<br>**Near the limit:** whenever the money left is within twice the learned estimate, MIZAN goes back to the hard bound.<br>**Images:** each counts at the provider's documented ceiling.<br>**Anthropic prompt-cache writes:** counted at 1.25× input. |
| Output | `max_tokens` is capped at what the money left buys. Providers enforce `max_tokens`, so this bound holds. If even this model's learned 10th-percentile answer no longer fits, the call is refused instead of being cut short. |
| Calls running at the same time | Each admitted call reserves its worst case until it is settled, so two calls in parallel cannot spend the same money. |
| A model with no known price | Refused while a limit applies (`MIZAN_BUDGET_UNPRICED=refuse`, the default). With `allow` it runs and is charged what the provider reports. |
| OpenRouter fallback models | The request is priced at the most expensive model OpenRouter may serve it with. |

## How a call is settled

When a call ends, MIZAN records what it cost:

- **Provider-reported cost** (for example OpenRouter's `usage.cost`) is charged when it is sent.
- **Otherwise, the price table:** the reported token counts are priced from `api.prices`, including cache reads (0.1×) and cache writes (1.25×) on Anthropic.
- **Cut off before usage arrived:** a stream that broke or a request that timed out may still have run upstream. Whatever the provider did not report is charged from what MIZAN knows: the request's size (at the model's learned mean tokens per byte once it has three observations, else one token per byte, plus each image at its ceiling), plus the output that was visibly streamed. An unreported call is never free.
- **Rejected with an explicit HTTP error** (a status code, such as 429 or 5xx): nothing was generated, so nothing is charged and the reservation is freed.

Each settled call also updates the model's learned input ratio and output size.

## Fixed-price actions

A paid action that is not a model call, such as a WhatsApp template message
([Bab](bab.md)), goes through `charge_fee`: it is sent only when the owner's
daily and monthly limits (with what is in flight) leave room for its price,
and it is recorded in the same ledger (`source: fee`).

## Prices

`backend/api/prices.py` holds the list prices, in this order:

1. `MIZAN_PRICE_OVERRIDES`
2. the static table
3. live OpenRouter catalog prices, refreshed with the model limits and saved in `$MIZAN_DATA_DIR/prices_live.json`, so a restart without network still knows them. OpenRouter's negative "variable price" entries are treated as unknown.

## Limits

| Setting (System settings) | Meaning |
|---|---|
| `MIZAN_BUDGET_DAILY_USD` | Limit per user per local day. Empty means no limit. |
| `MIZAN_BUDGET_MONTHLY_USD` | Limit per user per calendar month. Empty means no limit. |
| `MIZAN_BUDGET_UNPRICED` | `refuse` (default) or `allow` for models with no known price. |

Who each limit applies to:

- **Server default:** the two server limits apply to every user who is not an administrator.
- **Per-user limit (administrator):** an administrator can set limits for any user, including another administrator, with `PUT /api/iqtisad/limits/{user_id}`. These replace the server default for that user. Empty values return the user to the default.
- **Own limit (every user):** every user can set their own limits with `PUT /api/iqtisad/limits`. These only make the budget smaller: the lowest limit that applies wins.

The day is the user's local day. Its timezone is the place the user set for prayer times (Muraqabah), else the timezone remembered from the first chat that sent one, else UTC. A chat that later sends another timezone never moves the spending day, since that would renew the daily limit early.

## What the user sees

- **Settings → Spending:**
  - today and this month against the limits, with when each renews;
  - spend per day for the last 30 days;
  - spend per model this month;
  - the user's own limits.
  - Administrators also see every user's spend this month and can set their limits.
- **When the budget is used up:** the chat ends with "Your daily model budget of $X is used up … It renews at …" (error code `budget_exhausted`).
- **Work that needs no model:** MIZAN's own tools still answer. Quran and hadith quotes, calculations and dates need no model.
- **Tadbir recipes:** a recipe that needed the language model says why it stopped.

## Storage

`$MIZAN_DATA_DIR/iqtisad.db` has four tables:

- `spend`: one row per call, with the owner, local day and month, model, tokens, cost, and whether the cost came from the provider, the table or a bound;
- `limits`
- `zones`
- `calibration`: the learned ratios.

If the data directory cannot be written and a limit applies, no paid call runs (fail closed). With no limit, calls run and are not recorded.

## API

- `GET /api/iqtisad`: your spend, limits, renewal times, history and per-model totals.
- `PUT /api/iqtisad/limits`: body `{"daily_usd": number | null, "monthly_usd": number | null}`, sets your own limits.
- `GET /api/iqtisad/all` (administrators): this month's spend for every user.
- `PUT /api/iqtisad/limits/{user_id}` (administrators): sets one user's limits.
