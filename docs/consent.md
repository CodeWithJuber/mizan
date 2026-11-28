# Consent: what MIZAN may learn and keep

MIZAN learns from each person's work for that person, keeps a ledger of what it learned, and turns a person's words into training data only with their yes. This page records the owner's decisions and where each one is enforced.

## The owner's decisions (30 Oct 2026)

| Question | Decision | Status |
|---|---|---|
| Learning from a person's chats for them | On by default, listed in their Daftar, one switch turns it off | Built |
| Their words as training data for MIZAN's own model | Off unless they switch it on | Built |
| A teacher model's output as a training target | Only when MIZAN verified it and the teacher's licence allows training on its output | Built (`mizan_reply`) |
| Minimum age | 16 or older | Built |
| A blinded audit of MIZAN's own answers against the teacher | 2 to 5 % of answers, about $0.17 a week | Built (Tadqiq, [tadqiq.md](tadqiq.md)): only runs whose person has learning on |
| Learning shared across users | Opt-in when it is built | Not built |

On 31 Oct 2026 the owner decided that MIZAN's own models should learn while it works, not only in a training run ([tadrib.md](tadrib.md)):

| Question | Decision | Status |
|---|---|---|
| Does each lesson need a person's review first? | No: a check by MIZAN stands in for the review on this path, every lesson is listed, and the person (or an administrator) can take any lesson back, after which every model that learned it is rebuilt without it | Built for the reader (phase 1) |
| May an own model answer instead of the teacher? | Per task and language, once an anytime-valid test shows it is as good; MIZAN still checks every answer and the teacher answers when the check fails | Phase 2, not built |

## Purposes

Each run has one of these purposes, and only the person can widen it.

- **Turn.** Answering the message. Always allowed; the chat's messages are saved so the chat can be read back.
- **Self.** Learning for the same person: Ta'allum wording, Qasd intents, Hifz programs, Tajriba lessons, Majlis routing, Ahl al-Dhikr `ilm`, memory strengthening on recall (FSRS review, Masalik), episodes of what the person said ([episodic-memory.md](episodic-memory.md); shadow: kept and counted, not yet recalled), task records and the knowledge graph, decisions the agent records and the chat's hand-off, and a project's or watcher's drift chart ([azm.md](azm.md)). On by default. Switched off with `learning: off`.
- **Train.** Keeping the person's messages and MIZAN's replies as unreviewed training candidates for MIZAN's own model. Off by default. Switched on with `training: on`. A candidate is still not training data until a named reviewer accepts it (`docs/own-learning-cycle.md`). One path differs, by the owner's decision of 31 Oct 2026: the person's own words are a **lesson** for MIZAN's language reader as soon as Lughah and the reader read them in the same language (Tadrib, [tadrib.md](tadrib.md)); each lesson is listed under `GET /api/tadrib/lessons` and taken back with `DELETE /api/tadrib/lessons/{digest}`. MIZAN's own models are one per server, shared by everyone who switched training on; the reader learns which language words are in, not what they say.

A note the person asks MIZAN to remember is kept whatever `learning` says, because they asked for it.

## How a choice is made

- **In the app.** Library → Memory → **What MIZAN may learn** has the two switches. A new chat says that MIZAN learns and links there.
- **In the API.** `PUT /api/chat/preferences/learning` or `/training` with `{"value": "on"}` or `"off"`; any other value is refused with 422, by the memory layer itself, so no writer can store anything else. `DELETE` returns the choice to its default.
- **In the Daftar.** Both choices appear among the person's preferences. Editing or forgetting one there works like the switch, with the same check and receipt. An imported ledger never carries a consent choice; it is skipped.
- **Receipts.** Every change is a Sakk receipt of kind `consent` with the purpose and the new value (`default` after a delete), in the person's own signed chain (`docs/sakk.md`).

A choice applies from the person's next message.

## Where it is enforced

`memory/stateless.py` holds three gates, read wherever MIZAN learns or captures:

