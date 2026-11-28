/**
 * One place for what MIZAN is doing on a reply: thinking, tool steps (with
 * diffs), the plan, skills and approval prompts. While a reply runs it is the
 * only progress indicator; afterwards it folds into "Worked 12s · 5 steps"
 * above the answer.
 */
import { useEffect, useState } from "react";
import {
  Check, ChevronRight, ListTodo, LoaderCircle, ShieldAlert, Sparkles, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DiffView, type ApprovalDecision } from "../../components/AgentActivity";
import {
  type AgentActivity, type ApprovalRequest, type ToolCall, allowedLabel, toolLabel,
} from "../../utils/agentActivity";
import { phaseLabel } from "../../utils/chatRecovery.ts";
import type { ThinkingTrace } from "../../types/ruh";
import type { RunProgress } from "./ChatProvider";
import { ElicitationPrompt } from "./ElicitationPrompt";
import type { ElicitationAction } from "../../utils/elicitation";

function seconds(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function useElapsed(startedAt: number | undefined): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!startedAt) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  return startedAt ? now - startedAt : 0;
}

function inputPreview(input: unknown): string {
  if (input == null) return "";
  try {
    const text = JSON.stringify(input, null, 2);
    return text.length > 4000 ? `${text.slice(0, 4000)}…` : text;
  } catch {
    return String(input);
  }
}

function ToolStep({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(call.diff || call.summary || call.input);
  return (
    <li>
      <button
        type="button"
        onClick={() => expandable && setOpen((value) => !value)}
        aria-expanded={expandable ? open : undefined}
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-sm",
          expandable && "hover:bg-muted",
        )}
      >
        {call.status === "running" ? (
          <LoaderCircle className="size-3.5 shrink-0 animate-spin text-brand" aria-label="running" />
        ) : call.status === "failed" ? (
          <X className="size-3.5 shrink-0 text-destructive" aria-label="failed" />
        ) : (
          <Check className="size-3.5 shrink-0 text-success" aria-label="done" />
        )}
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground/85">{toolLabel(call)}</span>
        {call.durationMs != null && (
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {call.durationMs < 1000 ? `${call.durationMs}ms` : `${(call.durationMs / 1000).toFixed(1)}s`}
          </span>
        )}
        {expandable && (
          <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
        )}
      </button>
      {open && (
        <div className="mb-2 ml-6 mt-1 space-y-2">
          {call.diff && <DiffView diff={call.diff} />}
          {!call.diff && call.input != null && (
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/50 p-2 font-mono text-xs">
              {inputPreview(call.input)}
            </pre>
          )}
          {call.summary && (
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/50 p-2 font-mono text-xs text-muted-foreground">
              {call.summary}
            </pre>
          )}
        </div>
      )}
    </li>
  );
}

