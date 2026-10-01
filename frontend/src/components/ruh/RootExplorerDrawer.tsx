/**
 * RootExplorerDrawer — mobile bottom sheet for root-morphology exploration.
 * Reuses the slide-in drawer pattern (PR #51): fixed overlay + backdrop,
 * drag handle, Escape/backdrop dismiss, max-height 85vh, ≥44px touch targets.
 *
 * Tabs: Overview | Senses | Family | Pattern, plus "Ask AI about this word"
 * (wired via onAskAI — see AskAIWiring.txt for the exact /api/chat payload).
 * Every linguistic claim carries a VerifiedBadge (trust moat).
 */

import { useCallback, useEffect, useState } from "react";
import { useMorphology } from "../../hooks/useMorphology";
import type {
  AnalyzeWordResponse,
  ExplainPromptResponse,
  Occurrence,
  RootEntryResponse,
} from "../../types/morphology";
import { VerifiedBadge } from "./VerifiedBadge";
import { SenseCompare } from "./SenseCompare";
import { WordFamilyGraph } from "./WordFamilyGraph";
import { PatternTutorCard } from "./PatternTutorCard";

type View = "overview" | "senses" | "family" | "pattern";

interface RootExplorerDrawerProps {
  /** Null = closed. */
  word: string | null;
  onClose: () => void;
  /**
   * Called with the word + explain-prompt payload when the user taps
   * "Ask AI about this word". The parent sends POST /api/chat
   * (see AskAIWiring.txt). When omitted, the button is hidden.
   */
  onAskAI?: (word: string, prompt: ExplainPromptResponse) => void;
}

const TABS: Array<{ id: View; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "senses", label: "Senses" },
  { id: "family", label: "Family" },
  { id: "pattern", label: "Pattern" },
];

