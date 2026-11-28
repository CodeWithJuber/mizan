/** Small pieces the connectors page shares: status dot, tone badges, the clock. */
import { useSyncExternalStore, type ReactNode } from "react";
import { BadgeCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { STATUS_META, type Tone } from "./logic";
import type { ConnectorStatus } from "./types";

const DOT: Record<Tone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  destructive: "bg-destructive",
  info: "bg-info",
  muted: "bg-muted-foreground/50",
};

const TONE_BADGE: Record<Tone, string> = {
  success: "border-success/30 bg-success/10 text-foreground",
  warning: "border-warning/40 bg-warning/12 text-foreground",
  destructive: "border-destructive/30 bg-destructive/10 text-destructive",
  info: "border-info/30 bg-info/10 text-foreground",
  muted: "border-border bg-muted text-muted-foreground",
};

export function Dot({ tone, pulse = false, className }: { tone: Tone; pulse?: boolean; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone], pulse && "animate-pulse", className)} />;
}

export function StatusPill({ status }: { status: ConnectorStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={cn("inline-flex h-5 items-center gap-1.5 rounded-full border px-2 text-xs font-medium", TONE_BADGE[meta.tone])}>
      <Dot tone={meta.tone} pulse={status === "connecting"} />
      {meta.label}
    </span>
  );
}

export function ToneBadge({ tone, children, className, title }: { tone: Tone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full border px-2 text-xs font-medium whitespace-nowrap", TONE_BADGE[tone], className)}>
      {children}
    </span>
  );
}

export function OfficialBadge() {
  return (
    <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-primary/15 px-2 text-xs font-medium text-brand">
      <BadgeCheck className="size-3" aria-hidden /> Official
    </span>
  );
}

// One clock for every "expires in …" on the page, ticking while something reads it.
let clock = Date.now();
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(listener: () => void) {
  listeners.add(listener);
  clock = Date.now();
  timer ??= setInterval(() => {
    clock = Date.now();
    listeners.forEach((notify) => notify());
  }, 30_000);
  return () => {
    listeners.delete(listener);
    if (!listeners.size && timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

export const useNow = () => useSyncExternalStore(subscribe, () => clock);
