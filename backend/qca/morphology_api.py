"""Ruh Morphology API (صرف) — deterministic Arabic root-morphology helpers.

Pure, dependency-light functions powering chat features (root explorer,
sense disambiguation, concept bridge, explain prompts). Every linguistic
claim returned carries provenance so the UI can tag it "verified" vs
"heuristic" — nothing here invents roots, meanings, or verse numbers.

Verified data sources:
- backend/qca/roots.py :: ARABIC_ROOTS (55 curated roots, meaning/domain/
  frequency/derivatives) and CONCEPT_MAP (117 English->Arabic mappings).
- ruh_model/tokenizer/morphology.py :: ArabicMorphAnalyzer (rule-based
  affix stripping + trilateral root extraction + pattern classification).

Provenance values: "verified" | "heuristic" | "unavailable".
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Data imports (repo convention: backend/ on sys.path, mirroring qca/engine.py)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - import path varies by entry point
    from qca.roots import ARABIC_ROOTS, CONCEPT_MAP
except ImportError:  # pragma: no cover
    try:
        from backend.qca.roots import ARABIC_ROOTS, CONCEPT_MAP  # type: ignore[no-redef]
    except ImportError:  # pragma: no cover
        ARABIC_ROOTS: dict[str, dict[str, Any]] = {}
        CONCEPT_MAP: dict[str, str] = {}

try:
    from ruh_model.tokenizer.morphology import ArabicMorphAnalyzer
except ImportError:  # pragma: no cover
    ArabicMorphAnalyzer = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Provenance constants
# ---------------------------------------------------------------------------

VERIFIED = "verified"
HEURISTIC = "heuristic"
UNAVAILABLE = "unavailable"

SOURCE_ROOTS_DB = "backend/qca/roots.py:ARABIC_ROOTS"
SOURCE_CONCEPT_MAP = "backend/qca/roots.py:CONCEPT_MAP"
SOURCE_ANALYZER = "ruh_model/tokenizer/morphology.py:ArabicMorphAnalyzer"
SOURCE_STOPWORDS = "ruh_model/tokenizer/bayan.py:_ARABIC_STOPWORDS"

# ---------------------------------------------------------------------------
# Normalization helpers (local copies — avoid depending on private helpers)
# ---------------------------------------------------------------------------

_TASHKEEL_RE = re.compile(
    "[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed]"
)
_HAMZA_MAP = {"أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ي"}
_ARABIC_RE = re.compile("[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")


def _strip_tashkeel(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


def _normalize_hamza(text: str) -> str:
    return "".join(_HAMZA_MAP.get(ch, ch) for ch in text)


def _norm_key(text: str) -> str:
    """Canonical lookup key: strip tashkeel, normalize hamza, NFKC."""
    return unicodedata.normalize("NFKC", _normalize_hamza(_strip_tashkeel(text)))


def _is_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


# Normalized-key index over the DB so hamza variants ("قرأ" vs "قرا") match.
_DB_KEY_INDEX: dict[str, str] = {_norm_key(k): k for k in ARABIC_ROOTS}


def _lookup_root_key(root: str) -> str | None:
    """Resolve a root string to its canonical DB key (exact, then normalized)."""
    if not root:
        return None
    if root in ARABIC_ROOTS:
        return root
    return _DB_KEY_INDEX.get(_norm_key(root))


# Arabic stopwords: prefer the repo list, fall back to a minimal embedded set.
try:  # pragma: no cover - heavy import, guarded
    from ruh_model.tokenizer.bayan import _ARABIC_STOPWORDS as _REPO_STOPWORDS

    ARABIC_STOPWORDS: frozenset[str] = frozenset(_REPO_STOPWORDS)
    _STOPWORD_SOURCE = SOURCE_STOPWORDS
except Exception:  # pragma: no cover
    ARABIC_STOPWORDS = frozenset(
        {"في", "من", "إلى", "على", "عن", "مع", "لا", "ما", "إن", "أن", "قد", "ثم", "أو"}
    )
    _STOPWORD_SOURCE = "morphology_api.py:embedded fallback stopword set (heuristic)"


_ANALYZER = ArabicMorphAnalyzer() if ArabicMorphAnalyzer is not None else None

# Canonical wazn per analyzer pattern class. The analyzer returns coarse
# pattern *classes*, never the exact vocalized wazn — so these mappings are
# always heuristic approximations of the surface form's true wazn.
_PATTERN_WAZN: dict[str, str | None] = {
    "VERB_PAST": "فَعَلَ",
    "VERB_PRESENT": "يَفْعَلُ",
    "ACTIVE_PARTICIPLE": "فَاعِل",
    "PASSIVE_PARTICIPLE": "مَفْعُول",
    "VERBAL_NOUN": "مَصْدَر",
    "PLACE_NOUN": "مَفْعَلَة",
    "INSTRUMENT_NOUN": "مِفْعَل",
    "NOUN": None,
    "ADJECTIVE": None,
    "STOPWORD": None,
}


# ---------------------------------------------------------------------------
# 1. analyze_word
# ---------------------------------------------------------------------------


def analyze_word(word: str) -> dict[str, Any]:
    """Analyze one word into (root, pattern, wazn) with provenance.

    Provenance is "verified" when the extracted root resolves to an entry in
    the verified root DB; "heuristic" otherwise (analyzer guess, non-Arabic
    input, stopword, or empty input). Never invents a root.
    """
    if not word or not isinstance(word, str) or not word.strip():
        return {
            "word": word,
            "root": "",
            "root_provenance": HEURISTIC,
            "pattern": "UNKNOWN",
            "pattern_provenance": HEURISTIC,
            "wazn": None,
            "wazn_provenance": HEURISTIC,
            "provenance": HEURISTIC,
            "source": SOURCE_ANALYZER,
            "note": "Empty input: no root could be determined.",
        }

    token = word.strip()

    if token in ARABIC_STOPWORDS:
        return {
            "word": token,
            "root": "",
            "root_provenance": VERIFIED,
            "pattern": "STOPWORD",
            "pattern_provenance": VERIFIED,
            "wazn": None,
            "wazn_provenance": HEURISTIC,
            "provenance": VERIFIED,
            "source": _STOPWORD_SOURCE,
            "note": "Particle with no trilateral root (repo stopword list).",
        }

    if not _is_arabic(token):
        # English path: bridge through the verified CONCEPT_MAP only.
        mapped = CONCEPT_MAP.get(token.lower())
        if mapped is not None:
            return {
                "word": token,
                "root": mapped,
                "root_provenance": VERIFIED,
                "pattern": "CONCEPT_BRIDGE",
                "pattern_provenance": HEURISTIC,
                "wazn": None,
                "wazn_provenance": HEURISTIC,
                "provenance": VERIFIED,
                "source": SOURCE_CONCEPT_MAP,
                "note": (
                    "English word bridged to Arabic root via the verified "
                    "concept map; morphological pattern is not determined."
                ),
            }
        return {
            "word": token,
            "root": "",
            "root_provenance": HEURISTIC,
            "pattern": "NON_ARABIC",
            "pattern_provenance": HEURISTIC,
            "wazn": None,
            "wazn_provenance": HEURISTIC,
            "provenance": HEURISTIC,
            "source": SOURCE_ANALYZER,
            "note": "Non-Arabic word with no verified concept-map bridge.",
        }

    if _ANALYZER is None:  # pragma: no cover - analyzer should be present
        return {
            "word": token,
            "root": "",
            "root_provenance": HEURISTIC,
            "pattern": "UNKNOWN",
            "pattern_provenance": HEURISTIC,
            "wazn": None,
            "wazn_provenance": HEURISTIC,
            "provenance": HEURISTIC,
            "source": SOURCE_ANALYZER,
            "note": "Morphological analyzer unavailable; no root determined.",
        }

    root, pattern = _ANALYZER.analyze(token)
    db_key = _lookup_root_key(root)
    recovered = False
    if db_key is None:
        # The analyzer's greedy affix stripping can over-strip short words
        # (e.g. "كتب" -> "تب" via the ka- preposition prefix). Retry with the
        # cleaned surface form itself — still only accepted on a DB hit, so
        # nothing unverified is ever promoted.
        surface_key = _lookup_root_key(_strip_tashkeel(token))
        if surface_key is not None:
            db_key = surface_key
            root = surface_key
            recovered = True
    wazn = _PATTERN_WAZN.get(pattern)

    if db_key is not None:
        note = (
            "Root verified in the root database. Pattern class and wazn "
            "come from the rule-based analyzer and are heuristic "
            "approximations, not exact vocalized forms."
        )
        if recovered:
            note += (
                " The analyzer's affix stripping over-removed a prefix; the "
                "root was recovered from the surface form and verified "
                "against the database."
            )
        return {
            "word": token,
            "root": db_key,
            "root_provenance": VERIFIED,
            "pattern": pattern,
            "pattern_provenance": HEURISTIC,
            "wazn": wazn,
            "wazn_provenance": HEURISTIC,
            "provenance": VERIFIED,
            "source": SOURCE_ROOTS_DB,
            "note": note,
        }

    return {
        "word": token,
        "root": root,
        "root_provenance": HEURISTIC,
        "pattern": pattern,
        "pattern_provenance": HEURISTIC,
        "wazn": wazn,
        "wazn_provenance": HEURISTIC,
        "provenance": HEURISTIC,
        "source": SOURCE_ANALYZER,
        "note": (
            f"Analyzer guessed root '{root}', which is not in the verified "
            "root database. Treat root and pattern as heuristic."
        ),
    }


# ---------------------------------------------------------------------------
# 2. get_root_family
# ---------------------------------------------------------------------------


def get_root_family(root: str) -> dict[str, Any] | None:
    """Return the verified DB entry for a root, or None if unknown.

    derivatives: [{surface, gloss}] in DB order. patterns: distinct analyzer
    pattern classes observed across the derivative surface forms (heuristic).
    """
    db_key = _lookup_root_key((root or "").strip())
    if db_key is None:
        return None

    entry = ARABIC_ROOTS[db_key]
    derivatives_raw = entry.get("derivatives", {}) or {}
    derivatives = [
        {"surface": surface, "gloss": gloss} for surface, gloss in derivatives_raw.items()
    ]

    patterns: list[str] = []
    if _ANALYZER is not None:
        for surface in derivatives_raw:
            try:
                _, pattern = _ANALYZER.analyze(surface)
            except Exception:  # noqa: BLE001, S110 - resilient iteration
                continue
            if pattern and pattern not in patterns:
                patterns.append(pattern)

    meaning = entry.get("meaning", "")
    return {
        "root": db_key,
        "meaning": meaning,
        # The DB stores meanings in English only; both fields carry it.
        "meaning_en": meaning,
        "domain": entry.get("domain", ""),
        "derivatives": derivatives,
        "patterns": patterns,
        "patterns_provenance": HEURISTIC,
        "frequency": entry.get("frequency"),
        "provenance": VERIFIED,
        "source": SOURCE_ROOTS_DB,
        "note": (
            "Meaning, domain, frequency and derivatives are verified DB data. "
            "'patterns' are analyzer pattern classes over the derivative "
            "surface forms (heuristic), not canonical wazn labels."
        ),
    }


# ---------------------------------------------------------------------------
# 3. get_senses
# ---------------------------------------------------------------------------


def get_senses(word: str, context: str | None = None) -> dict[str, Any]:
    """Sense options for a word, grouped from the verified root entry.

    Each sense is a derivative surface form + its DB gloss. When `context`
    is given, senses whose gloss mentions a context word rank first
    (deterministic substring ranking).
    """
    analysis = analyze_word(word)
    root = analysis.get("root") or ""
    family = get_root_family(root) if root else None

    if family is None:
        return {
            "word": word,
            "root": root,
            "senses": [],
            "ranked_by_context": False,
            "provenance": HEURISTIC,
            "source": SOURCE_ANALYZER,
            "note": "No verified root entry; no sense options available.",
        }

    senses: list[dict[str, Any]] = [
        {
            "surface": family["root"],
            "gloss": family["meaning"],
            "kind": "root",
            "pattern": None,
        }
    ]
    for deriv in family["derivatives"]:
        pattern = None
        if _ANALYZER is not None:
            try:
                pattern = _ANALYZER.analyze(deriv["surface"])[1]
            except Exception:  # noqa: BLE001, S110 - resilient iteration
                pattern = None
        senses.append(
            {
                "surface": deriv["surface"],
                "gloss": deriv["gloss"],
                "kind": "derivative",
                "pattern": pattern,
            }
        )

    ranked = False
    if context:
        tokens = [t.lower() for t in re.split(r"\s+", context.strip()) if t]
        if tokens:

            def _score(sense: dict[str, Any]) -> int:
                gloss = str(sense.get("gloss") or "").lower()
                return sum(1 for t in tokens if t in gloss)

            senses.sort(key=_score, reverse=True)
            ranked = True

    return {
        "word": word,
        "root": family["root"],
        "senses": senses,
        "ranked_by_context": ranked,
        "provenance": VERIFIED,
        "source": SOURCE_ROOTS_DB,
        "note": (
            "Glosses are verified DB data. Sense grouping follows the DB's "
            "derivative list; 'pattern' per sense is an analyzer heuristic."
        ),
    }


# ---------------------------------------------------------------------------
# 4. bridge_concept
# ---------------------------------------------------------------------------


def bridge_concept(concept_en: str) -> dict[str, Any] | None:
    """Bridge an English concept to an Arabic root via CONCEPT_MAP.

    Returns None for unknown concepts — never invents a mapping.
    """
    if not concept_en or not isinstance(concept_en, str):
        return None
    key = concept_en.strip().lower()
    arabic_root = CONCEPT_MAP.get(key)
    if arabic_root is None:
        return None

    entry = ARABIC_ROOTS.get(arabic_root, {})
    return {
        "concept": key,
        "arabic_root": arabic_root,
        "root_entry": {
            "meaning": entry.get("meaning", ""),
            "domain": entry.get("domain", ""),
            "frequency": entry.get("frequency"),
        },
        "provenance": VERIFIED,
        "source": SOURCE_CONCEPT_MAP,
        "note": "Concept->root mapping is verified repo data.",
    }


# ---------------------------------------------------------------------------
# 5. get_pattern_siblings
# ---------------------------------------------------------------------------


def get_pattern_siblings(wazn: str) -> dict[str, Any]:
    """Sibling words sharing a morphological pattern (wazn).

    The root DB stores derivatives as {surface: gloss} with NO per-derivative
    pattern/wazn labels, so no verified sibling data exists. Per spec, this
    returns available=false rather than synthesizing unverified groupings.
    """
    return {
        "wazn": wazn,
        "available": False,
        "siblings": [],
        "provenance": UNAVAILABLE,
        "source": ("backend/qca/roots.py:ARABIC_ROOTS has no per-derivative pattern/wazn fields"),
        "reason": (
            "The root database does not label derivatives with their "
            "morphological pattern (wazn), so sibling words cannot be "
            "grouped from verified data."
        ),
    }


# ---------------------------------------------------------------------------
# 6. get_occurrences
# ---------------------------------------------------------------------------


def get_occurrences(root: str) -> dict[str, Any]:
    """Quranic occurrences for a root.

    The qca engine has no static per-verse occurrence lists (verses are only
    loaded at runtime via load_quran_verses()), so no verse list can be
    returned. The aggregate frequency count from the DB is included as
    labeled context — it is NOT a verse list.
    """
    db_key = _lookup_root_key((root or "").strip())
    frequency = ARABIC_ROOTS[db_key].get("frequency") if db_key else None
    return {
        "root": db_key or (root or "").strip(),
        "available": False,
        "occurrences": [],
        "frequency": frequency,
        "frequency_note": (
            "Aggregate Quranic frequency count from the root DB "
            "(verified), not a per-verse occurrence list."
        ),
        "provenance": UNAVAILABLE,
        "source": "backend/qca/engine.py (no static per-verse occurrence data); "
        "frequency from " + SOURCE_ROOTS_DB,
        "reason": (
            "No static per-verse occurrence lists exist in the qca engine; "
            "verses are loaded at runtime only via load_quran_verses(). "
            "No verse numbers are invented."
        ),
    }


# ---------------------------------------------------------------------------
# 7. build_explain_prompt
# ---------------------------------------------------------------------------

_EXPLAIN_SYSTEM_INSTRUCTION = """\
You are explaining Arabic morphology to a chat user. You are given VERIFIED FACTS \
below — a root analysis produced by a deterministic, rule-based analyzer and a \
curated root database.

