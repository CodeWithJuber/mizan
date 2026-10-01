/**
 * RootBridgeCard — English concept → Arabic root family card.
 * A concept with no verified bridge renders a friendly empty state;
 * we never invent a root.
 */

import { useState } from "react";
import { useMorphology } from "../../hooks/useMorphology";
import type { BridgeResponse } from "../../types/morphology";
import { VerifiedBadge } from "./VerifiedBadge";

interface RootBridgeCardProps {
  onExploreRoot?: (root: string) => void;
}

export function RootBridgeCard({ onExploreRoot }: RootBridgeCardProps) {
  const morph = useMorphology();
  const [concept, setConcept] = useState("");
  const [result, setResult] = useState<BridgeResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLookup = async () => {
    const q = concept.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setNotFound(false);
    try {
      const bridge = await morph.getRootBridge(q);
      if (bridge === null) {
        setNotFound(true);
      } else {
        setResult(bridge);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bridge lookup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
          Concept → root bridge
        </h4>
        <p className="text-xs text-gray-400">
          Type an English concept (“mercy”, “knowledge”) to find its Arabic root
          family — only verified bridges are shown.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleLookup()}
          placeholder="e.g. mercy"
          aria-label="English concept"
          className="flex-1 min-h-[44px] px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500/30 focus:border-purple-400"
        />
        <button
          onClick={handleLookup}
          disabled={loading || !concept.trim()}
          className="min-h-[44px] px-4 text-sm font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap cursor-pointer focus-ring"
        >
          {loading ? "Bridging…" : "Bridge"}
        </button>
      </div>

      {error && (
        <div
          className="px-3 py-2.5 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-700 dark:text-red-300"
          role="alert"
        >
          {error}
        </div>
      )}

      {notFound && (
        <div className="px-3 py-3 rounded-xl bg-gray-50 dark:bg-zinc-800/60 border border-dashed border-gray-300 dark:border-zinc-600 text-sm text-gray-500 dark:text-gray-400">
          No verified bridge for “{concept.trim()}” yet. We don’t invent links —
          this concept hasn’t been mapped to an Arabic root in the verified
          dataset.
        </div>
      )}

      {result && (
        <article className="p-4 rounded-xl bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 space-y-3 animate-fade-in">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div
                dir="rtl"
                lang="ar"
                className="text-3xl font-bold text-gray-900 dark:text-gray-100"
              >
                {result.arabic_root}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                root of “{result.concept}”
              </div>
            </div>
            <VerifiedBadge level={result.provenance} source={result.source} />
          </div>

          <div className="space-y-1">
            <p className="text-sm text-gray-800 dark:text-gray-200">
              {result.root_entry.meaning}
            </p>
            {result.root_entry.domain && (
              <p className="text-xs text-gray-400">
                Domain: {result.root_entry.domain}
              </p>
            )}
            {typeof result.root_entry.frequency === "number" && (
              <p className="text-xs text-gray-400">
                Quranic frequency: {result.root_entry.frequency}
              </p>
            )}
          </div>

          {onExploreRoot && (
            <button
              onClick={() => onExploreRoot(result.arabic_root)}
              className="w-full min-h-[44px] px-4 text-sm font-medium rounded-lg bg-mizan-gold/10 text-mizan-gold-text dark:text-mizan-gold border border-mizan-gold/25 hover:bg-mizan-gold/20 transition-colors cursor-pointer focus-ring"
            >
              Explore this root
            </button>
          )}
        </article>
      )}
    </div>
  );
}
