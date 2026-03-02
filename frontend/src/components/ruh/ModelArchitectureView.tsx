/**
 * ModelArchitectureView — Visual representation of the Ruh model architecture
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../../types";
import type { ModelArchitecture } from "../../types/ruh";

interface ModelArchitectureViewProps {
  api: ApiClient;
}

function formatParams(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const LAYER_COLORS = [
  "from-indigo-500 to-purple-500",
  "from-blue-500 to-cyan-500",
  "from-purple-500 to-pink-500",
  "from-emerald-500 to-teal-500",
  "from-amber-500 to-orange-500",
  "from-rose-500 to-red-500",
  "from-violet-500 to-indigo-500",
];

export function ModelArchitectureView({ api }: ModelArchitectureViewProps) {
  const [arch, setArch] = useState<ModelArchitecture | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchArch = async () => {
      try {
        const data = (await api.get("/ruh/architecture")) as Record<
          string,
          unknown
        >;
        setArch({
          ...data,
          architecture_layers: (data.architecture_layers ??
            []) as ModelArchitecture["architecture_layers"],
          components: (data.components ??
            []) as ModelArchitecture["components"],
        } as ModelArchitecture);
      } catch {
        setError("Failed to load architecture");
      } finally {
        setLoading(false);
      }
    };
    fetchArch();
  }, [api]);

  if (loading) {
    return (
      <div className="text-sm text-gray-400 animate-pulse py-4 text-center">
        Loading architecture...
      </div>
    );
  }

  if (error || !arch) {
    return (
      <div className="text-sm text-red-400 py-4 text-center">
        {error ?? "Architecture unavailable"}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Config overview */}
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
        {[
          { label: "Total Params", value: formatParams(arch.total_params) },
          { label: "Layers", value: arch.n_layers },
          { label: "d_model", value: arch.d_model },
          { label: "Heads", value: arch.n_heads },
          { label: "Roots", value: formatParams(arch.n_roots) },
          { label: "Patterns", value: arch.n_patterns },
          { label: "d_root", value: arch.d_root },
          { label: "Max Seq", value: arch.max_seq_len },
        ].map((item) => (
          <div
            key={item.label}
            className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-2.5 text-center border border-gray-100 dark:border-zinc-700/50"
          >
            <span className="block font-mono text-sm text-gray-900 dark:text-gray-100">
              {item.value}
            </span>
            <span className="block text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* Architecture flow diagram */}
      <div className="space-y-1">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Layer Stack
        </h4>

        <div className="relative">
          {/* Vertical connector line */}
          <div className="absolute left-5 top-4 bottom-4 w-0.5 bg-gradient-to-b from-purple-500 via-blue-500 to-emerald-500 opacity-30" />

          <div className="space-y-1.5">
            {/* Input */}
            <FlowNode
              label="Input"
              desc="Text → (root_id, pattern_id) pairs via Bayan tokenizer"
              color="from-gray-500 to-gray-600"
            />

            {/* Architecture layers */}
            {arch.architecture_layers.map((layer, idx) => (
              <FlowNode
                key={layer.name}
                label={layer.name}
                desc={layer.desc}
                color={LAYER_COLORS[idx % LAYER_COLORS.length]}
                params={arch.components[idx]?.params}
              />
            ))}

            {/* Output */}
            <FlowNode
              label="Output"
              desc="Root-space logits → decoded text"
              color="from-gray-500 to-gray-600"
            />
          </div>
        </div>
      </div>

      {/* Component details */}
      {arch.components.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
            Module Parameters
          </h4>
          <div className="space-y-1">
            {arch.components.map((comp) => {
              const pct =
                arch.total_params > 0
                  ? (comp.params / arch.total_params) * 100
                  : 0;
              return (
                <div
                  key={comp.name}
                  className="flex items-center gap-3 text-xs"
                >
                  <span className="w-32 text-gray-500 dark:text-gray-400 truncate text-right">
                    {comp.name}
                  </span>
                  <div className="flex-1 h-4 bg-gray-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full transition-all"
                      style={{ width: `${Math.max(pct, 1)}%` }}
                    />
                  </div>
                  <span className="w-20 font-mono text-gray-400 text-right">
                    {formatParams(comp.params)}
                  </span>
                  <span className="w-12 font-mono text-gray-400 text-right">
                    {pct.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function FlowNode({
  label,
  desc,
  color,
  params,
}: {
  label: string;
  desc: string;
  color: string;
  params?: number;
}) {
  return (
    <div className="flex items-start gap-3 pl-2">
      <div
        className={`w-6 h-6 rounded-full bg-gradient-to-br ${color} flex-shrink-0 mt-0.5 shadow-sm`}
      />
      <div className="flex-1 bg-gray-50 dark:bg-zinc-800/50 rounded-lg px-3 py-2 border border-gray-100 dark:border-zinc-700/50">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">
            {label}
          </span>
          {params !== undefined && (
            <span className="text-[10px] font-mono text-gray-400">
              {formatParams(params)} params
            </span>
          )}
        </div>
        <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
          {desc}
        </p>
      </div>
    </div>
  );
}
