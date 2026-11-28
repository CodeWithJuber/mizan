# 'Azm: decisions and the hand-off

> "And when you have decided (*'azamta*), put your trust in Allah" (3:159)

A decision is made once and then acted on. Chats lose that: the next chat on the same project asks again what was settled, or contradicts it. 'Azm (`backend/memory/azm.py`) keeps two things per person, in `$MIZAN_DATA_DIR/private/<sha256(owner)>/azm.sqlite3`. The ideas come from ForgeKit's `decide.js` (an append-only decision log) and `handoff.js` (a bounded snapshot rewritten at the end of each session).

## Decisions

An append-only log of what the person decided and why. Each entry keeps:

- the decision and its reason (up to 500 characters each)
- the chat it was decided in, and the project or agent it belongs to, if any
- the person's message it came from (the chat saves it; `message_id`)
- when, and its source: `person` (added in Library or through the API) or `chat` (the agent recorded what the person said)

An entry is never edited. A decision that changes is a new entry; any entry can be forgotten. A decision is refused when it holds something shaped like a credential, or when Amanah reads it as an instruction to the AI ([amanah.md](amanah.md)), since it is shown to the model in later chats.

### How a decision is recorded

- **By the person**: `POST /api/azm/decisions`, or later in Library → Memory (Daftar, kind Decisions).
- **By the agent**: the `record_decision` tool (`decision`, `why`). The model proposes; MIZAN keeps it only when the person's own words in this chat (this request, their earlier messages, an answer they gave Tabayyun) hold most of the decision's distinctive information (`ahl_dhikr.about`: more than half of the information of its words above their average). A decision the model made up is refused. The tool writes only MIZAN's own record (approval category `read`: never asked about, never held), is offered through the tool catalog like every tool (an ordinary chat still sends only `mizan_discover_tools`), and keeps nothing in a stateless chat or with `learning: off`.
- **Not automatically.** Qasd has no facet for "the person is stating a decision", and adding one would need seeds and a pre-registered measurement like the others ([fahm.md](fahm.md)); until then nothing is detected by itself.

## The hand-off

A snapshot of at most 8 KB (8192 UTF-8 bytes) rewritten, never appended, at the end of every run the person sees (not a delegated part, not a stateless run, not with `learning: off`), for the chat, its project (if bound) and its agent (not for a replayed task: a watcher, schedule, trigger or queued run keeps only its own chat's). In priority order:

1. **Goal**: the project's or watcher's goal ([Niyyah](coding-workspaces.md#niyyah-the-projects-goal)), else the chat's first request.
2. **Open items**: the chat's unfinished plan steps (`todo_write`) and a Tabayyun question left unanswered ([tabayyun.md](tabayyun.md)).
3. **Decisions**: the last ten of this chat and its project.
4. **State**: the last request (pasted instructions removed, `amanah.clean_message`) and the start of the last answer.

The writer selects rows in that order until the snapshot fits, so what is written is exactly what is read. Every heading stays, and a section that lost rows ends with "(+N more not kept)": a drop is never silent. A row longer than a quarter of the budget is cut, so one long answer cannot push out the rest, and anything shaped like a credential is replaced with `[redacted]`.

The hand-off is never a way for outside text to reach a later chat:

- every row is read by Amanah before it is kept, and a row it reads as an instruction to the AI is dropped (the same check a decision passes);
- a run that read outside text with an instruction in it (a page, a file, a tool result, pasted text: Amanah's taint, `amanah.ignored`) keeps nothing the model wrote in it: no last answer, no plan steps, no question it would have asked; only the goal, the person's last request and the decisions;
- when a later chat reads it, the text is neutralized and fenced like outside text (`amanah.guard`, `<<untrusted …>>`), framed as data and not instructions, and an instruction found in it then taints that run as well.

### Where it is read

A new chat (one with no earlier turns) starts with a hand-off in its context, as a block the model reads as MIZAN's note, not as the person's request (`[HAND-OFF …]` in `BaseAgent._build_messages`; the current request wins):

- **on a project**: the project's hand-off, written by another chat on it;
- **with an agent**, no project: the agent's hand-off, only when the new request is about what that one was about (one shared distinctive concept or more, `niyyah.related`), so "write a poem" does not start from a booking service.

A chat never gets its own hand-off back. It is carried across chats like recall, so a stateless chat, the preference `cross_chat_recall: off` and `learning: off` get none ([daftar.md](daftar.md), [consent.md](consent.md)).

## Never failing a chat

Every read of a store that is missing, damaged or in a data directory that cannot be created returns nothing, and every write returns false and logs a warning; the routes answer 503 when a decision cannot be kept. The chat goes on.

## Forgetting

- **One entry**: Library → Memory, kind Decisions or Hand-off notes, **Forget**; or `DELETE /api/azm/decisions/{id}`.
- **A chat**: deleting it ([Mahw](mahw.md)) erases its decisions, every hand-off it wrote (its own, its project's, its agent's) and any hand-off another chat wrote that quotes one of its decisions; Mahw's check then looks for its words in both tables.
- **Export**: Markdown carries decisions and hand-off notes; JSON carries decisions (an import adds them as the person's own; hand-offs are rebuilt where they are used).

## API

Every route acts on the caller's own data; a chat, project or agent named must be the caller's (404 otherwise).

| Route | Purpose |
|---|---|
| `GET /api/azm/decisions?session_id=&workspace_id=&agent_id=&limit=&offset=` | Your decisions, oldest first |
| `POST /api/azm/decisions` | Add one: `decision`, `why`, and optionally `session_id`, `workspace_id`, `agent_id`, `message_id` (a message of that chat) |
| `DELETE /api/azm/decisions/{id}` | Forget one |
| `GET /api/azm/handoff?session_id=` (or `workspace_id=`, `agent_id=`) | The hand-off of one chat, project or agent |
