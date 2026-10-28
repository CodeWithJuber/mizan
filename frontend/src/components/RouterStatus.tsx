/**
 * RouterStatus — Provider routing decision indicator
 * Compact badge showing which LLM provider is handling the current request,
 * with confidence level and a tooltip explaining the routing reason.
 */

import { useState } from "react";
import type { RouterDecision } from "../types/ruh";

// ===== Provider color mapping =====

const PROVIDER_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  anthropic: {
    bg: "bg-amber-50 dark:bg-amber-500/10",
    text: "text-amber-700 dark:text-amber-400",
    border: "border-amber-200 dark:border-amber-500/20",
  },
  openrouter: {
    bg: "bg-blue-50 dark:bg-blue-500/10",
    text: "text-blue-700 dark:text-blue-400",
    border: "border-blue-200 dark:border-blue-500/20",
  },
  openai: {
    bg: "bg-green-50 dark:bg-green-500/10",
    text: "text-green-700 dark:text-green-400",
    border: "border-green-200 dark:border-green-500/20",
  },
  ollama: {
    bg: "bg-purple-50 dark:bg-purple-500/10",
    text: "text-purple-700 dark:text-purple-400",
    border: "border-purple-200 dark:border-purple-500/20",
  },
};

const DEFAULT_STYLE = {
  bg: "bg-muted/60",
  text: "text-foreground/80",
  border: "border-border",
};

function getProviderStyle(provider: string) {
  const key = provider.toLowerCase();
  return PROVIDER_STYLES[key] ?? DEFAULT_STYLE;
}

function ConfidenceDot({ confidence }: { confidence: number }) {
  const color =
    confidence >= 0.8
      ? "bg-emerald-500"
      : confidence >= 0.5
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <span
      className={`w-1.5 h-1.5 rounded-full ${color}`}
      title={`Routing confidence: ${Math.round(confidence * 100)}%`}
    />
  );
}

// ===== Main Component =====

interface RouterStatusProps {
  decision: RouterDecision | null;
  compact?: boolean;
}

export function RouterStatus({ decision, compact = false }: RouterStatusProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (!decision) return null;

  const style = getProviderStyle(decision.provider);

  // Extract short model name from full identifier
  const shortModel = decision.model.includes("/")
    ? decision.model.split("/").pop() ?? decision.model
    : decision.model;

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border ${style.bg} ${style.text} ${style.border} font-mono`}
        title={`${decision.provider}: ${decision.model} (${Math.round(decision.confidence * 100)}%) - ${decision.reason}`}
      >
        <ConfidenceDot confidence={decision.confidence} />
        {decision.provider}
      </span>
    );
  }

  return (
    <div className="relative inline-block">
      <button
        className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border ${style.bg} ${style.text} ${style.border} font-mono transition-colors hover:opacity-80 cursor-pointer`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onFocus={() => setShowTooltip(true)}
        onBlur={() => setShowTooltip(false)}
        aria-label={`Routed to ${decision.provider} using ${decision.model}. Reason: ${decision.reason}`}
      >
        <ConfidenceDot confidence={decision.confidence} />
        <span className="font-medium">{decision.provider}</span>
        <span className="text-muted-foreground/80">/</span>
        <span className="truncate max-w-[120px]">{shortModel}</span>
      </button>

      {/* Tooltip */}
      {showTooltip && (
        <div
          role="tooltip"
          className="absolute z-dropdown bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2.5 rounded-lg border border-border bg-card shadow-lg animate-fade-in"
        >
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground/80">
                Routing Decision
              </span>
              <span className="text-xs font-mono text-muted-foreground/80">
                {Math.round(decision.confidence * 100)}%
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">Model:</span>{" "}
              <span className="font-mono">{decision.model}</span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {decision.reason}
            </p>
          </div>
          {/* Tooltip arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px">
            <div className="w-2 h-2 bg-card border-r border-b border-border transform rotate-45" />
          </div>
        </div>
      )}
    </div>
  );
}
