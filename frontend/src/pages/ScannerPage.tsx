/**
 * Security Scanner Page (Raqib - رَقِيب - The Watcher)
 * "Not a word does he utter but there is a watcher (Raqib) ready" — 50:18
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, ScanReport, ScanFinding, ScanHistoryItem, ScanSeverity } from "../types";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#3b82f6",
  info: "#6b7280",
};

const SEVERITY_BG: Record<string, string> = {
  critical: "rgba(220,38,38,0.15)",
  high: "rgba(239,68,68,0.15)",
  medium: "rgba(245,158,11,0.15)",
  low: "rgba(59,130,246,0.15)",
  info: "rgba(107,114,128,0.15)",
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
    <>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <h2 className="page-title">Security Scanner · رَقِيب (Raqib)</h2>
      </div>
      <div className="px-4 pb-2 pt-1 text-xs text-gray-500 dark:text-gray-400 italic">
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

      <div className="flex-1 overflow-auto p-4">
        {activeTab === "scan" && (
          <div className="max-w-[600px]">
            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Target Path</label>
              <input className="input w-full text-sm" value={scanPath}
                onChange={e => setScanPath(e.target.value)}
                placeholder="/path/to/project" />
            </div>

            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Scan Type</label>
              <div className="flex gap-1.5 flex-wrap">
                {[
                  { id: "full", label: "Full Scan", desc: "All checks combined" },
                  { id: "secrets", label: "Secret Scan", desc: "Leaked credentials" },
                  { id: "code", label: "Code Scan", desc: "OWASP vulnerabilities" },
                  { id: "deps", label: "Dependency Audit", desc: "Known CVEs" },
                  { id: "config", label: "Config Check", desc: "Misconfigurations" },
                  { id: "docker", label: "Docker Scan", desc: "Dockerfile issues" },
                ].map(st => (
                  <button key={st.id}
                    className={`${scanType === st.id ? "btn-primary" : "btn-secondary"} flex-[1_0_45%] justify-center flex-col items-center px-3 py-2.5`}
                    onClick={() => setScanType(st.id)}>
                    <span className="text-xs">{st.label}</span>
                    <span className="text-[9px] text-gray-500 dark:text-gray-400 mt-0.5">{st.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            <button className="btn-primary w-full justify-center py-3 mt-3"
              onClick={runScan} disabled={scanning || !scanPath}>
              {scanning ? "Scanning..." : "Start Raqib Scan"}
            </button>
          </div>
        )}

        {activeTab === "results" && report && (
          <>
            {report.summary && (
              <div className="card mb-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="font-serif text-3xl text-mizan-gold">رقيب</div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Scan Report
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {report.scan_type} · {report.target}
                    </div>
                  </div>
                  <div className="ml-auto text-right">
                    <div className={`font-mono text-2xl ${
                      (report.summary.risk_score || 0) > 50 ? "text-red-500" :
                      (report.summary.risk_score || 0) > 20 ? "text-amber-500" : "text-emerald-500"
                    }`}>
                      {(report.summary.risk_score || 0).toFixed(0)}
                    </div>
                    <div className="text-[9px] text-gray-500 dark:text-gray-400">RISK SCORE</div>
                  </div>
                </div>

                {report.summary.verdict && (
                  <div className="px-3 py-2 bg-amber-500/5 border border-amber-500/15 rounded-md text-xs text-mizan-gold italic mb-3">
                    {report.summary.verdict}
                  </div>
                )}

                <div className="flex gap-2">
                  {Object.entries(report.summary.by_severity || {}).map(([sev, count]) => (
                    <div key={sev} className="flex-1 text-center p-2 rounded-md"
                      style={{
                        background: count > 0 ? SEVERITY_BG[sev] : undefined,
                        border: `1px solid ${count > 0 ? SEVERITY_COLORS[sev] + "40" : "rgba(200,200,200,0.2)"}`,
                      }}>
                      <div className="font-mono text-lg"
                        style={{ color: count > 0 ? SEVERITY_COLORS[sev] : undefined }}>
                        {count}
                      </div>
                      <div className="text-[9px] uppercase tracking-wide text-gray-500 dark:text-gray-400">{sev}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="text-[10px] tracking-widest text-gray-500 dark:text-gray-400 uppercase mb-2">
              Findings ({(report.findings || []).length})
            </div>

            {(report.findings || []).map((finding, i) => (
              <div key={finding.id || i} className="card mb-3"
                style={{ borderLeft: `3px solid ${SEVERITY_COLORS[finding.severity] || "#6b7280"}` }}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[9px] font-mono px-1.5 rounded uppercase"
                    style={{
                      background: SEVERITY_BG[finding.severity],
                      color: SEVERITY_COLORS[finding.severity],
                      border: `1px solid ${SEVERITY_COLORS[finding.severity]}30`,
                    }}>
                    {finding.severity}
                  </span>
                  <span className="text-[9px] font-mono px-1.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-zinc-800">
                    {finding.category}
                  </span>
                  {finding.cwe_id && (
                    <span className="text-[9px] font-mono text-gray-500 dark:text-gray-400">
                      {finding.cwe_id}
                    </span>
                  )}
                </div>

                <div className="text-xs text-gray-900 dark:text-gray-100 font-medium mb-1">
                  {finding.title}
                </div>

                {finding.file_path && (
                  <div className="text-[10px] font-mono text-blue-500 mb-1">
                    {finding.file_path}{finding.line_number ? `:${finding.line_number}` : ""}
                  </div>
                )}

                {finding.code_snippet && (
                  <pre className="text-[10px] font-mono text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-zinc-800/50 px-2 py-1 rounded whitespace-pre-wrap my-1">
                    {finding.code_snippet}
                  </pre>
                )}

                {finding.recommendation && (
                  <div className="text-xs text-emerald-500 mt-1 px-2 py-1 bg-emerald-500/5 rounded border border-emerald-500/10">
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
              <div key={scan.id} className="card mb-3">
                <div className="flex items-center gap-2">
                  <span className="memory-type-badge type-semantic">{scan.scan_type}</span>
                  <span className="text-xs text-gray-900 dark:text-gray-100">{scan.target}</span>
                  <span className="ml-auto text-[10px] font-mono text-gray-500 dark:text-gray-400">
                    {scan.finding_count} findings
                  </span>
                  {scan.summary?.risk_score != null && (
                    <span className={`text-[10px] font-mono ${
                      scan.summary.risk_score > 50 ? "text-red-500" :
                      scan.summary.risk_score > 20 ? "text-amber-500" : "text-emerald-500"
                    }`}>
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
