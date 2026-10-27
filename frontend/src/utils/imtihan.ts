/** Shapes an Imtihan (AGI test) run for display. */

export type Arm = "base" | "mizan";

export interface ArmBlock {
  scored: number;
  errors: number;
  passed: number;
  rate: number | null;
  interval: [number, number];
  pass_at_1: number | null;
  pass_all: number | null;
}

export interface BlockEntry {
  tasks: number;
  base: ArmBlock;
  mizan: ArmBlock;
  delta: number | null;
}

export interface Report {
  blocks: Record<string, BlockEntry>;
  index: Record<Arm, { score: number | null; pooled: number | null; interval: [number, number] }>;
  calibration: Record<Arm, { ece: number | null; brier: number | null; answers_with_confidence: number; answers: number }>;
  consistency: Record<Arm, { groups: number; consistent: number; rate: number | null }>;
  isnad?: Record<Arm, { supported: number | null; fabricated_claims: number }>;
  cost: Record<Arm, { input_tokens: number; output_tokens: number; cost_usd: number | null; latency_ms: number; model_calls: number; tool_calls: number }>;
  /** Categories weighted like the Artificial Analysis index (agents 30, coding 20, …). */
  weighted?: {
    categories: Record<string, { weight: number; blocks: string[]; base: number | null; mizan: number | null }>;
    base: number | null;
    mizan: number | null;
  };
  /** Agentic tasks: success and the four dimensions, per arm. */
  agentic?: Partial<Record<Arm, AgenticSummary>>;
  /** Interactive games (ARC-AGI-3 style): levels won and action efficiency, per arm. */
  games?: Partial<Record<Arm, GamesSummary>>;
}

export interface GamesSummary {
  games: number;
  won: number;
  levels: number;
  efficiency: number;
  actions: number;
  model_calls: number;
}

/** One arm of an agentic task or a game, as the drill-down shows it. */
export interface PlainArm {
  title: string;
  text: string;
  checks: { label: string; pass: boolean }[];
  calls: string[];
  final?: string;
}

/** Agentic tasks and games keep both arms' text, checks and calls (not a debug trace). */
export function plainArms(compare: unknown): { prompt: string; arms: PlainArm[] } | null {
  if (!compare || typeof compare !== "object") return null;
  const value = compare as { prompt?: string; agentic?: Record<string, unknown>; game?: Record<string, unknown> };
  const source = value.agentic ?? value.game;
  if (!source) return null;
  const arms: PlainArm[] = [];
  for (const [arm, title] of [["base", "Base model alone"], ["mizan", "MIZAN"]] as const) {
    const data = source[arm] as
      | { text?: string; final?: string; objectives?: { check: string; pass: boolean }[]; calls?: { name: string; error?: string | null }[] }
      | undefined;
    if (!data) continue;
    arms.push({
      title,
      text: data.text ?? "",
      final: data.final,
      checks: (data.objectives ?? []).map((item) => ({ label: item.check, pass: item.pass })),
      calls: (data.calls ?? []).map((call) => (call.error ? `${call.name} (failed: ${call.error})` : call.name)),
    });
  }
  return { prompt: value.prompt ?? "", arms };
}

export function gameRows(report: Report) {
  const base = report.games?.base;
  const mizan = report.games?.mizan;
  if (!base && !mizan) return [];
  const count = (s?: GamesSummary) => (s ? `${s.won}/${s.games}` : "—");
  return [
    { label: "Games won (every level)", base: count(base), mizan: count(mizan) },
    { label: "Levels won", base: pct(base?.levels), mizan: pct(mizan?.levels) },
    { label: "Action efficiency (optimal ÷ used)", base: pct(base?.efficiency), mizan: pct(mizan?.efficiency) },
    { label: "Actions taken", base: String(base?.actions ?? "—"), mizan: String(mizan?.actions ?? "—") },
    { label: "Model calls", base: String(base?.model_calls ?? "—"), mizan: String(mizan?.model_calls ?? "—") },
  ];
}

export interface AgenticSummary {
  tasks: number;
  success: number;
  objectives: number;
  tool_accuracy: number | null;
  groundedness: number | null;
  recovery: number | null;
  guardrail_violations: number;
  latency_median_ms: number | null;
  tool_calls: number;
}

export interface ResultRow {
  task_id: string;
  block: string;
  arm: Arm;
  attempt: number;
  pass: boolean;
  detail?: string;
  error?: string;
}

export interface RunSummary {
  id: string;
  created_at: number;
  status: string;
  model: string | null;
  repeats: number | null;
  blocks: string[] | null;
  index: Report["index"] | null;
  progress?: { done: number; total: number; current?: string };
  /** Shown on the public reliability page. */
  published?: boolean;
}

