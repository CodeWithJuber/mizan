"""Bayan public API — clean, torch-free facade over the Bayan tokenizer.

Bayan is Ruh's morphological tokenizer: Arabic words are analysed into
``(root, pattern)`` pairs (e.g. ``الكتاب`` → root ``كتب``, pattern ``NOUN``)
instead of BPE subword fragments. This module exposes that capability as a
small, dependency-free API:

* pure standard library — no torch, no numpy, no downloads;
* deterministic: tables + rule-based lexicon, same input → same output;
* honest about limits: the bundled analyzer is rule-based and has NOT been
  benchmarked against CAMeL/Farasa; unknown English words surface as
  ``<ENG:bucket>`` placeholders rather than invented roots.

Import note: the repo's ``ruh_model/__init__.py`` unconditionally imports
torch (via ``RuhModel``). In torch-less environments, load this file directly
by path instead of through the package::

    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "bayan_public_api", Path("ruh_model/tokenizer/public_api.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    BayanTokenizer = mod.BayanTokenizer

Where torch IS installed, the normal package import also works.
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path
from typing import Any

__all__ = ["BayanTokenizer", "NotAvailableError"]


class NotAvailableError(RuntimeError):
    """Raised when the model-backed Bayan path is requested.

    The torch-free tables/lexicon path is the only supported path in this
    release. This error is never silent: it always explains what is missing
    and what to use instead.
    """


def _tokenizer_dir() -> Path:
    """Directory containing this file (``ruh_model/tokenizer``)."""
    return Path(__file__).resolve().parent


def _ensure_package_stubs() -> None:
    """No-op in the standalone ``bayan`` package.

    The vendored copy imports ``bayan._tok.*`` directly, so no
    ``sys.modules`` stubs are needed. The numpy/Q28 guard lives in the
    vendored ``bayan.py`` instead.
    """
_inner_modules: types.SimpleNamespace | None = None


def _load_inner_modules() -> types.SimpleNamespace:
    """Load the real tokenizer modules by dotted name (cached).

    Works both through the real package (torch installed) and through the
    stub packages above (torch-less): either way the same module files are
    executed exactly once.
    """
    global _inner_modules
    if _inner_modules is None:
        _ensure_package_stubs()
        _inner_modules = types.SimpleNamespace(
            bayan=importlib.import_module("bayan._tok.bayan"),
            morphology=importlib.import_module("bayan._tok.morphology"),
            root_vocab=importlib.import_module("bayan._tok.root_vocab"),
            english_bridge=importlib.import_module("bayan._tok.english_bridge"),
        )
    return _inner_modules


class BayanTokenizer:
    """Torch-free public facade for the Bayan morphological tokenizer.

    Built on the bundled root tables + rule-based lexicon only: no torch, no
    numpy, no network, no downloads. Deterministic across runs.

    Example:
        >>> tok = BayanTokenizer()
        >>> tok.tokenize("الكتاب")
        [{'surface': 'الكتاب', 'root': 'كتب', 'root_id': 42,
          'pattern': 'NOUN', 'pattern_id': 7}]
    """

    def __init__(self) -> None:
        """Initialise the tokenizer from the bundled tables and lexicon."""
        inner = _load_inner_modules()
        self._inner = inner
        self._vocab = inner.root_vocab.build_default_vocab()
        self._analyzer = inner.morphology.ArabicMorphAnalyzer()
        roots_mod = inner.root_vocab._load_roots_module()
        self._bridge = inner.english_bridge.EnglishRootBridge(roots_mod.CONCEPT_MAP)

    def _encode_word(self, word: str) -> dict[str, Any]:
        """Encode one word into its public token dict."""
        inner = self._inner
        vocab_mod = inner.root_vocab
        if inner.bayan._is_stopword(word):
            return {
                "surface": word,
                "root": "",
                "root_id": vocab_mod.PAD_ID,
                "pattern": "STOPWORD",
                "pattern_id": vocab_mod.PATTERN_STOPWORD,
            }
        if inner.bayan._contains_arabic(word):
            root, pattern = self._analyzer.analyze(word)
        else:
            root, pattern = self._bridge.to_root(word)
        return {
            "surface": word,
            "root": root,
            "root_id": self._vocab.get_root_id(root),
            "pattern": pattern,
            "pattern_id": self._vocab.get_pattern_id(pattern),
        }

    def tokenize(self, text: str) -> list[dict[str, Any]]:
        """Tokenize text into one morphological token per word.

        Each token is ``{"surface", "root", "root_id", "pattern",
        "pattern_id"}``. Stopwords yield ``root == ""`` and pattern
        ``"STOPWORD"``. Unknown roots (e.g. unresolved English words, which
        surface as ``<ENG:bucket>`` placeholders) map to ``UNK`` root id.

        Empty or whitespace-only input returns ``[]``.
        """
        if not text or not text.strip():
            return []
        words = self._inner.bayan._tokenize_text(text)
        return [self._encode_word(word) for word in words]

    def roots(self, text: str) -> list[str]:
        """Return the resolved linguistic roots, one per word.

        Stopwords and unresolved placeholders (``<ENG:...>``) are excluded —
        what remains are roots the lexicon actually knows. Empty input
        returns ``[]``.
        """
        return [
            token["root"]
            for token in self.tokenize(text)
            if token["root"] and not token["root"].startswith("<")
        ]

    def patterns(self, text: str) -> list[str]:
        """Return the morphological pattern name per word.

        Parallel to :meth:`tokenize` — one entry per word, ``"STOPWORD"``
        for stopwords. Empty input returns ``[]``.
        """
        return [token["pattern"] for token in self.tokenize(text)]

    def fertility(self, text: str) -> float:
        """Return tokens-per-word (fertility) for the input text.

        Bayan emits exactly one morphological token per word, so this is
        1.0 by construction on non-empty input — the number is reported for
        honest comparison against BPE/WordPiece baselines (see
        ``scripts/bayan_fertility.py``), not as a quality claim. Returns
        0.0 when the input has no words.
        """
        words = self._inner.bayan._tokenize_text(text)
        if not words:
            return 0.0
        return len(self.tokenize(text)) / len(words)

    def supported(self) -> bool:
        """Return True when the torch-free pipeline is ready.

        Always True after successful construction — it reports that the
        tables/lexicon path (the only supported path) loaded correctly.
        """
        return True

    @property
    def vocab_size(self) -> int:
        """Total vocabulary size (roots × patterns)."""
        return self._vocab.n_roots * self._vocab.n_patterns

    @classmethod
    def with_model(cls, weights_path: str | Path) -> BayanTokenizer:
        """Model-backed Bayan — NOT IMPLEMENTED (explicit stub).

        Always raises :class:`NotAvailableError`: a missing weights file is
        reported as missing, and a present-but-unloadable weights file is
        reported as unsupported. There is deliberately no silent fallback
        to the torch-free path — callers must choose explicitly.
        """
        path = Path(weights_path)
        if not path.exists():
            raise NotAvailableError(
                f"Bayan model weights not found at {path}. "
                "The default torch-free BayanTokenizer() needs no weights."
            )
        raise NotAvailableError(
            "Model-backed Bayan is not implemented in this release "
            f"(weights exist at {path} but no loader exists). "
            "Use the default torch-free BayanTokenizer() instead."
        )
