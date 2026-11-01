"""Dialect -> root normalization (use case #6).

``normalize(word, dialect_hint=None)`` strips dialect-specific affixes
using explicit per-region tables, then runs the shared rule-based MSA
morphological analyzer on the remainder to recover ``(root, pattern)``.

BETA / UNVERIFIED -- read before trusting any output:
* Neither the analyzer nor these tables have been evaluated on real
  dialectal text. The NADI/MADAR eval harness is a separate track;
  until it reports, every normalization is provisional.
* Tables are explicit data below. Anything not in a table is NOT
  stripped -- there is no guessing. (Quran lens: la taqfu.)
* Foreign bucket: non-Semitic loans (Maghrebi French stock) get
  ``foreign=True, root=None``. A root is NEVER hallucinated for them.
* Unknown forms get low confidence + ``needs_review=True`` (tabayyun).

Gulf table is deliberately minimal (v0.1): only the affixes verified
for this build (``ba-/b-`` future, ``ma-`` negation). The spec's
``ga-`` candidate was EXCLUDED by a JEV typed decision
(``exclude``, confidence 1.00, 2026-09-29): no evidence for it was
found in the track-8 research notes, and the task's hard rule forbids
unverified mappings. Revisit with Gulf dialect references before
extending.

Torch-free: the morphology analyzer is loaded by file path (see
``ruh_model/reader/annotator.py`` for why).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_DIALECTS: tuple[str, ...] = ("egyptian", "levantine", "gulf", "maghrebi")

# ---------------------------------------------------------------------------
# Per-region affix tables. Explicit data: (surface, tag), longest-first.
# Only affixes attested in the standard dialect descriptions are listed.
# ---------------------------------------------------------------------------

# Egyptian: ha- future (هيكتب "he will write"), bi- progressive/habitual
# (بيكتب "he writes"), ma-...-sh negation (مايعرفش "he doesn't know").
_EGYPTIAN_PREFIXES: list[tuple[str, str]] = [
    ("ما", "neg_ma"),
    ("ه", "fut_ha"),
    ("ب", "prog_bi"),
]

# Levantine: b-/bi- progressive (بيكتب), 'am- progressive (عميكتب),
# rah-/lah- future, ma- negation (مابيعرف), optional -sh (مابيعرفش).
_LEVANTINE_PREFIXES: list[tuple[str, str]] = [
    ("عم", "prog_am"),
    ("رح", "fut_rah"),
    ("لح", "fut_lah"),
    ("ما", "neg_ma"),
    ("ب", "prog_b"),
]

# Gulf v0.1 (minimal, verified only): ba-/b- future (Emirati بايكتب
# "he will write"), ma- negation (مايعرف "he doesn't know").
# PARTIAL COVERAGE -- extend from Gulf dialect references, not guesses.
_GULF_PREFIXES: list[tuple[str, str]] = [
    ("ما", "neg_ma"),
    ("با", "fut_ba"),
    ("ب", "fut_b"),
]

# Maghrebi: ka- imperfect (كايكتب "he writes"), ta- imperfect variant,
# ma-...-sh negation (مايعرفش).
_MAGHREBI_PREFIXES: list[tuple[str, str]] = [
    ("ما", "neg_ma"),
    ("كا", "imp_ka"),
    ("ك", "imp_ka"),
    ("تا", "imp_ta"),
    ("ت", "imp_ta"),
]

_NEG_SH_SUFFIXES: list[tuple[str, str]] = [("ش", "neg_sh")]

# Region config: prefixes, suffixes, and the ma-...-sh circumfix pair
# (applied as one unit when both halves are present).
_REGION_TABLES: dict[str, dict[str, Any]] = {
    "egyptian": {
        "prefixes": _EGYPTIAN_PREFIXES,
        "suffixes": _NEG_SH_SUFFIXES,
        "circumfix": ("ما", "ش"),
    },
    "levantine": {
        "prefixes": _LEVANTINE_PREFIXES,
        "suffixes": _NEG_SH_SUFFIXES,
        "circumfix": ("ما", "ش"),
    },
    "gulf": {
        "prefixes": _GULF_PREFIXES,
        "suffixes": [],
        "circumfix": None,
    },
    "maghrebi": {
        "prefixes": _MAGHREBI_PREFIXES,
        "suffixes": _NEG_SH_SUFFIXES,
        "circumfix": ("ما", "ش"),
    },
}

# ---------------------------------------------------------------------------
# Foreign bucket: explicit non-Semitic loanword list (Maghrebi French
# stock). Non-exhaustive by design -- anything not listed is NOT guessed;
# unknown Arabic-script loans fall through to needs_review.
# ---------------------------------------------------------------------------

_FOREIGN_LOANS: dict[str, str] = {
    "طوموبيل": "tomobile (car) < Fr. automobile",
    "تيليفون": "telephone < Fr. téléphone",
    "تليفون": "telephone < Fr. téléphone",
    "بيرو": "bureau (desk/office) < Fr. bureau",
    "كوزينة": "cuisine (kitchen) < Fr. cuisine",
    "سبيطار": "hôpital (hospital) < Fr. hôpital",
    "ميرسي": "merci (thanks) < Fr. merci",
}

# --- confidence rubric (deterministic heuristic, NOT measured accuracy) ----

CONF_FOREIGN_LIST = 0.85  # explicit list hit
CONF_FOREIGN_LATIN = 0.90  # script detection is deterministic
CONF_HINT_STRIP = 0.60  # caller asserted the dialect, affix stripped
CONF_AUTO_STRIP = 0.50  # dialect auto-detected via affix strip
CONF_MSA_FALLBACK = 0.50  # no dialectal affix found; plain MSA analysis
CONF_UNKNOWN = 0.15  # no root recovered -> needs_review

_MIN_STEM_LEN = 3  # never strip down to fewer than 3 letters
# Auto-detect attribution needs a substantive stem: stripping into a bare
# 3-letter remainder (e.g. maghrebi "ka-" off "كتاب" -> "تاب") usually
# means the "affix" was part of the root. With an explicit hint the
# caller owns the attribution, so hint mode keeps _MIN_STEM_LEN.
_MIN_AUTO_STEM_LEN = 4

# Known limit of the shared rule-based analyzer (not this module's to
# fix -- tokenizer quality is another track): single-letter MSA prefixes
# are stripped aggressively, so a bare 3-letter stem starting with kaf
# (e.g. "كتب") loses it ("تب"). Forms with a protective imperfect
# prefix ("يكتب") analyse correctly.


def _load_morphology() -> ModuleType:
    """Load ruh_model/tokenizer/morphology.py by path (torch-free)."""
    path = Path(__file__).resolve().parents[2] / "ruh_model" / "tokenizer" / "morphology.py"
    spec = importlib.util.spec_from_file_location("ruh_dialect_morphology", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load morphology analyzer from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_morphology = _load_morphology()
_analyzer = _morphology.ArabicMorphAnalyzer()
_strip_tashkeel = _morphology._strip_tashkeel  # noqa: SLF001 -- same-project helper


def _strip_region_affixes(word: str, region: str) -> tuple[str, bool]:
    """Strip one region's affixes. Returns (remainder, stripped_any)."""
    cfg = _REGION_TABLES[region]
    w = word

    circumfix = cfg["circumfix"]
    if circumfix is not None:
        pre, suf = circumfix
        if w.startswith(pre) and w.endswith(suf) and len(w) - len(pre) - len(suf) >= _MIN_STEM_LEN:
            return w[len(pre) : -len(suf)], True

    stripped = False
    for prefix, _tag in cfg["prefixes"]:
        if w.startswith(prefix) and len(w) - len(prefix) >= _MIN_STEM_LEN:
            w = w[len(prefix) :]
            stripped = True
            break

    for suffix, _tag in cfg["suffixes"]:
        if w.endswith(suffix) and len(w) - len(suffix) >= _MIN_STEM_LEN:
            w = w[: -len(suffix)]
            stripped = True
            break

    return w, stripped


