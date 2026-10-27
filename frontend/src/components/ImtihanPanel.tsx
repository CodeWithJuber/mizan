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
import {
  BLOCK_LABELS,
  blockRows,
  historyPoints,
  intervalText,
  pct,
  signed,
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

// Series colours, validated for both themes (dataviz validator: CVD ΔE ≥ 24).
const VIZ_STYLE = `
.imtihan-viz { --viz-mizan: #2a78d6; --viz-base: #eb6834; --viz-grid: #e5e4e0; }
.dark .imtihan-viz { --viz-mizan: #3987e5; --viz-base: #d95926; --viz-grid: #3f3f46; }
`;

function Bar({ value, color, label }: { value: number | null; color: string; label: string }) {
  const width = value == null ? 0 : Math.max(2, Math.round(value * 100));
  return (
    <div className="flex items-center gap-2 min-w-0" title={label}>
      <div className="flex-1 h-2.5 rounded-r bg-gray-100 dark:bg-zinc-800 overflow-hidden">
        <div className="h-full rounded-r" style={{ width: `${width}%`, background: color }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums">{pct(value)}</span>
    </div>
  );
}

function Legend2() {
  return (
    <div className="flex gap-4 text-xs text-gray-500">
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-2.5 rounded-sm" style={{ background: "var(--viz-base)" }} />
        Base model alone
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-2.5 rounded-sm" style={{ background: "var(--viz-mizan)" }} />
        MIZAN
      </span>
    </div>
  );
}

function ReportView({ run, onOpen }: { run: RunDetail; onOpen: (taskId: string) => void }) {
  const result = run.result!;
  const report = result.report;
  const rows = blockRows(report);
  const tasks = taskRows(result.results, result.tasks);
  const hero = (arm: "base" | "mizan", title: string) => (
    <div className="card p-4">
      <div className="text-xs text-gray-500">{title}</div>
      <div className="text-3xl font-semibold tabular-nums">{pct(report.index[arm].score)}</div>
      <div className="text-xs text-gray-500">{intervalText(report.index[arm].interval)}</div>
    </div>
  );
  const delta =
    report.index.mizan.score != null && report.index.base.score != null
      ? report.index.mizan.score - report.index.base.score
      : null;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {hero("base", "Base model alone")}
        {hero("mizan", "MIZAN")}
        <div className="card p-4">
          <div className="text-xs text-gray-500">MIZAN's difference</div>
          <div className="text-3xl font-semibold tabular-nums">{signed(delta)}</div>
          <div className="text-xs text-gray-500">mean of block pass rates · {run.model}</div>
        </div>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <h3 className="font-semibold text-sm">Pass rate by block</h3>
          <div className="ml-auto">
            <Legend2 />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-xs text-gray-500 text-left">
                <th className="font-normal pb-2">Block</th>
                <th className="font-normal pb-2 w-[30%]">Base model</th>
                <th className="font-normal pb-2 w-[30%]">MIZAN</th>
                <th className="font-normal pb-2 text-right">Δ</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.block} className="border-t border-gray-100 dark:border-zinc-800">
                  <td className="py-2 pr-3">
                    <div>{row.label}</div>
                    <div className="text-[11px] text-gray-500">
                      {row.tasks} task(s)
                      {row.base.errors + row.mizan.errors > 0 &&
                        ` · ${row.base.errors + row.mizan.errors} unscored (provider errors)`}
                    </div>
                  </td>
                  <td className="py-2 pr-3">
                    <Bar
                      value={row.base.rate}
                      color="var(--viz-base)"
                      label={`Base: ${row.base.passed}/${row.base.scored} passed, ${intervalText(row.base.interval)}`}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <Bar
                      value={row.mizan.rate}
                      color="var(--viz-mizan)"
                      label={`MIZAN: ${row.mizan.passed}/${row.mizan.scored} passed, ${intervalText(row.mizan.interval)}`}
                    />
                  </td>
                  <td className="py-2 text-right text-xs tabular-nums whitespace-nowrap">
                    {signed(row.delta)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Claims with support (Isnad)</div>
          <div>
            Base {pct(report.isnad?.base.supported)} · {report.isnad?.base.fabricated_claims ?? 0} fabricated
          </div>
          <div>
            MIZAN {pct(report.isnad?.mizan.supported)} · {report.isnad?.mizan.fabricated_claims ?? 0} fabricated
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Calibration (TruthfulQA, lower is better)</div>
          <div>Base ECE {report.calibration.base.ece ?? "—"} · Brier {report.calibration.base.brier ?? "—"}</div>
          <div>MIZAN ECE {report.calibration.mizan.ece ?? "—"} · Brier {report.calibration.mizan.brier ?? "—"}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Same answer to every paraphrase</div>
          <div>Base {report.consistency.base.consistent}/{report.consistency.base.groups}</div>
          <div>MIZAN {report.consistency.mizan.consistent}/{report.consistency.mizan.groups}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Work done</div>
          <div>Base: {report.cost.base.model_calls} model calls</div>
          <div>
            MIZAN: {report.cost.mizan.model_calls} model calls, {report.cost.mizan.tool_calls} tools
          </div>
        </div>
      </div>

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
                className={`text-xs px-2.5 py-1 rounded-full border ${on ? "border-amber-500 text-amber-700 dark:text-amber-400" : "border-gray-200 dark:border-zinc-700 text-gray-500"}`}
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
              className="rounded border border-gray-200 dark:border-zinc-700 bg-transparent px-2 py-1"
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
        </div>
        {running?.progress && (
          <div className="space-y-1">
            <div className="h-2 rounded bg-gray-100 dark:bg-zinc-800 overflow-hidden">
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
          {opened.compare ? (
            <CompareView run={opened.compare} />
          ) : (
            <div className="card p-4 text-sm text-gray-500">This attempt did not run.</div>
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
