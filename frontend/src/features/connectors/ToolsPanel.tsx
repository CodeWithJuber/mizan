/**
 * What a connector offers: its tools (with a policy each, held tools to
 * check, new ones marked once), its resources and its prompts.
 */
import { useEffect, useRef, useState } from "react";
import { FileText, MessageSquareText, Search, ShieldAlert, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { addToast } from "../../components/Toast";
import { type ConnectorActions, usePrompts, useResources } from "./api";
import { SELECT_CLASS } from "./ConnectorForm";
import { stableJson } from "./diff";
import { ToneBadge } from "./parts";
import { ToolChange } from "./ToolChange";
import type { Connector, ConnectorTool, HeldReason, ToolPolicy } from "./types";

const POLICY_LABEL: Record<ToolPolicy, string> = { allow: "Allow", ask: "Ask first", never: "Never" };

const HELD_TEXT: Record<HeldReason | "unknown", string> = {
  new: "This tool is new since you accepted this connector's tools, so the agent can't use it until you allow it.",
  changed: "This tool changed since you accepted it, so the agent can't use it until you check what changed.",
  poisoned: "Amanah found instructions aimed at the AI in this tool's description. Trust it only if you know why they are there.",
  unknown: "Amanah is holding this tool until you check it.",
};

const plain = (description: string) => description.replace(/^\[[^\]]+\]\s*/, "");

