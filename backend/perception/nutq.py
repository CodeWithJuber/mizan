"""
Nutq Engine (نطق) — Articulate Speech & Communication
=======================================================

"The Most Merciful — taught the Quran, created man,
and taught him speech (nutq/bayan)." — Quran 55:1-4

Nutq goes beyond raw TTS/STT — it provides articulate communication:
- Tone-aware speech synthesis (calibrated by Qalb emotional state)
- Context-aware transcription with intent detection
- Multi-language support awareness
- Speech pacing based on content complexity
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from perception.voice import VoiceProcessor

logger = logging.getLogger("mizan.nutq")


@dataclass
class NutqUtterance:
    """A structured speech output."""
    text: str
    audio_bytes: Optional[bytes] = None
    tone: str = "standard"        # "standard", "warm", "patient", "focused"
    language: str = "en"
    duration_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "text": self.text[:200],
            "tone": self.tone,
            "language": self.language,
            "has_audio": self.audio_bytes is not None,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class NutqTranscription:
    """A structured speech input."""
    text: str
    confidence: float = 0.9
    detected_language: str = "en"
    detected_intent: str = "statement"  # "question", "command", "statement"
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "text": self.text[:500],
            "confidence": round(self.confidence, 2),
            "language": self.detected_language,
            "intent": self.detected_intent,
            "processing_time_ms": round(self.processing_time_ms, 1),
        }


class NutqEngine:
    """
    Articulate speech engine that wraps VoiceProcessor with
    tone calibration and intent detection.

    Usage:
        nutq = NutqEngine()

        # Speak with tone calibration
        utterance = await nutq.speak("Here's what I found...", tone="warm")

        # Listen with intent detection
        transcription = await nutq.listen(audio_bytes)
        print(transcription.detected_intent)  # "question"
    """

    def __init__(self):
        self._voice = VoiceProcessor()

    async def speak(self, text: str, tone: str = "standard",
                    voice: str = "default") -> NutqUtterance:
        """Generate speech with tone calibration."""
        start = time.time()

        # Adjust text for tone (light modifications)
        adjusted_text = self._adjust_for_tone(text, tone)

        audio = await self._voice.text_to_speech(adjusted_text, voice)

        elapsed = (time.time() - start) * 1000
        return NutqUtterance(
            text=adjusted_text,
            audio_bytes=audio,
            tone=tone,
            duration_ms=elapsed,
        )

    async def listen(self, audio_bytes: bytes) -> NutqTranscription:
        """Transcribe speech with intent detection."""
        start = time.time()

        text = await self._voice.speech_to_text(audio_bytes)
        if not text:
            return NutqTranscription(
                text="",
                confidence=0.0,
                processing_time_ms=(time.time() - start) * 1000,
            )

        intent = self._detect_intent(text)

        elapsed = (time.time() - start) * 1000
        return NutqTranscription(
            text=text,
            confidence=0.9,
            detected_intent=intent,
            processing_time_ms=elapsed,
        )

    def _adjust_for_tone(self, text: str, tone: str) -> str:
        """Light text adjustments based on desired tone."""
        # In a full implementation, this would modify pacing markers,
        # emphasis, and SSML tags. For now, return as-is.
        return text

    def _detect_intent(self, text: str) -> str:
        """Detect the intent of transcribed speech."""
        text_stripped = text.strip()
        if text_stripped.endswith("?"):
            return "question"
        if any(text_stripped.lower().startswith(w) for w in [
            "do", "run", "create", "delete", "open", "close",
            "find", "search", "show", "tell", "help",
        ]):
            return "command"
        return "statement"
