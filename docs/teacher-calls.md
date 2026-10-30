# Teacher calls: how often MIZAN answers on its own

MIZAN's aim is to use the hosted language model as a teacher that is asked less and less: MIZAN plans, runs and checks what it understands, keeps what it verified (Hifz, Ta'allum, Qasd, Tajriba, and answers its sources confirmed: Talaqqi), and asks the model only for words it cannot yet produce. This page is how that is measured. Before it existed, nothing recorded which answers needed the model, so the aim could not be checked.

## Per answer: `usage.lisan`

Every answer's `usage` (saved with the assistant message, returned in the chat stream's `final` event) carries:

| Field | Meaning |
|---|---|
| `calls` | Hosted-model calls this request made (the same calls listed in `usage.calls`) |
| `zero_call` | `true` when the answer needed no hosted-model call at all |
| `tasks` | Calls per kind of work: Lisan's tasks (`write_code`, `cross_check`, `plan_steps`, `form_checks`, `conform`, …) and `answer` for the model answering in words |
| `family` | What Fahm read the request as (`compute`, `quran`, `run_code`, `converse`, …); `unplaced` when MIZAN did not read it (`MIZAN_ORCHESTRATION=llm`, evaluations) |
| `language` | The language Lughah read |
| `source` | `mizan` (a recipe MIZAN ran) or `language_model` (the model answered) |
| `verified` | Whether MIZAN verified the result itself |

The running summary of a very long chat (`reasoning/context_engine.py`) is a model call made outside the agent: Iqtisad charges it, but it is not in `usage.calls` or `usage.lisan`.

## Over time: `GET /api/tadbir/teacher-calls`

`?days=30` (1 to 365) and `scope=me` (your own answers) or `scope=all` (administrators: every user's). It reads the saved answers' usage only, never their text, and returns:

- `requests`, `zero_call`, `zero_call_share` and `interval`: the share of answers with no model call and its Wilson 95 % interval;
- `by_day`: the same per day, so the trend shows;
- `by_family`: the same per (family, language), most frequent first: the share is only expected to reach about 1 where a verifier or a finite recipe exists (arithmetic, dates, Quran and hadith lookup, programs MIZAN keeps), and stays below that for open conversation;
- `lisan_tasks`: which kinds of work still called the model, the list of what to teach MIZAN next.

The same numbers for your own answers are shown under **Agents → Majlis → Learning → On its own · بنفسه** (the share with its interval, the most frequent families, and the Lisan tasks still asked of the model).

Answers saved before this field existed are counted by their recorded calls under the family `unrecorded`. Unfinished answers and evaluations (`stateless`) are left out.

## In evaluations and spend

- Imtihan rows keep each arm's `lisan_calls`; the report gives MIZAN's zero-call share with a Wilson interval and how many of its model calls were Lisan tasks.
- Iqtisad records every paid call with its chat request and Lisan task (`spend.request_id`, `spend.task`), so cost can be split the same way.

A Wilson interval needs enough answers to mean anything: about 250 to 400 answers in a family and language give a share to within ±5 points.
