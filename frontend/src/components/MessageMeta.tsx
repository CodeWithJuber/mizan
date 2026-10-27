import { useState } from "react";
import type { MessageUsageMeta } from "../types";
import { isIsnad } from "../utils/isnad.ts";
import IsnadView from "./IsnadView";
import { fmtCost, fmtTokens, usageMetrics } from "../utils/responseMetrics.ts";
export { fmtCost, fmtLatency, fmtTokens } from "../utils/responseMetrics.ts";

/** True when there is anything worth showing. */
export function hasDisplayableMeta(meta?: MessageUsageMeta): boolean {
  return usageMetrics(meta).parts.length > 0;
}

interface MessageMetaProps {
  meta?: MessageUsageMeta;
}

/**
 * Per-assistant-message transparency line (chat workstreams C + E).
 *
 * Collapsed by default: a single subtle line — model · in/out tokens ·
 * application-measured model-call time · reported/estimated cost.
 * Clicking explains the sources and shows the raw metadata for auditing.
 * Renders nothing when there is no metadata.
 */
export function MessageMeta({ meta }: MessageMetaProps) {
  const [open, setOpen] = useState(false);
  if (!hasDisplayableMeta(meta)) return null;
  const m = meta as MessageUsageMeta;

  const { parts, explanations } = usageMetrics(m);

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex max-w-full items-start gap-1.5 text-left text-[10px] font-mono text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        aria-expanded={open}
        title={open ? "Hide response details" : "Show response details"}
      >
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-2.5 h-2.5 shrink-0 mt-0.5 transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
        <span className="min-w-0 wrap-break-word">{parts.join(" · ")}</span>
        {m.cost_usd != null && Number.isFinite(m.cost_usd) && m.cost_usd >= 0 && m.cost_estimated && (
          <span
            className="text-gray-300 dark:text-gray-600"
            title="Estimated from public list prices, not your actual bill"
          >
            est.
          </span>
        )}
      </button>
      {isIsnad(m.isnad) && <IsnadView isnad={m.isnad} />}
      {open && (
        <div className="mt-1.5 space-y-1.5">
          {explanations.map((text) => (
            <p key={text} className="wrap-break-word text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">{text}</p>
          ))}
          <pre className="max-h-64 overflow-auto rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-900 p-3 text-[10px] leading-relaxed font-mono text-gray-600 dark:text-gray-400 whitespace-pre-wrap break-all">
            {JSON.stringify(m, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

interface SessionUsageFooterProps {
  totalInput: number;
  totalOutput: number;
  totalCost: number;
  estimated: boolean;
  messageCount: number;
}

/** Running session totals — rendered only when at least one message in the
 *  session reported usage. Subtle, above the composer. */
export function SessionUsageFooter({
  totalInput,
  totalOutput,
  totalCost,
  estimated,
  messageCount,
}: SessionUsageFooterProps) {
  if (messageCount === 0) return null;
  return (
    <div className="flex justify-center pb-1">
      <div
        className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-mono text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-zinc-900/60 border border-gray-100 dark:border-zinc-800"
        title={
          estimated
            ? "Reported token totals; cost estimated from a price table, not your actual bill"
            : "Totals of provider-reported usage; missing counts are excluded"
        }
      >
        <span>session</span>
        <span aria-hidden="true">·</span>
        <span>
          {fmtTokens(totalInput)} in / {fmtTokens(totalOutput)} out
        </span>
        {totalCost > 0 && (
          <>
            <span aria-hidden="true">·</span>
            <span>{fmtCost(totalCost, estimated)}</span>
            {estimated && (
              <span className="text-gray-300 dark:text-gray-600">est.</span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
