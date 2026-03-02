/**
 * QueueDashboard — Task queue status panel with real-time updates
 */

import { useState, useEffect, useCallback } from "react";
import type { ApiClient, QueueTask, QueueStatus } from "../types";

interface QueueDashboardProps {
  api: ApiClient;
  onCancel?: (taskId: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  complete: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
  cancelled: "bg-gray-100 text-gray-500 dark:bg-zinc-700/50 dark:text-gray-400",
};

const PRIORITY_LABELS: Record<string, { label: string; color: string }> = {
  dharurah: { label: "Critical", color: "text-red-500" },
  hajah: { label: "Need", color: "text-amber-500" },
  tahsiniyyah: { label: "Standard", color: "text-blue-500" },
  takmiliyyah: { label: "Low", color: "text-gray-400" },
};

function formatTime(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  const now = Date.now();
  const diffMs = now - date.getTime();
  if (diffMs < 60_000) return "just now";
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function QueueDashboard({ api, onCancel }: QueueDashboardProps) {
  const [status, setStatus] = useState<QueueStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get("/queue/status");
      setStatus(data as unknown as QueueStatus);
    } catch {
      // Queue may not be available yet
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleCancel = async (taskId: string) => {
    try {
      await api.del(`/queue/tasks/${taskId}`);
      onCancel?.(taskId);
      await fetchStatus();
    } catch {
      // Task may already be running/complete
    }
  };

  if (loading) {
    return (
      <div className="text-sm text-gray-400 animate-pulse py-4 text-center">
        Loading queue status...
      </div>
    );
  }

  if (!status) {
    return (
      <div className="text-center py-6 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
        <p className="text-sm text-gray-400">Queue unavailable</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Counts row */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: "Pending", value: status.pending, color: "text-amber-500" },
          { label: "Running", value: status.running, color: "text-blue-500" },
          { label: "Complete", value: status.complete, color: "text-emerald-500" },
          { label: "Failed", value: status.failed, color: "text-red-500" },
        ].map((item) => (
          <div
            key={item.label}
            className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-2.5 text-center border border-gray-100 dark:border-zinc-700/50"
          >
            <span className={`block font-mono text-lg font-semibold ${item.color}`}>
              {item.value}
            </span>
            <span className="block text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* Worker status */}
      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <span
          className={`w-2 h-2 rounded-full ${status.worker.running ? "bg-emerald-500 animate-pulse" : "bg-gray-400"}`}
        />
        <span>
          Worker {status.worker.running ? "active" : "stopped"}
          {status.worker.active_tasks > 0 && ` (${status.worker.active_tasks} processing)`}
        </span>
      </div>

      {/* Task list */}
      {status.tasks.length > 0 ? (
        <div className="space-y-1">
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Recent Tasks ({status.total})
          </h4>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {status.tasks.map((task: QueueTask) => (
              <div
                key={task.task_id}
                className="flex items-center gap-2 bg-gray-50 dark:bg-zinc-800/50 rounded-lg px-3 py-2 border border-gray-100 dark:border-zinc-700/50"
              >
                {/* Status badge */}
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${STATUS_COLORS[task.status] || STATUS_COLORS.pending}`}
                >
                  {task.status}
                </span>

                {/* Priority */}
                <span className={`text-[10px] font-mono ${PRIORITY_LABELS[task.priority]?.color || "text-gray-400"}`}>
                  {PRIORITY_LABELS[task.priority]?.label || task.priority}
                </span>

                {/* Task text */}
                <span className="flex-1 text-xs text-gray-700 dark:text-gray-300 truncate">
                  {task.payload?.task || task.task_id.slice(0, 8)}
                </span>

                {/* Time */}
                <span className="text-[10px] text-gray-400 shrink-0">
                  {formatTime(task.created_at)}
                </span>

                {/* Cancel button for pending tasks */}
                {task.status === "pending" && (
                  <button
                    onClick={() => handleCancel(task.task_id)}
                    className="text-[10px] text-red-400 hover:text-red-600 transition-colors shrink-0"
                    title="Cancel task"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-center py-4 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
          <p className="text-sm text-gray-400">No tasks in queue</p>
          <p className="text-xs text-gray-400 mt-1">Tasks are queued via chat or API</p>
        </div>
      )}
    </div>
  );
}
