# Tadbir: MIZAN directs the work, the LLM supplies language

Tadbir (تدبير, "directing the affair") is MIZAN's own orchestration layer. For
every request it understands, MIZAN's architecture does the work:

- it understands the request
- it plans the steps
- it chooses and runs the tools
- it verifies the results
- it decides what to say

The language model is used only as **Lisan** (لسان), the language faculty, and
only for language work:

- write or repair a program from a precise request
- answer from sources that MIZAN fetched
- word a reply from facts that MIZAN established

```
request → Fahm (understand) → plan → act through MIZAN's tools → verify → express
                 MIZAN            MIZAN         MIZAN                MIZAN    MIZAN (+ Lisan wording, checked by Furqan)
```

Code: `backend/tadbir/`. It is hooked in at the start of
`BaseAgent._execute_impl`, after the faculties (Ruh, Nafs, Qalb, Hawa, Hikmah)
and before the model-driven loop.

## What MIZAN does itself

| Part | Module | Notes |
|------|--------|-------|
| **Fahm** (understanding) | `fahm.py`, `lughah.py`, `qasd.py` | Language (English, Hinglish, Urdu, Hindi, Arabic) and intent are posteriors of a naive Bayes model fitted by leave-one-out (`core/tamyiz.py`); entities come from exact parsers, whose findings are also the model's evidence. No word lists or cue patterns, no language model. See [fahm.md](fahm.md). |
| **Plan** | `engine.py` | Each recipe declares its steps. They stream to the chat's Activity card as a live plan. |
| **Act** | `engine.py` | Tools run through `BaseAgent._execute_tool_safe`, so chat permissions, Fitrah, Izn and approvals all apply. |
| **Verify** | `engine.py`, `express.furqan` | Sandbox exit codes; MIZAN's own calculation cross-checks sandbox output; citations, numbers and links in any wording must come from MIZAN's facts. |
| **Express** | `express.py` | MIZAN's own templates in five languages. Lisan's wording is used only when Furqan accepts it. |
| **Calculation** | `calc.py` | Exact big integers and fractions, bounded, no `eval`. |
| **Quran** | `quran.py` | 114-surah index checked against the Hafs count of 6236 ayahs. Parses references in Latin, Arabic, Urdu and Devanagari, including named ayahs such as Ayat al-Kursi. Fetches the Uthmani text and an established translation from api.alquran.cloud, quotes them verbatim, and strips the source's Basmala prefix from ayah 1, except in Al-Fatihah. The model never writes or rewrites ayahs. |
| **Hadith** | `hadith.py` | Index of ten collections: Bukhari, Muslim, Abu Dawud, Tirmidhi, Nasa'i, Ibn Majah, the Muwatta, and the Forty of an-Nawawi, Qudsi and Dehlawi. Parses references in all five languages and checks each number against the collection. Sahih Muslim uses 'Abd al-Baqi's numbering (`2564`, `2564b`) through a bundled table, `muslim_numbers.json`. Fetches the Arabic text and a translation (English or Urdu) from the open hadith-api dataset, quoted verbatim. Grades are shown scholar by scholar, as the source gives them, and a weak grade triggers a warning. MIZAN never grades a hadith itself. |
| **Waqt** (dates) | `waqt.py` | Today's date and time in the user's timezone (the browser sends its IANA zone with each chat; UTC otherwise, and the reply says so). Hijri dates use the Umm al-Qura calendar (`hijridate`, 1343–1500 AH) and conversions run both ways. Ramadan, the Eids, Arafah, Ashura and the new year are given with their expected Gregorian dates. Every Hijri date notes that local sighting of the crescent can move the month by a day. For Ramadan and the Eids, the reply quotes the hadith on fasting by the sighting of the crescent (Sahih al-Bukhari 1909, Sahih Muslim 1081). |
| **Projects** | `project.py` | MIZAN picks the files from its own blueprints: a static web app (`index.html`, `style.css`, `app.js`) or a Python program with `unittest` tests (`main.py`, `test_main.py`). Lisan writes each file. MIZAN saves them through the workspace tools and checks them itself. Web apps: the page loads both assets (MIZAN adds a missing link itself), every element id the script looks up exists, the CSS is well formed, and `node --check` passes in the sandbox. Python programs: the tests pass and `main.py` runs and exits. Failures go back to Lisan with MIZAN's exact finding, at most twice. |

## Recipes

