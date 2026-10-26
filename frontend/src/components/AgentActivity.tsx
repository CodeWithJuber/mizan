/**
 * AgentActivity — live timeline of what the agent is doing in this reply:
 * tool calls (with diffs), its todo plan, skill activations and approval
 * prompts the user answers inline (Izn: ask before acting).
 */
import { useState } from "react";
import {
  Check, ChevronDown, ChevronRight, ListTodo, LoaderCircle, ShieldAlert, Sparkles, X,
} from "lucide-react";
import {
  type AgentActivity as Activity, type ApprovalRequest, type ToolCall, toolLabel,
} from "../utils/agentActivity";

export type ApprovalDecision = "allow" | "deny" | "always";

interface Props {
  activity: Activity;
  onDecision?: (approvalId: string, decision: ApprovalDecision) => Promise<void> | void;
  /** History view: collapsed by default, no approval buttons. */
  compact?: boolean;
}

export function DiffView({ diff, maxLines = 400 }: { diff: string; maxLines?: number }) {
  const lines = diff.split("\n");
  const shown = lines.slice(0, maxLines);
  return (
    <pre className="text-xs font-mono overflow-x-auto rounded-md border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-950 p-2 max-h-80">
      {shown.map((line, index) => {
        const color = line.startsWith("+++") || line.startsWith("---")
          ? "text-gray-500"
          : line.startsWith("+")
            ? "text-emerald-700 dark:text-emerald-400 bg-emerald-50/60 dark:bg-emerald-950/40"
            : line.startsWith("-")
              ? "text-rose-700 dark:text-rose-400 bg-rose-50/60 dark:bg-rose-950/40"
              : line.startsWith("@@") ? "text-sky-700 dark:text-sky-400" : "text-gray-700 dark:text-zinc-300";
        return <div key={index} className={`${color} whitespace-pre`}>{line || " "}</div>;
      })}
      {lines.length > maxLines && <div className="text-gray-500">… {lines.length - maxLines} more lines</div>}
    </pre>
  );
}

function StatusIcon({ status }: { status: ToolCall["status"] }) {
  if (status === "running") return <LoaderCircle className="w-3.5 h-3.5 animate-spin text-amber-600" aria-label="running" />;
  if (status === "failed") return <X className="w-3.5 h-3.5 text-rose-600" aria-label="failed" />;
  return <Check className="w-3.5 h-3.5 text-emerald-600" aria-label="done" />;
}

function inputPreview(input: unknown): string {
  if (input == null) return "";
  try {
    const textValue = JSON.stringify(input, null, 2);
    return textValue.length > 4000 ? `${textValue.slice(0, 4000)}…` : textValue;
  } catch {
    return String(input);
  }
}

