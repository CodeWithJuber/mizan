import { agentCatalogSource, agentCatalogSources, agentCreatePayload, agentFormData, agentModelChange,
  agentModelOptions, agentModelValue, agentSettingsScope, loadAgentModels, saveAgentEdits } from "./agentSettings.ts";
import type { ApiClient } from "../types.ts";

let checks = 0;
function check(name: string, value: boolean) { if (!value) throw new Error(name); checks++; }
const has = (value: Record<string, unknown> | undefined, key: string) => Object.prototype.hasOwnProperty.call(value, key);
const current = () => true;
const agent = { id: "active-agent", name: "Khalifah", role: "khalifah", provider: "openrouter", model: "nvidia/nemotron-3.5-super-vl:free", system_prompt: "" };
const initial = agentFormData(agent);
check("editing keeps the live model and type absent from the old static select", initial.model === agent.model && initial.type === "khalifah");
check("empty custom prompt remains empty rather than pretending built-in instructions are missing", initial.system_prompt === "");
check("new agent never preselects a paid or hardcoded model", agentFormData().model === "" && agentFormData().provider === "");
check("a missing model remains unknown rather than becoming Claude", agentFormData({ ...agent, model: undefined }).model === "");

const optionArgs = { currentModel: agent.model, currentProvider: agent.provider, selectedModel: agent.model, selectedProvider: agent.provider, catalogProvider: "openrouter", models: [] };
const offline = agentModelOptions(optionArgs);
check("catalog failure or missing listing keeps an exact selectable current value", offline.length === 1 && offline[0].value === agentModelValue(initial.provider, initial.model));
const selected = agentModelOptions({ ...optionArgs, selectedModel: "vendor/new", models: [{ id: "vendor/other", name: "Other" }] });
check("search or pagination cannot remove a model explicitly selected on another page", selected.some((model) => model.id === "vendor/new") && selected.some((model) => model.id === agent.model));
const sameId = agentModelOptions({ ...optionArgs, catalogProvider: "mizan-hybrid", models: [{ id: agent.model, name: "Hybrid" }] });
check("same model ID on different providers remains two distinct choices", sameId.length === 2 && sameId[0].value !== sameId[1].value);
check("catalog models carry their provider rather than inferring it from slashes", sameId[1].provider === "mizan-hybrid");
const emptyOptions = agentModelOptions({ ...optionArgs, currentModel: "", selectedModel: "", models: [] });
check("empty catalog with no current model creates no fallback option", emptyOptions.length === 0);

const status = { active: "openrouter", default_model: agent.model, providers: [
  { name: "openrouter", display: "OpenRouter", configured: true, default_model: "paid-example" },
  { name: "ollama", display: "Local", configured: true, default_model: "compiled-example" },
  { name: "anthropic", display: "Anthropic", configured: false, default_model: "claude-example" },
] };
check("provider menu comes from runtime status and preserves configuration flags", agentCatalogSources(status).length === 3 && agentCatalogSources(status)[2].configured === false);
check("active runtime model is offered as an explicit choice", agentCatalogSource(status)?.defaultModel === agent.model);
check("inactive compiled provider examples are not offered as defaults", agentCatalogSource(status, "ollama")?.defaultModel === "");
check("unconfigured active provider has no default model choice", agentCatalogSource({ ...status, active: "anthropic", default_model: "paid" })?.defaultModel === "");
check("unknown current provider does not silently fall back to another", agentCatalogSource(status, "custom-unavailable") === null);
check("browsing catalogs does not alter the current form model/provider", initial.model === agent.model && initial.provider === agent.provider);

const catalogPaths: string[] = [];
const page = await loadAgentModels(async (path) => { catalogPaths.push(path); return { models: [{ id: "model/one", name: "One" }, { name: "invalid" }, null], total: 75 }; }, "openrouter", "nemotron & free", 50);
check("catalog uses the existing read-only provider endpoint with search and pagination", catalogPaths[0] === "/providers/openrouter/models?limit=50&offset=50&search=nemotron+%26+free");
check("invalid catalog rows do not invent model choices", page.models.length === 1 && page.total === 75);
let catalogRejected = false;
try { await loadAgentModels(async () => ({ error: "offline" }), "openrouter"); } catch { catalogRejected = true; }
check("failed catalog has no static-model fallback", catalogRejected);

