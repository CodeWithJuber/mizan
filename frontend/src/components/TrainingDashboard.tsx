/**
 * TrainingDashboard — Ruh Model training status card
 * Displays current training progress, loss metrics,
 * and learner interaction statistics.
 */

import type { TrainingMetrics, LearnerStats, RuhStatus } from "../types/ruh";

// ===== Sub-components =====

function StatusBadge({ running }: { running: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${
        running
          ? "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
          : "bg-gray-100 dark:bg-zinc-700/30 text-gray-500 dark:text-gray-400"
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${running ? "bg-emerald-500 animate-pulse-slow" : "bg-gray-400 dark:bg-gray-500"}`}
      />
      {running ? "Training" : "Idle"}
    </span>
  );
}

function MetricItem({
  label,
  value,
  subtext,
}: {
  label: string;
  value: string | number;
  subtext?: string;
}) {
  return (
    <div className="text-center py-2 px-2 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-100 dark:border-zinc-700/50">
      <span className="block font-mono text-sm text-gray-900 dark:text-gray-100">
        {value}
      </span>
      <span className="block text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wider">
        {label}
      </span>
      {subtext && (
        <span className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          {subtext}
        </span>
      )}
    </div>
  );
}

function LossIndicator({ loss }: { loss: number | null }) {
  if (loss === null) {
    return (
      <span className="text-gray-400 dark:text-gray-500 font-mono text-sm">--</span>
    );
  }

  const lossColor =
    loss < 0.5
      ? "text-emerald-600 dark:text-emerald-400"
      : loss < 1.0
        ? "text-amber-600 dark:text-amber-400"
        : "text-red-600 dark:text-red-400";

  return <span className={`font-mono text-sm ${lossColor}`}>{loss.toFixed(4)}</span>;
}

function formatLastExport(lastExport: string | null): string {
  if (!lastExport) return "Never";
  try {
    const date = new Date(lastExport);
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return lastExport;
  }
}

// ===== Main Component =====

interface TrainingDashboardProps {
  metrics: TrainingMetrics | null;
  learnerStats: LearnerStats | null;
  ruhStatus: RuhStatus | null;
}

export function TrainingDashboard({
  metrics,
  learnerStats,
  ruhStatus,
}: TrainingDashboardProps) {
  return (
    <div className="card space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-purple-100 dark:bg-purple-500/15 flex items-center justify-center">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-4 h-4 text-purple-600 dark:text-purple-400"
              aria-hidden="true"
            >
              <path d="M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.57 50.57 0 00-2.658-.813A59.905 59.905 0 0112 3.493a59.902 59.902 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.697 50.697 0 0112 13.489a50.702 50.702 0 017.74-3.342" />
            </svg>
          </div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Ruh Model
          </h3>
        </div>
        <StatusBadge running={metrics?.running ?? false} />
      </div>

      {/* Model status */}
      {ruhStatus && (
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span
            className={`w-2 h-2 rounded-full ${ruhStatus.loaded ? "bg-emerald-500" : "bg-gray-400"}`}
          />
          <span>{ruhStatus.loaded ? "Model loaded" : "Model not loaded"}</span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="font-mono">{ruhStatus.device}</span>
        </div>
      )}

      {/* Training metrics */}
      {metrics?.running ? (
        <div className="space-y-3">
          {/* Stage label */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Stage: <span className="font-medium text-gray-700 dark:text-gray-300">{metrics.stage ?? "Initializing"}</span>
            </span>
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-3 gap-2">
            <MetricItem label="Epoch" value={metrics.epoch} />
            <MetricItem
              label="Loss"
              value={metrics.loss !== null ? metrics.loss.toFixed(4) : "--"}
            />
            <MetricItem
              label="Confidence"
              value={metrics.loss !== null ? `${Math.round(Math.max(0, 1 - metrics.loss) * 100)}%` : "--"}
            />
          </div>

          {/* Status message */}
          {metrics.message && (
            <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-zinc-800/50 rounded px-2 py-1.5 font-mono">
              {metrics.message}
            </p>
          )}
        </div>
      ) : (
        <div className="text-center py-3 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No training in progress
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
            Start training via CLI:{" "}
            <code className="font-mono bg-gray-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded text-xs">
              mizan train --start
            </code>
          </p>
        </div>
      )}

      {/* Learner stats */}
      {learnerStats && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Learner Stats
          </h4>
          <div className="grid grid-cols-3 gap-2">
            <MetricItem
              label="Captured"
              value={learnerStats.total_interactions}
            />
            <MetricItem
              label="Exportable"
              value={learnerStats.exportable_count}
            />
            <MetricItem
              label="Last Export"
              value={formatLastExport(learnerStats.last_export)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
