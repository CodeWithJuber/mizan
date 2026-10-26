import type { ApiClient, ProviderModel } from "../types";

export interface AgentSettingsSource {
  id: string;
  name: string;
  role: string;
  model?: string;
  provider?: string;
  system_prompt?: string;
}

export interface AgentFormData {
  name: string;
  type: string;
  model: string;
  provider: string;
  system_prompt: string;
}

/** Bind an editor/read operation to the account that started it. The epoch
 * also invalidates work if a user switches away and back to the same token. */
export function agentSettingsScope(readToken: () => string | null, readEpoch: () => number): () => boolean {
  const token = readToken();
  const epoch = readEpoch();
  return () => !!token && readToken() === token && readEpoch() === epoch;
}

// These canonical creation types are accepted by AgentCreate and the agent
// factory. There is no runtime type-catalog endpoint; edit displays the actual
// stored role, including aliases and roles absent from this creation menu.
export const AGENT_CREATION_TYPES = [
  { id: "super", label: "Khalifah / General Agent" },
  { id: "general", label: "General Purpose" },
  { id: "browser", label: "Browser / Web Research" },
  { id: "research", label: "Deep Research" },
  { id: "code", label: "Code Generation" },
  { id: "communication", label: "Communication" },
];

export function agentFormData(agent?: AgentSettingsSource | null): AgentFormData {
  return {
    name: agent?.name ?? "", type: agent?.role ?? "general",
    model: agent?.model ?? "", provider: agent?.provider ?? "",
    system_prompt: agent?.system_prompt ?? "",
  };
}

const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export interface AgentCatalogSource {
  provider: string;
  display: string;
  configured: boolean;
  defaultModel: string;
}

export function agentCatalogSource(value: unknown, currentProvider = ""): AgentCatalogSource | null {
  if (!object(value) || !Array.isArray(value.providers)) return null;
  const name = currentProvider || (typeof value.active === "string" ? value.active : "");
  const provider = value.providers.find((entry) => object(entry) && entry.name === name);
  if (!object(provider) || !name) return null;
  return {
    provider: name,
    display: typeof provider.display === "string" ? provider.display : name,
    configured: provider.configured === true,
    // Only the active runtime default is authoritative. Per-provider defaults
    // can be examples; never silently select either one in the form.
    defaultModel: value.active === name && provider.configured === true && typeof value.default_model === "string"
      ? value.default_model : "",
  };
}

export function agentCatalogSources(value: unknown): AgentCatalogSource[] {
  if (!object(value) || !Array.isArray(value.providers)) return [];
  return value.providers.flatMap((provider) => {
    const source = object(provider) && typeof provider.name === "string" ? agentCatalogSource(value, provider.name) : null;
    return source ? [source] : [];
  });
}

export const agentModelValue = (provider: string, model: string): string => model ? JSON.stringify([provider, model]) : "";

export function agentModelOptions(options: {
  currentModel: string;
  currentProvider: string;
  selectedModel: string;
  selectedProvider: string;
  catalogProvider: string;
  defaultModel?: string;
  models: ProviderModel[];
}): { id: string; provider: string; value: string; label: string }[] {
  const models = new Map<string, { id: string; provider: string; value: string; label: string }>();
  const add = (provider: string, model: string, label: string) => {
    const value = agentModelValue(provider, model);
    if (model && !models.has(value)) models.set(value, { id: model, provider, value, label });
  };
  add(options.currentProvider, options.currentModel, `${options.currentModel} (current${options.currentProvider ? ` · ${options.currentProvider}` : ""})`);
  add(options.selectedProvider, options.selectedModel, `${options.selectedModel} (selected · ${options.selectedProvider})`);
  add(options.catalogProvider, options.defaultModel ?? "", `${options.defaultModel} (configured default)`);
  for (const model of options.models) {
    add(options.catalogProvider, model.id, model.name && model.name !== model.id ? `${model.id} — ${model.name}` : model.id);
  }
  return [...models.values()];
}

export async function loadAgentModels(
  get: ApiClient["get"], provider: string, search = "", offset = 0,
): Promise<{ models: ProviderModel[]; total: number }> {
  const query = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (search) query.set("search", search);
  const data = await get(`/providers/${encodeURIComponent(provider)}/models?${query}`);
  if (!Array.isArray(data.models)) throw new Error("The model catalog is unavailable.");
  const models = data.models.filter((model): model is ProviderModel => object(model) &&
    typeof model.id === "string" && model.id.length > 0);
  return { models, total: typeof data.total === "number" && Number.isFinite(data.total) && data.total >= 0
    ? data.total : models.length };
}

export function agentProfileChanges(agent: AgentSettingsSource, data: AgentFormData): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  if (data.name !== agent.name) changes.name = data.name;
  if (data.system_prompt !== (agent.system_prompt ?? "")) changes.system_prompt = data.system_prompt;
  return changes;
}

export function agentModelChange(agent: AgentSettingsSource, data: AgentFormData): { provider: string; model: string } | null {
  if (data.model === (agent.model ?? "") && data.provider === (agent.provider ?? "")) return null;
  if (!data.model || !data.provider) throw new Error("Choose a model from a configured provider before changing it.");
  return { provider: data.provider, model: data.model };
}

/** Only explicit model changes use the existing provider-aware endpoint. */
export async function saveAgentEdits(api: Pick<ApiClient, "put" | "post">, agent: AgentSettingsSource, data: AgentFormData, isCurrent: () => boolean): Promise<boolean> {
  if (!isCurrent()) return false;
  const model = agentModelChange(agent, data);
  const profile = agentProfileChanges(agent, data);
  let modelSaved = false;
  try {
    if (model) {
      await api.post(`/agents/${encodeURIComponent(agent.id)}/model`, model);
      modelSaved = true;
      if (!isCurrent()) return false;
    }
    if (Object.keys(profile).length) await api.put(`/agents/${encodeURIComponent(agent.id)}`, profile);
    return isCurrent();
  } catch (error) {
    if (!isCurrent()) return false;
    if (modelSaved) throw new Error(`The model changed, but the other agent changes were not saved. ${error instanceof Error ? error.message : "Try saving again."}`);
    throw error;
  }
}

export function agentCreatePayload(data: AgentFormData): Record<string, unknown> {
  if (!data.model || !data.provider) throw new Error("Choose a model from a configured provider before creating an agent.");
  if (data.model.length > 200) throw new Error("Model IDs must be 200 characters or fewer.");
  return { name: data.name, type: data.type, provider: data.provider, model: data.model, system_prompt: data.system_prompt || undefined };
}
