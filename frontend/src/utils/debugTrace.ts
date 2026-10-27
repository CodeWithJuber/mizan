/** Shapes a debug comparison (base model vs MIZAN) and MIZAN's trace for display. */

import type { IsnadSummary } from "./isnad.ts";

export interface TraceSpan {
  id: string;
  parent: string | null;
  op: string;
  name: string;
  start_ms: number;
  duration_ms: number;
  status: string;
  attributes: Record<string, unknown>;
}

export interface ArmChecks {
  unsupported_numbers: string[];
  unbacked_action_claims: string[];
  abstained: boolean;
  characters: number;
}

export interface CompareChecks {
  intent: string;
  grounded: boolean;
  base: ArmChecks;
  mizan: ArmChecks;
  agreement?: { verified_values: string[]; base_states: string[]; share: number };
  quote?: {
    status: "matches" | "excerpt" | "close" | "differs" | "missing";
    coverage: number;
    precision: number;
    words: number;
    changed?: { source: string; given: string }[];
  };
  isnad?: { base: IsnadSummary; mizan: IsnadSummary };
  similarity: number;
  diff: string[];
}

export interface Badge {
  label: string;
  tone: "good" | "bad" | "warn" | "info";
}

const OP_LABELS: Record<string, string> = {
  understand: "Understood",
  plan: "Plan",
  invoke_agent: "Agent",
  execute_tool: "Tool",
  chat: "Model call",
  verify: "Check",
  learn: "Learned",
};

export function opLabel(span: Pick<TraceSpan, "op" | "name">): string {
  if (span.op === "chat" && span.name.startsWith("lisan.")) return "Lisan";
  return OP_LABELS[span.op] ?? span.op;
}

/** Spans in start order, each with its depth under its parent. */
export function spanTree(spans: TraceSpan[]): { span: TraceSpan; depth: number }[] {
  const ids = new Set(spans.map((span) => span.id));
  const children = new Map<string | null, TraceSpan[]>();
  for (const span of spans) {
    const parent = span.parent && ids.has(span.parent) ? span.parent : null;
    children.set(parent, [...(children.get(parent) ?? []), span]);
  }
  const ordered: { span: TraceSpan; depth: number }[] = [];
  const visit = (parent: string | null, depth: number) => {
    const level = [...(children.get(parent) ?? [])].sort((a, b) => a.start_ms - b.start_ms);
    for (const span of level) {
      ordered.push({ span, depth });
      visit(span.id, depth + 1);
    }
  };
  visit(null, 0);
  return ordered;
}

/** One line saying what a span did, from its attributes. */
export function spanSummary(span: TraceSpan): string {
  const a = span.attributes ?? {};
  switch (span.op) {
    case "understand":
      return `${span.name} · ${String(a.language ?? "")} · by ${String(a.by ?? "fahm")}`;
    case "execute_tool":
      return a.ok === false ? "failed" : a.source ? "authentic source" : "ran";
    case "verify":
      return a.accepted ? "passed" : `rejected: ${((a.problems as string[]) ?? []).join("; ")}`;
    case "chat": {
      const tokens = [a.input_tokens, a.output_tokens].filter((value) => value != null);
      return tokens.length ? `${tokens.join(" → ")} tokens` : "";
    }
    case "learn":
      return a.estimate != null ? `success estimate ${percent(Number(a.estimate))}` : "";
    default:
      return "";
  }
}

export const percent = (value: number) => `${Math.round(value * 100)}%`;

export function formatMs(ms: number | undefined): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function formatCost(cost: number | undefined, estimated?: boolean): string {
  if (cost == null) return "—";
  return `${estimated ? "~" : ""}$${cost < 0.01 ? cost.toFixed(5) : cost.toFixed(3)}`;
}

/** What MIZAN found in one arm's answer. */
export function armBadges(checks: CompareChecks, arm: "base" | "mizan"): Badge[] {
  const found = checks[arm];
  const badges: Badge[] = [];
  if (found.unsupported_numbers.length) {
    badges.push({
      label: `${found.unsupported_numbers.length} number(s) no fact supports`,
      tone: "bad",
    });
  }
  if (found.unbacked_action_claims.length) {
    badges.push({ label: "Claims an action with no receipt", tone: "bad" });
  }
  if (found.abstained) badges.push({ label: "Declined or unsure", tone: "warn" });
  if (arm === "base" && checks.agreement) {
    const { share } = checks.agreement;
    badges.push({
      label: `States ${percent(share)} of MIZAN's verified values`,
      tone: share === 1 ? "good" : share === 0 ? "bad" : "warn",
    });
  }
  if (arm === "base" && checks.quote) {
    const { status, coverage, changed } = checks.quote;
    const tones = {
      matches: "good",
      excerpt: "info",
      close: "warn",
      differs: "bad",
      missing: "warn",
    } as const;
    const words = {
      matches: "Quote matches the source",
      excerpt: `Quotes ${percent(coverage)} of the text, word for word`,
      close: `Quote has ${changed?.length ?? 0} wording change(s) from the source`,
      differs: "Quote differs from the source",
      missing: "No Arabic text quoted",
    };
    badges.push({ label: words[status], tone: tones[status] });
  }
  if (!badges.length && checks.grounded) badges.push({ label: "Nothing unsupported", tone: "good" });
  return badges;
}

/** Unified-diff lines marked for colouring. */
export function diffRows(diff: string[]): { text: string; kind: "add" | "del" | "hunk" | "same" }[] {
  return diff
    .filter((line) => !line.startsWith("---") && !line.startsWith("+++"))
    .map((text) => ({
      text,
      kind: text.startsWith("+")
        ? "add"
        : text.startsWith("-")
          ? "del"
          : text.startsWith("@@")
            ? "hunk"
            : "same",
    }));
}
