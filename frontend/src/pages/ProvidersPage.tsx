/**
 * Providers Page — LLM Provider Configuration
 * Model selection, health monitoring, and provider switching.
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps, ProviderStatus, ProviderInfo, ProviderModel, ProviderHealth } from "../types";

export default function ProvidersPage({ api, addTerminalLine }: PageProps) {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [health, setHealth] = useState<Record<string, ProviderHealth>>({});
  const [models, setModels] = useState<Record<string, ProviderModel[]>>({});
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [browseProvider, setBrowseProvider] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get("/providers") as unknown as ProviderStatus;
      setStatus(data);
      setSelectedProvider(data.active);
      setSelectedModel(data.default_model);
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
      const result = await api.get(`/providers/${providerName}/health`) as unknown as ProviderHealth;
      setHealth((prev) => ({ ...prev, [providerName]: result }));
    } catch {
      setHealth((prev) => ({
        ...prev,
        [providerName]: { provider: providerName, healthy: false, error: "Request failed" },
      }));
    }
  };

  const browseModels = async (providerName: string) => {
    setBrowseProvider(providerName);
    try {
      const data = await api.get(`/providers/${providerName}/models`) as unknown as { models: ProviderModel[] };
      setModels((prev) => ({ ...prev, [providerName]: data.models || [] }));
    } catch {
      addTerminalLine?.(`Failed to fetch models for ${providerName}`, "error");
    }
  };

  const switchProvider = async () => {
    if (!selectedProvider || !selectedModel) return;
    setSwitching(true);
    try {
      await api.post("/providers/switch", {
        provider: selectedProvider,
        model: selectedModel,
      });
      addTerminalLine?.(`Switched to ${selectedProvider} / ${selectedModel}`, "gold");
      await fetchStatus();
    } catch {
      addTerminalLine?.("Failed to switch provider", "error");
    } finally {
      setSwitching(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400 dark:text-gray-500 animate-pulse">Loading providers...</div>
      </div>
    );
  }

  const providerIcons: Record<string, string> = {
    anthropic: "A",
    openrouter: "R",
    openai: "O",
    ollama: "L",
  };

  const providerColors: Record<string, string> = {
    anthropic: "border-amber-300 dark:border-amber-500/30 bg-gradient-to-br from-amber-50 dark:from-amber-500/10 to-amber-50/50 dark:to-amber-900/5",
    openrouter: "border-purple-300 dark:border-purple-500/30 bg-gradient-to-br from-purple-50 dark:from-purple-500/10 to-purple-50/50 dark:to-purple-900/5",
    openai: "border-emerald-300 dark:border-emerald-500/30 bg-gradient-to-br from-emerald-50 dark:from-emerald-500/10 to-emerald-50/50 dark:to-emerald-900/5",
    ollama: "border-blue-300 dark:border-blue-500/30 bg-gradient-to-br from-blue-50 dark:from-blue-500/10 to-blue-50/50 dark:to-blue-900/5",
  };

  const providerAccent: Record<string, string> = {
    anthropic: "text-amber-600 dark:text-amber-400",
    openrouter: "text-purple-600 dark:text-purple-400",
    openai: "text-emerald-600 dark:text-emerald-400",
    ollama: "text-blue-600 dark:text-blue-400",
  };

  return (
    <div className="page-wrapper">
      {/* Header */}
      <div className="page-header">
        <div>
          <h2 className="page-title">LLM Providers</h2>
          <p className="page-description">
            Active: <span className="text-mizan-gold font-medium">{status?.active}</span>
            {" \u00B7 "}Model: <span className="text-mizan-gold font-medium">{status?.default_model}</span>
          </p>
        </div>
      </div>

      <div className="page-body">
        {/* Provider Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {status?.providers.map((provider: ProviderInfo) => {
            const isActive = status.active === provider.name;
            const h = health[provider.name];
            const colorClass = providerColors[provider.name] || "border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900";
            const accentClass = providerAccent[provider.name] || "text-gray-600 dark:text-gray-400";

            return (
              <div
                key={provider.name}
                className={`relative rounded-xl border p-4 transition-all ${colorClass} ${
                  isActive ? "ring-2 ring-mizan-gold/40" : ""
                }`}
              >
                {/* Active badge */}
                {isActive && (
                  <div className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold bg-mizan-gold/10 text-mizan-gold border border-mizan-gold/20">
                    ACTIVE
                  </div>
                )}

                {/* Provider header */}
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg font-bold ${accentClass} bg-gray-100 dark:bg-white/5`}>
                    {providerIcons[provider.name] || "?"}
                  </div>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-gray-100">{provider.display}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {provider.configured ? (
                        <span className="text-emerald-600 dark:text-emerald-400">Configured</span>
                      ) : (
                        <span className="text-red-500 dark:text-red-400">Not configured</span>
                      )}
                      {provider.models.length > 0 && ` \u00B7 ${provider.models.length} models`}
                    </div>
                  </div>
                </div>

                {/* Model list preview */}
                {provider.models.length > 0 && (
                  <div className="mb-3 space-y-1">
                    {provider.models.slice(0, 3).map((m) => (
                      <div
                        key={m.id}
                        className={`text-xs px-2 py-1 rounded cursor-pointer transition-colors ${
                          selectedProvider === provider.name && selectedModel === m.id
                            ? "bg-mizan-gold/10 text-mizan-gold border border-mizan-gold/20"
                            : "bg-gray-100 dark:bg-white/5 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-white/10"
                        }`}
                        onClick={() => {
                          setSelectedProvider(provider.name);
                          setSelectedModel(m.id);
                        }}
                      >
                        <span className="font-mono">{m.id}</span>
                        {m.context ? (
                          <span className="ml-2 text-gray-400 dark:text-gray-500">{(m.context / 1000).toFixed(0)}k ctx</span>
                        ) : null}
                        {m.vision && <span className="ml-1 text-purple-500 dark:text-purple-400/60">vision</span>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => checkHealth(provider.name)}
                    className="btn-secondary btn-sm"
                  >
                    Health Check
                  </button>
                  <button
                    onClick={() => browseModels(provider.name)}
                    className="btn-secondary btn-sm"
                  >
                    Browse Models
                  </button>
                  {!isActive && provider.configured && (
                    <button
                      onClick={() => {
                        setSelectedProvider(provider.name);
                        setSelectedModel(provider.default_model);
                      }}
                      className={`btn-secondary btn-sm ${accentClass}`}
                    >
                      Select
                    </button>
                  )}
                </div>

                {/* Health result */}
                {h && (
                  <div className={`mt-2 px-2 py-1 rounded text-xs ${h.healthy
                    ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400"
                  }`}>
                    {h.healthy ? "Healthy" : `Unhealthy: ${h.error || "unknown"}`}
                    {h.usage !== undefined && (
                      <span className="ml-2 text-gray-500 dark:text-gray-400">
                        Usage: ${(h.usage || 0).toFixed(4)}
                        {h.limit && ` / $${h.limit}`}
                      </span>
                    )}
                    {h.models !== undefined && (
                      <span className="ml-2 text-gray-500 dark:text-gray-400">{h.models} models available</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Switch Provider Bar */}
        {selectedProvider && selectedModel && (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-100 dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800">
            <div className="flex-1 text-sm">
              <span className="text-gray-500 dark:text-gray-400">Switch to:</span>{" "}
              <span className={providerAccent[selectedProvider] || "text-gray-900 dark:text-gray-100"}>
                {selectedProvider}
              </span>{" "}
              <span className="text-gray-300 dark:text-gray-600">/</span>{" "}
              <span className="font-mono text-mizan-gold">{selectedModel}</span>
            </div>
            <button
              onClick={switchProvider}
              disabled={switching || (status?.active === selectedProvider && status?.default_model === selectedModel)}
              className="btn-gold text-sm disabled:opacity-30"
            >
              {switching ? "Switching..." : "Apply"}
            </button>
          </div>
        )}

        {/* Model Browser */}
        {browseProvider && models[browseProvider] && (
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {browseProvider === "openrouter" ? "OpenRouter Model Catalog" :
                 browseProvider === "ollama" ? "Local Ollama Models" :
                 `${browseProvider} Models`}
              </h3>
              <button
                onClick={() => setBrowseProvider(null)}
                className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              >
                Close
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto space-y-1 scrollbar-thin">
              {models[browseProvider].length === 0 ? (
                <div className="text-xs text-gray-400 dark:text-gray-500 py-4 text-center">
                  No models found. {browseProvider === "ollama" ? "Is Ollama running?" : "Check API key."}
                </div>
              ) : (
                models[browseProvider].map((m) => (
                  <div
                    key={m.id}
                    className={`flex items-center justify-between px-3 py-2 rounded cursor-pointer transition-colors ${
                      selectedModel === m.id
                        ? "bg-mizan-gold/10 border border-mizan-gold/20"
                        : "bg-gray-50 dark:bg-zinc-800/50 hover:bg-gray-100 dark:hover:bg-zinc-800"
                    }`}
                    onClick={() => {
                      setSelectedProvider(browseProvider);
                      setSelectedModel(m.id);
                    }}
                  >
                    <div>
                      <div className="text-xs font-mono text-gray-900 dark:text-gray-200">{m.id}</div>
                      {m.name && m.name !== m.id && (
                        <div className="text-[10px] text-gray-500 dark:text-gray-400">{m.name}</div>
                      )}
                    </div>
                    <div className="text-right text-[10px] text-gray-400 dark:text-gray-500">
                      {m.context ? `${(m.context / 1000).toFixed(0)}k` : ""}
                      {m.pricing && (
                        <div>
                          ${parseFloat(m.pricing.prompt || "0").toFixed(4)}/1k
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Setup Guide */}
        <div className="card">
          <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wider">Quick Setup</h3>
          <div className="space-y-2 text-xs font-mono">
            <div>
              <span className="text-amber-600 dark:text-amber-400">Anthropic:</span>{" "}
              <span className="text-gray-600 dark:text-gray-400">ANTHROPIC_API_KEY=sk-ant-...</span>
            </div>
            <div>
              <span className="text-purple-600 dark:text-purple-400">OpenRouter:</span>{" "}
              <span className="text-gray-600 dark:text-gray-400">OPENROUTER_API_KEY=sk-or-... </span>
              <span className="text-gray-400 dark:text-gray-500">(300+ models from openrouter.ai)</span>
            </div>
            <div>
              <span className="text-emerald-600 dark:text-emerald-400">OpenAI:</span>{" "}
              <span className="text-gray-600 dark:text-gray-400">OPENAI_API_KEY=sk-...</span>
            </div>
            <div>
              <span className="text-blue-600 dark:text-blue-400">Ollama:</span>{" "}
              <span className="text-gray-600 dark:text-gray-400">OLLAMA_URL=http://localhost:11434</span>
              <span className="text-gray-400 dark:text-gray-500"> (local models)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
