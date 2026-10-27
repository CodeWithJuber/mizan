/**
 * Bab WhatsApp: link your own number to your MIZAN.
 *
 * MIZAN uses the official Cloud API only as Meta's terms allow: it chats with
 * numbers in the markets where regulators compelled Meta to admit assistants
 * (EEA, Brazil, Türkiye) and elsewhere sends only your notices.
 */
import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";

interface Status {
  available: boolean;
  number: string;
  linked: boolean;
  linked_number: string | null;
  region: string | null;
  mode: "assistant" | "ancillary" | null;
  error: string;
}

interface Code {
  text: string;
  url: string | null;
  expires: number;
}

export function WhatsAppLink({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [status, setStatus] = useState<Status | null>(null);
  const [code, setCode] = useState<Code | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus((await api.get("/bab/whatsapp")) as unknown as Status);
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
        <div className="font-medium text-gray-900 dark:text-gray-100">WhatsApp</div>
        <p className="mt-1">
          Not running. An administrator connects MIZAN's own WhatsApp Business number under
          System settings → Channels (official Cloud API: access token, phone number ID, app
          secret, webhook verify token).{status.error ? ` (${status.error})` : ""}
        </p>
      </div>
    );

  const where =
    status.mode === "assistant"
      ? "you can chat with your own MIZAN there"
      : "Meta's terms let MIZAN send only your notices there (it chats on WhatsApp only in the EEA, Brazil and Türkiye)";

  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100 break-all">
            WhatsApp{status.number ? ` · ${status.number}` : ""}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {status.linked
              ? `Linked to +${status.linked_number}${status.region ? ` (${status.region})` : ""}: ${where}. Actions are never allowed from WhatsApp, and nothing said there is used to train a model.`
              : "Link your number. Where Meta allows assistants, you chat with MIZAN there; elsewhere your notices come there."}
          </p>
        </div>
        {status.linked ? (
          <button
            className="btn-secondary btn-sm min-h-[36px]"
            onClick={async () => {
              await api.del("/bab/whatsapp/link");
              setCode(null);
              await load();
              addToast({ type: "success", title: "WhatsApp unlinked" });
            }}
          >
            Unlink
          </button>
        ) : (
          <button
            className="btn-gold btn-sm min-h-[36px]"
            onClick={async () => {
              try {
                const made = await api.post("/bab/whatsapp/link");
                setCode({
                  text: String(made.text),
                  url: made.url ? String(made.url) : null,
                  expires: Number(made.expires_in),
                });
              } catch (error) {
                addToast({ type: "error", title: "No code made", description: (error as Error).message });
              }
            }}
          >
            Link WhatsApp
          </button>
        )}
      </div>
      {code && !status.linked && (
        <div className="text-xs space-y-1">
          {code.url ? (
            <a className="text-sky-600 dark:text-sky-400 underline break-all" href={code.url} target="_blank" rel="noreferrer">
              Open WhatsApp with the message ready
            </a>
          ) : (
            <p className="text-gray-600 dark:text-gray-300">Send this to MIZAN's WhatsApp number:</p>
          )}
          <code className="block font-mono break-all rounded bg-gray-50 dark:bg-zinc-900 p-2 select-all">
            {code.text}
          </code>
          <p className="text-gray-500 dark:text-gray-400">
            It works once, within {Math.round(code.expires / 60)} minutes.{" "}
            <button className="underline" onClick={load}>I sent it</button>
          </p>
        </div>
      )}
    </div>
  );
}
