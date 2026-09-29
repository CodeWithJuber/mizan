/**
 * VerifiedBadge — the trust-moat pill.
 * Every linguistic claim in the morphology UI carries one:
 *  - verified  → green  "✓ verified"      (deterministic backend; tooltip = source)
 *  - heuristic → amber  "heuristic"       (rule-based guess; never labelled verified)
 *  - ai        → gray   "AI-generated"    (LLM output)
 *  - unavailable → slate "unavailable"   (backend honestly has no data)
 */

import type { Provenance } from "../../types/morphology";

interface VerifiedBadgeProps {
  level: Provenance;
  /** Shown as a tooltip on the verified pill (dataset / lexicon name). */
  source?: string;
}

const STYLES: Record<Provenance, string> = {
  verified:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  heuristic:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400",
  ai: "bg-gray-100 dark:bg-zinc-700/40 text-gray-500 dark:text-gray-400",
  unavailable:
    "bg-slate-100 dark:bg-slate-700/40 text-slate-500 dark:text-slate-400",
};

const LABELS: Record<Provenance, string> = {
  verified: "verified",
  heuristic: "heuristic",
  ai: "AI-generated",
  unavailable: "unavailable",
};

export function VerifiedBadge({ level, source }: VerifiedBadgeProps) {
  const title =
    level === "verified"
      ? source
        ? `Verified — source: ${source}`
        : "Verified against the deterministic morphology engine"
      : level === "heuristic"
        ? "Heuristic — rule-based guess, not a verified fact"
        : level === "ai"
          ? "AI-generated — produced by the language model, verify before relying on it"
          : "Unavailable — the backend has no verified data for this yet";

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap ${STYLES[level]}`}
      title={title}
      aria-label={`Provenance: ${title}`}
    >
      {level === "verified" && (
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-3 h-3"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
            clipRule="evenodd"
          />
        </svg>
      )}
      {LABELS[level]}
    </span>
  );
}
