/**
 * Providers Page — LLM Provider Configuration
 * Click a provider card to expand inline model picker. Select + Activate.
 */

import { useState, useEffect, useCallback } from "react";
import type {
  PageProps,
  ProviderStatus,
  ProviderInfo,
  ProviderModel,
  ProviderHealth,
} from "../types";
import { SkeletonCard } from "../components/Skeleton";

const PROVIDER_ICONS: Record<string, string> = {
  anthropic: "A",
  openrouter: "R",
  openai: "O",
  ollama: "L",
};

const PROVIDER_COLORS: Record<string, string> = {
  anthropic:
    "border-amber-300 dark:border-amber-500/30 bg-gradient-to-br from-amber-50 dark:from-amber-500/10 to-amber-50/50 dark:to-amber-900/5",
  openrouter:
    "border-purple-300 dark:border-purple-500/30 bg-gradient-to-br from-purple-50 dark:from-purple-500/10 to-purple-50/50 dark:to-purple-900/5",
  openai:
    "border-emerald-300 dark:border-emerald-500/30 bg-gradient-to-br from-emerald-50 dark:from-emerald-500/10 to-emerald-50/50 dark:to-emerald-900/5",
  ollama:
    "border-blue-300 dark:border-blue-500/30 bg-gradient-to-br from-blue-50 dark:from-blue-500/10 to-blue-50/50 dark:to-blue-900/5",
};

const PROVIDER_ACCENT: Record<string, string> = {
  anthropic: "text-amber-600 dark:text-amber-400",
  openrouter: "text-purple-600 dark:text-purple-400",
  openai: "text-emerald-600 dark:text-emerald-400",
  ollama: "text-blue-600 dark:text-blue-400",
};

const DYNAMIC_PROVIDERS = new Set(["openrouter", "ollama"]);
const MODEL_PAGE_SIZE = 50;

