import { useState } from "react";
import type { MessageUsageMeta } from "../types";

/** Format a token count compactly: 1234 -> "1.2k". */
export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

/** Format latency: 340 -> "340ms", 1500 -> "1.5s". */
export function fmtLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

/** Format cost. Estimates MUST carry the "~" prefix — never render an
 *  estimate as an exact figure. */
export function fmtCost(usd: number, estimated?: boolean): string {
  const body = usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
  return estimated ? `~${body}` : body;
}

/** True when there is anything worth showing. */
export function hasDisplayableMeta(meta?: MessageUsageMeta): boolean {
  if (!meta) return false;
  return Boolean(
    meta.model ||
    meta.input_tokens != null ||
    meta.output_tokens != null ||
    meta.latency_ms != null ||
    meta.cost_usd != null,
  );
}

interface MessageMetaProps {
  meta?: MessageUsageMeta;
}

/**
 * Per-assistant-message transparency line (chat workstreams C + E).
 *
 * Collapsed by default: a single subtle line — model · in/out tokens ·
 * latency · cost (each shown only when the provider actually reported it).
 * Clicking expands inline to the full raw metadata JSON for auditing.
 * Renders nothing when there is no metadata.
 */
export function MessageMeta({ meta }: MessageMetaProps) {
  const [open, setOpen] = useState(false);
  if (!hasDisplayableMeta(meta)) return null;
  const m = meta as MessageUsageMeta;

  const parts: string[] = [];
  if (m.model) parts.push(m.model);
  if (m.input_tokens != null || m.output_tokens != null) {
    const inT =
      m.input_tokens != null ? `${fmtTokens(m.input_tokens)} in` : null;
    const outT =
      m.output_tokens != null ? `${fmtTokens(m.output_tokens)} out` : null;
    parts.push([inT, outT].filter(Boolean).join(" / "));
  }
  if (m.latency_ms != null) parts.push(fmtLatency(m.latency_ms));
  if (m.cost_usd != null) parts.push(fmtCost(m.cost_usd, m.cost_estimated));

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 text-[10px] font-mono text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        aria-expanded={open}
        title={open ? "Hide response details" : "Show response details"}
      >
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-2.5 h-2.5 transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
        <span>{parts.join(" · ")}</span>
        {m.cost_estimated && (
          <span
            className="text-gray-300 dark:text-gray-600"
            title="Estimated from public list prices, not your actual bill"
          >
            est.
          </span>
        )}
      </button>
      {open && (
        <pre className="mt-1.5 max-h-64 overflow-auto rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-900 p-3 text-[10px] leading-relaxed font-mono text-gray-600 dark:text-gray-400 whitespace-pre-wrap break-all">
          {JSON.stringify(m, null, 2)}
        </pre>
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
            ? "Session totals estimated from public list prices — not your actual bill"
            : "Session totals from provider-reported usage"
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