const calls: { method: string; path: string; body: Record<string, unknown> | undefined }[] = [];
const api: Pick<ApiClient, "post" | "put"> = {
  post: async (path, body) => { calls.push({ method: "POST", path, body }); return {}; },
  put: async (path, body) => { calls.push({ method: "PUT", path, body }); return {}; },
};
await saveAgentEdits(api, agent, initial, current);
check("opening and saving untouched settings issues no model or profile mutation", calls.length === 0);
await saveAgentEdits(api, agent, { ...initial, name: "Renamed", system_prompt: "Use precise citations." }, current);
check("save sends submitted edited fields rather than the stale parent form", calls.length === 1 && calls[0].body?.name === "Renamed" && calls[0].body?.system_prompt === "Use precise citations.");
check("name/prompt edit neither changes model nor destroys a provider override", calls[0].method === "PUT" && !has(calls[0].body, "model") && !has(calls[0].body, "provider"));
calls.length = 0;
await saveAgentEdits(api, { ...agent, model: undefined, provider: undefined }, { ...agentFormData({ ...agent, model: undefined, provider: undefined }), name: "Only name" }, current);
check("unreported model remains untouched when editing another field", calls.length === 1 && calls[0].body?.name === "Only name" && !has(calls[0].body, "model"));
calls.length = 0;
await saveAgentEdits(api, agent, { ...initial, model: "hf.co/custom/local", provider: "ollama" }, current);
check("explicit model change uses the existing provider-aware endpoint", calls.length === 1 && calls[0].path === "/agents/active-agent/model" && calls[0].body?.provider === "ollama" && calls[0].body?.model === "hf.co/custom/local");
check("provider-only choice with identical model ID is still explicit", agentModelChange(agent, { ...initial, provider: "mizan-hybrid" })?.provider === "mizan-hybrid");
calls.length = 0;
await saveAgentEdits(api, { ...agent, system_prompt: "Old custom prompt" }, initial, current);
check("deliberately clearing a custom prompt sends the empty override", calls[0].body?.system_prompt === "");
let rejectedEmpty = false;
try { await saveAgentEdits(api, agent, { ...initial, model: "" }, current); } catch { rejectedEmpty = true; }
check("empty model edit cannot trigger a backend default", rejectedEmpty && calls.length === 1);
let rejectedCreate = false;
try { agentCreatePayload({ ...agentFormData(), name: "New" }); } catch { rejectedCreate = true; }
check("new agent cannot be created until a model is explicitly chosen", rejectedCreate);

const chosen = { ...agentFormData(), name: "Custom", provider: "ollama", model: "hf.co/custom/local" };
const createPayload = agentCreatePayload(chosen);
check("creation passes the chosen model rather than the stale initial form", createPayload.model === chosen.model && createPayload.name === "Custom");
check("creation sends the explicit provider and model in a single atomic request", createPayload.provider === "ollama" && createPayload.model === "hf.co/custom/local");
check("creation accepts catalog model IDs within the shared 200-character API limit", agentCreatePayload({ ...chosen, model: "x".repeat(200) }).model === "x".repeat(200));
let rejectedLong = false;
try { agentCreatePayload({ ...chosen, model: "x".repeat(201) }); } catch { rejectedLong = true; }
check("oversized model IDs fail explicitly instead of truncating or falling back", rejectedLong);
let partialNotice = "";
try { await saveAgentEdits({ post: api.post, put: async () => { throw new Error("Database unavailable"); } }, agent, { ...initial, model: "vendor/new", name: "Renamed" }, current); }
catch (error) { partialNotice = (error as Error).message; }
check("partial settings save reports that model already changed", partialNotice.startsWith("The model changed, but the other agent changes were not saved."));

let token: string | null = "account-A";
let epoch = 0;
const readToken = () => token;
const readEpoch = () => epoch;
const saveScope = agentSettingsScope(readToken, readEpoch);
const scopedCalls: string[] = [];
let successUi = 0;
const scopedSaved = await saveAgentEdits({
  post: async () => { scopedCalls.push(`model:${token}`); token = "account-B"; epoch++; return {}; },
  put: async () => { scopedCalls.push(`profile:${token}`); return {}; },
}, agent, { ...initial, model: "vendor/new", name: "Renamed" }, saveScope);
if (scopedSaved && saveScope()) successUi++;
check("switching account while the model POST is pending prevents a name/prompt PUT under the new token", scopedCalls.join() === "model:account-A");
check("stale save completion cannot report success or refresh the new account's editor", !scopedSaved && successUi === 0);
token = "account-A";
check("switching away and back does not revive an old editor operation", !saveScope());
const callsBeforeStaleSave = calls.length;
const noMutation = await saveAgentEdits(api, agent, { ...initial, name: "Old form" }, saveScope);
check("already-stale form sends no mutation", !noMutation && calls.length === callsBeforeStaleSave);
token = "account-A";
const profileScope = agentSettingsScope(readToken, readEpoch);
const profileSaved = await saveAgentEdits({ post: api.post, put: async () => { token = "account-B"; epoch++; return {}; } }, agent, { ...initial, name: "Name only" }, profileScope);
check("account switch during a profile-only save suppresses stale completion", !profileSaved);
token = "account-A";
const failedScope = agentSettingsScope(readToken, readEpoch);
let staleFailureUi = 0;
try {
  const failed = await saveAgentEdits({ post: async () => { token = "account-B"; epoch++; throw new Error("Old request failed"); }, put: api.put }, agent, { ...initial, model: "vendor/new", name: "Old form" }, failedScope);
  if (failed) staleFailureUi++;
} catch { staleFailureUi++; }
check("failure from the old account cannot emit a new-account save notice", staleFailureUi === 0);
token = null;
check("logged-out forms cannot start a save scope", !agentSettingsScope(readToken, readEpoch)());
token = "account-A";
const catalogScope = agentSettingsScope(readToken, readEpoch);
await loadAgentModels(async () => { token = "account-B"; epoch++; return { models: [{ id: "old-account-model", name: "Old" }] }; }, "openrouter");
check("catalog response after account change cannot be applied by its owning scope", !catalogScope());
console.log(`${checks} agent settings/catalog checks passed`);