| Intent | Example | Model calls |
|--------|---------|-------------|
| capabilities | "Hai tumhare paas tools?" | none: answered from the live tool registry |
| compute | "2**100 kitna hai?" | none |
| run_code | "Python me 2\*\*100 run karo", or a fenced code block plus "run" | none. MIZAN writes `print(...)` itself, runs it, and cross-checks the output against its own calculation. |
| build_and_run | "Ek python program likho jo … aur run karo", "Help me write a Python script that …" | Lisan writes the program. MIZAN runs it; on failure Lisan repairs it, at most twice. A program that opens a window (tkinter, PyQt, pygame, …, read from its imports) is compiled instead of run, because the sandbox has no screen; the reply shows the code and says it was not run. |
| quran | "Ayatul Kursi", "Surah Ikhlas", "سورة البقرة 255" | none |
| quran_search | "Sidratul muntaha kya hai", "Quran me Kausar ka zikr", "light upon light" (no reference) | MIZAN finds the ayah in its own index ([Fihris](fihris.md)) and quotes it from the source; Lisan only answers the question from the ayah's translation |
| run_follow | "Run this code", "isko chalao" after a program in the chat | none: MIZAN runs the longest runnable block of the most recent message that shows one |
| hadith | "Bukhari 1", "Sahih Muslim 2564b", "Tirmidhi 2516 dikhao", "بخاری شریف حدیث نمبر 1" | none |
| waqt | "aaj ki date kya hai", "aaj ki hijri date", "15 March 2026 hijri mein", "1 Ramadan 1448 kab hai", "Eid kab hai" | none |
| build_project | "Ek calculator app banao", "Create a quiz game", "Python CLI todo app banao" | Lisan writes each file and repairs what MIZAN's checks find. A new project is created, or the selected project is used when it is empty. An existing project is edited by the agent loop. Frameworks and backends (React, Django, databases, logins) also go to the agent loop. |
| web_search | "latest … search karo" | Lisan answers only from the numbered results. MIZAN adds the source list itself. |
| web_read | URL + "padho / summarize" | as for web_search, with one page |
| recall | "yaad hai maine kya bataya tha?" | Lisan may word the recalled memories, checked by Furqan |
| remember | "yaad rakhna meri beti ka naam Maryam hai" | None: MIZAN keeps the user's own words as a note tied to the chat (`chat:<id>`); never from a watcher's task |
| edit_project | "Button ka color red karo", "add a dark mode toggle" (in a selected project) | Lisan writes the changed files. MIZAN picks the files it reads (BM25), saves with `expected_sha256` so a newer version is never overwritten, and checks the changes: local references, CSS, JSON, `node --check` and `py_compile` in the sandbox, and `unittest` when the project has tests. It repairs at most twice and shows a diff. A build request in a project that already has files becomes an edit. |
| qiyas | a puzzle given as worked examples (JSON `train` input/output grids and `test` inputs, as in ARC) | Lisan proposes the rule as a Python `transform(grid)`. MIZAN runs it in the sandbox on every example and accepts it only if it reproduces all of them. Otherwise Lisan revises it from the examples it got wrong, at most twice. Only a proven rule's answer is verified; an unproven best guess says how many examples it fits. |
| use_tool | anything else Lisan maps to an action: a connector, a skill, memory | MIZAN chooses the tool from the user's permitted tools (BM25 × the tool's reliability posterior). Shell, raw files, raw HTTP and host Python are never chosen. Lisan fills the arguments; MIZAN validates them against the tool's JSON Schema with `jsonschema`, allows one retry, and runs the tool through the agent's gate. Lisan may word the result (Furqan). The answer is `evidence_observed`, not verified. |

**Lisan plans, MIZAN validates.** When Fahm finds an action more probable
than conversation but no recipe can be built from the words, or places only
part of a message, Lisan maps the wording into one to four steps of
MIZAN's action schema. MIZAN validates each step (invalid ones are dropped) and
runs them under one plan, each by its own recipe and agent.

