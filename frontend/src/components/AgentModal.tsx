/**
 * The agent builder: who the agent is (Basics), how it works (Behaviour), what
 * it may use (Tools & knowledge) and how a chat with it starts (Starter
 * prompts). Every behaviour setting can stay on the server's default.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Ban, Check, Plus, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { Agent, AgentEffort, AgentOrchestration, AgentSettings, ApiClient, ProviderModel } from "../types";
import { useAuth } from "../app/auth";
import { PERMISSION_MODES, type PermissionMode } from "../utils/agentActivity";
import {
  AGENT_AVATAR_MAX, AGENT_CREATION_TYPES, AGENT_EFFORTS, AGENT_NAME_MAX, AGENT_ORCHESTRATIONS, AGENT_PROMPT_MAX,
  MAX_OUTPUT_TOKENS_MAX, MAX_OUTPUT_TOKENS_MIN, MAX_STEPS_MAX, ORCHESTRATION_LABELS, STARTER_PROMPT_MAX, STARTER_PROMPTS_MAX,
  TEMPERATURE_MAX, agentCatalogSource, agentCatalogSources, agentFormData, agentModelOptions, agentModelValue,
  agentSettingsFrom, agentSettingsProblem, agentToolCatalog, cycleTool, isClaudeModel, loadAgentModels, parseSettingNumber,
  textLength, toggled, toolChoice,
  type AgentCatalogSource, type AgentFormData, type ToolChoice,
} from "../utils/agentSettings.ts";
import { PERMISSION_LABELS } from "./PermissionModeSwitch";
import { AgentAvatar } from "./AgentCard";
import { addToast } from "./Toast";

interface AgentModalProps {
  editingAgent: Agent | null;
  initialData: AgentFormData;
  api: ApiClient;
  onSave: (data: AgentFormData) => Promise<void>;
  onClose: () => void;
  /** Admins may share a new agent with everyone. */
  canShare?: boolean;
  /** Tools the person's agents have, offered in the allow/deny chips. */
  toolCatalog?: string[];
}

type Tab = "basics" | "behaviour" | "tools" | "starters";
type NumberField = "temperature" | "max_steps" | "max_output_tokens";

const EFFORT_LABELS: Record<AgentEffort, string> = {
  low: "Low", medium: "Medium", high: "High", xhigh: "Extra high", max: "Max",
};

const TOOL_LABELS: Record<ToolChoice, string> = { default: "available", allow: "only these", deny: "never" };

const fieldLabel = "text-xs font-medium uppercase tracking-wider text-muted-foreground";
const hint = "mt-1 text-xs text-muted-foreground";

interface ConnectorRow {
  id: string;
  name: string;
  slug?: string;
  enabled?: boolean;
}

interface SkillRow {
  name: string;
  description?: string;
  enabled?: boolean;
}

const numberText = (value: number | null) => (value === null ? "" : String(value));

function tabOf(field: keyof AgentSettings): Tab {
  if (field === "avatar") return "basics";
  if (field === "starter_prompts") return "starters";
  return "behaviour";
}

function PickChip({ pressed, onClick, children, title }: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      title={title}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 max-w-full items-center gap-1 rounded-full border px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        pressed ? "border-primary/60 bg-primary/10 text-foreground" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {pressed && <Check className="size-3 shrink-0 text-brand" />}
      <span className="truncate">{children}</span>
    </button>
  );
}

