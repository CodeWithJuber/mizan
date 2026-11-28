# Mahw (محو): forgetting for real, with a receipt

Deleting a chat, or forgetting a note, removes it from every place MIZAN keeps it. It also removes what MIZAN derived from it. MIZAN then checks that nothing is left and gives you a receipt. The code is in `backend/memory/mahw.py`.

## What deleting a chat removes

| Store | What goes |
|---|---|
| Chat | Its title, its messages, its running summary, its request receipts, Muhasaba's reviews of its answers, its artifacts (with their versions), its plan file, actions held for it, and the images attached in it (Basar), unless another of your chats still shows the same picture |
| Your notes | Notes made from this chat (source `chat:<id>`), with their vectors, and the memory-strength reviews logged for them (`memory_reviews`: grade and time, no words). A memory-strength fit adopted after those reviews were logged goes back to FSRS's defaults ([Tadhkir](quranic-algorithms.md#fitted-on-mizans-own-log-tadhkirrest-run-by-nawm)) |
| What MIZAN learned while answering | Task records, wisdom, and knowledge-graph entries (with their links) for the chat's requests. Also the intents (Qasd), wording (Ta'allum), programs (Hifz), source-settled sentences (Ahl al-Dhikr's `ilm`), answers kept to give again (Talaqqi, which name their chat) and repair lessons (Tajriba) learned from those requests. A repair lesson names the chats it was learned in; one also used in another chat goes too, because its words or its repair came from the erased chat |
| Learning record | The chat's notes in the live learning record (Sijill, Agents → Majlis → Learning now) and the failure signatures it gave the instruction harness (Tajdid) |
| Lessons, earned skills, replays | In your `learning.db`: the chat's answers and every lesson from corrections that drew on them (Islah; one also confirmed in another chat goes too), the verified runs it counted toward a skill and any skill they earned (Itqan, removed from your skills), and its runs in replay families, whose evidence is then counted afresh (Athar) ([automatic learning](automatic-learning.md#where-they-live)) |
| Episodic memory | The chat's episodes (what you said in it, kept as weak traces) and every strengthening it gave an episode from another chat ([episodic memory](episodic-memory.md)) |
| Learner | Training candidates captured from the chat, with their reviews |
| Language reader | A version of MIZAN's own language reader that learned the chat's reviewed words while resting is dropped, and the newest version that did not becomes the current one (weights cannot have one text subtracted; [Ruh reader](ruh-reader.md)) |
| Debug mode | Saved comparison runs of the chat's requests |
| Pathways (Masalik) | Rebuilt from the notes and task records you keep. A Hebbian update cannot be subtracted, so the network is rebuilt rather than edited. 5,000 records take under a second |

A preference you set in the chat stays in your Daftar. It is a setting, not part of the conversation, and you can forget it there. It stops pointing to the deleted chat.

Action receipts (Sakk) stay: they hold which tool ran and how it ended, with keyed digests only and no words from the chat. The erase itself is recorded as a Sakk receipt of kind `erase` (the chat id as a keyed digest, with the counts removed and traces found).

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
- what was deliberately kept (the Sakk receipts, and preferences set in the chat)
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
