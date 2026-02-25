"""
Voice Processing (Sama' - سَمْع)
===================================

"Say: He is the one who created you and made for you hearing and vision and hearts" — Quran 67:23

Text-to-Speech and Speech-to-Text with multiple backends.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("mizan.voice")


class VoiceProcessor:
    """
    Voice I/O processor.
    Supports ElevenLabs for TTS and Whisper for STT.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
        self._openai_key = os.getenv("OPENAI_API_KEY", "")

    async def text_to_speech(self, text: str, voice: str = "default") -> Optional[bytes]:
        """Convert text to speech audio bytes"""
        if self._elevenlabs_key:
            return await self._tts_elevenlabs(text, voice)
        return None

    async def speech_to_text(self, audio_bytes: bytes) -> Optional[str]:
        """Convert speech audio to text"""
        if self._openai_key:
            return await self._stt_whisper(audio_bytes)
        return None

    async def _tts_elevenlabs(self, text: str, voice: str) -> Optional[bytes]:
        """Text-to-Speech via ElevenLabs"""
        try:
            from elevenlabs import ElevenLabs

            client = ElevenLabs(api_key=self._elevenlabs_key)

            audio_generator = client.text_to_speech.convert(
                text=text[:5000],
                voice_id=voice if voice != "default" else "21m00Tcm4TlvDq8ikWAM",
                model_id="eleven_monolingual_v1",
            )

            # Collect audio bytes
            audio_bytes = b""
            for chunk in audio_generator:
                audio_bytes += chunk

            return audio_bytes

        except ImportError:
            logger.warning("[VOICE] elevenlabs not installed")
            return None
        except Exception as e:
            logger.error(f"[VOICE] ElevenLabs TTS failed: {e}")
            return None

    async def _stt_whisper(self, audio_bytes: bytes) -> Optional[str]:
        """Speech-to-Text via OpenAI Whisper API"""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._openai_key}"},
                    files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                    data={"model": "whisper-1"},
                )

                if response.status_code == 200:
                    return response.json().get("text", "")
                else:
                    logger.error(f"[VOICE] Whisper API error: {response.text}")
                    return None

        except Exception as e:
            logger.error(f"[VOICE] Whisper STT failed: {e}")
            return None
