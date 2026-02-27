"""
MIZAN Skills Platform (Hikmah - حِكْمَة — Wisdom)
=====================================================

"He gives wisdom (Hikmah) to whom He wills" — Quran 2:269

Extensible skills framework. Each skill is a unit of wisdom
that agents can learn and use. Better than OpenClaw's ClawHub:
every skill is Wali-guarded and Izn-permissioned.
"""

from .base import SkillBase as SkillBase
from .base import SkillManifest as SkillManifest
from .registry import SkillRegistry as SkillRegistry
