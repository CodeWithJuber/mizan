/**
 * One project beside its chat: Preview, Code (files + editor), Changes (what the last
 * message changed, hunk by hunk) and Terminal (commands and the server sandbox).
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, RefreshCw, RotateCw, Save, Share2, Wrench, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import type { Artifact } from "../../types";
import FileTree from "../../components/workspace/FileTree";
import { projectPreview, type ProjectPreview } from "../../utils/workspacePreview";
import type { WorkspaceEntry } from "../../utils/workspaceTree";
import { previewSrc } from "../../utils/sandboxCommands";
import type { SandboxStatus } from "../../components/workspace/SandboxPanel";
import { type Capabilities, jsonBody, onProjectChanged, workspaceApi } from "./projects";
import { ChangesTab } from "./ChangesTab";

const CodeEditor = lazy(() => import("../../components/workspace/CodeEditor"));
const PreviewPane = lazy(() => import("../../components/workspace/PreviewPane"));
const SandboxPanel = lazy(() => import("../../components/workspace/SandboxPanel"));

export type ProjectTab = "preview" | "code" | "changes" | "terminal";
const TABS: { id: ProjectTab; label: string }[] = [
  { id: "preview", label: "Preview" },
  { id: "code", label: "Code" },
  { id: "changes", label: "Changes" },
  { id: "terminal", label: "Terminal" },
];
const TAB_KEY = "mizan_project_tab";

interface RunResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  duration_ms: number;
  changed_files: string[];
  truncated: boolean;
}
interface Buffer {
  content: string;
  original: string;
  sha?: string;
  image?: boolean;
}

export interface FixRequest {
  source: "preview" | "server" | "terminal";
  error: string;
}

interface Props {
  projectId: string;
  sessionId: string;
  capabilities: Capabilities | null;
  /** The checkpoint saved before the chat's latest message in this project. */
  turnCheckpoint?: string;
  /** A dev server started for this project (the chat's `preview` event). */
  livePreviewUrl?: string;
  /** Bumped when the chat changed files (a reply finished). */
  filesRevision: number;
  onArtifact: (artifact: Artifact) => void;
  onDirtyChange: (dirty: boolean) => void;
  /** "Fix with MIZAN": send the error to the chat. */
  onFix?: (fix: FixRequest) => void;
}

const isImage = (path: string) => /\.(png|jpe?g|webp|gif)$/i.test(path);

function initialTab(): ProjectTab {
  try {
    const saved = localStorage.getItem(TAB_KEY);
    return TABS.some((tab) => tab.id === saved) ? (saved as ProjectTab) : "preview";
  } catch {
    return "preview";
  }
}

