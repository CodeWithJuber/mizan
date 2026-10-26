"""Tadbir (تدبير): MIZAN's own architecture directs the work; the LLM is only its language faculty.

- ``fahm``: understanding (language, intent, entities) without a model
- ``engine``: plan → act through MIZAN's tools → verify → express
- ``lisan``: the language faculty (the only model calls)
- ``express``: MIZAN's own wording and Furqan checks on Lisan's wording
- ``calc`` and ``quran``: MIZAN's own exact calculation and Quran index
"""

from .engine import MODES, Tadbir, orchestration_mode

__all__ = ["MODES", "Tadbir", "orchestration_mode"]
