import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, ExternalLink, Eye, EyeOff, RefreshCw, RotateCw, Save, Share2, X } from "lucide-react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import type { Artifact } from "../types";
import FileTree from "./workspace/FileTree";
import { DiffView } from "./AgentActivity";
import { projectPreview, type ProjectPreview } from "../utils/workspacePreview";
import type { WorkspaceEntry } from "../utils/workspaceTree";
import { previewSrc } from "../utils/sandboxCommands";
import type { SandboxStatus } from "./workspace/SandboxPanel";
import { confirmDialog } from "@/components/ui/confirm";
import { SidebarTrigger } from "@/components/ui/sidebar";

const CodeEditor = lazy(() => import("./workspace/CodeEditor"));
const PreviewPane = lazy(() => import("./workspace/PreviewPane"));
const SandboxPanel = lazy(() => import("./workspace/SandboxPanel"));

interface Workspace {
  id: string;
  name: string;
}
interface Capabilities {
  execution_available: boolean;
  execution_detail?: string;
  hardware_inspection: boolean;
}
interface RunResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  duration_ms: number;
  changed_files: string[];
  truncated: boolean;
}
interface Checkpoint {
  id: string;
  message: string;
  created_at: string;
}
interface Buffer {
  content: string;
  original: string;
  sha?: string;
  image?: boolean;
}
interface Props {
  sessionId: string;
  selectedId: string;
  onSelect: (id: string) => void;
  onArtifact: (artifact: Artifact) => void;
  onAskAgent: (content: string) => void;
  onDirtyChange: (dirty: boolean) => void;
}
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`${config.API_URL}/workspaces${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Workspace request failed (${response.status})`,
    );
  return body as T;
}
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const button =
  "px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-gray-100 dark:hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1";
const field =
  "w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus-ring";
const isImage = (path: string) => /\.(png|jpe?g|webp|gif)$/i.test(path);

