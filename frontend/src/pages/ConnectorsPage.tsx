/**
 * Connectors (Wasl - وَصْل - connection): MCP servers the agent can use.
 * Browse the official MCP Registry, add remote (OAuth or headers) or local
 * servers, connect, and choose which of their tools the agent may call.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ExternalLink, Plug, PlugZap, Plus, Power, RefreshCw, Search, ShieldCheck, Trash2,
} from "lucide-react";
import type { PageProps } from "../types";
import { useToast } from "../components/Toast";

interface ConnectorTool {
  name: string;
  exposed: string;
  description: string;
  read_only: boolean;
  destructive: boolean;
  enabled: boolean;
  /** Amanah holds a tool whose description changed since you accepted it, or that instructs the AI. */
  held?: "changed" | "flagged";
  amanah?: string[];
}

interface Connector {
  id: string;
  name: string;
  slug: string;
  transport: "http" | "stdio";
  url: string;
  command: string;
  args: string[];
  runtime: string;
  enabled: boolean;
  disabled_tools: string[];
  status: string;
  last_error: string;
  source: string;
  header_names: string[];
  env_names: string[];
  oauth_connected: boolean;
  tools: ConnectorTool[];
}

interface RegistryField { name: string; description: string; required: boolean; secret: boolean }
interface RegistryServer {
  name: string;
  title: string;
  description: string;
  version: string;
  repository: string;
  remotes: { type: string; url: string; headers: RegistryField[] }[];
  packages: { registry: string; identifier: string; version: string; runtime: string; env: RegistryField[] }[];
}

interface Draft {
  name: string;
  transport: "http" | "stdio";
  url: string;
  command: string;
  args: string;
  source: string;
  secrets: { key: string; value: string; secret: boolean; description?: string }[];
}

const emptyDraft = (): Draft => ({ name: "", transport: "http", url: "", command: "", args: "", source: "", secrets: [] });

const STATUS_STYLE: Record<string, string> = {
  connected: "badge-success",
  auth_required: "badge-warning",
  error: "badge-error",
  disconnected: "badge-info",
  new: "badge-info",
};

/** Split an argument line like a shell would for simple quoting. */
export function splitArgs(line: string): string[] {
  const args: string[] = [];
  const pattern = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(line)) !== null) args.push(match[1] ?? match[2] ?? match[3]);
  return args;
}

