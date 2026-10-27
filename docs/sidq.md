# Sidq (صدق): the Truth Gate

No claim MIZAN can prove false reaches the user. Muhasaba reviews answers once a day; Sidq (`backend/tadbir/sidq.py`) checks each answer **before it is shown**, with the same proofs and no model call.

| What | How MIZAN checks | What strict mode does |
|---|---|---|
| Arithmetic stated as `expression = value` | Recomputed exactly (MIZAN's calculator) | The wrong value is replaced by the right one |
| Quran or hadith quoted with a reference | Compared with the text MIZAN reads from its authentic source (Arabic folded across scripts) | The altered quote is replaced by the source text, with the reference |
| An action claimed with no receipt ("I ran the code") | The Isnad ledger grades it mawdu' (fabricated) | The sentence is removed |
| A citation to a source that does not exist (`[7]` with 3 sources) | The Isnad ledger | The marker is removed |
| A link MIZAN never found | Opened (public addresses only) | Removed when the page is gone (404/410) or the host does not exist; never judged when MIZAN is offline |

Answers MIZAN itself verified (computed, quoted from source, run and checked) skip the gate: they are already established.

## Settings

`MIZAN_TRUTH_GATE` in System settings:

- `strict` (default): correct and remove
- `flag`: keep the text and list each problem
- `off`: no gate

## What the user sees

Under the answer, a **Truth Gate** line lists what was corrected, removed or marked; the answer ends with a short note when the gate changed it. The report is also in the message's usage (`usage.sidq`), and each correction appears in the live learning record (Learning → Learning now).
