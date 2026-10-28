# Sidq (صدق): the Truth Gate

No claim MIZAN can prove false reaches the user. Muhasaba reviews answers once a day; Sidq (`backend/tadbir/sidq.py`) checks each answer **before it is shown**, with the same proofs and no model call.

| What | How MIZAN checks | What strict mode does |
|---|---|---|
| Arithmetic stated as `expression = value` | Recomputed exactly (MIZAN's calculator) | The wrong value is replaced by the right one |
| Quran or hadith quoted with a reference | Compared with the text MIZAN reads from its authentic source (Arabic folded across scripts) | The altered quote is replaced by the source text, with the reference |
| An action claimed with no receipt ("I ran the code") | The Isnad ledger grades it mawdu' (fabricated) | The sentence is removed |
| A citation to a source that does not exist (`[7]` with 3 sources) | The Isnad ledger | The marker is removed |
| A link MIZAN never found | Opened (public addresses only; up to five links, each redirect hop checked, at most five hops) | Removed when the page is gone (404/410) or the host does not exist; never judged when MIZAN is offline |

Answers MIZAN itself verified (computed, quoted from source, run and checked) skip the gate: they are already established.

### How a quote is read

- **Each quote under its own reference.** A reference names a number, so a verse's own words are never read as one. Each Arabic line belongs to the reference given most recently above it, or on the same line. An answer quoting 112:1 and then 2:255 has each passage checked against its own ayah, never both against the first. Up to four references are checked.
- **Only attempts to quote.** Each stretch of Arabic is judged on its own. It counts as a quote when most of its words are the source's, or when it is at least half as long as the source (a passage given as the ayah, however different). Arabic terms used in an explanation ("here يوم means a stage") are not quotes, so a correct answer that discusses a word is not marked as a misquote.
- **Every altered quote is replaced** by its own source text, the last one first, so one replacement never moves the lines of another.

## Hadith cited to the wrong book (`tadbir/hadith_index.py`)

A quote the answer gives as a hadith of one of the six books (`"…" (Sahih al-Bukhari)`) is looked up in MIZAN's own index of their English text: the hadith-api editions `tadbir/hadith.py` already quotes from, downloaded once into `$MIZAN_DATA_DIR/hadith` (about 20 MB) and indexed with BM25. Translations of one hadith differ from book to book ("actions are judged by intentions" is "the reward of deeds depends upon the intentions" in Bukhari's), so words alone never settle that a book lacks it:

1. The narrations that hold more than half of the quote's distinctive information (`ahl_dhikr.about`) are found in the other books.
2. The cited books' closest narrations (BM25) are read against the quote by the NLI model Ahl al-Dhikr uses; if one says it (entailment is the MAP label), the citation stands.
3. Otherwise, the other books' narrations that say it are reported: "*"The martyr has six distinctions with Allah…" is found in Sunan Ibn Majah 2799, Jami` at-Tirmidhi 1663, not in Sahih al-Bukhari and Sahih Muslim*" (the 3.3.0 benchmark's false reference), with sunnah.com links.

The answer's text is never changed by this check; it is marked under the answer (kind `hadith_source`). Without the index or the NLI model nothing is claimed. `MIZAN_HADITH_INDEX=off` turns it off.

## Settings

`MIZAN_TRUTH_GATE` in System settings:

- `strict` (default): correct and remove
- `flag`: keep the text and list each problem
- `off`: no gate

## What the user sees

Under the answer, a **Truth Gate** line lists what was corrected, removed or marked. The note is never added to the answer's text (`usage.sidq.note`); a Telegram, WhatsApp or email reply, which has no notes view, prints it on its own line. The report is also in the message's usage (`usage.sidq`), and each correction appears in the live learning record (Learning → Learning now).
