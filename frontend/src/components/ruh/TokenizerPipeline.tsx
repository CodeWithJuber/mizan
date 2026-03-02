/**
 * TokenizerPipeline — Step-by-step visualization of the Bayan tokenizer
 * Shows how text flows through: language detection → morphology → root extraction
 * → pattern matching → Q28 features → final tokens
 */

import { useState } from "react";
import type { ApiClient } from "../../types";
import type { TokenizeResult, TokenizationStep } from "../../types/ruh";

interface TokenizerPipelineProps {
  api: ApiClient;
}

const PHASE_INFO: Record<string, { label: string; icon: string; color: string }> = {
  language_detection: { label: "Language Detection", icon: "🌐", color: "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-400" },
  morphology: { label: "Morphological Analysis", icon: "🔬", color: "bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400" },
  id_mapping: { label: "Root/Pattern ID Mapping", icon: "🔢", color: "bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-400" },
  articulatory_features: { label: "Q28 Articulatory Features", icon: "🎯", color: "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  final_tokens: { label: "Final Token Pairs", icon: "✅", color: "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400" },
};

export function TokenizerPipeline({ api }: TokenizerPipelineProps) {
  const [input, setInput] = useState("");
  const [result, setResult] = useState<TokenizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);

  const handleTokenize = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setExpandedPhase(null);

    try {
      const data = await api.post("/ruh/tokenize", { text: input, detailed: true });
      setResult(data as unknown as TokenizeResult);
      // Auto-expand first step
      const pipeline = (data as unknown as TokenizeResult).pipeline;
      if (pipeline && pipeline.length > 0) {
        setExpandedPhase(pipeline[0].phase);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tokenization failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Tokenizer Pipeline Explorer
        </h4>
        <p className="text-xs text-gray-400 mb-3">
          Enter Arabic or English text to see how the Bayan tokenizer processes it step by step.
        </p>
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleTokenize()}
          placeholder="Type Arabic (كتب الطالب الدرس) or English (the student wrote)..."
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500/30 focus:border-purple-400"
          dir="auto"
        />
        <button
          onClick={handleTokenize}
          disabled={loading || !input.trim()}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
        >
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {/* Quick result summary */}
      {result && (
        <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-zinc-800/50 rounded-lg border border-gray-100 dark:border-zinc-700/50">
          <span className="text-xs text-gray-500">
            <strong className="text-gray-700 dark:text-gray-300">{result.token_count}</strong> tokens
          </span>
          <div className="flex flex-wrap gap-1">
            {result.tokens.map(([rootId, patternId], idx) => (
              <span
                key={idx}
                className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-500/20"
              >
                ({rootId},{patternId})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Pipeline steps */}
      {result?.pipeline && (
        <div className="space-y-2">
          {/* Vertical pipeline connector */}
          <div className="relative">
            {result.pipeline.map((step, idx) => (
              <PipelineStep
                key={step.phase}
                step={step}
                index={idx}
                total={result.pipeline!.length}
                expanded={expandedPhase === step.phase}
                onToggle={() =>
                  setExpandedPhase(expandedPhase === step.phase ? null : step.phase)
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* Per-word analysis */}
      {result && result.analysis.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Per-Word Analysis
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-400 uppercase tracking-wider">
                  <th className="text-left py-1.5 px-2">Word</th>
                  <th className="text-left py-1.5 px-2">Root</th>
                  <th className="text-left py-1.5 px-2">Pattern</th>
                  <th className="text-left py-1.5 px-2">Meaning</th>
                </tr>
              </thead>
              <tbody>
                {result.analysis.map((item, idx) => (
                  <tr key={idx} className="border-t border-gray-100 dark:border-zinc-700/50">
                    <td className="py-1.5 px-2 font-medium text-gray-800 dark:text-gray-200" dir="auto">
                      {String(item.surface)}
                    </td>
                    <td className="py-1.5 px-2 font-mono text-purple-600 dark:text-purple-400" dir="auto">
                      {String(item.root) || "—"}
                    </td>
                    <td className="py-1.5 px-2">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${
                        item.is_stopword
                          ? "bg-gray-100 dark:bg-zinc-700/30 text-gray-400"
                          : "bg-indigo-100 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-400"
                      }`}>
                        {String(item.pattern)}
                      </span>
                    </td>
                    <td className="py-1.5 px-2 text-gray-500 dark:text-gray-400">
                      {String(item.root_meaning)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function PipelineStep({
  step,
  index,
  total,
  expanded,
  onToggle,
}: {
  step: TokenizationStep;
  index: number;
  total: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const info = PHASE_INFO[step.phase] ?? {
    label: step.phase,
    icon: "⚡",
    color: "bg-gray-100 dark:bg-zinc-700/30 text-gray-700 dark:text-gray-300",
  };

  return (
    <div className="mb-2">
      {/* Step connector arrow */}
      {index > 0 && (
        <div className="flex justify-center py-0.5">
          <svg className="w-4 h-4 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
          </svg>
        </div>
      )}

      <button
        onClick={onToggle}
        className={`w-full text-left rounded-lg border transition-colors ${
          expanded
            ? "border-purple-300 dark:border-purple-500/30 bg-purple-50/50 dark:bg-purple-500/5"
            : "border-gray-100 dark:border-zinc-700/50 bg-gray-50 dark:bg-zinc-800/50 hover:bg-gray-100 dark:hover:bg-zinc-700/30"
        }`}
      >
        <div className="flex items-center gap-3 px-3 py-2.5">
          <span className={`px-2 py-1 rounded text-xs font-medium ${info.color}`}>
            {info.icon} {info.label}
          </span>
          <span className="flex-1 text-[10px] text-gray-400">{step.description}</span>
          <span className="text-xs text-gray-400 font-mono">{index + 1}/{total}</span>
          <svg
            className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="mt-1 ml-4 mr-1 p-3 bg-white dark:bg-zinc-900 rounded-lg border border-gray-100 dark:border-zinc-700/50 overflow-x-auto">
          <StepOutput phase={step.phase} output={step.output} />
        </div>
      )}
    </div>
  );
}

function StepOutput({ phase, output }: { phase: string; output: unknown }) {
  if (!output || (Array.isArray(output) && output.length === 0)) {
    return <p className="text-xs text-gray-400 italic">No data</p>;
  }

  // Language detection
  if (phase === "language_detection" && Array.isArray(output)) {
    return (
      <div className="flex flex-wrap gap-2">
        {(output as Array<{ word: string; language: string; is_stopword: boolean }>).map((item, idx) => (
          <span
            key={idx}
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs border ${
              item.language === "arabic"
                ? "bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20 text-blue-700 dark:text-blue-400"
                : "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-400"
            } ${item.is_stopword ? "opacity-50" : ""}`}
            dir="auto"
          >
            <span className="font-medium">{item.word}</span>
            <span className="text-[10px] opacity-70">
              {item.language === "arabic" ? "AR" : "EN"}
              {item.is_stopword ? " · stop" : ""}
            </span>
          </span>
        ))}
      </div>
    );
  }

  // Morphology
  if (phase === "morphology" && Array.isArray(output)) {
    return (
      <div className="space-y-1">
        {(output as Array<{ word: string; type: string; root: string; pattern: string }>).map((item, idx) => (
          <div key={idx} className="flex items-center gap-3 text-xs py-1 border-b border-gray-50 dark:border-zinc-800 last:border-0">
            <span className="w-20 font-medium text-gray-800 dark:text-gray-200" dir="auto">{item.word}</span>
            <span className="text-gray-400">→</span>
            <span className="font-mono text-purple-600 dark:text-purple-400" dir="auto">{item.root || "—"}</span>
            <span className="px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 text-[10px]">
              {item.pattern}
            </span>
            <span className="text-[10px] text-gray-400">{item.type}</span>
          </div>
        ))}
      </div>
    );
  }

  // ID mapping
  if (phase === "id_mapping" && Array.isArray(output)) {
    return (
      <div className="flex flex-wrap gap-2">
        {(output as Array<{ word: string; root_id: number; pattern_id: number; root: string; pattern: string }>).map((item, idx) => (
          <div key={idx} className="bg-gray-50 dark:bg-zinc-800 rounded px-2 py-1.5 text-xs border border-gray-100 dark:border-zinc-700/50">
            <span className="font-medium text-gray-700 dark:text-gray-300" dir="auto">{item.word}</span>
            <div className="flex items-center gap-1 mt-0.5 font-mono text-[10px] text-gray-400">
              <span>root:{item.root_id}</span>
              <span>pat:{item.pattern_id}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Q28 features
  if (phase === "articulatory_features" && Array.isArray(output)) {
    const dims = ["place", "manner", "voicing", "nasality", "emphasis", "length"];
    return (
      <div className="space-y-2">
        {(output as Array<{ word: string; features: number[][]; dimensions?: string[] }>).map((item, idx) => (
          <div key={idx} className="space-y-1">
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300" dir="auto">{item.word}</span>
            {item.features.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {item.features.slice(0, 8).map((feat, fidx) => (
                  <div key={fidx} className="flex gap-0.5">
                    {feat.map((val, didx) => (
                      <div
                        key={didx}
                        className="w-4 h-4 rounded-sm text-[8px] flex items-center justify-center"
                        style={{
                          backgroundColor: `rgba(139, 92, 246, ${typeof val === "number" ? val : 0})`,
                          color: (typeof val === "number" ? val : 0) > 0.5 ? "#fff" : "#9ca3af",
                        }}
                        title={`${dims[didx] ?? `d${didx}`}: ${typeof val === "number" ? val.toFixed(2) : val}`}
                      />
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-[10px] text-gray-400 italic">No articulatory data</span>
            )}
          </div>
        ))}
        <div className="flex gap-2 mt-1">
          {dims.map((dim) => (
            <span key={dim} className="text-[8px] text-gray-400 uppercase">{dim}</span>
          ))}
        </div>
      </div>
    );
  }

  // Final tokens
  if (phase === "final_tokens" && Array.isArray(output)) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {(output as Array<{ root_id: number; pattern_id: number }>).map((tok, idx) => (
          <span
            key={idx}
            className={`inline-flex items-center px-2 py-1 rounded text-xs font-mono border ${
              tok.root_id <= 2
                ? "bg-gray-100 dark:bg-zinc-700/30 border-gray-200 dark:border-zinc-700 text-gray-400"
                : "bg-purple-50 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20 text-purple-700 dark:text-purple-300"
            }`}
          >
            ({tok.root_id}, {tok.pattern_id})
            {tok.root_id === 1 && <span className="ml-1 text-[10px] text-gray-400">BOS</span>}
            {tok.root_id === 2 && <span className="ml-1 text-[10px] text-gray-400">EOS</span>}
          </span>
        ))}
      </div>
    );
  }

  // Fallback: JSON
  return (
    <pre className="text-[10px] font-mono text-gray-500 dark:text-gray-400 max-h-48 overflow-auto">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}
