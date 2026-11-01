/** Server sandbox session: start/stop, sync, interactive terminal and dev servers. */
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Play, RefreshCw, Square, TerminalSquare } from "lucide-react";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";
import { suggestServers, type ServerSuggestion } from "../../utils/sandboxCommands";

const SandboxTerminal = lazy(() => import("./SandboxTerminal"));

export interface SandboxService {
  port: number;
  command: string;
  mode: string;
  alive: boolean;
  preview_url: string;
}
export interface SandboxStatus {
  available: boolean;
  running: boolean;
  egress?: boolean;
  services: SandboxService[];
}
interface SyncResult {
  pushed: string[];
  pulled: string[];
  conflicts: string[];
  warning: string;
}
interface Props {
  workspaceId: string;
  packageJson?: string;
  disabled?: boolean;
  onStatus: (status: SandboxStatus | null) => void;
  onFilesChanged: () => void;
  onOpenPreview: (url: string) => void;
}

const button =
  "px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-gray-100 dark:hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1";
const field =
  "px-3 py-2 rounded-lg border border-border bg-background text-sm focus-ring";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`${config.API_URL}/workspaces${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Sandbox request failed (${response.status})`);
  return body as T;
}
const post = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export default function SandboxPanel({ workspaceId, packageJson, disabled, onStatus, onFilesChanged, onOpenPreview }: Props) {
  const base = `/${encodeURIComponent(workspaceId)}/session`;
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [terminal, setTerminal] = useState(false);
  const suggestions = suggestServers(packageJson);
  const [server, setServer] = useState<ServerSuggestion>(suggestions[0]);
  const [logs, setLogs] = useState<{ port: number; log: string } | null>(null);

  const load = useCallback(async () => {
    const data = await call<SandboxStatus>(base);
    setStatus(data);
    onStatus(data);
    return data;
  }, [base, onStatus]);

  useEffect(() => {
    setStatus(null);
    setTerminal(false);
    setLogs(null);
    load().catch((e) => setError((e as Error).message));
  }, [load]);

  const run = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const describeSync = (sync: SyncResult) => {
    const parts = [];
    if (sync.pulled.length) parts.push(`${sync.pulled.length} file(s) copied from the sandbox`);
    if (sync.pushed.length) parts.push(`${sync.pushed.length} sent to it`);
    if (sync.conflicts.length) parts.push(`editor kept for ${sync.conflicts.join(", ")}`);
    return sync.warning || (parts.length ? `${parts.join("; ")}.` : "Files are in sync.");
  };

  const sync = () =>
    run("Syncing", async () => {
      const data = await call<SyncResult>(`${base}/sync`, post());
      setNotice(describeSync(data));
      if (data.pulled.length) onFilesChanged();
    });

  if (status && !status.available) {
    return (
      <p className="p-3 text-xs text-gray-500">
        Server sandbox sessions need the private workspace runner. Web and Python previews still run in your browser.
      </p>
    );
  }

  return (
    <div className="p-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`text-xs font-semibold ${status?.running ? "text-emerald-600" : "text-gray-500"}`} role="status">
          {status === null ? "Checking sandbox…" : status.running ? `Sandbox running${status.egress ? " · package registries reachable" : " · offline"}` : "Sandbox stopped"}
        </span>
        {status?.running ? (
          <>
            <button className={button} disabled={Boolean(busy) || disabled} onClick={sync} title="Copy changes both ways">
              <RefreshCw className="w-3.5 h-3.5" /> Sync
            </button>
            <button className={button} disabled={Boolean(busy)} onClick={() => setTerminal((value) => !value)} aria-pressed={terminal}>
              <TerminalSquare className="w-3.5 h-3.5" /> {terminal ? "Hide shell" : "Open shell"}
            </button>
            <button
              className={button}
              disabled={Boolean(busy)}
              onClick={() => run("Stopping", async () => {
                setTerminal(false);
                await call(base, { method: "DELETE" });
                await load();
                onFilesChanged();
                setNotice("Sandbox stopped. Project files are saved; installed packages were removed.");
              })}
            >
              <Square className="w-3.5 h-3.5" /> Stop
            </button>
          </>
        ) : (
          <button
            className={`${button} bg-amber-600! text-white! border-amber-600!`}
            disabled={Boolean(busy) || disabled || status === null}
            onClick={() => run("Starting", async () => {
              const data = await call<{ sync: SyncResult }>(base, post());
              await load();
              setNotice(`Sandbox started. ${describeSync(data.sync)}`);
            })}
          >
            <Play className="w-3.5 h-3.5" /> {busy === "Starting" ? "Starting…" : "Start sandbox"}
          </button>
        )}
      </div>
      {(error || notice) && (
        <p role={error ? "alert" : "status"} className={`text-xs ${error ? "text-red-600" : "text-muted-foreground"}`}>{error || notice}</p>
      )}
      {!status?.running && status !== null && (
        <p className="text-xs text-gray-500">
          A private Linux container for this project: install packages, run dev servers and use a shell. It stops after 30 idle minutes.
        </p>
      )}
      {status?.running && terminal && (
        <Suspense fallback={<p className="text-xs text-gray-500">Loading terminal…</p>}>
          <SandboxTerminal workspaceId={workspaceId} onClosed={() => void sync()} />
        </Suspense>
      )}
      {status?.running && (
        <div className="space-y-2">
          <h3 className="text-2xs uppercase tracking-wider font-semibold text-gray-500">Dev server</h3>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void run("Starting server", async () => {
                const info = await call<{ preview_url: string }>(`${base}/services`, post(server));
                await load();
                onOpenPreview(info.preview_url);
                setNotice(`Server starting on port ${server.port}. If the preview is blank, open its log.`);
              });
            }}
          >
            <select
              aria-label="Server preset"
              className={`${field} w-auto`}
              value={suggestions.findIndex((item) => item.label === server.label)}
              onChange={(event) => setServer(suggestions[Number(event.target.value)] ?? suggestions[0])}
            >
              {suggestions.map((item, index) => <option key={item.label} value={index}>{item.label}</option>)}
            </select>
            <input aria-label="Server command" className={`${field} flex-1 min-w-[160px] font-mono text-xs`} value={server.command} onChange={(event) => setServer({ ...server, command: event.target.value })} />
            <input aria-label="Server port" type="number" min={1024} max={65535} className={`${field} w-24`} value={server.port} onChange={(event) => setServer({ ...server, port: Number(event.target.value) })} />
            <button className={`${button} bg-amber-600! text-white! border-amber-600!`} disabled={Boolean(busy) || !server.command.trim()}>Start server</button>
          </form>
          {status.services.map((service) => (
            <div key={service.port} className="flex flex-wrap items-center gap-2 text-xs">
              <span className={`w-2 h-2 rounded-full ${service.alive ? "bg-emerald-500" : "bg-gray-400"}`} aria-hidden />
              <span className="font-mono">:{service.port}</span>
              <span className="font-mono text-gray-500 truncate max-w-[40ch]" title={service.command}>{service.command}</span>
              <button className="underline" onClick={() => onOpenPreview(service.preview_url)}>Preview</button>
              <button className="underline" onClick={() => void run("Loading log", async () => setLogs(await call(`${base}/services/${service.port}/logs`)))}>Log</button>
              <button className="underline text-rose-600" onClick={() => void run("Stopping server", async () => { await call(`${base}/services/${service.port}`, { method: "DELETE" }); await load(); })}>Stop</button>
            </div>
          ))}
          {logs && (
            <pre className="whitespace-pre-wrap wrap-break-word font-mono text-xs rounded-lg bg-zinc-900 text-gray-100 p-3 max-h-48 overflow-auto" aria-label={`Log for port ${logs.port}`}>
              {logs.log || "No output yet."}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
