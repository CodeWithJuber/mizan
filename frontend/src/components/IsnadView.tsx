/**
 * Isnad (إسناد): the support behind every claim of an answer, and the Mizan
 * (balance) of how much of it MIZAN stands behind.
 */

import { useState } from "react";
import { GRADES, headline, segments, type IsnadSummary } from "../utils/isnad.ts";

export default function IsnadView({ isnad, compact = false }: { isnad: IsnadSummary; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!isnad.claims) return null;
  const bars = segments(isnad);
  return (
    <div className={compact ? "text-xs" : "text-xs mt-1"}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        title="What supports each claim (Isnad)"
      >
        <span className="font-medium">Isnad</span>
        <span
          className="inline-flex h-1.5 w-20 rounded-full overflow-hidden bg-gray-200 dark:bg-zinc-700"
          role="img"
          aria-label={`Supported: ${Math.round((isnad.supported ?? 0) * 100)}% of ${isnad.claims} claims`}
        >
          {bars.map((bar, index) => (
            <span
              key={bar.grade}
              style={{
                width: `${bar.share * 100}%`,
                background: GRADES[bar.grade].color,
                marginLeft: index ? 2 : 0,
              }}
            />
          ))}
        </span>
        <span>{headline(isnad)}</span>
      </button>
      {open && (
        <ol className="mt-2 space-y-1.5">
          {isnad.ledger.map((claim, index) => {
            const grade = GRADES[claim.grade];
            return (
              <li key={index} className="flex gap-2">
                <span
                  className="shrink-0 inline-flex items-center gap-1 rounded px-1.5 py-0.5 border h-fit"
                  style={{ borderColor: grade.color, color: grade.color }}
                  title={grade.meaning}
                >
                  <span aria-hidden>{grade.icon}</span>
                  {grade.label}
                </span>
                <span className="min-w-0">
                  <span
                    className="block text-gray-700 dark:text-gray-300 break-words"
                    dir={claim.kind === "quote" ? "auto" : undefined}
                  >
                    {claim.text}
                  </span>
                  <span className="block text-gray-500">{claim.support.join("; ")}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
