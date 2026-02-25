"""
Qalb Engine (قلب) — Emotional Intelligence & Sentiment Awareness
=================================================================

"Verily, in the remembrance of Allah do hearts (qulub) find rest." — Quran 13:28
"There is a piece of flesh in the body — if it is sound, the whole body
is sound; if it is corrupt, the whole body is corrupt. Indeed, it is the heart (qalb)."
— Hadith (Bukhari & Muslim)

Qalb provides:
- Sentiment analysis of user messages
- Emotional state tracking over time
- Empathetic response calibration
- Tone adjustment based on user emotional state
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("mizan.qalb")


class EmotionalState(Enum):
    """Detected emotional states."""
    NEUTRAL = "neutral"
    POSITIVE = "positive"        # Happy, grateful, excited
    FRUSTRATED = "frustrated"    # Stuck, annoyed
    ANXIOUS = "anxious"          # Worried, uncertain
    CONFUSED = "confused"        # Lost, unclear
    DETERMINED = "determined"    # Focused, driven
    FATIGUED = "fatigued"        # Tired, burnt out


class ToneStyle(Enum):
    """Response tone calibration."""
    STANDARD = "standard"
    ENCOURAGING = "encouraging"
    PATIENT = "patient"
    CONCISE = "concise"
    WARM = "warm"
    FOCUSED = "focused"


# Keyword signals for basic sentiment detection
_SENTIMENT_SIGNALS: Dict[EmotionalState, List[str]] = {
    EmotionalState.FRUSTRATED: [
        "frustrated", "annoyed", "stuck", "broken", "doesn't work",
        "failing", "error", "wrong", "ugh", "impossible", "hate",
    ],
    EmotionalState.ANXIOUS: [
        "worried", "nervous", "scared", "afraid", "anxious",
        "deadline", "urgent", "pressure", "stressed",
    ],
    EmotionalState.CONFUSED: [
        "confused", "don't understand", "unclear", "lost",
        "what does", "how do", "help me understand",
    ],
    EmotionalState.POSITIVE: [
        "thanks", "great", "awesome", "perfect", "love",
        "excellent", "wonderful", "alhamdulillah", "mashallah",
    ],
    EmotionalState.DETERMINED: [
        "let's do", "need to", "must", "important", "focus",
        "priority", "goal", "achieve", "ship",
    ],
    EmotionalState.FATIGUED: [
        "tired", "exhausted", "long day", "burned out", "burnt out",
        "need a break", "too much", "overwhelmed",
    ],
}

# Map emotional states to recommended tones
_STATE_TO_TONE: Dict[EmotionalState, ToneStyle] = {
    EmotionalState.NEUTRAL: ToneStyle.STANDARD,
    EmotionalState.POSITIVE: ToneStyle.WARM,
    EmotionalState.FRUSTRATED: ToneStyle.PATIENT,
    EmotionalState.ANXIOUS: ToneStyle.ENCOURAGING,
    EmotionalState.CONFUSED: ToneStyle.PATIENT,
    EmotionalState.DETERMINED: ToneStyle.FOCUSED,
    EmotionalState.FATIGUED: ToneStyle.ENCOURAGING,
}


@dataclass
class QalbReading:
    """A snapshot of emotional state detection."""
    state: EmotionalState
    confidence: float          # 0.0 - 1.0
    recommended_tone: ToneStyle
    signals_detected: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "state": self.state.value,
            "confidence": round(self.confidence, 2),
            "recommended_tone": self.recommended_tone.value,
            "signals": self.signals_detected[:5],
        }


class QalbEngine:
    """
    Emotional intelligence engine.

    Usage:
        qalb = QalbEngine()

        # Analyze user message
        reading = qalb.analyze("I'm so frustrated, this keeps failing!")
        print(reading.state)            # EmotionalState.FRUSTRATED
        print(reading.recommended_tone) # ToneStyle.PATIENT

        # Track over time
        qalb.record(user_id, reading)
        trend = qalb.get_trend(user_id)
    """

    def __init__(self):
        self._history: Dict[str, List[QalbReading]] = {}

    def analyze(self, message: str) -> QalbReading:
        """Analyze the emotional content of a message."""
        msg_lower = message.lower()

        # Score each emotional state
        scores: Dict[EmotionalState, float] = {}
        signals_found: Dict[EmotionalState, List[str]] = {}

        for state, keywords in _SENTIMENT_SIGNALS.items():
            matched = [kw for kw in keywords if kw in msg_lower]
            if matched:
                scores[state] = len(matched) / len(keywords)
                signals_found[state] = matched

        if not scores:
            return QalbReading(
                state=EmotionalState.NEUTRAL,
                confidence=0.5,
                recommended_tone=ToneStyle.STANDARD,
            )

        # Pick the strongest signal
        best_state = max(scores, key=lambda s: scores[s])
        confidence = min(0.95, scores[best_state] + 0.3)
        tone = _STATE_TO_TONE.get(best_state, ToneStyle.STANDARD)

        return QalbReading(
            state=best_state,
            confidence=confidence,
            recommended_tone=tone,
            signals_detected=signals_found.get(best_state, []),
        )

    def record(self, user_id: str, reading: QalbReading):
        """Record a reading for historical tracking."""
        if user_id not in self._history:
            self._history[user_id] = []
        self._history[user_id].append(reading)
        # Keep last 100 readings per user
        if len(self._history[user_id]) > 100:
            self._history[user_id] = self._history[user_id][-100:]

    def get_trend(self, user_id: str, window: int = 10) -> Dict:
        """Get the emotional trend for a user over recent interactions."""
        readings = self._history.get(user_id, [])[-window:]
        if not readings:
            return {"dominant_state": "neutral", "stability": 1.0, "readings": 0}

        # Count states
        state_counts: Dict[str, int] = {}
        for r in readings:
            state_counts[r.state.value] = state_counts.get(r.state.value, 0) + 1

        dominant = max(state_counts, key=lambda s: state_counts[s])
        stability = state_counts[dominant] / len(readings)

        return {
            "dominant_state": dominant,
            "stability": round(stability, 2),
            "readings": len(readings),
            "state_distribution": state_counts,
        }

    def suggest_response_prefix(self, reading: QalbReading) -> Optional[str]:
        """Suggest an empathetic opening based on detected emotion."""
        prefixes = {
            EmotionalState.FRUSTRATED: "I understand this is frustrating. Let me help — ",
            EmotionalState.ANXIOUS: "No need to worry, we'll work through this together. ",
            EmotionalState.CONFUSED: "Let me explain this clearly. ",
            EmotionalState.FATIGUED: "Let's keep this focused so you can wrap up. ",
            EmotionalState.POSITIVE: "",  # No prefix needed for positive
            EmotionalState.DETERMINED: "",  # Don't slow them down
            EmotionalState.NEUTRAL: "",
        }
        prefix = prefixes.get(reading.state, "")
        return prefix if prefix else None
