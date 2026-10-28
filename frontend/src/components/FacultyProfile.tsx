/**
 * Quwa: the AGI test as the ten faculties of Google DeepMind's cognitive
 * framework. A radar of each arm's pass rate per faculty (and the human
 * panel's median where every axis has one), then the same numbers as a table
 * with intervals, the percentile of the panel each arm outperforms, and each
 * faculty's Quranic name and ayah. Propensities (injection, safety) are listed
 * apart, never on the profile.
 */

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  BLOCK_LABELS,
  FACULTY_SHORT,
  facultyPoints,
  intervalText,
  pct,
  percentileText,
  signed,
  type FacultyProfile as Profile,
} from "../utils/imtihan.ts";

function Swatch({ color, dashed }: { color: string; dashed?: boolean }) {
  return (
    <span
      className="w-4 h-0 inline-block"
      style={{ borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}` }}
      aria-hidden
    />
  );
}

export function FacultyProfile({ profile }: { profile: Profile }) {
  const points = facultyPoints(profile).map((point) => ({
    ...point,
    faculty: FACULTY_SHORT[point.key] ?? point.faculty,
  }));
  const panelComplete = points.length > 0 && points.every((point) => point.panel != null);
  // On a phone the axis names need room outside the web.
  const narrow = typeof window !== "undefined" && window.innerWidth < 480;
  const propensity = Object.entries(profile.propensity);
  return (
    <div className="card p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold text-sm">Cognitive faculties</h3>
        <div className="ml-auto flex flex-wrap gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <Swatch color="var(--viz-base)" /> Base model alone
          </span>
          <span className="flex items-center gap-1.5">
            <Swatch color="var(--viz-mizan)" /> MIZAN
          </span>
          {panelComplete && (
            <span className="flex items-center gap-1.5">
              <Swatch color="var(--viz-panel)" dashed /> Human panel (median)
            </span>
          )}
        </div>
      </div>
      <p className="text-[11px] text-gray-500">
        The ten faculties of {profile.framework}. Each axis is the pass rate on that faculty's items; problem solving
        and social cognition are composites that draw on the others. Read each axis with its interval in the table: the
        shape and area of the chart are not a score.
      </p>
      {points.length >= 3 && (
        <div className="h-80" role="img" aria-label="Pass rate per faculty, base model and MIZAN">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={points} outerRadius={narrow ? "52%" : "62%"}>
              <PolarGrid stroke="var(--viz-grid)" />
              <PolarAngleAxis dataKey="faculty" tick={{ fontSize: narrow ? 9 : 10, fill: "currentColor" }} />
              <PolarRadiusAxis
                domain={[0, 100]}
                tickCount={5}
                tick={{ fontSize: 9, fill: "currentColor", opacity: 0.55 }}
                angle={72}
                axisLine={false}
              />
              <Tooltip formatter={(value) => `${value}%`} />
              <Radar
                name="Base model"
                dataKey="base"
                stroke="var(--viz-base)"
                fill="var(--viz-base)"
                fillOpacity={0.08}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
              <Radar
                name="MIZAN"
                dataKey="mizan"
                stroke="var(--viz-mizan)"
                fill="var(--viz-mizan)"
                fillOpacity={0.12}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
              {panelComplete && (
                <Radar
                  name="Human panel (median)"
                  dataKey="panel"
                  stroke="var(--viz-panel)"
                  fill="none"
                  strokeDasharray="5 4"
                  strokeWidth={2}
                />
              )}
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className="text-xs text-gray-500 text-left">
              <th className="font-normal pb-2">Faculty</th>
              <th className="font-normal pb-2 text-right">Items</th>
              <th className="font-normal pb-2 text-right">Base</th>
              <th className="font-normal pb-2 text-right">MIZAN</th>
              <th className="font-normal pb-2 text-right">Δ</th>
              <th className="font-normal pb-2 pl-3">MIZAN against the human panel</th>
            </tr>
          </thead>
          <tbody>
            {profile.faculties.map((entry) => (
              <tr key={entry.key} className="border-t border-gray-100 dark:border-zinc-800 align-top">
                <td className="py-2 pr-3">
                  <div>
                    {entry.name}
                    {entry.composite && <span className="text-[11px] text-gray-500"> (composite)</span>}
                  </div>
                  <div className="text-[11px] text-gray-500">
                    <span dir="rtl" lang="ar">
                      {entry.script}
                    </span>{" "}
                    {entry.arabic} · {entry.ayah}: “{entry.words}”
                  </div>
                  {entry.blocks.length > 0 && (
                    <div className="text-[11px] text-gray-500">
                      {entry.blocks.map((block) => BLOCK_LABELS[block] ?? block).join(", ")}
                    </div>
                  )}
                </td>
                <td className="py-2 text-right tabular-nums">{entry.items}</td>
                {(["base", "mizan"] as const).map((arm) => (
                  <td
                    key={arm}
                    className="py-2 pl-2 text-right tabular-nums whitespace-nowrap"
                    title={entry[arm].scored ? intervalText(entry[arm].interval) : "not run"}
                  >
                    {pct(entry[arm].rate)}
                    {entry[arm].scored > 0 && (
                      <div className="text-[10px] text-gray-500">
                        {Math.round(entry[arm].interval[0] * 100)}–{Math.round(entry[arm].interval[1] * 100)}%
                      </div>
                    )}
                  </td>
                ))}
                <td className="py-2 pl-2 text-right tabular-nums whitespace-nowrap">{signed(entry.delta)}</td>
                <td className="py-2 pl-3 text-xs text-gray-600 dark:text-gray-300">
                  {percentileText(entry.mizan.human)}
                  {entry.panel && (
                    <div className="text-[11px] text-gray-500">
                      panel: median {pct(entry.panel.median)}, {entry.panel.people} people
                    </div>
                  )}
                  {entry.anchors.map((anchor) => (
                    <div key={anchor.block} className="text-[11px] text-gray-500">
                      Published human result for the source benchmark, other items:{" "}
                      <a className="underline" href={anchor.source} target="_blank" rel="noreferrer">
                        {anchor.measure} {pct(anchor.value)}
                      </a>
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {propensity.length > 0 && (
        <p className="text-[11px] text-gray-500">
          Not on the profile, since they measure what a system is inclined to do, not what it can do:{" "}
          {propensity
            .map(([block, arms]) => `${BLOCK_LABELS[block] ?? block} base ${pct(arms.base.rate)}, MIZAN ${pct(arms.mizan.rate)}`)
            .join(" · ")}
          .
        </p>
      )}
      <p className="text-[11px] text-gray-500">
        Levels follow {profile.levels_source}; one is shown only when the lower end of the percentile interval reaches
        it. Ayah wording: {profile.translation}.
      </p>
    </div>
  );
}