**Compound requests.** A message made of two to four independent requests
("Bukhari 1 aur Surah Ikhlas dikhao", "2+2 kitna hai aur aaj ki date kya hai")
is split at its conjunctions. The split is used only when every part maps to a
recipe. The parts then run under one plan, and the answer is verified only if
every part is. A message whose conjunction joins one request ("app banao …
aur result dikhaye") stays whole.

## Majlis: MIZAN's agents share the work

`majlis.py`. MIZAN, not the language model, decides which agent does each part
of a request:

- **Candidates.** Every running agent that holds the needed tool, and that the
  user's permissions allow.
- **Choice.** Thompson sampling over a Beta posterior per (agent, kind of work),
  using `core/adaptive`. The prior favours the role made for the work:
  - Katib: code and projects
  - Mundhir: search
  - Mubashir: reading pages
  - Khalifah: Quran, hadith, dates and memory

  Exploration is rare, under one choice in five, and is measured by a test.
- **Running.** The chosen agent runs MIZAN's recipe through its own tool gate,
  so its Izn policy applies. Receipts and metrics go to the chat's agent.
- **Compound requests.** Each part goes to its own agent. Different agents run
  side by side; one agent runs its parts in order.
- **Credit.** The plan names the agent ("MIZAN gives this to Katib (code
  agent)"), and the reply says who did the work. The agent's task and success
  counts grow, and its Nafs evolves.
- **Learning.** Each verified or failed result updates that agent's posterior.
  An agent whose work keeps failing MIZAN's checks stops getting it.

## Ta'allum: learning from verified work

`taallum.py`. When Lisan maps wording that Fahm did not recognise, and MIZAN
verifies the result, MIZAN keeps the wording for that user:

- **Reuse.** A later message close to a kept wording is mapped by MIZAN
  itself, with no Lisan call. Closeness is BM25 over content words, plus 60%
  of the kept example's words. MIZAN's validation still runs on every reuse.
- **Questions are excluded.** "…ka matlab samjhao" never reuses a learned
  request.
- **Unlearning.** Each example has a Beta posterior and is dropped when reuse
  stops verifying.
- **Scope.** Only write-and-run, web search and project builds are learned,
  because their details can be rebuilt from the new message.

Nothing here trains model weights or exports chats. Training the own model
still needs an approved bundle (`docs/own-learning-cycle.md`); its watcher
already trains automatically once a bundle is approved.

`GET /api/tadbir/learning` returns the routing estimates and your learned
wording count. `DELETE /api/tadbir/learning/wording` forgets your wording.
Both appear in **Majlis → Learning**.

Results carry `completion_status`:

- `verified_by_mizan`: exit code checked, cross-check passed, citations supported, or authentic text quoted
- `evidence_observed`: a tool answered but the claim is not fully verified
- `unverified_answer`: Lisan conversed in strict mode

Results also carry `orchestrator: "mizan"`. The chat shows "Done by MIZAN" and
"Verified by MIZAN".

## Modes

Admins set `MIZAN_ORCHESTRATION` in Settings → System settings. It applies
immediately.

| Mode | Behaviour |
|------|-----------|
| `mizan` (default) | MIZAN performs every action, and **the model never controls a tool**. A request with no recipe or plan is answered in words through the full chat pipeline (memory, persona, history, streaming), with zero tools offered, not even tool discovery. `strict` is accepted as the former name. |
| `hybrid` | Tadbir handles what it understands. Anything else goes to the model-driven agent loop, which keeps the capability and execution guards. This was the default before. |
| `llm` | Tadbir is off. The model drives the agent loop as before. |

## Learning automatically

Majlis, Ta'allum, Hifz (verified programs re-run without the model) and
Muhasaba (a daily self-review that corrects mistakes it can prove) are described in
[automatic-learning.md](automatic-learning.md).

## Seeing what MIZAN adds

The debug mode ([debug-mode.md](debug-mode.md)) sends one message to the base
model alone and to MIZAN. It shows every step MIZAN took: Fahm, Majlis,
tools, Lisan's prompts and replies, Furqan and learning. It also flags what
the base model got wrong: numbers no fact supports, unbacked action claims,
and misquoted Quran or hadith text. Every answer also carries its Isnad
([isnad.md](isnad.md)): each claim graded by what supports it. The AGI test
([imtihan.md](imtihan.md)) scores the base model and MIZAN on 72 tasks.

## Limits

- **Recognisers.** They are rule based. A request they do not place goes to
  Lisan's step mapping, which MIZAN validates. Anything still unplaced is
  answered in words in `mizan` mode, or by the agent loop in `hybrid` mode.
  It is never forced into a recipe. Add a recipe or recogniser to widen
  MIZAN's own coverage, and learned wording widens it automatically.
- **Furqan.** It checks that wording stays inside the facts: numbers,
  citations, links and action claims. It does not prove the entailment of
  every sentence.
- **Tafsir and sharh.** MIZAN quotes text and established translations. For
  tafsir or a hadith's explanation, it names a recognised work for that
  collection (for example Fath al-Bari for Bukhari) and does not generate one.
- **Hadith numbers.** Lisan may map unusual wording to a hadith reference only
  when the user wrote the number. A topic ("the hadith about intention") is
  never turned into a reference from the model's memory.