def _unknown(surface: str, dialect: str, pattern: str = "UNKNOWN") -> dict[str, Any]:
    return {
        "surface": surface,
        "dialect": dialect,
        "root": "",
        "pattern": pattern,
        "confidence": CONF_UNKNOWN,
        "foreign": False,
        "needs_review": True,
    }


def normalize(word: str, dialect_hint: str | None = None) -> dict[str, Any]:
    """Normalize one dialectal word into root-space.

    Returns ``{surface, dialect, root, pattern, confidence, foreign,
    needs_review}``. ``dialect_hint`` is one of ``egyptian``,
    ``levantine``, ``gulf``, ``maghrebi`` (or None for auto-detect).
    Contract: single word in, never a hallucinated root out.
    """
    surface = word.strip()

    if dialect_hint is not None and dialect_hint not in _DIALECTS:
        raise ValueError(
            f"Unknown dialect_hint {dialect_hint!r}; expected one of {list(_DIALECTS)} or None"
        )

    if not surface:
        return _unknown(surface, dialect_hint or "unknown", pattern="EMPTY")

    has_arabic = bool(_ARABIC_RE.search(surface))
    has_latin = bool(_LATIN_RE.search(surface))

    # Latin-only token: not Semitic root-space representable -> foreign.
    if has_latin and not has_arabic:
        return {
            "surface": surface,
            "dialect": dialect_hint or "unknown",
            "root": None,
            "pattern": "FOREIGN",
            "confidence": CONF_FOREIGN_LATIN,
            "foreign": True,
            "needs_review": False,
        }

    # Mixed-script token: intra-word code-switch, out of scope -> review.
    if has_latin and has_arabic:
        return _unknown(surface, dialect_hint or "unknown", pattern="MIXED_SCRIPT")

    # Explicit foreign-loan list (Arabic-script French stock).
    loan_key = _strip_tashkeel(surface)
    if loan_key in _FOREIGN_LOANS:
        return {
            "surface": surface,
            "dialect": "maghrebi",
            "root": None,
            "pattern": "FOREIGN",
            "confidence": CONF_FOREIGN_LIST,
            "foreign": True,
            "needs_review": False,
        }

    regions: tuple[str, ...] = (dialect_hint,) if dialect_hint else _DIALECTS
    for region in regions:
        remainder, stripped = _strip_region_affixes(surface, region)
        if not stripped:
            # No dialectal affix found. With an explicit hint the word is
            # still that dialect's (MSA-shaped words exist in dialects);
            # without a hint, do NOT misattribute -- analyse as MSA.
            if dialect_hint is None:
                continue
            remainder = surface
        elif dialect_hint is None and len(remainder) < _MIN_AUTO_STEM_LEN:
            # Stripped into a bare trilateral-or-less remainder: the
            # "affix" was probably root material. Not a dialect claim.
            continue
        root, pattern = _analyzer.analyze(remainder)
        if root:
            confidence = CONF_HINT_STRIP if dialect_hint else CONF_AUTO_STRIP
            return {
                "surface": surface,
                "dialect": region,
                "root": root,
                "pattern": pattern,
                "confidence": confidence,
                "foreign": False,
                "needs_review": False,
            }

    # No region recovered a root. Last resort: plain MSA analysis so
    # MSA-shaped input still yields something honest.
    root, pattern = _analyzer.analyze(surface)
    if root:
        return {
            "surface": surface,
            "dialect": dialect_hint or "msa",
            "root": root,
            "pattern": pattern,
            "confidence": CONF_MSA_FALLBACK,
            "foreign": False,
            "needs_review": False,
        }
    return _unknown(surface, dialect_hint or "unknown")
