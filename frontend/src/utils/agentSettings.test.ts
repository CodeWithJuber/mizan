import { agentCatalogSource, agentCatalogSources, agentCreatePayload, agentExportFilename, agentFormData, agentModelChange,
  agentModelOptions, agentModelValue, agentSettingsChanges, agentSettingsFrom, agentSettingsProblem, agentSettingsScope,
  agentStarterPrompts, agentToolCatalog, agentTools, cycleTool, DEFAULT_AGENT_SETTINGS, isClaudeModel, loadAgentModels,
  parseAgentImport, parseSettingNumber, saveAgentEdits, toolChoice } from "./agentSettings.ts";
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

// ===== Agent builder settings =====
const oldServer = agentSettingsFrom(undefined);
check("an older server's agent (no settings) reads as every default", JSON.stringify(oldServer) === JSON.stringify(DEFAULT_AGENT_SETTINGS));
check("defaults mean the server decides: nulls, empty lists, learning skills on (the server's default)",
  oldServer.temperature === null && oldServer.orchestration === null && oldServer.permission_mode === null
  && oldServer.tools_allow.length === 0 && oldServer.starter_prompts.length === 0 && oldServer.learn_skills === true);
check("a saved learn_skills choice is kept", agentSettingsFrom({ learn_skills: false }).learn_skills === false);
const partial = agentSettingsFrom({ temperature: 0.4, effort: "turbo", permission_mode: "auto", tools_allow: ["bash", 3, "", "bash"], avatar: "  ", starter_prompts: ["a", "", "b", "c", "d", "e", "f", "g"] });
check("known values are kept, unknown choices fall back to the default", partial.temperature === 0.4 && partial.effort === null && partial.permission_mode === "auto");
check("lists keep only distinct non-empty names", JSON.stringify(partial.tools_allow) === JSON.stringify(["bash"]));
check("a blank avatar is no avatar", partial.avatar === null);
check("at most six starter prompts are read", partial.starter_prompts.length === 6 && partial.starter_prompts[0] === "a" && partial.starter_prompts[1] === "b");
check("a missing key in a partial payload still reads as its default", partial.max_steps === null && partial.connectors.length === 0);
check("an old agent's form carries default settings and is not shared", JSON.stringify(agentFormData(agent).settings) === JSON.stringify(DEFAULT_AGENT_SETTINGS) && agentFormData(agent).shared === false);

const before = agentSettingsFrom({ temperature: 0.7, effort: "high", tools_deny: ["bash"], starter_prompts: ["Hi"] });
const longAvatar = agentSettingsFrom({ avatar: "https://example.org/a.png" });
check("a saved value the server holds never blocks an edit of another key", agentSettingsProblem({ ...longAvatar, effort: "low" }, longAvatar) === null
  && agentSettingsProblem({ ...longAvatar, effort: "low" })?.field === "avatar");
check("temperature and output tokens follow the server's ranges", agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, temperature: 1.5 })?.field === "temperature"
  && agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, max_output_tokens: 100 })?.field === "max_output_tokens"
  && agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, temperature: 1, max_output_tokens: 128_000 }) === null);
check("a starter prompt is one line", agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, starter_prompts: ["two\nlines"] })?.field === "starter_prompts");
check("no change gives no settings keys", Object.keys(agentSettingsChanges(before, { ...before })).length === 0);
const diff = agentSettingsChanges(before, { ...before, temperature: null, effort: "high", tools_deny: [], learn_skills: false });
check("only changed keys are sent, a reset as null", JSON.stringify(diff) === JSON.stringify({ temperature: null, tools_deny: [], learn_skills: false }));
check("reordering starter prompts is a change", "starter_prompts" in agentSettingsChanges(agentSettingsFrom({ starter_prompts: ["a", "b"] }), agentSettingsFrom({ starter_prompts: ["b", "a"] })));

calls.length = 0;
const withSettings = { ...agent, settings: { orchestration: "mizan", starter_prompts: ["Hello"] } };
const editForm = agentFormData(withSettings);
await saveAgentEdits(api, withSettings, editForm, current);
check("an agent with settings saved untouched sends nothing", calls.length === 0);
await saveAgentEdits(api, withSettings, { ...editForm, settings: { ...editForm.settings, orchestration: "hybrid", permission_mode: "ask" } }, current);
check("a settings edit is one PUT with only the changed settings keys", calls.length === 1 && calls[0].method === "PUT"
  && JSON.stringify(calls[0].body) === JSON.stringify({ settings: { orchestration: "hybrid", permission_mode: "ask" } }));
