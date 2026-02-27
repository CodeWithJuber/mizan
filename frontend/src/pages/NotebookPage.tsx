/**
 * Notebook Page (Kitab - كِتَاب - The Book)
 * Interactive computational notebooks — like MoltBook but Quranic
 * "Read! In the name of your Lord who created" — 96:1
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, Notebook, NotebookCell, CellOutput } from "../types";

const CELL_BORDER_COLOR: Record<string, string> = {
  markdown: "border-l-blue-500",
  error: "border-l-red-500",
  success: "border-l-emerald-500",
  default: "border-l-mizan-gold",
};

export default function NotebookPage({ api, addTerminalLine }: PageProps) {
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [activeNotebook, setActiveNotebook] = useState<Notebook | null>(null);
  const [showCreate, setShowCreate] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>("");
  const [newLang, setNewLang] = useState<string>("python");
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [cellSource, setCellSource] = useState<string>("");

  const loadNotebooks = useCallback(async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "list",
      });
      setNotebooks((data.notebooks || []) as Notebook[]);
    } catch {}
  }, [api]);

  const loadNotebook = useCallback(async (id: string) => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "get", notebook_id: id,
      });
      if (!(data as Record<string, unknown>).error) setActiveNotebook(data as unknown as Notebook);
    } catch {}
  }, [api]);

  useEffect(() => { loadNotebooks(); }, [loadNotebooks]);

  const createNotebook = async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "create",
        title: newTitle, language: newLang,
      });
      if (data.id) {
        setActiveNotebook(data as unknown as Notebook);
        setShowCreate(false);
        setNewTitle("");
        loadNotebooks();
        addTerminalLine?.(`Kitab created: ${newTitle}`, "gold");
      }
    } catch {}
  };

  const addCell = async (type: string = "code") => {
    if (!activeNotebook) return;
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "add_cell",
        notebook_id: activeNotebook.id, cell_type: type, source: "",
      });
      loadNotebook(activeNotebook.id);
    } catch {}
  };

  const executeCell = async (cellId: string) => {
    if (!activeNotebook) return;
    addTerminalLine?.("Executing cell...", "info");
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "execute_cell",
        notebook_id: activeNotebook.id, cell_id: cellId,
      });
      loadNotebook(activeNotebook.id);
      const cell = (data as Record<string, unknown>).cell as Record<string, unknown> | undefined;
      if (cell?.status === "error") {
        addTerminalLine?.("Cell execution error", "error");
      } else {
        addTerminalLine?.("Cell executed successfully", "gold");
      }
    } catch {}
  };

  const executeAll = async () => {
    if (!activeNotebook) return;
    addTerminalLine?.("Executing all cells...", "info");
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "execute_all",
        notebook_id: activeNotebook.id,
      });
      loadNotebook(activeNotebook.id);
      addTerminalLine?.("All cells executed", "gold");
    } catch {}
  };

  const updateCell = async (cellId: string) => {
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "update_cell",
        notebook_id: activeNotebook!.id, cell_id: cellId, source: cellSource,
      });
      setEditingCell(null);
      loadNotebook(activeNotebook!.id);
    } catch {}
  };

  const exportNotebook = async (format: string) => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "export",
        notebook_id: activeNotebook!.id, format,
      });
      addTerminalLine?.(`Exported: ${data.exported}`, "gold");
    } catch {}
  };

  // Notebook list view
  if (!activeNotebook) {
    return (
      <div className="page-wrapper">
        <div className="page-header">
          <div>
            <h2 className="page-title">Notebooks</h2>
            <p className="page-description">كِتَاب (Kitab) — Interactive computation</p>
          </div>
          <button className="btn-gold btn-sm" onClick={() => setShowCreate(true)}>
            + New Notebook
          </button>
        </div>

        <div className="quran-quote">
          "Read! In the name of your Lord who created" — Quran 96:1
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          <div className="card-grid">
            {notebooks.map(nb => (
              <div key={nb.id} className="card-hover" onClick={() => loadNotebook(nb.id)}>
                <div className="text-xl font-arabic text-mizan-gold/60 mb-2">كتاب</div>
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{nb.title}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{nb.description}</div>
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
                <div className="empty-sub">"He taught by the pen" — 96:4</div>
              </div>
            )}
          </div>
        </div>

        {showCreate && (
          <div className="modal-overlay" onClick={() => setShowCreate(false)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-title">
                <span className="font-arabic text-2xl text-mizan-gold">كتاب</span>
                New Kitab Notebook
              </div>
              <div className="form-group">
                <label className="form-label">Title</label>
                <input className="form-input" placeholder="e.g., Data Analysis" value={newTitle}
                  onChange={e => setNewTitle(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Language</label>
                <select className="form-select" value={newLang} onChange={e => setNewLang(e.target.value)}>
                  <option value="python">Python</option>
                  <option value="shell">Shell</option>
                </select>
              </div>
              <div className="modal-footer">
                <button className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
                <button className="btn-gold" onClick={createNotebook} disabled={!newTitle}>Create</button>
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
          <button className="btn-secondary btn-sm" onClick={() => setActiveNotebook(null)}>Back</button>
          <div>
            <h2 className="page-title text-base">{activeNotebook.title}</h2>
            <p className="page-description text-xs mt-0">كتاب</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary btn-sm" onClick={() => addCell("code")}>+ Code</button>
          <button className="btn-secondary btn-sm" onClick={() => addCell("markdown")}>+ Markdown</button>
          <button className="btn-gold btn-sm" onClick={executeAll}>Run All</button>
          <button className="btn-secondary btn-sm" onClick={() => exportNotebook("markdown")}>Export</button>
        </div>
      </div>

      <div className="page-body">
        {(activeNotebook.cells || []).map((cell, i) => {
          const borderColor = cell.cell_type === "markdown"
            ? CELL_BORDER_COLOR.markdown
            : cell.status === "error"
              ? CELL_BORDER_COLOR.error
              : cell.status === "success"
                ? CELL_BORDER_COLOR.success
                : CELL_BORDER_COLOR.default;

          return (
            <div key={cell.id} className={`card border-l-4 ${borderColor} overflow-hidden p-0`}>
              {/* Cell header */}
              <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-zinc-800 border-b border-gray-200 dark:border-zinc-700">
                <span className="text-micro font-mono text-gray-400 dark:text-gray-500">
                  [{i}] {cell.cell_type}
                </span>
                {cell.execution_count != null && cell.execution_count > 0 && (
                  <span className="text-micro font-mono text-gray-400 dark:text-gray-500">
                    run: {cell.execution_count}
                  </span>
                )}
                <div className="ml-auto flex gap-1">
                  {cell.cell_type !== "markdown" && (
                    <button className="btn-gold btn-sm text-micro px-2 py-0.5"
                      onClick={() => executeCell(cell.id)}>Run</button>
                  )}
                  <button className="btn-secondary btn-sm text-micro px-2 py-0.5"
                    onClick={() => { setEditingCell(cell.id); setCellSource(cell.source); }}>Edit</button>
                </div>
              </div>

              {/* Cell source */}
              {editingCell === cell.id ? (
                <div className="p-3">
                  <textarea className="form-input font-mono text-xs min-h-[80px] resize-y w-full"
                    value={cellSource} onChange={e => setCellSource(e.target.value)} />
                  <div className="flex gap-2 mt-2">
                    <button className="btn-gold btn-sm" onClick={() => updateCell(cell.id)}>Save</button>
                    <button className="btn-secondary btn-sm" onClick={() => setEditingCell(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <pre className={`px-3 py-2 font-mono text-xs whitespace-pre-wrap leading-relaxed m-0
                  ${cell.cell_type === "markdown"
                    ? "text-gray-600 dark:text-gray-400"
                    : "text-emerald-600 dark:text-emerald-400"
                  }`}>
                  {cell.source || "(empty)"}
                </pre>
              )}

              {/* Cell outputs */}
              {cell.outputs?.length != null && cell.outputs.length > 0 && cell.outputs.map((out, oi) => (
                <div key={oi} className="border-t border-gray-200 dark:border-zinc-700 px-3 py-2 bg-gray-50 dark:bg-zinc-800/50">
                  {out.output_type === "error" ? (
                    <pre className="font-mono text-xs text-red-500 dark:text-red-400 whitespace-pre-wrap m-0">{out.text || out.stderr}</pre>
                  ) : (
                    <>
                      {out.stdout && (
                        <pre className="font-mono text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap m-0">{out.stdout}</pre>
                      )}
                      {out.stderr && (
                        <pre className="font-mono text-xs text-amber-600 dark:text-amber-400 whitespace-pre-wrap m-0">{out.stderr}</pre>
                      )}
                    </>
                  )}
                  {out.execution_time != null && (
                    <div className="text-micro text-gray-400 dark:text-gray-500 font-mono mt-1">
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
