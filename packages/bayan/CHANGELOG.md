# Changelog

## 0.2.0 — prepared 2026-10-28 (not yet on PyPI)

Root ids and pattern names change for the words below, so token ids from
0.1.0 are not stable across this upgrade.

- **ك, ب, ل, ف or و as a root letter.** When a word starts with one of these
  letters, the analyzer keeps it as a root letter if only that reading gives a
  root the bundled lexicon knows. كتاب, كتب and كاتب now give the root كتب; 0.1.0
  gave تاب, تب and اتب.
- **Nouns after ال, ب or ك.** These prefixes attach only to nouns, so the stem
  after them is never read as a verb. العلم and بالقلم are now `NOUN`; 0.1.0
  said `VERB_PAST`.
- **Active participle.** The fa'il shape needs alef right after the first root
  letter: كاتب is `ACTIVE_PARTICIPLE`, كتاب is `NOUN`.
- **Quranic alef wasla (ٱ, U+0671)** is read as a plain alef, so ٱلكتاب gives
  the root كتب.
- The root vocabulary validates its id mapping on load.
- The root accuracy on the 172-word QAC-derived gold set is 81/172 (47.1%);
  0.1.0 scored 60/172 (34.9%).
- `requires-python` is now `>=3.11`.

## 0.1.0 — 2026-09-29

First release.