calls.length = 0;
let badSettings = "";
try { await saveAgentEdits(api, withSettings, { ...editForm, settings: { ...editForm.settings, temperature: 3 } }, current); }
catch (error) { badSettings = (error as Error).message; }
check("out-of-range settings fail in words before any request", badSettings.includes("Temperature") && calls.length === 0);

const created = agentCreatePayload({ ...chosen, shared: true, settings: { ...DEFAULT_AGENT_SETTINGS, avatar: "🤖", starter_prompts: ["Plan my day"] } });
check("creation sends every settings key and sharing only when chosen", JSON.stringify(Object.keys(created.settings as object)) === JSON.stringify(Object.keys(DEFAULT_AGENT_SETTINGS)) && created.shared === true);
check("a private agent's create body says so (an admin's agent is shared unless told otherwise)", agentCreatePayload(chosen).shared === false);
check("an emoji avatar counts as one character", agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, avatar: "👩‍💻👩‍💻" }) === null
  && agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, avatar: "123456789" })?.field === "avatar");
check("steps must be whole", agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, max_steps: 2.5 })?.field === "max_steps");
check("seven starter prompts are refused", agentSettingsProblem({ ...DEFAULT_AGENT_SETTINGS, starter_prompts: Array(7).fill("x") })?.field === "starter_prompts");
check("an empty number field is the server's default; text is invalid", parseSettingNumber(" ").value === null && parseSettingNumber(" ").valid && !parseSettingNumber("abc").valid && parseSettingNumber("0.5").value === 0.5);
check("Claude models are known by provider or model id", isClaudeModel("anthropic", "x") && isClaudeModel("openrouter", "anthropic/claude-opus-5-5") && !isClaudeModel("xai", "grok-5"));

let tools = { tools_allow: [] as string[], tools_deny: [] as string[] };
tools = cycleTool(tools, "bash");
check("first click: only these tools", toolChoice(tools, "bash") === "allow");
tools = cycleTool(tools, "bash");
check("second click: never", toolChoice(tools, "bash") === "deny" && !tools.tools_allow.includes("bash"));
tools = cycleTool(tools, "bash");
check("third click: back to available", toolChoice(tools, "bash") === "default" && tools.tools_deny.length === 0);
check("the card shows the server's effective tools, else the old tool table", agentTools({ tools: ["a", "b"], effective_tools: ["a"] }).join() === "a"
  && agentTools({ tools: ["a", "b"] }).join() === "a,b" && agentTools({ tools: ["a"], effective_tools: [] }).length === 0);
check("the tool catalog joins every agent's tools and the settings' names, sorted", agentToolCatalog([{ tools: ["web", "bash"] }, { effective_tools: ["bash", "code"] }], { tools_allow: [], tools_deny: ["gone"] }).join() === "bash,code,gone,web");
check("starter prompts come from the agent's settings", agentStarterPrompts({ settings: { starter_prompts: ["Hi"] } }).join() === "Hi" && agentStarterPrompts(null).length === 0 && agentStarterPrompts({}).length === 0);

check("export file is named after the agent", agentExportFilename("Research Assistant") === "Research Assistant.mizan-agent.json");
check("export names drop path and control characters", agentExportFilename("a/b\\c:\u0007d") === "a b c d.mizan-agent.json" && agentExportFilename("///") === "agent.mizan-agent.json");
const exportFile = { format: "mizan-agent/1", agent: { name: "Katib", type: "katib", provider: "anthropic", model: "claude-haiku-5-5", system_prompt: "", settings: { avatar: "✍️" } } };
const imported = parseAgentImport(JSON.stringify(exportFile));
check("an exported agent file imports as the same body", JSON.stringify(imported) === JSON.stringify(exportFile));
const importError = (text: string) => { try { parseAgentImport(text); return ""; } catch (error) { return (error as Error).message; } };
check("a file that is not JSON is refused in words", importError("{not json").includes("not JSON"));
check("another format is refused", importError(JSON.stringify({ format: "mizan-daftar/1", agent: { name: "x" } })).includes("mizan-agent/1"));
check("an agent with no name is refused", importError(JSON.stringify({ format: "mizan-agent/1", agent: { name: " " } })).includes("no name"));

console.log(`${checks} agent settings/catalog checks passed`);