export function ProjectWorkspace({
  projectId, sessionId, capabilities, turnCheckpoint, livePreviewUrl, filesRevision,
  onArtifact, onDirtyChange, onFix,
}: Props) {
  const [tab, setTabState] = useState<ProjectTab>(initialTab);
  const setTab = (next: ProjectTab) => {
    setTabState(next);
    try { localStorage.setItem(TAB_KEY, next); } catch { /* a convenience only */ }
  };
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [buffers, setBuffers] = useState<Record<string, Buffer>>({});
  const [tabs, setTabs] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [language, setLanguage] = useState<"shell" | "python" | "javascript">("shell");
  const [command, setCommand] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [revision, setRevision] = useState(0);
  const [sandbox, setSandbox] = useState<SandboxStatus | null>(null);
  const [serverPreview, setServerPreview] = useState("");
  const [previewMode, setPreviewMode] = useState<"browser" | "server">("browser");
  const [frameKey, setFrameKey] = useState(0);
  const [packageJson, setPackageJson] = useState<string | undefined>();
  const selectedRef = useRef(projectId);
  selectedRef.current = projectId;
  const base = `/${encodeURIComponent(projectId)}`;

  const current = path ? buffers[path] : undefined;
  const dirtyPaths = useMemo(
    () => Object.entries(buffers)
      .filter(([, b]) => !b.image && (b.content !== b.original || b.sha === undefined))
      .map(([p]) => p),
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

  const loadTree = useCallback(async (id: string) => {
    const data = await workspaceApi<{ files: WorkspaceEntry[]; truncated: boolean }>(`/${encodeURIComponent(id)}/tree`);
    if (selectedRef.current === id) {
      setEntries(data.files);
      if (data.truncated) setNotice("The file list is limited.");
    }
  }, []);

  // A different project starts clean.
  useEffect(() => {
    setEntries([]);
    setError("");
    setNotice("");
    setPath("");
    setTabs([]);
    setBuffers({});
    setResult(null);
    setPreview(null);
    setSandbox(null);
    setServerPreview("");
    setPreviewMode("browser");
    setPackageJson(undefined);
    void loadTree(projectId).catch((e: Error) => setError(e.message));
  }, [projectId, loadTree]);

  // The chat changed files (a reply finished), or the window came back: reload.
  const filesChanged = useCallback(() => {
    void loadTree(projectId).catch(() => {});
    setRevision((r) => r + 1);
  }, [loadTree, projectId]);
  useEffect(() => {
    if (filesRevision) filesChanged();
  }, [filesRevision, filesChanged]);
  useEffect(() => {
    window.addEventListener("focus", filesChanged);
    const stop = onProjectChanged(projectId, filesChanged);
    return () => {
      window.removeEventListener("focus", filesChanged);
      stop();
    };
  }, [filesChanged, projectId]);

  // Open files that the chat changed and that have no unsaved edits are reloaded.
  useEffect(() => {
    if (!filesRevision) return;
    for (const [open, buffer] of Object.entries(buffers)) {
      if (buffer.image || buffer.content !== buffer.original) continue;
      void workspaceApi<{ content: string; sha256: string }>(`${base}/file?path=${encodeURIComponent(open)}`)
        .then((data) => setBuffers((all) => all[open] && all[open].content === all[open].original
          ? { ...all, [open]: { content: data.content, original: data.content, sha: data.sha256 } }
          : all))
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filesRevision]);

  useEffect(() => {
    if (tab !== "preview") return;
    let cancelled = false;
    workspaceApi<{ files: Record<string, string> }>(`${base}/files`)
      .then((data) => {
        if (cancelled || selectedRef.current !== projectId) return;
        const files = { ...data.files };
        for (const [p, b] of Object.entries(buffers)) if (!b.image) files[p] = b.content;
        setPackageJson(files["package.json"]);
        setPreview(projectPreview(files, path));
      })
      .catch((e: Error) => !cancelled && setPreview({ kind: "none", reason: e.message }));
    return () => { cancelled = true; };
    // Rebuild on explicit revisions (save, run, refresh), not on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, tab, revision, base]);

  const openServerPreview = useCallback((url: string) => {
    setServerPreview(url);
    setPreviewMode("server");
    setFrameKey((k) => k + 1);
    setTabState("preview");
  }, []);
  // A dev server started from the chat opens here at once.
  useEffect(() => {
    if (livePreviewUrl) openServerPreview(livePreviewUrl);
  }, [livePreviewUrl, openServerPreview]);

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
    const data = await workspaceApi<{ sha256: string }>(
      `${base}/file`, jsonBody("PUT", { path: target, content: buffer.content, expected_sha256: buffer.sha ?? "" }),
    );
    setBuffers((all) => ({ ...all, [target]: { ...all[target], original: buffer.content, sha: data.sha256 } }));
  };
  const saveAll = async () => {
    for (const target of dirtyPaths) await saveFile(target);
    if (dirtyPaths.length) {
      setNotice(dirtyPaths.length === 1 ? "File saved." : `${dirtyPaths.length} files saved.`);
      await loadTree(projectId);
      setRevision((r) => r + 1);
      // A running dev server should see the edit; failures surface on the next sync.
      if (sandbox?.running) void workspaceApi(`${base}/session/sync`, jsonBody("POST", {})).catch(() => {});
    }
  };

  const openFile = (next: string) => {
    setTab("code");
    if (buffers[next]) {
      setPath(next);
      setTabs((list) => list.includes(next) ? list : [...list, next]);
      return;
    }
    void action("Opening", async () => {
      const id = projectId;
      if (isImage(next)) {
        setBuffers((all) => ({ ...all, [next]: { content: "", original: "", image: true } }));
      } else {
        const data = await workspaceApi<{ content: string; sha256: string }>(`${base}/file?path=${encodeURIComponent(next)}`);
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
        await workspaceApi(`${base}/directory`, jsonBody("POST", { path: target }));
      } else {
        setBuffers((all) => ({ ...all, [target]: { content: "", original: "" } }));
        setTabs((list) => [...list.filter((p) => p !== target), target]);
        setPath(target);
        await workspaceApi<{ sha256: string }>(`${base}/file`, jsonBody("PUT", { path: target, content: "", expected_sha256: "" }))
          .then((data) => setBuffers((all) => ({ ...all, [target]: { content: all[target]?.content ?? "", original: "", sha: data.sha256 } })));
      }
      await loadTree(projectId);
    });

  const rename = (from: string, to: string) =>
    void action("Renaming", async () => {
      if (buffers[from] && buffers[from].content !== buffers[from].original) await saveFile(from);
      await workspaceApi(`${base}/rename`, jsonBody("POST", { path: from, new_path: to }));
      setBuffers((all) => {
        const { [from]: moved, ...rest } = all;
        return moved ? { ...rest, [to]: moved } : rest;
      });
      setTabs((list) => list.map((p) => (p === from ? to : p)));
      if (path === from) setPath(to);
      await loadTree(projectId);
      setRevision((r) => r + 1);
    });

  const remove = (target: string) =>
    void action("Deleting", async () => {
      await workspaceApi(`${base}/file?path=${encodeURIComponent(target)}`, { method: "DELETE" });
      setTabs((list) => list.filter((p) => p !== target));
      setBuffers((all) => {
        const { [target]: _removed, ...rest } = all;
        return rest;
      });
      if (path === target) setPath("");
      await loadTree(projectId);
      setRevision((r) => r + 1);
    });

  const publish = () =>
    void action("Creating artifact", async () => {
      if (current && !current.image && current.content !== current.original) await saveFile(path);
      const data = await workspaceApi<{ artifact: Artifact }>(
        `${base}/artifact`, jsonBody("POST", { path, session_id: sessionId, title: path.split("/").pop() }),
      );
      onArtifact(data.artifact);
      setNotice("Shown in the chat.");
    });

  const runCommand = () =>
    void action("Running", async () => {
      await saveAll();
      setResult(null);
      const data = sandbox?.running
        ? await workspaceApi<RunResult>(`${base}/session/exec`, jsonBody("POST", { command, language, timeout_s: 300 }))
        : await workspaceApi<RunResult>(`${base}/run`, jsonBody("POST", { command, language, timeout_s: 60 }));
      setResult(data);
      await loadTree(projectId);
      setRevision((r) => r + 1);
    });
  const failedRun = result && (result.exit_code !== 0 || result.timed_out);

  return (
    <section className="flex h-full min-h-0 flex-col bg-background" aria-label="Project">
      <div className="flex shrink-0 items-center gap-1 border-b px-2 py-1.5">
        <div role="tablist" aria-label="Project views" className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
              className={`rounded-md px-3 py-1 text-sm whitespace-nowrap focus-ring ${tab === item.id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >
              {item.label}{item.id === "terminal" && sandbox?.running ? " ●" : ""}
            </button>
          ))}
        </div>
        <Button variant="ghost" size="icon-sm" title="Reload files" aria-label="Reload files" disabled={Boolean(busy)}
          onClick={() => void action("Refreshing", async () => { await loadTree(projectId); setRevision((r) => r + 1); })}>
          <RefreshCw />
        </Button>
      </div>
      {(error || notice) && (
        <div role={error ? "alert" : "status"} className={`px-3 py-2 text-sm ${error ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-foreground"}`}>
          {error || notice}
        </div>
      )}

      {tab === "preview" && (
        <div className="flex min-h-0 flex-1 flex-col" role="tabpanel" aria-label="Preview">
          <div className="flex items-center gap-2 border-b px-3 py-1.5">
            <span className="mr-auto truncate text-xs text-muted-foreground">
              {previewMode === "server" ? "Sandbox server" : preview?.kind === "web" ? preview.template : preview?.kind === "python" ? "Python" : ""}
            </span>
            {serverPreview && (
              <fieldset className="flex overflow-hidden rounded-md border text-xs">
                <legend className="sr-only">Preview source</legend>
                {(["browser", "server"] as const).map((mode) => (
                  <button key={mode} type="button" className={`px-2 py-0.5 ${previewMode === mode ? "bg-muted font-medium" : "text-muted-foreground"}`}
                    aria-pressed={previewMode === mode} onClick={() => setPreviewMode(mode)}>
                    {mode === "browser" ? "Browser" : "Server"}
                  </button>
                ))}
              </fieldset>
            )}
            {previewMode === "server" && serverPreview ? (
              <>
                <Button variant="ghost" size="icon-sm" aria-label="Reload server preview" onClick={() => setFrameKey((k) => k + 1)}>
                  <RotateCw />
                </Button>
                <a className="rounded p-1 text-muted-foreground hover:text-foreground" href={previewSrc(serverPreview)} target="_blank"
                  rel="noopener noreferrer" aria-label="Open server preview in a new tab">
                  <ExternalLink className="size-3.5" />
                </a>
              </>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => void action("Updating preview", async () => { await saveAll(); setRevision((r) => r + 1); })}>
                Update
              </Button>
            )}
          </div>
          <div className="min-h-0 flex-1">
            {previewMode === "server" && serverPreview ? (
              <iframe
                key={frameKey}
                src={previewSrc(serverPreview)}
                title="Sandbox server preview"
                sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads"
                className="h-full min-h-[320px] w-full border-0 bg-white"
              />
            ) : (
              <Suspense fallback={<p className="p-4 text-sm text-muted-foreground">Loading preview…</p>}>
                <PreviewPane
                  preview={preview}
                  revision={revision}
                  onError={onFix ? (message) => onFix({ source: "preview", error: message }) : undefined}
                />
              </Suspense>
            )}
          </div>
        </div>
      )}

      {tab === "code" && (
        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] sm:grid-cols-[200px_minmax(0,1fr)] sm:grid-rows-1" role="tabpanel" aria-label="Code">
          <aside className="max-h-48 overflow-auto border-b sm:max-h-none sm:border-r sm:border-b-0">
            <FileTree entries={entries} selected={path} disabled={Boolean(busy)} onOpen={openFile} onCreate={create} onRename={rename} onDelete={remove} />
          </aside>
          <div className="flex min-h-0 min-w-0 flex-col">
            <div className="flex items-center overflow-x-auto border-b">
              {tabs.map((open) => {
                const buffer = buffers[open];
                const changed = buffer && !buffer.image && buffer.content !== buffer.original;
                return (
                  <div key={open} className={`flex items-center gap-1 border-r py-1.5 pr-1 pl-3 font-mono text-xs whitespace-nowrap ${open === path ? "bg-muted/50 text-foreground" : "text-muted-foreground"}`}>
                    <button type="button" onClick={() => setPath(open)} title={open}>{open.split("/").pop()}{changed ? " ●" : ""}</button>
                    <button type="button" className="rounded p-0.5 hover:bg-muted" aria-label={`Close ${open}`} onClick={() => void closeTab(open)}>
                      <X className="size-3" />
                    </button>
                  </div>
                );
              })}
              <div className="ml-auto flex items-center gap-1 px-2 py-1">
                <Button variant="outline" size="sm" disabled={!dirty || Boolean(busy)} onClick={() => void action("Saving", saveAll)} title="Save (Ctrl/Cmd+S)">
                  <Save /> Save
                </Button>
                <Button variant="outline" size="sm" disabled={!path || Boolean(busy)} onClick={publish} title="Show this file in the chat">
                  <Share2 /> To chat
                </Button>
              </div>
            </div>
            <div className="min-h-[260px] flex-1 overflow-auto">
              {current?.image ? (
                <p className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
                  Image selected. Use “To chat” to view it in the conversation.
                </p>
              ) : path && current ? (
                <Suspense fallback={<p className="p-4 text-sm text-muted-foreground">Loading editor…</p>}>
                  <CodeEditor
                    path={path}
                    value={current.content}
                    onChange={(value) => setBuffers((all) => ({ ...all, [path]: { ...all[path], content: value } }))}
                    onSave={() => void action("Saving", saveAll)}
                  />
                </Suspense>
              ) : (
                <p className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
                  Choose a file, or ask in the chat to change the project.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === "changes" && (
        <div className="min-h-0 flex-1 overflow-auto" role="tabpanel" aria-label="Changes">
          <ChangesTab projectId={projectId} turnCheckpoint={turnCheckpoint} revision={revision + filesRevision} onChanged={filesChanged} />
        </div>
      )}

      {tab === "terminal" && (
        <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3" role="tabpanel" aria-label="Terminal">
          {sandbox?.running ? (
            <p className="text-xs text-muted-foreground">Commands run in this project's sandbox; installed packages stay until it stops.</p>
          ) : !capabilities?.execution_available ? (
            <p className="text-xs text-muted-foreground">
              {capabilities?.execution_detail || "Server execution is unavailable."} Web and Python projects still run in Preview.
            </p>
          ) : null}
          <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); runCommand(); }}>
            <select aria-label="Run language" className="rounded-lg border bg-background px-2 py-1.5 text-sm focus-ring" value={language}
              onChange={(event) => setLanguage(event.target.value as typeof language)}>
              <option value="shell">Terminal</option>
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
            </select>
            <input
              aria-label="Command or code to run"
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              className="min-w-[120px] flex-1 rounded-lg border bg-background px-3 py-1.5 font-mono text-sm focus-ring"
              placeholder={language === "shell" ? "npm test" : language === "javascript" ? "console.log('Hello')" : "print('Hello')"}
            />
            <Button type="submit" disabled={!command.trim() || !(capabilities?.execution_available || sandbox?.running) || Boolean(busy)}>
              {busy === "Running" ? "Running…" : sandbox?.running ? "Run in sandbox" : "Run"}
            </Button>
          </form>
          {result && (
            <div aria-live="polite" className="space-y-1">
              <p className={`text-xs ${failedRun ? "text-destructive" : "text-muted-foreground"}`}>
                {result.timed_out ? "Time limit reached" : `Exit ${result.exit_code}`} · {(result.duration_ms / 1000).toFixed(1)}s
                {result.truncated ? " · output limited" : ""}
              </p>
              <pre className="max-h-52 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
                {result.stdout || "No standard output."}
                {result.stderr ? `\n\n${result.stderr}` : ""}
              </pre>
              {failedRun && onFix && (
                <Button size="sm" variant="outline" onClick={() => onFix({
                  source: "terminal",
                  error: `$ ${command}\n${(result.stderr || result.stdout).slice(-4000)}`,
                })}>
                  <Wrench /> Fix with MIZAN
                </Button>
              )}
            </div>
          )}
          <Suspense fallback={<p className="text-xs text-muted-foreground">Loading sandbox…</p>}>
            <SandboxPanel
              workspaceId={projectId}
              packageJson={packageJson}
              disabled={Boolean(busy)}
              onStatus={setSandbox}
              onFilesChanged={filesChanged}
              onOpenPreview={openServerPreview}
            />
          </Suspense>
        </div>
      )}
    </section>
  );
}
