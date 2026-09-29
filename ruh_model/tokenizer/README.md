# Bayan Tokenizer — public package (مُبَيِّن)

Bayan is Ruh's morphological tokenizer: Arabic words are analysed into
**(root, pattern)** pairs instead of BPE subword fragments.

```python
tok.tokenize("الكتاب")
# [{'surface': 'الكتاب', 'root': 'كتب', 'root_id': 42,
#   'pattern': 'NOUN', 'pattern_id': 7}]
```

This directory ships Bayan as a **free, dependency-free, pip-friendly**
library — the top-of-funnel on-ramp from the Ruh use-case study (#7):
*Bay an tokenizer, free + MIT* → here: free under the repo's license,
zero dependencies.

## Install

From the repo root:

```bash
git clone https://github.com/CodeWithJuber/mizan
cd mizan
pip install -e .          # installs the pymizan project (backend/nlp/CLI)
```

`ruh_model/` is used from the source tree (it is not in the wheel's
`packages` list yet). No torch, no numpy, no downloads — the public facade
is pure standard library.

### Torch-free import (important)

The repo's `ruh_model/__init__.py` unconditionally imports torch (via
`RuhModel`). In environments **without** torch, do NOT `import ruh_model…`;
load the facade directly by file path:

```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "bayan_public_api", Path("ruh_model/tokenizer/public_api.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

tok = mod.BayanTokenizer()
print(tok.roots("الكتاب يكتب"))   # ['كتب', 'كتب']
```

Where torch IS installed, the normal package import also works:
`from ruh_model.tokenizer.public_api import BayanTokenizer`.

## Quickstart

```python
tok = BayanTokenizer()

tok.tokenize("العلم نور")
# [{'surface': 'العلم', 'root': 'علم', ...}, {'surface': 'نور', ...}]

tok.roots("الكتاب يكتب")      # ['كتب', 'كتب']  (stopwords/unknowns excluded)
tok.patterns("الكتاب يكتب")   # ['NOUN', 'VERB_PRESENT']
tok.fertility("العلم نور")    # 1.0  (one morphological token per word)
tok.supported()               # True (torch-free tables/lexicon path ready)
tok.vocab_size                # roots × patterns
```

Model-backed decoding is intentionally **not** faked:

```python
BayanTokenizer.with_model("weights.bin")
# NotAvailableError: Bayan model weights not found at weights.bin. ...
```

## API reference (summary)

| Method | Returns |
|---|---|
| `tokenize(text)` | `list[{"surface","root","root_id","pattern","pattern_id"}]`, one per word; `[]` on empty input |
| `roots(text)` | `list[str]` — resolved linguistic roots only (stopwords and `<ENG:…>` placeholders excluded) |
| `patterns(text)` | `list[str]` — pattern name per word (`"STOPWORD"` for stopwords) |
| `fertility(text)` | `float` — tokens per word; `1.0` by construction, `0.0` when no words |
| `supported()` | `bool` — torch-free pipeline ready |
| `vocab_size` | `int` — roots × patterns |
| `with_model(path)` | always raises `NotAvailableError` — no silent fallback |

Type hints and docstrings on every public method; see
[`public_api.py`](public_api.py) for details.

## Fertility playground

```bash
python scripts/bayan_fertility.py
```

Measures Bayan's tokens-per-word against a whitespace baseline on a small
Arabic sample, plus a BPE comparison **only if** the `tokenizers` library is
installed (otherwise it skips with an explicit note). Every number printed
is measured — nothing is invented, and the script says so. Fertility alone
is not a quality claim; the real Bayan-vs-BPE question needs a
corpus-trained BPE and downstream evals (study track #17).

## Running the tests

```bash
BAYAN_REPO=$PWD PYTHONPATH=$HOME/workspace/bayan-pytest-stub \
  python -m pytest -p bayan_torchfree_stub --noconftest \
  ruh_model/tests/test_bayan_public_api.py
```

(The `-p` stub plugin bypasses the torch-pulling `ruh_model/__init__.py`
at collection time; see `public_api.py` module docstring for why. In
torch environments the plain `pytest` invocation works.)

```bash
ruff check ruh_model/tokenizer/public_api.py \
           ruh_model/tests/test_bayan_public_api.py \
           scripts/bayan_fertility.py
ruff format --check ruh_model/tokenizer/public_api.py \
                    ruh_model/tests/test_bayan_public_api.py \
                    scripts/bayan_fertility.py
```

## License

Bayan ships **free** under the repository's license: **Apache-2.0**
(see repo-root `LICENSE`). That is permissive — commercial use,
modification and distribution are allowed, with attribution and a license
notice. Note: the use-case study (#7) aspires to MIT for a standalone
`bayan` package; the repo as it stands is Apache-2.0, not MIT.
Re-licensing (or a standalone MIT `pip install bayan`) is the repo owner's
explicit decision, not something this packaging assumes.

## Honest limitations

- The bundled analyzer is **rule-based and heuristic** — it misanalyses
  some bare forms today (e.g. `كتاب` alone). Accuracy has **not** been
  benchmarked against CAMeL/Farasa; that eval is tracked separately
  (study Part B, Phase 0). Test assertions pin *measured* behaviour.
- English words resolve through a concept map; unknown English words
  surface as deterministic `<ENG:bucket>` placeholders mapped to `UNK` —
  never invented roots.
- `vocab_size` is small (tens of roots in the bundled tables); the
  table-generation pipeline stays private per the study's moat note.
