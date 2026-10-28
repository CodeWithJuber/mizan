/**
 * Imtihan (AGI test): every task to the base model alone and to MIZAN, scored
 * by rule. Shows the score per block with 95% intervals, calibration,
 * consistency and cost, the history of runs, and each task's comparison.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ApiClient } from "../types";
import { CompareView, type Run } from "./DebugCompare";
import HumanPanel from "./HumanPanel";
import { Legend2, ReportSummary, VIZ_STYLE } from "./ReportSummary";
import {
  BLOCK_LABELS,
  historyPoints,
  pct,
  plainArms,
  taskRows,
  type Report,
  type ResultRow,
  type RunSummary,
} from "../utils/imtihan.ts";

interface RunDetail extends RunSummary {
  error?: string;
  result?: {
    tasks: { id: string; block: string; prompt: string; source?: string }[];
    repeats: number;
    results: ResultRow[];
    attempts: { task_id: string; attempt: number; compare: Run | null }[];
    report: Report;
  };
}

function PlainArmsView({ compared }: { compared: NonNullable<ReturnType<typeof plainArms>> }) {
  return (
    <div className="space-y-3">
      <div className="card p-4 text-sm whitespace-pre-wrap">{compared.prompt}</div>
      <div className="grid gap-4 md:grid-cols-2">
        {compared.arms.map((arm) => (
          <div key={arm.title} className="card p-4 space-y-2 min-w-0">
            <h4 className="font-semibold text-sm">{arm.title}</h4>
            {arm.checks.length > 0 && (
              <ul className="space-y-0.5 text-xs">
                {arm.checks.map((check) => (
                  <li key={check.label} className={check.pass ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    {check.pass ? "✓" : "✗"} {check.label}
                  </li>
                ))}
              </ul>
            )}
            <pre className="max-h-72 overflow-auto rounded-lg bg-muted/50 p-3 text-xs whitespace-pre-wrap wrap-break-word">
              {arm.text || "(no answer)"}
            </pre>
            {arm.final && (
              <pre className="overflow-auto rounded-lg bg-muted/50 p-3 text-[11px] leading-tight font-mono">{arm.final}</pre>
            )}
            {arm.calls.length > 0 && (
              <div className="text-[11px] text-gray-500 wrap-break-word">Tools: {arm.calls.join(" → ")}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportView({ run, onOpen }: { run: RunDetail; onOpen: (taskId: string) => void }) {
  const result = run.result!;
  const tasks = taskRows(result.results, result.tasks);
  return (
    <div className="space-y-4">
      <ReportSummary report={result.report} model={run.model} />
      <div className="card p-4">
        <h3 className="font-semibold text-sm mb-2">Tasks</h3>
        <div className="divide-y divide-gray-100 dark:divide-zinc-800">
          {tasks.map((task) => (
            <button
              type="button"
              key={task.id}
              onClick={() => onOpen(task.id)}
              className="w-full text-left py-2 grid grid-cols-[1fr_auto_auto] gap-3 items-center text-sm hover:bg-gray-50 dark:hover:bg-zinc-800/50"
            >
              <span className="min-w-0">
                <span className="block truncate">{task.prompt}</span>
                <span className="block text-[11px] text-gray-500 truncate">
                  {BLOCK_LABELS[task.block] ?? task.block} · {task.mizan.detail || task.base.detail}
                </span>
              </span>
              {(["base", "mizan"] as const).map((arm) => {
                const entry = task[arm];
                const text = entry.error
                  ? "error"
                  : entry.scored
                    ? `${entry.passed}/${entry.scored}`
                    : "—";
                const ok = entry.scored > 0 && entry.passed === entry.scored;
                return (
                  <span
                    key={arm}
                    className={`text-xs tabular-nums w-16 text-right ${entry.error ? "text-gray-500" : ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
                    title={arm === "base" ? "Base model" : "MIZAN"}
                  >
                    {arm === "base" ? "Base " : "MIZAN "}
                    {ok ? "✓" : entry.error ? "" : "✗"} {text}
                  </span>
                );
              })}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ImtihanPanel({ api }: { api: ApiClient }) {
  const [blocks, setBlocks] = useState<{ block: string; tasks: number }[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [repeats, setRepeats] = useState(1);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<RunDetail | null>(null);
  const [opened, setOpened] = useState<{ taskId: string; compare: Run | null } | null>(null);
  const [error, setError] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);

  const loadRuns = useCallback(async () => {
    try {
      const data = await api.get("/imtihan/runs");
      setRuns((data.runs as RunSummary[]) ?? []);
    } catch {
      setError("Runs could not be loaded (admins only)");
    }
  }, [api]);

  const select = useCallback(
    async (id: string) => {
      try {
        setSelected((await api.get(`/imtihan/runs/${id}`)) as unknown as RunDetail);
        setOpened(null);
      } catch {
        setError("That run could not be loaded");
      }
    },
    [api],
  );

  useEffect(() => {
    api
      .get("/imtihan/tasks")
      .then((data) => {
        const list = (data.blocks as { block: string; tasks: number }[]) ?? [];
        setBlocks(list);
        setChosen(list.map((entry) => entry.block));
      })
      .catch(() => setError("The AGI test is available to admins only"));
    loadRuns();
  }, [api, loadRuns]);

  const running = runs.find((run) => run.status === "running");
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      await loadRuns();
    }, 3000);
    return () => clearInterval(timer);
  }, [running, loadRuns]);

  useEffect(() => {
    const latest = runs.find((run) => run.status === "complete");
    if (!selected && latest) select(latest.id);
  }, [runs, selected, select]);

  const start = async () => {
    setError("");
    try {
      const all = chosen.length === blocks.length;
      await api.post("/imtihan/run", { repeats, ...(all ? {} : { blocks: chosen }) });
      await loadRuns();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The test could not start");
    }
  };

  const togglePublished = async (publish: boolean) => {
    if (!selected) return;
    setError("");
    try {
      if (publish) await api.post(`/imtihan/runs/${selected.id}/publish`);
      else await api.del(`/imtihan/runs/${selected.id}/publish`);
      await loadRuns();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Publishing failed");
    }
  };

  const points = useMemo(() => historyPoints(runs), [runs]);
  const taskCount = blocks
    .filter((entry) => chosen.includes(entry.block))
    .reduce((sum, entry) => sum + entry.tasks, 0);

  const openTask = (taskId: string) => {
    const attempt = selected?.result?.attempts.find((item) => item.task_id === taskId);
    setOpened({ taskId, compare: attempt?.compare ?? null });
  };

  return (
    <div className="imtihan-viz space-y-4">
      <style>{VIZ_STYLE}</style>
      <div className="card p-4 space-y-3">
        <p className="text-sm text-gray-500">
          Each task goes to the base model alone and to MIZAN, and both answers are scored by
          rule, never by another model. Sources and licences: ARC-AGI-2, TruthfulQA and XSTest
          subsets, plus tasks written for MIZAN.
        </p>
        <div className="flex flex-wrap gap-2">
          {blocks.map((entry) => {
            const on = chosen.includes(entry.block);
            return (
              <button
                type="button"
                key={entry.block}
                aria-pressed={on}
                onClick={() =>
                  setChosen(on ? chosen.filter((b) => b !== entry.block) : [...chosen, entry.block])
                }
                className={`text-xs px-2.5 py-1 rounded-full border ${on ? "border-amber-500 text-amber-700 dark:text-amber-400" : "border-border text-gray-500"}`}
              >
                {BLOCK_LABELS[entry.block] ?? entry.block} ({entry.tasks})
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-primary"
            disabled={Boolean(running) || chosen.length === 0}
            onClick={start}
          >
            {running ? "Running…" : "Run the AGI test"}
          </button>
          <label className="text-xs text-gray-500 flex items-center gap-2">
            Attempts per task
            <select
              className="rounded border border-border bg-transparent px-2 py-1"
              value={repeats}
              onChange={(event) => setRepeats(Number(event.target.value))}
            >
              {[1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <span className="text-xs text-gray-500">
            {taskCount} tasks × {repeats} × 2 arms; at least {taskCount * repeats * 2} model calls.
          </span>
          <button
            type="button"
            className="ml-auto text-xs underline"
            aria-expanded={panelOpen}
            onClick={() => setPanelOpen(!panelOpen)}
          >
            {panelOpen ? "Hide the human panel" : "Human panel: people take the test"}
          </button>
        </div>
        {running?.progress && (
          <div className="space-y-1">
            <div className="h-2 rounded bg-muted overflow-hidden">
              <div
                className="h-full"
                style={{
                  width: `${Math.round((running.progress.done / Math.max(1, running.progress.total)) * 100)}%`,
                  background: "var(--viz-mizan)",
                }}
              />
            </div>
            <div className="flex text-xs text-gray-500">
              <span>
                {running.progress.done} / {running.progress.total} · {running.progress.current ?? ""}
              </span>
              <button
                type="button"
                className="ml-auto underline"
                onClick={async () => {
                  await api.post(`/imtihan/runs/${running.id}/cancel`);
                  loadRuns();
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        {error && <div className="text-sm text-red-500">{error}</div>}
      </div>

      {panelOpen && <HumanPanel api={api} onChange={() => selected && select(selected.id)} />}

      {points.length > 1 && (
        <div className="card p-4">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <h3 className="font-semibold text-sm">Score over runs</h3>
            <div className="ml-auto">
              <Legend2 />
            </div>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
                <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.6} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.6} />
                <Tooltip formatter={(value) => `${value}%`} />
                <Legend wrapperStyle={{ display: "none" }} />
                <Line type="monotone" dataKey="base" name="Base model" stroke="var(--viz-base)" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="mizan" name="MIZAN" stroke="var(--viz-mizan)" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {runs.length > 0 && (
        <div className="card p-4">
          <h3 className="font-semibold text-sm mb-2">Runs</h3>
          <div className="divide-y divide-gray-100 dark:divide-zinc-800">
            {runs.map((run) => (
              <button
                type="button"
                key={run.id}
                onClick={() => run.status !== "running" && select(run.id)}
                className={`w-full text-left py-2 flex flex-wrap items-center gap-x-3 text-sm ${selected?.id === run.id ? "text-amber-700 dark:text-amber-400" : ""}`}
              >
                <span>{new Date(run.created_at * 1000).toLocaleString()}</span>
                <span className="text-xs text-gray-500">{run.status}</span>
                <span className="text-xs text-gray-500 truncate">{run.model}</span>
                {run.index && (
                  <span className="ml-auto text-xs tabular-nums">
                    base {pct(run.index.base.score)} · MIZAN {pct(run.index.mizan.score)}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {opened && (
        <div className="space-y-2">
          <div className="flex items-center">
            <h3 className="font-semibold text-sm">Task {opened.taskId}</h3>
            <button type="button" className="ml-auto text-xs underline" onClick={() => setOpened(null)}>
              Close
            </button>
          </div>
          {opened.compare && plainArms(opened.compare) ? (
            <PlainArmsView compared={plainArms(opened.compare)!} />
          ) : opened.compare ? (
            <CompareView run={opened.compare} />
          ) : (
            <div className="card p-4 text-sm text-gray-500">This attempt did not run.</div>
          )}
        </div>
      )}

      {selected?.result && selected.status === "complete" && (
        <div className="card p-3 flex flex-wrap items-center gap-2 text-sm">
          {runs.find((run) => run.id === selected.id)?.published ? (
            <>
              <span>This run is on the public reliability page.</span>
              <a className="underline" href="/reliability" target="_blank" rel="noreferrer">
                View
              </a>
              <button type="button" className="ml-auto text-xs underline" onClick={() => togglePublished(false)}>
                Remove from the public page
              </button>
            </>
          ) : (
            <>
              <span className="text-gray-500">
                Publish shows this run's scores to anyone (aggregates only: no prompts or answers), with its report hash
                in MIZAN's signed receipts.
              </span>
              <button type="button" className="btn-primary ml-auto text-xs" onClick={() => togglePublished(true)}>
                Publish on the public page
              </button>
            </>
          )}
        </div>
      )}
      {selected?.result && <ReportView run={selected} onOpen={openTask} />}
      {selected && !selected.result && selected.status !== "running" && (
        <div className="card p-4 text-sm text-gray-500">
          This run {selected.status}
          {selected.error ? `: ${selected.error}` : ""}.
        </div>
      )}
    </div>
  );
}
