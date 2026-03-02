/**
 * DataComposition — Training data source visualization
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../../types";
import type { DataStats, DataSource } from "../../types/ruh";

interface DataCompositionProps {
  api: ApiClient;
}

const SOURCE_COLORS: Record<string, string> = {
  quran: "#8b5cf6",
  hadith: "#3b82f6",
  arabic_wiki: "#10b981",
  opus: "#f59e0b",
  tashkeela: "#ef4444",
  seed_roots: "#6366f1",
  seed_concepts: "#ec4899",
};

function formatNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function DataComposition({ api }: DataCompositionProps) {
  const [stats, setStats] = useState<DataStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.get("/ruh/data-stats");
        setStats(data as unknown as DataStats);
      } catch {
        // Endpoint may not exist
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [api]);

  if (loading) {
    return <div className="text-sm text-gray-400 animate-pulse py-4 text-center">Loading data stats...</div>;
  }

  if (!stats || stats.sources.length === 0) {
    return (
      <div className="text-center py-6 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
        <p className="text-sm text-gray-400">No training data found</p>
        <p className="text-xs text-gray-400 mt-1">
          Generate seed data: <code className="font-mono bg-gray-100 dark:bg-zinc-800 px-1 py-0.5 rounded">python -m ruh_model.train --generate-data</code>
        </p>
      </div>
    );
  }

  // Group by type
  const seedSources = stats.sources.filter((s) => s.type === "seed");
  const hfSources = stats.sources.filter((s) => s.type === "huggingface");

  // Stacked bar data from sources that have samples
  const activeSources = stats.sources.filter((s) => s.samples > 0);
  const maxSamples = Math.max(...activeSources.map((s) => s.samples), 1);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Training Data
        </h4>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span>{formatNum(stats.total_samples)} samples</span>
          <span>{stats.total_size_mb} MB</span>
        </div>
      </div>

      {/* Bars */}
      {activeSources.length > 0 && (
        <div className="space-y-2">
          {activeSources.map((source) => (
            <SourceBar key={source.name} source={source} maxSamples={maxSamples} />
          ))}
        </div>
      )}

      {/* Seed data section */}
      {seedSources.length > 0 && (
        <div className="space-y-1">
          <h5 className="text-[10px] text-gray-400 uppercase tracking-wider">Seed Data (On Disk)</h5>
          <div className="grid grid-cols-2 gap-2">
            {seedSources.map((s) => (
              <div
                key={s.name}
                className="bg-gray-50 dark:bg-zinc-800/50 rounded px-3 py-2 border border-gray-100 dark:border-zinc-700/50"
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: SOURCE_COLORS[s.name] ?? "#94a3b8" }}
                  />
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{s.name}</span>
                </div>
                <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                  <span>{formatNum(s.samples)} samples</span>
                  <span>{s.size_mb} MB</span>
                  <span className={s.available ? "text-emerald-500" : "text-gray-400"}>
                    {s.available ? "✓" : "✗"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* HuggingFace datasets */}
      {hfSources.length > 0 && (
        <div className="space-y-1">
          <h5 className="text-[10px] text-gray-400 uppercase tracking-wider">HuggingFace Datasets</h5>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {hfSources.map((s) => (
              <div
                key={s.name}
                className={`rounded px-3 py-2 border ${
                  s.available
                    ? "bg-gray-50 dark:bg-zinc-800/50 border-gray-100 dark:border-zinc-700/50"
                    : "bg-gray-50/50 dark:bg-zinc-800/20 border-dashed border-gray-200 dark:border-zinc-700"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: SOURCE_COLORS[s.name] ?? "#94a3b8", opacity: s.available ? 1 : 0.4 }}
                  />
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{s.name}</span>
                </div>
                <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
                  <span>{((s.weight ?? 0) * 100).toFixed(0)}% weight</span>
                  <span className={s.available ? "text-emerald-500" : "text-amber-500"}>
                    {s.available ? "Available" : "Not downloaded"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SourceBar({ source, maxSamples }: { source: DataSource; maxSamples: number }) {
  const pct = (source.samples / maxSamples) * 100;
  const color = SOURCE_COLORS[source.name] ?? "#94a3b8";

  return (
    <div className="flex items-center gap-3">
      <span className="w-24 text-xs text-gray-500 dark:text-gray-400 truncate text-right">
        {source.name}
      </span>
      <div className="flex-1 h-5 bg-gray-100 dark:bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-16 text-xs font-mono text-gray-400 text-right">
        {formatNum(source.samples)}
      </span>
    </div>
  );
}
