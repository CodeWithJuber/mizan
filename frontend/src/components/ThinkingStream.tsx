/**
 * ThinkingStream — Expandable thinking trace visualization
 * Shows a collapsible timeline of cognitive processing steps
 * with phase-coded colors and confidence indicators.
 */

import { useState, useEffect, useRef } from "react";
import type { ThinkingTrace, ThinkingStep, ThinkingPhase } from "../types/ruh";

// ===== Phase Configuration =====

interface PhaseConfig {
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
  icon: string;
}

const PHASE_CONFIG: Record<ThinkingPhase, PhaseConfig> = {
  perception: {
    label: "Perception",
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
    borderColor: "border-blue-500/30",
    icon: "M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",
  },
  comprehension: {
    label: "Comprehension",
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/10",
    borderColor: "border-cyan-500/30",
    icon: "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z",
  },
  reasoning: {
    label: "Reasoning",
    color: "text-purple-400",
    bgColor: "bg-purple-500/10",
    borderColor: "border-purple-500/30",
    icon: "M13 10V3L4 14h7v7l9-11h-7z",
  },
  memory: {
    label: "Memory",
    color: "text-green-400",
    bgColor: "bg-green-500/10",
    borderColor: "border-green-500/30",
    icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  },
  evaluation: {
    label: "Evaluation",
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/10",
    borderColor: "border-yellow-500/30",
    icon: "M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3",
  },
  generation: {
    label: "Generation",
    color: "text-orange-400",
    bgColor: "bg-orange-500/10",
    borderColor: "border-orange-500/30",
    icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
  },
  reflection: {
    label: "Reflection",
    color: "text-pink-400",
    bgColor: "bg-pink-500/10",
    borderColor: "border-pink-500/30",
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  },
};

// ===== Sub-components =====

function PhaseIcon({ phase, className }: { phase: ThinkingPhase; className?: string }) {
  const config = PHASE_CONFIG[phase];
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`${config.color} ${className ?? "w-4 h-4"}`}
      aria-hidden="true"
    >
      <path d={config.icon} />
    </svg>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const percentage = Math.round(confidence * 100);
  const barColor =
    confidence >= 0.7
      ? "bg-emerald-500"
      : confidence >= 0.4
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <div className="flex items-center gap-1.5" title={`Confidence: ${percentage}%`}>
      <div className="w-16 h-1 bg-gray-200 dark:bg-zinc-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-xs font-mono text-gray-400 dark:text-gray-500 tabular-nums">
        {percentage}%
      </span>
    </div>
  );
}

function StepItem({ step }: { step: ThinkingStep }) {
  const config = PHASE_CONFIG[step.phase];

  return (
    <div className="flex gap-3 animate-fade-in">
      {/* Timeline dot + line */}
      <div className="flex flex-col items-center">
        <div
          className={`w-7 h-7 rounded-full ${config.bgColor} border ${config.borderColor} flex items-center justify-center shrink-0`}
        >
          <PhaseIcon phase={step.phase} className="w-3.5 h-3.5" />
        </div>
        <div className="w-px flex-1 bg-gray-200 dark:bg-zinc-700 mt-1" />
      </div>

      {/* Content */}
      <div className="pb-4 flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-semibold uppercase tracking-wider ${config.color}`}>
            {config.label}
          </span>
          <ConfidenceBar confidence={step.confidence} />
        </div>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
          {step.content}
        </p>
      </div>
    </div>
  );
}

function AnimatedDots() {
  return (
    <span className="inline-flex gap-0.5 ml-1">
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="w-1 h-1 bg-current rounded-full animate-pulse-slow"
          style={{ animationDelay: `${index * 200}ms` }}
        />
      ))}
    </span>
  );
}

function TraceSummary({ trace }: { trace: ThinkingTrace }) {
  const durationDisplay =
    trace.duration_ms < 1000
      ? `${trace.duration_ms}ms`
      : `${(trace.duration_ms / 1000).toFixed(1)}s`;

  return (
    <div className="flex items-center gap-3 pt-2 border-t border-gray-100 dark:border-zinc-800 mt-2">
      <span className="text-xs text-gray-400 dark:text-gray-500">
        {trace.steps.length} steps
      </span>
      <span className="text-xs text-gray-300 dark:text-gray-600">|</span>
      <span className="text-xs text-gray-400 dark:text-gray-500">{durationDisplay}</span>
      <span className="text-xs text-gray-300 dark:text-gray-600">|</span>
      <span className="text-xs text-gray-400 dark:text-gray-500">
        Avg confidence: {Math.round(trace.avg_confidence * 100)}%
      </span>
    </div>
  );
}

// ===== Main Component =====

interface ThinkingStreamProps {
  trace: ThinkingTrace | null;
  isStreaming?: boolean;
}

export function ThinkingStream({ trace, isStreaming = false }: ThinkingStreamProps) {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest step during streaming
  useEffect(() => {
    if (expanded && isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [expanded, isStreaming, trace?.steps.length]);

  if (!trace && !isStreaming) return null;

  const steps = trace?.steps ?? [];
  const hasSteps = steps.length > 0;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-zinc-700/50 bg-gray-50 dark:bg-zinc-900/50 overflow-hidden animate-fade-in">
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-zinc-800/50 transition-colors cursor-pointer"
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse thinking trace" : "Expand thinking trace"}
      >
        {/* Chevron */}
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-4 h-4 text-gray-400 transition-transform duration-200 shrink-0 ${expanded ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>

        <span className="text-sm text-gray-600 dark:text-gray-300 font-medium">
          {isStreaming ? (
            <>
              Thinking
              <AnimatedDots />
            </>
          ) : (
            `Thought for ${trace ? (trace.duration_ms < 1000 ? `${trace.duration_ms}ms` : `${(trace.duration_ms / 1000).toFixed(1)}s`) : "..."}`
          )}
        </span>

        {hasSteps && !expanded && (
          <span className="ml-auto text-xs text-gray-400 dark:text-gray-500 font-mono">
            {steps.length} steps
          </span>
        )}
      </button>

      {/* Expandable content */}
      {expanded && (
        <div
          ref={scrollRef}
          className="px-3 pb-3 max-h-80 overflow-y-auto"
        >
          {hasSteps ? (
            <>
              <div className="space-y-0 pt-1">
                {steps.map((step) => (
                  <StepItem key={step.id} step={step} />
                ))}
              </div>
              {trace && !isStreaming && <TraceSummary trace={trace} />}
            </>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500 py-2">
              Waiting for thinking steps...
            </p>
          )}
        </div>
      )}
    </div>
  );
}
