import { useEffect, useRef, useState } from "react";
import type { Agent, ApiClient, ProviderModel } from "../types";
import { AGENT_CREATION_TYPES, agentCatalogSource, agentCatalogSources, agentFormData, agentModelOptions, agentModelValue, loadAgentModels,
  type AgentCatalogSource, type AgentFormData } from "../utils/agentSettings.ts";

interface AgentModalProps {
  editingAgent: Agent | null;
  initialData: AgentFormData;
  api: ApiClient;
  onSave: (data: AgentFormData) => Promise<void>;
  onClose: () => void;
}

export function AgentModal({
  editingAgent,
  initialData,
  api,
  onSave,
  onClose,
}: AgentModalProps) {
  const [formData, setFormData] = useState<AgentFormData>(() => editingAgent ? agentFormData(editingAgent) : initialData);
  const [nameError, setNameError] = useState("");
  const [saving, setSaving] = useState(false);
  const [source, setSource] = useState<AgentCatalogSource | null>(null);
  const [providers, setProviders] = useState<AgentCatalogSource[]>([]);
  const [browseProvider, setBrowseProvider] = useState(editingAgent?.provider ?? "");
  const [models, setModels] = useState<ProviderModel[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const ownerToken = useRef(localStorage.getItem("mizan_token"));

  useEffect(() => {
    let cancelled = false;
    const current = () => !cancelled && localStorage.getItem("mizan_token") === ownerToken.current;
    setCatalogLoading(true);
    setCatalogError("");
    setModels([]);
    setTotal(0);
    void (async () => {
      try {
        const status = await api.get("/providers");
        if (!current()) return;
        setProviders(agentCatalogSources(status));
        const next = agentCatalogSource(status, browseProvider);
        setSource(next);
        if (!next?.configured) {
          setModels([]);
          setCatalogError("No configured model catalog is available. Configure a provider in Settings to choose a model.");
          return;
        }
        const catalog = await loadAgentModels(api.get, next.provider, query, offset);
        if (!current()) return;
        setModels(catalog.models);
        setTotal(catalog.total);
      } catch {
        if (current()) {
          setModels([]);
          setCatalogError("Could not load the model catalog. The current model is unchanged; you can retry loading it.");
        }
      } finally { if (current()) setCatalogLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [api, editingAgent?.id, browseProvider, query, offset, refresh]);

  const modelOptions = agentModelOptions({ currentModel: editingAgent?.model ?? "", currentProvider: editingAgent?.provider ?? "",
    selectedModel: formData.model, selectedProvider: formData.provider, catalogProvider: source?.provider ?? "",
    defaultModel: source?.defaultModel, models });
  const canSave = !!formData.name.trim() && !saving && (!!editingAgent || (!!formData.model && providers.some((provider) => provider.provider === formData.provider && provider.configured)));

  const handleSave = async () => {
    if (saving || localStorage.getItem("mizan_token") !== ownerToken.current) return;
    if (!formData.name.trim()) {
      setNameError("Agent name is required");
      return;
    }
    if (!canSave) return;
    setNameError("");
    setSaving(true);
    try { await onSave(formData); }
    finally { setSaving(false); }
  };

  return (
    <div
      className="modal-backdrop"
      onClick={() => { if (!saving) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-modal-title"
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3
          id="agent-modal-title"
          className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-5"
        >
          {editingAgent ? "Edit Agent" : "Create New Agent"}
        </h3>

        <div className="space-y-4">
          <div>
            <label
              htmlFor="agent-name"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Agent Name
            </label>
            <input
              id="agent-name"
              className={`input w-full ${nameError ? "ring-2 ring-red-500/40 border-red-500" : ""}`}
              placeholder="e.g., Research Assistant, Code Helper..."
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (nameError) setNameError("");
              }}
              autoFocus
            />
            {nameError && (
              <p className="text-xs text-red-500 mt-1">{nameError}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="agent-type"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Agent Type
            </label>
            <select
              id="agent-type"
              className="input w-full"
              value={formData.type}
              onChange={(e) =>
                setFormData({ ...formData, type: e.target.value })
              }
              disabled={!!editingAgent}
            >
              {editingAgent ? <option value={formData.type}>{formData.type || "Type not reported"}</option>
                : AGENT_CREATION_TYPES.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
            </select>
            {editingAgent && (
              <p className="text-xs text-gray-400 mt-1">
                Agent type cannot be changed after creation
              </p>
            )}
          </div>

          <div>
            <label htmlFor="agent-provider" className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
              Browse provider models
            </label>
            <select id="agent-provider" className="input w-full mb-3" value={browseProvider || source?.provider || ""}
              onChange={(event) => { setBrowseProvider(event.target.value); setSource(null); setModels([]); setSearch(""); setQuery(""); setOffset(0); }}>
              {!browseProvider && !source && <option value="">No provider catalog available</option>}
              {browseProvider && !providers.some((provider) => provider.provider === browseProvider) && <option value={browseProvider}>{browseProvider} (current)</option>}
              {providers.map((provider) => <option key={provider.provider} value={provider.provider} disabled={!provider.configured}>
                {provider.display}{provider.configured ? "" : " (not configured)"}
              </option>)}
            </select>
            <label
              htmlFor="agent-model"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              AI Model
            </label>
            <select
              id="agent-model"
              className="input w-full"
              value={agentModelValue(formData.provider, formData.model)}
              onChange={(e) => {
                const model = modelOptions.find((option) => option.value === e.target.value);
                if (model) setFormData({ ...formData, model: model.id, provider: model.provider });
              }}
            >
              <option value="" disabled={!!formData.model}>{editingAgent ? "No model reported — keep unchanged" : "Choose a model"}</option>
              {modelOptions.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}
            </select>
            <p className="mt-1 text-xs text-gray-500 break-words">
              {editingAgent?.provider ? `Current provider: ${editingAgent.provider}. ` : ""}
              {source ? `Catalog: ${source.display}. ` : ""}
              A model changes only when you select one and save.
            </p>
            {source?.provider === "openrouter" && <div className="mt-2 flex gap-2">
              <input className="input min-w-0 flex-1 text-sm" aria-label="Search model catalog" placeholder="Search model IDs or names"
                value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => {
                  if (event.key === "Enter") { event.preventDefault(); setOffset(0); setQuery(search); }
                }} />
              <button type="button" className="btn-secondary" disabled={catalogLoading}
                onClick={() => { setOffset(0); setQuery(search); }}>Search</button>
            </div>}
            {catalogLoading && <p role="status" className="mt-1 text-xs text-gray-500">Loading models…</p>}
            {catalogError && <p role="status" className="mt-1 text-xs text-amber-700 dark:text-amber-300">{catalogError}</p>}
            {!catalogLoading && !catalogError && models.length === 0 && <p className="mt-1 text-xs text-gray-500">
              No matching catalog models were returned. The current selection is unchanged.
            </p>}
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <button type="button" className="btn-secondary" disabled={catalogLoading} onClick={() => setRefresh((value) => value + 1)}>Reload models</button>
              {source?.provider === "openrouter" && total > 50 && <>
                <span>{offset + 1}–{Math.min(offset + 50, total)} of {total}</span>
                <button type="button" className="btn-secondary" disabled={catalogLoading || offset === 0} onClick={() => setOffset((value) => Math.max(0, value - 50))}>Previous</button>
                <button type="button" className="btn-secondary" disabled={catalogLoading || offset + 50 >= total} onClick={() => setOffset((value) => value + 50)}>Next</button>
              </>}
            </div>
          </div>

          <div>
            <label
              htmlFor="agent-prompt"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              System Prompt{" "}
              <span className="normal-case tracking-normal font-normal">
                (optional)
              </span>
            </label>
            <textarea
              id="agent-prompt"
              className="input w-full h-24 resize-none text-sm"
              placeholder="Custom instructions for this agent... Leave empty for defaults."
              value={formData.system_prompt}
              onChange={(e) =>
                setFormData({ ...formData, system_prompt: e.target.value })
              }
            />
            <p className="mt-1 text-xs text-gray-500">This field stores optional custom instructions. Built-in instructions are applied separately.</p>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button className="btn-secondary cursor-pointer" disabled={saving} onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-gold cursor-pointer"
            onClick={handleSave}
            disabled={!canSave}
          >
            {saving ? "Saving…" : editingAgent ? "Save Changes" : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
