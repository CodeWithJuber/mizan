# Debug mode (Muqabala): the base model alone vs MIZAN

Debug mode sends one message to two places and shows the answers side by side:

- **Base model**: the same provider and model MIZAN uses. It gets one plain system prompt ("You are a helpful assistant." with the current date and time in the user's zone, the same clock MIZAN's arm reads), no tools and no memory, and the same per-call output limit as MIZAN's own agent loop (`MIZAN_CHAT_MAX_OUTPUT_TOKENS`, else the model's cap up to 16k; it was 4096 before 28 October). A reasoning model can spend that whole limit thinking; its arm then says "No answer: the model reached its output limit" (`stop_reason: max_tokens`) instead of a bare "No answer". On production on 27 October this happened for the sequence `13, 26, 64, 118, 274, ?, …`: 62 s and 4,160 tokens, no answer, while MIZAN answered 376 in 0.5 s with no model call.
- **MIZAN**: the agent, run the way a chat runs it, with a trace bound so every step is recorded.

MIZAN then checks both answers against what it established itself.

## Where to find it

- **Debug** in the sidebar (Tools). It is shown only to accounts allowed to use it.
- In a chat, turn on **Debug** under the permission switch. Every message you sent then gets a **Compare with the base model** link.

## Who may use it

Admins set this in Settings → System settings → **Debug mode**, or with `MIZAN_DEBUG_MODE`:

| Value | Meaning |
|---|---|
| `admins` | Default. Only admins may compare. |
| `users` | Every signed-in user may compare. |
| `off` | No one may compare. |

A comparison calls the model twice, once for the base model and at least once for MIZAN when it needs language.

## What the trace shows

`tadbir/trace.py` records spans. Their names follow the OpenTelemetry GenAI operations:

| Span | What it records |
|---|---|
| `understand` | The intent Fahm recognised, the language, and who understood it: `fahm`, `lisan`, `lisan_plan` or `mizan_learned` |
| `invoke_agent` | The agent Majlis gave the work to |
| `execute_tool` | Every tool MIZAN ran and every authentic source it read (Quran, hadith), with input and result |
| `chat` `lisan.<task>` | Each Lisan request: its instructions, its prompt, the model Wazn chose and the reply |
| `chat` `<model>` | Each observed provider call, with tokens, cost and latency |
| `verify` | Furqan verdicts, JSON Schema checks of tool arguments, Amanah findings, Tathabbut cross-checks, Qiyas and Silsila rule checks, and checks of a page program or a browse plan |
| `learn` | What Majlis, Ta'allum, Qasd, Hifz, Tajriba, Tajdid and Daftar learned or kept from the result |
| `recover` | A tool call retried after an error |
| `plan` | The tool MIZAN chose, the final plan, and whether the model answered in words |

When no trace is bound, recording does nothing. Ordinary chats pay nothing for it.

## The checks

`tadbir/muqabala.py` checks both answers:

- **Numbers no fact supports.** Any number in an answer is checked against MIZAN's facts: the tool results, the sources it read and its computed values. Arabic-Indic digits count as numbers. This check runs only when MIZAN grounded the answer.
- **Actions with no receipt.** The base model has no tools, so "I ran", "I checked" or "I searched" from it is unbacked.
- **Agreement.** The share of MIZAN's verified values that the base answer states. Numbers the user wrote in the request do not count.
- **Quote fidelity** (Quran and hadith). The base answer's Arabic is compared with the text MIZAN quoted from its source. Marks are ignored, and the letter forms that differ between the Uthmani and the common script are folded together.
  - **coverage**: the share of the source's words given, in order.
  - **precision**: the share of words in the quoted passage that are the source's.
  - The verdict is `matches`, `excerpt` (a correct part), `close`, `differs` or `missing`. The words that differ are listed.
- **Declined or unsure.** Whether either arm abstained.
- **Isnad.** Both answers' claims graded sahih, hasan, da'if or mawdu' ([Isnad](isnad.md)); the base model's are weighed against MIZAN's evidence.
- A line **diff** of the two answers, and their overall similarity.

## Example (live, free OpenRouter model)

| Message | Base model | MIZAN |
|---|---|---|
| `2**100 kitna hota hai?` | Correct, after 5.8 s and 1,120 output tokens | Exact value in 14 ms with no model call |
| `Ayatul Kursi sunao` | Text matches the source (coverage 100%), written from memory | Read from the Tanzil Uthmani source: 0 model calls, 1 source read |
| `Bukhari 1` | Quote **differs**: it gave the wording of another narration (يتزوجها for ينكحها, an added hijra clause) | Bukhari 1 verbatim from the hadith source, with its isnad |

## API

| Route | Purpose |
|---|---|
| `GET /api/debug/status` | `{enabled, access}` for the signed-in account |
| `POST /api/debug/compare` | Runs one comparison. Body: `{prompt, agent_id?, session_id?, workspace_id?, timezone?, permission_mode: auto\|plan}` |
| `GET /api/debug/runs` | Your last 50 comparisons |
| `GET /api/debug/runs/{id}` | One saved comparison |
| `DELETE /api/debug/runs` | Clear your saved comparisons |

- `session_id` gives both arms that chat's earlier turns. Nothing is saved to the chat.
- `permission_mode`: with `auto`, MIZAN runs the tools it chooses, such as sandboxed code and project edits. `plan` is read-only.
- **Storage:** comparisons are kept per user in `$MIZAN_DATA_DIR/private/<user hash>/debug_runs.db`. Long text is trimmed to 6,000 characters. They are never saved to chat history and never become training data.

## Comparisons change nothing

A comparison is an evaluation, so it is stateless (`memory/stateless.py`):
- MIZAN's arm recalls none of your other chats;
- it learns nothing from the run (no learned wording, routing or programs);
- it never becomes a training candidate.

The same holds for a chat sent with `stateless: true`.
