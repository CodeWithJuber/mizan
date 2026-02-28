"""
Qalb Processor (قلب) — State-Modulated Global Workspace
=========================================================

"There is a piece of flesh in the body — if it is sound, the whole body is sound;
 if it is corrupt, the whole body is corrupt. Indeed, it is the heart (qalb)."
— Hadith (Bukhari & Muslim)

Upgrades the Qalb from keyword sentiment detection to a **global workspace**
with cardiac-inspired systole/diastole oscillation that modulates LLM parameters.

Cardiac cycle:
  Systole (QABD — قبض)  : Contraction — focused, analytical, precise
  Diastole (BAST — بسط) : Expansion  — creative, exploratory, open

KHUSHU (خشوع) — Deep focus state triggered at high nafs_level + extreme tasks.
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("mizan.qalb_processor")


class QalbState(Enum):
    QABD = "qabd"        # Contraction — analytical, focused
    BAST = "bast"        # Expansion — creative, open
    KHUSHU = "khushu"   # Deep focus — highest attention


@dataclass
class QalbOutput:
    """LLM parameter recommendations from Qalb state."""
    state: QalbState
    max_tokens: int
    temperature: float
    reasoning: str         # Why this state was chosen

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "max_tokens": self.max_tokens,
            "temperature": round(self.temperature, 2),
            "reasoning": self.reasoning,
        }


# LLM params per Qalb state
_STATE_PARAMS = {
    QalbState.QABD: {"max_tokens": 2048, "temperature": 0.3},
    QalbState.BAST: {"max_tokens": 4096, "temperature": 0.75},
    QalbState.KHUSHU: {"max_tokens": 3000, "temperature": 0.45},
}

# Emotional states that force a specific Qalb state
# (from core/qalb.py EmotionalState values)
_EMOTION_TO_STATE = {
    "frustrated": QalbState.QABD,
    "anxious": QalbState.QABD,
    "confused": QalbState.QABD,
    "positive": QalbState.BAST,
    "determined": QalbState.BAST,
    "fatigued": QalbState.QABD,   # Tired → reduce load
    "neutral": None,               # Follow oscillation
}


class QalbProcessor:
    """
    Global workspace with cardiac oscillation.

    The oscillation_phase advances by PHASE_STEP with each call to process().
    Phase 0.0 – 0.5 → Systole (QABD)
    Phase 0.5 – 1.0 → Diastole (BAST)

    Emotional state can override the natural oscillation.
    KHUSHU is triggered when nafs_level >= 4 and task complexity is "extreme".

    Usage:
        processor = QalbProcessor()
        output = processor.process("Analyse logs", emotional_reading, nafs_level=3)
        # Use output.max_tokens and output.temperature in LLM call
    """

    PHASE_STEP = 0.04  # Advance ~25 interactions per full cycle

    def __init__(self):
        self.oscillation_phase: float = 0.0
        self._interaction_count: int = 0

    def process(
        self,
        task: str,
        emotional_state: str = "neutral",
        nafs_level: int = 1,
        complexity: str = "moderate",
    ) -> QalbOutput:
        """
        Determine Qalb state and return LLM parameter recommendations.

        Priority order:
        1. KHUSHU — if nafs_level >= 4 AND complexity == "extreme"
        2. Emotional override — if emotion maps to specific state
        3. Cardiac oscillation — systole vs diastole from phase
        """
        self._interaction_count += 1
        # Advance oscillation
        self.oscillation_phase = (self.oscillation_phase + self.PHASE_STEP) % 1.0

        # 1. KHUSHU override
        if nafs_level >= 4 and complexity == "extreme":
            state = QalbState.KHUSHU
            reasoning = f"KHUSHU: nafs_level={nafs_level} + extreme task"
        # 2. Emotional override
        elif emotional_state in _EMOTION_TO_STATE and _EMOTION_TO_STATE[emotional_state]:
            state = _EMOTION_TO_STATE[emotional_state]
            reasoning = f"Emotional override: {emotional_state} → {state.value}"
        # 3. Cardiac oscillation
        else:
            if self.oscillation_phase < 0.5:
                state = QalbState.QABD
                phase_pct = int(self.oscillation_phase / 0.5 * 100)
                reasoning = f"Systole phase {phase_pct}%: analytical focus"
            else:
                state = QalbState.BAST
                phase_pct = int((self.oscillation_phase - 0.5) / 0.5 * 100)
                reasoning = f"Diastole phase {phase_pct}%: creative expansion"

        params = _STATE_PARAMS[state]
        output = QalbOutput(
            state=state,
            max_tokens=params["max_tokens"],
            temperature=params["temperature"],
            reasoning=reasoning,
        )

        logger.debug(
            "[QALB] phase=%.2f emotion=%s nafs=%d → %s (tokens=%d temp=%.2f)",
            self.oscillation_phase, emotional_state, nafs_level,
            state.value, output.max_tokens, output.temperature,
        )
        return output

    def get_phase_info(self) -> dict:
        """Current oscillation state for monitoring."""
        phase = "systole (QABD)" if self.oscillation_phase < 0.5 else "diastole (BAST)"
        return {
            "oscillation_phase": round(self.oscillation_phase, 3),
            "cardiac_phase": phase,
            "interaction_count": self._interaction_count,
        }
