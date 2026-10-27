# Sama' (سَمْع): speak to MIZAN

You can speak instead of typing: with the microphone button in the message box, or by sending a Telegram voice note to a linked bot ([Bab](bab.md)). MIZAN turns speech into text **on its own server**. The audio is never sent to another service and is kept nowhere. Every answer has a **Read aloud** button; it uses the browser's own voice and never recites Quran.

The code is in `backend/perception/sama.py`, the `/api/voice*` routes in `backend/api/main.py`, `frontend/src/components/VoiceInput.tsx` and `frontend/src/utils/voice.ts`.

## How it hears

- **Engine:** [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) 1.2 (MIT) runs OpenAI's Whisper weights (MIT), as [Systran's CTranslate2 conversion](https://huggingface.co/Systran), on the CPU.
  - Settings: int8, one beam, and voice-activity detection, so silence is skipped.
  - Audio is decoded with PyAV, at most 90 seconds.
- **The model:**
  - Downloaded once, at a pinned revision, into `$MIZAN_DATA_DIR/models/whisper`. The base model is 145 MB.
  - Loaded on first use, which takes about 10 s including the download. After that a 5-second recording takes about 1.5 s on two CPU threads.
  - Let go after 10 idle minutes. Recordings are heard one at a time.
- **Which language** is a posterior, not a setting:

  ```
  language = argmax  P(lang | audio) · (1 + w·q(lang)) / (N + w)
  ```

  - `P(lang | audio)` is Whisper's own language detection.
  - `q` is the language of your earlier messages in this chat, from [Lughah](fahm.md). Roman Hindi/Urdu counts half towards Hindi and half towards Urdu.
  - `w` is how many earlier messages there are (at most 12).
  - `N` is the number of languages Whisper knows.
  - With no history the prior is flat and the audio decides. A clear recording is never overruled. A borderline one (Hindi or Urdu, which sound alike) follows your chat.
- **Your words as context:** when the chat is in the language you spoke, your recent words (the last 200 characters) are given to Whisper as context, so names and your own spelling, including Roman script, carry over.

## What happens to the words

- **In the web app:** the words go into the message box after anything already typed. You read them and press Send; nothing is sent on its own.
- **In Telegram:** the bot replies "Heard: …" and then answers it like typed text. A forwarded voice note is someone else's words, so it is fenced as data like forwarded text and never treated as your request.

## Limits

| Limit | Value |
|---|---|
| One recording | 2 MB and 90 seconds. Length is checked while decoding, so a long file is never decoded in full. Telegram notes are checked against their announced size and duration before download, and again while downloading. |
| Types | webm, ogg/opus, mp3, m4a/mp4/aac, wav |
| Per user per day | `MIZAN_STT_DAILY_SECONDS` seconds of speech (default 1800) for non-admins |
| Rate | the usual per-user Wali limit |

## Read aloud

- **Engine:** the button under each answer uses the browser's `speechSynthesis`; nothing is sent to MIZAN.
- **What is not read:**
  - code is replaced with "(code)" and links with "(link)";
  - Quranic text is named, not read: "(Quran text, read it yourself)". The Quran is recited by people, with tajwid. Vowelled Arabic or Quranic annotation marks are what identify it.
- **Urdu and Arabic:** Urdu and plain Arabic prose are read normally.

## Settings

Under Settings → System settings → Channels:

| Setting | Default | |
|---|---|---|
| `MIZAN_STT` | on | `off` hides the microphone and turns off Telegram voice notes |
| `MIZAN_STT_MODEL_SIZE` | base | `tiny` (75 MB, fastest), `base` (145 MB) or `small` (484 MB). `small` hears Urdu, Hindi and Arabic best but needs about 500 MB of memory. |
| `MIZAN_STT_DAILY_SECONDS` | 1800 | seconds per non-admin user per day |

`faster-whisper` is in `backend/requirements.txt` (the production image) and in the `voice-local` extra (`pip install -e ".[voice-local]"`). Without it the microphone is hidden and `POST /api/voice/transcribe` answers 503.

The browser needs microphone permission for MIZAN's own origin. The page itself sends no `Permissions-Policy` that blocks it; the API's `microphone=()` applies to API responses only.

## API

| Route | |
|---|---|
| `GET /api/voice` | `{available, seconds_left, max_seconds, max_bytes}`. `seconds_left` is `null` for admins. |
| `POST /api/voice/transcribe` | multipart: `file` and optional `session_id` (your own chat, for the language prior). Returns `{text, language, seconds, seconds_left}`. |

Errors:

- **400:** the recording cannot be heard (wrong type, empty, unreadable, over 90 s).
- **413:** the body is over 2 MB.
- **429:** too fast, or the daily allowance is used up.
- **503:** voice input is not installed or is off.
