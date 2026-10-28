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
| **Act** | `engine.py` | Tools run through `BaseAgent._execute_tool_safe`, so chat permissions, Fitrah, Izn and approvals all apply. A passing failure (busy, 503, rate limit) of a tool that only reads or runs is retried after 0.5 s and 2 s. Outside text in a tool result passes Amanah before anything reads it. |
| **Verify** | `engine.py`, `express.furqan` | Sandbox exit codes; MIZAN's own calculation cross-checks sandbox output; a program that prints numbers must agree with an independent program (Tathabbut); citations, numbers and links in any wording must come from MIZAN's facts, and a warning in a tool's result must be kept. |
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
| compute | "2**100 kitna hai?" | none. When the user asks for the working (Qasd's `explain` facet), the steps come from MIZAN's own evaluation. |
| run_code | "Python me 2\*\*100 run karo", or a fenced code block plus "run" | none. MIZAN writes `print(...)` itself, runs it, and cross-checks the output against its own calculation. |
| build_and_run | "Ek python program likho jo … aur run karo", "Help me write a Python script that …" | Lisan writes the program. MIZAN runs it; on failure Lisan repairs it, at most twice. A program that prints numbers is verified only when an independent program Lisan writes for the same request prints the same numbers (Tathabbut); a verified program is kept and re-run for the same request with no model call (Hifz, [automatic-learning.md](automatic-learning.md)). A program that opens a window (tkinter, PyQt, pygame, …, read from its imports) is compiled instead of run, because the sandbox has no screen; the reply shows the code and says it was not run. |
| silsila | "Find the next number 13,26,64,118,274,376", a sequence with a term missing inside it | none when MIZAN's own methods (polynomials in n and in the n-th prime, recurrences) or the OEIS give a rule that reproduces every term. Otherwise Lisan proposes the rule as a program, which MIZAN tests on every term in the sandbox, with at most two revisions (six when the user asks it to try harder). A missing inner term uses MIZAN's methods and the OEIS only. |
| quran | "Ayatul Kursi", "Surah Ikhlas", "سورة البقرة 255" | none for the text, at most 10 ayahs per reply, with the translation the user names ("Urdu tarjuma") or that of their language. A question about the ayah (`quran_question`) is answered by Lisan from its translation only, checked by Furqan. |
| quran_search | "Quran me Kausar ka zikr", "Which surah mentions the elephant?", "inna lillahi wa inna ilayhi rajiun" (no reference) | MIZAN finds the ayah in its own index ([Fihris](fihris.md)) and quotes it from the source; Lisan only answers the question from the ayah's translation |
| quran_count | "Quran mein kitni ayat hain?", "Baqarah mein kitni ayat" | none: read from MIZAN's surah index (114 surahs, 6236 ayahs), never searched |
| sarf | "كاتب ka root kya hai?", "What is the wazn of استغفر?" | none: root, wazn, part of speech and meaning are read from the Quranic Arabic Corpus ([Sarf](sarf.md)) |
| run_follow | "Run this code", "isko chalao" after a program in the chat | none: MIZAN runs the longest runnable block of the most recent message that shows one |
| hadith | "Bukhari 1", "Sahih Muslim 2564b", "Tirmidhi 2516 dikhao", "بخاری شریف حدیث نمبر 1" | none |
| waqt | "aaj ki date kya hai", "aaj ki hijri date", "15 March 2026 hijri mein", "1 Ramadan 1448 kab hai", "Eid kab hai" | none |
| salah | "Maghrib ka time kya hai aaj", "Prayer times today" | none: computed for the user's place, or a city named in the message ([Muraqabah](muraqabah.md)) |
| watch | "Har subah Fajr ke baad ek ayat bhejo", "Remind me every morning at 7 am to drink water" | none: MIZAN saves a watcher and says when it runs next ([Muraqabah](muraqabah.md)); never from a watcher's own task |
| build_project | "Ek calculator app banao", "Create a quiz game", "Python CLI todo app banao" | Lisan writes each file and repairs what MIZAN's checks find. A new project is created, or the selected project is used when it is empty; a selected project that already has files is changed by `edit_project`. Frameworks and backends (React, Django, databases, logins) are beyond the blueprints: the agent loop takes them in `hybrid` mode. |
| web_search | "latest … search karo" | Lisan answers only from the numbered results. MIZAN adds the source list itself. |
| web_read | URL + "padho / summarize" | as for web_search, with one page. When the page is gone, the next link the user gave is read. A question a table on the page answers ("the cheapest", "the total") is computed by a program Lisan writes, run on the page within Hudud's limits. |
| browse | a link plus "click on Pricing", "search for … and tell me the price", "take a screenshot" | Lisan proposes browser steps; MIZAN checks each one and runs them in its browser sandbox on the user's sites only; nothing is sent to a site without the user's approval ([Shahid](shahid.md)) |
| hf_hub | `https://huggingface.co/datasets/<owner>/<name>`, "Hugging Face pe mere datasets dikhao" | none: MIZAN lists, previews or imports through its read-only Hub tools ([Hugging Face](huggingface.md)) |
| recall | "yaad hai maine kya bataya tha?" | Lisan may word what is recalled (first what the user said earlier in this chat, else MIZAN's memory), checked by Furqan |
| remember | "yaad rakhna meri beti ka naam Maryam hai" | None: MIZAN keeps the user's own words as a note tied to the chat (`chat:<id>`); never from a watcher's task |
| edit_project | "Button ka color red karo", "add a dark mode toggle" (in a selected project) | Lisan writes the changed files. MIZAN picks the files it reads (BM25), saves with `expected_sha256` so a newer version is never overwritten, and checks the changes: local references, CSS, JSON, `node --check` and `py_compile` in the sandbox, and `unittest` when the project has tests. It repairs at most twice and shows a diff. A build request in a project that already has files becomes an edit. |
| run_file | "Run main.py and show me the output" (in a selected project) | none: MIZAN finds the file, runs it in the project's sandbox and shows exactly what it printed |
| project_task | "Count the errors in app.log", "Sales.csv me total kitna hai nikalo" (in a selected project, naming a data file) | Lisan writes the program; MIZAN runs it on the project within Hudud's limits ([Hudud](hudud.md)), checks that each named output exists (a JSON output parses, a CSV one is not empty) and that no other file changed, repairs at most twice, and Lisan may word the reply from what the program printed (Furqan) |
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
  - Katib: code, calculation, sequences and projects
  - Mundhir: search and Hugging Face
  - Mubashir: reading and browsing pages
  - Khalifah: Quran, hadith, dates, prayer times, watchers, memory and connected tools

  Exploration is rare, under one choice in five, and is measured by a test.
- **Running.** The chosen agent runs MIZAN's recipe through its own tool gate,
  so its Izn policy applies. Receipts and metrics go to the chat's agent.
- **Compound requests.** Each part goes to its own agent. Different agents run
  side by side; one agent runs its parts in order.
- **Credit.** The plan names the agent ("MIZAN gives this to Katib (code
  agent)"), and the result's `orchestration.agents` records who did the work
  (metadata, never the answer's text). The agent's task and success counts
  grow, and its Nafs evolves.
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
- **Scope.** Only write-and-run, web search, project builds and edits, and
  requests for a connected tool (with the need Lisan named) are learned,
  because their details can be rebuilt from the new message. Up to 200
  examples are kept per user.

Nothing here trains model weights or exports chats. Training the own model
still needs an approved bundle (`docs/own-learning-cycle.md`); its watcher
already trains automatically once a bundle is approved.

`GET /api/tadbir/learning` returns the routing estimates and your learned
wording count. `DELETE /api/tadbir/learning/wording` forgets your wording.
`GET /api/tadbir/learning/live?after=<seq>` returns each learning step as it
happens (Sijill), shown as **Learning now**. All appear in
**Majlis → Learning**.

Results carry `completion_status`:

- `verified_by_mizan`: exit code checked, cross-check passed, citations supported, or authentic text quoted
- `evidence_observed`: a tool answered but the claim is not fully verified
- `unverified_answer`: words no tool backs, such as the model's answer to a request with no recipe

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

Majlis, Ta'allum, Hifz (verified programs re-run without the model),
Tathabbut (an independent program must agree), Muhasaba (a daily self-review
that corrects mistakes it can prove), Tajriba (verified repair lessons),
Tajdid (Lisan's code instructions renewed only when proven better) and Wazn
(the cheapest ready model) are described in
[automatic-learning.md](automatic-learning.md).

## Seeing what MIZAN adds

The debug mode ([debug-mode.md](debug-mode.md)) sends one message to the base
model alone and to MIZAN. It shows every step MIZAN took: Fahm, Majlis,
tools, Lisan's prompts and replies, Furqan and learning. It also flags what
the base model got wrong: numbers no fact supports, unbacked action claims,
and misquoted Quran or hadith text. Every answer also carries its Isnad
([isnad.md](isnad.md)): each claim graded by what supports it. The AGI test
([imtihan.md](imtihan.md)) scores the base model and MIZAN on 194 tasks.

## Limits

- **Understanding.** Fahm acts only on a reading its model finds decisive,
  learned from seed examples; the parsers that find references, expressions
  and links are exact grammars. A request it does not place goes to Lisan's
  step mapping, which MIZAN validates. Anything still unplaced is answered in
  words in `mizan` mode, or by the agent loop in `hybrid` mode. It is never
  forced into a recipe. Seeds (or Ta'lim examples, [talim.md](talim.md))
  widen MIZAN's own coverage, and verified wording widens it automatically.
- **Furqan.** It checks that wording stays inside the facts: numbers,
  citations, links and action claims, and that a warning in a tool's result
  is kept. It does not prove the entailment of every sentence.
- **Tafsir and sharh.** MIZAN quotes text and established translations. For
  tafsir or a hadith's explanation, it names a recognised work for that
  collection (for example Fath al-Bari for Bukhari) and does not generate one.
- **Hadith numbers.** Lisan may map unusual wording to a hadith reference only
  when the user wrote the number. A topic ("the hadith about intention") is
  never turned into a reference from the model's memory.