- `learns()` is false in an evaluation and under `learning: off` (`no_learning`). `AdaptiveStateStore.put`, memory reinforcement on recall, task records, Tafakkur and the knowledge graph all check it.
- `trains()` is true only under the person's yes (`allow_training`) and never in an evaluation or a WhatsApp run. With no choice bound, nothing is captured. The two places a chat's words become candidates check it (`agents/base.py`, `agents/khalifah.py`).
- `barred_from_training()` is what no yes can lift: an evaluation, or a channel whose terms forbid training (WhatsApp). The training store (`learner/ruh_learner.py`) refuses these itself.

MIZAN's own language reader (`tadbir/ruh_reader`, `docs/ruh-reader.md`) is the one model that trains on a person's words: while MIZAN works, from the lessons Tadrib keeps under their `training: on` (`tadbir/tadrib`, which checks `learns()`, `trains()`, `barred_from_training()` and stateless runs itself, and never keeps pasted text, an injection or scripture), and while MIZAN rests, from those lessons and the messages a named reviewer accepted (the review hash must still match). It checks `learns()`, `trains()` and `barred_from_training()` again itself, never learns a message holding the Quran's words, and keeps the SHA-256 of each learned message (no words) so that erasing the chat (Mahw) drops every version that learned from it. Since v2 (31 Oct 2026) it also never learns text a language model wrote: Hinglish-Everyday-Conversations-1M, which GPT-4o-mini wrote, is measured only, and Lughah's seeds from it are never its training, development or replay lines (`corpus.MODEL_WRITTEN`, `ruh_reader.written_by_a_model`).

`consent_bindings` in `api/main.py` turns a person's saved choices into those gates, and `owner_consent` reads them for a run done for an owner. Every path that runs a person's request binds them: the web chat stream, `POST /api/chat`, the WebSocket chat and task messages, `POST /api/tasks`, the federation route, watchers, unattended runs (schedules, triggers, queue), and Telegram, WhatsApp and email turns. If the choices cannot be read, the run learns and keeps nothing.

`usage.memory` on each answer reports `learning` and `training` for that run.

## Minimum age

`POST /api/auth/register` requires `"age_16_or_older": true` and answers 422 otherwise. Sign-up in the app has the checkbox. The audit log records that the age was attested, not the age.

Chats with an Islamic assistant reveal religious belief, which data-protection law treats as a special category (GDPR Art. 9). Under GDPR Art. 8, a child under 16 needs a parent's consent unless a member state lowers the age. Some laws set the line higher. India's Digital Personal Data Protection Act 2023 counts everyone under 18 as a child and requires a parent's verifiable consent for them. An operator serving such a jurisdiction must raise `MINIMUM_AGE` in `api/main.py` or verify a parent's consent.

## Teacher output as training data

`mizan_reply` (the own reply model) accepts a record with provenance origin `licensed_teacher` only when every condition holds:

- `teacher.licence` is one that allows training on the output: `apache-2.0`, `mit`, `deepseek-terms-of-use` or `deepseek-model-license`.
- The teacher is not Anthropic or OpenAI. Their terms forbid using output to build or train competing models, so their answers are for lookup only. The model's vendor decides, not the router: `anthropic/…` or `openai/…` through OpenRouter is refused, and so is any model name with `claude` or starting with `gpt-`.
- `verification` names the MIZAN check that passed: `tathabbut`, `sandbox`, `sidq`, `ahl_dhikr`, `fihris`, `calc`, `hifz` or `qiyas`, with `passed: true`.
- `creation_method` is `machine_generation`, and the record still needs an accepted review by a named reviewer.
- None of its sources is Quran or hadith. Scripture is never a training target, whoever wrote the answer (`ruh_model/data/scripture.py`).

The JSON schema (`research/own_model/schemas/reply-record.schema.json`) states the same rules, and `mizan_reply/data.py` enforces them, including the vendor check the schema cannot express. The data module's hash in `research/registry/runtime_sources.json` was revised for this change.
