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
from dataclasses import dataclass

from perception.voice import VoiceProcessor

logger = logging.getLogger("mizan.nutq")


@dataclass
class NutqUtterance:
    """A structured speech output."""

    text: str
    audio_bytes: bytes | None = None
    tone: str = "standard"  # "standard", "warm", "patient", "focused"
    language: str = "en"
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
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

    def to_dict(self) -> dict:
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

    async def speak(
        self,
        text: str,
        tone: str = "standard",
        voice: str = "default",
        qalb_state: str = "",
    ) -> NutqUtterance:
        """Generate speech with tone calibration, optionally driven by Qalb state."""
        start = time.time()

        # Qalb-driven tone override (when tone is default "standard")
        effective_tone = tone
        if qalb_state and tone == "standard":
            qalb_tone_map = {
                "frustrated": "patient",
                "anxious": "warm",
                "confused": "patient",
                "fatigued": "warm",
                "determined": "focused",
                "positive": "warm",
            }
            effective_tone = qalb_tone_map.get(qalb_state, tone)

        adjusted_text = self._adjust_for_tone(text, effective_tone)
        language = self._detect_language(adjusted_text)
        audio = await self._voice.text_to_speech(adjusted_text, voice)

        elapsed = (time.time() - start) * 1000
        return NutqUtterance(
            text=adjusted_text,
            audio_bytes=audio,
            tone=effective_tone,
            language=language,
            duration_ms=elapsed,
        )

    async def listen(self, audio_bytes: bytes) -> NutqTranscription:
        """Transcribe speech with intent and language detection."""
        start = time.time()

        text = await self._voice.speech_to_text(audio_bytes)
        if not text:
            return NutqTranscription(
                text="",
                confidence=0.0,
                processing_time_ms=(time.time() - start) * 1000,
            )

        intent = self._detect_intent(text)
        language = self._detect_language(text)

        elapsed = (time.time() - start) * 1000
        return NutqTranscription(
            text=text,
            confidence=0.9,
            detected_language=language,
            detected_intent=intent,
            processing_time_ms=elapsed,
        )

    @staticmethod
    def _adjust_for_tone(text: str, tone: str) -> str:
        """Light text adjustments based on desired tone."""
        if not text:
            return text

        if tone == "warm":
            # Softer pacing: add pause markers between sentences
            text = text.replace(". ", "... ").replace("! ", "... ")
        elif tone == "patient":
            # Slow down: extra spacing between sentences
            text = text.replace(". ", ".   ").replace("? ", "?   ")
        elif tone == "focused":
            # Strip filler words for conciseness
            fillers = ["well, ", "so, ", "you know, ", "basically, ", "actually, ", "like, "]
            for filler in fillers:
                text = text.replace(filler, "")
                text = text.replace(filler.capitalize(), "")

        return text

    @staticmethod
    def _detect_intent(text: str) -> str:
        """Detect the intent of transcribed speech."""
        text_stripped = text.strip()
        if not text_stripped:
            return "statement"

        text_lower = text_stripped.lower()

        # Question detection: question mark or question words at start
        if text_stripped.endswith("?"):
            return "question"
        question_starts = [
            "what ", "where ", "when ", "who ", "whom ", "which ", "why ", "how ",
            "is it ", "are there ", "can you ", "could you ", "would you ",
            "do you ", "does it ", "will it ", "shall ",
        ]
        if any(text_lower.startswith(q) for q in question_starts):
            return "question"

        # Greeting detection
        greetings = [
            "hello", "hi ", "hey ", "good morning", "good afternoon",
            "good evening", "salam", "assalamu",
        ]
        if any(text_lower.startswith(g) for g in greetings):
            return "greeting"

        # Farewell detection
        farewells = ["goodbye", "bye", "see you", "take care", "good night", "ma'a salama"]
        if any(text_lower.startswith(f) for f in farewells):
            return "farewell"

        # Confirmation/negation
        if text_lower in ("yes", "yeah", "yep", "sure", "ok", "okay", "right", "correct"):
            return "confirmation"
        if text_lower in ("no", "nope", "nah", "wrong", "incorrect"):
            return "negation"

        # Command detection: imperative verbs
        command_verbs = [
            "do ", "run ", "create ", "delete ", "open ", "close ", "find ", "search ",
            "show ", "tell ", "help ", "make ", "build ", "write ", "read ", "send ",
            "stop ", "start ", "restart ", "install ", "update ", "fix ", "check ",
            "list ", "get ", "set ", "add ", "remove ", "move ", "copy ", "save ",
            "load ", "deploy ", "test ", "analyze ", "explain ", "summarize ",
        ]
        if any(text_lower.startswith(w) for w in command_verbs):
            return "command"

        # Request detection (polite commands)
        request_patterns = ["please ", "could you ", "can you ", "would you ", "i need ", "i want "]
        if any(text_lower.startswith(p) for p in request_patterns):
            return "request"

        return "statement"

    @staticmethod
    def _detect_language(text: str) -> str:
        """Basic language detection based on Unicode character ranges."""
        if not text:
            return "en"

        # Count characters in Arabic Unicode range
        arabic_count = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
        # Extended Arabic (includes Urdu-specific)
        extended_arabic = sum(1 for c in text if "\uFB50" <= c <= "\uFDFF" or "\uFE70" <= c <= "\uFEFF")
        total_alpha = sum(1 for c in text if c.isalpha())

        if total_alpha == 0:
            return "en"

        arabic_ratio = (arabic_count + extended_arabic) / total_alpha

        if arabic_ratio > 0.3:
            # Distinguish Arabic from Urdu by checking for Urdu-specific characters
            urdu_specific = sum(1 for c in text if c in "\u0679\u067E\u0686\u0688\u0691\u0698\u06BA\u06BE\u06C1\u06CC\u06D2")
            if urdu_specific > 0:
                return "ur"
            return "ar"

        return "en"
