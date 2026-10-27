/**
 * Bab Telegram: link your own Telegram account to your MIZAN.
 *
 * MIZAN gives a one-time link (10 minutes); opening it in Telegram sends the
 * code back to the bot, which then answers only you, in a private chat, with
 * your own agent. Watcher notices and held actions come there too.
 */
import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";

interface Status {
  available: boolean;
  bot: string;
  linked: boolean;
  linked_at: string | null;
  error: string;
}

export function TelegramLink({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [status, setStatus] = useState<Status | null>(null);
  const [link, setLink] = useState<{ url: string; expires: number } | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus((await api.get("/bab/telegram")) as unknown as Status);
    } catch {
      setStatus(null);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  if (!status) return null;
  if (!status.available)
    return (
      <div className="card p-4 text-sm text-gray-600 dark:text-gray-400">
        <div className="font-medium text-gray-900 dark:text-gray-100">Telegram</div>
        <p className="mt-1">
          Not running. An administrator turns it on by saving a bot token from @BotFather as
          TELEGRAM_BOT_TOKEN in System settings.{status.error ? ` (${status.error})` : ""}
        </p>
      </div>
    );

  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Telegram{status.bot ? ` · @${status.bot}` : ""}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {status.linked
              ? "Linked: messages to the bot go to your own MIZAN, and your watchers' notices come there."
              : "Talk to your own MIZAN from Telegram. Only your linked account is answered, in a private chat."}
          </p>
        </div>
        {status.linked ? (
          <button
            className="btn-secondary btn-sm min-h-[36px]"
            onClick={async () => {
              await api.del("/bab/telegram/link");
              setLink(null);
              await load();
              addToast({ type: "success", title: "Telegram unlinked" });
            }}
          >
            Unlink
          </button>
        ) : (
          <button
            className="btn-gold btn-sm min-h-[36px]"
            onClick={async () => {
              try {
                const made = await api.post("/bab/telegram/link");
                setLink({ url: String(made.url), expires: Number(made.expires_in) });
              } catch (error) {
                addToast({ type: "error", title: "No link made", description: (error as Error).message });
              }
            }}
          >
            Link Telegram
          </button>
        )}
      </div>
      {link && !status.linked && (
        <div className="text-xs space-y-1">
          <a className="text-sky-600 dark:text-sky-400 underline break-all" href={link.url} target="_blank" rel="noreferrer">
            {link.url}
          </a>
          <p className="text-gray-500 dark:text-gray-400">
            Open it on the phone with your Telegram and press Start. It works once, within{" "}
            {Math.round(link.expires / 60)} minutes.{" "}
            <button className="underline" onClick={load}>I pressed Start</button>
          </p>
        </div>
      )}
    </div>
  );
}