function ToolChip({ tool, choice, onClick }: { tool: string; choice: ToolChoice; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${tool}: ${TOOL_LABELS[choice]}`}
      title={`${tool}: ${TOOL_LABELS[choice]} (click to change)`}
      className={cn(
        "inline-flex h-7 max-w-full items-center gap-1 rounded-full border px-2.5 font-mono text-xs transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        choice === "allow" && "border-primary/60 bg-primary/10 text-foreground",
        choice === "deny" && "border-destructive/40 bg-destructive/10 text-destructive line-through",
        choice === "default" && "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {choice === "allow" && <Check className="size-3 shrink-0 text-brand" />}
      {choice === "deny" && <Ban className="size-3 shrink-0" />}
      <span className="truncate">{tool}</span>
    </button>
  );
}

export function AgentModal({
  editingAgent,
  initialData,
  api,
  onSave,
  onClose,
  canShare = false,
  toolCatalog = [],
}: AgentModalProps) {
  const [formData, setFormData] = useState<AgentFormData>(() => editingAgent ? agentFormData(editingAgent) : initialData);
  const [numbers, setNumbers] = useState<Record<NumberField, string>>(() => ({
    temperature: numberText(formData.settings.temperature),
    max_steps: numberText(formData.settings.max_steps),
    max_output_tokens: numberText(formData.settings.max_output_tokens),
  }));
  const [tab, setTab] = useState<Tab>("basics");
  const [problem, setProblem] = useState<{ tab: Tab; message: string } | null>(null);
  const [toolFilter, setToolFilter] = useState("");
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
  const revision = useAuth((state) => state.revision);
  const settings = formData.settings;
  const setSettings = (change: Partial<AgentSettings>) =>
    setFormData((previous) => ({ ...previous, settings: { ...previous.settings, ...change } }));

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

  // The person's own MCP servers and skills: an agent may be limited to some of them.
  const connectors = useQuery({
    queryKey: ["agent-builder-connectors", revision],
    staleTime: 60_000,
    retry: false,
    queryFn: async () => ((await api.get("/connectors")).connectors as ConnectorRow[] | undefined) ?? [],
  });
  const skills = useQuery({
    queryKey: ["agent-skills"],
    staleTime: 5 * 60_000,
    retry: false,
    queryFn: async () => ((await api.get("/agent-skills")).skills as SkillRow[] | undefined) ?? [],
  });

  const modelOptions = agentModelOptions({ currentModel: editingAgent?.model ?? "", currentProvider: editingAgent?.provider ?? "",
    selectedModel: formData.model, selectedProvider: formData.provider, catalogProvider: source?.provider ?? "",
    defaultModel: source?.defaultModel, models });
  const claude = isClaudeModel(formData.provider, formData.model || editingAgent?.model || "");
  const tools = agentToolCatalog([{ tools: toolCatalog }, editingAgent ?? {}], settings);
  const filter = toolFilter.trim().toLowerCase();
  const shownTools = filter ? tools.filter((tool) => tool.toLowerCase().includes(filter)) : tools;
  const connectorRows = connectors.data ?? [];
  const skillRows = (skills.data ?? []).filter((skill) => skill.enabled !== false || settings.skills.includes(skill.name));
  const unknownConnectors = settings.connectors.filter((value) => !connectorRows.some((row) => row.id === value || row.slug === value));
  const unknownSkills = settings.skills.filter((value) => !skillRows.some((row) => row.name === value));

  const fail = (where: Tab, message: string) => {
    setProblem({ tab: where, message });
    setTab(where);
    addToast({ type: "error", title: "Check the agent's settings", description: message });
  };

  const handleSave = async () => {
    if (saving || localStorage.getItem("mizan_token") !== ownerToken.current) return;
    if (!formData.name.trim()) return fail("basics", "Give the agent a name.");
    const configured = providers.some((provider) => provider.provider === formData.provider && provider.configured);
    if (!editingAgent && (!formData.model || !configured)) {
      return fail("basics", "Choose a model from a configured provider before creating the agent.");
    }
    const parsed = {} as Record<NumberField, number | null>;
    for (const field of ["temperature", "max_steps", "max_output_tokens"] as const) {
      const { value, valid } = parseSettingNumber(numbers[field]);
      if (!valid) return fail("behaviour", "Use a number, or leave the field empty for the server's default.");
      parsed[field] = value;
    }
    const avatar = settings.avatar?.trim() || null;
    const next: AgentSettings = {
      ...settings, ...parsed, avatar,
      starter_prompts: settings.starter_prompts.map((prompt) => prompt.trim()).filter(Boolean),
    };
    const issue = agentSettingsProblem(next, editingAgent ? agentSettingsFrom(editingAgent.settings) : undefined);
    if (issue) return fail(tabOf(issue.field), issue.message);
    setProblem(null);
    setSaving(true);
    try { await onSave({ ...formData, name: formData.name.trim(), settings: next }); }
    finally { setSaving(false); }
  };

  const starters = settings.starter_prompts;
  const orchestration = settings.orchestration;
  const permission = settings.permission_mode;

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 p-0 sm:max-w-2xl">
        <DialogHeader className="border-b px-4 pb-3 pt-4 pr-12">
          <DialogTitle className="flex items-center gap-2">
            <AgentAvatar agent={{ name: formData.name || "A", settings }} className="size-7 text-xs" />
            {editingAgent ? "Edit agent" : "Create an agent"}
          </DialogTitle>
          <DialogDescription>
            {editingAgent
              ? "Changes apply from the next message sent to this agent."
              : "Give it a name, a model and instructions. Everything else can stay on the server's defaults."}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)} className="flex min-h-0 flex-1 flex-col gap-0">
          <div className="px-4 pt-3">
            <TabsList className="w-full">
              <TabsTrigger value="basics">Basics</TabsTrigger>
              <TabsTrigger value="behaviour">Behaviour</TabsTrigger>
              {/* Short words on a phone; the full name is the tab's name everywhere. */}
              <TabsTrigger value="tools" aria-label="Tools & knowledge">
                <span className="sm:hidden">Tools</span>
                <span className="hidden sm:inline">Tools &amp; knowledge</span>
              </TabsTrigger>
              <TabsTrigger value="starters" aria-label="Starter prompts">
                <span className="sm:hidden">Prompts</span>
                <span className="hidden sm:inline">Starter prompts</span>
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <TabsContent value="basics" className="space-y-4">
              <div className="flex gap-3">
                <div className="w-24 shrink-0">
                  <Label htmlFor="agent-avatar" className={cn(fieldLabel, "mb-1.5")}>Avatar</Label>
                  <Input
                    id="agent-avatar"
                    value={settings.avatar ?? ""}
                    placeholder="🙂"
                    aria-describedby="agent-avatar-hint"
                    onChange={(event) => {
                      const value = Array.from(event.target.value).slice(0, AGENT_AVATAR_MAX).join("");
                      setSettings({ avatar: value ? value : null });
                    }}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <Label htmlFor="agent-name" className={cn(fieldLabel, "mb-1.5")}>Name</Label>
                  <Input
                    id="agent-name"
                    value={formData.name}
                    maxLength={AGENT_NAME_MAX}
                    placeholder="e.g. Research Assistant, Code Helper"
                    aria-invalid={problem?.tab === "basics" && !formData.name.trim() ? true : undefined}
                    onChange={(event) => setFormData({ ...formData, name: event.target.value })}
                    autoFocus
                  />
                </div>
              </div>
              <p id="agent-avatar-hint" className={cn(hint, "-mt-2")}>
                Avatar: an emoji or up to {AGENT_AVATAR_MAX} characters ({textLength(settings.avatar ?? "")}/{AGENT_AVATAR_MAX}).
              </p>

              <div>
                <Label htmlFor="agent-type" className={cn(fieldLabel, "mb-1.5")}>Type</Label>
                <select
                  id="agent-type"
                  className="input w-full"
                  value={formData.type}
                  onChange={(event) => setFormData({ ...formData, type: event.target.value })}
                  disabled={!!editingAgent}
                >
                  {editingAgent ? <option value={formData.type}>{formData.type || "Type not reported"}</option>
                    : AGENT_CREATION_TYPES.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
                </select>
                {editingAgent && <p className={hint}>The type cannot be changed after the agent is created.</p>}
              </div>

              <div>
                <Label htmlFor="agent-provider" className={cn(fieldLabel, "mb-1.5")}>Provider</Label>
                <select id="agent-provider" className="input mb-3 w-full" value={browseProvider || source?.provider || ""}
                  onChange={(event) => { setBrowseProvider(event.target.value); setSource(null); setModels([]); setSearch(""); setQuery(""); setOffset(0); }}>
                  {!browseProvider && !source && <option value="">No provider catalog available</option>}
                  {browseProvider && !providers.some((provider) => provider.provider === browseProvider) && <option value={browseProvider}>{browseProvider} (current)</option>}
                  {providers.map((provider) => <option key={provider.provider} value={provider.provider} disabled={!provider.configured}>
                    {provider.display}{provider.configured ? "" : " (not configured)"}
                  </option>)}
                </select>
                <Label htmlFor="agent-model" className={cn(fieldLabel, "mb-1.5")}>Model</Label>
                <select
                  id="agent-model"
                  className="input w-full"
                  value={agentModelValue(formData.provider, formData.model)}
                  onChange={(event) => {
                    const model = modelOptions.find((option) => option.value === event.target.value);
                    if (model) setFormData({ ...formData, model: model.id, provider: model.provider });
                  }}
                >
                  <option value="" disabled={!!formData.model}>{editingAgent ? "No model reported — keep unchanged" : "Choose a model"}</option>
                  {modelOptions.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}
                </select>
                <p className={cn(hint, "wrap-break-word")}>
                  {editingAgent?.provider ? `Current provider: ${editingAgent.provider}. ` : ""}
                  {source ? `Catalog: ${source.display}. ` : ""}
                  A model changes only when you select one and save.
                </p>
                {source?.provider === "openrouter" && <div className="mt-2 flex gap-2">
                  <Input className="min-w-0 flex-1" aria-label="Search model catalog" placeholder="Search model IDs or names"
                    value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => {
                      if (event.key === "Enter") { event.preventDefault(); setOffset(0); setQuery(search); }
                    }} />
                  <Button type="button" variant="outline" disabled={catalogLoading}
                    onClick={() => { setOffset(0); setQuery(search); }}>Search</Button>
                </div>}
                <div aria-live="polite">
                  {catalogLoading && <p className={hint}>Loading models…</p>}
                  {catalogError && <p className={cn(hint, "flex items-start gap-1.5")}>
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" /> {catalogError}
                  </p>}
                  {!catalogLoading && !catalogError && models.length === 0 && <p className={hint}>
                    No matching catalog models were returned. The current selection is unchanged.
                  </p>}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <Button type="button" variant="outline" size="sm" disabled={catalogLoading} onClick={() => setRefresh((value) => value + 1)}>Reload models</Button>
                  {source?.provider === "openrouter" && total > 50 && <>
                    <span>{offset + 1}–{Math.min(offset + 50, total)} of {total}</span>
                    <Button type="button" variant="outline" size="sm" disabled={catalogLoading || offset === 0} onClick={() => setOffset((value) => Math.max(0, value - 50))}>Previous</Button>
                    <Button type="button" variant="outline" size="sm" disabled={catalogLoading || offset + 50 >= total} onClick={() => setOffset((value) => value + 50)}>Next</Button>
                  </>}
                </div>
                {editingAgent?.provider_warning && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
                    <span className="min-w-0 wrap-break-word">{editingAgent.provider_warning}</span>
                  </p>
                )}
              </div>

              <div>
                <Label htmlFor="agent-prompt" className={cn(fieldLabel, "mb-1.5")}>
                  Instructions <span className="font-normal normal-case tracking-normal">(persona, optional)</span>
                </Label>
                <Textarea
                  id="agent-prompt"
                  className="min-h-32 resize-y"
                  rows={6}
                  maxLength={AGENT_PROMPT_MAX}
                  placeholder="Who this agent is and how it should answer: its role, tone, what to always or never do."
                  value={formData.system_prompt}
                  onChange={(event) => setFormData({ ...formData, system_prompt: event.target.value })}
                />
                <p className={cn(hint, "flex justify-between gap-3")}>
                  <span>Added to MIZAN's own instructions, which always apply.</span>
                  <span className="shrink-0 tabular-nums">
                    {formData.system_prompt.length.toLocaleString()} / {AGENT_PROMPT_MAX.toLocaleString()}
                  </span>
                </p>
              </div>

              {canShare && !editingAgent && (
                <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
                  <span className="min-w-0">
                    <Label htmlFor="agent-shared" className="text-sm">Share with everyone on this server</Label>
                    <span className={cn(hint, "block")}>Off: only you see it. On: every signed-in person can chat with it.</span>
                  </span>
                  <Switch id="agent-shared" checked={formData.shared}
                    onCheckedChange={(checked) => setFormData({ ...formData, shared: checked })} />
                </div>
              )}
              {editingAgent && editingAgent.shared !== undefined && (
                <p className={hint}>
                  <Badge variant="outline">{editingAgent.shared ? "Shared" : "Private"}</Badge>{" "}
                  {editingAgent.shared ? "Everyone on this server can chat with it." : "Only you can see it."}
                </p>
              )}
            </TabsContent>

            <TabsContent value="behaviour" className="space-y-4">
              <div>
                <Label htmlFor="agent-orchestration" className={cn(fieldLabel, "mb-1.5")}>Who directs the work</Label>
                <select
                  id="agent-orchestration"
                  className="input w-full"
                  value={orchestration ?? ""}
                  onChange={(event) => setSettings({ orchestration: (event.target.value || null) as AgentOrchestration | null })}
                >
                  <option value="">Server default</option>
                  {AGENT_ORCHESTRATIONS.map((value) => <option key={value} value={value}>{ORCHESTRATION_LABELS[value].title}</option>)}
                </select>
                <p className={hint}>
                  {orchestration ? ORCHESTRATION_LABELS[orchestration].hint : "Follows the server's orchestration setting (MIZAN_ORCHESTRATION)."}
                </p>
              </div>

              <div>
                <Label htmlFor="agent-permission" className={cn(fieldLabel, "mb-1.5")}>What it may do without asking</Label>
                <select
                  id="agent-permission"
                  className="input w-full"
                  value={permission ?? ""}
                  onChange={(event) => setSettings({ permission_mode: (event.target.value || null) as PermissionMode | null })}
                >
                  <option value="">Server default</option>
                  {PERMISSION_MODES.map((value) => <option key={value} value={value}>{PERMISSION_LABELS[value].title}</option>)}
                </select>
                <p className={hint}>
                  {permission ? `${PERMISSION_LABELS[permission].hint}. ` : ""}
                  A new chat with this agent starts in this mode; the person can still change it in the chat.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="agent-effort" className={cn(fieldLabel, "mb-1.5")}>Effort</Label>
                  <select
                    id="agent-effort"
                    className="input w-full"
                    value={settings.effort ?? ""}
                    onChange={(event) => setSettings({ effort: (event.target.value || null) as AgentEffort | null })}
                  >
                    <option value="">Server default</option>
                    {AGENT_EFFORTS.map((value) => <option key={value} value={value}>{EFFORT_LABELS[value]}</option>)}
                  </select>
                  <p className={hint}>How hard the model thinks before it answers.</p>
                </div>
                <div>
                  <Label htmlFor="agent-temperature" className={cn(fieldLabel, "mb-1.5")}>Temperature</Label>
                  <Input
                    id="agent-temperature"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    max={TEMPERATURE_MAX}
                    step={0.05}
                    placeholder="Server default"
                    disabled={claude}
                    value={numbers.temperature}
                    onChange={(event) => setNumbers({ ...numbers, temperature: event.target.value })}
                  />
                  <p className={hint}>
                    {claude
                      ? "Claude models set their own sampling, so no temperature is sent to them: use Effort instead."
                      : `0 is steady, ${TEMPERATURE_MAX} is varied. Empty: the server's default.`}
                  </p>
                </div>
                <div>
                  <Label htmlFor="agent-max-steps" className={cn(fieldLabel, "mb-1.5")}>Max steps</Label>
                  <Input
                    id="agent-max-steps"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={MAX_STEPS_MAX}
                    step={1}
                    placeholder="Server default"
                    value={numbers.max_steps}
                    onChange={(event) => setNumbers({ ...numbers, max_steps: event.target.value })}
                  />
                  <p className={hint}>Tool steps per message before it stops and reports.</p>
                </div>
                <div>
                  <Label htmlFor="agent-max-tokens" className={cn(fieldLabel, "mb-1.5")}>Max output tokens</Label>
                  <Input
                    id="agent-max-tokens"
                    type="number"
                    inputMode="numeric"
                    min={MAX_OUTPUT_TOKENS_MIN}
                    max={MAX_OUTPUT_TOKENS_MAX}
                    step={1}
                    placeholder="Server default"
                    value={numbers.max_output_tokens}
                    onChange={(event) => setNumbers({ ...numbers, max_output_tokens: event.target.value })}
                  />
                  <p className={hint}>
                    The longest answer the model may write ({MAX_OUTPUT_TOKENS_MIN}–{MAX_OUTPUT_TOKENS_MAX.toLocaleString()}).
                  </p>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="tools" className="space-y-5">
              <section aria-labelledby="agent-tools-heading">
                <h4 id="agent-tools-heading" className={fieldLabel}>Tools</h4>
                <p className={hint}>
                  Click a tool to cycle it: <Check className="inline size-3 text-brand" /> only the ticked tools,{" "}
                  <Ban className="inline size-3 text-destructive" /> never, or back to available. Nothing ticked: every permitted tool.
                </p>
                <p className="mt-1 text-xs font-medium">
                  {settings.tools_allow.length
                    ? `Only ${settings.tools_allow.length} tool${settings.tools_allow.length === 1 ? "" : "s"}`
                    : "Every permitted tool"}
                  {settings.tools_deny.length ? `, never ${settings.tools_deny.length}` : ""}
                </p>
                {tools.length > 12 && (
                  <Input className="mt-2" aria-label="Filter tools" placeholder="Filter tools"
                    value={toolFilter} onChange={(event) => setToolFilter(event.target.value)} />
                )}
                <div className="mt-2 flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
                  {shownTools.map((tool) => (
                    <ToolChip key={tool} tool={tool} choice={toolChoice(settings, tool)}
                      onClick={() => setFormData((previous) => ({ ...previous, settings: cycleTool(previous.settings, tool) }))} />
                  ))}
                  {tools.length === 0 && <p className={hint}>The server listed no tools for this agent yet.</p>}
                  {tools.length > 0 && shownTools.length === 0 && <p className={hint}>No tool matches.</p>}
                </div>
              </section>

              <section aria-labelledby="agent-connectors-heading">
                <h4 id="agent-connectors-heading" className={fieldLabel}>Connectors</h4>
                <p className={hint}>Your MCP servers this agent may use. None picked: all of them.</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {connectors.isLoading && <p className={hint}>Loading your connectors…</p>}
                  {connectors.isError && <p className={hint}>Could not load your connectors.</p>}
                  {connectorRows.map((row) => {
                    // Saved by the server name its tools carry (mcp__<slug>__<tool>).
                    const key = row.slug || row.id;
                    const pressed = settings.connectors.includes(key) || settings.connectors.includes(row.id);
                    return (
                      <PickChip key={row.id} pressed={pressed}
                        onClick={() => setSettings({
                          connectors: pressed
                            ? settings.connectors.filter((value) => value !== row.id && value !== key)
                            : [...settings.connectors, key],
                        })}>
                        {row.name}{row.enabled === false ? " (off)" : ""}
                      </PickChip>
                    );
                  })}
                  {unknownConnectors.map((value) => (
                    <PickChip key={value} pressed title="No longer in your connectors: click to remove"
                      onClick={() => setSettings({ connectors: settings.connectors.filter((item) => item !== value) })}>
                      {value} (missing)
                    </PickChip>
                  ))}
                  {connectors.isSuccess && connectorRows.length === 0 && (
                    <p className={hint}>
                      No connectors yet. <Link to="/settings/connectors" className="font-medium text-brand hover:underline">Add one</Link>.
                    </p>
                  )}
                </div>
              </section>

              <section aria-labelledby="agent-skills-heading">
                <h4 id="agent-skills-heading" className={fieldLabel}>Skills</h4>
                <p className={hint}>Skills this agent may use. None picked: all of them.</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {skills.isLoading && <p className={hint}>Loading skills…</p>}
                  {skills.isError && <p className={hint}>Could not load skills.</p>}
                  {skillRows.map((skill) => (
                    <PickChip key={skill.name} pressed={settings.skills.includes(skill.name)} title={skill.description}
                      onClick={() => setSettings({ skills: toggled(settings.skills, skill.name) })}>
                      {skill.name}
                    </PickChip>
                  ))}
                  {unknownSkills.map((value) => (
                    <PickChip key={value} pressed title="No longer installed: click to remove"
                      onClick={() => setSettings({ skills: settings.skills.filter((item) => item !== value) })}>
                      {value} (missing)
                    </PickChip>
                  ))}
                  {skills.isSuccess && skillRows.length === 0 && (
                    <p className={hint}>
                      No skills installed. <Link to="/settings/skills" className="font-medium text-brand hover:underline">Browse skills</Link>.
                    </p>
                  )}
                </div>
              </section>

              <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
                <span className="min-w-0">
                  <Label htmlFor="agent-learn-skills" className="text-sm">Let this agent save what it learns as skills</Label>
                  <span className={cn(hint, "block")}>A way of working that succeeded can be kept as a skill and reused later.</span>
                </span>
                <Switch id="agent-learn-skills" checked={settings.learn_skills}
                  onCheckedChange={(checked) => setSettings({ learn_skills: checked })} />
              </div>
            </TabsContent>

            <TabsContent value="starters" className="space-y-3">
              <p className={hint}>
                Shown as one-tap prompts when someone opens a new chat with this agent (up to {STARTER_PROMPTS_MAX}).
              </p>
              {starters.map((prompt, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Input
                    aria-label={`Starter prompt ${index + 1}`}
                    value={prompt}
                    maxLength={STARTER_PROMPT_MAX}
                    placeholder="e.g. Summarise today's news on my topics"
                    onChange={(event) => setSettings({
                      starter_prompts: starters.map((item, at) => (at === index ? event.target.value : item)),
                    })}
                  />
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove starter prompt ${index + 1}`}
                    onClick={() => setSettings({ starter_prompts: starters.filter((_, at) => at !== index) })}>
                    <X />
                  </Button>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" disabled={starters.length >= STARTER_PROMPTS_MAX}
                onClick={() => setSettings({ starter_prompts: [...starters, ""] })}>
                <Plus /> Add starter prompt
              </Button>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter className="mx-0 mb-0 items-center">
          {problem && <p role="alert" className="mr-auto text-xs text-destructive">{problem.message}</p>}
          <Button type="button" variant="outline" disabled={saving} onClick={onClose}>Cancel</Button>
          <Button type="button" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Saving…" : editingAgent ? "Save changes" : "Create agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
