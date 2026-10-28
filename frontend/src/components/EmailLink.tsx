/**
 * Bab email: link your own address to your MIZAN.
 *
 * MIZAN gives a one-time code (10 minutes); mailing "link <code>" to MIZAN's
 * address from your own address links it. MIZAN then answers only mail from
 * that address, and only when your provider proved it was really you (DMARC).
 */
import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";

interface Status {
  available: boolean;
  address: string;
  linked: boolean;
  linked_address: string | null;
  error: string;
}

interface Code {
  subject: string;
  address: string;
  expires: number;
}

export function EmailLink({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [status, setStatus] = useState<Status | null>(null);
  const [code, setCode] = useState<Code | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus((await api.get("/bab/email")) as unknown as Status);
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
      <div className="card p-4 text-sm text-muted-foreground">
        <div className="font-medium text-foreground">Email</div>
        <p className="mt-1">
          Not running. An administrator gives MIZAN its own mailbox under System settings →
          Channels (address, app password, IMAP and SMTP servers, and the receiving server's
          name).{status.error ? ` (${status.error})` : ""}
        </p>
      </div>
    );

  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground break-all">
            Email · {status.address}
          </div>
          <p className="text-xs text-muted-foreground">
            {status.linked
              ? `Linked to ${status.linked_address}: mail from it goes to your own MIZAN, and the answer comes back by mail. Actions are never allowed by mail.`
              : "Mail MIZAN from your own address. Only your linked address is answered, and only when your provider proves the mail is yours."}
          </p>
        </div>
        {status.linked ? (
          <button
            className="btn-secondary btn-sm min-h-[36px]"
            onClick={async () => {
              await api.del("/bab/email/link");
              setCode(null);
              await load();
              addToast({ type: "success", title: "Email unlinked" });
            }}
          >
            Unlink
          </button>
        ) : (
          <button
            className="btn-gold btn-sm min-h-[36px]"
            onClick={async () => {
              try {
                const made = await api.post("/bab/email/link");
                setCode({
                  subject: String(made.subject),
                  address: String(made.address),
                  expires: Number(made.expires_in),
                });
              } catch (error) {
                addToast({ type: "error", title: "No code made", description: (error as Error).message });
              }
            }}
          >
            Link email
          </button>
        )}
      </div>
      {code && !status.linked && (
        <div className="text-xs space-y-1">
          <p className="text-foreground/75">
            From your own address, send a mail to <span className="font-mono break-all">{code.address}</span>{" "}
            with this subject:
          </p>
          <code className="block font-mono break-all rounded bg-muted/50 p-2 select-all">
            {code.subject}
          </code>
          <p className="text-muted-foreground">
            It works once, within {Math.round(code.expires / 60)} minutes. MIZAN replies when it is
            linked. <button className="underline" onClick={load}>I sent it</button>
          </p>
        </div>
      )}
    </div>
  );
}
