/**
 * What MIZAN may do with a person's chats (docs/consent.md): learning for them
 * is on unless they switch it off; their words train a model only if they
 * switch that on. Each change is a signed receipt on the server.
 */
import { useEffect, useState } from "react";
import { Switch } from "@/components/ui/switch";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

const CHOICES = [
  {
    key: "learning",
    initial: true,
    title: "Learn from my chats for me",
    detail:
      "MIZAN keeps what it verified while helping you (wording, programs, repair lessons) so it needs the base model less next time. Everything it keeps is listed in your Daftar above and goes with a chat you erase.",
  },
  {
    key: "training",
    initial: false,
    title: "Let my words help train MIZAN's own model",
    detail:
      "Off unless you turn it on. When on, MIZAN's own language reader learns from each of your messages within seconds (each one is listed below and you can take it back), and your messages may become reviewed training examples. Quran and hadith text is never a training target.",
  },
] as const;

type Key = (typeof CHOICES)[number]["key"];

export function LearningConsent() {
  const [chosen, setChosen] = useState<Record<Key, boolean> | null>(null);
  const [busy, setBusy] = useState<Key | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const defaults = { learning: true, training: false };
      try {
        const response = await authFetch(`${config.API_URL}/chat/preferences`, { signal: controller.signal });
        if (!response.ok) throw new Error("unavailable");
        const data = (await response.json()) as { preferences: { key: string; value: string }[] };
        for (const { key, value } of data.preferences) {
          if (key === "learning" || key === "training") defaults[key] = value.trim().toLowerCase() === "on";
        }
        if (!controller.signal.aborted) setChosen(defaults);
      } catch {
        if (!controller.signal.aborted) setStatus("Your choices could not be loaded. Reopen this page to retry.");
      }
    })();
    return () => controller.abort();
  }, []);

  const change = async (key: Key, on: boolean) => {
    setBusy(key);
    setStatus("");
    try {
      const response = await authFetch(`${config.API_URL}/chat/preferences/${key}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: on ? "on" : "off" }),
      });
      if (!response.ok) throw new Error("not saved");
      setChosen((current) => (current ? { ...current, [key]: on } : current));
      setStatus("Saved. It applies from your next message.");
    } catch {
      setStatus("Could not save your choice. Try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby="learning-consent" className="mx-5 mt-3 rounded-lg border bg-card p-4 text-sm">
      <h3 id="learning-consent" className="font-semibold">What MIZAN may learn</h3>
      <div className="mt-3 space-y-4">
        {CHOICES.map((choice) => (
          <div key={choice.key} className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <label htmlFor={`consent-${choice.key}`} className="font-medium">{choice.title}</label>
              <p className="mt-0.5 text-xs text-muted-foreground">{choice.detail}</p>
            </div>
            <Switch
              id={`consent-${choice.key}`}
              aria-label={choice.title}
              checked={chosen ? chosen[choice.key] : choice.initial}
              disabled={chosen === null || busy !== null}
              onCheckedChange={(on) => void change(choice.key, on)}
            />
          </div>
        ))}
      </div>
      {status && <output aria-live="polite" className="mt-3 block text-xs text-muted-foreground">{status}</output>}
    </section>
  );
}
