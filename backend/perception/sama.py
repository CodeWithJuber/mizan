"""Sama' (سَمْع, hearing): MIZAN turns a short voice message into text on its own server.

Uses ``faster-whisper`` (MIT) with OpenAI's Whisper weights (MIT) converted to
CTranslate2, int8 on the CPU, with voice-activity detection so silence is
skipped. The audio never leaves the server. The model is downloaded once at a
pinned revision into the data volume, loaded on first use, shared, and let go
after ten idle minutes; one recording is transcribed at a time.

Which language was spoken is a posterior, not a setting: Whisper's own
P(language | audio) times a prior from the language of the user's earlier
messages in this chat (Lughah). With no history the prior is flat and the audio
decides; a chat in Roman Hindi/Urdu tips a borderline recording towards Hindi
and Urdu, and its recent words are given to Whisper as context, so names and
spellings follow the user's own.

Limits: 2 MB and 90 seconds per recording, audio types only, and a daily
allowance of seconds per user (``MIZAN_STT_DAILY_SECONDS``). The transcript
goes back to the person, who reads and sends it; it is never acted on unseen.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.sama")

MAX_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 90.0
SAMPLE_RATE = 16_000
IDLE_SECONDS = 600
PROMPT_CHARS = 200
AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/opus",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
}
# Systran's CTranslate2 conversions of the Whisper weights (MIT), pinned.
MODELS = {
    "tiny": "d90ca5fe260221311c53c58e660288d3deb8d356",
    "base": "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
    "small": "536b0662742c02347bc0e980a01041f333bce120",
}
# Lughah's languages as Whisper names them; Roman Hindi/Urdu is spoken Hindustani.
SPOKEN = {
    "en": {"en": 1.0},
    "ar": {"ar": 1.0},
    "ur": {"ur": 1.0},
    "hi": {"hi": 1.0},
    "hi-latn": {"hi": 0.5, "ur": 0.5},
}

_model: Any = None
_model_size = ""
_model_lock = threading.Lock()
_busy = threading.Lock()
_last_used = 0.0


class HearingError(ValueError):
    """The audio cannot be transcribed (too long, too large, wrong type, over the allowance)."""


@dataclass
class Heard:
    text: str
    language: str
    seconds: float


def available() -> bool:
    if os.getenv("MIZAN_STT", "on").strip().lower() in {"off", "0", "false", "no"}:
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _size() -> str:
    size = os.getenv("MIZAN_STT_MODEL_SIZE", "base").strip().lower()
    return size if size in MODELS else "base"


def _load() -> Any:
    global _model, _model_size
    with _model_lock:
        size = _size()
        if _model is None or _model_size != size:
            from faster_whisper import WhisperModel

            root = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "models" / "whisper"
            _model = WhisperModel(
                size,
                device="cpu",
                compute_type="int8",
                cpu_threads=int(os.getenv("MIZAN_STT_THREADS", "2") or 2),
                download_root=str(root),
                revision=MODELS[size],
            )
            _model_size = size
        return _model


def _let_go_when_idle() -> None:
    global _model
    if time.monotonic() - _last_used < IDLE_SECONDS or not _busy.acquire(blocking=False):
        return
    try:
        with _model_lock:
            _model = None
    finally:
        _busy.release()


# ── the daily allowance ─────────────────────────────────────────────────


def _allowance() -> float:
    try:
        return max(0.0, float(os.getenv("MIZAN_STT_DAILY_SECONDS", "1800") or 1800))
    except ValueError:
        return 1800.0


def _key(owner: str) -> str:
    return f"stt:{owner}:{datetime.now(UTC).date().isoformat()}"


def used_today(store: Any, owner: str) -> float:
    try:
        return float(store.get(_key(owner), "0") or 0)
    except ValueError:
        return 0.0


def left_today(store: Any, owner: str) -> float:
    return max(0.0, _allowance() - used_today(store, owner))


# ── which language ──────────────────────────────────────────────────────


def spoken_language(audio_probs: list[tuple[str, float]], earlier: list[str]) -> str:
    """argmax P(audio | lang) P(lang | chat), the chat prior smoothed towards flat."""
    if not audio_probs:
        return ""
    chat: dict[str, float] = {}
    if earlier:
        from tadbir import lughah

        for label, probability in lughah.posterior(earlier[-1], earlier[:-1]).items():
            for spoken, share in SPOKEN.get(label, {}).items():
                chat[spoken] = chat.get(spoken, 0.0) + probability * share
    weight = float(min(len(earlier), 12))  # each earlier message counts once, as Lughah's does
    languages = len(audio_probs)

    def score(item: tuple[str, float]) -> float:
        lang, probability = item
        prior = (1.0 + weight * chat.get(lang, 0.0)) / (languages + weight)
        return probability * prior

    return max(audio_probs, key=score)[0]


def _prompt(language: str, earlier: list[str]) -> str | None:
    """The user's recent words as context, when the chat is in the language spoken."""
    if not earlier or language not in {"en", "ar", "ur", "hi"}:
        return None
    from tadbir import lughah

    chat = lughah.language(earlier[-1], earlier[:-1])
    if language not in SPOKEN.get(chat, {}):
        return None
    return " ".join(earlier)[-PROMPT_CHARS:].strip() or None


