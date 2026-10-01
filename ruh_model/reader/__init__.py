"""RootSpace Reader backend -- use case #5 (Build 4).

Precomputed per-word annotation (root + pattern + sense per occurrence)
plus an offline lookup store for a tap-any-word Quran reader.

BETA / UNVERIFIED: root/pattern come from the rule-based
``ArabicMorphAnalyzer`` (never measured against a gold standard);
per-occurrence sense disambiguation requires a scholar-evaluated
sense inventory (see ``annotator.annotate_text``) and is NOT shipped
until that gold eval exists. Confidence values are deterministic
heuristics, not measured accuracy.

Torch-free: ``ruh_model/__init__.py`` imports torch, so this package
deliberately does NOT import its submodules eagerly. Load
``annotator`` / ``store`` directly by file path in torch-less
environments (see ``backend/api/_ruh_loader.py``).
"""

__all__ = ["annotator", "store"]
