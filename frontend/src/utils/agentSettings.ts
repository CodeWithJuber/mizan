import type { AgentEffort, AgentOrchestration, AgentSettings, ApiClient, ProviderModel } from "../types";
import { PERMISSION_MODES, type PermissionMode } from "./agentActivity.ts";

export interface AgentSettingsSource {
  id: string;
  name: string;
  role: string;
  model?: string;
  provider?: string;
  system_prompt?: string;
  settings?: unknown;
  shared?: boolean;
}

export interface AgentFormData {
  name: string;
  type: string;
  model: string;
  provider: string;
  system_prompt: string;
  settings: AgentSettings;
  /** Share with everyone on the server (admins only, when creating). */
  shared: boolean;
}

// Limits the form checks before asking the server (the server checks again).
export const AGENT_NAME_MAX = 100;
export const AGENT_PROMPT_MAX = 10_000;
export const AGENT_AVATAR_MAX = 8;
export const STARTER_PROMPTS_MAX = 6;
export const STARTER_PROMPT_MAX = 500;
// The server's own ranges for the behaviour settings.
export const TEMPERATURE_MAX = 1;
export const MAX_STEPS_MAX = 1000;
export const MAX_OUTPUT_TOKENS_MIN = 256;
export const MAX_OUTPUT_TOKENS_MAX = 128_000;

export const AGENT_EFFORTS: readonly AgentEffort[] = ["low", "medium", "high", "xhigh", "max"];
export const AGENT_ORCHESTRATIONS: readonly AgentOrchestration[] = ["mizan", "hybrid", "llm"];

export const ORCHESTRATION_LABELS: Record<AgentOrchestration, { title: string; hint: string }> = {
  mizan: {
    title: "MIZAN decides (mizan)",
    hint: "MIZAN plans and runs every tool; the model only words the answer. Requests MIZAN has no recipe for are answered in words.",
  },
  hybrid: {
    title: "Hybrid — MIZAN recipes first, then the model acts with tools (recommended)",
    hint: "MIZAN's checked recipes (Quran, hadith, compute, code) run first; anything else the model does itself with this agent's tools.",
  },
  llm: {
    title: "Model drives (llm)",
    hint: "The model chooses and calls the tools itself, like a plain agent. MIZAN's checks still run on the answer.",
  },
};

/** Every key present: null = the server's default, an empty list = no restriction. */
export const DEFAULT_AGENT_SETTINGS: AgentSettings = {
  temperature: null, effort: null, max_steps: null, max_output_tokens: null, orchestration: null,
  permission_mode: null, tools_allow: [], tools_deny: [], connectors: [], skills: [], starter_prompts: [],
  avatar: null, learn_skills: true,
};

const finite = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const strings = (value: unknown): string[] =>
  Array.isArray(value) ? [...new Set(value.filter((item): item is string => typeof item === "string" && item.trim() !== ""))] : [];
const oneOf = <T extends string>(choices: readonly T[], value: unknown): T | null =>
  typeof value === "string" && (choices as readonly string[]).includes(value) ? (value as T) : null;

/** An agent's settings as the server sent them; an older server sends none, so every key falls back to its default. */
export function agentSettingsFrom(value: unknown): AgentSettings {
  const raw = object(value) ? value : {};
  const avatar = typeof raw.avatar === "string" && raw.avatar.trim() ? raw.avatar.trim() : null;
  return {
    temperature: finite(raw.temperature),
    effort: oneOf(AGENT_EFFORTS, raw.effort),
    max_steps: finite(raw.max_steps),
    max_output_tokens: finite(raw.max_output_tokens),
    orchestration: oneOf(AGENT_ORCHESTRATIONS, raw.orchestration),
    permission_mode: oneOf<PermissionMode>(PERMISSION_MODES, raw.permission_mode),
    tools_allow: strings(raw.tools_allow),
    tools_deny: strings(raw.tools_deny),
    connectors: strings(raw.connectors),
    skills: strings(raw.skills),
    starter_prompts: Array.isArray(raw.starter_prompts)
      ? raw.starter_prompts.filter((item): item is string => typeof item === "string" && item.trim() !== "").slice(0, STARTER_PROMPTS_MAX)
      : [],
    avatar,
    learn_skills: typeof raw.learn_skills === "boolean" ? raw.learn_skills : DEFAULT_AGENT_SETTINGS.learn_skills,
  };
}

