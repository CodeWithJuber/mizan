/**
 * RuhModelPage — Full dashboard for the Ruh model
 *
 * Sub-tabs:
 *   Dashboard   — live training metrics, loss curve, controls
 *   NLP Explorer — tokenizer pipeline + tasrif playground
 *   Model       — architecture diagram + checkpoint browser
 *   Data        — data composition + training history + learner stats
 */

import { useState, useEffect, useCallback } from "react";
import type { ApiClient } from "../types";
import type {
  RuhStatus,
  TrainingMetrics,
  LearnerStats,
  TrainingRun,
} from "../types/ruh";
import { useToast } from "../components/Toast";
import { useTrainingWebSocket } from "../hooks/useTrainingWebSocket";
import { TrainingControls } from "../components/ruh/TrainingControls";
import { LossCurveChart } from "../components/ruh/LossCurveChart";
import { CheckpointBrowser } from "../components/ruh/CheckpointBrowser";
import { DataComposition } from "../components/ruh/DataComposition";
import { ModelArchitectureView } from "../components/ruh/ModelArchitectureView";
import { TokenizerPipeline } from "../components/ruh/TokenizerPipeline";
import { TasrifVisualizer } from "../components/ruh/TasrifVisualizer";
import { TrainingHistory } from "../components/ruh/TrainingHistory";

// ===== Sub-tab definitions =====

type SubTab = "dashboard" | "nlp" | "model" | "data";

const SUB_TABS: { id: SubTab; label: string; desc: string }[] = [
  { id: "dashboard", label: "Dashboard", desc: "Training & metrics" },
  { id: "nlp", label: "NLP Explorer", desc: "Tokenizer & tasrif" },
  { id: "model", label: "Model", desc: "Architecture & checkpoints" },
  { id: "data", label: "Data & History", desc: "Datasets & past runs" },
];

// ===== Generate playground types =====

interface GenerateResult {
  text: string;
  model: string;
  usage: Record<string, unknown>;
}

// ===== Page component =====

