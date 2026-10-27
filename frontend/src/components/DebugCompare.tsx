/**
 * Debug mode (Muqabala): one message to the base model alone and to MIZAN,
 * side by side, with every step MIZAN took and what MIZAN found in each answer.
 */

import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../types";
import { Markdown } from "./Markdown";
import {
  armBadges,
  diffRows,
  formatCost,
  formatMs,
  opLabel,
  spanSummary,
  spanTree,
  type Badge,
  type CompareChecks,
  type TraceSpan,
} from "../utils/debugTrace.ts";

interface Usage {
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  cost_estimated?: boolean;
}

interface Arm {
  text: string;
  error: string | null;
  usage: Usage;
  latency_ms?: number;
  model_calls?: number;
  lisan_calls?: number;
  tool_calls?: number;
  spans?: TraceSpan[];
  verified?: boolean;
  completion_status?: string;
  system?: string;
}

interface Run {
  id: string;
  prompt: string;
  model: string | null;
  agent: string | null;
  base: Arm;
  mizan: Arm;
  checks: CompareChecks;
}

interface RunSummary {
  id: string;
  created_at: number;
  prompt: string;
  intent: string | null;
  mizan_verified: boolean;
  base_unsupported: number;
  quote: string | null;
}

const TONES: Record<Badge["tone"], string> = {
  good: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  bad: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30",
  warn: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
  info: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30",
};

function Badges({ badges }: { badges: Badge[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {badges.map((badge) => (
        <span
          key={badge.label}
          className={`text-[11px] px-2 py-0.5 rounded-full border ${TONES[badge.tone]}`}
        >
          {badge.label}
        </span>
      ))}
    </div>
  );
}

function QuoteChanges({ changes }: { changes: { source: string; given: string }[] }) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-gray-500">Where the quote differs from the source</summary>
      <table className="mt-2 w-full table-fixed border-collapse">
        <thead>
          <tr className="text-gray-500">
            <th className="text-left font-normal pb-1">Source (MIZAN)</th>
            <th className="text-left font-normal pb-1">Base model wrote</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change, index) => (
            <tr key={index} className="align-top border-t border-gray-100 dark:border-zinc-800">
              <td dir="rtl" className="py-1 pr-2 break-words text-emerald-700 dark:text-emerald-400">
                {change.source}
              </td>
              <td dir="rtl" className="py-1 break-words text-red-600 dark:text-red-400">
                {change.given}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-gray-500">Marks and letter forms are ignored when comparing.</p>
    </details>
  );
}

