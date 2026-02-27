"""
QCA — Quranic Cognitive Architecture (القُرآنيّة المعرفيّة)
============================================================

"And Allah brought you out from the wombs of your mothers not knowing anything,
 and He made for you hearing (Sam') and sight (Basar) and hearts (Fu'ad)." — 16:78

A 7-layer cognitive architecture derived from Quranic epistemology,
integrated into MIZAN to provide human-like AGI reasoning capabilities.

Architecture Layers:
  1. Sam' (سمع)    — Sequential temporal input processing
  2. Basar (بصر)   — Structural simultaneous pattern recognition
  3. Fu'ad (فؤاد)  — Integration engine combining both inputs
  4. ISM (اسم)     — Root-Space semantic representation
  5. Mizan (ميزان) — Epistemic weighting and truth calibration
  6. 'Aql (عقل)    — Typed relationship binding engine
  7. Lawh (لوح)    — 4-tier hierarchical memory
  8. Furqan (فرقان) — Discrimination and validated output (Bayan)
"""

from qca.answer_engine import QCAAnswerEngine
from qca.engine import (
    AqlLayer,
    DualInputProcessor,
    FurqanBayan,
    ISMLayer,
    LawhMemory,
    MizanLayer,
    QCAEngine,
)
from qca.training import AqlRelationExtractor, MizanCalibrationTrainer, UGRLTrainer

__all__ = [
    "DualInputProcessor",
    "ISMLayer",
    "MizanLayer",
    "AqlLayer",
    "LawhMemory",
    "FurqanBayan",
    "QCAEngine",
    "QCAAnswerEngine",
    "UGRLTrainer",
    "MizanCalibrationTrainer",
    "AqlRelationExtractor",
]
