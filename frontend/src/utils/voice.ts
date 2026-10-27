/**
 * Voice input helpers (Sama'): which recording format the browser can make,
 * how the heard words join what is already typed, and how long is left.
 */

// Opus in WebM (Chrome, Firefox, Edge) first; MP4/AAC for Safari.
export const RECORDING_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

export function pickRecordingType(supported: (type: string) => boolean): string {
  return RECORDING_TYPES.find((type) => supported(type)) ?? "";
}

/** The upload's file name, from the recording's type. */
export function recordingName(type: string): string {
  const base = type.split(";")[0];
  const extension = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a" }[base];
  return `voice.${extension ?? "webm"}`;
}

/** The heard words go after what is already typed, never replacing it. */
export function withHeard(typed: string, heard: string): string {
  const words = heard.trim();
  if (!words) return typed;
  if (!typed.trim()) return words;
  return /\s$/.test(typed) ? typed + words : `${typed} ${words}`;
}

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export interface VoiceStatus {
  available: boolean;
  seconds_left: number | null;
  max_seconds: number;
  max_bytes: number;
}

export function isVoiceStatus(value: unknown): value is VoiceStatus {
  const status = value as VoiceStatus | null;
  return !!status && typeof status.available === "boolean" && typeof status.max_seconds === "number";
}

// A run of Arabic-script text holding vowel or Quranic annotation marks.
const ARABIC = "\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF";
const QURANIC = new RegExp(`[${ARABIC}\\s]*[\u064B-\u065F\u0670\u06D6-\u06ED][${ARABIC}\\s]*`, "g");

/**
 * What "Speak" reads aloud: the answer as plain text without code, links or
 * Quranic text. Quran is recited by people, with tajwid; a speech engine does
 * not recite it, so vowelled Arabic is named instead of read.
 */
export function speakable(plain: string): string {
  return plain
    .replace(/```[\s\S]*?```/g, " (code) ")
    .replace(/`[^`]*`/g, " ")
    .replace(/https?:\/\/\S+/g, " (link) ")
    .replace(QURANIC, " (Quran text, read it yourself) ")
    .replace(/[ \t]+/g, " ")
    .replace(/(\(Quran text, read it yourself\)\s*)+/g, "(Quran text, read it yourself) ")
    .trim();
}