export default function ProvidersPage({ api, addTerminalLine }: PageProps) {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [health, setHealth] = useState<Record<string, ProviderHealth>>({});
  const [models, setModels] = useState<Record<string, ProviderModel[]>>({});
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);

  // Expand-to-select state
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [pendingModel, setPendingModel] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // OpenRouter search/filter/pagination
  const [modelSearch, setModelSearch] = useState("");
  const [modelFreeOnly, setModelFreeOnly] = useState(false);
  const [modelOffset, setModelOffset] = useState(0);
  const [modelTotal, setModelTotal] = useState(0);
  const [browseLoading, setBrowseLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = (await api.get("/providers")) as unknown as ProviderStatus;
      setStatus(data);
    } catch {
      addTerminalLine?.("Failed to fetch provider status", "error");
    } finally {
      setLoading(false);
    }
  }, [api, addTerminalLine]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const checkHealth = async (providerName: string) => {
    try {
      const result = (await api.get(
        `/providers/${providerName}/health`,
      )) as unknown as ProviderHealth;
      setHealth((prev) => ({ ...prev, [providerName]: result }));
    } catch {
      setHealth((prev) => ({
        ...prev,
        [providerName]: {
          provider: providerName,
          healthy: false,
          error: "Request failed",
        },
      }));
    }
  };

  const fetchModels = async (
    providerName: string,
    search = "",
    freeOnly = false,
    offset = 0,
  ) => {
    setBrowseLoading(true);
    try {
      const params = new URLSearchParams({
        limit: String(MODEL_PAGE_SIZE),
        offset: String(offset),
      });
      if (search) params.set("search", search);
      if (freeOnly) params.set("free_only", "true");

      const data = (await api.get(
        `/providers/${providerName}/models?${params}`,
      )) as unknown as {
        models: ProviderModel[];
        total: number;
        offset: number;
      };
      setModels((prev) => ({ ...prev, [providerName]: data.models || [] }));
      setModelTotal(data.total ?? data.models?.length ?? 0);
      setModelOffset(offset);
    } catch {
      addTerminalLine?.(`Failed to fetch models for ${providerName}`, "error");
    } finally {
      setBrowseLoading(false);
    }
  };

  const handleCardClick = (provider: ProviderInfo) => {
    if (!provider.configured) return;

    if (expandedProvider === provider.name) {
      setExpandedProvider(null);
      setPendingModel("");
      return;
    }

    setExpandedProvider(provider.name);
    const isActive = status?.active === provider.name;
    setPendingModel(
      isActive
        ? status?.default_model || provider.default_model
        : provider.default_model,
    );
    setModelSearch("");
    setModelFreeOnly(false);
    setModelOffset(0);

    if (DYNAMIC_PROVIDERS.has(provider.name)) {
      fetchModels(provider.name);
    }
  };

  const switchProvider = async (provider: string, model: string) => {
    if (!provider || !model) return;
    setSwitching(true);
    try {
      await api.post("/providers/switch", { provider, model });
      await fetchStatus();
      setExpandedProvider(null);
      setPendingModel("");
      setSuccessMessage(`Switched to ${provider} / ${model}`);
      setTimeout(() => setSuccessMessage(null), 3000);
      addTerminalLine?.(`Switched to ${provider} / ${model}`, "gold");
    } catch {
      addTerminalLine?.("Failed to switch provider", "error");
    } finally {
      setSwitching(false);
    }
  };

  if (loading) {
    return (
      <div className="p-5" aria-live="polite">
        <div className="card-grid">
          <SkeletonCard count={4} />
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">LLM Providers</h2>
          <p className="page-description">
            Active:{" "}
            <span className="text-mizan-gold font-medium">
              {status?.active}
            </span>
            {" \u00B7 "}
            <span className="text-mizan-gold font-mono text-xs">
              {status?.default_model}
            </span>
          </p>
        </div>
      </div>

      <div className="page-body">
        {/* Success toast */}
        {successMessage && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-sm animate-in">
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-4 h-4 shrink-0"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                clipRule="evenodd"
              />
            </svg>
            {successMessage}
          </div>
        )}

        {/* Provider Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(status?.providers ?? []).map((provider: ProviderInfo) => {
            const isActive = status?.active === provider.name;
            const isExpanded = expandedProvider === provider.name;
            const h = health[provider.name];
            const colorClass =
              PROVIDER_COLORS[provider.name] ||
              "border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900";
            const accentClass =
              PROVIDER_ACCENT[provider.name] ||
              "text-gray-600 dark:text-gray-400";
            const isDynamic = DYNAMIC_PROVIDERS.has(provider.name);
            const providerModels = isDynamic
              ? models[provider.name] || []
              : provider.models;

            return (
              <div
                key={provider.name}
                className={`relative rounded-xl border p-4 transition-all ${colorClass} ${
                  isActive ? "ring-2 ring-mizan-gold/40" : ""
                }`}
              >
                {/* Active badge */}
                {isActive && (
                  <div className="absolute top-2 right-2 px-2 py-0.5 rounded text-xs font-bold bg-mizan-gold/10 text-mizan-gold border border-mizan-gold/20">
                    ACTIVE
                  </div>
                )}

                {/* Card header — clickable */}
                <div
                  className={`flex items-center gap-3 ${provider.configured ? "cursor-pointer" : ""}`}
                  onClick={() => handleCardClick(provider)}
                >
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg font-bold ${accentClass} bg-gray-100 dark:bg-white/5`}
                  >
                    {PROVIDER_ICONS[provider.name] || "?"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {provider.display}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {provider.configured ? (
                        <span className="text-emerald-600 dark:text-emerald-400">
                          Configured
                        </span>
                      ) : (
                        <span className="text-red-500 dark:text-red-400">
                          Not configured
                        </span>
                      )}
                    </div>
                  </div>
                  {provider.configured && (
                    <span className="text-gray-400 dark:text-gray-500 text-xs">
                      {isExpanded ? "\u25B2" : "\u25BC"}
                    </span>
                  )}
                </div>

                {/* Collapsed: model pills + health check */}
                {!isExpanded && (
                  <>
                    {provider.models.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {provider.models.slice(0, 3).map((m) => (
                          <span
                            key={m.id}
                            className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-white/5 text-gray-500 dark:text-gray-400 font-mono"
                          >
                            {m.name || m.id}
                          </span>
                        ))}
                        {provider.models.length > 3 && (
                          <span className="text-xs text-gray-400 dark:text-gray-500 px-1">
                            +{provider.models.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                    <div className="mt-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          checkHealth(provider.name);
                        }}
                        className="btn-secondary btn-sm"
                      >
                        Health Check
                      </button>
                    </div>
                    {/* Health result */}
                    {h && <HealthBadge health={h} />}
                  </>
                )}

                {/* ===== EXPANDED: inline model picker ===== */}
                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-gray-200/60 dark:border-zinc-700/60 space-y-3">
                    {/* Search + filter for dynamic providers */}
                    {provider.name === "openrouter" && (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder="Search models..."
                          value={modelSearch}
                          onChange={(e) => setModelSearch(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              fetchModels(
                                provider.name,
                                modelSearch,
                                modelFreeOnly,
                                0,
                              );
                            }
                          }}
                          className="input flex-1 text-sm py-1.5"
                        />
                        <button
                          onClick={() =>
                            fetchModels(
                              provider.name,
                              modelSearch,
                              modelFreeOnly,
                              0,
                            )
                          }
                          className="btn-secondary btn-sm"
                        >
                          Search
                        </button>
                        <label className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 cursor-pointer whitespace-nowrap">
                          <input
                            type="checkbox"
                            checked={modelFreeOnly}
                            onChange={(e) => {
                              setModelFreeOnly(e.target.checked);
                              fetchModels(
                                provider.name,
                                modelSearch,
                                e.target.checked,
                                0,
                              );
                            }}
                            className="rounded border-gray-300 dark:border-zinc-600 text-mizan-gold focus:ring-mizan-gold/50"
                          />
                          Free
                        </label>
                      </div>
                    )}

                    {/* Model count for dynamic */}
                    {isDynamic && modelTotal > 0 && (
                      <div className="text-xs text-gray-400 dark:text-gray-500">
                        {modelTotal} models available
                      </div>
                    )}

                    {/* Model list */}
                    <div className="max-h-64 overflow-y-auto space-y-1 scrollbar-thin">
                      {browseLoading && isDynamic ? (
                        <div className="text-sm text-gray-400 dark:text-gray-500 py-6 text-center animate-pulse">
                          Loading models...
                        </div>
                      ) : providerModels.length === 0 && isDynamic ? (
                        <div className="text-sm text-gray-400 dark:text-gray-500 py-4 text-center">
                          No models found.{" "}
                          {provider.name === "ollama"
                            ? "Is Ollama running?"
                            : modelSearch
                              ? "Try a different search."
                              : "Check API key."}
                        </div>
                      ) : (
                        providerModels.map((m) => (
                          <ModelRow
                            key={m.id}
                            model={m}
                            selected={pendingModel === m.id}
                            providerName={provider.name}
                            onSelect={() => setPendingModel(m.id)}
                          />
                        ))
                      )}
                    </div>

                    {/* Pagination for OpenRouter */}
                    {provider.name === "openrouter" &&
                      modelTotal > MODEL_PAGE_SIZE && (
                        <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-zinc-700">
                          <span className="text-xs text-gray-400 dark:text-gray-500">
                            {modelOffset + 1}&ndash;
                            {Math.min(
                              modelOffset + MODEL_PAGE_SIZE,
                              modelTotal,
                            )}{" "}
                            of {modelTotal}
                          </span>
                          <div className="flex gap-2">
                            <button
                              onClick={() =>
                                fetchModels(
                                  provider.name,
                                  modelSearch,
                                  modelFreeOnly,
                                  modelOffset - MODEL_PAGE_SIZE,
                                )
                              }
                              disabled={modelOffset === 0}
                              className="btn-secondary btn-sm disabled:opacity-30"
                            >
                              Prev
                            </button>
                            <button
                              onClick={() =>
                                fetchModels(
                                  provider.name,
                                  modelSearch,
                                  modelFreeOnly,
                                  modelOffset + MODEL_PAGE_SIZE,
                                )
                              }
                              disabled={
                                modelOffset + MODEL_PAGE_SIZE >= modelTotal
                              }
                              className="btn-secondary btn-sm disabled:opacity-30"
                            >
                              Next
                            </button>
                          </div>
                        </div>
                      )}

                    {/* Action row */}
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() =>
                          switchProvider(provider.name, pendingModel)
                        }
                        disabled={
                          switching ||
                          !pendingModel ||
                          (isActive && status?.default_model === pendingModel)
                        }
                        className="btn-gold btn-sm disabled:opacity-30"
                      >
                        {switching
                          ? "Switching..."
                          : isActive && status?.default_model === pendingModel
                            ? "Already Active"
                            : "Activate"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          checkHealth(provider.name);
                        }}
                        className="btn-secondary btn-sm"
                      >
                        Health Check
                      </button>
                      <button
                        onClick={() => {
                          setExpandedProvider(null);
                          setPendingModel("");
                        }}
                        className="ml-auto text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                      >
                        Cancel
                      </button>
                    </div>

                    {h && <HealthBadge health={h} />}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Setup Guide */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wider">
            Quick Setup
          </h3>
          <div className="space-y-2 text-sm font-mono">
            <div>
              <span className="text-amber-600 dark:text-amber-400">
                Anthropic:
              </span>{" "}
              <span className="text-gray-600 dark:text-gray-400">
                ANTHROPIC_API_KEY=sk-ant-...
              </span>
            </div>
            <div>
              <span className="text-purple-600 dark:text-purple-400">
                OpenRouter:
              </span>{" "}
              <span className="text-gray-600 dark:text-gray-400">
                OPENROUTER_API_KEY=sk-or-...
              </span>{" "}
              <span className="text-gray-400 dark:text-gray-500">
                (300+ models)
              </span>
            </div>
            <div>
              <span className="text-emerald-600 dark:text-emerald-400">
                OpenAI:
              </span>{" "}
              <span className="text-gray-600 dark:text-gray-400">
                OPENAI_API_KEY=sk-...
              </span>
            </div>
            <div>
              <span className="text-blue-600 dark:text-blue-400">Ollama:</span>{" "}
              <span className="text-gray-600 dark:text-gray-400">
                OLLAMA_URL=http://localhost:11434
              </span>{" "}
              <span className="text-gray-400 dark:text-gray-500">(local)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ModelRow({
  model,
  selected,
  providerName,
  onSelect,
}: {
  model: ProviderModel;
  selected: boolean;
  providerName: string;
  onSelect: () => void;
}) {
  return (
    <label
      className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
        selected
          ? "bg-mizan-gold/10 border border-mizan-gold/20"
          : "bg-gray-50 dark:bg-zinc-800/50 hover:bg-gray-100 dark:hover:bg-zinc-800 border border-transparent"
      }`}
    >
      <input
        type="radio"
        name={`model-${providerName}`}
        checked={selected}
        onChange={onSelect}
        className="text-mizan-gold focus:ring-mizan-gold/50 shrink-0"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-gray-900 dark:text-gray-200 truncate">
            {model.id}
          </span>
          {model.free && (
            <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20">
              FREE
            </span>
          )}
        </div>
        {model.name && model.name !== model.id && (
          <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {model.name}
          </div>
        )}
      </div>
      <div className="text-right text-xs text-gray-400 dark:text-gray-500 shrink-0 ml-2">
        {model.context ? `${(model.context / 1000).toFixed(0)}k` : ""}
        {model.vision && (
          <div className="text-purple-500 dark:text-purple-400/60">vision</div>
        )}
        {model.pricing && !model.free && (
          <div>${parseFloat(model.pricing.prompt || "0").toFixed(4)}/1k</div>
        )}
      </div>
    </label>
  );
}

function HealthBadge({ health }: { health: ProviderHealth }) {
  return (
    <div
      className={`mt-2 px-2 py-1 rounded text-sm ${
        health.healthy
          ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400"
      }`}
    >
      {health.healthy ? "Healthy" : `Unhealthy: ${health.error || "unknown"}`}
      {health.usage !== undefined && (
        <span className="ml-2 text-gray-500 dark:text-gray-400">
          Usage: ${(health.usage || 0).toFixed(4)}
          {health.limit && ` / $${health.limit}`}
        </span>
      )}
      {health.models !== undefined && (
        <span className="ml-2 text-gray-500 dark:text-gray-400">
          {health.models} models available
        </span>
      )}
    </div>
  );
}
