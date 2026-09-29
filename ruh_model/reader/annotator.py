"""Per-word annotation for the RootSpace Reader (use case #5, Build 4).

``annotate_text`` turns running text into a list of per-occurrence
annotations ``{word_index, surface, root, pattern, sense_id,
sense_pending, confidence}`` -- the precomputed layer a tap-any-word
Quran reader serves offline.

BETA / UNVERIFIED -- read before trusting any output:
* root/pattern come from the rule-based ``ArabicMorphAnalyzer``
  (``ruh_model/tokenizer/morphology.py``); that analyzer has never
  been measured against a gold morphology standard.
* ``confidence`` is a deterministic heuristic (rubric below), NOT a
  measured accuracy. Treat every value as provisional.
* ``sense_id`` is populated ONLY from an explicit sense inventory
  supplied by the caller (another track owns that inventory). When no
  inventory is available -- or when the inventory lists more than one
  candidate sense for a root -- ``sense_id`` is ``None`` and
  ``sense_pending`` is ``True``. This module NEVER invents a sense:
  a wrong Quranic sense is an amana failure, so ambiguity resolves to
  silence, not a guess.

Sense-inventory contract (for the track that builds it):
* ``sense_lookup``: ``Callable[[root, surface], list[str]]`` returning
  candidate sense ids for the occurrence (empty list = unknown).
* ``sense_inventory``: ``dict`` mapping ``root -> list[{"sense_id": ...}]``.
  If both are given, ``sense_lookup`` wins.
* Selection rule: exactly one candidate -> assigned
  (``sense_pending=False``); zero or several -> ``sense_id=None``,
  ``sense_pending=True``. Per-occurrence disambiguation of genuinely
  ambiguous roots needs the scholar-evaluated disambiguator (gold eval
  on ~1k sampled words, per the study) -- until then it stays pending.

Torch-free: the morphology analyzer is loaded by file path so this
module never triggers ``ruh_model/__init__.py`` (which needs torch).
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

# --- word splitting / script detection (mirrors bayan.py) -----------------

_WORD_SPLIT_RE = re.compile(
    r"[^\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
)
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

# Arabic function words with no trilateral root. Explicit, conservative
# subset -- particles/pronouns only, never content words.
_ARABIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "في",
        "من",
        "إلى",
        "على",
        "عن",
        "مع",
        "هو",
        "هي",
        "هم",
        "هن",
        "أنا",
        "نحن",
        "أنت",
        "أنتم",
        "هذا",
        "هذه",
        "ذلك",
        "تلك",
        "هؤلاء",
        "أولئك",
        "لا",
        "لم",
        "لن",
        "ما",
        "إن",
        "أن",
        "كان",
        "ليس",
        "قد",
        "ثم",
        "أو",
        "بل",
        "لكن",
        "حتى",
    }
)

# --- confidence rubric (deterministic heuristic, NOT measured accuracy) ----

CONF_STOPWORD = 0.95  # list membership is deterministic
CONF_ANALYZED = 0.55  # rule-based root+pattern; unverified vs gold
CONF_UNKNOWN_AR = 0.25  # analyzer found no root
CONF_NON_ARABIC = 0.15  # out of scope for the Arabic analyzer

_ANNOTATOR_VERSION = "0.1.0-beta"


def _load_morphology() -> ModuleType:
    """Load ruh_model/tokenizer/morphology.py by path (torch-free)."""
    path = Path(__file__).resolve().parents[2] / "ruh_model" / "tokenizer" / "morphology.py"
    spec = importlib.util.spec_from_file_location("ruh_reader_morphology", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load morphology analyzer from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_morphology = _load_morphology()
_analyzer = _morphology.ArabicMorphAnalyzer()


def _is_arabic(word: str) -> bool:
    return bool(_ARABIC_RE.search(word))


def _split_words(text: str) -> list[str]:
    return [w for w in _WORD_SPLIT_RE.split(text) if w]


def _inventory_to_lookup(
    inventory: dict[str, list[dict[str, Any]]],
) -> Callable[[str, str], list[str]]:
    """Adapt a ``{root: [{sense_id, ...}]}`` inventory to the lookup protocol."""

    def lookup(root: str, _surface: str) -> list[str]:
        senses = inventory.get(root, [])
        return [s["sense_id"] for s in senses if "sense_id" in s]

    return lookup


def _resolve_sense(
    root: str,
    surface: str,
    lookup: Callable[[str, str], list[str]] | None,
) -> tuple[str | None, bool]:
    """Return (sense_id, sense_pending).

    Never fabricates: ambiguous or unknown -> (None, True).
    """
    if lookup is None or not root:
        return None, True
    try:
        candidates = lookup(root, surface)
    except Exception:  # a broken inventory must not corrupt annotations
        return None, True
    if len(candidates) == 1:
        return candidates[0], False
    return None, True


def annotate_text(
    text: str,
    ref_id: str | None = None,
    sense_lookup: Callable[[str, str], list[str]] | None = None,
    sense_inventory: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Annotate each word of ``text`` with root/pattern/sense metadata.

    Returns a list of dicts with keys: ``word_index`` (0-based),
    ``surface`` (original surface form), ``root``, ``pattern``,
    ``sense_id`` (or None), ``sense_pending`` (bool), ``confidence``.
    ``ref_id`` is carried through untouched when supplied (the store
    uses it as the document key); it is not otherwise validated here.
    """
    if sense_lookup is None and sense_inventory is not None:
        sense_lookup = _inventory_to_lookup(sense_inventory)

    annotations: list[dict[str, Any]] = []
    for index, surface in enumerate(_split_words(text)):
        if surface in _ARABIC_STOPWORDS:
            annotations.append(
                {
                    "word_index": index,
                    "surface": surface,
                    "root": "",
                    "pattern": "STOPWORD",
                    "sense_id": None,
                    "sense_pending": False,
                    "confidence": CONF_STOPWORD,
                }
            )
            continue

        if not _is_arabic(surface):
            annotations.append(
                {
                    "word_index": index,
                    "surface": surface,
                    "root": "",
                    "pattern": "NON_ARABIC",
                    "sense_id": None,
                    "sense_pending": True,
                    "confidence": CONF_NON_ARABIC,
                }
            )
            continue

        root, pattern = _analyzer.analyze(surface)
        if root and pattern != "UNKNOWN":
            confidence = CONF_ANALYZED
        else:
            confidence = CONF_UNKNOWN_AR
            pattern = "UNKNOWN"
        sense_id, sense_pending = _resolve_sense(root, surface, sense_lookup)
        annotations.append(
            {
                "word_index": index,
                "surface": surface,
                "root": root,
                "pattern": pattern,
                "sense_id": sense_id,
                "sense_pending": sense_pending,
                "confidence": confidence,
            }
        )
    return annotations


def annotator_version() -> str:
    """Version stamp recorded into annotation DBs built by this module."""
    return _ANNOTATOR_VERSION
