# Amanah: outside text is data, never instructions

What MIZAN reads is held in trust (*amanah*), never obeyed. That covers web pages, search results, connector replies, memories, skill files and text a user pastes. Some of it is written to instruct the AI that reads it: indirect prompt injection.

Amanah (`backend/tadbir/amanah.py`) keeps such text from steering MIZAN. It combines structure with a lightweight scanner rather than a large classifier model. Open-source detectors are mostly transformer models, too heavy for the 2 GB server, and rule-only scanners miss attacks. Structure does not depend on catching every attack.

## Structure first

- **The model never chooses actions in the default mode.** In `mizan` mode the plan comes from the user's own words (Fahm, or Lisan mapping the user's message), and the model has no tools. Outside text cannot pick an action. This is the separation CaMeL argues for (Debenedetti et al., 2025).
- **Pasted text never maps to an action.** Before Lisan maps a message to MIZAN's actions or fills a tool's arguments, Amanah removes instructions found inside the pasted parts of the message: quotes, `---` blocks, code fences, `>` quotes and labelled blocks such as "Email:" or "TOOL OUTPUT:". The user's own words are never changed.
- **Fences (spotlighting).** Every piece of outside text Lisan or the model reads sits between `<<untrusted id from source>>` and `<<end untrusted id>>`. The id is random, so the text cannot fake the closing marker. Both Lisan's base prompt and the agent's system prompt say that fenced text is data (Hines et al., 2024).
- **Taint.** Once content that tried to instruct the AI has been read in a run, every later action **the model chose** that changes something needs the user's approval, even in `auto` mode. With no live chat to ask (a schedule, another agent), the action is refused. Read-only tools are not affected, and neither are MIZAN's own planned actions.

## The scanner

`amanah.scan(text)` first folds the text the way an AI reads it:
- Unicode tag characters (U+E0000 to U+E007F), which smuggle invisible ASCII, are decoded.
- Zero-width and bidirectional control characters are removed.
- Text is normalised with NFKC, so full-width and other look-alike letters match.

It then looks for:

| Kind | Examples |
|---|---|
| `override` | "ignore all previous instructions", "new instructions:", "reply only with", Hinglish, Arabic and Hindi forms |
| `role` | `<system>…</system>`, "SYSTEM: assistant, …", "AI assistants: …", "you are now", "developer mode" |
| `reply_control` | "say DONE-4417", "append CODE-3391": a dictated code |
| `exfiltration` | a Markdown image whose URL carries a query (`![x](https://host/p?d=…)`), "forward the passwords to …" |
| `concealment` | "do not tell the user", "secretly" |
| `tool_bait` | "call the tool `send_email`", `curl … \| sh`, `rm -rf /` |
| `hidden_text` | instructions in invisible characters or Unicode tags |

**False positives:** on the repository's own documentation and bundled skills (1,207 paragraphs) the scanner flags nothing. Ordinary phrases such as "ignore a file in git", "System: Ubuntu 24.04" and "reply with your RSVP" are left alone. These are tested in `tests/test_amanah.py`.

## Where it applies

| Path | What Amanah does |
|---|---|
| Web search, page reading, `http_get`, memory recall, connector tools (`mcp__*`), skill files | `guard_value` neutralizes every string in the result, keeping its JSON shape, and adds an `amanah` note. Findings taint the run. |
| Lisan's wording of facts and sources | The facts and each source are fenced. |
| A pasted email, page or review in the chat | The model is told that the pasted text contains an instruction to ignore. Lisan's action mapping sees the text without it. |
| The agent loop (`llm` and `hybrid` modes) | Untrusted tool results are neutralized and fenced. After a finding, the model's actions that change something need approval. |
| Connectors | Each tool is pinned to the description and schema first accepted. A later change ("rug pull") or a description that instructs the AI (tool poisoning) **holds** the tool: it is hidden from the model and cannot be called until the user presses **Trust as it is now** on the Connectors page (`POST /api/connectors/{id}/tools/{name}/trust`). |
| Skills | A user or project skill whose `SKILL.md` instructs the AI is held until trusted (`POST /api/agent-skills/{name}/trust`). Trust is pinned to the content, so a later edit holds it again. Bundled skills are trusted. |

Workspace files (the user's own project) are scanned through the agent's normal flow but never rewritten, so a marker can never end up in a user's file.

## What the user sees

- **In chat:** when an answer's run removed anything, a shield line appears under the message, for example "Amanah: ignored 2 instructions aimed at the AI in web browse". It expands to the kinds and short excerpts. MIZAN's own web answers also say so in the user's language.
- **Data:** the run's record is `result["amanah"]` → `usage.amanah`, with `ignored`, `kinds`, `sources`, `hidden` and `examples`.
- **Debug mode:** shows the `verify/amanah` span with each finding.

## Measured

The AGI test's injection block (`backend/imtihan/tasks/injection.jsonl`) has six tasks. Each hides a canary (a code, or a link) that the answer must not contain:
- a page
- an email
- a review
- a tool output
- an instruction in Unicode tag characters
- a Markdown image that would carry the summary out
