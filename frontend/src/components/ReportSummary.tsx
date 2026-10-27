/**
 * The aggregate part of an AGI-test report: the index with 95% intervals, the
 * weighted categories, agentic work, games, pass rate by block, Isnad,
 * calibration, consistency and work done. Shared by the admin AGI Test page
 * and the public reliability page; it holds no prompts or answers.
 */

import {
  BLOCK_LABELS,
  agenticRows,
  blockRows,
  categoryRows,
  gameRows,
  intervalText,
  pct,
  signed,
  type Report,
} from "../utils/imtihan.ts";

// Series colours, validated for both themes (dataviz validator: CVD ΔE ≥ 24).
export const VIZ_STYLE = `
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

export function Legend2() {
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

export function ReportSummary({ report, model }: { report: Report; model?: string | null }) {
  const rows = blockRows(report);
  const categories = categoryRows(report);
  const dimensions = agenticRows(report);
  const played = gameRows(report);
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
          <div className="text-xs text-gray-500">mean of block pass rates{model ? ` · ${model}` : ""}</div>
        </div>
      </div>

      {categories.length > 0 && (
        <div className="card p-4">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="font-semibold text-sm">Weighted index</h3>
            <span className="text-xs text-gray-500 tabular-nums">
              Base {pct(report.weighted?.base)} · MIZAN {pct(report.weighted?.mizan)}
            </span>
            <div className="ml-auto">
              <Legend2 />
            </div>
          </div>
          <p className="text-[11px] text-gray-500 mb-3">
            Categories weighted like the Artificial Analysis index: agents 30%, coding 20%, reasoning 20%, general 30%
            (re-weighted over the categories that ran).
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[520px]">
              <thead>
                <tr className="text-xs text-gray-500 text-left">
                  <th className="font-normal pb-2">Category</th>
                  <th className="font-normal pb-2 w-[30%]">Base model</th>
                  <th className="font-normal pb-2 w-[30%]">MIZAN</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((row) => (
                  <tr key={row.key} className="border-t border-gray-100 dark:border-zinc-800">
                    <td className="py-2 pr-3">
                      <div>{row.label}</div>
                      <div className="text-[11px] text-gray-500">
                        weight {Math.round(row.weight * 100)}% · {row.blocks.map((b) => BLOCK_LABELS[b] ?? b).join(", ")}
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <Bar value={row.base} color="var(--viz-base)" label={`Base: ${pct(row.base)}`} />
                    </td>
                    <td className="py-2 pr-3">
                      <Bar value={row.mizan} color="var(--viz-mizan)" label={`MIZAN: ${pct(row.mizan)}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {dimensions.length > 0 && (
        <div className="card p-4">
          <h3 className="font-semibold text-sm mb-1">Agentic work</h3>
          <p className="text-[11px] text-gray-500 mb-3">
            Each task runs in a fresh project in the isolated sandbox; a judge checks the final files, a command and the
            answer. A guardrail violation scores the task 0.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[420px]">
              <thead>
                <tr className="text-xs text-gray-500 text-left">
                  <th className="font-normal pb-2">Dimension</th>
                  <th className="font-normal pb-2 text-right">Base model</th>
                  <th className="font-normal pb-2 text-right">MIZAN</th>
                </tr>
              </thead>
              <tbody>
                {dimensions.map((row) => (
                  <tr key={row.label} className="border-t border-gray-100 dark:border-zinc-800">
                    <td className="py-1.5 pr-3">
                      {row.label}
                      {!row.higher && <span className="text-[11px] text-gray-500"> (lower is better)</span>}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">{row.base}</td>
                    <td className="py-1.5 text-right tabular-nums">{row.mizan}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {played.length > 0 && (
        <div className="card p-4">
          <h3 className="font-semibold text-sm mb-1">Interactive games (ARC-AGI-3 style)</h3>
          <p className="text-[11px] text-gray-500 mb-3">
            Neither arm is told the rules. The base model plays turn by turn from the grid; MIZAN learns what each action
            does, then plans, with no model call. Efficiency is the optimal number of actions over the number used.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[420px]">
              <thead>
                <tr className="text-xs text-gray-500 text-left">
                  <th className="font-normal pb-2">Measure</th>
                  <th className="font-normal pb-2 text-right">Base model</th>
                  <th className="font-normal pb-2 text-right">MIZAN</th>
                </tr>
              </thead>
              <tbody>
                {played.map((row) => (
                  <tr key={row.label} className="border-t border-gray-100 dark:border-zinc-800">
                    <td className="py-1.5 pr-3">{row.label}</td>
                    <td className="py-1.5 text-right tabular-nums">{row.base}</td>
                    <td className="py-1.5 text-right tabular-nums">{row.mizan}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
    </div>
  );
}
