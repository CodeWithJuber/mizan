/**
 * TrainingControls — Start/Stop training with stage selection
 */

import { useState } from "react";
import type { ApiClient } from "../../types";
import type { RuhStatus } from "../../types/ruh";

const STAGES = [
  { value: "nutfah", label: "Nutfah (نطفة)", desc: "Stage 1: seq_len=128, lr=3e-4" },
  { value: "alaqah", label: "Alaqah (علقة)", desc: "Stage 2: seq_len=512, lr=1e-4" },
  { value: "mudghah", label: "Mudghah (مضغة)", desc: "Stage 3: seq_len=1024, lr=5e-5" },
  { value: "khalq_akhar", label: "Khalq Akhar (خلق آخر)", desc: "Stage 4: seq_len=2048, lr=1e-5" },
];

interface TrainingControlsProps {
  api: ApiClient;
  running: boolean;
  ruhStatus: RuhStatus | null;
  onStatusChange: () => void;
}

export function TrainingControls({ api, running, ruhStatus, onStatusChange }: TrainingControlsProps) {
  const [stage, setStage] = useState("nutfah");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);

  const disabled = !ruhStatus?.enabled;

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.post("/training/start", { stage });
      if ((result as Record<string, unknown>).running) {
        onStatusChange();
      } else {
        setError("Failed to start training");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start training");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    if (!confirmStop) {
      setConfirmStop(true);
      return;
    }
    setLoading(true);
    setError(null);
    setConfirmStop(false);
    try {
      await api.post("/training/stop");
      onStatusChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop training");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Training Controls
        </h4>
        {running && (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Running
          </span>
        )}
      </div>

      {!running ? (
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
              Stage
            </label>
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              disabled={disabled || loading}
              className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500/30 disabled:opacity-50"
            >
              {STAGES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-gray-400">
              {STAGES.find((s) => s.value === stage)?.desc}
            </p>
          </div>
          <button
            onClick={handleStart}
            disabled={disabled || loading}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {loading ? "Starting..." : "Start Training"}
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <button
            onClick={handleStop}
            disabled={loading}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              confirmStop
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-amber-600 text-white hover:bg-amber-700"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {loading ? "Stopping..." : confirmStop ? "Confirm Stop" : "Stop Training"}
          </button>
          {confirmStop && (
            <button
              onClick={() => setConfirmStop(false)}
              className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            >
              Cancel
            </button>
          )}
        </div>
      )}

      {disabled && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          Set <code className="font-mono bg-amber-100 dark:bg-amber-500/20 px-1 py-0.5 rounded">RUH_ENABLED=true</code> to enable training.
        </p>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
