/**
 * Security Scanner Page (Raqib - رَقِيب - The Watcher)
 * "Not a word does he utter but there is a watcher (Raqib) ready" — 50:18
 */

import { useState, useEffect, useCallback } from "react";
import {
  PageProps,
  ScanReport,
  ScanFinding,
  ScanHistoryItem,
  ScanSeverity,
} from "../types";
import { useToast } from "../components/Toast";

const SEVERITY_STYLES: Record<
  string,
  { text: string; bg: string; border: string }
> = {
  critical: {
    text: "text-red-600 dark:text-red-400",
    bg: "bg-red-500/15",
    border: "border-red-500/30",
  },
  high: {
    text: "text-red-500 dark:text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/20",
  },
  medium: {
    text: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
  },
  low: {
    text: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
  },
  info: {
    text: "text-gray-500 dark:text-gray-400",
    bg: "bg-gray-500/10",
    border: "border-gray-500/20",
  },
};

const SEVERITY_BORDER_LEFT: Record<string, string> = {
  critical: "border-l-red-600",
  high: "border-l-red-500",
  medium: "border-l-amber-500",
  low: "border-l-blue-500",
  info: "border-l-gray-400",
};

// Plain-language scan types (no jargon)
const SCAN_TYPES: { id: string; label: string; desc: string }[] = [
  { id: "full", label: "Full Scan", desc: "Everything below, in one go" },
  {
    id: "secrets",
    label: "Password & Key Scan",
    desc: "Leaked passwords, API keys, tokens",
  },
  {
    id: "code",
    label: "Code Problems Scan",
    desc: "Common coding mistakes attackers exploit",
  },
  {
    id: "deps",
    label: "Library Check",
    desc: "Known security holes in used libraries",
  },
  {
    id: "config",
    label: "Settings Check",
    desc: "Unsafe settings in config files",
  },
  {
    id: "docker",
    label: "Docker Check",
    desc: "Problems in Docker setup files",
  },
];

// Common CWE ids → plain words. Unknown ids render as-is.
const CWE_NAMES: Record<string, string> = {
  "CWE-798": "hardcoded password",
  "CWE-89": "SQL injection",
  "CWE-79": "cross-site scripting",
  "CWE-78": "OS command injection",
  "CWE-22": "path traversal",
  "CWE-20": "bad input checking",
  "CWE-287": "broken login check",
  "CWE-306": "missing login check",
  "CWE-311": "missing encryption",
  "CWE-312": "password stored as plain text",
  "CWE-319": "password sent without encryption",
  "CWE-352": "cross-site request forgery",
  "CWE-434": "unsafe file upload",
  "CWE-502": "unsafe data loading",
  "CWE-611": "XXE",
  "CWE-918": "server-side request forgery",
};

const riskLevel = (score: number): string =>
  score >= 80
    ? "Critical"
    : score >= 60
      ? "High"
      : score >= 40
        ? "Medium"
        : "Low";

const riskColor = (score: number): string =>
  score >= 60
    ? "text-red-500"
    : score >= 40
      ? "text-amber-500"
      : "text-emerald-500";

