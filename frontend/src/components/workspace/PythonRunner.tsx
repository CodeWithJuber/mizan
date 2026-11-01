/**
 * Run a project's Python in the browser with Pyodide, inside a sandboxed
 * frame with an opaque origin: the code cannot read MIZAN's storage or
 * cookies, and it talks to the page only through postMessage.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Play, Wrench } from "lucide-react";

export const PYODIDE_VERSION = "314.0.7";
const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

function runnerDocument(): string {
  const csp = [
    "default-src 'none'",
    `script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' ${PYODIDE_BASE}`,
    `connect-src ${PYODIDE_BASE}`,
    "style-src 'unsafe-inline'",
  ].join("; ");
  return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<script src="${PYODIDE_BASE}pyodide.js"></script></head><body><script>
const post = (data) => parent.postMessage({ source: "mizan-pyodide", ...data }, "*");
let ready = loadPyodide({ indexURL: "${PYODIDE_BASE}" }).then((py) => {
  py.setStdout({ batched: (text) => post({ type: "out", text }) });
  py.setStderr({ batched: (text) => post({ type: "err", text }) });
  post({ type: "ready" });
  return py;
}).catch((error) => { post({ type: "fail", text: String(error) }); });
window.addEventListener("message", async (event) => {
  const data = event.data || {};
  if (data.type !== "run") return;
  const py = await ready;
  if (!py) return;
  const started = performance.now();
  try {
    const root = "/home/pyodide/project";
    py.FS.mkdirTree(root);
    for (const [path, text] of Object.entries(data.files || {})) {
      const full = root + "/" + path;
      py.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
      py.FS.writeFile(full, text);
    }
    py.runPython("import os, sys; os.chdir('" + root + "'); sys.path.insert(0, '" + root + "')");
    await py.loadPackagesFromImports(data.files[data.entry] || "");
    py.globals.set("__mizan_entry__", data.entry);
    await py.runPythonAsync("import runpy; runpy.run_path(__mizan_entry__, run_name='__main__')");
    post({ type: "done", ok: true, ms: Math.round(performance.now() - started) });
  } catch (error) {
    post({ type: "err", text: String(error) });
    post({ type: "done", ok: false, ms: Math.round(performance.now() - started) });
  }
});
</script></body></html>`;
}

interface Line { kind: "out" | "err" | "info"; text: string }

export default function PythonRunner({ files, entry, onError }: {
  files: Record<string, string>;
  entry: string;
  /** "Fix with MIZAN": the failed run's error output goes to the chat. */
  onError?: (message: string) => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<Line[]>([{ kind: "info", text: "Loading Python (Pyodide)…" }]);
  const [failed, setFailed] = useState(false);
  const doc = useMemo(runnerDocument, []);

  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return;
      const data = event.data as { source?: string; type?: string; text?: string; ok?: boolean; ms?: number };
      if (data?.source !== "mizan-pyodide") return;
      if (data.type === "ready") { setReady(true); setLines([{ kind: "info", text: "Python is ready." }]); }
      else if (data.type === "out" || data.type === "err") setLines((list) => [...list, { kind: data.type as "out" | "err", text: String(data.text ?? "") }].slice(-2000));
      else if (data.type === "fail") setLines([{ kind: "err", text: `Could not load Python: ${data.text}` }]);
      else if (data.type === "done") {
        setRunning(false);
        setFailed(!data.ok);
        setLines((list) => [...list, { kind: "info", text: `${data.ok ? "Finished" : "Failed"} in ${((data.ms ?? 0) / 1000).toFixed(2)}s` }]);
      }
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, []);

  const run = () => {
    setRunning(true);
    setFailed(false);
    setLines([{ kind: "info", text: `$ python ${entry}` }]);
    frame.current?.contentWindow?.postMessage({ type: "run", files, entry }, "*");
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <span className="text-xs font-mono text-gray-500 truncate mr-auto">python {entry} · in your browser</span>
        {failed && onError && (
          <button
            type="button"
            className="btn-secondary btn-sm inline-flex items-center gap-1"
            onClick={() => onError(lines.filter((line) => line.kind === "err").map((line) => line.text).join("\n").slice(-4000))}
          >
            <Wrench className="w-3.5 h-3.5" /> Fix with MIZAN
          </button>
        )}
        <button type="button" className="btn-primary btn-sm inline-flex items-center gap-1" disabled={!ready || running} onClick={run}>
          <Play className="w-3.5 h-3.5" /> {running ? "Running…" : "Run Python"}
        </button>
      </div>
      <pre className="flex-1 min-h-[160px] overflow-auto bg-zinc-950 text-gray-100 text-xs font-mono p-3 whitespace-pre-wrap" aria-live="polite">
        {lines.map((line, index) => (
          <div key={index} className={line.kind === "err" ? "text-rose-300" : line.kind === "info" ? "text-gray-400" : ""}>{line.text}</div>
        ))}
      </pre>
      <iframe ref={frame} title="Python runtime" sandbox="allow-scripts" srcDoc={doc} className="hidden" />
    </div>
  );
}