const sameValue = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Only the keys that changed (the server merges them; null resets one to its default). */
export function agentSettingsChanges(before: AgentSettings, after: AgentSettings): Partial<AgentSettings> {
  const changes: Record<string, unknown> = {};
  for (const key of Object.keys(DEFAULT_AGENT_SETTINGS) as (keyof AgentSettings)[]) {
    if (!sameValue(before[key], after[key])) changes[key] = after[key];
  }
  return changes as Partial<AgentSettings>;
}

/** Code points, so an emoji counts once (as the server counts it). */
export const textLength = (value: string): number => Array.from(value).length;

export interface AgentSettingsProblem {
  field: keyof AgentSettings;
  message: string;
}

/**
 * The first problem with the settings, in words for the person, or null.
 * Given `before` (an agent's saved settings), only the keys that changed are
 * checked: a value the server already holds is never refused here.
 */
export function agentSettingsProblem(settings: AgentSettings, before?: AgentSettings): AgentSettingsProblem | null {
  const checked = before ? { ...DEFAULT_AGENT_SETTINGS, ...agentSettingsChanges(before, settings) } : settings;
  const { temperature, max_steps, max_output_tokens, avatar, starter_prompts } = checked;
  if (avatar !== null && textLength(avatar) > AGENT_AVATAR_MAX) {
    return { field: "avatar", message: `The avatar can be at most ${AGENT_AVATAR_MAX} characters.` };
  }
  if (temperature !== null && (temperature < 0 || temperature > TEMPERATURE_MAX)) {
    return { field: "temperature", message: `Temperature must be between 0 and ${TEMPERATURE_MAX}.` };
  }
  if (max_steps !== null && (!Number.isInteger(max_steps) || max_steps < 1 || max_steps > MAX_STEPS_MAX)) {
    return { field: "max_steps", message: `Max steps must be a whole number from 1 to ${MAX_STEPS_MAX.toLocaleString("en")}.` };
  }
  if (max_output_tokens !== null && (!Number.isInteger(max_output_tokens) || max_output_tokens < MAX_OUTPUT_TOKENS_MIN
    || max_output_tokens > MAX_OUTPUT_TOKENS_MAX)) {
    return {
      field: "max_output_tokens",
      message: `Max output tokens must be a whole number from ${MAX_OUTPUT_TOKENS_MIN} to ${MAX_OUTPUT_TOKENS_MAX.toLocaleString("en")}.`,
    };
  }
  if (starter_prompts.length > STARTER_PROMPTS_MAX) {
    return { field: "starter_prompts", message: `At most ${STARTER_PROMPTS_MAX} starter prompts.` };
  }
  if (starter_prompts.some((prompt) => prompt.length > STARTER_PROMPT_MAX || /[\r\n]/.test(prompt))) {
    return { field: "starter_prompts", message: `Each starter prompt is one line of at most ${STARTER_PROMPT_MAX} characters.` };
  }
  return null;
}

/** A number field: empty = the server's default (null); anything else must be a number. */
export function parseSettingNumber(raw: string): { value: number | null; valid: boolean } {
  const text = raw.trim();
  if (!text) return { value: null, valid: true };
  const value = Number(text);
  return Number.isFinite(value) ? { value, valid: true } : { value: null, valid: false };
}

/** Claude models take no temperature (the API rejects it): effort sets how hard they think. */
export function isClaudeModel(provider: string, model: string): boolean {
  return provider === "anthropic" || /claude/i.test(model);
}

export type ToolChoice = "default" | "allow" | "deny";

export function toolChoice(settings: Pick<AgentSettings, "tools_allow" | "tools_deny">, tool: string): ToolChoice {
  if (settings.tools_deny.includes(tool)) return "deny";
  if (settings.tools_allow.includes(tool)) return "allow";
  return "default";
}

