/**
 * TasrifVisualizer — Interactive demo of morphophonemic transformation operators
 * Visualizes how 6D articulatory feature vectors change through tasrif operations.
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../../types";
import type { TasrifResult } from "../../types/ruh";

interface TasrifVisualizerProps {
  api: ApiClient;
}

const DIMENSIONS = ["place", "manner", "voicing", "nasality", "emphasis", "length"];

const OPERATOR_INFO: Record<string, string> = {
  idgham: "Assimilation — adopts place of following sound",
  iqlab: "Substitution — nasal replaces target before labials",
  ikhfa: "Concealment — partial nasalization",
  tafkhim: "Velarization — spreads emphasis to neighbors",
  tarqiq: "Thinning — removes emphasis, restores plain",
  qalb: "Metathesis — swaps place and manner features",
  ibdal: "Replacement — mirrors place of articulation",
  hazf: "Deletion — zeros out all features",
  ziadah: "Addition — strengthens all features",
  madd: "Extension — maximizes length feature",
  hamzah: "Glottalization — shifts toward glottal stop",
  tashdid: "Gemination — doubles all feature intensity",
  sukun: "Quiescence — reduces manner toward stop",
  tanwin: "Nunation — adds nasality (followed by /n/)",
  imaalah: "Inclination — shifts toward palatal region",
};

const DEFAULT_FEATURES = [0.5, 0.5, 1.0, 0.0, 0.0, 0.5];

export function TasrifVisualizer({ api }: TasrifVisualizerProps) {
  const [features, setFeatures] = useState<number[]>(DEFAULT_FEATURES);
  const [selectedOps, setSelectedOps] = useState<string[]>([]);
  const [result, setResult] = useState<TasrifResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [availableOps, setAvailableOps] = useState<string[]>(Object.keys(OPERATOR_INFO));

  // Fetch available operators on mount (if different from hardcoded)
  useEffect(() => {
    const fetchOps = async () => {
      try {
        const data = await api.post("/ruh/tasrif-demo", {
          features: DEFAULT_FEATURES,
          operators: ["idgham"],
        });
        const res = data as unknown as TasrifResult;
        if (res.available_operators) {
          setAvailableOps(res.available_operators);
        }
      } catch {
        // Use hardcoded fallback
      }
    };
    fetchOps();
  }, [api]);

  const toggleOp = (op: string) => {
    setSelectedOps((prev) =>
      prev.includes(op) ? prev.filter((o) => o !== op) : [...prev, op]
    );
    setResult(null);
  };

  const handleApply = async () => {
    if (selectedOps.length === 0) return;
    setLoading(true);
    setError(null);

    try {
      const data = await api.post("/ruh/tasrif-demo", {
        features,
        operators: selectedOps,
      });
      setResult(data as unknown as TasrifResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tasrif demo failed");
    } finally {
      setLoading(false);
    }
  };

  const updateFeature = (idx: number, value: number) => {
    setFeatures((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
    setResult(null);
  };

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
          Tasrif Operator Playground
        </h4>
        <p className="text-xs text-gray-400">
          Explore how morphophonemic operators transform 6D articulatory feature vectors.
        </p>
      </div>

      {/* Feature sliders */}
      <div className="space-y-2">
        <h5 className="text-[10px] text-gray-400 uppercase tracking-wider">Input Features</h5>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {DIMENSIONS.map((dim, idx) => (
            <div key={dim} className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-xs text-gray-500 dark:text-gray-400 capitalize">{dim}</label>
                <span className="text-[10px] font-mono text-gray-400">{features[idx].toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={features[idx]}
                onChange={(e) => updateFeature(idx, parseFloat(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-purple-600"
              />
            </div>
          ))}
        </div>

        {/* Feature bar visualization */}
        <div className="flex gap-1 h-8">
          {features.map((val, idx) => (
            <div key={idx} className="flex-1 relative rounded overflow-hidden bg-gray-100 dark:bg-zinc-800">
              <div
                className="absolute bottom-0 w-full bg-gradient-to-t from-purple-500 to-purple-400 transition-all"
                style={{ height: `${val * 100}%` }}
              />
              <span className="absolute inset-0 flex items-center justify-center text-[8px] font-mono text-gray-500 dark:text-gray-400">
                {DIMENSIONS[idx][0].toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Operator selection */}
      <div className="space-y-2">
        <h5 className="text-[10px] text-gray-400 uppercase tracking-wider">
          Select Operators ({selectedOps.length} selected)
        </h5>
        <div className="flex flex-wrap gap-1.5">
          {availableOps.map((op) => {
            const selected = selectedOps.includes(op);
            const orderIdx = selectedOps.indexOf(op);
            return (
              <button
                key={op}
                onClick={() => toggleOp(op)}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors border ${
                  selected
                    ? "bg-purple-100 dark:bg-purple-500/15 border-purple-300 dark:border-purple-500/30 text-purple-700 dark:text-purple-400"
                    : "bg-gray-50 dark:bg-zinc-800/50 border-gray-200 dark:border-zinc-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-700/30"
                }`}
                title={OPERATOR_INFO[op] ?? op}
              >
                {selected && (
                  <span className="w-4 h-4 rounded-full bg-purple-500 text-white text-[10px] flex items-center justify-center">
                    {orderIdx + 1}
                  </span>
                )}
                {op}
              </button>
            );
          })}
        </div>
      </div>

      {/* Apply button */}
      <button
        onClick={handleApply}
        disabled={loading || selectedOps.length === 0}
        className="px-4 py-2 text-sm font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "Applying..." : `Apply ${selectedOps.length} Operator${selectedOps.length !== 1 ? "s" : ""}`}
      </button>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {/* Results */}
      {result && (
        <div className="space-y-3">
          {/* Step-by-step transformations */}
          {result.steps.map((step, idx) => (
            <div
              key={idx}
              className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 border border-gray-100 dark:border-zinc-700/50"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="w-5 h-5 rounded-full bg-purple-500 text-white text-[10px] flex items-center justify-center">
                  {idx + 1}
                </span>
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">{step.operator}</span>
                <span className="text-[10px] text-gray-400">{OPERATOR_INFO[step.operator] ?? ""}</span>
              </div>

              {/* Before/After comparison */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-[10px] text-gray-400 uppercase">Before</span>
                  <FeatureBar values={step.input} changedDims={[]} />
                </div>
                <div>
                  <span className="text-[10px] text-gray-400 uppercase">After</span>
                  <FeatureBar values={step.output} changedDims={step.changed_dims} />
                </div>
              </div>

              {/* Changed dimensions highlight */}
              {step.changed_dims.length > 0 && (
                <div className="mt-1 flex items-center gap-1 text-[10px]">
                  <span className="text-gray-400">Changed:</span>
                  {step.changed_dims.map((dim) => (
                    <span key={dim} className="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400">
                      {DIMENSIONS[dim]}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {/* Final comparison */}
          <div className="bg-purple-50 dark:bg-purple-500/5 rounded-lg p-3 border border-purple-200 dark:border-purple-500/20">
            <h5 className="text-xs font-semibold text-purple-700 dark:text-purple-400 mb-2">
              Overall Transformation
            </h5>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-[10px] text-gray-400 uppercase">Original</span>
                <FeatureBar values={result.original} changedDims={[]} />
                <div className="flex gap-1 mt-1">
                  {result.original.map((v, i) => (
                    <span key={i} className="text-[9px] font-mono text-gray-400 flex-1 text-center">
                      {v.toFixed(2)}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 uppercase">Final</span>
                <FeatureBar
                  values={result.final}
                  changedDims={result.original.reduce<number[]>((acc, v, i) => {
                    if (Math.abs(v - result.final[i]) > 0.001) acc.push(i);
                    return acc;
                  }, [])}
                />
                <div className="flex gap-1 mt-1">
                  {result.final.map((v, i) => (
                    <span key={i} className="text-[9px] font-mono text-gray-400 flex-1 text-center">
                      {v.toFixed(2)}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FeatureBar({ values, changedDims }: { values: number[]; changedDims: number[] }) {
  return (
    <div className="flex gap-0.5 h-6 mt-1">
      {values.map((val, idx) => (
        <div
          key={idx}
          className={`flex-1 relative rounded-sm overflow-hidden ${
            changedDims.includes(idx)
              ? "ring-1 ring-amber-400"
              : ""
          }`}
        >
          <div className="absolute inset-0 bg-gray-200 dark:bg-zinc-700" />
          <div
            className={`absolute bottom-0 w-full transition-all ${
              changedDims.includes(idx)
                ? "bg-amber-500"
                : "bg-purple-500"
            }`}
            style={{ height: `${val * 100}%` }}
          />
          <span className="absolute inset-0 flex items-center justify-center text-[7px] font-mono text-gray-600 dark:text-gray-400">
            {DIMENSIONS[idx]?.[0]?.toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  );
}
