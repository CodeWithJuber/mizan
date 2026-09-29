/**
 * PatternTutorCard — explains a morphological pattern (wazn) and shows
 * sibling words built on it. When the backend reports available:false the
 * card carries an honest "beta" label instead of a fake verified claim;
 * the sibling list itself is heuristic data, badged as such.
 */

import { useEffect, useState } from "react";
import { useMorphology } from "../../hooks/useMorphology";
import type { PatternResponse } from "../../types/morphology";
import { VerifiedBadge } from "./VerifiedBadge";

interface PatternTutorCardProps {
  wazn: string | null;
  onSelectWord?: (word: string) => void;
}

export function PatternTutorCard({
  wazn,
  onSelectWord,
}: PatternTutorCardProps) {
  const morph = useMorphology();
  const [data, setData] = useState<PatternResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    if (!wazn) {
      setLoading(false);
      return;
    }
    morph
      .getPattern(wazn)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Pattern lookup failed",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [wazn, morph]);

  if (!wazn) {
    return (
      <p className="text-xs text-gray-400">
        No pattern determined for this word — the analyzer could not classify
        it. Nothing guessed.
      </p>
    );
  }

  if (loading) {
    return (
      <div className="py-6 text-center text-sm text-gray-400">
        Loading pattern…
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="px-3 py-2.5 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-700 dark:text-red-300"
        role="alert"
      >
        {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Pattern tutor
        </h4>
        {!data.available ? (
          <span
            className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400"
            title="Pattern data is incomplete — treat everything here as provisional"
          >
            beta
          </span>
        ) : (
          <VerifiedBadge level="heuristic" />
        )}
      </div>

      <div className="p-4 rounded-xl bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700">
        <div
          dir="rtl"
          lang="ar"
          className="text-3xl font-bold text-center text-gray-900 dark:text-gray-100"
        >
          {data.wazn}
        </div>
        {!data.available && (
          <p className="text-xs text-amber-700 dark:text-amber-400 text-center mt-2">
            Beta: this pattern’s data is still being verified. Siblings below
            are heuristic, not verified facts.
          </p>
        )}
      </div>

      {data.siblings.length > 0 ? (
        <div>
          <div className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
            Sibling words on this pattern
          </div>
          <div className="flex flex-wrap gap-1.5">
            {data.siblings.map((s, i) => (
              <button
                key={i}
                onClick={() => s.word && onSelectWord?.(s.word)}
                title={s.root ? `root ${s.root}` : undefined}
                className="min-h-[44px] px-3 py-1.5 rounded-full text-sm bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-200 dark:hover:bg-indigo-500/25 transition-colors cursor-pointer focus-ring"
              >
                <span dir="rtl" lang="ar">
                  {s.word}
                </span>
                <span className="text-[11px] opacity-70" dir="rtl" lang="ar">
                  {" "}
                  · {s.root}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-400">
          No sibling words recorded for this pattern yet.
        </p>
      )}
    </div>
  );
}
