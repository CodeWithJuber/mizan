"""Dialect -> root normalization (use case #6).

Maps dialectal Arabic word forms (Egyptian / Levantine / Gulf /
Maghrebi) into Ruh's root-space via explicit per-region affix-stripper
tables, then the shared MSA morphological analyzer.

BETA / UNVERIFIED: the analyzer and these tables have NEVER been run
against real dialectal text (NADI/MADAR eval is a separate track's
job). Non-Semitic loanwords (Maghrebi French stock, ~20-30% of tokens
per the study) go to the foreign bucket -- this module NEVER invents a
root for them. Unknown forms return low confidence + ``needs_review``.

Torch-free: see ``ruh_model/reader/__init__.py`` for why submodules are
not imported eagerly here.
"""

__all__ = ["normalize"]