export function ApprovalPrompt({
  approval,
  onDecision,
}: {
  approval: ApprovalRequest;
  onDecision?: (approvalId: string, decision: ApprovalDecision) => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const input = (approval.input && typeof approval.input === "object" ? approval.input : {}) as Record<string, unknown>;
  const headline = typeof input.command === "string" ? input.command : typeof input.path === "string" ? input.path : "";
  const diff = approval.preview?.diff ?? (typeof input.diff === "string" ? input.diff : "");
  if (approval.decision) {
    return (
      <li className="flex items-center gap-2 px-1.5 text-xs text-muted-foreground">
        <ShieldAlert className="size-3.5" />
        <span title={approval.tool}>{allowedLabel(approval.tool)}</span>
        {approval.decision === "deny" ? "declined" : approval.decision === "always" ? "allowed for this chat"
          : approval.decision === "expired" ? "expired" : "allowed"}
      </li>
    );
  }
  const decide = async (decision: ApprovalDecision) => {
    if (!onDecision) return;
    setBusy(true);
    try {
      await onDecision(approval.approvalId, decision);
    } finally {
      setBusy(false);
    }
  };
  return (
    <li role="alert" className="rounded-lg border border-primary/50 bg-primary/8 p-3">
      <div className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-brand" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            Allow <span title={approval.tool}>{allowedLabel(approval.tool)}</span>?
          </p>
          {headline && <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{headline}</p>}
          {approval.reason && <p className="mt-1 text-xs text-muted-foreground">{approval.reason}</p>}
          {(approval.preview?.newFile || approval.preview?.truncated) && (
            <p className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
              {approval.preview.newFile && <span className="badge-info">New file</span>}
              {approval.preview.truncated && (
                <span className="text-muted-foreground">The change is long; only its start is shown here.</span>
              )}
            </p>
          )}
          {diff && <div className="mt-2"><DiffView diff={diff} maxLines={120} /></div>}
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-muted-foreground">Details</summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">
              {inputPreview(approval.input)}
            </pre>
          </details>
          {onDecision && (
            <div className="mt-2.5 flex flex-wrap gap-2">
              <Button size="sm" disabled={busy} onClick={() => decide("allow")}>Allow</Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => decide("always")}>
                Always in this chat
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => decide("deny")}>Deny</Button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

const PHASES: Record<string, string> = {
  perception: "Reading",
  comprehension: "Understanding",
  reasoning: "Reasoning",
  memory: "Remembering",
  evaluation: "Weighing",
  generation: "Writing",
  reflection: "Checking",
};

interface Props {
  activity?: AgentActivity;
  trace?: ThinkingTrace;
  /** Present while the reply runs. */
  progress?: RunProgress | null;
  awaitingText?: boolean;
  onDecision?: (approvalId: string, decision: ApprovalDecision) => Promise<void> | void;
  onElicitation?: (id: string, action: ElicitationAction, content?: Record<string, unknown>) => Promise<void> | void;
}

export function RunTimeline({ activity, trace, progress, awaitingText, onDecision, onElicitation }: Props) {
  const live = Boolean(progress);
  const [open, setOpen] = useState(false);
  const elapsed = useElapsed(progress?.startedAt);
  const tools = activity?.tools ?? [];
  const todos = activity?.todos ?? [];
  const skills = activity?.skills ?? [];
  const approvals = activity?.approvals ?? [];
  const elicitations = activity?.elicitations ?? [];
  const steps = trace?.steps ?? [];
  const pending = approvals.filter((item) => !item.decision);
  const asking = elicitations.filter((item) => !item.decision);
  const running = tools.find((tool) => tool.status === "running");
  const stepCount = tools.length + steps.length;
  const hasDetail = stepCount > 0 || todos.length > 0 || skills.length > 0;

  if (!live && !hasDetail && approvals.length === 0 && elicitations.length === 0) return null;

  const label = live
    ? pending.length
      ? "Waiting for your approval"
      : asking.length
        ? "Waiting for your answer"
        : progress?.note
        ?? (running ? `Using ${toolLabel(running)}` : steps.length && awaitingText
          ? `${PHASES[steps[steps.length - 1].phase] ?? "Thinking"}…`
          : awaitingText ? `${phaseLabel(progress?.phase)}…` : "Writing…")
    : [
        trace?.duration_ms ? `Worked ${seconds(trace.duration_ms)}` : "Worked",
        stepCount ? `${stepCount} step${stepCount === 1 ? "" : "s"}` : "",
        todos.length ? `plan ${todos.filter((todo) => todo.status === "completed").length}/${todos.length}` : "",
      ].filter(Boolean).join(" · ");

  return (
    <section aria-label={live ? "MIZAN is working" : "How MIZAN worked"} className="mb-2 text-sm">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((value) => !value)}
        aria-expanded={hasDetail ? open : undefined}
        className={cn(
          "inline-flex max-w-full items-center gap-2 rounded-md py-1 pr-2 text-left text-muted-foreground",
          hasDetail && "hover:text-foreground",
        )}
      >
        {live ? (
          <LoaderCircle className="size-4 shrink-0 animate-spin text-brand" />
        ) : (
          <Check className="size-4 shrink-0" />
        )}
        <span className={cn("truncate", live && "shimmer-text")}>{label}</span>
        {live && <span className="shrink-0 tabular-nums text-xs">{seconds(elapsed)}</span>}
        {hasDetail && <ChevronRight className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")} />}
      </button>
      <span className="sr-only" aria-live="polite">{live ? "" : "Finished"}</span>

      {open && hasDetail && (
        <div className="ml-2 mt-1 space-y-3 border-l pl-4">
          {skills.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {skills.map((name) => (
                <span key={name} className="inline-flex items-center gap-1 rounded-full bg-primary/12 px-2 py-0.5 text-xs text-brand">
                  <Sparkles className="size-3" /> {name}
                </span>
              ))}
            </div>
          )}
          {steps.length > 0 && (
            <ol className="space-y-1.5">
              {steps.map((step) => (
                <li key={step.id} className="text-sm">
                  <span className="mr-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {PHASES[step.phase] ?? step.phase}
                  </span>
                  <span className="text-foreground/80">{step.content}</span>
                </li>
              ))}
            </ol>
          )}
          {todos.length > 0 && (
            <div>
              <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <ListTodo className="size-3.5" /> Plan
              </p>
              <ul className="space-y-0.5">
                {todos.map((todo, index) => (
                  <li
                    key={index}
                    className={cn(
                      "flex items-start gap-2",
                      todo.status === "completed" && "text-muted-foreground line-through",
                      todo.status === "in_progress" && "font-medium text-brand",
                    )}
                  >
                    <span className="mt-0.5 text-xs">{todo.status === "completed" ? "☑" : todo.status === "in_progress" ? "◐" : "☐"}</span>
                    <span>{todo.content}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {tools.length > 0 && <ul className="space-y-0.5">{tools.map((call) => <ToolStep key={call.callId} call={call} />)}</ul>}
        </div>
      )}

      {approvals.length > 0 && (live || approvals.some((item) => item.decision)) && (
        <ul className="mt-2 space-y-2">
          {approvals.map((approval) => (
            <ApprovalPrompt key={approval.approvalId} approval={approval} onDecision={live ? onDecision : undefined} />
          ))}
        </ul>
      )}

      {elicitations.length > 0 && (live || elicitations.some((item) => item.decision)) && (
        <ul className="mt-2 space-y-2">
          {elicitations.map((request) => (
            <ElicitationPrompt key={request.id} request={request} onAnswer={live ? onElicitation : undefined} />
          ))}
        </ul>
      )}
    </section>
  );
}
