import { useEffect, useState } from "react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

interface Summary {
  owned_sessions: number;
  stored_chat_messages: number;
  recall_limit: number;
}

interface Preference {
  key: string;
  value: string;
}

const preferenceFields = [
  { key: "language", label: "Fallback reply language", limit: 120 },
  { key: "greeting", label: "Preferred greeting", limit: 120 },
  { key: "avoid_greetings", label: "Greetings to avoid", limit: 300 },
  { key: "custom_instructions", label: "Other reply preferences", limit: 2000 },
  { key: "muhasaba", label: "MIZAN's corrections of earlier answers (write off to stop them)", limit: 8 },
] as const;

function PreferenceField({ field, saved }: {
  field: typeof preferenceFields[number]; saved: string;
}) {
  const [value, setValue] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const save = async () => {
    setBusy(true);
    setStatus("");
    try {
      const response = await authFetch(`${config.API_URL}/chat/preferences/${field.key}`, {
        method: value.trim() ? "PUT" : "DELETE",
        headers: { "Content-Type": "application/json" },
        ...(value.trim() ? { body: JSON.stringify({ value }) } : {}),
      });
      if (!response.ok) throw new Error("Could not save this preference. Try again.");
      setStatus(value.trim() ? "Saved for your future chats." : "Preference removed.");
    } catch {
      setStatus("Could not save this preference. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <label htmlFor={`chat-preference-${field.key}`} className="block text-xs font-medium mb-1">
        {field.label}
      </label>
      <div className="flex gap-2">
        <textarea
          id={`chat-preference-${field.key}`}
          rows={field.key === "custom_instructions" ? 3 : 1}
          maxLength={field.limit}
          value={value}
          disabled={busy}
          onChange={(event) => { setValue(event.target.value); setStatus(""); }}
          className="min-w-0 flex-1 rounded border border-input bg-transparent px-2 py-1.5"
        />
        <button type="button" disabled={busy} onClick={() => void save()}
          className="self-start rounded border border-input px-3 py-1.5 disabled:opacity-50">
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
      {field.key === "language" && <p className="mt-1 text-xs text-gray-500">
        Used for ambiguous or language-neutral prompts. An explicit language request takes priority;
        otherwise replies follow the current message's language. Greeting preferences are separate.
      </p>}
      {status && <p role="status" className="mt-1 text-xs">{status}</p>}
    </div>
  );
}

function ChatPreferences() {
  const [preferences, setPreferences] = useState<Preference[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await authFetch(`${config.API_URL}/chat/preferences`, { signal: controller.signal });
        if (!response.ok) throw new Error("Preferences unavailable");
        const data = await response.json() as { preferences: Preference[] };
        if (!controller.signal.aborted) setPreferences(data.preferences);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    })();
    return () => controller.abort();
  }, []);
  return (
    <div className="mt-4 border-t border-amber-200 dark:border-amber-900 pt-3">
      <h4 className="font-semibold">Your reply preferences</h4>
      <p className="mt-1 mb-3 text-xs text-gray-500">
        Saved for your account across conversations. Your current request takes priority.
        Clear a field and save to forget it.
      </p>
      {error ? <p role="status">Preferences are unavailable. Reopen this page to retry.</p>
        : preferences === null ? <p>Loading preferences…</p>
          : <div className="grid gap-3 sm:grid-cols-2">{preferenceFields.map((field) => (
            <PreferenceField key={field.key} field={field}
              saved={preferences.find((preference) => preference.key === field.key)?.value ?? ""} />
          ))}</div>}
    </div>
  );
}

export function ConversationMemorySummary() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await authFetch(`${config.API_URL}/chat/memory/summary`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Memory unavailable");
        const data = (await response.json()) as Summary;
        if (!controller.signal.aborted) {
          setSummary(data);
          setError(false);
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  return (
    <section className="mx-5 mt-3 p-4 rounded-lg border border-amber-200 dark:border-amber-900 text-sm">
      <h3 className="font-semibold">Your chat memory</h3>
      {error ? (
        <p role="status">Chat memory status is temporarily unavailable.</p>
      ) : summary ? (
        <>
          <p>{summary.stored_chat_messages} saved messages across {summary.owned_sessions} conversations.</p>
          <p className="mt-1 text-xs text-gray-500">
            New chats can recall up to {summary.recall_limit} recent or relevant statements from your other conversations.
            This is separate from the knowledge records below and does not train model weights.
          </p>
        </>
      ) : <p>Loading chat memory…</p>}
      <ChatPreferences />
    </section>
  );
}
