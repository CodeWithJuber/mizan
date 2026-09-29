"""Ruh eval harnesses — Phase 0 credibility foundation (beta).

Every quality claim about Ruh is provisional until measured. These modules are
the measurement tools: morphology head-to-head vs CAMeL Tools, dialect scoring
scaffolds (NADI/MADAR), the Q-CSMP benchmark runner, and the adjudication
pilot tooling (Cohen's kappa).

Torch-free by design: modules here must not import torch. The Ruh analyzer
used is :class:`ruh_model.tokenizer.morphology.ArabicMorphAnalyzer`
(stdlib-only rule-based core of Bayan). In torch-less environments, import via
``ruh_model/eval/_bootstrap.py`` (loaded by file path), which registers stub
packages so submodule imports bypass the torch-importing
``ruh_model/__init__.py``.

Status: beta / unverified — harnesses, not results.
"""

__all__ = []
