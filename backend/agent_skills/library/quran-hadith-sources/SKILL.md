---
name: quran-hadith-sources
description: Answer questions about Islam using authentic, precisely cited sources — Quran references (surah:ayah) and hadith with collection, number and authenticity grading. Use for any question about the Quran, hadith, sunnah, Islamic rulings, history or Arabic Quranic terms.
license: MIT
metadata:
  author: mizan
  version: "1.0"
---

# Quran and hadith with authentic sources

The Quran and authentic Sunnah come first. Accuracy of attribution matters more than
length: never invent, paraphrase as a quote, or guess a reference.

## Citing the Quran
- Give the reference as **Surah name surah:ayah** (e.g. Al-Baqarah 2:255).
- Quote the Arabic only when you are certain of the exact text; otherwise give the
  meaning and the reference. Name the translation used for any English/Urdu rendering
  (e.g. Sahih International, Taqi Usmani) and say it is a translation of the meaning.
- When explaining, distinguish the verse itself from tafsir; name the tafsir
  (Ibn Kathir, al-Tabari, al-Qurtubi, etc.) when you rely on one.

## Citing hadith
- Give the collection and number (e.g. Sahih al-Bukhari 1, Sahih Muslim 2564,
  Sunan Abi Dawud 4607) and the grading with who graded it when it is outside the
  two Sahihs (e.g. "graded sahih by al-Albani").
- Never present a weak (da'if) or fabricated (mawdu') narration as established;
  if a well-known saying has no authentic source, say so plainly.
- If you are not sure of the exact number or wording, say that the reference should
  be verified rather than giving a precise-looking citation.

## Rulings (fiqh)
- Present the evidence first (Quran, then authentic hadith), then the positions of
  the major schools where they differ, without inventing consensus.
- For personal fatwa questions, give the general evidence and advise consulting a
  qualified scholar for the specific situation.

## Method
- Use `query_knowledge` / `recall_memory` for sources the user ingested, and
  `web_search` + `web_browse` to verify references on reliable sites (quran.com,
  sunnah.com) before citing them when in doubt.
- Answer in the user's language; keep Arabic terms with a short explanation.
