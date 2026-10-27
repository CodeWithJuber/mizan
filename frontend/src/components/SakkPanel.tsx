/**
 * Sakk: your receipts. Every action MIZAN took or held for you, newest first,
 * each chained to the one before. Verify recomputes the whole chain; Export
 * gives you the chain, your digest key and MIZAN's signed proof to check
 * anywhere with scripts/verify_sakk.py. Receipts hold no words of yours.
 */
import { useCallback, useEffect, useState } from "react";
import { config } from "../config";
import type { ApiClient } from "../types";
import { authFetch } from "../utils/authFetch";
import { short } from "../utils/reliability.ts";
import { KIND_LABELS, isReceipts, outcomeTone, verdictLine, type Receipt, type Verdict } from "../utils/sakk.ts";
import { useToast } from "./Toast";

const TONE = {
  good: "text-emerald-700 dark:text-emerald-400",
  held: "text-amber-700 dark:text-amber-400",
  bad: "text-red-700 dark:text-red-400",
  plain: "text-gray-600 dark:text-gray-400",
};

export default function SakkPanel({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [publicKey, setPublicKey] = useState("");
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (before?: number) => {
      const data = await api.get(`/sakk?limit=50${before ? `&before=${before}` : ""}`);
      if (!isReceipts(data)) return;
      setPublicKey(data.public_key);
      setReceipts((current) => (before ? [...current, ...data.receipts] : data.receipts));
      setMore(data.receipts.length === 50);
    },
    [api],
  );

  useEffect(() => {
    load().catch(() => addToast({ type: "error", title: "Receipts could not be loaded" }));
  }, [load, addToast]);

  const verify = async () => {
    setBusy(true);
    try {
      setVerdict((await api.get("/sakk/verify")) as unknown as Verdict);
    } finally {
      setBusy(false);
    }
  };

  const exportChain = async () => {
    const response = await authFetch(`${config.API_URL}/sakk/export`);
    if (!response.ok) return addToast({ type: "error", title: "Export failed" });
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement("a"), { href: url, download: "mizan-sakk.json" });
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Receipts</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Every action MIZAN takes or holds for you is written here, chained to the one before it, so nothing can be
          changed, removed or reordered later without the chain showing it. Receipts keep no words of yours: only the
          tool, how it ended, and digests under a key that is yours.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary text-sm" onClick={verify} disabled={busy}>
          {busy ? "Checking…" : "Verify my chain"}
        </button>
        <button type="button" className="btn-secondary text-sm" onClick={exportChain}>
          Export to check elsewhere
        </button>
        <a href="/reliability" target="_blank" rel="noreferrer" className="text-sm underline ml-auto">
          MIZAN's signed roots
        </a>
      </div>
      {verdict && (
        <div
          role="status"
          className={`card p-3 text-sm ${verdict.ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}
        >
          {verdict.ok ? "✓ " : "✗ "}
          {verdictLine(verdict)}
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        {receipts.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">No receipts yet. They appear when MIZAN uses a tool for you.</p>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-zinc-800">
            {receipts.map((receipt) => (
              <li key={receipt.seq} className="px-4 py-2 grid grid-cols-[auto_1fr_auto] gap-x-3 items-baseline text-sm">
                <span className="text-xs tabular-nums text-gray-500">#{receipt.seq}</span>
                <span className="min-w-0">
                  <span className={TONE[outcomeTone(receipt.outcome)]}>{receipt.display || receipt.kind}</span>
                  <span className="block text-[11px] text-gray-500">
                    {KIND_LABELS[receipt.kind] ?? receipt.kind} · {new Date(receipt.at).toLocaleString()}
                  </span>
                </span>
                <code className="text-[11px] text-gray-500" title={receipt.hash}>
                  {short(receipt.hash, 8)}
                </code>
              </li>
            ))}
          </ul>
        )}
      </div>
      {more && (
        <button
          type="button"
          className="text-sm underline"
          onClick={() => load(receipts[receipts.length - 1]?.seq)}
        >
          Older receipts
        </button>
      )}
      {publicKey && (
        <p className="text-[11px] text-gray-500 break-all">
          MIZAN's signing key: <code>{publicKey}</code>
        </p>
      )}
    </div>
  );
}
