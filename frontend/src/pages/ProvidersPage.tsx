/**
 * Providers Page (Ruh al-Ilm - روح العلم)
 * LLM Provider configuration, model selection, and health monitoring.
 * Inspired by OpenClaw's multi-provider architecture.
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
        <div className="text-gold-500/50 animate-pulse">Loading providers...</div>
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
    anthropic: "from-amber-500/20 to-amber-900/10 border-amber-500/30",
    openrouter: "from-purple-500/20 to-purple-900/10 border-purple-500/30",
    openai: "from-emerald-500/20 to-emerald-900/10 border-emerald-500/30",
    ollama: "from-blue-500/20 to-blue-900/10 border-blue-500/30",
  };

  const providerAccent: Record<string, string> = {
    anthropic: "text-amber-400",
    openrouter: "text-purple-400",
    openai: "text-emerald-400",
    ollama: "text-blue-400",
  };

  return (
    <div className="space-y-6 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gold-300">
            روح العلم — LLM Providers
          </h2>
          <p className="text-xs text-white/40 mt-1">
            Active: <span className="text-gold-400">{status?.active}</span>
            {" · "}Model: <span className="text-gold-400">{status?.default_model}</span>
          </p>
        </div>
      </div>

      {/* Provider Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {status?.providers.map((provider: ProviderInfo) => {
          const isActive = status.active === provider.name;
          const h = health[provider.name];
          const colorClass = providerColors[provider.name] || "from-gray-500/20 to-gray-900/10 border-gray-500/30";
          const accentClass = providerAccent[provider.name] || "text-gray-400";

          return (
            <div
              key={provider.name}
              className={`relative rounded-lg border bg-gradient-to-br p-4 transition-all ${colorClass} ${
                isActive ? "ring-1 ring-gold-500/50" : ""
              }`}
            >
              {/* Active badge */}
              {isActive && (
                <div className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold bg-gold-500/20 text-gold-400 border border-gold-500/30">
                  ACTIVE
                </div>
              )}

              {/* Provider header */}
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg font-bold ${accentClass} bg-white/5`}>
                  {providerIcons[provider.name] || "?"}
                </div>
                <div>
                  <div className="font-medium text-white/90">{provider.display}</div>
                  <div className="text-xs text-white/40">
                    {provider.configured ? (
                      <span className="text-emerald-400">Configured</span>
                    ) : (
                      <span className="text-red-400">Not configured</span>
                    )}
                    {provider.models.length > 0 && ` · ${provider.models.length} models`}
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
                          ? "bg-gold-500/20 text-gold-300 border border-gold-500/30"
                          : "bg-white/5 text-white/60 hover:bg-white/10"
                      }`}
                      onClick={() => {
                        setSelectedProvider(provider.name);
                        setSelectedModel(m.id);
                      }}
                    >
                      <span className="font-mono">{m.id}</span>
                      {m.context ? (
                        <span className="ml-2 text-white/30">{(m.context / 1000).toFixed(0)}k ctx</span>
                      ) : null}
                      {m.vision && <span className="ml-1 text-purple-400/60">vision</span>}
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 mt-2">
                <button
                  onClick={() => checkHealth(provider.name)}
                  className="px-3 py-1 text-xs rounded bg-white/5 hover:bg-white/10 text-white/60 transition-colors"
                >
                  Health Check
                </button>
                <button
                  onClick={() => browseModels(provider.name)}
                  className="px-3 py-1 text-xs rounded bg-white/5 hover:bg-white/10 text-white/60 transition-colors"
                >
                  Browse Models
                </button>
                {!isActive && provider.configured && (
                  <button
                    onClick={() => {
                      setSelectedProvider(provider.name);
                      setSelectedModel(provider.default_model);
                    }}
                    className={`px-3 py-1 text-xs rounded bg-white/5 hover:bg-white/10 transition-colors ${accentClass}`}
                  >
                    Select
                  </button>
                )}
              </div>

              {/* Health result */}
              {h && (
                <div className={`mt-2 px-2 py-1 rounded text-xs ${h.healthy ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
                  {h.healthy ? "Healthy" : `Unhealthy: ${h.error || "unknown"}`}
                  {h.usage !== undefined && (
                    <span className="ml-2 text-white/40">
                      Usage: ${(h.usage || 0).toFixed(4)}
                      {h.limit && ` / $${h.limit}`}
                    </span>
                  )}
                  {h.models !== undefined && (
                    <span className="ml-2 text-white/40">{h.models} models available</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Switch Provider Bar */}
      {selectedProvider && selectedModel && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-white/5 border border-white/10">
          <div className="flex-1 text-sm">
            <span className="text-white/50">Switch to:</span>{" "}
            <span className={providerAccent[selectedProvider] || "text-white"}>
              {selectedProvider}
            </span>{" "}
            <span className="text-white/30">/</span>{" "}
            <span className="font-mono text-gold-300">{selectedModel}</span>
          </div>
          <button
            onClick={switchProvider}
            disabled={switching || (status?.active === selectedProvider && status?.default_model === selectedModel)}
            className="px-4 py-1.5 text-sm rounded bg-gold-500/20 text-gold-300 border border-gold-500/30 hover:bg-gold-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {switching ? "Switching..." : "Apply"}
          </button>
        </div>
      )}

      {/* Model Browser Modal */}
      {browseProvider && models[browseProvider] && (
        <div className="rounded-lg border border-white/10 bg-[#0a1520] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-white/80">
              {browseProvider === "openrouter" ? "OpenRouter Model Catalog" :
               browseProvider === "ollama" ? "Local Ollama Models" :
               `${browseProvider} Models`}
            </h3>
            <button
              onClick={() => setBrowseProvider(null)}
              className="text-xs text-white/40 hover:text-white/60"
            >
              Close
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto space-y-1 scrollbar-thin">
            {models[browseProvider].length === 0 ? (
              <div className="text-xs text-white/30 py-4 text-center">
                No models found. {browseProvider === "ollama" ? "Is Ollama running?" : "Check API key."}
              </div>
            ) : (
              models[browseProvider].map((m) => (
                <div
                  key={m.id}
                  className={`flex items-center justify-between px-3 py-2 rounded cursor-pointer transition-colors ${
                    selectedModel === m.id
                      ? "bg-gold-500/15 border border-gold-500/30"
                      : "bg-white/5 hover:bg-white/10"
                  }`}
                  onClick={() => {
                    setSelectedProvider(browseProvider);
                    setSelectedModel(m.id);
                  }}
                >
                  <div>
                    <div className="text-xs font-mono text-white/80">{m.id}</div>
                    {m.name && m.name !== m.id && (
                      <div className="text-[10px] text-white/40">{m.name}</div>
                    )}
                  </div>
                  <div className="text-right text-[10px] text-white/30">
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
      <div className="rounded-lg border border-white/5 bg-white/[0.02] p-4">
        <h3 className="text-xs font-semibold text-white/50 mb-2 uppercase tracking-wider">Quick Setup</h3>
        <div className="space-y-2 text-xs text-white/40 font-mono">
          <div>
            <span className="text-amber-400">Anthropic:</span>{" "}
            <span className="text-white/60">ANTHROPIC_API_KEY=sk-ant-...</span>
          </div>
          <div>
            <span className="text-purple-400">OpenRouter:</span>{" "}
            <span className="text-white/60">OPENROUTER_API_KEY=sk-or-... </span>
            <span className="text-white/25">(300+ models from openrouter.ai)</span>
          </div>
          <div>
            <span className="text-emerald-400">OpenAI:</span>{" "}
            <span className="text-white/60">OPENAI_API_KEY=sk-...</span>
          </div>
          <div>
            <span className="text-blue-400">Ollama:</span>{" "}
            <span className="text-white/60">OLLAMA_URL=http://localhost:11434</span>
            <span className="text-white/25"> (local models)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