export default function ScannerPage({ api, addTerminalLine }: PageProps) {
  const { addToast } = useToast();
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanPath, setScanPath] = useState<string>("/home/user/mizan");
  const [report, setReport] = useState<ScanReport | null>(null);
  const [history, setHistory] = useState<ScanHistoryItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>("scan");
  const [scanType, setScanType] = useState<string>("full");
  const [scanError, setScanError] = useState<string | null>(null);
  const [loadingReport, setLoadingReport] = useState<boolean>(false);

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.post("/skills/execute", {
        skill: "raqib_scanner",
        action: "history",
      });
      setHistory((data.scans || []) as ScanHistoryItem[]);
    } catch {
      addToast({
        type: "error",
        title: "Scan history load nahi hui",
        description: "Phir se try karo ya page refresh karo.",
      });
    }
  }, [api, addToast]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const runScan = async () => {
    setScanning(true);
    setScanError(null);
    addTerminalLine?.(`Raqib scanning: ${scanPath} (${scanType})...`, "gold");
    try {
      const data = await api.post("/skills/execute", {
        skill: "raqib_scanner",
        action: scanType,
        path: scanPath,
      });
      // Skill-level errors come back as {error: "..."} with HTTP 200
      if (typeof data.error === "string") throw new Error(data.error);
      const rep = data as unknown as ScanReport;
      setReport(rep);
      setActiveTab("results");
      loadHistory();
      const total = rep.summary?.total_findings || rep.findings?.length || 0;
      addTerminalLine?.(
        `Scan complete: ${total} findings`,
        total > 0 ? "warn" : "gold",
      );
      if (total === 0) {
        addToast({
          type: "success",
          title: "Scan complete — no issues found",
          description:
            "Note: agar folder ka path galat hai to scan khaali folder dekhta hai. Path server pe maujood hona chahiye.",
        });
      } else {
        addToast({
          type: "warning",
          title: `Scan complete — ${total} issue${total === 1 ? "" : "s"} found`,
        });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Scan failed";
      setScanError(msg);
      addToast({ type: "error", title: "Scan fail ho gaya", description: msg });
      addTerminalLine?.("Scan failed", "error");
    }
    setScanning(false);
  };

  const loadReport = async (id: string) => {
    setLoadingReport(true);
    try {
      const data = await api.post("/skills/execute", {
        skill: "raqib_scanner",
        action: "report",
        report_id: id,
      });
      if (typeof data.error === "string") throw new Error(data.error);
      setReport(data as unknown as ScanReport);
      setActiveTab("results");
    } catch (e) {
      addToast({
        type: "error",
        title: "Report load nahi hui",
        description: e instanceof Error ? e.message : undefined,
      });
    }
    setLoadingReport(false);
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Security Scanner</h2>
          <p className="page-description">
            رَقِيب (Raqib) — Vulnerability detection
          </p>
        </div>
      </div>

      <div className="quran-quote">
        "Not a word does he utter but there is a watcher (Raqib) ready" — Quran
        50:18
      </div>

      <div className="tab-bar">
        {[
          { id: "scan", label: "New Scan" },
          { id: "results", label: "Results" },
          { id: "history", label: "History" },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
            aria-selected={activeTab === tab.id}
            role="tab"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="page-body">
        {activeTab === "scan" && (
          <div className="max-w-xl space-y-4">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Checks a project on your server for leaked passwords and known
              security problems.
            </p>
            <div className="form-group">
              <label className="form-label" htmlFor="scan-target">
                Target Path
              </label>
              <input
                id="scan-target"
                className="form-input"
                value={scanPath}
                onChange={(e) => setScanPath(e.target.value)}
                placeholder="/path/to/project"
              />
              <p className="text-2xs text-gray-400 dark:text-gray-500 mt-1">
                A folder on the Mizan server — not on your phone.
              </p>
            </div>

            <div className="form-group">
              <label className="form-label">Scan Type</label>
              <div className="grid grid-cols-2 gap-2">
                {SCAN_TYPES.map((st) => (
                  <button
                    key={st.id}
                    className={`flex flex-col items-center p-2.5 rounded-lg border text-center transition-colors cursor-pointer min-h-[64px]
                      ${
                        scanType === st.id
                          ? "bg-mizan-gold/10 border-mizan-gold/30 text-mizan-gold"
                          : "bg-gray-50 dark:bg-zinc-800 border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-700"
                      }`}
                    onClick={() => setScanType(st.id)}
                  >
                    <span className="text-xs font-medium">{st.label}</span>
                    <span className="text-micro text-gray-400 dark:text-gray-500 mt-0.5">
                      {st.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {scanError && (
              <div className="card border-red-500/30 bg-red-500/5">
                <div className="text-sm font-medium text-red-600 dark:text-red-400">
                  Scan fail ho gaya
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 break-all">
                  {scanError}
                </div>
                <button
                  className="btn-secondary btn-sm mt-2 min-h-[44px]"
                  onClick={runScan}
                  disabled={scanning}
                >
                  Retry scan
                </button>
              </div>
            )}

            <button
              className="btn-gold w-full py-3 mt-3 min-h-[48px]"
              onClick={runScan}
              disabled={scanning || !scanPath}
            >
              {scanning ? "Scanning…" : "Start Raqib Scan"}
            </button>
            {scanning && (
              <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
                This can take a few minutes for large projects…
              </p>
            )}
          </div>
        )}

        {activeTab === "results" && report && (
          <>
            {report.summary && (
              <div className="card">
                <div className="flex items-center gap-3 mb-3">
                  <div className="text-3xl font-arabic text-mizan-gold">
                    رقيب
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
                      Scan Report
                    </div>
                    <div className="text-xs font-mono text-gray-500 dark:text-gray-400 break-all">
                      {report.scan_type} · {report.target}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div
                      className={`text-2xl font-mono font-bold ${riskColor(report.summary.risk_score || 0)}`}
                    >
                      {(report.summary.risk_score || 0).toFixed(0)}
                      <span className="text-sm font-normal text-gray-400 dark:text-gray-500">
                        /100
                      </span>
                    </div>
                    <div className="text-micro text-gray-400 dark:text-gray-500 uppercase">
                      Risk Score — {riskLevel(report.summary.risk_score || 0)}
                    </div>
                  </div>
                </div>

                {report.summary.verdict && (
                  <div className="bg-mizan-gold/5 border border-mizan-gold/15 rounded-md px-3 py-2 text-xs text-mizan-gold italic mb-3">
                    {report.summary.verdict}
                  </div>
                )}

                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                  {Object.entries(report.summary.by_severity || {}).map(
                    ([sev, count]) => {
                      const style =
                        SEVERITY_STYLES[sev] || SEVERITY_STYLES.info;
                      return (
                        <div
                          key={sev}
                          className={`text-center p-2 rounded-md border ${count > 0 ? `${style.bg} ${style.border}` : "bg-gray-50 dark:bg-zinc-800/50 border-gray-200 dark:border-zinc-700/50"}`}
                        >
                          <div
                            className={`text-lg font-mono ${count > 0 ? style.text : "text-gray-400 dark:text-gray-500"}`}
                          >
                            {count}
                          </div>
                          <div className="text-micro uppercase tracking-wider text-gray-400 dark:text-gray-500 break-words">
                            {sev}
                          </div>
                        </div>
                      );
                    },
                  )}
                </div>
              </div>
            )}

            <div className="text-xxs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
              Findings ({(report.findings || []).length})
            </div>

            {(report.findings || []).map((finding, i) => {
              const style =
                SEVERITY_STYLES[finding.severity] || SEVERITY_STYLES.info;
              const borderL =
                SEVERITY_BORDER_LEFT[finding.severity] || "border-l-gray-400";
              return (
                <div
                  key={finding.id || i}
                  className={`memory-item border-l-4 ${borderL}`}
                >
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span
                      className={`text-micro font-mono px-1.5 py-0.5 rounded ${style.bg} ${style.text} border ${style.border} uppercase`}
                    >
                      {finding.severity}
                    </span>
                    <span className="tool-tag">{finding.category}</span>
                    {finding.cwe_id && (
                      <span className="text-micro font-mono text-gray-400 dark:text-gray-500">
                        {finding.cwe_id}
                        {CWE_NAMES[finding.cwe_id]
                          ? `: ${CWE_NAMES[finding.cwe_id]}`
                          : ""}
                      </span>
                    )}
                  </div>

                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {finding.title}
                  </div>

                  {finding.file_path && (
                    <div className="text-2xs font-mono text-blue-500 dark:text-blue-400 mb-1">
                      {finding.file_path}
                      {finding.line_number ? `:${finding.line_number}` : ""}
                    </div>
                  )}

                  {finding.code_snippet && (
                    <pre className="detail-panel font-mono text-2xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap break-all my-1">
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
            {history.map((scan) => (
              <button
                key={scan.id}
                type="button"
                className="memory-item w-full text-left cursor-pointer hover:bg-gray-50 dark:hover:bg-zinc-800/60 disabled:opacity-60"
                onClick={() => loadReport(scan.id)}
                disabled={loadingReport}
                title="Report kholo"
              >
                <div className="flex items-center gap-2">
                  <span className="memory-type-badge type-semantic shrink-0">
                    {scan.scan_type}
                  </span>
                  <span className="text-xs text-gray-900 dark:text-gray-100 min-w-0 flex-1 truncate">
                    {scan.target}
                  </span>
                  <span className="ml-auto text-2xs font-mono text-gray-400 dark:text-gray-500 shrink-0">
                    {scan.finding_count} findings
                  </span>
                  {scan.summary?.risk_score != null && (
                    <span
                      className={`text-2xs font-mono shrink-0 ${riskColor(scan.summary.risk_score)}`}
                    >
                      {scan.summary.risk_score.toFixed(0)}/100
                    </span>
                  )}
                </div>
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