function ArmCard({ title, subtitle, arm, badges, quoteChanges }: {
  title: string;
  subtitle: string;
  arm: Arm;
  badges: Badge[];
  quoteChanges?: { source: string; given: string }[];
}) {
  const stats = [
    arm.usage?.model ?? null,
    arm.usage?.input_tokens != null
      ? `${arm.usage.input_tokens} → ${arm.usage.output_tokens ?? 0} tokens`
      : null,
    arm.usage?.cost_usd != null ? formatCost(arm.usage.cost_usd, arm.usage.cost_estimated) : null,
    formatMs(arm.latency_ms),
    `${arm.model_calls ?? 0} model call(s)`,
    `${arm.tool_calls ?? 0} tool(s)`,
  ].filter(Boolean);
  return (
    <div className="card p-4 flex flex-col gap-3 min-w-0">
      <div>
        <div className="flex items-center gap-2">
          <h3 className="font-semibold">{title}</h3>
          {arm.verified && (
            <span className="text-[11px] px-2 py-0.5 rounded-full border bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30">
              Verified by MIZAN
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500">{subtitle}</p>
      </div>
      <Badges badges={badges} />
      {quoteChanges && quoteChanges.length > 0 && <QuoteChanges changes={quoteChanges} />}
      <div className="text-sm min-w-0 break-words">
        {arm.error ? (
          <div className="text-red-500">{arm.error}</div>
        ) : arm.text ? (
          <Markdown content={arm.text} />
        ) : (
          <div className="text-gray-500">No answer</div>
        )}
      </div>
      <div className="text-[11px] text-gray-500 flex flex-wrap gap-x-3 gap-y-1 border-t border-gray-200 dark:border-zinc-800 pt-2">
        {stats.map((item) => (
          <span key={String(item)}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function SpanRow({ span, depth }: { span: TraceSpan; depth: number }) {
  const [open, setOpen] = useState(false);
  const a = span.attributes ?? {};
  const prompts = span.name.startsWith("lisan.");
  return (
    <div style={{ paddingLeft: `${depth * 16}px` }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full text-left flex items-center gap-2 py-1 text-sm hover:bg-gray-100 dark:hover:bg-zinc-800/60 rounded px-1"
        aria-expanded={open}
      >
        <span className="text-[10px] uppercase tracking-wide text-gray-500 w-20 shrink-0">
          {opLabel(span)}
        </span>
        <span className={`font-mono truncate ${span.status === "error" ? "text-red-500" : ""}`}>
          {span.name}
        </span>
        <span className="text-xs text-gray-500 truncate">{spanSummary(span)}</span>
        <span className="ml-auto text-xs text-gray-500 shrink-0">
          {span.duration_ms ? formatMs(span.duration_ms) : ""}
        </span>
      </button>
      {open && (
        <div className="ml-20 mb-2 space-y-2">
          {prompts ? (
            <>
              {(["system", "user", "reply"] as const).map((key) => (
                <div key={key}>
                  <div className="text-[10px] uppercase tracking-wide text-gray-500">
                    {key === "user" ? "Prompt" : key === "reply" ? "Lisan's reply" : "Instructions"}
                  </div>
                  <pre className="text-xs whitespace-pre-wrap bg-gray-50 dark:bg-zinc-900 rounded p-2 max-h-64 overflow-auto">
                    {String(a[key] ?? "")}
                  </pre>
                </div>
              ))}
            </>
          ) : (
            <pre className="text-xs whitespace-pre-wrap bg-gray-50 dark:bg-zinc-900 rounded p-2 max-h-64 overflow-auto">
              {JSON.stringify(a, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function DebugCompare({
  api,
  initialPrompt,
  onPromptUsed,
}: {
  api: ApiClient;
  initialPrompt?: string;
  onPromptUsed?: () => void;
}) {
  const [prompt, setPrompt] = useState(initialPrompt ?? "");
  const [mode, setMode] = useState<"auto" | "plan">("auto");
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [view, setView] = useState<"trace" | "diff">("trace");

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.get("/debug/runs");
      setHistory((data.runs as RunSummary[]) ?? []);
    } catch {
      setHistory([]);
    }
  }, [api]);

  const compare = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      setBusy(true);
      setError("");
      try {
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const data = await api.post("/debug/compare", {
          prompt: text,
          permission_mode: mode,
          ...(timezone ? { timezone } : {}),
        });
        setRun(data as unknown as Run);
        loadHistory();
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "The comparison could not run");
      } finally {
        setBusy(false);
      }
    },
    [api, mode, loadHistory],
  );

  useEffect(() => {
    api
      .get("/debug/status")
      .then((data) => setEnabled(Boolean(data.enabled)))
      .catch(() => setEnabled(false));
    loadHistory();
  }, [api, loadHistory]);

  useEffect(() => {
    if (initialPrompt && enabled) {
      setPrompt(initialPrompt);
      onPromptUsed?.();
      compare(initialPrompt);
    }
    // Run once for a prompt sent from the chat.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrompt, enabled]);

  const open = async (id: string) => {
    try {
      setRun((await api.get(`/debug/runs/${id}`)) as unknown as Run);
    } catch {
      setError("That comparison could not be loaded");
    }
  };

  if (enabled === false) {
    return (
      <div className="card p-4 text-sm text-gray-500">
        Debug mode is off for this account. An admin can turn it on in Settings → System
        settings → Debug mode.
      </div>
    );
  }

  const tree = run ? spanTree(run.mizan.spans ?? []) : [];
  return (
    <div className="space-y-4">
      <div className="card p-4 space-y-3">
        <textarea
          className="w-full min-h-24 rounded-lg border border-gray-200 dark:border-zinc-700 bg-transparent p-3 text-sm"
          placeholder="One message, e.g. 2**100, Ayatul Kursi sunao, Bukhari 1"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) compare(prompt);
          }}
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !prompt.trim()}
            onClick={() => compare(prompt)}
          >
            {busy ? "Comparing…" : "Compare"}
          </button>
          <label className="text-xs text-gray-500 flex items-center gap-2">
            MIZAN's tools
            <select
              className="rounded border border-gray-200 dark:border-zinc-700 bg-transparent px-2 py-1"
              value={mode}
              onChange={(event) => setMode(event.target.value as "auto" | "plan")}
            >
              <option value="auto">Run what it chooses</option>
              <option value="plan">Read-only</option>
            </select>
          </label>
          <span className="text-xs text-gray-500">
            The model is called twice. Nothing is saved to your chats.
          </span>
        </div>
        {error && <div className="text-sm text-red-500">{error}</div>}
      </div>

      {run && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <ArmCard
              title="Base model"
              subtitle={`${run.model ?? "model"} alone: plain prompt, no tools, no memory`}
              arm={run.base}
              badges={armBadges(run.checks, "base")}
              quoteChanges={run.checks.quote?.changed}
            />
            <ArmCard
              title="MIZAN"
              subtitle={`Understood as ${run.checks.intent}; the model is only its language faculty`}
              arm={run.mizan}
              badges={armBadges(run.checks, "mizan")}
            />
          </div>
          <div className="card p-4 space-y-3">
            <div className="flex items-center gap-2">
              {(["trace", "diff"] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setView(key)}
                  className={`text-sm px-3 py-1 rounded-full border whitespace-nowrap ${view === key ? "border-amber-500 text-amber-600 dark:text-amber-400" : "border-gray-200 dark:border-zinc-700 text-gray-500"}`}
                >
                  {key === "trace" ? `Steps (${tree.length})` : "Difference"}
                </button>
              ))}
              <span className="ml-auto text-xs text-gray-500">
                Similarity {Math.round(run.checks.similarity * 100)}%
              </span>
            </div>
            {view === "trace" ? (
              <div className="overflow-x-auto">
                {tree.length ? (
                  tree.map(({ span, depth }) => <SpanRow key={span.id} span={span} depth={depth} />)
                ) : (
                  <div className="text-sm text-gray-500">No steps recorded</div>
                )}
              </div>
            ) : (
              <pre className="text-xs overflow-x-auto">
                {diffRows(run.checks.diff).map((row, index) => (
                  <div
                    key={index}
                    className={
                      row.kind === "add"
                        ? "text-emerald-600 dark:text-emerald-400"
                        : row.kind === "del"
                          ? "text-red-600 dark:text-red-400"
                          : row.kind === "hunk"
                            ? "text-sky-600 dark:text-sky-400"
                            : "text-gray-500"
                    }
                  >
                    {row.text}
                  </div>
                ))}
              </pre>
            )}
          </div>
        </>
      )}

      {history.length > 0 && (
        <div className="card p-4">
          <div className="flex items-center mb-2">
            <h3 className="font-semibold text-sm">Recent comparisons</h3>
            <button
              type="button"
              className="ml-auto text-xs text-gray-500 underline"
              onClick={async () => {
                await api.del("/debug/runs");
                loadHistory();
              }}
            >
              Clear
            </button>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-zinc-800">
            {history.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => open(item.id)}
                className="w-full text-left py-2 flex items-center gap-2 text-sm hover:bg-gray-50 dark:hover:bg-zinc-800/50"
              >
                <span className="truncate">{item.prompt}</span>
                <span className="ml-auto text-xs text-gray-500 shrink-0">{item.intent}</span>
                {item.mizan_verified && <span className="text-xs text-emerald-500 shrink-0">verified</span>}
                {item.base_unsupported > 0 && (
                  <span className="text-xs text-red-500 shrink-0">base: {item.base_unsupported} unsupported</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
