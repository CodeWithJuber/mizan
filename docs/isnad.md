# Isnad (إسناد): what supports each claim

Every answer carries its **Isnad**: the answer split into claims (sentences and quoted passages), each graded by what supports it. The grades are the terms of hadith science.

| Grade | Meaning | When |
|---|---|---|
| **Sahih** (صحيح) | MIZAN established or verified it | MIZAN calculated it, read it verbatim from its Quran or hadith source, ran it in its sandbox and checked it, or proved a rule on every example. Also any claim verified against the evidence. |
| **Hasan** (حسن) | Evidence MIZAN gathered supports it | Its numbers are in a tool result, it cites a real source, or most of its words are in the evidence. Not verified. |
| **Da'if** (ضعيف) | Only the language model's words | Nothing MIZAN holds supports it, or one of its numbers has no evidence |
| **Mawdu'** (موضوع) | Fabricated | It claims an action that never happened ("I checked…"), cites a source that does not exist, or links to a page MIZAN never found |

The **Mizan** (balance) is the share of the answer's claims graded sahih or hasan.

## Where it shows

- **Chat:** under each answer, an **Isnad** bar with its grade counts. Open it to see each claim, its grade and its support. It is saved with the message (`usage.isnad`).
- **Debug mode:** both answers are graded. The base model's claims are weighed against MIZAN's evidence, so a base claim that contradicts MIZAN's facts shows as da'if and an invented action as mawdu'.
- **AGI test:** each arm's average share of supported claims and its count of fabricated claims.

## How it works

`tadbir/isnad.py` grades by rule: numbers, citations, links and word overlap with the evidence. It shows what supports a claim, not whether the claim is true.

There are three cases:

1. **MIZAN's own established work** (compute, quran, hadith, waqt, a verified run, a proven Qiyas rule, passed project checks). Every claim is sahih, and the basis is named: "MIZAN calculated it exactly", "read verbatim from MIZAN's Quran source", and so on.
2. **Answers Lisan worded from evidence** (web search and read, tool results, recall). Each claim is weighed against the facts and tool receipts of that run.
3. **The model's words with no evidence.** Every claim is da'if, unless it fabricates an action, a citation or a link, which makes it mawdu'.

Code blocks, source lists and MIZAN's italic notes are not claims and are not graded.