function ToolRow({ tool, isNew, connector, actions }: {
  tool: ConnectorTool; isNew: boolean; connector: Connector; actions: ConnectorActions;
}) {
  const [busy, setBusy] = useState(false);
  const policyId = `policy-${connector.id}-${tool.name}`;
  const schema = stableJson(tool.input_schema);
  const run = async (work: () => Promise<unknown>, failure: string, success?: string) => {
    setBusy(true);
    try {
      await work();
      if (success) addToast({ type: "success", title: success });
    } catch (problem) {
      addToast({ type: "error", title: failure, description: problem instanceof Error ? problem.message : undefined });
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="flex flex-wrap items-center gap-1.5">
            <span className="break-all font-mono text-xs font-medium">{tool.name}</span>
            {isNew && <ToneBadge tone="info">New</ToneBadge>}
            {tool.held && <ToneBadge tone="warning">Held</ToneBadge>}
            {tool.read_only && <ToneBadge tone="muted">Read-only</ToneBadge>}
            {tool.destructive && <ToneBadge tone="destructive">Destructive</ToneBadge>}
          </p>
          {tool.description && <p className="line-clamp-2 text-xs text-muted-foreground">{plain(tool.description)}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <label htmlFor={policyId} className="text-xs text-muted-foreground">
            Policy<span className="sr-only"> for {tool.name}</span>
          </label>
          <select
            id={policyId}
            className={`${SELECT_CLASS} w-32`}
            value={tool.policy}
            disabled={busy || tool.held}
            title={tool.held ? "Check and trust the tool first" : undefined}
            onChange={(event) => {
              const policy = event.target.value as ToolPolicy;
              void run(() => actions.policy(connector, tool.name, policy), `Could not change ${tool.name}`);
            }}
          >
            {(Object.keys(POLICY_LABEL) as ToolPolicy[]).map((value) => (
              <option key={value} value={value}>{POLICY_LABEL[value]}</option>
            ))}
          </select>
        </div>
      </div>

      {tool.held && (
        <div className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-2.5 text-xs">
          <p className="flex items-start gap-1.5">
            <ShieldAlert className="mt-px size-3.5 shrink-0 text-brand" aria-hidden />
            <span>{HELD_TEXT[tool.held_reason ?? "unknown"]}</span>
          </p>
          {tool.amanah.map((excerpt) => (
            <p key={excerpt} className="break-all font-mono">“{excerpt}”</p>
          ))}
          <ToolChange tool={tool} />
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void run(
              () => actions.trust(connector, tool.name),
              `Could not trust ${tool.name}`,
              `${tool.name} is available to the agent`,
            )}
          >
            {tool.held_reason === "new" ? "Allow this tool" : "Trust it as it is now"}
          </Button>
        </div>
      )}

      {(schema || tool.description.length > 120) && (
        <details className="text-xs">
          <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">Details and input schema</summary>
          <div className="mt-2 space-y-2">
            {tool.description && <p className="whitespace-pre-wrap break-words">{plain(tool.description)}</p>}
            {tool.exposed && <p className="text-muted-foreground">The agent calls it as <code className="code break-all">{tool.exposed}</code></p>}
            {schema && (
              <pre className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-xs">{schema}</pre>
            )}
          </div>
        </details>
      )}
    </li>
  );
}

function Resources({ connector, active }: { connector: Connector; active: boolean }) {
  const connected = connector.status === "connected";
  const { data, isLoading, error } = useResources(connector.id, active && connected);
  if (!connected) return <p className="text-xs text-muted-foreground">Connect to see the resources this server shares.</p>;
  if (isLoading) return <p className="text-xs text-muted-foreground">Loading resources…</p>;
  if (error) return <p className="text-xs text-destructive">Could not load resources: {error.message}</p>;
  if (!data?.length) return <p className="text-xs text-muted-foreground">This server shares no resources.</p>;
  return (
    <ul className="space-y-2">
      {data.map((resource) => (
        <li key={resource.uri} className="space-y-1 rounded-lg border p-3">
          <p className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium">{resource.name}</span>
            {resource.mime_type && <ToneBadge tone="muted">{resource.mime_type}</ToneBadge>}
          </p>
          <p className="break-all font-mono text-xs text-muted-foreground">{resource.uri}</p>
          {resource.description && <p className="text-xs text-muted-foreground">{resource.description}</p>}
        </li>
      ))}
    </ul>
  );
}

function Prompts({ connector, active }: { connector: Connector; active: boolean }) {
  const connected = connector.status === "connected";
  const { data, isLoading, error } = usePrompts(connector.id, active && connected);
  if (!connected) return <p className="text-xs text-muted-foreground">Connect to see the prompts this server offers.</p>;
  if (isLoading) return <p className="text-xs text-muted-foreground">Loading prompts…</p>;
  if (error) return <p className="text-xs text-destructive">Could not load prompts: {error.message}</p>;
  if (!data?.length) return <p className="text-xs text-muted-foreground">This server offers no prompts.</p>;
  return (
    <ul className="space-y-2">
      {data.map((prompt) => (
        <li key={prompt.name} className="space-y-1 rounded-lg border p-3">
          <p className="font-mono text-xs font-medium">{prompt.name}</p>
          {prompt.description && <p className="text-xs text-muted-foreground">{prompt.description}</p>}
          {prompt.arguments.length > 0 && (
            <ul className="mt-1 space-y-0.5 text-xs">
              {prompt.arguments.map((arg) => (
                <li key={arg.name}>
                  <code className="code">{arg.name}</code>
                  {arg.required && <span className="ml-1 text-muted-foreground">(required)</span>}
                  {arg.description && <span className="text-muted-foreground"> · {arg.description}</span>}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ToolsPanel({ connector, actions }: { connector: Connector; actions: ConnectorActions }) {
  const [tab, setTab] = useState<string>("tools");
  const [filter, setFilter] = useState("");
  // What was new when the panel opened keeps its badge while it stays open; the server is told it was seen.
  const [seenNew] = useState(() => new Set(connector.tools.filter((tool) => tool.new).map((tool) => tool.name)));
  const acknowledged = useRef(false);
  useEffect(() => {
    if (acknowledged.current || seenNew.size === 0) return;
    acknowledged.current = true;
    actions.ack(connector, [...seenNew]).catch(() => {
      acknowledged.current = false;
    });
  }, [actions, connector, seenNew]);

  const query = filter.trim().toLowerCase();
  const rank = (tool: ConnectorTool) => (tool.held ? 0 : seenNew.has(tool.name) ? 1 : 2);
  const tools = connector.tools
    .filter((tool) => !query || tool.name.toLowerCase().includes(query) || tool.description.toLowerCase().includes(query))
    .map((tool, index) => ({ tool, index }))
    .sort((a, b) => rank(a.tool) - rank(b.tool) || a.index - b.index)
    .map(({ tool }) => tool);
  const { counts } = connector;

  return (
    <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="gap-3">
      <TabsList aria-label={`What ${connector.name} offers`} className="max-w-full overflow-x-auto">
        <TabsTrigger value="tools"><Wrench aria-hidden /> Tools ({counts.total})</TabsTrigger>
        <TabsTrigger value="resources"><FileText aria-hidden /> Resources</TabsTrigger>
        <TabsTrigger value="prompts"><MessageSquareText aria-hidden /> Prompts</TabsTrigger>
      </TabsList>
      <TabsContent value="tools" className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {counts.enabled} of {counts.total} usable
          {counts.held > 0 && ` · ${counts.held} held for you to check`}
          {seenNew.size > 0 && ` · ${seenNew.size} new`}
          . Ask first makes the agent wait for your approval before each call.
        </p>
        {connector.tools.length > 8 && (
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              aria-label={`Filter ${connector.name} tools`}
              placeholder="Filter tools"
              className="pl-8"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />
          </div>
        )}
        {connector.tools.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {connector.status === "connected" ? "This server offers no tools." : "Connect to load its tools."}
          </p>
        ) : tools.length === 0 ? (
          <p className="text-xs text-muted-foreground">No tool matches “{filter}”.</p>
        ) : (
          <ul className="space-y-2">
            {tools.map((tool) => (
              <ToolRow key={tool.name} tool={tool} isNew={seenNew.has(tool.name)} connector={connector} actions={actions} />
            ))}
          </ul>
        )}
      </TabsContent>
      <TabsContent value="resources">
        <Resources connector={connector} active={tab === "resources"} />
      </TabsContent>
      <TabsContent value="prompts">
        <Prompts connector={connector} active={tab === "prompts"} />
      </TabsContent>
    </Tabs>
  );
}