export default function ConnectorsPage({ api }: PageProps) {
  const { addToast } = useToast();
  const [tab, setTab] = useState<"mine" | "browse" | "add">("mine");
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [hostStdio, setHostStdio] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string>("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RegistryServer[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const polls = useRef<Record<string, number>>({});

  const load = useCallback(async () => {
    try {
      const data = await api.get("/connectors");
      setConnectors((data.connectors as Connector[]) ?? []);
      setHostStdio(Boolean((data.capabilities as Record<string, unknown> | undefined)?.host_stdio));
    } catch (error) {
      addToast({ type: "error", title: "Connectors unavailable", description: (error as Error).message });
    } finally {
      setLoading(false);
    }
  }, [api, addToast]);

  useEffect(() => {
    void load();
    const timers = polls.current;
    return () => Object.values(timers).forEach((timer) => window.clearInterval(timer));
  }, [load]);

  const search = useCallback(async (cursor = "") => {
    setSearching(true);
    try {
      const params = new URLSearchParams({ search: query, limit: "30", ...(cursor ? { cursor } : {}) });
      const data = await api.get(`/connectors/registry?${params}`);
      const servers = (data.servers as RegistryServer[]) ?? [];
      setResults((previous) => cursor ? [...previous, ...servers] : servers);
      setNextCursor((data.next_cursor as string) || null);
    } catch (error) {
      addToast({ type: "error", title: "Registry unavailable", description: (error as Error).message });
    } finally {
      setSearching(false);
    }
  }, [api, query, addToast]);

  useEffect(() => {
    if (tab === "browse" && results.length === 0) void search();
  }, [tab, results.length, search]);

  const pollUntilConnected = (id: string) => {
    window.clearInterval(polls.current[id]);
    let attempts = 0;
    polls.current[id] = window.setInterval(async () => {
      attempts += 1;
      try {
        const server = (await api.get(`/connectors/${id}`)) as unknown as Connector;
        setConnectors((list) => list.map((item) => item.id === id ? server : item));
        if (server.status === "connected" || attempts > 90) {
          window.clearInterval(polls.current[id]);
          if (server.status === "connected") addToast({ type: "success", title: `${server.name} connected` });
        }
      } catch {
        window.clearInterval(polls.current[id]);
      }
    }, 2000);
  };

  const connect = async (connector: Connector) => {
    setBusy(connector.id);
    try {
      const data = await api.post(`/connectors/${connector.id}/connect`);
      if (data.status === "authorization_required" && typeof data.authorization_url === "string") {
        window.open(data.authorization_url, "_blank", "noopener,noreferrer");
        addToast({ type: "info", title: "Authorize in the new window", description: "This page updates when you are done." });
        pollUntilConnected(connector.id);
      } else if (data.status === "connected") {
        addToast({ type: "success", title: `${connector.name} connected` });
      } else {
        pollUntilConnected(connector.id);
      }
      const updated = data.connector as Connector | undefined;
      if (updated?.id) setConnectors((list) => list.map((item) => item.id === updated.id ? updated : item));
    } catch (error) {
      addToast({ type: "error", title: `Could not connect ${connector.name}`, description: (error as Error).message });
      await load();
    } finally {
      setBusy("");
    }
  };

  const update = async (connector: Connector, changes: Record<string, unknown>) => {
    setBusy(connector.id);
    try {
      const updated = (await api.patch(`/connectors/${connector.id}`, changes)) as unknown as Connector;
      setConnectors((list) => list.map((item) => item.id === connector.id ? updated : item));
    } catch (error) {
      addToast({ type: "error", title: "Update failed", description: (error as Error).message });
    } finally {
      setBusy("");
    }
  };

  const remove = async (connector: Connector) => {
    if (!window.confirm(`Remove ${connector.name}? Its saved credentials are deleted too.`)) return;
    try {
      await api.del(`/connectors/${connector.id}`);
      setConnectors((list) => list.filter((item) => item.id !== connector.id));
    } catch (error) {
      addToast({ type: "error", title: "Remove failed", description: (error as Error).message });
    }
  };

  const toggleTool = (connector: Connector, tool: ConnectorTool) => {
    const disabled = new Set(connector.disabled_tools);
    if (tool.enabled) disabled.add(tool.name); else disabled.delete(tool.name);
    void update(connector, { disabled_tools: [...disabled] });
  };

  const trustTool = async (connector: Connector, tool: ConnectorTool) => {
    try {
      const updated = (await api.post(
        `/connectors/${connector.id}/tools/${encodeURIComponent(tool.name)}/trust`,
        {},
      )) as unknown as Connector;
      setConnectors((list) => list.map((item) => item.id === connector.id ? updated : item));
      addToast({ type: "success", title: `${tool.name} is available to the agent again` });
    } catch (error) {
      addToast({ type: "error", title: "Could not trust the tool", description: (error as Error).message });
    }
  };

  const addFromRemote = (server: RegistryServer, remote: RegistryServer["remotes"][number]) => {
    setDraft({
      name: (server.title || server.name).split("/").pop() || server.name,
      transport: "http",
      url: remote.url,
      command: "",
      args: "",
      source: server.name,
      secrets: remote.headers.map((h) => ({ key: h.name, value: "", secret: h.secret, description: h.description })),
    });
    setTab("add");
  };

  const addFromPackage = (server: RegistryServer, pkg: RegistryServer["packages"][number]) => {
    const npm = pkg.registry === "npm";
    const spec = pkg.version ? (npm ? `${pkg.identifier}@${pkg.version}` : `${pkg.identifier}==${pkg.version}`) : pkg.identifier;
    setDraft({
      name: (server.title || server.name).split("/").pop() || server.name,
      transport: "stdio",
      url: "",
      command: pkg.runtime || (npm ? "npx" : "uvx"),
      args: npm ? `-y ${spec}` : spec,
      source: server.name,
      secrets: pkg.env.map((e) => ({ key: e.name, value: "", secret: e.secret, description: e.description })),
    });
    setTab("add");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const secrets = Object.fromEntries(draft.secrets.filter((s) => s.key.trim()).map((s) => [s.key.trim(), s.value]));
    const body: Record<string, unknown> = { name: draft.name.trim(), transport: draft.transport, source: draft.source };
    if (draft.transport === "http") Object.assign(body, { url: draft.url.trim(), headers: secrets });
    else Object.assign(body, { command: draft.command.trim(), args: splitArgs(draft.args), env: secrets });
    setBusy("add");
    try {
      const created = (await api.post("/connectors", body)) as unknown as Connector;
      setConnectors((list) => [...list, created]);
      setDraft(emptyDraft());
      setTab("mine");
      addToast({ type: "success", title: `${created.name} added`, description: "Press Connect to load its tools." });
    } catch (error) {
      addToast({ type: "error", title: "Could not add connector", description: (error as Error).message });
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-5xl mx-auto space-y-5">
        <header>
          <h1 className="page-title flex items-center gap-2"><Plug className="w-6 h-6 text-mizan-gold" /> Connectors</h1>
          <p className="page-description">
            Connect MCP servers (GitHub, Notion, databases, search…). Their tools join your agent and
            still pass permission checks and your approval mode.
          </p>
        </header>

        <div className="tab-bar" role="tablist">
          {(["mine", "browse", "add"] as const).map((value) => (
            <button key={value} role="tab" aria-selected={tab === value} className={`tab ${tab === value ? "active" : ""}`} onClick={() => setTab(value)}>
              {value === "mine" ? `My connectors (${connectors.length})` : value === "browse" ? "Browse registry" : "Add custom"}
            </button>
          ))}
        </div>

        {tab === "mine" && (
          <section className="space-y-3">
            {loading && <p className="text-sm text-gray-500">Loading…</p>}
            {!loading && connectors.length === 0 && (
              <div className="card text-center py-10">
                <PlugZap className="w-8 h-8 mx-auto text-mizan-gold" />
                <p className="mt-2 font-medium">No connectors yet</p>
                <p className="text-sm text-gray-500">Browse the MCP Registry or add a server URL.</p>
                <button className="btn-gold mt-4" onClick={() => setTab("browse")}>Browse registry</button>
              </div>
            )}
            {connectors.map((connector) => (
              <article key={connector.id} className="card space-y-3">
                <div className="flex flex-wrap items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="font-semibold text-gray-900 dark:text-zinc-100">{connector.name}</h2>
                      <span className={STATUS_STYLE[connector.status] ?? "badge-info"}>{connector.status.replace("_", " ")}</span>
                      <span className="badge-gold">{connector.transport === "http" ? "remote" : `local · ${connector.runtime}`}</span>
                      {connector.oauth_connected && <span className="badge-success inline-flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> OAuth</span>}
                    </div>
                    <p className="text-xs font-mono text-gray-500 break-all mt-1">
                      {connector.transport === "http" ? connector.url : `${connector.command} ${connector.args.join(" ")}`}
                    </p>
                    {connector.last_error && connector.status !== "connected" && (
                      <p className="text-xs text-rose-600 mt-1">{connector.last_error}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn-primary btn-sm inline-flex items-center gap-1" disabled={busy === connector.id || !connector.enabled} onClick={() => connect(connector)}>
                      <RefreshCw className={`w-3.5 h-3.5 ${busy === connector.id ? "animate-spin" : ""}`} />
                      {connector.status === "connected" ? "Reconnect" : "Connect"}
                    </button>
                    <button className="btn-secondary btn-sm inline-flex items-center gap-1" disabled={busy === connector.id} onClick={() => update(connector, { enabled: !connector.enabled })}>
                      <Power className="w-3.5 h-3.5" /> {connector.enabled ? "Disable" : "Enable"}
                    </button>
                    <button className="btn-danger btn-sm inline-flex items-center gap-1" onClick={() => remove(connector)} aria-label={`Remove ${connector.name}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                {connector.tools.length > 0 && (
                  <details>
                    <summary className="text-sm cursor-pointer text-gray-600 dark:text-zinc-400">
                      {connector.tools.filter((t) => t.enabled).length}/{connector.tools.length} tools enabled
                    </summary>
                    <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                      {connector.tools.map((tool) => (
                        <li key={tool.name} className="flex items-start gap-2 rounded-md border border-gray-100 dark:border-zinc-800 p-2">
                          <input type="checkbox" className="mt-1" checked={tool.enabled} onChange={() => toggleTool(connector, tool)} aria-label={`Enable ${tool.name}`} />
                          <div className="min-w-0">
                            <p className="text-xs font-mono font-medium break-all">
                              {tool.name}
                              {tool.read_only && <span className="ml-1 badge-info">read-only</span>}
                              {tool.destructive && <span className="ml-1 badge-error">destructive</span>}
                              {tool.held && <span className="ml-1 badge-warning">held</span>}
                            </p>
                            <p className="text-xs text-gray-500 line-clamp-2">{tool.description.replace(/^\[[^\]]+\]\s*/, "")}</p>
                            {tool.held && (
                              <div className="mt-1 rounded-md bg-amber-50 dark:bg-amber-950/30 p-1.5 text-xs text-amber-800 dark:text-amber-300">
                                <p>
                                  {tool.held === "changed"
                                    ? "Amanah: this tool's description changed since you accepted it, so the agent cannot use it until you check it."
                                    : "Amanah: this tool's description contains instructions aimed at the AI, so the agent cannot use it until you check it."}
                                </p>
                                {tool.amanah?.map((excerpt) => (
                                  <p key={excerpt} className="mt-0.5 font-mono break-all">“{excerpt}”</p>
                                ))}
                                <button type="button" className="btn-secondary btn-sm mt-1" onClick={() => void trustTool(connector, tool)}>
                                  Trust as it is now
                                </button>
                              </div>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </article>
            ))}
          </section>
        )}

        {tab === "browse" && (
          <section className="space-y-3">
            <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); void search(); }}>
              <input className="input flex-1" placeholder="Search MCP servers (github, notion, postgres, search…)" value={query} onChange={(event) => setQuery(event.target.value)} />
              <button className="btn-primary inline-flex items-center gap-1" disabled={searching}><Search className="w-4 h-4" /> Search</button>
            </form>
            <div className="grid gap-3 md:grid-cols-2">
              {results.map((server) => (
                <article key={`${server.name}@${server.version}`} className="card space-y-2">
                  <div>
                    <h3 className="font-semibold break-all">{server.title || server.name}</h3>
                    <p className="text-xs font-mono text-gray-500 break-all">{server.name}{server.version && ` · v${server.version}`}</p>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-zinc-400 line-clamp-3">{server.description}</p>
                  <div className="flex flex-wrap gap-2">
                    {server.remotes.slice(0, 2).map((remote) => (
                      <button key={remote.url} className="btn-gold btn-sm" onClick={() => addFromRemote(server, remote)}>Add remote</button>
                    ))}
                    {server.packages.slice(0, 2).map((pkg) => (
                      <button key={`${pkg.registry}:${pkg.identifier}`} className="btn-secondary btn-sm" onClick={() => addFromPackage(server, pkg)} title={hostStdio ? "Runs on the server" : "Runs in the sandbox runner"}>
                        Add local ({pkg.registry || "package"})
                      </button>
                    ))}
                    {server.repository && (
                      <a className="btn-ghost btn-sm inline-flex items-center gap-1" href={server.repository} target="_blank" rel="noreferrer noopener">
                        Source <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
            {searching && <p className="text-sm text-gray-500">Searching…</p>}
            {!searching && results.length === 0 && <p className="text-sm text-gray-500">No servers found.</p>}
            {nextCursor && !searching && <button className="btn-secondary" onClick={() => search(nextCursor)}>Load more</button>}
          </section>
        )}

        {tab === "add" && (
          <form className="card space-y-4" onSubmit={submit}>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="text-sm font-medium">Name</span>
                <input className="input w-full" required maxLength={60} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="GitHub" />
              </label>
              <label className="space-y-1">
                <span className="text-sm font-medium">Type</span>
                <select className="input w-full" value={draft.transport} onChange={(event) => setDraft({ ...draft, transport: event.target.value as Draft["transport"] })}>
                  <option value="http">Remote (HTTPS URL)</option>
                  <option value="stdio">Local command (stdio)</option>
                </select>
              </label>
            </div>
            {draft.transport === "http" ? (
              <label className="block space-y-1">
                <span className="text-sm font-medium">Server URL</span>
                <input className="input w-full font-mono" type="url" required value={draft.url} onChange={(event) => setDraft({ ...draft, url: event.target.value })} placeholder="https://example.com/mcp" />
                <span className="text-xs text-gray-500">Servers that use OAuth open a sign-in window when you press Connect.</span>
              </label>
            ) : (
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="space-y-1">
                  <span className="text-sm font-medium">Command</span>
                  <input className="input w-full font-mono" required value={draft.command} onChange={(event) => setDraft({ ...draft, command: event.target.value })} placeholder="npx" />
                </label>
                <label className="space-y-1 sm:col-span-2">
                  <span className="text-sm font-medium">Arguments</span>
                  <input className="input w-full font-mono" value={draft.args} onChange={(event) => setDraft({ ...draft, args: event.target.value })} placeholder="-y @modelcontextprotocol/server-everything" />
                </label>
                <p className="text-xs text-gray-500 sm:col-span-3">
                  {hostStdio ? "Local servers you add run as a process on the MIZAN server." : "Local servers run in the isolated sandbox runner when it is enabled."}
                </p>
              </div>
            )}
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">{draft.transport === "http" ? "Headers" : "Environment variables"} <span className="text-xs text-gray-500">(stored encrypted)</span></legend>
              {draft.secrets.map((secret, index) => (
                <div key={index} className="flex gap-2 items-start">
                  <input className="input w-1/3 font-mono" placeholder={draft.transport === "http" ? "Authorization" : "API_KEY"} value={secret.key} onChange={(event) => setDraft({ ...draft, secrets: draft.secrets.map((s, i) => i === index ? { ...s, key: event.target.value } : s) })} />
                  <div className="flex-1">
                    <input className="input w-full font-mono" type={secret.secret ? "password" : "text"} placeholder={secret.description || "value"} value={secret.value} onChange={(event) => setDraft({ ...draft, secrets: draft.secrets.map((s, i) => i === index ? { ...s, value: event.target.value } : s) })} />
                  </div>
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setDraft({ ...draft, secrets: draft.secrets.filter((_, i) => i !== index) })} aria-label="Remove">✕</button>
                </div>
              ))}
              <button type="button" className="btn-secondary btn-sm inline-flex items-center gap-1" onClick={() => setDraft({ ...draft, secrets: [...draft.secrets, { key: "", value: "", secret: true }] })}>
                <Plus className="w-3.5 h-3.5" /> Add {draft.transport === "http" ? "header" : "variable"}
              </button>
            </fieldset>
            <div className="flex gap-2">
              <button className="btn-gold" disabled={busy === "add"}>Add connector</button>
              <button type="button" className="btn-ghost" onClick={() => setDraft(emptyDraft())}>Clear</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
