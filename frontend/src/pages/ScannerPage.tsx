/**
 * Security Scanner Page (Raqib - رَقِيب - The Watcher)
 * "Not a word does he utter but there is a watcher (Raqib) ready" — 50:18
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, ScanReport, ScanFinding, ScanHistoryItem, ScanSeverity } from "../types";

const SEVERITY_STYLES: Record<string, { text: string; bg: string; border: string }> = {
  critical: { text: "text-red-600 dark:text-red-400", bg: "bg-red-500/15", border: "border-red-500/30" },
  high: { text: "text-red-500 dark:text-red-400", bg: "bg-red-500/10", border: "border-red-500/20" },
  medium: { text: "text-amber-600 dark:text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  low: { text: "text-blue-600 dark:text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  info: { text: "text-gray-500 dark:text-gray-400", bg: "bg-gray-500/10", border: "border-gray-500/20" },
};

const SEVERITY_BORDER_LEFT: Record<string, string> = {
  critical: "border-l-red-600",
  high: "border-l-red-500",
  medium: "border-l-amber-500",
  low: "border-l-blue-500",
  info: "border-l-gray-400",
};

export default function ScannerPage({ api, addTerminalLine }: PageProps) {
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanPath, setScanPath] = useState<string>("/home/user/mizan");
  const [report, setReport] = useState<ScanReport | null>(null);
  const [history, setHistory] = useState<ScanHistoryItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>("scan");
  const [scanType, setScanType] = useState<string>("full");

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "raqib_scanner", action: "history",
      });
      setHistory((data.scans || []) as ScanHistoryItem[]);
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
      setReport(data as unknown as ScanReport);
      setActiveTab("results");
      loadHistory();
      const report = data as unknown as ScanReport;
      const total = report.summary?.total_findings || report.findings?.length || 0;
      addTerminalLine?.(`Scan complete: ${total} findings`, total > 0 ? "warn" : "gold");
    } catch (e) {
      addTerminalLine?.("Scan failed", "error");
    }
    setScanning(false);
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Security Scanner</h2>
          <p className="page-description">رَقِيب (Raqib) — Vulnerability detection</p>
        </div>
      </div>

      <div className="quran-quote">
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

      <div className="page-body">
        {activeTab === "scan" && (
          <div className="max-w-xl space-y-4">
            <div className="form-group">
              <label className="form-label">Target Path</label>
              <input className="form-input" value={scanPath}
                onChange={e => setScanPath(e.target.value)}
                placeholder="/path/to/project" />
            </div>

            <div className="form-group">
              <label className="form-label">Scan Type</label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: "full", label: "Full Scan", desc: "All checks combined" },
                  { id: "secrets", label: "Secret Scan", desc: "Leaked credentials" },
                  { id: "code", label: "Code Scan", desc: "OWASP vulnerabilities" },
                  { id: "deps", label: "Dependency Audit", desc: "Known CVEs" },
                  { id: "config", label: "Config Check", desc: "Misconfigurations" },
                  { id: "docker", label: "Docker Scan", desc: "Dockerfile issues" },
                ].map(st => (
                  <button key={st.id}
                    className={`flex flex-col items-center p-2.5 rounded-lg border text-center transition-colors cursor-pointer
                      ${scanType === st.id
                        ? "bg-mizan-gold/10 border-mizan-gold/30 text-mizan-gold"
                        : "bg-gray-50 dark:bg-zinc-800 border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-700"
                      }`}
                    onClick={() => setScanType(st.id)}>
                    <span className="text-xs font-medium">{st.label}</span>
                    <span className="text-micro text-gray-400 dark:text-gray-500 mt-0.5">{st.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            <button className="btn-gold w-full py-3 mt-3"
              onClick={runScan} disabled={scanning || !scanPath}>
              {scanning ? "Scanning..." : "Start Raqib Scan"}
            </button>
          </div>
        )}

        {activeTab === "results" && report && (
          <>
            {report.summary && (
              <div className="card">
                <div className="flex items-center gap-3 mb-3">
                  <div className="text-3xl font-arabic text-mizan-gold">رقيب</div>
                  <div className="flex-1">
                    <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
                      Scan Report
                    </div>
                    <div className="text-xs font-mono text-gray-500 dark:text-gray-400">
                      {report.scan_type} · {report.target}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-2xl font-mono font-bold
                      ${(report.summary.risk_score || 0) > 50 ? "text-red-500" :
                        (report.summary.risk_score || 0) > 20 ? "text-amber-500" : "text-emerald-500"}`}>
                      {(report.summary.risk_score || 0).toFixed(0)}
                    </div>
                    <div className="text-micro text-gray-400 dark:text-gray-500 uppercase">Risk Score</div>
                  </div>
                </div>

                {report.summary.verdict && (
                  <div className="bg-mizan-gold/5 border border-mizan-gold/15 rounded-md px-3 py-2 text-xs text-mizan-gold italic mb-3">
                    {report.summary.verdict}
                  </div>
                )}

                <div className="flex gap-2">
                  {Object.entries(report.summary.by_severity || {}).map(([sev, count]) => {
                    const style = SEVERITY_STYLES[sev] || SEVERITY_STYLES.info;
                    return (
                      <div key={sev} className={`flex-1 text-center p-2 rounded-md border ${count > 0 ? `${style.bg} ${style.border}` : "bg-gray-50 dark:bg-zinc-800/50 border-gray-200 dark:border-zinc-700/50"}`}>
                        <div className={`text-lg font-mono ${count > 0 ? style.text : "text-gray-400 dark:text-gray-500"}`}>{count}</div>
                        <div className="text-micro uppercase tracking-wider text-gray-400 dark:text-gray-500">{sev}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="text-xxs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
              Findings ({(report.findings || []).length})
            </div>

            {(report.findings || []).map((finding, i) => {
              const style = SEVERITY_STYLES[finding.severity] || SEVERITY_STYLES.info;
              const borderL = SEVERITY_BORDER_LEFT[finding.severity] || "border-l-gray-400";
              return (
                <div key={finding.id || i} className={`memory-item border-l-4 ${borderL}`}>
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className={`text-micro font-mono px-1.5 py-0.5 rounded ${style.bg} ${style.text} border ${style.border} uppercase`}>
                      {finding.severity}
                    </span>
                    <span className="tool-tag">{finding.category}</span>
                    {finding.cwe_id && (
                      <span className="text-micro font-mono text-gray-400 dark:text-gray-500">{finding.cwe_id}</span>
                    )}
                  </div>

                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {finding.title}
                  </div>

                  {finding.file_path && (
                    <div className="text-2xs font-mono text-blue-500 dark:text-blue-400 mb-1">
                      {finding.file_path}{finding.line_number ? `:${finding.line_number}` : ""}
                    </div>
                  )}

                  {finding.code_snippet && (
                    <pre className="detail-panel font-mono text-2xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap my-1">
                      {finding.code_snippet}
                    </pre>
                  )}

                  {finding.recommendation && (
                    <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 px-2 py-1 bg-emerald-500/5 border border-emerald-500/10 rounded">
                      Fix: {finding.recommendation}
                    </div>
                  )}
                </div>
              );
            })}

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
                <div className="flex items-center gap-2">
                  <span className="memory-type-badge type-semantic">{scan.scan_type}</span>
                  <span className="text-xs text-gray-900 dark:text-gray-100">{scan.target}</span>
                  <span className="ml-auto text-2xs font-mono text-gray-400 dark:text-gray-500">
                    {scan.finding_count} findings
                  </span>
                  {scan.summary?.risk_score != null && (
                    <span className={`text-2xs font-mono
                      ${scan.summary.risk_score > 50 ? "text-red-500" :
                        scan.summary.risk_score > 20 ? "text-amber-500" : "text-emerald-500"}`}>
                      Risk: {scan.summary.risk_score.toFixed(0)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
