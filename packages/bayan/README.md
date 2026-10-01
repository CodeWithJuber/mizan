# Bayan — morphological tokenizer (مُبَيِّن)

Bayan is Ruh's morphological tokenizer: Arabic words are analysed into
**(root, pattern)** pairs instead of BPE subword fragments. English words are
bridged through a concept map to shared roots.

```python
from bayan import BayanTokenizer

tok = BayanTokenizer()
tok.tokenize("الكتاب")
# [{'surface': 'الكتاب', 'root': 'كتب', 'root_id': ..., 'pattern': 'NOUN', 'pattern_id': ...}]

tok.roots("العلم نور")     # ['علم', 'نور']
tok.patterns("العلم نور")  # ['NOUN', 'NOUN']
tok.fertility("العلم نور") # 1.0 — one morphological token per word, by construction
```

> "He created man. He taught him al-Bayan (clear expression)." — Quran 55:3-4

## Why

Subword tokenizers (BPE/WordPiece) shred Arabic morphology: one root scatters
across dozens of unrelated fragments. Bayan keeps the root — the unit Arabic
grammar has used for 1,400+ years — so models see *كتب* in *كتاب*, *كاتب*,
*مكتبة* as the same root, not three coincidences.

## Install

```bash
pip install bayan-tokenizer
```

Zero dependencies. Pure standard library — no torch, no numpy, no downloads.
Works on Python 3.9+.

## API

| Method | Returns |
|---|---|
| `tokenize(text)` | list of `{surface, root, root_id, pattern, pattern_id}` — one per word |
| `roots(text)` | resolved linguistic roots (stopwords and `<ENG:…>` placeholders excluded) |
| `patterns(text)` | morphological pattern name per word |
| `fertility(text)` | tokens-per-word (1.0 by construction; reported for honest BPE comparison) |
| `vocab_size` | `n_roots × n_patterns` |
| `supported()` | `True` when the tables/lexicon path loaded |

Stopwords yield `root == ""` and pattern `"STOPWORD"`.

## Honest limits

- The bundled analyzer is **rule-based** (tables + lexicon). It has **not**
  been benchmarked against CAMeL Tools or Farasa — do not claim SOTA.
- Unknown English words surface as `<ENG:bucket>` placeholders, never as
  invented roots.
- `BayanTokenizer.with_model(path)` is an explicit stub and raises
  `NotAvailableError`: model-backed Bayan is not implemented in this release.

## Development

The package vendors the tokenizer from the Mizan monorepo
(`ruh_model/tokenizer/` + `backend/qca/roots.py`). After changing the
upstream sources, re-vendor and rebuild:

```bash
python packages/bayan/scripts/sync_vendor.py
cd packages/bayan && python -m build && twine check dist/*
```

See `../../docs/BAYAN_RELEASE.md` for the full release checklist.

## License

MIT — see [LICENSE](LICENSE).