export function CodingWorkspace({
  sessionId,
  selectedId,
  onSelect,
  onArtifact,
  onAskAgent,
  onDirtyChange,
}: Props) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [buffers, setBuffers] = useState<Record<string, Buffer>>({});
  const [tabs, setTabs] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [panel, setPanel] = useState<"run" | "sandbox" | "changes">("run");
  const [language, setLanguage] = useState<"shell" | "python" | "javascript">("shell");
  const [command, setCommand] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [changes, setChanges] = useState<{ path: string; status: string; diff: string }[] | null>(null);
  const [hardware, setHardware] = useState<Record<string, unknown> | null>(null);
  const [showPreview, setShowPreview] = useState(() => {
    try { return localStorage.getItem("mizan_workspace_preview") !== "0"; } catch { return true; }
  });
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [revision, setRevision] = useState(0);
  const [sandbox, setSandbox] = useState<SandboxStatus | null>(null);
  const [serverPreview, setServerPreview] = useState("");
  const [previewMode, setPreviewMode] = useState<"browser" | "server">("browser");
  const [frameKey, setFrameKey] = useState(0);
  const [packageJson, setPackageJson] = useState<string | undefined>();
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;

  const current = path ? buffers[path] : undefined;
  const dirtyPaths = useMemo(
    () => Object.entries(buffers).filter(([, b]) => !b.image && (b.content !== b.original || b.sha === undefined)).map(([p]) => p),
    [buffers],
  );
  const dirty = dirtyPaths.length > 0;
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const base = `/${encodeURIComponent(selectedId)}`;
  const loadTree = useCallback(async (id: string) => {
    const data = await api<{ files: WorkspaceEntry[]; truncated: boolean }>(`/${encodeURIComponent(id)}/tree`);
    if (selectedRef.current === id) {
      setEntries(data.files);
      if (data.truncated) setNotice("The file list is limited.");
    }
  }, []);
  const refresh = useCallback(async () => {
    const data = await api<{ workspaces: Workspace[]; capabilities: Capabilities }>("");
    setWorkspaces(data.workspaces ?? []);
    setCapabilities(data.capabilities ?? null);
  }, []);
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    setEntries([]);
    setError("");
    setNotice("");
    setPath("");
    setTabs([]);
    setBuffers({});
    setResult(null);
    setChanges(null);
    setCheckpoints([]);
    setPreview(null);
    setSandbox(null);
    setServerPreview("");
    setPreviewMode("browser");
    setPackageJson(undefined);
    if (!selectedId) return;
    void loadTree(selectedId).catch((e) => setError(e.message));
    void api<{ checkpoints: Checkpoint[] }>(`${base}/checkpoints`)
      .then((data) => { if (selectedRef.current === selectedId) setCheckpoints(data.checkpoints); })
      .catch(() => {});
  }, [selectedId, base, loadTree]);

  // The agent edits files from the chat; pick those changes up on focus.
  useEffect(() => {
    if (!selectedId) return;
    const onFocus = () => { void loadTree(selectedId).catch(() => {}); setRevision((r) => r + 1); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [selectedId, loadTree]);

  useEffect(() => {
    if (!selectedId || !showPreview) return;
    let cancelled = false;
    api<{ files: Record<string, string> }>(`${base}/files`)
      .then((data) => {
        if (cancelled || selectedRef.current !== selectedId) return;
        const files = { ...data.files };
        for (const [p, b] of Object.entries(buffers)) if (!b.image) files[p] = b.content;
        setPackageJson(files["package.json"]);
        setPreview(projectPreview(files, path));
      })
      .catch((e) => !cancelled && setPreview({ kind: "none", reason: (e as Error).message }));
    return () => { cancelled = true; };
    // Rebuild on explicit revisions (save, run, refresh), not on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, showPreview, revision, base]);

  const action = async (label: string, work: () => Promise<void>) => {
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

  const saveFile = async (target: string) => {
    const buffer = buffers[target];
    if (!buffer || buffer.image) return;
    const data = await api<{ sha256: string }>(`${base}/file`, json("PUT", { path: target, content: buffer.content, expected_sha256: buffer.sha ?? "" }));
    setBuffers((all) => ({ ...all, [target]: { ...all[target], original: buffer.content, sha: data.sha256 } }));
  };
  const saveAll = async () => {
    for (const target of dirtyPaths) await saveFile(target);
    if (dirtyPaths.length) {
      setNotice(dirtyPaths.length === 1 ? "File saved." : `${dirtyPaths.length} files saved.`);
      await loadTree(selectedId);
      setRevision((r) => r + 1);
      // A running dev server should see the edit; failures surface on the next sync.
      if (sandbox?.running) void api(`${base}/session/sync`, json("POST", {})).catch(() => {});
    }
  };
  const openServerPreview = useCallback((url: string) => {
    setServerPreview(url);
    setPreviewMode("server");
    setFrameKey((k) => k + 1);
    setShowPreview(true);
  }, []);
  const filesChanged = useCallback(() => {
    void loadTree(selectedId).catch(() => {});
    setRevision((r) => r + 1);
  }, [loadTree, selectedId]);

  const openFile = (next: string) => {
    if (buffers[next]) {
      setPath(next);
      setTabs((list) => list.includes(next) ? list : [...list, next]);
      return;
    }
    void action("Opening", async () => {
      const id = selectedId;
      if (isImage(next)) {
        setBuffers((all) => ({ ...all, [next]: { content: "", original: "", image: true } }));
      } else {
        const data = await api<{ path: string; content: string; sha256: string }>(`${base}/file?path=${encodeURIComponent(next)}`);
        if (selectedRef.current !== id) return;
        setBuffers((all) => ({ ...all, [next]: { content: data.content, original: data.content, sha: data.sha256 } }));
      }
      setTabs((list) => list.includes(next) ? list : [...list, next].slice(-8));
      setPath(next);
    });
  };

  const closeTab = async (target: string) => {
    const buffer = buffers[target];
    if (buffer && !buffer.image && buffer.content !== buffer.original
      && !(await confirmDialog({ title: `Discard unsaved changes in ${target}?`, confirmLabel: "Discard", destructive: true }))) return;
    setTabs((list) => {
      const next = list.filter((p) => p !== target);
      if (path === target) setPath(next[next.length - 1] ?? "");
      return next;
    });
    setBuffers((all) => {
      const { [target]: _removed, ...rest } = all;
      return rest;
    });
  };

  const create = (kind: "file" | "directory", target: string) =>
    void action("Creating", async () => {
      if (kind === "directory") {
        await api(`${base}/directory`, json("POST", { path: target }));
      } else {
        setBuffers((all) => ({ ...all, [target]: { content: "", original: "" } }));
        setTabs((list) => [...list.filter((p) => p !== target), target]);
        setPath(target);
        await api<{ sha256: string }>(`${base}/file`, json("PUT", { path: target, content: "", expected_sha256: "" }))
          .then((data) => setBuffers((all) => ({ ...all, [target]: { content: all[target]?.content ?? "", original: "", sha: data.sha256 } })));
      }
      await loadTree(selectedId);
    });

  const rename = (from: string, to: string) =>
    void action("Renaming", async () => {
      if (buffers[from] && buffers[from].content !== buffers[from].original) await saveFile(from);
      await api(`${base}/rename`, json("POST", { path: from, new_path: to }));
      setBuffers((all) => {
        const { [from]: moved, ...rest } = all;
        return moved ? { ...rest, [to]: moved } : rest;
      });
      setTabs((list) => list.map((p) => (p === from ? to : p)));
      if (path === from) setPath(to);
      await loadTree(selectedId);
      setRevision((r) => r + 1);
    });

  const remove = (target: string) =>
    void action("Deleting", async () => {
      await api(`${base}/file?path=${encodeURIComponent(target)}`, { method: "DELETE" });
      setTabs((list) => list.filter((p) => p !== target));
      setBuffers((all) => {
        const { [target]: _removed, ...rest } = all;
        return rest;
      });
      if (path === target) setPath("");
      await loadTree(selectedId);
      setRevision((r) => r + 1);
    });

  const publish = () =>
    void action("Creating artifact", async () => {
      if (current && !current.image && current.content !== current.original) await saveFile(path);
      const data = await api<{ artifact: Artifact }>(`${base}/artifact`, json("POST", { path, session_id: sessionId, title: path.split("/").pop() }));
      onArtifact(data.artifact);
      setNotice("Artifact added to this conversation.");
    });

  const togglePreview = () => {
    setShowPreview((value) => {
      try { localStorage.setItem("mizan_workspace_preview", value ? "0" : "1"); } catch { /* convenience only */ }
      return !value;
    });
  };

  return (
    <section className="flex-1 min-h-0 flex flex-col bg-background" aria-label="Code">
      <div className="px-4 py-3 border-b flex flex-wrap items-center gap-2">
        <SidebarTrigger className="-ml-1 md:hidden" />
        <div className="mr-auto min-w-0">
          <h1 className="text-lg font-semibold tracking-tight">Code</h1>
          <p className="text-xs text-muted-foreground">Edit, preview and run your project; MIZAN works in the same files.</p>
        </div>
        <select
          aria-label="Selected workspace"
          value={selectedId}
          disabled={Boolean(busy)}
          className={`${field} w-auto! max-w-full`}
          onChange={async (event) => {
            const next = event.target.value;
            if (!dirty || await confirmDialog({ title: "Discard unsaved file changes?", confirmLabel: "Discard", destructive: true })) onSelect(next);
          }}
        >
          <option value="">Choose a workspace</option>
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
          ))}
        </select>
        {selectedId && (
          <>
            <button className={button} disabled={Boolean(busy)} title="Reload files" onClick={() => void action("Refreshing", async () => { await Promise.all([loadTree(selectedId), refresh()]); setRevision((r) => r + 1); })}>
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button className={button} onClick={togglePreview} aria-pressed={showPreview}>
              {showPreview ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />} Preview
            </button>
            <button
              className={`${button} bg-amber-600! text-white! border-amber-600!`}
              disabled={Boolean(busy)}
              onClick={() => void action("Saving draft", async () => {
                await saveAll();
                onAskAgent(`Help me work in this selected workspace.${path ? ` Review ${path} and explain what should change.` : " Inspect the files and help me plan the project."}`);
              })}
            >
              <Bot className="w-3.5 h-3.5" /> Ask agent
            </button>
          </>
        )}
      </div>
      {(error || notice) && (
        <div role={error ? "alert" : "status"} className={`px-4 py-2 text-sm ${error ? "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300" : "bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200"}`}>
          {error || notice}
        </div>
      )}
      {!selectedId ? (
        <div className="p-6 sm:p-10 max-w-lg">
          <h2 className="text-xl font-semibold">A place for your next project</h2>
          <p className="text-sm text-gray-500 my-3">
            Create a workspace or reopen one above. Saved files and checkpoints stay with your account.
          </p>
          <form
            className="flex gap-2 mt-5"
            onSubmit={(event) => {
              event.preventDefault();
              void action("Creating workspace", async () => {
                const workspace = await api<Workspace>("", json("POST", { name: newName }));
                await refresh();
                onSelect(workspace.id);
                setNewName("");
              });
            }}
          >
            <input aria-label="Workspace name" placeholder="Project name" value={newName} onChange={(event) => setNewName(event.target.value)} maxLength={100} className={field} />
            <button disabled={!newName.trim() || Boolean(busy)} className={`${button} bg-amber-600! text-white! whitespace-nowrap`}>Create workspace</button>
          </form>
        </div>
      ) : (
        <div className={`flex-1 min-h-0 grid grid-cols-1 auto-rows-max lg:grid-rows-[minmax(0,1fr)] overflow-auto lg:overflow-hidden ${showPreview ? "lg:grid-cols-[220px_minmax(0,1fr)_minmax(0,0.9fr)]" : "lg:grid-cols-[220px_minmax(0,1fr)]"}`}>
          <aside className="border-b lg:border-b-0 lg:border-r border-border lg:overflow-auto max-h-56 lg:max-h-none overflow-auto">
            <FileTree entries={entries} selected={path} disabled={Boolean(busy)} onOpen={openFile} onCreate={create} onRename={rename} onDelete={remove} />
          </aside>
          <div className="min-w-0 min-h-0 flex flex-col">
            <div className="flex items-center border-b border-border/60 overflow-x-auto">
              {tabs.map((tab) => {
                const buffer = buffers[tab];
                const changed = buffer && !buffer.image && buffer.content !== buffer.original;
                return (
                  <div key={tab} className={`flex items-center gap-1 pl-3 pr-1 py-1.5 text-xs font-mono border-r border-border/60 whitespace-nowrap ${tab === path ? "bg-muted/50 text-gray-900 dark:text-zinc-100" : "text-gray-500"}`}>
                    <button type="button" onClick={() => setPath(tab)} title={tab}>{tab.split("/").pop()}{changed ? " ●" : ""}</button>
                    <button type="button" className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-zinc-800" aria-label={`Close ${tab}`} onClick={() => closeTab(tab)}>
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                );
              })}
              <div className="ml-auto flex items-center gap-1 px-2 py-1">
                <button className={button} disabled={!dirty || Boolean(busy)} onClick={() => void action("Saving", saveAll)} title="Save (Ctrl/Cmd+S)">
                  <Save className="w-3.5 h-3.5" /> Save
                </button>
                <button className={button} disabled={!path || Boolean(busy)} onClick={publish} title="Show this file in the chat">
                  <Share2 className="w-3.5 h-3.5" /> To chat
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-[260px] overflow-auto">
              {current?.image ? (
                <div className="h-full flex items-center justify-center text-sm text-gray-500 p-6">
                  Image selected. Use “To chat” to view it in the conversation.
                </div>
              ) : path && current ? (
                <Suspense fallback={<div className="p-4 text-sm text-gray-500">Loading editor…</div>}>
                  <CodeEditor
                    path={path}
                    value={current.content}
                    onChange={(value) => setBuffers((all) => ({ ...all, [path]: { ...all[path], content: value } }))}
                    onSave={() => void action("Saving", saveAll)}
                  />
                </Suspense>
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-gray-400 p-6">Select a file to edit, or ask the agent to build something.</div>
              )}
            </div>
            <div className={`border-t border-border overflow-auto ${panel === "sandbox" ? "lg:max-h-[60%]" : "lg:max-h-[40%]"}`}>
              <div className="flex items-center gap-1 px-3 pt-2">
                {(["run", "sandbox", "changes"] as const).map((value) => (
                  <button key={value} className={`px-3 py-1 text-xs rounded-md ${panel === value ? "bg-muted font-semibold" : "text-gray-500"}`} onClick={() => setPanel(value)}>
                    {value === "run" ? "Command" : value === "sandbox" ? `Sandbox${sandbox?.running ? " ●" : ""}` : "Changes"}
                  </button>
                ))}
              </div>
              {panel === "sandbox" ? (
                <Suspense fallback={<p className="p-3 text-xs text-gray-500">Loading sandbox…</p>}>
                  <SandboxPanel
                    workspaceId={selectedId}
                    packageJson={packageJson}
                    disabled={Boolean(busy)}
                    onStatus={setSandbox}
                    onFilesChanged={filesChanged}
                    onOpenPreview={openServerPreview}
                  />
                </Suspense>
              ) : panel === "run" ? (
                <div className="p-3 space-y-2">
                  {sandbox?.running && (
                    <p className="text-xs text-emerald-600">Commands run in this project's sandbox; installed packages stay until it stops.</p>
                  )}
                  {!capabilities?.execution_available && !sandbox?.running && (
                    <p className="text-xs text-gray-500">
                      {capabilities?.execution_detail || "Server execution is unavailable."} Python and web apps still run in the Preview panel.
                    </p>
                  )}
                  <form
                    className="flex flex-wrap gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void action("Running", async () => {
                        await saveAll();
                        setResult(null);
                        const data = sandbox?.running
                          ? await api<RunResult>(`${base}/session/exec`, json("POST", { command, language, timeout_s: 300 }))
                          : await api<RunResult>(`${base}/run`, json("POST", { command, language, timeout_s: 60 }));
                        setResult(data);
                        await loadTree(selectedId);
                        setRevision((r) => r + 1);
                      });
                    }}
                  >
                    <select aria-label="Run language" className={`${field} w-auto!`} value={language} onChange={(event) => setLanguage(event.target.value as typeof language)}>
                      <option value="shell">Terminal</option>
                      <option value="python">Python</option>
                      <option value="javascript">JavaScript</option>
                    </select>
                    <input
                      aria-label="Command or code to run"
                      value={command}
                      onChange={(event) => setCommand(event.target.value)}
                      className={`${field} flex-1 min-w-[120px] font-mono`}
                      placeholder={language === "shell" ? "python -m pytest -q" : language === "javascript" ? "console.log('Hello')" : "print('Hello')"}
                    />
                    <button className={`${button} bg-amber-600! text-white!`} disabled={!command.trim() || !(capabilities?.execution_available || sandbox?.running) || Boolean(busy)}>
                      {busy === "Running" ? "Running…" : sandbox?.running ? "Run in sandbox" : "Run on server"}
                    </button>
                  </form>
                  {result && (
                    <div role="status" className="space-y-1">
                      <p className={`text-xs ${result.exit_code === 0 ? "text-emerald-600" : "text-red-600"}`}>
                        {result.timed_out ? "Time limit reached" : `Exit ${result.exit_code}`} · {(result.duration_ms / 1000).toFixed(1)}s
                        {result.truncated ? " · output limited" : ""}
                      </p>
                      <pre className="whitespace-pre-wrap wrap-break-word font-mono text-xs rounded-lg bg-zinc-900 text-gray-100 p-3 max-h-52 overflow-auto">
                        {result.stdout || "No standard output."}
                        {result.stderr ? `\n\n${result.stderr}` : ""}
                      </pre>
                      {result.changed_files?.length > 0 && <p className="text-xs text-gray-500">Changed: {result.changed_files.join(", ")}</p>}
                    </div>
                  )}
                  {capabilities?.hardware_inspection && (
                    <button className="text-xs text-gray-500 underline" onClick={() => void action("Inspecting hardware", async () => setHardware(await api<Record<string, unknown>>("/hardware")))}>
                      Inspect available hardware
                    </button>
                  )}
                  {hardware && (
                    <p className="text-xs text-gray-500">
                      {String(hardware.cpu_count)} CPU cores ·{" "}
                      {typeof hardware.memory_total_bytes === "number" ? (hardware.memory_total_bytes / 1024 ** 3).toFixed(1) : "—"} GB memory ·{" "}
                      {Array.isArray(hardware.gpus) ? hardware.gpus.length : 0} GPU(s)
                    </p>
                  )}
                </div>
              ) : (
                <div className="p-3 space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      className={button}
                      disabled={Boolean(busy)}
                      onClick={() => void action("Saving checkpoint", async () => {
                        await saveAll();
                        const checkpoint = await api<Checkpoint>(`${base}/checkpoint`, json("POST", { message: `Saved ${path || "workspace"}` }));
                        setCheckpoints((previous) => [checkpoint, ...previous]);
                        setNotice("Checkpoint saved. Compare later changes against it.");
                      })}
                    >
                      Save checkpoint
                    </button>
                    {checkpoints.length > 0 && (
                      <button
                        className={button}
                        disabled={Boolean(busy)}
                        onClick={() => void action("Comparing changes", async () => {
                          const data = await api<{ files: { path: string; status: string; diff: string }[]; truncated: boolean }>(`${base}/diff?checkpoint_id=${encodeURIComponent(checkpoints[0].id)}`);
                          setChanges(data.files);
                          if (data.truncated) setNotice("Some diff output was limited.");
                        })}
                      >
                        Compare with last checkpoint
                      </button>
                    )}
                  </div>
                  {checkpoints.length > 0 && (
                    <p className="text-xs text-gray-500">Latest checkpoint: {checkpoints[0].message} · {new Date(checkpoints[0].created_at).toLocaleString()}</p>
                  )}
                  {changes && changes.length === 0 && <p className="text-xs text-gray-500">No changes since this checkpoint.</p>}
                  {changes?.map((file) => (
                    <div key={file.path}>
                      <p className="text-xs font-mono mb-1"><span className="badge-info mr-1">{file.status}</span>{file.path}</p>
                      <DiffView diff={file.diff} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          {showPreview && (
            <div className="min-w-0 min-h-[320px] border-t lg:border-t-0 lg:border-l border-border flex flex-col">
              <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
                <span className="text-xs font-semibold mr-auto">
                  Preview{previewMode === "server" ? " · sandbox server" : preview?.kind === "web" ? ` · ${preview.template}` : preview?.kind === "python" ? " · Python" : ""}
                </span>
                {serverPreview && (
                  <div className="flex rounded-md border border-border overflow-hidden text-xs" role="group" aria-label="Preview source">
                    {(["browser", "server"] as const).map((mode) => (
                      <button key={mode} className={`px-2 py-0.5 ${previewMode === mode ? "bg-muted font-semibold" : "text-gray-500"}`} aria-pressed={previewMode === mode} onClick={() => setPreviewMode(mode)}>
                        {mode === "browser" ? "Browser" : "Server"}
                      </button>
                    ))}
                  </div>
                )}
                {previewMode === "server" && serverPreview ? (
                  <>
                    <button className="p-1 text-gray-500 hover:text-gray-800" title="Reload" aria-label="Reload server preview" onClick={() => setFrameKey((k) => k + 1)}>
                      <RotateCw className="w-3.5 h-3.5" />
                    </button>
                    <a className="p-1 text-gray-500 hover:text-gray-800" href={previewSrc(serverPreview)} target="_blank" rel="noopener noreferrer" title="Open in a new tab" aria-label="Open server preview in a new tab">
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </>
                ) : (
                  <button className="text-xs text-gray-500 hover:underline" onClick={() => void action("Updating preview", async () => { await saveAll(); setRevision((r) => r + 1); })}>
                    Update
                  </button>
                )}
              </div>
              <div className="flex-1 min-h-0">
                {previewMode === "server" && serverPreview ? (
                  <iframe
                    key={frameKey}
                    src={previewSrc(serverPreview)}
                    title="Sandbox server preview"
                    sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads"
                    className="w-full h-full min-h-[320px] bg-white border-0"
                  />
                ) : (
                  <Suspense fallback={<div className="p-4 text-sm text-gray-500">Loading preview…</div>}>
                    <PreviewPane preview={preview} revision={revision} />
                  </Suspense>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
