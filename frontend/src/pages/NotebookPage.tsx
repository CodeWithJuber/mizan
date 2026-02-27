/**
 * Notebook Page (Kitab - كِتَاب - The Book)
 * Interactive computational notebooks — like MoltBook but Quranic
 * "Read! In the name of your Lord who created" — 96:1
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { PageProps, Notebook, NotebookCell, CellOutput } from "../types";

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
      <>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
          <h2 className="page-title">Notebooks · كِتَاب (Kitab)</h2>
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + New Notebook
          </button>
        </div>
        <div className="px-4 pb-2 pt-1 text-xs text-gray-500 dark:text-gray-400 italic">
          "Read! In the name of your Lord who created" — Quran 96:1
        </div>

        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3 p-4 overflow-auto flex-1">
          {notebooks.map(nb => (
            <div key={nb.id} className="card-hover cursor-pointer" onClick={() => loadNotebook(nb.id)}>
              <div className="font-serif text-xl text-mizan-gold mb-2">كتاب</div>
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{nb.title}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{nb.description}</div>
              <div className="flex gap-3 mt-2.5">
                <div className="text-center py-1.5 px-1 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-100 dark:border-zinc-700/50 flex-1">
                  <span className="block font-mono text-sm text-gray-900 dark:text-gray-100">{nb.cell_count}</span>
                  <span className="block text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wider">Cells</span>
                </div>
                <div className="text-center py-1.5 px-1 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-100 dark:border-zinc-700/50 flex-1">
                  <span className="block font-mono text-sm text-gray-900 dark:text-gray-100">{nb.language}</span>
                  <span className="block text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wider">Language</span>
                </div>
                <div className="text-center py-1.5 px-1 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-100 dark:border-zinc-700/50 flex-1">
                  <span className="block font-mono text-sm text-gray-900 dark:text-gray-100">v{nb.version}</span>
                  <span className="block text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wider">Version</span>
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

        {showCreate && (
          <div className="modal-overlay" onClick={() => setShowCreate(false)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-title">
                <span className="font-serif text-[22px] text-mizan-gold">كتاب</span>
                New Kitab Notebook
              </div>
              <div className="space-y-1.5 mb-4">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Title</label>
                <input className="input w-full text-sm" placeholder="e.g., Data Analysis" value={newTitle}
                  onChange={e => setNewTitle(e.target.value)} />
              </div>
              <div className="space-y-1.5 mb-4">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Language</label>
                <select className="input w-full text-sm" value={newLang} onChange={e => setNewLang(e.target.value)}>
                  <option value="python">Python</option>
                  <option value="shell">Shell</option>
                </select>
              </div>
              <div className="modal-footer">
                <button className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
                <button className="btn-primary" onClick={createNotebook} disabled={!newTitle}>Create</button>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  // Active notebook view
  return (
    <>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <button className="btn-secondary text-[10px]" onClick={() => setActiveNotebook(null)}>Back</button>
        <h2 className="page-title">{activeNotebook.title} · كتاب</h2>
        <div className="flex gap-1.5">
          <button className="btn-secondary text-[10px]" onClick={() => addCell("code")}>+ Code</button>
          <button className="btn-secondary text-[10px]" onClick={() => addCell("markdown")}>+ Markdown</button>
          <button className="btn-primary text-[10px]" onClick={executeAll}>Run All</button>
          <button className="btn-secondary text-[10px]" onClick={() => exportNotebook("markdown")}>Export</button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {(activeNotebook.cells || []).map((cell, i) => (
          <div key={cell.id} className="mb-3 border border-gray-200 dark:border-zinc-800 rounded-lg bg-white dark:bg-zinc-900 overflow-hidden"
            style={{
              borderLeft: `3px solid ${cell.cell_type === "markdown" ? "#3b82f6" : cell.status === "error" ? "#ef4444" : cell.status === "success" ? "#10b981" : "#c9a227"}`,
            }}>
            <div className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-50 dark:bg-zinc-800/50 border-b border-gray-200 dark:border-zinc-800">
              <span className="text-[9px] font-mono text-gray-500 dark:text-gray-400">
                [{i}] {cell.cell_type}
              </span>
              {cell.execution_count != null && cell.execution_count > 0 && (
                <span className="text-[9px] font-mono text-gray-500 dark:text-gray-400">
                  run: {cell.execution_count}
                </span>
              )}
              <div className="ml-auto flex gap-1">
                {cell.cell_type !== "markdown" && (
                  <button className="btn-primary text-[9px] px-2 py-0.5"
                    onClick={() => executeCell(cell.id)}>Run</button>
                )}
                <button className="btn-secondary text-[9px] px-2 py-0.5"
                  onClick={() => { setEditingCell(cell.id); setCellSource(cell.source); }}>Edit</button>
              </div>
            </div>

            {editingCell === cell.id ? (
              <div className="p-2">
                <textarea className="input w-full font-mono text-xs min-h-[80px] resize-y"
                  value={cellSource} onChange={e => setCellSource(e.target.value)} />
                <div className="flex gap-1.5 mt-1.5">
                  <button className="btn-primary text-[10px]" onClick={() => updateCell(cell.id)}>Save</button>
                  <button className="btn-secondary text-[10px]" onClick={() => setEditingCell(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <pre className={`px-3 py-2 font-mono text-xs whitespace-pre-wrap m-0 leading-relaxed ${
                cell.cell_type === "markdown" ? "text-gray-600 dark:text-gray-300" : "text-emerald-500"
              }`}>
                {cell.source || "(empty)"}
              </pre>
            )}

            {cell.outputs?.length != null && cell.outputs.length > 0 && cell.outputs.map((out, oi) => (
              <div key={oi} className="border-t border-gray-200 dark:border-zinc-800 px-3 py-2 bg-gray-50 dark:bg-zinc-800/50">
                {out.output_type === "error" ? (
                  <pre className="font-mono text-xs text-red-500 whitespace-pre-wrap m-0">{out.text || out.stderr}</pre>
                ) : (
                  <>
                    {out.stdout && (
                      <pre className="font-mono text-xs text-gray-900 dark:text-gray-100 whitespace-pre-wrap m-0">{out.stdout}</pre>
                    )}
                    {out.stderr && (
                      <pre className="font-mono text-xs text-amber-500 whitespace-pre-wrap m-0">{out.stderr}</pre>
                    )}
                  </>
                )}
                {out.execution_time != null && (
                  <div className="text-[9px] text-gray-500 dark:text-gray-400 font-mono mt-1">
                    {out.execution_time.toFixed(2)}s
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}
