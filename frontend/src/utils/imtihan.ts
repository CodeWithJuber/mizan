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
};

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
