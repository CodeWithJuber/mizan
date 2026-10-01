/**
 * SenseCompare — side-by-side sense cards for one Arabic word.
 * Two-column on desktop, stacked on mobile (stacked keeps every
 * provenance badge visible — the trust moat beats swipe hiding).
 * Each sense card carries its own VerifiedBadge.
 */

import { useEffect, useState } from "react";
import { useMorphology } from "../../hooks/useMorphology";
import type { Provenance, SenseEntry } from "../../types/morphology";
import { VerifiedBadge } from "./VerifiedBadge";

interface SenseCompareProps {
  word: string;
  /** Optional disambiguating context ("...in the verse about light"). */
  context?: string;
  /** Pre-fetched senses; when omitted the component fetches itself. */
  initialSenses?: SenseEntry[];
}

export function SenseCompare({
  word,
  context,
  initialSenses,
}: SenseCompareProps) {
  const morph = useMorphology();
  const [senses, setSenses] = useState<SenseEntry[] | null>(
    initialSenses ?? null,
  );
  const [provenance, setProvenance] = useState<Provenance>("verified");
  const [source, setSource] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(!initialSenses);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialSenses) {
      setSenses(initialSenses);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    morph
      .getSenses(word, context)
      .then((res) => {
        if (cancelled) return;
        setSenses(res.senses);
        setProvenance(res.provenance);
        setSource(res.source);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Sense lookup failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [word, context, initialSenses, morph]);

  if (loading) {
    return (
      <div className="py-6 text-center text-sm text-gray-400">
        Comparing senses…
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

  if (!senses || senses.length === 0) {
    return (
      <p className="text-sm text-gray-400">
        No senses found for “{word}”. Nothing invented — try another word.
      </p>
    );
  }

  return (
    <div>
      <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
        Senses of “{word}” ({senses.length})
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {senses.map((sense, i) => (
          <article
            key={i}
            className="p-3 rounded-xl bg-gray-50 dark:bg-zinc-800/60 border border-gray-200/60 dark:border-zinc-700/50 space-y-1.5"
          >
            <div className="flex items-start justify-between gap-2">
              <span
                dir="rtl"
                lang="ar"
                className="text-base font-bold text-gray-900 dark:text-gray-100"
              >
                {sense.surface}
              </span>
              <VerifiedBadge level={provenance} source={source} />
            </div>
            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
              {sense.gloss}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-700/50 text-gray-500 dark:text-gray-400">
                {sense.kind === "root" ? "root meaning" : "derivative"}
              </span>
              {sense.pattern && (
                <span dir="rtl" lang="ar" className="text-[11px] text-gray-400">
                  {sense.pattern}
                </span>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