function ToolRow({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const expandable = !!(call.diff || call.summary || call.input);
  return (
    <li className="text-sm">
      <button
        type="button"
        onClick={() => expandable && setOpen((value) => !value)}
        className="w-full flex items-center gap-2 py-1 px-1 rounded hover:bg-gray-100 dark:hover:bg-zinc-800 text-left"
        aria-expanded={open}
      >
        {expandable ? (open ? <ChevronDown className="w-3.5 h-3.5 text-gray-400" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400" />) : <span className="w-3.5" />}
        <StatusIcon status={call.status} />
        <span className="font-mono text-xs truncate flex-1 text-gray-800 dark:text-zinc-200">{toolLabel(call)}</span>
        {call.durationMs != null && <span className="text-2xs text-gray-400 tabular-nums">{call.durationMs < 1000 ? `${call.durationMs}ms` : `${(call.durationMs / 1000).toFixed(1)}s`}</span>}
      </button>
      {open && (
        <div className="ml-7 mt-1 mb-2 space-y-2">
          {call.diff && <DiffView diff={call.diff} />}
          {!call.diff && call.input != null && (
            <pre className="text-xs font-mono whitespace-pre-wrap break-words rounded-md bg-gray-50 dark:bg-zinc-950 border border-gray-200 dark:border-zinc-700 p-2 max-h-48 overflow-auto">{inputPreview(call.input)}</pre>
          )}
          {call.summary && (
            <pre className="text-xs font-mono whitespace-pre-wrap break-words rounded-md bg-gray-50 dark:bg-zinc-950 border border-gray-200 dark:border-zinc-700 p-2 max-h-48 overflow-auto text-gray-600 dark:text-zinc-400">{call.summary}</pre>
          )}
        </div>
      )}
    </li>
  );
}

function ApprovalCard({ approval, onDecision }: { approval: ApprovalRequest; onDecision?: Props["onDecision"] }) {
  const [busy, setBusy] = useState(false);
  const input = (approval.input && typeof approval.input === "object" ? approval.input : {}) as Record<string, unknown>;
  const headline = typeof input.command === "string" ? input.command
    : typeof input.path === "string" ? input.path : "";
  const decide = async (decision: ApprovalDecision) => {
    if (!onDecision) return;
    setBusy(true);
    try { await onDecision(approval.approvalId, decision); } finally { setBusy(false); }
  };
  if (approval.decision) {
    return (
      <li className="text-xs text-gray-500 dark:text-zinc-400 flex items-center gap-2 px-1">
        <ShieldAlert className="w-3.5 h-3.5" />
        {approval.tool}: {approval.decision === "deny" ? "declined" : approval.decision === "always" ? "allowed for this chat" : "allowed"}
      </li>
    );
  }
  return (
    <li className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 p-3" role="alert">
      <div className="flex items-start gap-2">
        <ShieldAlert className="w-4 h-4 mt-0.5 text-amber-600 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
            Allow <span className="font-mono">{approval.tool}</span>?
          </p>
          {headline && <p className="mt-1 text-xs font-mono break-all text-amber-900/80 dark:text-amber-100/80">{headline}</p>}
          {approval.reason && <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">{approval.reason}</p>}
          <details className="mt-1">
            <summary className="text-2xs cursor-pointer text-amber-800/80 dark:text-amber-300/80">Details</summary>
            <pre className="mt-1 text-xs font-mono whitespace-pre-wrap break-words max-h-40 overflow-auto">{inputPreview(approval.input)}</pre>
          </details>
          {onDecision && (
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={() => decide("allow")} className="btn-primary btn-sm">Allow</button>
              <button type="button" disabled={busy} onClick={() => decide("always")} className="btn-secondary btn-sm">Always in this chat</button>
              <button type="button" disabled={busy} onClick={() => decide("deny")} className="btn-danger btn-sm">Deny</button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

export default function AgentActivity({ activity, onDecision, compact = false }: Props) {
  const [open, setOpen] = useState(!compact);
  const running = activity.tools.filter((t) => t.status === "running").length;
  const done = activity.todos.filter((t) => t.status === "completed").length;
  const pending = activity.approvals.filter((a) => !a.decision);
  return (
    <section className="my-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/70 text-sm" aria-label="Agent activity">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
        {open ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
        <span className="font-medium text-gray-700 dark:text-zinc-200">Activity</span>
        <span className="text-xs text-gray-500">
          {activity.tools.length} step{activity.tools.length === 1 ? "" : "s"}
          {activity.todos.length > 0 && ` · plan ${done}/${activity.todos.length}`}
          {running > 0 && " · working"}
        </span>
        {pending.length > 0 && <span className="ml-auto badge-warning">Needs your approval</span>}
      </button>
      {(open || pending.length > 0) && (
        <div className="px-3 pb-3 space-y-3">
          {activity.skills.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {activity.skills.map((name) => (
                <span key={name} className="inline-flex items-center gap-1 rounded-full bg-mizan-gold/10 text-mizan-gold-text dark:text-mizan-gold px-2 py-0.5 text-xs">
                  <Sparkles className="w-3 h-3" /> {name}
                </span>
              ))}
            </div>
          )}
          {activity.todos.length > 0 && (
            <div>
              <p className="flex items-center gap-1 text-xs font-medium text-gray-500 mb-1"><ListTodo className="w-3.5 h-3.5" /> Plan</p>
              <ul className="space-y-0.5">
                {activity.todos.map((todo, index) => (
                  <li key={index} className={`flex items-start gap-2 text-sm ${todo.status === "completed" ? "text-gray-400 line-through" : todo.status === "in_progress" ? "text-amber-700 dark:text-amber-400 font-medium" : "text-gray-700 dark:text-zinc-300"}`}>
                    <span className="mt-0.5">{todo.status === "completed" ? "☑" : todo.status === "in_progress" ? "◐" : "☐"}</span>
                    <span>{todo.content}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {activity.approvals.length > 0 && (
            <ul className="space-y-2">
              {activity.approvals.map((approval) => (
                <ApprovalCard key={approval.approvalId} approval={approval} onDecision={compact ? undefined : onDecision} />
              ))}
            </ul>
          )}
          {open && activity.tools.length > 0 && (
            <ul className="divide-y divide-gray-100 dark:divide-zinc-800">
              {activity.tools.map((call) => <ToolRow key={call.callId} call={call} />)}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
