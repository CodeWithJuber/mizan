/**
 * Speak instead of typing (Sama'). The recording is heard on MIZAN's own server
 * and the words go into the message box, where you read them and press Send;
 * nothing is sent on its own. Hidden when the server has no voice input or the
 * browser cannot record.
 */
import { useEffect, useRef, useState } from "react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import { clock, isVoiceStatus, pickRecordingType, recordingName, type VoiceStatus } from "../utils/voice.ts";
import { useToast } from "./Toast";

type Phase = "idle" | "recording" | "hearing";

export function VoiceInput({
  sessionId,
  onHeard,
  disabled,
}: {
  sessionId: string;
  onHeard: (words: string) => void;
  disabled?: boolean;
}) {
  const { addToast } = useToast();
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let live = true;
    authFetch(`${config.API_URL}/voice`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => live && setStatus(isVoiceStatus(body) ? body : null))
      .catch(() => live && setStatus(null));
    return () => {
      live = false;
    };
  }, []);

  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
      recorder.current?.stream.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  const type = typeof MediaRecorder === "undefined" ? "" : pickRecordingType((t) => MediaRecorder.isTypeSupported(t));
  if (!status?.available || !type || !navigator.mediaDevices?.getUserMedia) return null;

  const fail = (title: string, description?: string) => {
    addToast({ type: "warning", title, description });
    setPhase("idle");
  };

  const hear = async (blob: Blob) => {
    if (blob.size > status.max_bytes) return fail("That recording is too long; try a shorter one");
    setPhase("hearing");
    const form = new FormData();
    form.append("file", new File([blob], recordingName(type), { type: blob.type || type }));
    form.append("session_id", sessionId);
    try {
      const response = await authFetch(`${config.API_URL}/voice/transcribe`, { method: "POST", body: form });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) return fail("Could not hear that", String(body.detail || response.statusText));
      if (!String(body.text || "").trim()) return fail("No words were heard; try again closer to the microphone");
      onHeard(String(body.text));
      setStatus((current) => (current ? { ...current, seconds_left: body.seconds_left ?? null } : current));
      setPhase("idle");
    } catch (error) {
      fail("Could not hear that", (error as Error).message);
    }
  };

  const start = async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return fail("Microphone not allowed", "Allow the microphone for MIZAN in your browser to speak.");
    }
    const parts: Blob[] = [];
    const made = new MediaRecorder(stream, { mimeType: type });
    made.ondataavailable = (event) => event.data.size && parts.push(event.data);
    made.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
      void hear(new Blob(parts, { type: made.mimeType || type }));
    };
    recorder.current = made;
    made.start();
    setElapsed(0);
    setPhase("recording");
    const began = Date.now();
    timer.current = window.setInterval(() => {
      const seconds = (Date.now() - began) / 1000;
      setElapsed(seconds);
      if (seconds >= status.max_seconds - 0.5 && made.state === "recording") made.stop();
    }, 250);
  };

  const stop = () => {
    if (recorder.current?.state === "recording") recorder.current.stop();
  };

  const left = status.seconds_left;
  const title =
    phase === "recording"
      ? `Stop and turn into text (${clock(elapsed)} of ${clock(status.max_seconds)})`
      : phase === "hearing"
        ? "Hearing…"
        : `Speak instead of typing${left !== null ? ` (${clock(left)} left today)` : ""}`;

  return (
    <button
      type="button"
      className={`chat-input-btn ${phase === "recording" ? "text-red-500! animate-pulse" : ""}`}
      title={title}
      aria-label={title}
      aria-pressed={phase === "recording"}
      disabled={disabled || phase === "hearing" || (left !== null && left <= 0)}
      onClick={() => (phase === "recording" ? stop() : void start())}
    >
      {phase === "hearing" ? (
        <svg viewBox="0 0 24 24" className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
        </svg>
      ) : phase === "recording" ? (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
          <rect x="5" y="5" width="10" height="10" rx="2" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
          <path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z" />
          <path d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z" />
        </svg>
      )}
    </button>
  );
}
