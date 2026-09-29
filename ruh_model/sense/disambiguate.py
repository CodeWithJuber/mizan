"""Deterministic word-sense disambiguation over the versioned inventory.

Current scoring (provisional, honest): for each candidate sense of the lemma,
count context-token overlap with the sense's keywords (lemma + English gloss
words + root when known). Confidences are the normalized shares. No neural
model is consulted yet — the ``model_scores`` hook exists so a trained
classifier posterior (e.g. ``nlp/wsd.py``'s per-lemma artifact) can be mixed
in later; until then no ``"model"`` provenance signal is ever emitted.

Conservative abstention (Quran lens: amāna — a wrong sense stated as fact is
worse than "I don't know"):

- ``confidence < threshold`` → ``sense_id`` is ``None``, ``status`` is
  ``"uncertain"``, and the top-k alternatives are still returned.
- Zero context evidence at all → ``"uncertain"`` regardless of threshold.
- Lemma absent from the inventory → ``status`` ``"unknown_lemma"`` (the
  inventory has no opinion rather than a guessed sense).

Threshold policy (JEV choice, confidence 0.92): tiered — ``0.6`` for general
senses, ``0.8`` for religious/Quranic-flagged senses, where the cost of a
wrong sense is higher. An explicit ``threshold`` argument overrides the tier.

Everything is deterministic: same inputs → same outputs, byte-identical.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _sibling(name: str):
    """Resolve a sibling sense module without importing torch.

    Normal package import first (works when torch is installed); file-path
    fallback when ``ruh_model/__init__.py``'s torch import fails (torch-less
    ``[dev, nlp]`` installs). The fallback registers under a stable synthetic
    name so sibling modules share one copy.
    """
    try:
        return importlib.import_module(f"ruh_model.sense.{name}")
    except ImportError:
        path = Path(__file__).with_name(f"{name}.py")
        mod_name = f"ruh_model_sense_{name}"
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise ImportError(f"cannot load sibling module {name!r} from {path}") from None
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module


_inventory = _sibling("inventory")
_provenance = _sibling("provenance")

SenseInventory = _inventory.SenseInventory
SenseEntry = _inventory.SenseEntry
ProvenanceSignal = _provenance.ProvenanceSignal

#: Abstention bar for general senses.
DEFAULT_THRESHOLD = 0.6
#: Abstention bar for religious/Quranic-flagged senses (JEV 0.92: the cost of
#: a wrong religious sense justifies the stricter bar).
RELIGIOUS_THRESHOLD = 0.8

#: Provenance source tag for the deterministic overlap scorer.
CONTEXT_OVERLAP_SOURCE = "ruh_model.sense.disambiguate:context_overlap/v1"

_PUNCT = re.compile(r"[^\w\u0600-\u06FF]+", re.UNICODE)
_GLOSS_WORD = re.compile(r"[a-z0-9\u0600-\u06FF]+")


def _normalize_token(tok: str) -> str:
    """Light deterministic normalization: strip a leading definite article.

    ``"العين"`` and ``"عين"`` are the same keyword for overlap purposes.
    Deliberately minimal — deeper orthographic normalization (hamza/taa
    variants) is out of scope for the provisional scorer.
    """
    if tok.startswith("ال") and len(tok) > 3:
        return tok[2:]
    return tok


def _tokenize(text: str) -> list[str]:
    """Split text into normalized tokens (diacritics stripped, Latin lowered)."""
    tokens = []
    for raw in _PUNCT.split(text):
        if not raw:
            continue
        tok = _inventory.strip_diacritics(raw)
        if re.fullmatch(r"[A-Za-z0-9]+", tok):
            tok = tok.lower()
        else:
            tok = _normalize_token(tok)
        if tok:
            tokens.append(tok)
    return tokens


def _sense_keywords(entry) -> list[str]:
    """Deterministic keyword set for one sense.

    English gloss words + Arabic gloss words (when a reviewed ``gloss_ar``
    exists) + root when known. The lemma itself is deliberately EXCLUDED: it
    occurs in every candidate's context and carries zero discriminative
    information — counting it would only dilute real evidence.

    English-only glosses never match Arabic context tokens — that is an
    honest limitation of the provisional scorer, not a bug to paper over.
    """
    keywords = list(_GLOSS_WORD.findall(entry.gloss_en.lower()))
    if entry.gloss_ar:
        keywords.extend(
            _normalize_token(w)
            for w in _GLOSS_WORD.findall(_inventory.strip_diacritics(entry.gloss_ar))
        )
    if entry.root:
        keywords.append(_normalize_token(_inventory.strip_diacritics(entry.root)))
    # De-duplicate, keep order (deterministic).
    return list(dict.fromkeys(k for k in keywords if k and len(k) >= 2))


def _keyword_hits(keywords: list[str], counts: dict[str, int]) -> float:
    """Count context-token occurrences matching any keyword (substring match).

    Substring (either direction) because Arabic surface forms carry prefixes
    and suffixes the provisional scorer does not strip (``"بصر"`` in
    ``"ببصره"``). Deterministic; documented as provisional.
    """
    total = 0.0
    for kw in keywords:
        for tok, n in counts.items():
            if kw in tok or tok in kw:
                total += n
    return total


@dataclass(frozen=True)
class SenseAlternative:
    """One non-winning candidate sense."""

    sense_id: str
    gloss_ar: str | None
    gloss_en: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Disambiguation:
    """Full outcome of one :func:`disambiguate` call (JSON-serializable)."""

    word: str
    lemma: str
    status: str  # "ok" | "uncertain" | "unknown_lemma"
    sense_id: str | None
    confidence: float | None
    gloss_ar: str | None
    gloss_en: str | None
    alternatives: tuple
    provenance: tuple
    inventory_version: str
    threshold_used: float | None
    abstained: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["alternatives"] = [
            a.to_dict() if isinstance(a, SenseAlternative) else a for a in self.alternatives
        ]
        d["provenance"] = [
            p.to_dict() if isinstance(p, ProvenanceSignal) else p for p in self.provenance
        ]
        return d


def _threshold_for(entry, override: float | None) -> float:
    if override is not None:
        return override
    return RELIGIOUS_THRESHOLD if entry.religious else DEFAULT_THRESHOLD


def disambiguate(
    word: str,
    context: str,
    inventory,
    *,
    top_k: int = 3,
    threshold: float | None = None,
    model_scores: dict[str, float] | None = None,
    model_source: str = "model/provisional-unspecified",
) -> Disambiguation:
    """Disambiguate which sense of ``word`` is used in ``context``.

    Args:
        word: The word/lemma to disambiguate (Arabic, diacritized or not).
        context: The surrounding text (verse, sentence, passage).
        inventory: A :class:`SenseInventory`.
        top_k: How many alternatives to return.
        threshold: Override the tiered abstention bar (0.6 general / 0.8
            religious). Must be in [0.0, 1.0] when given.
        model_scores: Optional ``{sense_id: posterior}`` from a trained
            classifier. Mixed 50/50 with the context-overlap share
            (provisional hook — documented, deterministic). When given, a
            ``"model"`` provenance signal is emitted; otherwise it never is.
        model_source: Dataset/artifact tag for the model signal, e.g.
            ``"mizan-sense-wsd/1.2.1"``.

    Returns:
        A :class:`Disambiguation`. Never raises for linguistic reasons —
        unknown lemmas and zero evidence produce honest ``"uncertain"`` /
        ``"unknown_lemma"`` outcomes, not guesses.
    """
    if not isinstance(word, str) or not word.strip():
        raise ValueError("disambiguate() requires a non-empty word")
    if not isinstance(context, str) or not context.strip():
        raise ValueError("disambiguate() requires a non-empty context")
    if threshold is not None and not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0.0, 1.0], got {threshold!r}")
    top_k = max(1, int(top_k))

    version = inventory.version
    inv_source = f"sense-inventory/v{version}"

    candidates = inventory.senses_for(word)
    if not candidates:
        return Disambiguation(
            word=word,
            lemma=word,
            status="unknown_lemma",
            sense_id=None,
            confidence=None,
            gloss_ar=None,
            gloss_en=None,
            alternatives=(),
            provenance=(),  # no decision was made — nothing to support
            inventory_version=version,
            threshold_used=None,
            abstained=True,
        )

    lemma = candidates[0].lemma
    tokens = _tokenize(context)
    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1

    raw_scores: dict[str, float] = {}
    for entry in candidates:
        raw_scores[entry.sense_id] = _keyword_hits(_sense_keywords(entry), counts)
    evidence = sum(raw_scores.values())

    if evidence <= 0:
        # Zero signal: abstain, but still show the candidate space honestly.
        ranked = sorted(candidates, key=lambda e: e.sense_id)
        alternatives = tuple(
            SenseAlternative(
                sense_id=e.sense_id,
                gloss_ar=e.gloss_ar,
                gloss_en=e.gloss_en,
                confidence=0.0,
            )
            for e in ranked[:top_k]
        )
        receipt = _provenance.build_receipt(
            [
                ProvenanceSignal(signal="inventory", source=inv_source, weight=1.0),
                ProvenanceSignal(
                    signal="context_overlap",
                    source=CONTEXT_OVERLAP_SOURCE,
                    weight=0.0,
                ),
            ]
        )
        return Disambiguation(
            word=word,
            lemma=lemma,
            status="uncertain",
            sense_id=None,
            confidence=0.0,
            gloss_ar=None,
            gloss_en=None,
            alternatives=alternatives,
            provenance=tuple(receipt),
            inventory_version=version,
            threshold_used=None,
            abstained=True,
        )

    ctx_conf = {sid: s / evidence for sid, s in raw_scores.items()}

    model_conf: dict[str, float] = {}
    use_model = False
    if model_scores:
        total_p = sum(float(model_scores.get(e.sense_id, 0.0)) for e in candidates)
        if total_p > 0:
            use_model = True
            model_conf = {
                e.sense_id: float(model_scores.get(e.sense_id, 0.0)) / total_p for e in candidates
            }

    if use_model:
        # Provisional 50/50 mix (documented); both sides already sum to 1.
        combined = {
            e.sense_id: 0.5 * ctx_conf[e.sense_id] + 0.5 * model_conf[e.sense_id]
            for e in candidates
        }
    else:
        combined = dict(ctx_conf)

    ranked = sorted(candidates, key=lambda e: (-combined[e.sense_id], e.sense_id))
    winner = ranked[0]
    win_conf = combined[winner.sense_id]
    bar = _threshold_for(winner, threshold)

    alternatives = tuple(
        SenseAlternative(
            sense_id=e.sense_id,
            gloss_ar=e.gloss_ar,
            gloss_en=e.gloss_en,
            confidence=round(combined[e.sense_id], 6),
        )
        for e in ranked[:top_k]
    )

    signals = [
        ProvenanceSignal(signal="inventory", source=inv_source, weight=1.0),
    ]
    if use_model:
        ctx_share = (0.5 * ctx_conf[winner.sense_id]) / win_conf if win_conf > 0 else 0.0
        model_share = (0.5 * model_conf[winner.sense_id]) / win_conf if win_conf > 0 else 0.0
        signals.append(
            ProvenanceSignal(
                signal="context_overlap",
                source=CONTEXT_OVERLAP_SOURCE,
                weight=round(ctx_share, 6),
            )
        )
        signals.append(
            ProvenanceSignal(signal="model", source=model_source, weight=round(model_share, 6))
        )
    else:
        signals.append(
            ProvenanceSignal(
                signal="context_overlap",
                source=CONTEXT_OVERLAP_SOURCE,
                weight=round(win_conf, 6),
            )
        )
    receipt = _provenance.build_receipt(signals)

    if win_conf < bar:
        return Disambiguation(
            word=word,
            lemma=lemma,
            status="uncertain",
            sense_id=None,
            confidence=round(win_conf, 6),
            gloss_ar=None,
            gloss_en=None,
            alternatives=alternatives,
            provenance=tuple(receipt),
            inventory_version=version,
            threshold_used=bar,
            abstained=True,
        )

    return Disambiguation(
        word=word,
        lemma=lemma,
        status="ok",
        sense_id=winner.sense_id,
        confidence=round(win_conf, 6),
        gloss_ar=winner.gloss_ar,
        gloss_en=winner.gloss_en,
        alternatives=alternatives,
        provenance=tuple(receipt),
        inventory_version=version,
        threshold_used=bar,
        abstained=False,
    )
