#!/usr/bin/env python3
"""Bayan fertility playground — honest, measured tokenizer comparison.

Measures tokens-per-word ("fertility") on a small Arabic sample for:

* Bayan (morphological, via the torch-free public facade) — measured;
* whitespace words (baseline: 1.0 by definition) — measured;
* BPE via the ``tokenizers`` library — measured ONLY if the library is
  installed; otherwise skipped with an explicit note. Nothing is invented.

Bayan emits exactly one (root, pattern) token per word, so its fertility is
1.0 by construction. That is not a quality claim — the interesting question
for the ablation paper (study track #17) is downstream quality, not this
number. This script exists so nobody quotes an unmeasured figure.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_API = REPO_ROOT / "ruh_model" / "tokenizer" / "public_api.py"

SAMPLE_AR = """خلق الإنسان علمه البيان
العلم نور يهدي العقول
الكتاب صديق القارئ"""


def _load_facade():
    """Load the Bayan public API by file path (torch-free)."""
    spec = importlib.util.spec_from_file_location("bayan_public_api", PUBLIC_API)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Bayan public API from {PUBLIC_API}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bayan_public_api"] = module
    spec.loader.exec_module(module)
    return module


def _bpe_fertility(text: str) -> float | None:
    """Train a toy BPE on the sample and measure its fertility.

    Returns None when the ``tokenizers`` library is unavailable. The BPE is
    trained on the sample itself, so the figure is illustrative only — a
    real comparison needs a BPE trained on a proper Arabic corpus.
    """
    try:
        from tokenizers import Tokenizer
        from tokenizers.models import BPE
        from tokenizers.pre_tokenizers import Whitespace
        from tokenizers.trainers import BpeTrainer
    except ImportError:
        return None

    tokenizer = Tokenizer(BPE(unk_token="[UNK]"))  # noqa: S106 -- not a password, tokenizer special token
    tokenizer.pre_tokenizer = Whitespace()
    trainer = BpeTrainer(vocab_size=200, special_tokens=["[UNK]"])
    tokenizer.train_from_iterator([text], trainer)

    words = text.split()
    pieces = sum(len(tokenizer.encode(word).tokens) for word in words)
    return pieces / len(words) if words else 0.0


def main() -> int:
    facade = _load_facade()
    tok = facade.BayanTokenizer()

    words = SAMPLE_AR.split()
    n_words = len(words)
    bayan_tokens = len(tok.tokenize(SAMPLE_AR))
    bayan_fertility = bayan_tokens / n_words
    whitespace_fertility = n_words / n_words  # 1.0 by definition
    bpe_fertility = _bpe_fertility(SAMPLE_AR)

    print("Bayan fertility playground (measured, not claimed)")
    print("=" * 52)
    print(f"Sample: {n_words} Arabic words")
    print()
    print(f"  {'tokenizer':<28}{'fertility (tok/word)'}")
    print(f"  {'-' * 28}{'-' * 20}")
    print(f"  {'Bayan (morphological)':<28}{bayan_fertility:.2f}")
    print(f"  {'whitespace baseline':<28}{whitespace_fertility:.2f}")
    if bpe_fertility is None:
        print(f"  {'BPE (tokenizers lib)':<28}{'SKIPPED — `tokenizers` not installed'}")
    else:
        print(f"  {'BPE (toy, trained on sample)':<28}{bpe_fertility:.2f}")
    print()
    print("Verdict: Bayan emits exactly one morphological token per word")
    print(f"(fertility {bayan_fertility:.2f}, deterministic). The whitespace baseline")
    print("is 1.00 by definition, so fertility alone is not a quality claim —")
    print("Bayan's bet is linguistically grounded tokens (root+pattern), not")
    print("fewer tokens. A real Bayan-vs-BPE comparison needs a corpus-trained")
    print("BPE and downstream evals (see study track #17, not this script).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
