# Mahw (محو): forgetting for real, with a receipt

Deleting a chat, or forgetting a note, removes it from every place MIZAN keeps it. It also removes what MIZAN derived from it. MIZAN then checks that nothing is left and gives you a receipt. The code is in `backend/memory/mahw.py`.

## What deleting a chat removes

| Store | What goes |
|---|---|
| Chat | Its messages, its running summary, its request receipts, Muhasaba's reviews of its answers, its artifacts, its plan file, and actions held for it |
| Your notes | Notes made from this chat (source `chat:<id>`), with their vectors |
| What MIZAN learned while answering | Task records, wisdom, and knowledge-graph entries for the chat's requests. Also the intents (Qasd), wording (Ta'allum) and programs (Hifz) learned from those requests |
| Learner | Training candidates captured from the chat, with their reviews |
| Debug mode | Saved comparison runs of the chat's requests |
| Pathways (Masalik) | Rebuilt from the notes and task records you keep. A Hebbian update cannot be subtracted, so the network is rebuilt rather than edited. 5,000 records take under a second |

A preference you set in the chat stays in your Daftar. It is a setting, not part of the conversation, and you can forget it there. It stops pointing to the deleted chat.

A chat that is still answering cannot be deleted (409). Stop it first.

## The check

After erasing, Mahw cuts every erased text (messages, summary, notes) into 20-character pieces, at most 400 of them. A 20-character run of someone's words almost never recurs by chance. It looks for each piece in:

- your remaining chat messages and summaries
- notes
- task records
- wisdom
- the knowledge graph
- learner rows
- debug runs

It also asks the vector store whether the erased notes' vectors are gone.

Matches are counted as follows:

- **Same words in another chat:** a piece that also appears in one of your other chats explains itself. You said it again there.
- **Any other copy:** counted as a trace and named by store. For example, you saved the same words as a separate note. Mahw never hides a copy it did not remove.

## The receipt

The receipt records:

- what was removed, per store
- how many checks ran
- how many traces were found, per store
- what was deliberately kept
- what MIZAN cannot reach: text already sent to a model provider is held under that provider's own retention policy

It keeps none of the erased content and no hashes of it.

Receipts are stored in `$MIZAN_DATA_DIR/mahw.db` and listed at `GET /api/daftar/receipts`.

## Where to use it

- **Chat → History:** the bin next to a chat deletes it after you confirm. A notice shows what was removed and the result of the check.
- **Daftar:** forgetting a note, one at a time or by topic, goes through Mahw too, so the note also leaves the vector store and the pathways.

## API

| Route | Purpose |
|---|---|
| `DELETE /api/chat/{session_id}` | Delete one of your chats and everything derived from it; returns the receipt |
| `POST /api/daftar/forget` | Forgetting notes returns a `receipt` |
| `GET /api/daftar/receipts` | Your receipts, newest first |
