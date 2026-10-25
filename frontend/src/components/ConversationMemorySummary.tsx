import { useEffect, useState } from "react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

interface Summary {
  owned_sessions: number;
  stored_chat_messages: number;
  recall_limit: number;
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
    </section>
  );
}