STRICT RULES:
1. Explain ONLY what the verified facts support. Use the exact root, glosses, \
domain, frequency, and pattern names given.
2. NEVER invent: do not state a different root, do not cite Quran verse numbers, \
do not claim an exact vocalized wazn beyond the heuristic approximation given, \
and do not add derivative forms not listed.
3. The 'pattern' and 'wazn' fields are heuristic approximations from a \
rule-based analyzer — present them as approximate, never as certain.
4. If the user asks for something beyond the verified facts, say plainly that \
it is not in the verified data instead of guessing.
5. Keep the explanation short and phone-readable. End with the provenance tag \
(verified/heuristic) for the root claim.
"""


def build_explain_prompt(word: str) -> dict[str, Any]:
    """Build a constrained LLM prompt: the model explains verified facts only."""
    analysis = analyze_word(word)
    root = analysis.get("root") or ""
    family = get_root_family(root) if root else None

    verified_facts: dict[str, Any] = {
        "word": analysis["word"],
        "root": root,
        "root_provenance": analysis["root_provenance"],
        "root_meaning": (family or {}).get("meaning", ""),
        "domain": (family or {}).get("domain", ""),
        "frequency": (family or {}).get("frequency"),
        "derivatives": (family or {}).get("derivatives", []),
        "pattern": analysis["pattern"],
        "pattern_provenance": analysis["pattern_provenance"],
        "wazn_approximate": analysis["wazn"],
        "wazn_provenance": analysis["wazn_provenance"],
        "provenance": analysis["provenance"],
        "source": analysis["source"],
        "note": analysis["note"],
    }
    return {
        "word": word,
        "verified_facts": verified_facts,
        "system_instruction": _EXPLAIN_SYSTEM_INSTRUCTION,
        "provenance": analysis["provenance"],
        "source": analysis["source"],
    }