/** One click on a tool: default → only these (allow) → never (deny) → default. */
export function cycleTool<T extends Pick<AgentSettings, "tools_allow" | "tools_deny">>(settings: T, tool: string): T {
  const without = (list: string[]) => list.filter((item) => item !== tool);
  const next = { ...settings, tools_allow: without(settings.tools_allow), tools_deny: without(settings.tools_deny) };
  const choice = toolChoice(settings, tool);
  if (choice === "default") next.tools_allow = [...next.tools_allow, tool];
  else if (choice === "allow") next.tools_deny = [...next.tools_deny, tool];
  return next;
}

/** The tools an agent may use: the server's list after allow/deny, else its whole tool table (older servers). */
export function agentTools(agent: { tools?: unknown; effective_tools?: unknown }): string[] {
  const effective = strings(agent.effective_tools);
  return effective.length || Array.isArray(agent.effective_tools) ? effective : strings(agent.tools);
}

/** Tools the builder can offer: every tool the person's agents have, plus any the settings name. */
export function agentToolCatalog(
  agents: { tools?: unknown; effective_tools?: unknown }[],
  settings?: Pick<AgentSettings, "tools_allow" | "tools_deny">,
): string[] {
  const all = new Set<string>();
  for (const agent of agents) for (const tool of [...strings(agent.tools), ...strings(agent.effective_tools)]) all.add(tool);
  for (const tool of [...(settings?.tools_allow ?? []), ...(settings?.tools_deny ?? [])]) all.add(tool);
  return [...all].sort((a, b) => a.localeCompare(b));
}

/** Toggle one item in a list setting (connectors, skills). */
export const toggled = (list: string[], item: string): string[] =>
  list.includes(item) ? list.filter((entry) => entry !== item) : [...list, item];

/** The agent's starter prompts, for a new chat. */
export function agentStarterPrompts(agent: { settings?: unknown } | null | undefined): string[] {
  return agent ? agentSettingsFrom(agent.settings).starter_prompts : [];
}

export const AGENT_EXPORT_FORMAT = "mizan-agent/1";

/** A file name for an exported agent: `<name>.mizan-agent.json`. */
export function agentExportFilename(name: string): string {
  const cleaned = Array.from(name.normalize("NFKC"))
    .map((char) => (char.charCodeAt(0) < 32 || '\\/:*?"<>|'.includes(char) ? " " : char))
    .join("");
  const safe = cleaned.replace(/\s+/g, " ").trim().slice(0, 80) || "agent";
  return `${safe}.mizan-agent.json`;
}

/** Read an exported agent file; throws a message for the person when it is not one. */
export function parseAgentImport(text: string): { format: string; agent: Record<string, unknown> } {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("This file is not JSON. Choose a .mizan-agent.json file exported from MIZAN.");
  }
  if (!object(data) || data.format !== AGENT_EXPORT_FORMAT || !object(data.agent)) {
    throw new Error(`This is not a MIZAN agent file (expected format "${AGENT_EXPORT_FORMAT}").`);
  }
  if (typeof data.agent.name !== "string" || !data.agent.name.trim()) throw new Error("The agent in this file has no name.");
  return { format: AGENT_EXPORT_FORMAT, agent: data.agent };
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
    settings: agentSettingsFrom(agent?.settings),
    shared: agent?.shared === true,
  };
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

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
  const settings = agentSettingsChanges(agentSettingsFrom(agent.settings), data.settings);
  if (Object.keys(settings).length) changes.settings = settings;
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
  const problem = agentSettingsProblem(data.settings, agentSettingsFrom(agent.settings));
  if (problem) throw new Error(problem.message);
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
  const problem = agentSettingsProblem(data.settings);
  if (problem) throw new Error(problem.message);
  return {
    name: data.name, type: data.type, provider: data.provider, model: data.model, system_prompt: data.system_prompt || undefined,
    // What the form shows is what is saved: every key, nulls meaning the server's default.
    settings: data.settings,
    // Always said: an admin's agent is shared unless this is false (others' never are).
    shared: data.shared,
  };
}
