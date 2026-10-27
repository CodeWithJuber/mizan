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
}

type Decision = "allow" | "deny";
type State = "waiting" | "working" | "done" | "denied" | "gone";

function HeldActionRow({ item }: { item: HeldAction }) {
  const [state, setState] = useState<State>("waiting");

  const decide = async (decision: Decision) => {
    setState("working");
    try {
      const response = await authFetch(`${config.API_URL}/chat/held/${item.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
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

  return (
    <li className="flex flex-wrap items-center gap-2 py-1.5">
      <code className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-800">
        {item.tool}
      </code>
      {item.reason && (
        <span className="text-2xs text-gray-500 dark:text-gray-400">{item.reason}</span>
      )}
      <span className="ml-auto flex items-center gap-2">
        {state === "waiting" && (
          <>
            <button
              className="btn-gold btn-sm min-h-[36px]"
              onClick={() => decide("allow")}
            >
              Allow once
            </button>
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
      <p className="text-2xs text-gray-600 dark:text-gray-400 mb-1">
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
