/**
 * TrainingHistory — Past training runs with loss curves
 */

import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { ApiClient } from "../../types";
import type { TrainingRun } from "../../types/ruh";

interface TrainingHistoryProps {
  api: ApiClient;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/15",
  stopped: "text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/15",
  failed: "text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-500/15",
};

const STAGE_COLORS: Record<string, string> = {
  nutfah: "#8b5cf6",
  alaqah: "#3b82f6",
  mudghah: "#10b981",
  khalq_akhar: "#f59e0b",
};

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(start: number, end: number): string {
  const secs = Math.round(end - start);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  return `${(secs / 3600).toFixed(1)}h`;
}

export function TrainingHistory({ api }: TrainingHistoryProps) {
  const [runs, setRuns] = useState<TrainingRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const data = await api.get("/training/history");
        setRuns((data as { runs: TrainingRun[] }).runs ?? []);
      } catch {
        // Endpoint may not exist
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, [api]);

  if (loading) {
    return <div className="text-sm text-gray-400 animate-pulse py-4 text-center">Loading history...</div>;
  }

  if (runs.length === 0) {
    return (
      <div className="text-center py-6 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
        <p className="text-sm text-gray-400">No training history yet</p>
        <p className="text-xs text-gray-400 mt-1">History is recorded after each training run</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
        Training History ({runs.length} runs)
      </h4>

      <div className="space-y-2">
        {runs.slice().reverse().map((run, idx) => {
          const runIdx = runs.length - 1 - idx;
          const isExpanded = expanded === runIdx;

          return (
            <div
              key={runIdx}
              className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg border border-gray-100 dark:border-zinc-700/50 overflow-hidden"
            >
              <button
                onClick={() => setExpanded(isExpanded ? null : runIdx)}
                className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-zinc-700/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: STAGE_COLORS[run.stage] ?? "#94a3b8" }}
                  />
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {run.stage}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[run.status] ?? ""}`}>
                    {run.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span>{run.epochs_completed}/{run.total_epochs} epochs</span>
                  {run.final_loss != null && (
                    <span className="font-mono">loss: {run.final_loss.toFixed(4)}</span>
                  )}
                  <span>{formatDate(run.started_at)}</span>
                  <span>{formatDuration(run.started_at, run.completed_at)}</span>
                  <svg
                    className={`w-4 h-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {isExpanded && run.losses.length > 0 && (
                <div className="px-3 pb-3 border-t border-gray-100 dark:border-zinc-700/50">
                  <div className="h-40 mt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={run.losses.map((loss, epoch) => ({ epoch: epoch + 1, loss }))}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                        <XAxis dataKey="epoch" tick={{ fontSize: 10, fill: "#9ca3af" }} />
                        <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#1f2937",
                            border: "1px solid #374151",
                            borderRadius: "6px",
                            fontSize: 11,
                            color: "#e5e7eb",
                          }}
                        />
                        <Line
                          type="monotone"
                          dataKey="loss"
                          stroke={STAGE_COLORS[run.stage] ?? "#8b5cf6"}
                          strokeWidth={2}
                          dot={{ r: 2 }}
                          animationDuration={300}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
                    <div className="bg-white dark:bg-zinc-900 rounded px-2 py-1.5 text-center">
                      <span className="block font-mono text-gray-700 dark:text-gray-300">
                        {run.dataset_size.toLocaleString()}
                      </span>
                      <span className="text-[10px] text-gray-400">Samples</span>
                    </div>
                    <div className="bg-white dark:bg-zinc-900 rounded px-2 py-1.5 text-center">
                      <span className="block font-mono text-gray-700 dark:text-gray-300">
                        {run.model_params.toLocaleString()}
                      </span>
                      <span className="text-[10px] text-gray-400">Parameters</span>
                    </div>
                    <div className="bg-white dark:bg-zinc-900 rounded px-2 py-1.5 text-center">
                      <span className="block font-mono text-gray-700 dark:text-gray-300">
                        {run.losses.length > 1
                          ? `${((1 - run.losses[run.losses.length - 1] / run.losses[0]) * 100).toFixed(1)}%`
                          : "—"}
                      </span>
                      <span className="text-[10px] text-gray-400">Improvement</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