export const BLOCK_LABELS: Record<string, string> = {
  exactness: "Exact answers",
  scripture: "Quran & hadith verbatim",
  abstention: "False premises",
  honesty: "Honesty when tools fail",
  injection: "Prompt injection",
  knowledge: "Truthfulness (TruthfulQA)",
  consistency: "Paraphrase consistency",
  multilingual: "Hinglish, Urdu, Arabic, Hindi",
  learning: "Learning from the chat",
  safety: "Safety without over-refusal (XSTest)",
  code: "Write and run code",
  arc: "Abstract reasoning (ARC-AGI-2)",
  agent_tools: "Agent: work on files",
  agent_coding: "Agent: fix and extend code",
  agent_web: "Agent: find it on a page",
  agent_recovery: "Agent: recover from failures",
  agent_guardrail: "Agent: keep to the request",
  games: "Interactive games (ARC-AGI-3 style)",
  locked_eval: "Your locked eval (mizan-eval-v1)",
};

export const CATEGORY_LABELS: Record<string, string> = {
  agents: "Agents",
  coding: "Coding",
  reasoning: "Reasoning",
  general: "General knowledge & honesty",
};

/** The weighted index's categories, largest weight first. */
export function categoryRows(report: Report) {
  return Object.entries(report.weighted?.categories ?? {})
    .map(([key, entry]) => ({ key, label: CATEGORY_LABELS[key] ?? key, ...entry }))
    .sort((a, b) => b.weight - a.weight);
}

/** The agentic dimensions as rows; ``higher`` says which way is better. */
export function agenticRows(report: Report) {
  const base = report.agentic?.base;
  const mizan = report.agentic?.mizan;
  if (!base && !mizan) return [];
  const ms = (value: number | null | undefined) => (value == null ? "—" : `${(value / 1000).toFixed(1)} s`);
  const rows: { label: string; base: string; mizan: string; higher: boolean }[] = [
    { label: "Tasks passed (final state)", base: pct(base?.success), mizan: pct(mizan?.success), higher: true },
    { label: "Objectives met", base: pct(base?.objectives), mizan: pct(mizan?.objectives), higher: true },
    { label: "Tool-call accuracy", base: pct(base?.tool_accuracy), mizan: pct(mizan?.tool_accuracy), higher: true },
    { label: "Groundedness (numbers from evidence)", base: pct(base?.groundedness), mizan: pct(mizan?.groundedness), higher: true },
    { label: "Recovery after a failure", base: pct(base?.recovery), mizan: pct(mizan?.recovery), higher: true },
    {
      label: "Guardrail violations",
      base: String(base?.guardrail_violations ?? "—"),
      mizan: String(mizan?.guardrail_violations ?? "—"),
      higher: false,
    },
    { label: "Median time per task", base: ms(base?.latency_median_ms), mizan: ms(mizan?.latency_median_ms), higher: false },
  ];
  return rows;
}

export const pct = (value: number | null | undefined) =>
  value == null ? "—" : `${Math.round(value * 100)}%`;

export const signed = (value: number | null | undefined) =>
  value == null ? "—" : `${value >= 0 ? "+" : ""}${Math.round(value * 100)} pts`;

export const intervalText = ([low, high]: [number, number]) =>
  `95% interval ${Math.round(low * 100)}–${Math.round(high * 100)}%`;

export function blockRows(report: Report) {
  return Object.entries(report.blocks).map(([block, entry]) => ({
    block,
    label: BLOCK_LABELS[block] ?? block,
    ...entry,
  }));
}

/** Completed runs, oldest first, for the history chart. */
export function historyPoints(runs: RunSummary[]) {
  return runs
    .filter((run) => run.status === "complete" && run.index)
    .sort((a, b) => a.created_at - b.created_at)
    .map((run) => ({
      id: run.id,
      label: new Date(run.created_at * 1000).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      }),
      base: run.index!.base.score == null ? null : Math.round(run.index!.base.score * 100),
      mizan: run.index!.mizan.score == null ? null : Math.round(run.index!.mizan.score * 100),
    }));
}

/** One row per task: passes per arm across attempts, and the first attempt's detail. */
export function taskRows(results: ResultRow[], tasks: { id: string; block: string; prompt: string }[]) {
  return tasks.map((task) => {
    const arms = {} as Record<Arm, { passed: number; scored: number; detail: string; error: boolean }>;
    for (const arm of ["base", "mizan"] as Arm[]) {
      const rows = results.filter((row) => row.task_id === task.id && row.arm === arm);
      const scored = rows.filter((row) => !row.error);
      const first = rows.find((row) => row.attempt === 1);
      arms[arm] = {
        passed: scored.filter((row) => row.pass).length,
        scored: scored.length,
        detail: first?.error ?? first?.detail ?? "",
        error: rows.length > 0 && scored.length === 0,
      };
    }
    return { ...task, ...arms };
  });
}
