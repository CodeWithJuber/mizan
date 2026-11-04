/**
 * Notebook Page (Kitab - كِتَاب - The Book)
 * Interactive computational notebooks — like MoltBook but Quranic
 * "Read! In the name of your Lord who created" — 96:1
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { PageProps, Notebook } from "../types";
import { useToast } from "../components/Toast";
import { confirmDialog } from "@/components/ui/confirm";

const CELL_BORDER_COLOR: Record<string, string> = {
  markdown: "border-l-blue-500",
  error: "border-l-red-500",
  success: "border-l-emerald-500",
  default: "border-l-mizan-gold",
};

export default function NotebookPage({ api, addTerminalLine }: PageProps) {
  const { addToast } = useToast();
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [activeNotebook, setActiveNotebook] = useState<Notebook | null>(null);
  const [showCreate, setShowCreate] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>("");
  const [newLang, setNewLang] = useState<string>("python");
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [cellSource, setCellSource] = useState<string>("");
  const [executingCell, setExecutingCell] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<string>("markdown");
  const [createError, setCreateError] = useState<string>("");

  // Guards for the Back-mid-execution race (#14): handlers capture the
  // notebook id they started with and skip setActiveNotebook if the user
  // navigated away (or the component unmounted) while awaiting.
  const mountedRef = useRef(true);
  const openNotebookRef = useRef<string | null>(null);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const closeNotebook = useCallback(() => {
    openNotebookRef.current = null;
    setActiveNotebook(null);
  }, []);

  const loadNotebooks = useCallback(async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "list",
      });
      if (!mountedRef.current) return;
      setNotebooks((data.notebooks || []) as Notebook[]);
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not load notebooks. Try again.",
      });
    }
  }, [api, addToast]);

  // Refresh the currently-open notebook. Skips setActiveNotebook when the
  // user has navigated away mid-request (Back button sets openNotebookRef
  // to null), so a slow execute can't pull them back in.
  const loadNotebook = useCallback(
    async (id: string) => {
      try {
        const data = await api.post("/skills/execute", {
          skill: "kitab_notebook",
          action: "get",
          notebook_id: id,
        });
        if (!mountedRef.current) return;
        if ((data as Record<string, unknown>).error) return;
        if (openNotebookRef.current !== id) return;
        setActiveNotebook(data as unknown as Notebook);
      } catch (e) {
        addToast({
          type: "error",
          title: (e as Error).message || "Could not refresh the notebook. Try again.",
        });
      }
    },
    [api, addToast],
  );

  // Open a notebook from the list view (claims the id before fetching).
  const openNotebookById = useCallback(
    async (id: string) => {
      openNotebookRef.current = id;
      try {
        const data = await api.post("/skills/execute", {
          skill: "kitab_notebook",
          action: "get",
          notebook_id: id,
        });
        if (!mountedRef.current) return;
        if ((data as Record<string, unknown>).error) {
          openNotebookRef.current = null;
          addToast({ type: "error", title: "Could not open the notebook" });
          return;
        }
        setActiveNotebook(data as unknown as Notebook);
      } catch (e) {
        openNotebookRef.current = null;
        addToast({
          type: "error",
          title: (e as Error).message || "Could not open the notebook",
        });
      }
    },
    [api, addToast],
  );

  useEffect(() => {
    loadNotebooks();
  }, [loadNotebooks]);

  const createNotebook = async () => {
    if (!newTitle.trim()) {
      setCreateError(
        "Enter a notebook title. A notebook needs a title.",
      );
      return;
    }
    setCreateError("");
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "create",
        title: newTitle.trim(),
        language: newLang,
      });
      if (!mountedRef.current) return;
      if (data.id) {
        openNotebookRef.current = data.id as string;
        setActiveNotebook(data as unknown as Notebook);
        setShowCreate(false);
        setNewTitle("");
        loadNotebooks();
        addToast({ type: "success", title: "Notebook created" });
        addTerminalLine?.(`Kitab created: ${newTitle.trim()}`, "gold");
      } else {
        addToast({ type: "error", title: "Could not create the notebook" });
      }
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not create the notebook",
      });
    }
  };

  const deleteNotebook = async (id: string, title: string) => {
    if (
      !(await confirmDialog({
        title: `Delete the notebook "${title}"?`,
        description: "It cannot be restored.",
        destructive: true,
      }))
    )
      return;
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "delete",
        notebook_id: id,
      });
      if ((data as Record<string, unknown>).deleted) {
        if (openNotebookRef.current === id) closeNotebook();
        loadNotebooks();
        addToast({ type: "success", title: "Notebook deleted" });
      } else {
        addToast({ type: "error", title: "Could not delete the notebook" });
      }
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not delete the notebook",
      });
    }
  };

  const addCell = async (type: string = "code") => {
    const nbId = openNotebookRef.current;
    if (!nbId) return;
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "add_cell",
        notebook_id: nbId,
        cell_type: type,
        source: "",
      });
      loadNotebook(nbId);
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not add the cell",
      });
    }
  };

  const executeCell = async (cellId: string) => {
    const nbId = openNotebookRef.current;
    if (!nbId) return;
    setExecutingCell(cellId);
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "execute_cell",
        notebook_id: nbId,
        cell_id: cellId,
      });
      if (openNotebookRef.current === nbId) loadNotebook(nbId);
      const cell = (data as Record<string, unknown>).cell as
        Record<string, unknown> | undefined;
      if (!cell) {
        addToast({
          type: "error",
          title: "The cell did not run. Try again.",
        });
      } else if (cell?.status === "error") {
        addToast({ type: "error", title: "The cell finished with an error" });
      } else {
        addToast({ type: "success", title: "Cell ran" });
      }
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "The cell did not run",
      });
    } finally {
      if (mountedRef.current) setExecutingCell(null);
    }
  };

  const executeAll = async () => {
    const nbId = openNotebookRef.current;
    if (!nbId) return;
    setExecutingCell("all");
    addTerminalLine?.("Executing all cells...", "info");
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "execute_all",
        notebook_id: nbId,
      });
      if (openNotebookRef.current === nbId) loadNotebook(nbId);
      addToast({ type: "success", title: "All cells ran" });
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not run all cells",
      });
    } finally {
      if (mountedRef.current) setExecutingCell(null);
    }
  };

  const updateCell = async (cellId: string) => {
    const nbId = openNotebookRef.current;
    if (!nbId) return;
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "update_cell",
        notebook_id: nbId,
        cell_id: cellId,
        source: cellSource,
      });
      setEditingCell(null);
      loadNotebook(nbId);
      addToast({ type: "success", title: "Cell saved" });
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not save the cell",
      });
    }
  };

  const exportNotebook = async () => {
    const nbId = openNotebookRef.current;
    if (!nbId) return;
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook",
        action: "export",
        notebook_id: nbId,
        format: exportFormat,
      });
      const rec = data as Record<string, unknown>;
      if (rec.error) {
        addToast({ type: "error", title: "Could not export the notebook" });
        return;
      }
      // Backend sirf server path return karta hai, file content nahi —
      // isliye honest toast: file server pe save hui hai.
      addToast({
        type: "success",
        title: "Saved on the server",
        description: String(rec.exported || ""),
      });
      addTerminalLine?.(`Exported: ${rec.exported}`, "gold");
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Could not export the notebook",
      });
    }
  };

  // Notebook list view
  if (!activeNotebook) {
    return (
      <div className="page-wrapper">
        <div className="page-header">
          <div>
            <h2 className="page-title">Notebooks</h2>
            <p className="page-description">
              كِتَاب (Kitab) — Interactive computation
            </p>
          </div>
          <button
            className="btn-gold btn-sm"
            onClick={() => setShowCreate(true)}
          >
            + New Notebook
          </button>
        </div>

        <div className="quran-quote">
          "Read! In the name of your Lord who created" — Quran 96:1
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          <div className="card-grid">
            {notebooks.map((nb) => (
              <div
                key={nb.id}
                role="button"
                tabIndex={0}
                className="card-hover cursor-pointer"
                onClick={() => openNotebookById(nb.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    openNotebookById(nb.id);
                  }
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xl font-arabic text-mizan-gold/60 mb-2">
                    كتاب
                  </div>
                  <button
                    className="btn-danger btn-sm shrink-0"
                    title="Delete notebook"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteNotebook(nb.id, nb.title);
                    }}
                  >
                    🗑
                  </button>
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {nb.title}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {nb.description}
                </div>
                <div className="flex gap-3 mt-3">
                  <div className="stat flex-1">
                    <span className="stat-value">{nb.cell_count}</span>
                    <span className="stat-label">Cells</span>
                  </div>
                  <div className="stat flex-1">
                    <span className="stat-value">{nb.language}</span>
                    <span className="stat-label">Language</span>
                  </div>
                  <div className="stat flex-1">
                    <span className="stat-value">v{nb.version}</span>
                    <span className="stat-label">Version</span>
                  </div>
                </div>
              </div>
            ))}
            {notebooks.length === 0 && (
              <div className="empty-state col-span-full">
                <div className="empty-arabic">كتاب</div>
                <div className="empty-text">No notebooks yet</div>
                <div className="empty-sub">
                  Click "+ New Notebook", then add your first cell with "+ Code"
                </div>
              </div>
            )}
          </div>
        </div>

        {showCreate && (
          <div
            className="modal-overlay"
            onClick={async () => {
              if (
                !newTitle.trim() ||
                await confirmDialog({ title: "Discard the new notebook?", confirmLabel: "Discard" })
              ) {
                setShowCreate(false);
              }
            }}
          >
            <div
              className="modal"
              role="dialog"
              aria-modal="true"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal-title">
                <span className="font-arabic text-2xl text-mizan-gold">
                  كتاب
                </span>
                New Kitab Notebook
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="notebook-title">
                  Title
                </label>
                <input
                  id="notebook-title"
                  className="form-input"
                  placeholder="e.g., Data Analysis"
                  value={newTitle}
                  onChange={(e) => {
                    setNewTitle(e.target.value);
                    if (createError) setCreateError("");
                  }}
                />
                {createError && (
                  <div className="text-xs text-red-500 dark:text-red-400 mt-1">
                    {createError}
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="notebook-lang">
                  Language
                </label>
                <select
                  id="notebook-lang"
                  className="form-select"
                  value={newLang}
                  onChange={(e) => setNewLang(e.target.value)}
                >
                  <option value="python">Python</option>
                  <option value="shell">Shell</option>
                </select>
              </div>
              <div className="modal-footer">
                <button
                  className="btn-secondary"
                  onClick={() => setShowCreate(false)}
                >
                  Cancel
                </button>
                <button className="btn-gold" onClick={createNotebook}>
                  Create
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Active notebook view
  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div className="flex items-center gap-3">
          <button className="btn-secondary btn-sm" onClick={closeNotebook}>
            Back
          </button>
          <div>
            <h2 className="page-title text-base">{activeNotebook.title}</h2>
            <p className="page-description text-xs mt-0">كتاب</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-secondary btn-sm min-h-[44px]"
            onClick={() => addCell("code")}
          >
            + Code
          </button>
          <button
            className="btn-secondary btn-sm min-h-[44px]"
            onClick={() => addCell("markdown")}
          >
            + Markdown
          </button>
          <button className="btn-gold btn-sm min-h-[44px]" onClick={executeAll}>
            {executingCell === "all" ? "Running…" : "Run All"}
          </button>
          <select
            className="form-select btn-sm min-h-[44px] w-auto"
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value)}
            title="Export format"
          >
            <option value="markdown">Markdown</option>
            <option value="python">Python</option>
            <option value="json">JSON</option>
          </select>
          <button
            className="btn-secondary btn-sm min-h-[44px]"
            onClick={exportNotebook}
          >
            Export
          </button>
        </div>
      </div>

      <div className="page-body">
        {(activeNotebook.cells || []).length === 0 && (
          <div className="empty-state">
            <div className="empty-arabic">✦</div>
            <div className="empty-text">This notebook is empty</div>
            <div className="empty-sub">
              Click "+ Code" above to add your first cell, then Run it
            </div>
          </div>
        )}
        {(activeNotebook.cells || []).map((cell, i) => {
          const borderColor =
            cell.cell_type === "markdown"
              ? CELL_BORDER_COLOR.markdown
              : cell.status === "error"
                ? CELL_BORDER_COLOR.error
                : cell.status === "success"
                  ? CELL_BORDER_COLOR.success
                  : CELL_BORDER_COLOR.default;

          return (
            <div
              key={cell.id}
              className={`card border-l-4 ${borderColor} overflow-hidden p-0`}
            >
              {/* Cell header */}
              <div className="flex items-center gap-2 px-3 py-2 bg-muted/60 border-b border-border">
                <span className="text-micro font-mono text-muted-foreground/80">
                  [{i}] {cell.cell_type}
                </span>
                {cell.execution_count != null && cell.execution_count > 0 && (
                  <span className="text-micro font-mono text-muted-foreground/80">
                    run: {cell.execution_count}
                  </span>
                )}
                {executingCell === cell.id && (
                  <span className="text-micro font-mono text-mizan-gold animate-pulse">
                    Running…
                  </span>
                )}
                <div className="ml-auto flex gap-1">
                  {cell.cell_type !== "markdown" && (
                    <button
                      className="btn-gold btn-sm text-micro px-2 py-0.5 min-h-[36px]"
                      onClick={() => executeCell(cell.id)}
                      disabled={executingCell !== null}
                    >
                      {executingCell === cell.id ? "…" : "Run"}
                    </button>
                  )}
                  <button
                    className="btn-secondary btn-sm text-micro px-2 py-0.5 min-h-[36px]"
                    onClick={() => {
                      setEditingCell(cell.id);
                      setCellSource(cell.source);
                    }}
                  >
                    Edit
                  </button>
                </div>
              </div>

              {/* Cell source */}
              {editingCell === cell.id ? (
                <div className="p-3">
                  <textarea
                    className="form-input font-mono text-xs min-h-[80px] resize-y w-full"
                    value={cellSource}
                    onChange={(e) => setCellSource(e.target.value)}
                  />
                  <div className="flex gap-2 mt-2">
                    <button
                      className="btn-gold btn-sm"
                      onClick={() => updateCell(cell.id)}
                    >
                      Save
                    </button>
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => setEditingCell(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <pre
                  className={`px-3 py-2 font-mono text-xs whitespace-pre-wrap wrap-break-word leading-relaxed m-0
                  ${
                    cell.cell_type === "markdown"
                      ? "text-muted-foreground"
                      : "text-emerald-600 dark:text-emerald-400"
                  }`}
                >
                  {cell.source || "(empty)"}
                </pre>
              )}

              {/* Cell outputs */}
              {cell.outputs?.length != null &&
                cell.outputs.length > 0 &&
                cell.outputs.map((out, oi) => (
                  <div
                    key={oi}
                    className="border-t border-border px-3 py-2 bg-muted/50"
                  >
                    {out.output_type === "error" ? (
                      <pre className="font-mono text-xs text-red-500 dark:text-red-400 whitespace-pre-wrap wrap-break-word m-0">
                        {out.text || out.stderr}
                      </pre>
                    ) : (
                      <>
                        {out.stdout && (
                          <pre className="font-mono text-xs text-foreground/90 whitespace-pre-wrap wrap-break-word m-0">
                            {out.stdout}
                          </pre>
                        )}
                        {out.stderr && (
                          <pre className="font-mono text-xs text-amber-600 dark:text-amber-400 whitespace-pre-wrap wrap-break-word m-0">
                            {out.stderr}
                          </pre>
                        )}
                      </>
                    )}
                    {out.execution_time != null && (
                      <div className="text-micro text-muted-foreground/80 font-mono mt-1">
                        {out.execution_time.toFixed(2)}s
                      </div>
                    )}
                  </div>
                ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
