/**
 * HeldActions — actions a watcher or other unattended run wanted to take.
 *
 * No one was watching that run, so MIZAN held each action that needs a person
 * with its exact parameters. Allowed, it runs once, as held; denied, never.
 */
import { useState } from "react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

export interface HeldAction {
  id: string;
  tool: string;
  reason?: string;
  /** The parameters as shown on a card (maybe cut short), when the action came with a chat reply. */
  shown?: string;
  complete?: boolean;
  /** The exact parameters, when read from the held-actions list. */
  params?: unknown;
  /** SHA-256 of the parameters; an approval is bound to it. */
  params_sha256?: string;
}

/** Every parameter as text, or null when only part of them is known here. */
function everything(item: HeldAction): string | null {
  if (item.params !== undefined) return JSON.stringify(item.params, null, 1);
  return item.complete && item.shown ? item.shown : null;
}

type Decision = "allow" | "deny";
type State = "waiting" | "working" | "done" | "denied" | "gone";

function HeldActionRow({ item }: { item: HeldAction }) {
  const [state, setState] = useState<State>("waiting");
  const [full, setFull] = useState<string | null>(() => everything(item));

  // Allow is offered only once every parameter can be read here.
  const loadAll = async () => {
    try {
      const response = await authFetch(`${config.API_URL}/chat/held`);
      if (!response.ok) return;
      const data = (await response.json()) as { held?: HeldAction[] };
      const found = data.held?.find((held) => held.id === item.id);
      if (found) setFull(everything(found));
      else setState("gone");
    } catch {
      /* stays as it was; Deny still works */
    }
  };

  const decide = async (decision: Decision) => {
    setState("working");
    try {
      const response = await authFetch(`${config.API_URL}/chat/held/${item.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          item.params_sha256 ? { decision, params_sha256: item.params_sha256 } : { decision }
        ),
      });
      if (!response.ok) {
        setState("gone");
        return;
      }
      setState(decision === "allow" ? "done" : "denied");
    } catch {
      setState("waiting");
    }
  };

  const preview = full ?? item.shown;
  return (
    <li className="flex flex-wrap items-center gap-2 py-1.5">
      <code className="text-xs px-1.5 py-0.5 rounded bg-muted">
        {item.tool}
      </code>
      {item.reason && (
        <span className="text-2xs text-muted-foreground">{item.reason}</span>
      )}
      <span className="ml-auto flex items-center gap-2">
        {state === "waiting" && (
          <>
            {full !== null ? (
              <button
                className="btn-gold btn-sm min-h-[36px]"
                onClick={() => decide("allow")}
              >
                Allow once
              </button>
            ) : (
              <button className="btn-secondary btn-sm min-h-[36px]" onClick={loadAll}>
                Read all parameters
              </button>
            )}
            <button
              className="btn-secondary btn-sm min-h-[36px]"
              onClick={() => decide("deny")}
            >
              Deny
            </button>
          </>
        )}
        {state === "working" && <span className="text-2xs text-gray-500">Running…</span>}
        {state === "done" && (
          <span className="text-2xs text-emerald-600 dark:text-emerald-400">
            Allowed: the result is in this chat
          </span>
        )}
        {state === "denied" && <span className="text-2xs text-gray-500">Denied</span>}
        {state === "gone" && (
          <span className="text-2xs text-gray-500">Already decided or expired</span>
        )}
      </span>
      {preview && (
        <details className="w-full" open={full !== null && full.length < 400}>
          <summary className="text-2xs text-muted-foreground cursor-pointer">
            What it will do
            {item.params_sha256 && (
              <span className="font-mono"> · fingerprint {item.params_sha256.slice(0, 12)}</span>
            )}
          </summary>
          <pre className="mt-1 text-2xs whitespace-pre-wrap break-all rounded bg-muted/50 p-2 max-h-64 overflow-auto">
            {preview}
            {full === null && "\n… (cut short)"}
          </pre>
        </details>
      )}
    </li>
  );
}

export function HeldActions({ items }: { items: HeldAction[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-amber-300/50 dark:border-amber-500/20 bg-amber-50/60 dark:bg-amber-500/5 px-3 py-2">
      <div className="text-xs font-medium text-amber-800 dark:text-amber-300">
        Waiting for your approval
      </div>
      <p className="text-2xs text-muted-foreground mb-1">
        No one was watching this run, so MIZAN held these actions instead of taking them.
        They expire after 24 hours.
      </p>
      <ul>
        {items.map((item) => (
          <HeldActionRow key={item.id} item={item} />
        ))}
      </ul>
    </div>
  );
}
