/**
 * WordFamilyGraph — lightweight pure-SVG word-family graph (no heavy libs).
 * Layered layout (JEV choice, conf 0.72): three tiers stacked vertically —
 * root tier → derivative tier → verse tier — so nothing crowds on a 360px
 * phone screen. Responsive via viewBox; tap a node for details.
 */

import { useState } from "react";
import type {
  Derivative,
  Occurrence,
  Provenance,
} from "../../types/morphology";
import { VerifiedBadge } from "./VerifiedBadge";

interface WordFamilyGraphProps {
  root: string;
  derivatives: Derivative[];
  occurrences: Occurrence[];
  /** Provenance of the family data (from the root-entry response). */
  provenance: Provenance;
  source?: string;
  onSelectDerivative?: (word: string) => void;
}

type Selection =
  | { kind: "derivative"; derivative: Derivative }
  | { kind: "verse"; occurrence: Occurrence };

const W = 360;
const PER_ROW = 4;
const MAX_VERSES = 12;

export function WordFamilyGraph({
  root,
  derivatives,
  occurrences,
  provenance,
  source,
  onSelectDerivative,
}: WordFamilyGraphProps) {
  const [selection, setSelection] = useState<Selection | null>(null);

  const rootX = W / 2;
  const rootY = 54;

  const rows = Math.max(1, Math.ceil(derivatives.length / PER_ROW));
  const tier2Y = 158;
  const rowGap = 78;
  const verseTierY = tier2Y + (rows - 1) * rowGap + 104;
  const H = verseTierY + 64;

  const shownVerses = occurrences.slice(0, MAX_VERSES);
  const hiddenVerses = occurrences.length - shownVerses.length;

  const derivativePos = (i: number) => {
    const row = Math.floor(i / PER_ROW);
    const inRow = i % PER_ROW;
    const countInRow = Math.min(PER_ROW, derivatives.length - row * PER_ROW);
    const x =
      countInRow === 1
        ? rootX
        : 46 + (inRow * (W - 92)) / Math.max(1, countInRow - 1);
    return { x, y: tier2Y + row * rowGap };
  };

  const versePos = (i: number) => {
    const count = shownVerses.length;
    const x =
      count === 1 ? rootX : 40 + (i * (W - 80)) / Math.max(1, count - 1);
    return { x, y: verseTierY };
  };

  const selectDerivative = (d: Derivative) => {
    setSelection({ kind: "derivative", derivative: d });
    onSelectDerivative?.(d.surface);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Word family
        </span>
        <VerifiedBadge level={provenance} source={source} />
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label={`Word family graph for root ${root}`}
      >
        {/* root → derivative links */}
        {derivatives.map((d, i) => {
          const p = derivativePos(i);
          return (
            <line
              key={`rl-${i}`}
              x1={rootX}
              y1={rootY + 26}
              x2={p.x}
              y2={p.y - 24}
              className="stroke-gray-300 dark:stroke-zinc-600"
              strokeWidth={1.5}
            />
          );
        })}
        {/* root → verse links (dashed: occurrences are root-level) */}
        {shownVerses.map((_, i) => {
          const p = versePos(i);
          return (
            <line
              key={`vl-${i}`}
              x1={rootX}
              y1={rootY + 26}
              x2={p.x}
              y2={p.y - 12}
              className="stroke-gray-200 dark:stroke-zinc-700"
              strokeWidth={1}
              strokeDasharray="4 4"
            />
          );
        })}

        {/* root node */}
        <g>
          <circle
            cx={rootX}
            cy={rootY}
            r={26}
            className="fill-mizan-gold/15 stroke-mizan-gold"
            strokeWidth={2}
          />
          <text
            x={rootX}
            y={rootY + 44}
            textAnchor="middle"
            className="fill-gray-900 dark:fill-gray-100"
            fontSize={20}
            fontWeight={700}
          >
            {root}
          </text>
        </g>

        {/* derivative nodes */}
        {derivatives.map((d, i) => {
          const p = derivativePos(i);
          const active =
            selection?.kind === "derivative" &&
            selection.derivative.surface === d.surface;
          return (
            <g
              key={`d-${i}`}
              onClick={() => selectDerivative(d)}
              className="cursor-pointer"
              role="button"
              aria-label={`Derivative ${d.surface}`}
            >
              <circle cx={p.x} cy={p.y} r={24} fill="transparent" />
              <circle
                cx={p.x}
                cy={p.y}
                r={18}
                className={
                  active
                    ? "fill-mizan-gold/25 stroke-mizan-gold"
                    : "fill-purple-100 dark:fill-purple-500/15 stroke-purple-400 dark:stroke-purple-500/60"
                }
                strokeWidth={active ? 2.5 : 1.5}
              />
              <text
                x={p.x}
                y={p.y + 36}
                textAnchor="middle"
                className="fill-gray-700 dark:fill-gray-300"
                fontSize={12}
              >
                {d.surface}
              </text>
            </g>
          );
        })}

        {/* verse nodes */}
        {shownVerses.map((o, i) => {
          const p = versePos(i);
          const active =
            selection?.kind === "verse" && selection.occurrence.ref === o.ref;
          return (
            <g
              key={`v-${i}`}
              onClick={() => setSelection({ kind: "verse", occurrence: o })}
              className="cursor-pointer"
              role="button"
              aria-label={`Verse ${o.ref}`}
            >
              <circle cx={p.x} cy={p.y} r={22} fill="transparent" />
              <circle
                cx={p.x}
                cy={p.y}
                r={7}
                className={
                  active
                    ? "fill-mizan-gold stroke-mizan-gold"
                    : "fill-emerald-400 dark:fill-emerald-500/70 stroke-emerald-600 dark:stroke-emerald-400"
                }
                strokeWidth={1.5}
              />
            </g>
          );
        })}
        {hiddenVerses > 0 && (
          <text
            x={rootX}
            y={verseTierY + 34}
            textAnchor="middle"
            className="fill-gray-400"
            fontSize={11}
          >
            +{hiddenVerses} more verses
          </text>
        )}
      </svg>

      {/* detail panel */}
      {selection?.kind === "derivative" && (
        <div className="mt-2 p-3 rounded-xl bg-gray-50 dark:bg-zinc-800/60 border border-gray-200/60 dark:border-zinc-700/50 animate-fade-in">
          <div className="flex items-center justify-between gap-2">
            <span
              dir="rtl"
              lang="ar"
              className="text-lg font-bold text-gray-900 dark:text-gray-100"
            >
              {selection.derivative.surface}
            </span>
            <VerifiedBadge level={provenance} source={source} />
          </div>
          {selection.derivative.gloss && (
            <div className="text-sm text-gray-600 dark:text-gray-300 mt-1">
              {selection.derivative.gloss}
            </div>
          )}
        </div>
      )}
      {selection?.kind === "verse" && (
        <div className="mt-2 p-3 rounded-xl bg-gray-50 dark:bg-zinc-800/60 border border-gray-200/60 dark:border-zinc-700/50 animate-fade-in">
          <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">
            {selection.occurrence.ref}
          </div>
          {selection.occurrence.text_ar && (
            <div
              dir="rtl"
              lang="ar"
              className="text-sm text-gray-800 dark:text-gray-200 mt-1 leading-relaxed"
            >
              {selection.occurrence.text_ar}
            </div>
          )}
          {selection.occurrence.text_en && (
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {selection.occurrence.text_en}
            </div>
          )}
        </div>
      )}

      {derivatives.length === 0 && (
        <p className="text-xs text-gray-400 mt-2">
          No derivatives recorded for this root yet.
        </p>
      )}
    </div>
  );
}
