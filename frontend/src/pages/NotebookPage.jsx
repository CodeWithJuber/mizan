/**
 * Notebook Page (Kitab - كِتَاب - The Book)
 * Interactive computational notebooks — like MoltBook but Quranic
 * "Read! In the name of your Lord who created" — 96:1
 */

import { useState, useEffect, useCallback, useRef } from "react";

export default function NotebookPage({ api, addTerminalLine }) {
  const [notebooks, setNotebooks] = useState([]);
  const [activeNotebook, setActiveNotebook] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newLang, setNewLang] = useState("python");
  const [editingCell, setEditingCell] = useState(null);
  const [cellSource, setCellSource] = useState("");

  const loadNotebooks = useCallback(async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "list",
      });
      setNotebooks(data.notebooks || []);
    } catch {}
  }, [api]);

  const loadNotebook = useCallback(async (id) => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "get", notebook_id: id,
      });
      if (!data.error) setActiveNotebook(data);
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
        setActiveNotebook(data);
        setShowCreate(false);
        setNewTitle("");
        loadNotebooks();
        addTerminalLine?.(`Kitab created: ${newTitle}`, "gold");
      }
    } catch {}
  };

  const addCell = async (type = "code") => {
    if (!activeNotebook) return;
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "add_cell",
        notebook_id: activeNotebook.id, cell_type: type, source: "",
      });
      loadNotebook(activeNotebook.id);
    } catch {}
  };

  const executeCell = async (cellId) => {
    if (!activeNotebook) return;
    addTerminalLine?.("Executing cell...", "info");
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "execute_cell",
        notebook_id: activeNotebook.id, cell_id: cellId,
      });
      loadNotebook(activeNotebook.id);
      if (data.cell?.status === "error") {
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

  const updateCell = async (cellId) => {
    try {
      await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "update_cell",
        notebook_id: activeNotebook.id, cell_id: cellId, source: cellSource,
      });
      setEditingCell(null);
      loadNotebook(activeNotebook.id);
    } catch {}
  };

  const exportNotebook = async (format) => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "kitab_notebook", action: "export",
        notebook_id: activeNotebook.id, format,
      });
      addTerminalLine?.(`Exported: ${data.exported}`, "gold");
    } catch {}
  };

  // Notebook list view
  if (!activeNotebook) {
    return (
      <>
        <div className="panel-header">
          <div className="panel-title">Notebooks · كِتَاب (Kitab)</div>
          <button className="btn primary" onClick={() => setShowCreate(true)}>
            + New Notebook
          </button>
        </div>
        <div style={{ padding: "4px 16px 8px", fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
          "Read! In the name of your Lord who created" — Quran 96:1
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12, padding: 16, overflow: "auto", flex: 1 }}>
          {notebooks.map(nb => (
            <div key={nb.id} className="agent-card" onClick={() => loadNotebook(nb.id)}
              style={{ cursor: "pointer" }}>
              <div style={{ fontFamily: "Georgia, serif", fontSize: 20, color: "var(--gold)", marginBottom: 8 }}>كتاب</div>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 13, color: "var(--text-primary)", fontWeight: 600 }}>{nb.title}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{nb.description}</div>
              <div style={{ display: "flex", gap: 12, marginTop: 10 }}>
                <div className="stat" style={{ flex: 1 }}>
                  <span className="stat-value">{nb.cell_count}</span>
                  <span className="stat-label">Cells</span>
                </div>
                <div className="stat" style={{ flex: 1 }}>
                  <span className="stat-value">{nb.language}</span>
                  <span className="stat-label">Language</span>
                </div>
                <div className="stat" style={{ flex: 1 }}>
                  <span className="stat-value">v{nb.version}</span>
                  <span className="stat-label">Version</span>
                </div>
              </div>
            </div>
          ))}
          {notebooks.length === 0 && (
            <div className="empty-state" style={{ gridColumn: "1/-1" }}>
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
                <span style={{ fontFamily: "Georgia", fontSize: 22, color: "var(--gold)" }}>كتاب</span>
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
                <button className="btn" onClick={() => setShowCreate(false)}>Cancel</button>
                <button className="btn primary" onClick={createNotebook} disabled={!newTitle}>Create</button>
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
      <div className="panel-header">
        <button className="btn" onClick={() => setActiveNotebook(null)} style={{ fontSize: 10 }}>Back</button>
        <div className="panel-title">{activeNotebook.title} · كتاب</div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn" onClick={() => addCell("code")} style={{ fontSize: 10 }}>+ Code</button>
          <button className="btn" onClick={() => addCell("markdown")} style={{ fontSize: 10 }}>+ Markdown</button>
          <button className="btn primary" onClick={executeAll} style={{ fontSize: 10 }}>Run All</button>
          <button className="btn" onClick={() => exportNotebook("markdown")} style={{ fontSize: 10 }}>Export</button>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
        {(activeNotebook.cells || []).map((cell, i) => (
          <div key={cell.id} style={{
            marginBottom: 12, border: "1px solid var(--border)", borderRadius: 8,
            background: "rgba(10,21,32,0.8)", overflow: "hidden",
            borderLeft: `3px solid ${cell.cell_type === "markdown" ? "var(--sapphire)" : cell.status === "error" ? "var(--ruby)" : cell.status === "success" ? "var(--emerald)" : "var(--gold)"}`,
          }}>
            {/* Cell header */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
              background: "rgba(6,12,16,0.5)", borderBottom: "1px solid rgba(30,58,85,0.3)" }}>
              <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                [{i}] {cell.cell_type}
              </span>
              {cell.execution_count > 0 && (
                <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                  run: {cell.execution_count}
                </span>
              )}
              <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                {cell.cell_type !== "markdown" && (
                  <button className="btn primary" style={{ fontSize: 9, padding: "2px 8px" }}
                    onClick={() => executeCell(cell.id)}>Run</button>
                )}
                <button className="btn" style={{ fontSize: 9, padding: "2px 8px" }}
                  onClick={() => { setEditingCell(cell.id); setCellSource(cell.source); }}>Edit</button>
              </div>
            </div>

            {/* Cell source */}
            {editingCell === cell.id ? (
              <div style={{ padding: 8 }}>
                <textarea className="form-input" style={{ fontFamily: "var(--font-mono)", fontSize: 12,
                  minHeight: 80, resize: "vertical", width: "100%" }}
                  value={cellSource} onChange={e => setCellSource(e.target.value)} />
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <button className="btn primary" style={{ fontSize: 10 }} onClick={() => updateCell(cell.id)}>Save</button>
                  <button className="btn" style={{ fontSize: 10 }} onClick={() => setEditingCell(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <pre style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 12,
                color: cell.cell_type === "markdown" ? "var(--text-secondary)" : "var(--emerald)",
                whiteSpace: "pre-wrap", margin: 0, lineHeight: 1.5 }}>
                {cell.source || "(empty)"}
              </pre>
            )}

            {/* Cell outputs */}
            {cell.outputs?.length > 0 && cell.outputs.map((out, oi) => (
              <div key={oi} style={{ borderTop: "1px solid rgba(30,58,85,0.3)",
                padding: "8px 12px", background: "rgba(3,6,8,0.5)" }}>
                {out.output_type === "error" ? (
                  <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ruby)",
                    whiteSpace: "pre-wrap", margin: 0 }}>{out.text || out.stderr}</pre>
                ) : (
                  <>
                    {out.stdout && (
                      <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11,
                        color: "var(--text-primary)", whiteSpace: "pre-wrap", margin: 0 }}>{out.stdout}</pre>
                    )}
                    {out.stderr && (
                      <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11,
                        color: "var(--amber)", whiteSpace: "pre-wrap", margin: 0 }}>{out.stderr}</pre>
                    )}
                  </>
                )}
                {out.execution_time != null && (
                  <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 4 }}>
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