export function RootExplorerDrawer({
  word,
  onClose,
  onAskAI,
}: RootExplorerDrawerProps) {
  const morph = useMorphology();
  const [view, setView] = useState<View>("overview");
  const [analyze, setAnalyze] = useState<AnalyzeWordResponse | null>(null);
  const [rootEntry, setRootEntry] = useState<RootEntryResponse | null>(null);
  const [occurrences, setOccurrences] = useState<Occurrence[] | null>(null);
  const [occAvailable, setOccAvailable] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [askLoading, setAskLoading] = useState(false);

  // Fetch analysis + root entry whenever the word changes.
  useEffect(() => {
    if (!word) return;
    let cancelled = false;
    setView("overview");
    setLoading(true);
    setError(null);
    setAnalyze(null);
    setRootEntry(null);
    setOccurrences(null);
    setOccAvailable(true);
    (async () => {
      try {
        const a = await morph.analyzeWord(word);
        if (cancelled) return;
        setAnalyze(a);
        if (a.root) {
          try {
            const r = await morph.getRootEntry(a.root);
            if (!cancelled) setRootEntry(r);
          } catch {
            // Root entry is enrichment; the analysis stands alone.
          }
        }
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Analysis failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [word, morph]);

  // Lazy-load verse occurrences when the Family tab opens.
  useEffect(() => {
    if (view !== "family" || !analyze || occurrences !== null) return;
    let cancelled = false;
    morph
      .getOccurrences(analyze.root)
      .then((res) => {
        if (cancelled) return;
        setOccAvailable(res.available);
        setOccurrences(res.available ? res.occurrences : []);
      })
      .catch(() => {
        if (!cancelled) {
          setOccAvailable(false);
          setOccurrences([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [view, analyze, occurrences, morph]);

  // Escape to close + lock body scroll while open.
  useEffect(() => {
    if (!word) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [word, onClose]);

  const handleAskAI = useCallback(async () => {
    if (!word || !onAskAI) return;
    setAskLoading(true);
    try {
      const prompt = await morph.getExplainPrompt(word);
      onAskAI(word, prompt);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not prepare AI context",
      );
    } finally {
      setAskLoading(false);
    }
  }, [word, onAskAI, morph]);

  if (!word) return null;

  return (
    <div
      className="fixed inset-0 z-[100]"
      role="dialog"
      aria-modal="true"
      aria-label={`Explore word ${word}`}
    >
      <div
        className="absolute inset-0 bg-black/50 animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="absolute bottom-0 left-0 right-0 max-h-[85vh] flex flex-col bg-white dark:bg-mizan-dark rounded-t-2xl border-t border-gray-200 dark:border-white/10 shadow-2xl animate-fade-in">
        {/* drag handle + close */}
        <div className="relative pt-2 pb-1 shrink-0">
          <div className="mx-auto w-10 h-1 rounded-full bg-gray-300 dark:bg-zinc-600" />
          <button
            onClick={onClose}
            aria-label="Close explorer"
            className="absolute top-1 right-2 w-11 h-11 flex items-center justify-center rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 cursor-pointer focus-ring"
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-5 h-5"
              aria-hidden="true"
            >
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* tabs */}
        <div
          className="flex gap-1 px-3 pb-2 shrink-0 overflow-x-auto"
          role="tablist"
          aria-label="Explorer views"
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={view === tab.id}
              onClick={() => setView(tab.id)}
              className={`min-h-[44px] px-4 text-sm font-medium rounded-lg whitespace-nowrap transition-colors cursor-pointer focus-ring ${
                view === tab.id
                  ? "bg-mizan-gold/15 text-mizan-gold-text dark:text-mizan-gold"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800"
              }`}
            >
              {tab.id === "senses"
                ? "Senses compare"
                : tab.id === "family"
                  ? "Word family"
                  : tab.id === "pattern"
                    ? "Pattern tutor"
                    : "Overview"}
            </button>
          ))}
        </div>

        {/* content */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 min-h-0">
          {loading && (
            <div className="py-10 text-center text-sm text-gray-400">
              Analyzing “{word}”…
            </div>
          )}
          {error && !loading && (
            <div
              className="px-3 py-2.5 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-700 dark:text-red-300"
              role="alert"
            >
              {error}
            </div>
          )}

          {!loading && !error && analyze && view === "overview" && (
            <OverviewView analyze={analyze} rootEntry={rootEntry} />
          )}
          {!loading && !error && view === "senses" && (
            <SenseCompare word={word} />
          )}
          {!loading && !error && view === "family" && analyze && (
            <>
              {!occAvailable && (
                <p className="text-xs text-amber-700 dark:text-amber-400 mb-2">
                  Verse occurrences aren’t indexed for this root yet — family
                  below is root data only.
                </p>
              )}
              <WordFamilyGraph
                root={analyze.root}
                derivatives={rootEntry?.derivatives ?? []}
                occurrences={occurrences ?? []}
                provenance={rootEntry?.provenance ?? analyze.provenance}
                source={rootEntry?.source ?? analyze.source}
              />
            </>
          )}
          {!loading && !error && view === "pattern" && analyze && (
            <PatternTutorCard wazn={analyze.wazn} />
          )}
        </div>

        {/* Ask AI footer */}
        {onAskAI && !loading && !error && (
          <div className="shrink-0 px-4 pb-4 pt-2 border-t border-gray-100 dark:border-white/5 safe-area-bottom">
            <button
              onClick={handleAskAI}
              disabled={askLoading}
              className="w-full min-h-[44px] px-4 text-sm font-medium rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer focus-ring"
            >
              {askLoading
                ? "Preparing verified context…"
                : "Ask AI about this word"}
            </button>
            <p className="text-[11px] text-gray-400 text-center mt-1.5">
              The AI gets verified morphology facts first — anything it adds is
              labeled AI-generated.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function OverviewView({
  analyze,
  rootEntry,
}: {
  analyze: AnalyzeWordResponse;
  rootEntry: RootEntryResponse | null;
}) {
  return (
    <div className="space-y-4 animate-fade-in">
      {/* word + root */}
      <div className="text-center py-2">
        <div
          dir="rtl"
          lang="ar"
          className="text-4xl font-bold text-gray-900 dark:text-gray-100"
        >
          {analyze.word}
        </div>
        <div className="mt-1 flex items-center justify-center gap-2">
          <span className="text-xs text-gray-400">root</span>
          <span
            dir="rtl"
            lang="ar"
            className="text-2xl font-bold text-mizan-gold-text dark:text-mizan-gold"
          >
            {analyze.root || "—"}
          </span>
          <VerifiedBadge level={analyze.provenance} source={analyze.source} />
        </div>
      </div>

      {/* pattern / wazn */}
      <div className="flex items-center justify-between gap-2 p-3 rounded-xl bg-gray-50 dark:bg-zinc-800/60 border border-gray-200/60 dark:border-zinc-700/50">
        <div>
          <div className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Pattern (wazn)
          </div>
          <div
            dir="rtl"
            lang="ar"
            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            {analyze.pattern}
            {analyze.wazn && analyze.wazn !== analyze.pattern && (
              <span className="text-sm text-gray-400"> · {analyze.wazn}</span>
            )}
          </div>
        </div>
        <VerifiedBadge level={analyze.provenance} source={analyze.source} />
      </div>

      {/* meaning */}
      {rootEntry ? (
        <div className="p-3 rounded-xl bg-gray-50 dark:bg-zinc-800/60 border border-gray-200/60 dark:border-zinc-700/50 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Meaning
            </div>
            <VerifiedBadge
              level={rootEntry.provenance}
              source={rootEntry.source}
            />
          </div>
          <p className="text-sm text-gray-800 dark:text-gray-200">
            {rootEntry.meaning_en || rootEntry.meaning}
          </p>
          {rootEntry.domain && (
            <p className="text-xs text-gray-400">Domain: {rootEntry.domain}</p>
          )}
          {typeof rootEntry.frequency === "number" && (
            <p className="text-xs text-gray-400">
              Quranic frequency: {rootEntry.frequency}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-gray-400">
          Root meaning not in the verified lexicon yet.
        </p>
      )}

      {/* derivatives */}
      {rootEntry && rootEntry.derivatives.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Derivatives
            </div>
            <VerifiedBadge
              level={rootEntry.provenance}
              source={rootEntry.source}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {rootEntry.derivatives.slice(0, 12).map((d, i) => (
              <span
                key={i}
                dir="rtl"
                lang="ar"
                title={d.gloss}
                className="px-2.5 py-1 rounded-full text-sm bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300"
              >
                {d.surface}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* backend note */}
      {analyze.note && (
        <p className="text-xs text-gray-400 leading-relaxed">{analyze.note}</p>
      )}
    </div>
  );
}
