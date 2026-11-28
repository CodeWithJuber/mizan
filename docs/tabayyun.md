# Tabayyun: ask before guessing

> "O you who believe, if a report comes to you, make it clear (*fa-tabayyanu*)" (49:6)

The verse is read two ways. *Fa-tathabbatu*, "make sure of it", is [Tathabbut](automatic-learning.md), which checks a program's result after it runs. *Fa-tabayyanu*, "make it clear", is Tabayyun: before an action the model chose runs, MIZAN checks that what the action would touch is something the person said, and asks once when it is not. The code is in `backend/tadbir/tabayyun.py`; the idea comes from ForgeKit's preflight (`src/preflight.js`), which scores how completely a task is specified and asks below a threshold. MIZAN does not score the wording with cue lists: it uses what it already reads by evidence.

## The rule

MIZAN asks exactly one question when all three hold:

1. **Fahm read no decisive request for this action.** Fahm ([fahm.md](fahm.md)) acts on a family of recipes only when that family is more probable than every other reading together (P > ½). A reading counts as decisive only when Fahm itself made it (not Lisan's mapping of the wording, `understood_by: lisan`), it is a kind of work (not conversation, a salam, a connector request or several parts) and the action is one of that family's own tools (`FAMILY_TOOLS`: a decisive "make a page" covers `workspace_*`, not an email). In `llm` mode, where Tadbir does not run, Tabayyun reads the request with Fahm itself, once per request.
2. **The action changes something.** `approvals.tool_category` is not `read`, with a connector tool's own read-only hint. A read is never asked about.
3. **A reference it needs was never given.** A required argument of the tool's schema holds a reference that is not in the person's messages in this chat, in MIZAN's earlier answers they read, in an answer they gave to Tabayyun, or in what this request's tools returned when they worked (a contact list the model read is no guess; an error or a refusal is no evidence, since it often repeats the arguments it was given). A reference is:
   - a number (an amount, an id, a count);
   - in a one-line value: an email address, a link, a date (`2026-12-04`), a time (`15:30`), a phone number, a handle (`@amina`, `#general`);
   - a value that is a single token with a digit or a slash (an id, `owner/repo`).

   A link counts as given without its scheme or a final slash; a handle when its name is a word the person used; a phone number by its digits; a value that is one of the schema's own `enum` choices is the tool's, not a guess. Words the action writes (a message body, a command, a program: text of more than one line, or a line with no reference in it) are never asked about.

Only actions whose arguments a model proposed are read: a tool call the model chose (`_model_directed`) and a connector tool MIZAN chose whose arguments Lisan filled (`amal`, `_arguments_proposed`). MIZAN's own recipes take their arguments from its parsers of the person's words and are not asked about. Plan mode refuses changes before this check; a held action its owner allowed runs exactly as held.

## What happens

| Where | What MIZAN does |
|---|---|
| An interactive chat | One question card in the run timeline (the elicitation card connectors use, kind `question`, answered with `POST /api/chat/elicitations/{id}`): *"Before send_email runs: which to do you mean? You have not said it, so “bob@example.com” would be a guess."*, its field filled with the value the model proposed. Nothing runs while it waits (5 minutes). The answer joins the person's words for this request, and the model is told to call the tool again with it; the check then reads the call again. Decline (or no answer) and the action does not run. |
| A run no one is watching (watcher, schedule, trigger, queue, Bab) | The action is held with its exact parameters for the owner (`approvals.hold_action`), its reason the question MIZAN would have asked. Allowed, it runs exactly once, as held. |
| No one to ask at all (no approval context, or no live chat) | The action does not run; the model is told to ask in its answer instead of guessing. |

One question per request: after it, a call that still holds an unsaid reference is not run, and the model is told to ask in its answer. Every request's question is reported without its answer as `usage.tabayyun` (`asked`, `tool`, `argument`, `outcome`: answered, declined, held or unasked), and an unanswered question is an open item of the chat's [hand-off](azm.md).

## Setting

`MIZAN_TABAYYUN` = `ask` (default) | `off`, in Settings → Developer → System settings, group Agents ([admin-settings.md](admin-settings.md)). It applies at once. Tests leave it at `ask`: the whole suite passes with it on, since scripted tools there either name what the request says or have no schema with required references.

## What it does not do

- It never reads the wording for vagueness ("make it better"): a request Fahm cannot place is answered or acted on as before; only an action resting on an unsaid reference waits.
- It is not Amanah. A reference taken from a page the run read is grounded for Tabayyun; Amanah's own rule (a change the model chooses after an injection finding needs a person) still applies ([amanah.md](amanah.md)).
- It never blocks on missing evidence: with no schema, no required argument or no request to read against, nothing is asked.
