/**
 * Security Scanner Page (Raqib - رَقِيب - The Watcher)
 * "Not a word does he utter but there is a watcher (Raqib) ready" — 50:18
 */

import { useState, useEffect, useCallback } from "react";

const SEVERITY_COLORS = {
  critical: "#dc2626",
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#3b82f6",
  info: "#6b7280",
};

const SEVERITY_BG = {
  critical: "rgba(220,38,38,0.15)",
  high: "rgba(239,68,68,0.15)",
  medium: "rgba(245,158,11,0.15)",
  low: "rgba(59,130,246,0.15)",
  info: "rgba(107,114,128,0.15)",
};

export default function ScannerPage({ api, addTerminalLine }) {
  const [scanning, setScanning] = useState(false);
  const [scanPath, setScanPath] = useState("/home/user/mizan");
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [activeTab, setActiveTab] = useState("scan");
  const [scanType, setScanType] = useState("full");

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "raqib_scanner", action: "history",
      });
      setHistory(data.scans || []);
    } catch {}
  }, [api]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const runScan = async () => {
    setScanning(true);
    addTerminalLine?.(`Raqib scanning: ${scanPath} (${scanType})...`, "gold");
    try {
      const data = await api.post("/skills/execute", {
        skill: "raqib_scanner", action: scanType, path: scanPath,
      });
      setReport(data);
      setActiveTab("results");
      loadHistory();
      const total = data.summary?.total_findings || data.findings?.length || 0;
      addTerminalLine?.(`Scan complete: ${total} findings`, total > 0 ? "warn" : "gold");
    } catch (e) {
      addTerminalLine?.("Scan failed", "error");
    }
    setScanning(false);
  };

  return (
    <>
      <div className="panel-header">
        <div className="panel-title">Security Scanner · رَقِيب (Raqib)</div>
      </div>
      <div style={{ padding: "4px 16px 8px", fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
        "Not a word does he utter but there is a watcher (Raqib) ready" — Quran 50:18
      </div>

      <div className="tab-bar">
        {[
          { id: "scan", label: "New Scan" },
          { id: "results", label: "Results" },
          { id: "history", label: "History" },
        ].map(tab => (
          <div key={tab.id} className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </div>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
        {activeTab === "scan" && (
          <div style={{ maxWidth: 600 }}>
            <div className="form-group">
              <label className="form-label">Target Path</label>
              <input className="form-input" value={scanPath}
                onChange={e => setScanPath(e.target.value)}
                placeholder="/path/to/project" />
            </div>

            <div className="form-group">
              <label className="form-label">Scan Type</label>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {[
                  { id: "full", label: "Full Scan", desc: "All checks combined" },
                  { id: "secrets", label: "Secret Scan", desc: "Leaked credentials" },
                  { id: "code", label: "Code Scan", desc: "OWASP vulnerabilities" },
                  { id: "deps", label: "Dependency Audit", desc: "Known CVEs" },
                  { id: "config", label: "Config Check", desc: "Misconfigurations" },
                  { id: "docker", label: "Docker Scan", desc: "Dockerfile issues" },
                ].map(st => (
                  <button key={st.id}
                    className={`btn ${scanType === st.id ? "primary" : ""}`}
                    style={{ flex: "1 0 45%", justifyContent: "center", flexDirection: "column", alignItems: "center", padding: "10px 12px" }}
                    onClick={() => setScanType(st.id)}>
                    <span style={{ fontSize: 11 }}>{st.label}</span>
                    <span style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 2 }}>{st.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            <button className="btn primary" style={{ width: "100%", justifyContent: "center", padding: "12px", marginTop: 12 }}
              onClick={runScan} disabled={scanning || !scanPath}>
              {scanning ? "Scanning..." : "Start Raqib Scan"}
            </button>
          </div>
        )}

        {activeTab === "results" && report && (
          <>
            {/* Summary */}
            {report.summary && (
              <div style={{ marginBottom: 16, padding: 16,
                background: "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
                border: "1px solid var(--border)", borderRadius: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <div style={{ fontFamily: "Georgia, serif", fontSize: 28, color: "var(--gold)" }}>رقيب</div>
                  <div>
                    <div style={{ fontFamily: "var(--font-display)", fontSize: 14, color: "var(--text-primary)" }}>
                      Scan Report
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                      {report.scan_type} · {report.target}
                    </div>
                  </div>
                  <div style={{ marginLeft: "auto", textAlign: "right" }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 24,
                      color: (report.summary.risk_score || 0) > 50 ? "var(--ruby)" :
                             (report.summary.risk_score || 0) > 20 ? "var(--amber)" : "var(--emerald)" }}>
                      {(report.summary.risk_score || 0).toFixed(0)}
                    </div>
                    <div style={{ fontSize: 9, color: "var(--text-muted)" }}>RISK SCORE</div>
                  </div>
                </div>

                {/* Verdict */}
                {report.summary.verdict && (
                  <div style={{ padding: "8px 12px", background: "rgba(201,162,39,0.05)",
                    border: "1px solid rgba(201,162,39,0.15)", borderRadius: 6,
                    fontSize: 12, color: "var(--gold)", fontStyle: "italic", marginBottom: 12 }}>
                    {report.summary.verdict}
                  </div>
                )}

                {/* Severity breakdown */}
                <div style={{ display: "flex", gap: 8 }}>
                  {Object.entries(report.summary.by_severity || {}).map(([sev, count]) => (
                    <div key={sev} style={{ flex: 1, textAlign: "center", padding: "8px",
                      background: count > 0 ? SEVERITY_BG[sev] : "rgba(6,12,16,0.5)",
                      borderRadius: 6, border: `1px solid ${count > 0 ? SEVERITY_COLORS[sev] + "40" : "rgba(30,58,85,0.3)"}` }}>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 18,
                        color: count > 0 ? SEVERITY_COLORS[sev] : "var(--text-muted)" }}>{count}</div>
                      <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.1em",
                        color: "var(--text-muted)" }}>{sev}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Findings */}
            <div style={{ fontFamily: "var(--font-display)", fontSize: 10, letterSpacing: "0.2em",
              color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
              Findings ({(report.findings || []).length})
            </div>

            {(report.findings || []).map((finding, i) => (
              <div key={finding.id || i} className="memory-item" style={{
                borderLeft: `3px solid ${SEVERITY_COLORS[finding.severity] || "var(--text-muted)"}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", padding: "1px 6px",
                    borderRadius: 3, background: SEVERITY_BG[finding.severity],
                    color: SEVERITY_COLORS[finding.severity],
                    border: `1px solid ${SEVERITY_COLORS[finding.severity]}30`,
                    textTransform: "uppercase" }}>
                    {finding.severity}
                  </span>
                  <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", padding: "1px 6px",
                    borderRadius: 3, background: "rgba(30,58,85,0.4)", color: "var(--text-muted)",
                    border: "1px solid var(--border)" }}>
                    {finding.category}
                  </span>
                  {finding.cwe_id && (
                    <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                      {finding.cwe_id}
                    </span>
                  )}
                </div>

                <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500, marginBottom: 4 }}>
                  {finding.title}
                </div>

                {finding.file_path && (
                  <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--sapphire)", marginBottom: 4 }}>
                    {finding.file_path}{finding.line_number ? `:${finding.line_number}` : ""}
                  </div>
                )}

                {finding.code_snippet && (
                  <pre style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-secondary)",
                    background: "rgba(3,6,8,0.5)", padding: "4px 8px", borderRadius: 4,
                    whiteSpace: "pre-wrap", margin: "4px 0" }}>
                    {finding.code_snippet}
                  </pre>
                )}

                {finding.recommendation && (
                  <div style={{ fontSize: 11, color: "var(--emerald)", marginTop: 4,
                    padding: "4px 8px", background: "rgba(16,185,129,0.05)", borderRadius: 4,
                    border: "1px solid rgba(16,185,129,0.1)" }}>
                    Fix: {finding.recommendation}
                  </div>
                )}
              </div>
            ))}

            {(report.findings || []).length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">طيب</div>
                <div className="empty-text">TAYYIB — Pure and Good</div>
                <div className="empty-sub">No security issues found</div>
              </div>
            )}
          </>
        )}

        {activeTab === "results" && !report && (
          <div className="empty-state">
            <div className="empty-arabic">رقيب</div>
            <div className="empty-text">No scan results yet</div>
            <div className="empty-sub">Run a scan to see results</div>
          </div>
        )}

        {activeTab === "history" && (
          <>
            {history.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">سجل</div>
                <div className="empty-text">No scan history</div>
              </div>
            )}
            {history.map(scan => (
              <div key={scan.id} className="memory-item">
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="memory-type-badge type-semantic">{scan.scan_type}</span>
                  <span style={{ fontSize: 11, color: "var(--text-primary)" }}>{scan.target}</span>
                  <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                    {scan.finding_count} findings
                  </span>
                  {scan.summary?.risk_score != null && (
                    <span style={{ fontSize: 10, fontFamily: "var(--font-mono)",
                      color: scan.summary.risk_score > 50 ? "var(--ruby)" :
                             scan.summary.risk_score > 20 ? "var(--amber)" : "var(--emerald)" }}>
                      Risk: {scan.summary.risk_score.toFixed(0)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </>
  );
}