# ── hearing ─────────────────────────────────────────────────────────────


def check(audio: bytes, mime: str) -> None:
    kind = (mime or "").split(";", 1)[0].strip().lower()
    if kind not in AUDIO_TYPES:
        raise HearingError("Send a voice recording (webm, ogg, mp3, m4a or wav)")
    if not audio:
        raise HearingError("The recording is empty")
    if len(audio) > MAX_BYTES:
        raise HearingError("The recording is over 2 MB; send a shorter one")


def _decode(audio: bytes) -> Any:
    """Mono 16 kHz float samples, decoding stopped as soon as 90 seconds are passed.

    PyAV directly, not faster-whisper's helper: that helper passes an argument
    PyAV 17+ no longer takes, and it decodes the whole file before any length
    check (2 MB of low-bitrate Opus is most of an hour).
    """
    import av
    import numpy as np

    limit = int(MAX_SECONDS * SAMPLE_RATE)
    chunks: list[Any] = []
    total = 0
    try:
        with av.open(io.BytesIO(audio), mode="r") as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(container.streams.audio[0]):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1))
                    total += chunks[-1].size
                if total > limit:
                    raise HearingError("The recording is over 90 seconds; send a shorter one")
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray().reshape(-1))
    except HearingError:
        raise
    except Exception as exc:  # PyAV raises its own error types for broken files
        raise HearingError("That recording could not be read") from exc
    samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    if samples.size > limit:
        raise HearingError("The recording is over 90 seconds; send a shorter one")
    if not samples.size:
        raise HearingError("The recording has no sound")
    return samples.astype(np.float32) / 32768.0


def _transcribe(audio: bytes, earlier: list[str]) -> Heard:
    global _last_used
    samples = _decode(audio)
    seconds = len(samples) / SAMPLE_RATE
    with _busy:
        model = _load()
        _found, _probability, probs = model.detect_language(audio=samples, vad_filter=True)
        language = spoken_language(probs, earlier) or None
        segments, info = model.transcribe(
            samples,
            language=language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=_prompt(language or "", earlier),
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        _last_used = time.monotonic()
    timer = threading.Timer(IDLE_SECONDS + 1, _let_go_when_idle)
    timer.daemon = True
    timer.start()
    return Heard(text, str(info.language or language or ""), seconds)


async def hear(
    audio: bytes,
    mime: str,
    *,
    owner: str,
    store: Any,
    earlier: list[str] | None = None,
    limited: bool = True,
) -> Heard:
    """Transcribe one short recording for its owner, within their daily allowance."""
    import asyncio

    check(audio, mime)
    if not available():
        raise HearingError("Voice input is not installed on this server")
    if limited and left_today(store, owner) <= 0:
        raise HearingError("Today's voice allowance is used up; type instead, or try tomorrow")
    heard = await asyncio.to_thread(_transcribe, audio, list(earlier or [])[-12:])
    store.put(_key(owner), str(used_today(store, owner) + heard.seconds))
    return heard