export default function RuhModelPage({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [tab, setTab] = useState<SubTab>("dashboard");
  const [ruhStatus, setRuhStatus] = useState<RuhStatus | null>(null);
  const [learnerStats, setLearnerStats] = useState<LearnerStats | null>(null);
  const [trainingHistory, setTrainingHistory] = useState<TrainingRun[]>([]);
  const [loading, setLoading] = useState(true);

  // Real-time training metrics via WebSocket
  const { metrics: wsMetrics, connected: wsConnected } = useTrainingWebSocket();

  // Polled training status (fallback when WS is stale)
  const [polledMetrics, setPolledMetrics] = useState<TrainingMetrics | null>(
    null,
  );

  // Merged metrics: prefer WebSocket when it's delivering real data,
  // otherwise fall back to polled status. (wsMetrics is never null —
  // INITIAL_METRICS.message is "Connecting..." until real data arrives.)
  const metrics: TrainingMetrics | null =
    wsConnected && wsMetrics.message !== "Connecting..."
      ? wsMetrics
      : (polledMetrics ?? wsMetrics);

  // Generate playground state
  const [generatePrompt, setGeneratePrompt] = useState("");
  const [generateResult, setGenerateResult] = useState<GenerateResult | null>(
    null,
  );
  const [generateLoading, setGenerateLoading] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [maxTokens, setMaxTokens] = useState(256);
  const [temperature, setTemperature] = useState(1.0);
  const [genValidationError, setGenValidationError] = useState<string | null>(
    null,
  );

  // Refresh-all spinner state
  const [refreshing, setRefreshing] = useState(false);

  // ===== Fetchers =====

  const fetchStatus = useCallback(async (): Promise<boolean> => {
    try {
      const data = await api.get("/ruh/status");
      setRuhStatus(data as unknown as RuhStatus);
      return true;
    } catch {
      // Endpoint may not exist yet
      return false;
    }
  }, [api]);

  const fetchTrainingStatus = useCallback(async (): Promise<boolean> => {
    try {
      const data = await api.get("/training/status");
      setPolledMetrics(data as unknown as TrainingMetrics);
      return true;
    } catch {
      // No training endpoint
      return false;
    }
  }, [api]);

  const fetchLearnerStats = useCallback(async (): Promise<boolean> => {
    try {
      const data = (await api.get("/learner/stats")) as Record<string, unknown>;
      if (data && typeof data.total_interactions === "number") {
        setLearnerStats(data as unknown as LearnerStats);
      }
      return true;
    } catch {
      // Optional — endpoint may 500 when learner isn't configured
      return false;
    }
  }, [api]);

  const fetchHistory = useCallback(async (): Promise<boolean> => {
    try {
      const data = await api.get("/training/history");
      setTrainingHistory((data as { runs: TrainingRun[] }).runs ?? []);
      return true;
    } catch {
      // Optional
      return false;
    }
  }, [api]);

  // Initial load + periodic refresh
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([
        fetchStatus(),
        fetchTrainingStatus(),
        fetchLearnerStats(),
        fetchHistory(),
      ]);
      setLoading(false);
    };
    load();
    const interval = setInterval(() => {
      fetchStatus();
      fetchTrainingStatus();
    }, 10_000);
    return () => clearInterval(interval);
  }, [fetchStatus, fetchTrainingStatus, fetchLearnerStats, fetchHistory]);

  const refreshAll = async () => {
    setRefreshing(true);
    try {
      const results = await Promise.all([
        fetchStatus(),
        fetchTrainingStatus(),
        fetchLearnerStats(),
        fetchHistory(),
      ]);
      const failed = results.filter((r) => !r).length;
      if (failed > 0) {
        addToast({
          type: "warning",
          title: "Partial refresh",
          description: `${failed} of ${results.length} sections could not be loaded. The model may not be set up yet.`,
        });
      }
    } finally {
      setRefreshing(false);
    }
  };

  // ===== Generate handler =====

  const handleGenerate = async () => {
    if (!generatePrompt.trim()) return;
    if (!Number.isFinite(maxTokens) || maxTokens < 1 || maxTokens > 4000) {
      setGenValidationError("Max tokens must be between 1 and 4000.");
      return;
    }
    if (!Number.isFinite(temperature) || temperature < 0 || temperature > 2) {
      setGenValidationError("Temperature must be between 0 and 2.");
      return;
    }
    setGenValidationError(null);
    setGenerateLoading(true);
    setGenerateError(null);
    setGenerateResult(null);
    try {
      const data = await api.post("/ruh/generate", {
        prompt: generatePrompt,
        max_tokens: maxTokens,
        temperature,
      });
      setGenerateResult(data as unknown as GenerateResult);
    } catch (err) {
      setGenerateError(
        err instanceof Error ? err.message : "Generation failed",
      );
    } finally {
      setGenerateLoading(false);
    }
  };

  // ===== Loading state =====

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex items-center gap-2 text-gray-400">
          <svg
            className="w-5 h-5 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M7.76 7.76L4.93 4.93" />
          </svg>
          Loading Ruh Model...
        </div>
      </div>
    );
  }

  // ===== Render =====

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <div>
          <h2 className="page-title">Ruh Model</h2>
          <p className="page-description">
            Train, explore &amp; monitor the Arabic-native AI model
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* WS indicator */}
          <span className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            <span
              className={`w-2 h-2 rounded-full ${wsConnected ? "bg-emerald-500" : "bg-gray-400"}`}
              title={
                wsConnected ? "WebSocket connected" : "WebSocket disconnected"
              }
            />
            {wsConnected ? "Live" : "Offline"}
          </span>
          <button
            onClick={refreshAll}
            disabled={refreshing}
            className="text-xs px-3 py-1.5 min-h-[36px] rounded-lg bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-zinc-700 transition-colors disabled:opacity-60 flex items-center gap-1.5"
          >
            {refreshing && (
              <svg
                className="w-3.5 h-3.5 animate-spin"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M7.76 7.76L4.93 4.93" />
              </svg>
            )}
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Framing banner for non-technical users */}
      <div className="px-4 sm:px-5 pt-3">
        <div className="rounded-lg bg-purple-50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 px-4 py-2.5">
          <p className="text-xs text-purple-800 dark:text-purple-300">
            This is the workshop where Mizan&apos;s Arabic brain is built. You
            don&apos;t need it for daily use.{" "}
            <span className="font-medium">
              {SUB_TABS.find((t) => t.id === tab)?.desc}
            </span>
          </p>
        </div>
      </div>

      {/* Sub-tab bar */}
      <div className="flex gap-1 px-4 sm:px-5 pt-2 pb-0 border-b border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-x-auto -webkit-overflow-scrolling-touch">
        {SUB_TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-xs font-medium rounded-t-lg transition-colors relative whitespace-nowrap shrink-0 min-h-[44px] ${
              tab === t.id
                ? "text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-500/10"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-zinc-800/50"
            }`}
          >
            {t.label}
            {tab === t.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500 rounded-t" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* =========== DASHBOARD TAB =========== */}
        {tab === "dashboard" && (
          <>
            {/* Model status bar */}
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  Model Status
                </h3>
                <span
                  className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full ${
                    ruhStatus?.enabled
                      ? "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                      : "bg-gray-100 dark:bg-zinc-700/30 text-gray-500 dark:text-gray-400"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${ruhStatus?.enabled ? "bg-emerald-500" : "bg-gray-400"}`}
                  />
                  {ruhStatus?.enabled ? "Enabled" : "Disabled"}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  {
                    label: "Status",
                    value: ruhStatus?.enabled ? "Active" : "Inactive",
                  },
                  { label: "Loaded", value: ruhStatus?.loaded ? "Yes" : "No" },
                  { label: "Device", value: ruhStatus?.device || "cpu" },
                  {
                    label: "Checkpoint",
                    value: ruhStatus?.model_path
                      ? ruhStatus.model_path.split("/").pop()
                      : "—",
                  },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 text-center border border-gray-100 dark:border-zinc-700/50"
                  >
                    <div
                      className="text-sm font-mono text-gray-900 dark:text-gray-100 truncate"
                      title={String(item.value)}
                    >
                      {item.value}
                    </div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>

              {!ruhStatus?.enabled && (
                <div className="mt-3 p-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg">
                  <p className="text-xs text-amber-700 dark:text-amber-400">
                    The Ruh Model is not enabled. Ask the person who set up
                    Mizan to enable it on the server.
                  </p>
                </div>
              )}
            </div>

            {/* Live training metrics */}
            {metrics && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  {
                    label: "Loss",
                    value: metrics.loss != null ? metrics.loss.toFixed(4) : "—",
                    color: "text-purple-600 dark:text-purple-400",
                  },
                  {
                    label: "Epoch",
                    value:
                      metrics.epoch != null
                        ? `${metrics.epoch}/${metrics.total_epochs ?? "—"}`
                        : "—",
                    color: "text-blue-600 dark:text-blue-400",
                  },
                  {
                    label: "Progress",
                    value: `${metrics.progress_pct.toFixed(1)}%`,
                    color: "text-emerald-600 dark:text-emerald-400",
                  },
                  {
                    label: "Learning Rate",
                    value:
                      metrics.lr != null ? metrics.lr.toExponential(2) : "—",
                    color: "text-amber-600 dark:text-amber-400",
                  },
                ].map((item) => (
                  <div key={item.label} className="card text-center">
                    <div
                      className={`text-lg font-mono font-semibold ${item.color}`}
                    >
                      {item.value}
                    </div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Progress bar */}
            {metrics?.running && (
              <div className="card">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                    Training:{" "}
                    <span className="text-purple-600 dark:text-purple-400">
                      {metrics.stage}
                    </span>
                  </span>
                  <span className="text-xs text-gray-400">
                    {metrics.message}
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-zinc-700 rounded-full h-2">
                  <div
                    className="bg-purple-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(metrics.progress_pct, 100)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between mt-1 text-[10px] text-gray-400">
                  <span>
                    Step {metrics.step}/{metrics.total_steps}
                  </span>
                  <span>
                    {metrics.elapsed > 0
                      ? `${Math.round(metrics.elapsed)}s elapsed`
                      : ""}
                  </span>
                </div>
              </div>
            )}

            {/* Training controls + loss curve side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <TrainingControls
                api={api}
                running={metrics?.running ?? false}
                ruhStatus={ruhStatus}
                onStatusChange={refreshAll}
              />
              <LossCurveChart metrics={metrics} history={trainingHistory} />
            </div>

            {/* Generation playground */}
            <div className="card space-y-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Generation Playground
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Generate text using the local Ruh Model.
                {!ruhStatus?.enabled && " (Requires RUH_ENABLED=true)"}
              </p>
              <textarea
                value={generatePrompt}
                onChange={(e) => setGeneratePrompt(e.target.value)}
                placeholder="Enter a prompt..."
                rows={3}
                className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500/30 focus:border-purple-400 resize-none"
              />
              <div className="flex flex-wrap items-end gap-3 sm:gap-4">
                <label className="flex flex-col gap-1 text-xs text-gray-500 dark:text-gray-400">
                  <span>
                    Max tokens{" "}
                    <span className="opacity-70">
                      — how long the answer can be (1–4000)
                    </span>
                  </span>
                  <input
                    type="number"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(Number(e.target.value))}
                    min={1}
                    max={4000}
                    className="w-20 px-2 py-1.5 min-h-[44px] text-xs rounded border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-gray-500 dark:text-gray-400">
                  <span>
                    Temperature{" "}
                    <span className="opacity-70">
                      — lower = careful, higher = creative (0–2)
                    </span>
                  </span>
                  <input
                    type="number"
                    value={temperature}
                    onChange={(e) => setTemperature(Number(e.target.value))}
                    min={0}
                    max={2}
                    step={0.1}
                    className="w-20 px-2 py-1.5 min-h-[44px] text-xs rounded border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100"
                  />
                </label>
                <button
                  onClick={handleGenerate}
                  disabled={
                    generateLoading ||
                    !generatePrompt.trim() ||
                    !ruhStatus?.enabled
                  }
                  className="w-full sm:w-auto sm:ml-auto px-4 py-2 min-h-[44px] text-sm font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {generateLoading ? "Generating..." : "Generate"}
                </button>
              </div>
              {genValidationError && (
                <p className="text-xs text-red-500">{genValidationError}</p>
              )}
              {generateError && (
                <p className="text-xs text-red-500">{generateError}</p>
              )}
              {generateResult && (
                <div className="space-y-2">
                  <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 border border-gray-100 dark:border-zinc-700/50">
                    <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
                      {generateResult.text}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-gray-400">
                    <span>Model: {generateResult.model}</span>
                    {generateResult.usage && (
                      <span>
                        Tokens: {JSON.stringify(generateResult.usage)}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* =========== NLP EXPLORER TAB =========== */}
        {tab === "nlp" && (
          <>
            <TokenizerPipeline api={api} />
            <TasrifVisualizer api={api} />
          </>
        )}

        {/* =========== MODEL TAB =========== */}
        {tab === "model" && (
          <>
            <ModelArchitectureView api={api} />
            <CheckpointBrowser api={api} />
          </>
        )}

        {/* =========== DATA & HISTORY TAB =========== */}
        {tab === "data" && (
          <>
            <DataComposition api={api} />
            <TrainingHistory api={api} />

            {/* Learner stats */}
            {learnerStats && (
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  Learner Pipeline
                </h3>
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 text-center border border-gray-100 dark:border-zinc-700/50">
                    <div className="text-lg font-mono font-semibold text-blue-600 dark:text-blue-400">
                      {(learnerStats.total_interactions ?? 0).toLocaleString()}
                    </div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
                      Total Interactions
                    </div>
                  </div>
                  <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 text-center border border-gray-100 dark:border-zinc-700/50">
                    <div className="text-lg font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                      {(learnerStats.exportable_count ?? 0).toLocaleString()}
                    </div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
                      Exportable Samples
                    </div>
                  </div>
                  <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 text-center border border-gray-100 dark:border-zinc-700/50">
                    <div className="text-sm font-mono text-gray-600 dark:text-gray-300 truncate">
                      {learnerStats.last_export ?? "Never"}
                    </div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
                      Last Export
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
