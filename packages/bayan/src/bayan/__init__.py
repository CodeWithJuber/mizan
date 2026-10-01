"""Bayan — morphological, root-cognizant tokenizer (مُبَيِّن).

Arabic words are analysed into ``(root, pattern)`` pairs instead of BPE
subword fragments; English words are bridged through a concept map.
Pure standard library — no torch, no numpy, no downloads, deterministic.

"He created man. He taught him al-Bayan (clear expression)." — Quran 55:3-4

Example:
    >>> from bayan import BayanTokenizer
    >>> tok = BayanTokenizer()
    >>> tok.tokenize("الكتاب")
    [{'surface': 'الكتاب', 'root': 'كتب', ...}]

Honest limits: the bundled analyzer is rule-based and has NOT been
benchmarked against CAMeL/Farasa; unknown English words surface as
``<ENG:bucket>`` placeholders rather than invented roots.
"""

from bayan._tok.public_api import BayanTokenizer, NotAvailableError

__version__ = "0.1.0"

__all__ = ["BayanTokenizer", "NotAvailableError", "__version__"]
