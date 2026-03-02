/**
 * CheckpointBrowser — Browse and inspect saved model checkpoints
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../../types";
import type { Checkpoint } from "../../types/ruh";

interface CheckpointBrowserProps {
  api: ApiClient;
}

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function CheckpointBrowser({ api }: CheckpointBrowserProps) {
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    const fetchCheckpoints = async () => {
      try {
        const data = await api.get("/ruh/checkpoints");
        setCheckpoints((data as { checkpoints: Checkpoint[] }).checkpoints ?? []);
      } catch {
        // Endpoint may not exist yet
      } finally {
        setLoading(false);
      }
    };
    fetchCheckpoints();
  }, [api]);

  if (loading) {
    return (
      <div className="text-sm text-gray-400 animate-pulse py-4 text-center">
        Loading checkpoints...
      </div>
    );
  }

  if (checkpoints.length === 0) {
    return (
      <div className="text-center py-6 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
        <p className="text-sm text-gray-400">No checkpoints saved yet</p>
        <p className="text-xs text-gray-400 mt-1">Checkpoints are created after each training epoch</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
        Checkpoints ({checkpoints.length})
      </h4>
      <div className="space-y-1">
        {checkpoints.map((cp) => (
          <div
            key={cp.name}
            className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg border border-gray-100 dark:border-zinc-700/50 overflow-hidden"
          >
            <button
              onClick={() => setExpanded(expanded === cp.name ? null : cp.name)}
              className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-zinc-700/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="w-8 h-8 rounded-full bg-purple-100 dark:bg-purple-500/15 flex items-center justify-center text-xs font-mono text-purple-600 dark:text-purple-400">
                  {cp.name.match(/\d+/)?.[0] ?? "?"}
                </span>
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {cp.name}
                  </span>
                  <span className="ml-2 text-xs text-gray-400">
                    {cp.size_mb} MB
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">{formatDate(cp.created_at)}</span>
                <svg
                  className={`w-4 h-4 text-gray-400 transition-transform ${expanded === cp.name ? "rotate-180" : ""}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>
            {expanded === cp.name && (
              <div className="px-3 pb-3 border-t border-gray-100 dark:border-zinc-700/50">
                <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                  {cp.max_seq_len && (
                    <div className="bg-white dark:bg-zinc-900 rounded px-2 py-1.5">
                      <span className="text-gray-400">Max Seq Len: </span>
                      <span className="font-mono text-gray-700 dark:text-gray-300">{cp.max_seq_len}</span>
                    </div>
                  )}
                  <div className="bg-white dark:bg-zinc-900 rounded px-2 py-1.5">
                    <span className="text-gray-400">Size: </span>
                    <span className="font-mono text-gray-700 dark:text-gray-300">{cp.size_mb} MB</span>
                  </div>
                </div>
                {Object.keys(cp.config).length > 0 && (
                  <pre className="mt-2 text-[10px] font-mono bg-white dark:bg-zinc-900 rounded p-2 overflow-x-auto text-gray-500 dark:text-gray-400 max-h-32 overflow-y-auto">
                    {JSON.stringify(cp.config, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
