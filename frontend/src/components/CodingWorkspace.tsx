import { useCallback, useEffect, useRef, useState } from "react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import type { Artifact } from "../types";
interface Workspace {
  id: string;
  name: string;
}
interface FileEntry {
  path: string;
  kind: "file" | "directory";
  size: number;
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
  "px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-zinc-700 hover:bg-gray-100 dark:hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed";
const field =
  "w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-sm focus-ring";
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
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const [original, setOriginal] = useState("");
  const [sha, setSha] = useState<string | undefined>();
  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [language, setLanguage] = useState<"shell" | "python" | "javascript">(
    "shell",
  );
  const [command, setCommand] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [diff, setDiff] = useState("");
  const [hardware, setHardware] = useState<Record<string, unknown> | null>(
    null,
  );
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const dirty = content !== original || (path.length > 0 && sha === undefined);
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
    const data = await api<{ files: FileEntry[]; truncated: boolean }>(
      `/${encodeURIComponent(id)}/tree`,
    );
    if (selectedRef.current === id) {
      setFiles(data.files);
      if (data.truncated) setNotice("The file list is limited.");
    }
  }, []);
  const refresh = useCallback(async () => {
    const data = await api<{
      workspaces: Workspace[];
      capabilities: Capabilities;
    }>("");
    setWorkspaces(data.workspaces);
    setCapabilities(data.capabilities);
  }, []);
  useEffect(() => {
    void refresh().catch((error) => setError(error.message));
  }, [refresh]);
  useEffect(() => {
    setPath("");
    setContent("");
    setOriginal("");
    setSha(undefined);
    setResult(null);
    setDiff("");
    setCheckpoints([]);
    if (!selectedId) {
      setFiles([]);
      return;
    }
    void loadTree(selectedId).catch((error) => setError(error.message));
    void api<{ checkpoints: Checkpoint[] }>(`${base}/checkpoints`)
      .then((data) => {
        if (selectedRef.current === selectedId)
          setCheckpoints(data.checkpoints);
      })
      .catch(() => {});
  }, [selectedId, base, loadTree]);
  const action = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy("");
    }
  };
  const save = async () => {
    const data = await api<{ sha256: string }>(
      `${base}/file`,
      json("PUT", { path, content, ...(sha ? { expected_sha256: sha } : {}) }),
    );
    setOriginal(content);
    setSha(data.sha256);
    setNotice("File saved.");
    await loadTree(selectedId);
  };
  const openFile = (nextPath: string) => {
    if (
      dirty &&
      !window.confirm("Discard unsaved changes before opening another file?")
    )
      return;
    void action("Opening", async () => {
      const id = selectedId;
      const data = await api<{ path: string; content: string; sha256: string }>(
        `${base}/file?path=${encodeURIComponent(nextPath)}`,
      );
      if (selectedRef.current !== id) return;
      setPath(data.path);
      setContent(data.content);
      setOriginal(data.content);
      setSha(data.sha256);
    });
  };
  const publish = () =>
    void action("Creating artifact", async () => {
      if (dirty) await save();
      const data = await api<{ artifact: Artifact }>(
        `${base}/artifact`,
        json("POST", {
          path,
          session_id: sessionId,
          title: path.split("/").pop(),
        }),
      );
      onArtifact(data.artifact);
      setNotice("Artifact added to this conversation.");
    });
  return (
    <section
      className="flex-1 min-h-0 flex flex-col bg-white dark:bg-zinc-950"
      aria-label="Coding workspace"
    >
      <div className="px-4 py-3 border-b border-gray-200 dark:border-zinc-800 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-lg font-semibold">Coding workspace</h1>
          <p className="text-xs text-gray-500 mt-1">
            Files, changes, tests and artifacts in one place.
          </p>
        </div>
        <select
          aria-label="Selected workspace"
          value={selectedId}
          disabled={Boolean(busy)}
          className={`${field} !w-auto max-w-full`}
          onChange={(event) => {
            if (!dirty || window.confirm("Discard unsaved file changes?"))
              onSelect(event.target.value);
          }}
        >
          <option value="">Choose a workspace</option>
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>
              {workspace.name}
            </option>
          ))}
        </select>
      </div>
      {(error || notice) && (
        <div
          role={error ? "alert" : "status"}
          className={`px-4 py-2 text-sm ${error ? "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300" : "bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200"}`}
        >
          {error || notice}
        </div>
      )}
      {!selectedId ? (
        <div className="p-6 sm:p-10 max-w-lg">
          <h2 className="text-xl font-semibold">
            A place for your next project
          </h2>
          <p className="text-sm text-gray-500 my-3">
            Create a workspace or reopen one above. Saved files and checkpoints
            stay with your account.
          </p>
          <form
            className="flex gap-2 mt-5"
            onSubmit={(event) => {
              event.preventDefault();
              void action("Creating workspace", async () => {
                const workspace = await api<Workspace>(
                  "",
                  json("POST", { name: newName }),
                );
                await refresh();
                onSelect(workspace.id);
                setNewName("");
              });
            }}
          >
            <input
              aria-label="Workspace name"
              placeholder="Project name"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              maxLength={100}
              className={field}
            />
            <button
              disabled={!newName.trim() || Boolean(busy)}
              className={`${button} !bg-amber-600 !text-white whitespace-nowrap`}
            >
              Create workspace
            </button>
          </form>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-auto lg:overflow-hidden">
          <aside className="lg:w-56 shrink-0 border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-zinc-800 flex flex-col lg:overflow-auto">
            <div className="px-3 py-3 flex items-center justify-between">
              <h2 className="text-xs uppercase tracking-wider font-semibold text-gray-500">
                Files
              </h2>
              <button
                className="text-xs hover:underline"
                disabled={Boolean(busy)}
                onClick={() =>
                  void action("Refreshing", () => loadTree(selectedId))
                }
              >
                Refresh
              </button>
            </div>
            <form
              className="px-3 pb-3 flex gap-1"
              onSubmit={(event) => {
                event.preventDefault();
                if (dirty && !window.confirm("Discard unsaved file changes?"))
                  return;
                setPath(newPath);
                setContent("");
                setOriginal("");
                setSha(undefined);
                setNewPath("");
              }}
            >
              <input
                aria-label="New file path"
                placeholder="main.py"
                value={newPath}
                onChange={(event) => setNewPath(event.target.value)}
                className={`${field} min-w-0`}
              />
              <button
                className={button}
                disabled={!newPath.trim() || Boolean(busy)}
              >
                New
              </button>
            </form>
            <div className="max-h-44 lg:max-h-none overflow-auto px-2 pb-3">
              {files.length ? (
                files.map((file) =>
                  file.kind === "directory" ? (
                    <div
                      className="px-2 py-1 text-xs text-gray-400"
                      key={file.path}
                    >
                      {file.path}/
                    </div>
                  ) : (
                    <button
                      className={`block w-full text-left px-2 py-2 rounded-md text-xs font-mono truncate focus-ring ${path === file.path ? "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300" : "hover:bg-gray-50 dark:hover:bg-zinc-900"}`}
                      key={file.path}
                      title={file.path}
                      disabled={Boolean(busy)}
                      onClick={() => openFile(file.path)}
                    >
                      {file.path}
                    </button>
                  ),
                )
              ) : (
                <p className="px-2 py-3 text-xs text-gray-400">
                  No saved files yet.
                </p>
              )}
            </div>
          </aside>
          <div className="flex-1 min-w-0 min-h-0 flex flex-col">
            <div className="px-4 py-2 border-b border-gray-100 dark:border-zinc-800 flex flex-wrap items-center gap-2">
              <span className="text-sm font-mono truncate mr-auto">
                {path || "Open or create a file"}
                {dirty ? " • unsaved" : ""}
              </span>
              <button
                className={button}
                disabled={!path || !dirty || Boolean(busy)}
                onClick={() => void action("Saving", save)}
              >
                Save
              </button>
              <button
                className={button}
                disabled={!path || Boolean(busy)}
                onClick={publish}
              >
                Preview artifact
              </button>
              <button
                className={button}
                disabled={Boolean(busy)}
                onClick={() =>
                  void action("Saving draft", async () => {
                    if (path && (dirty || !sha)) await save();
                    onAskAgent(
                      `Help me work in this selected workspace.${path ? ` Review ${path} and explain what should change.` : " Inspect the files and help me plan the project."}`,
                    );
                  })
                }
              >
                Ask agent
              </button>
            </div>
            {path ? (
              <textarea
                aria-label={`File editor ${path}`}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                spellCheck={false}
                className="flex-1 min-h-[260px] lg:min-h-0 resize-none bg-gray-50/50 dark:bg-zinc-950 px-5 py-4 font-mono text-sm leading-6 outline-none focus:ring-2 focus:ring-inset focus:ring-amber-300"
              />
            ) : (
              <div className="flex-1 min-h-[180px] flex items-center justify-center text-sm text-gray-400">
                Select a file to edit.
              </div>
            )}
            <div className="border-t border-gray-200 dark:border-zinc-800 p-4 space-y-3 lg:max-h-[42%] overflow-auto">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold mr-auto">Run & changes</h2>
                <button
                  className={button}
                  disabled={Boolean(busy)}
                  onClick={() =>
                    void action("Saving checkpoint", async () => {
                      if (dirty) await save();
                      const checkpoint = await api<Checkpoint>(
                        `${base}/checkpoint`,
                        json("POST", {
                          message: `Saved ${path || "workspace"}`,
                        }),
                      );
                      setCheckpoints((previous) => [checkpoint, ...previous]);
                      setNotice(
                        "Checkpoint saved. You can compare later changes.",
                      );
                    })
                  }
                >
                  Save checkpoint
                </button>
                {checkpoints.length > 0 && (
                  <button
                    className={button}
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void action("Comparing changes", async () => {
                        const data = await api<{
                          files: {
                            path: string;
                            status: string;
                            diff: string;
                          }[];
                          truncated: boolean;
                        }>(
                          `${base}/diff?checkpoint_id=${encodeURIComponent(checkpoints[0].id)}`,
                        );
                        setDiff(
                          data.files
                            .map(
                              (file) =>
                                `${file.status} ${file.path}\n${file.diff}`,
                            )
                            .join("\n\n") ||
                            "No changes since this checkpoint.",
                        );
                        if (data.truncated)
                          setNotice("Some diff output was limited.");
                      })
                    }
                  >
                    Compare changes
                  </button>
                )}
              </div>
              {!capabilities?.execution_available && (
                <p className="text-xs text-gray-500">
                  {capabilities?.execution_detail ||
                    "Execution is unavailable. Files, checkpoints and previews still work."}
                </p>
              )}
              <form
                className="flex flex-wrap gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  void action("Running", async () => {
                    if (dirty) await save();
                    setResult(null);
                    const data = await api<RunResult>(
                      `${base}/run`,
                      json("POST", { command, language, timeout_s: 60 }),
                    );
                    setResult(data);
                    await loadTree(selectedId);
                  });
                }}
              >
                <select
                  aria-label="Run language"
                  className={`${field} !w-auto`}
                  value={language}
                  onChange={(event) =>
                    setLanguage(event.target.value as typeof language)
                  }
                >
                  <option value="shell">Terminal</option>
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                </select>
                <input
                  aria-label="Command or code to run"
                  value={command}
                  onChange={(event) => setCommand(event.target.value)}
                  className={`${field} flex-1 min-w-[120px] font-mono`}
                  placeholder={
                    language === "shell" ? "python main.py" : "print('Hello')"
                  }
                />
                <button
                  className={`${button} !bg-amber-600 !text-white`}
                  disabled={
                    !command.trim() ||
                    !capabilities?.execution_available ||
                    Boolean(busy)
                  }
                >
                  {busy === "Running" ? "Running…" : "Run"}
                </button>
              </form>
              {result && (
                <div role="status" className="space-y-2">
                  <p
                    className={`text-xs ${result.exit_code === 0 ? "text-emerald-600" : "text-red-600"}`}
                  >
                    {result.timed_out
                      ? "Time limit reached"
                      : `Exit ${result.exit_code}`}{" "}
                    · {(result.duration_ms / 1000).toFixed(1)}s
                    {result.truncated ? " · output limited" : ""}
                  </p>
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs rounded-lg bg-zinc-900 text-gray-100 p-3 max-h-52 overflow-auto">
                    {result.stdout || "No standard output."}
                    {result.stderr ? `\n\n${result.stderr}` : ""}
                  </pre>
                  {result.changed_files?.length > 0 && (
                    <p className="text-xs text-gray-500">
                      Changed: {result.changed_files.join(", ")}
                    </p>
                  )}
                </div>
              )}
              {diff && (
                <pre className="whitespace-pre-wrap break-words text-xs font-mono p-3 bg-gray-50 dark:bg-zinc-900 max-h-56 overflow-auto">
                  {diff}
                </pre>
              )}
              {capabilities?.hardware_inspection && (
                <button
                  className="text-xs text-gray-500 underline"
                  onClick={() =>
                    void action("Inspecting hardware", async () =>
                      setHardware(
                        await api<Record<string, unknown>>("/hardware"),
                      ),
                    )
                  }
                >
                  Inspect available hardware
                </button>
              )}
              {hardware && (
                <p className="text-xs text-gray-500">
                  {String(hardware.cpu_count)} CPU cores ·{" "}
                  {typeof hardware.memory_total_bytes === "number"
                    ? (hardware.memory_total_bytes / 1024 ** 3).toFixed(1)
                    : "—"}{" "}
                  GB memory ·{" "}
                  {Array.isArray(hardware.gpus) ? hardware.gpus.length : 0}{" "}
                  GPU(s)
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
